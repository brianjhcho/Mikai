"""
Compare Voyage vs Nomic on a dense Claude thread, imported turn-by-turn.
Uses Graphiti's intended pattern: EpisodeType.message, one turn per episode, saga grouping.
"""

import asyncio
import os
import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Make sibling `sidecar` package importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.embedder.voyage import VoyageAIEmbedder, VoyageAIEmbedderConfig
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.nodes import EpisodeType
import numpy as np

from sidecar.client import DeepSeekClient, PassthroughReranker


class NomicEmbedder(EmbedderClient):
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

    def _embed_one(self, text):
        pipe = self._load()
        output = pipe(str(text)[:512], return_tensors=False)  # truncate for speed
        arr = np.array(output[0])
        mean = arr.mean(axis=0)
        norm = mean / (np.linalg.norm(mean) + 1e-10)
        return norm.tolist()[:768]

    async def create(self, input_data, **kwargs):
        if isinstance(input_data, str):
            return self._embed_one(input_data)
        elif isinstance(input_data, list) and len(input_data) > 0:
            return self._embed_one(str(input_data[0]))
        return self._embed_one(str(input_data))

    async def create_batch(self, input_data_list):
        return [self._embed_one(t) for t in input_data_list]


def parse_thread():
    db = sqlite3.connect(str(Path.home() / '.mikai' / 'mikai.db'))
    raw = db.execute("SELECT raw_content FROM sources WHERE label = 'Build Discussion: Semantic search across LLM conversation history'").fetchone()[0]
    db.close()

    turns = []
    current_role = None
    current_lines = []

    for line in raw.split('\n'):
        if line.startswith('[User]:'):
            if current_role:
                turns.append({'role': current_role, 'content': '\n'.join(current_lines).strip()})
            current_role = 'user'
            current_lines = [line[7:].strip()]
        elif line.startswith('[Assistant]:'):
            if current_role:
                turns.append({'role': current_role, 'content': '\n'.join(current_lines).strip()})
            current_role = 'assistant'
            current_lines = [line[12:].strip()]
        else:
            current_lines.append(line)

    if current_role:
        turns.append({'role': current_role, 'content': '\n'.join(current_lines).strip()})

    return turns


async def import_and_query(graphiti, group_id, saga_name, turns, queries):
    """Import turns sequentially with saga, then query."""
    await graphiti.build_indices_and_constraints()

    prev_uuid = None
    for i, turn in enumerate(turns):
        body = f"{turn['role']}: {turn['content'][:3000]}"  # cap per turn
        ref_time = datetime(2025, 3, 1, tzinfo=timezone.utc) + timedelta(minutes=i * 5)

        print(f"    Turn {i+1}/{len(turns)} [{turn['role']}] ({len(turn['content'])} chars)", flush=True)
        try:
            result = await graphiti.add_episode(
                name=f"Turn {i+1} ({turn['role']})",
                episode_body=body,
                source=EpisodeType.message,
                source_description="claude-thread: Build Discussion",
                reference_time=ref_time,
                group_id=group_id,
                saga=saga_name,
            )
            if result and result.episode:
                prev_uuid = str(result.episode.uuid)
            nodes = len(result.nodes) if result and result.nodes else 0
            edges = len(result.edges) if result and result.edges else 0
            print(f"      OK: +{nodes} nodes, +{edges} edges", flush=True)
        except Exception as e:
            print(f"      ERROR: {e}", flush=True)

        await asyncio.sleep(3)

    # Query
    print(f"\n  Querying {group_id}...", flush=True)
    driver = graphiti.driver

    result = await driver.execute_query(
        f"MATCH (e:Entity) WHERE e.group_id = '{group_id}' RETURN e.name AS name, e.summary AS summary ORDER BY e.name LIMIT 30"
    )
    entities = [(r['name'], (r['summary'] or '')[:120]) for r in result.records]

    result = await driver.execute_query(
        f"MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE r.group_id = '{group_id}' RETURN a.name AS src, r.name AS rel, b.name AS tgt, r.fact AS fact ORDER BY r.fact LIMIT 15"
    )
    edges = [(r['src'], r['rel'], r['tgt'], (r['fact'] or '')[:100]) for r in result.records]

    search_results = {}
    for q in queries:
        try:
            results = await graphiti.search(query=q, group_ids=[group_id], num_results=3)
            search_results[q] = [e.fact[:120] for e in results]
        except Exception as e:
            search_results[q] = [f"ERROR: {e}"]

    return {"entities": entities, "edges": edges, "search": search_results}


async def main():
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "mikai-local-dev")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    voyage_key = os.environ.get("VOYAGE_API_KEY")

    turns = parse_thread()
    # Use first 20 turns for comparison
    test_turns = turns[:20]
    print(f"Thread: 204 total turns, testing first {len(test_turns)}", flush=True)
    print(f"  User turns: {len([t for t in test_turns if t['role'] == 'user'])}", flush=True)
    print(f"  Assistant turns: {len([t for t in test_turns if t['role'] == 'assistant'])}", flush=True)

    llm = DeepSeekClient(
        config=LLMConfig(api_key=deepseek_key, model="deepseek-chat", small_model="deepseek-chat", base_url="https://api.deepseek.com"),
        max_tokens=8192,
    )

    queries = [
        "What is MIKAI trying to build?",
        "How does MIKAI compare to Mem.ai?",
        "semantic search over conversation history",
        "knowledge graph architecture decisions",
    ]

    results = {}

    for emb_name, embedder in [
        ("voyage", VoyageAIEmbedder(config=VoyageAIEmbedderConfig(api_key=voyage_key, model="voyage-3"))),
        ("nomic", NomicEmbedder()),
    ]:
        group_id = f"thread-{emb_name}"
        saga_name = f"Build Discussion ({emb_name})"

        print(f"\n{'='*60}", flush=True)
        print(f"  TESTING: {emb_name.upper()} — turn-by-turn with saga", flush=True)
        print(f"{'='*60}", flush=True)

        g = Graphiti(neo4j_uri, neo4j_user, neo4j_password, llm_client=llm, embedder=embedder, cross_encoder=PassthroughReranker())
        results[emb_name] = await import_and_query(g, group_id, saga_name, test_turns, queries)
        await g.close()

    # Print comparison
    print(f"\n\n{'='*80}", flush=True)
    print("THREAD COMPARISON: VOYAGE vs NOMIC", flush=True)
    print(f"{'='*80}\n", flush=True)

    for label in ["entities", "edges"]:
        v = results.get("voyage", {}).get(label, [])
        n = results.get("nomic", {}).get(label, [])
        print(f"{label.upper()}:", flush=True)
        print(f"  Voyage ({len(v)}):", flush=True)
        for item in v[:8]:
            if label == "entities":
                print(f"    {item[0]}: {item[1]}", flush=True)
            else:
                print(f"    {item[0]} →{item[1]}→ {item[2]}: {item[3]}", flush=True)
        print(f"  Nomic ({len(n)}):", flush=True)
        for item in n[:8]:
            if label == "entities":
                print(f"    {item[0]}: {item[1]}", flush=True)
            else:
                print(f"    {item[0]} →{item[1]}→ {item[2]}: {item[3]}", flush=True)
        print(flush=True)

    print("SEARCH:", flush=True)
    for q in queries:
        print(f"\n  '{q}'", flush=True)
        print(f"  Voyage:", flush=True)
        for f in results.get("voyage", {}).get("search", {}).get(q, []):
            print(f"    • {f}", flush=True)
        print(f"  Nomic:", flush=True)
        for f in results.get("nomic", {}).get("search", {}).get(q, []):
            print(f"    • {f}", flush=True)

    print(f"\n{'='*80}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    env_path = Path(__file__).parent.parent.parent.parent / '.env.local'
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
            key, _, val = line.partition('=')
            if key and val and key not in os.environ: os.environ[key] = val
    asyncio.run(main())
