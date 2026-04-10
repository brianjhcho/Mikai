"""
embedding_comparison.py

Side-by-side comparison of Voyage vs Nomic embeddings on the same content.
Imports 3 test episodes into two separate graph groups, one per embedder.
Then queries both and compares entity resolution + search quality.

Usage:
    python scripts/embedding_comparison.py
"""

import asyncio
import json
import os
import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Add parent for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig, ModelSize, DEFAULT_MAX_TOKENS
from graphiti_core.llm_client.client import Message
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.embedder.voyage import VoyageAIEmbedder, VoyageAIEmbedderConfig
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.nodes import EpisodeType
import json as json_mod


# ── DeepSeek client (same as sidecar) ────────────────────────────────────────

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
            schema_instruction = (
                f"\n\nYou MUST respond with valid JSON matching this exact schema:\n"
                f"```json\n{json_mod.dumps(schema, indent=2)}\n```\n"
                f"Respond ONLY with the JSON object, no other text."
            )
            injected = False
            for i, msg in enumerate(openai_messages):
                if msg['role'] == 'system':
                    openai_messages[i] = {'role': 'system', 'content': str(msg['content']) + schema_instruction}
                    injected = True
                    break
            if not injected:
                openai_messages.insert(0, {'role': 'system', 'content': schema_instruction})

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={'type': 'json_object'},
        )
        result = response.choices[0].message.content or '{}'
        return json_mod.loads(result)


class PassthroughReranker(CrossEncoderClient):
    async def rank(self, query, passages):
        return [(p, 1.0 - i * 0.01) for i, p in enumerate(passages)]


# ── Nomic local embedder (wraps MIKAI's existing local embeddings) ───────────

class NomicLocalEmbedder:
    """Graphiti-compatible embedder using Nomic ONNX (768-dim)."""

    def __init__(self):
        self._pipe = None

    async def _get_pipe(self):
        if not self._pipe:
            from transformers import pipeline, AutoTokenizer
            import os
            os.environ['TOKENIZERS_PARALLELISM'] = 'false'
            print("  Loading Nomic embedding model...", flush=True)
            self._pipe = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: __import__('transformers').pipeline(
                    'feature-extraction', 'nomic-ai/nomic-embed-text-v1.5', dtype='float32'
                )
            )
            print("  Nomic model ready.", flush=True)
        return self._pipe

    async def create(self, input_data: list[str], **kwargs) -> list[list[float]]:
        pipe = await self._get_pipe()
        results = []
        for text in input_data:
            output = await asyncio.get_event_loop().run_in_executor(
                None, lambda t=text: pipe(t, return_tensors=False)
            )
            # Mean pooling
            import numpy as np
            arr = np.array(output[0])
            mean = arr.mean(axis=0)
            norm = mean / np.linalg.norm(mean)
            results.append(norm.tolist()[:768])
        return results


# ── Test content ─────────────────────────────────────────────────────────────

def get_test_content():
    """Get the 3 test pieces of content."""
    # Apple Note: from dump
    sys.path.insert(0, 'scripts')
    from bulk_import import parse_dump
    notes = parse_dump('/tmp/mikai_notes_all.txt')
    apple_note = next((n for n in notes if 'David and the Dao' in n['name']), None)

    # Perplexity + Claude: from SQLite
    db = sqlite3.connect(str(Path.home() / '.mikai' / 'mikai.db'))
    db.row_factory = sqlite3.Row

    perplexity = db.execute(
        "SELECT label, raw_content, created_at FROM sources WHERE source='perplexity' AND label LIKE '%MIKA%REMY%' LIMIT 1"
    ).fetchone()

    claude = db.execute(
        "SELECT label, raw_content, created_at FROM sources WHERE source='claude-thread' AND label LIKE '%invisible%knowledge%' LIMIT 1"
    ).fetchone()

    db.close()

    content = []
    if apple_note:
        content.append({
            'name': f"apple-notes: {apple_note['name']}",
            'body': apple_note['body'][:5000],
            'date': apple_note['date'],
            'source': 'apple-notes',
        })
    if perplexity:
        content.append({
            'name': f"perplexity: {perplexity['label'][:60]}",
            'body': perplexity['raw_content'][:5000],
            'date': perplexity['created_at'] or '2026-01-01T00:00:00Z',
            'source': 'perplexity',
        })
    if claude:
        content.append({
            'name': f"claude: {claude['label'][:60]}",
            'body': claude['raw_content'][:5000],
            'date': claude['created_at'] or '2026-01-01T00:00:00Z',
            'source': 'claude-thread',
        })

    return content


# ── Main comparison ──────────────────────────────────────────────────────────

async def run_comparison():
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "mikai-local-dev")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    voyage_key = os.environ.get("VOYAGE_API_KEY")

    if not deepseek_key or not voyage_key:
        print("Need DEEPSEEK_API_KEY and VOYAGE_API_KEY in environment")
        sys.exit(1)

    content = get_test_content()
    print(f"Test content: {len(content)} pieces", flush=True)
    for c in content:
        print(f"  {c['name']} ({len(c['body'])} chars)", flush=True)

    # Shared LLM client
    llm = DeepSeekClient(
        config=LLMConfig(api_key=deepseek_key, model="deepseek-chat", small_model="deepseek-chat", base_url="https://api.deepseek.com"),
        max_tokens=8192,
    )

    # Two embedders
    voyage_embedder = VoyageAIEmbedder(config=VoyageAIEmbedderConfig(api_key=voyage_key, model="voyage-3"))
    nomic_embedder = NomicLocalEmbedder()

    results = {}

    for embedder_name, embedder in [("voyage", voyage_embedder), ("nomic", nomic_embedder)]:
        group_id = f"comparison-{embedder_name}"
        print(f"\n{'='*60}", flush=True)
        print(f"TESTING: {embedder_name.upper()} embeddings (group: {group_id})", flush=True)
        print(f"{'='*60}", flush=True)

        graphiti = Graphiti(
            neo4j_uri, neo4j_user, neo4j_password,
            llm_client=llm, embedder=embedder, cross_encoder=PassthroughReranker(),
        )
        await graphiti.build_indices_and_constraints()

        # Import all 3 test episodes
        for i, c in enumerate(content):
            print(f"\n  Importing [{i+1}/{len(content)}] {c['name'][:50]}...", flush=True)
            try:
                ref_time = datetime.fromisoformat(c['date'].replace('Z', '+00:00')) if c['date'] else datetime.now(timezone.utc)
                result = await graphiti.add_episode(
                    name=c['name'],
                    episode_body=c['body'],
                    source=EpisodeType.text,
                    source_description=c['source'],
                    reference_time=ref_time,
                    group_id=group_id,
                )
                nodes = len(result.nodes) if result.nodes else 0
                edges = len(result.edges) if result.edges else 0
                print(f"    OK: {nodes} nodes, {edges} edges", flush=True)
            except Exception as e:
                print(f"    ERROR: {e}", flush=True)

            await asyncio.sleep(5)  # Rate limit buffer

        # Query and collect results
        print(f"\n  Querying graph ({embedder_name})...", flush=True)

        queries = [
            "What is MIKAI and what does Brian want to build?",
            "Brian's philosophical views on technology",
            "AI knowledge architecture",
        ]

        embedder_results = {"entities": [], "edges": [], "search": {}}

        # Get entities
        from graphiti_core.driver.neo4j_driver import Neo4jDriver
        driver = graphiti.driver
        entity_records = await driver.execute_query(
            f"MATCH (e:Entity) WHERE e.group_id = '{group_id}' RETURN e.name AS name, e.summary AS summary ORDER BY e.name LIMIT 30"
        )
        embedder_results["entities"] = [(r["name"], r["summary"][:100] if r["summary"] else "") for r in entity_records]
        print(f"  Entities: {len(embedder_results['entities'])}", flush=True)

        # Get edges
        edge_records = await driver.execute_query(
            f"MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.group_id = '{group_id}' RETURN a.name AS from, r.name AS rel, b.name AS to, r.fact AS fact LIMIT 20"
        )
        embedder_results["edges"] = [(r["from"], r["rel"], r["to"], r["fact"][:80] if r["fact"] else "") for r in edge_records]
        print(f"  Edges: {len(embedder_results['edges'])}", flush=True)

        # Search
        for q in queries:
            search_results = await graphiti.search(query=q, group_ids=[group_id], num_results=3)
            embedder_results["search"][q] = [(e.fact[:100], round(getattr(e, 'score', 0) or 0, 3)) for e in search_results]
            print(f"  Search '{q[:40]}': {len(search_results)} results", flush=True)

        results[embedder_name] = embedder_results
        await graphiti.close()

    # Print comparison
    print(f"\n\n{'='*80}", flush=True)
    print("COMPARISON RESULTS", flush=True)
    print(f"{'='*80}", flush=True)

    print(f"\n--- ENTITIES ---", flush=True)
    print(f"{'Voyage':>40} | {'Nomic':>40}", flush=True)
    print(f"{'-'*40} | {'-'*40}", flush=True)
    v_ent = results.get("voyage", {}).get("entities", [])
    n_ent = results.get("nomic", {}).get("entities", [])
    v_names = set(e[0] for e in v_ent)
    n_names = set(e[0] for e in n_ent)
    print(f"  Count: {len(v_ent):>30} | {len(n_ent):>30}", flush=True)
    print(f"  Shared: {len(v_names & n_names)}", flush=True)
    print(f"  Voyage only: {v_names - n_names}", flush=True)
    print(f"  Nomic only: {n_names - v_names}", flush=True)

    print(f"\n--- EDGES ---", flush=True)
    print(f"  Voyage: {len(results.get('voyage', {}).get('edges', []))}", flush=True)
    print(f"  Nomic:  {len(results.get('nomic', {}).get('edges', []))}", flush=True)

    print(f"\n--- SEARCH RESULTS ---", flush=True)
    for q in queries:
        print(f"\n  Query: '{q}'", flush=True)
        v_search = results.get("voyage", {}).get("search", {}).get(q, [])
        n_search = results.get("nomic", {}).get("search", {}).get(q, [])
        print(f"  Voyage:", flush=True)
        for fact, score in v_search:
            print(f"    [{score}] {fact}", flush=True)
        print(f"  Nomic:", flush=True)
        for fact, score in n_search:
            print(f"    [{score}] {fact}", flush=True)


if __name__ == "__main__":
    # Load env
    env_path = Path(__file__).parent.parent.parent.parent / '.env.local'
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, _, val = line.partition('=')
            if key and val and key not in os.environ:
                os.environ[key] = val

    asyncio.run(run_comparison())
