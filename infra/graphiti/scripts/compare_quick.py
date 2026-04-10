"""
Quick comparison: Voyage (already imported) vs Nomic (import + query).
Queries both graph groups and prints side-by-side results.
"""

import asyncio
import json
import os
import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig, ModelSize
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.embedder.voyage import VoyageAIEmbedder, VoyageAIEmbedderConfig
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.nodes import EpisodeType
import json as json_mod
import numpy as np


# ── Clients ──────────────────────────────────────────────────────────────────

class DeepSeekClient(OpenAIGenericClient):
    async def _generate_response(self, messages, response_model=None, max_tokens=8192, model_size=ModelSize.medium):
        from openai.types.chat import ChatCompletionMessageParam
        openai_messages = []
        for m in messages:
            m.content = self._clean_input(m.content)
            if m.role == 'user':
                openai_messages.append({'role': 'user', 'content': m.content})
            elif m.role == 'system':
                openai_messages.append({'role': 'system', 'content': m.content})
        if response_model is not None:
            schema = response_model.model_json_schema()
            schema_instruction = f"\n\nRespond with valid JSON matching this schema:\n```json\n{json_mod.dumps(schema, indent=2)}\n```\nRespond ONLY with the JSON object."
            for i, msg in enumerate(openai_messages):
                if msg['role'] == 'system':
                    openai_messages[i] = {'role': 'system', 'content': str(msg['content']) + schema_instruction}
                    break
            else:
                openai_messages.insert(0, {'role': 'system', 'content': schema_instruction})
        response = await self.client.chat.completions.create(
            model=self.model, messages=openai_messages,
            temperature=self.temperature, max_tokens=self.max_tokens,
            response_format={'type': 'json_object'},
        )
        return json_mod.loads(response.choices[0].message.content or '{}')


class PassthroughReranker(CrossEncoderClient):
    async def rank(self, query, passages):
        return [(p, 1.0 - i * 0.01) for i, p in enumerate(passages)]


from graphiti_core.embedder.client import EmbedderClient
from abc import ABC


class NomicEmbedder(EmbedderClient):
    """Graphiti-compatible wrapper around HuggingFace transformers pipeline."""
    def __init__(self):
        self._pipe = None

    def _load(self):
        if not self._pipe:
            os.environ['TOKENIZERS_PARALLELISM'] = 'false'
            print("  Loading Nomic model...", flush=True)
            from transformers import pipeline
            self._pipe = pipeline('feature-extraction', 'nomic-ai/nomic-embed-text-v1.5')
            print("  Nomic ready.", flush=True)
        return self._pipe

    def _embed_one(self, text: str) -> list[float]:
        pipe = self._load()
        output = pipe(text, return_tensors=False)
        arr = np.array(output[0])
        mean = arr.mean(axis=0)
        norm = mean / (np.linalg.norm(mean) + 1e-10)
        return norm.tolist()[:768]

    async def create(self, input_data, **kwargs) -> list[float]:
        if isinstance(input_data, str):
            return self._embed_one(input_data)
        elif isinstance(input_data, list) and len(input_data) > 0 and isinstance(input_data[0], str):
            return self._embed_one(input_data[0])
        return self._embed_one(str(input_data))

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in input_data_list]


# ── Test content ─────────────────────────────────────────────────────────────

def get_test_content():
    sys.path.insert(0, 'scripts')
    from bulk_import import parse_dump
    notes = parse_dump('/tmp/mikai_notes_all.txt')
    apple_note = next((n for n in notes if 'David and the Dao' in n['name']), None)

    db = sqlite3.connect(str(Path.home() / '.mikai' / 'mikai.db'))
    db.row_factory = sqlite3.Row
    perplexity = db.execute("SELECT label, raw_content, created_at FROM sources WHERE source='perplexity' AND label LIKE '%MIKA%REMY%' LIMIT 1").fetchone()
    claude = db.execute("SELECT label, raw_content, created_at FROM sources WHERE source='claude-thread' AND label LIKE '%invisible%knowledge%' LIMIT 1").fetchone()
    db.close()

    content = []
    if apple_note:
        content.append({'name': f"apple-notes: {apple_note['name']}", 'body': apple_note['body'][:5000], 'date': apple_note['date']})
    if perplexity:
        content.append({'name': f"perplexity: {perplexity['label'][:60]}", 'body': perplexity['raw_content'][:5000], 'date': perplexity['created_at'] or '2026-01-01T00:00:00Z'})
    if claude:
        content.append({'name': f"claude: {claude['label'][:60]}", 'body': claude['raw_content'][:5000], 'date': claude['created_at'] or '2026-01-01T00:00:00Z'})
    return content


# ── Neo4j queries ────────────────────────────────────────────────────────────

async def query_group(graphiti, group_id, queries):
    """Query a group and return structured results."""
    driver = graphiti.driver

    # Entities
    result = await driver.execute_query(
        f"MATCH (e:Entity) WHERE e.group_id = '{group_id}' RETURN e.name AS name, e.summary AS summary ORDER BY e.name LIMIT 30"
    )
    entities = [(r['name'], (r['summary'] or '')[:100]) for r in result.records]

    # Edges
    result = await driver.execute_query(
        f"MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.group_id = '{group_id}' RETURN a.name AS src, r.name AS rel, b.name AS tgt, r.fact AS fact LIMIT 20"
    )
    edges = [(r['src'], r['rel'], r['tgt'], (r['fact'] or '')[:80]) for r in result.records]

    # Search
    search_results = {}
    for q in queries:
        try:
            results = await graphiti.search(query=q, group_ids=[group_id], num_results=3)
            search_results[q] = [e.fact[:100] for e in results]
        except Exception as e:
            search_results[q] = [f"ERROR: {e}"]

    return {"entities": entities, "edges": edges, "search": search_results}


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "mikai-local-dev")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    voyage_key = os.environ.get("VOYAGE_API_KEY")

    content = get_test_content()
    print(f"Test content: {len(content)} pieces\n", flush=True)

    llm = DeepSeekClient(
        config=LLMConfig(api_key=deepseek_key, model="deepseek-chat", small_model="deepseek-chat", base_url="https://api.deepseek.com"),
        max_tokens=8192,
    )

    queries = [
        "What is MIKAI and what does Brian want to build?",
        "Brian's philosophical views on technology",
        "AI knowledge architecture and memory",
    ]

    # ── Step 1: Query existing Voyage results ────────────────────────────────
    print("=" * 60, flush=True)
    print("QUERYING VOYAGE GROUP (already imported)", flush=True)
    print("=" * 60, flush=True)

    voyage_embedder = VoyageAIEmbedder(config=VoyageAIEmbedderConfig(api_key=voyage_key, model="voyage-3"))
    g_voyage = Graphiti(neo4j_uri, neo4j_user, neo4j_password, llm_client=llm, embedder=voyage_embedder, cross_encoder=PassthroughReranker())
    await g_voyage.build_indices_and_constraints()
    voyage_results = await query_group(g_voyage, "comparison-voyage", queries)
    await g_voyage.close()

    print(f"  Entities: {len(voyage_results['entities'])}", flush=True)
    print(f"  Edges: {len(voyage_results['edges'])}", flush=True)

    # ── Step 2: Import with Nomic + query ────────────────────────────────────
    print(f"\n{'=' * 60}", flush=True)
    print("IMPORTING WITH NOMIC EMBEDDINGS", flush=True)
    print("=" * 60, flush=True)

    nomic_embedder = NomicEmbedder()
    g_nomic = Graphiti(neo4j_uri, neo4j_user, neo4j_password, llm_client=llm, embedder=nomic_embedder, cross_encoder=PassthroughReranker())
    await g_nomic.build_indices_and_constraints()

    for i, c in enumerate(content):
        print(f"  [{i+1}/{len(content)}] {c['name'][:50]}...", flush=True)
        try:
            ref_time = datetime.fromisoformat(c['date'].replace('Z', '+00:00')) if c['date'] else datetime.now(timezone.utc)
            result = await g_nomic.add_episode(
                name=c['name'], episode_body=c['body'],
                source=EpisodeType.text, source_description=c['name'],
                reference_time=ref_time, group_id="comparison-nomic",
            )
            print(f"    OK: {len(result.nodes or [])} nodes, {len(result.edges or [])} edges", flush=True)
        except Exception as e:
            print(f"    ERROR: {e}", flush=True)
        await asyncio.sleep(5)

    print(f"\n  Querying Nomic group...", flush=True)
    nomic_results = await query_group(g_nomic, "comparison-nomic", queries)
    await g_nomic.close()

    print(f"  Entities: {len(nomic_results['entities'])}", flush=True)
    print(f"  Edges: {len(nomic_results['edges'])}", flush=True)

    # ── Step 3: Print comparison ─────────────────────────────────────────────
    print(f"\n\n{'=' * 80}", flush=True)
    print("SIDE-BY-SIDE COMPARISON", flush=True)
    print(f"{'=' * 80}\n", flush=True)

    # Entities
    v_names = set(e[0] for e in voyage_results['entities'])
    n_names = set(e[0] for e in nomic_results['entities'])
    shared = v_names & n_names

    print(f"ENTITIES:", flush=True)
    print(f"  Voyage: {len(voyage_results['entities'])}", flush=True)
    print(f"  Nomic:  {len(nomic_results['entities'])}", flush=True)
    print(f"  Shared: {len(shared)}", flush=True)
    if v_names - n_names:
        print(f"  Voyage only ({len(v_names - n_names)}): {list(v_names - n_names)[:10]}", flush=True)
    if n_names - v_names:
        print(f"  Nomic only ({len(n_names - v_names)}): {list(n_names - v_names)[:10]}", flush=True)

    # Edges
    print(f"\nEDGES:", flush=True)
    print(f"  Voyage: {len(voyage_results['edges'])}", flush=True)
    for src, rel, tgt, fact in voyage_results['edges'][:5]:
        print(f"    {src} →{rel}→ {tgt}: {fact}", flush=True)
    print(f"  Nomic: {len(nomic_results['edges'])}", flush=True)
    for src, rel, tgt, fact in nomic_results['edges'][:5]:
        print(f"    {src} →{rel}→ {tgt}: {fact}", flush=True)

    # Search
    print(f"\nSEARCH RESULTS:", flush=True)
    for q in queries:
        print(f"\n  Query: '{q}'", flush=True)
        print(f"  Voyage:", flush=True)
        for fact in voyage_results['search'].get(q, []):
            print(f"    • {fact}", flush=True)
        print(f"  Nomic:", flush=True)
        for fact in nomic_results['search'].get(q, []):
            print(f"    • {fact}", flush=True)

    print(f"\n{'=' * 80}", flush=True)
    print("COMPARISON COMPLETE", flush=True)


if __name__ == "__main__":
    env_path = Path(__file__).parent.parent.parent.parent / '.env.local'
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, _, val = line.partition('=')
            if key and val and key not in os.environ:
                os.environ[key] = val
    asyncio.run(main())
