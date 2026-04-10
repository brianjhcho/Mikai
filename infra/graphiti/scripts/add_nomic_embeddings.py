"""
add_nomic_embeddings.py

Adds Nomic embeddings as a second vector property on existing Entity nodes
and RELATES_TO edges. Runs locally, no API calls.

Usage:
    python scripts/add_nomic_embeddings.py [--batch-size 100]
"""

import argparse
import asyncio
import os
import sys
import numpy as np
from neo4j import AsyncGraphDatabase

os.environ['TOKENIZERS_PARALLELISM'] = 'false'


class NomicEmbedder:
    def __init__(self):
        self._pipe = None

    def _load(self):
        if not self._pipe:
            print("Loading Nomic model...", flush=True)
            from transformers import pipeline
            self._pipe = pipeline('feature-extraction', 'nomic-ai/nomic-embed-text-v1.5')
            print("Nomic ready.", flush=True)
        return self._pipe

    def embed(self, text: str) -> list[float]:
        pipe = self._load()
        output = pipe(str(text)[:512], return_tensors=False)
        arr = np.array(output[0])
        mean = arr.mean(axis=0)
        norm = mean / (np.linalg.norm(mean) + 1e-10)
        return norm.tolist()[:768]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--group-id", default="mikai-default")
    args = parser.parse_args()

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "mikai-local-dev")

    embedder = NomicEmbedder()
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async with driver.session() as session:
        # Count entities needing Nomic embeddings
        result = await session.run(
            "MATCH (e:Entity) WHERE e.group_id = $gid RETURN COUNT(e) AS total",
            gid=args.group_id,
        )
        record = await result.single()
        total = record["total"]
        print(f"Entities to embed: {total}", flush=True)

        # Process in batches
        skip = 0
        embedded = 0
        while skip < total:
            result = await session.run(
                "MATCH (e:Entity) WHERE e.group_id = $gid "
                "RETURN e.uuid AS uuid, e.name AS name "
                "ORDER BY e.uuid SKIP $skip LIMIT $limit",
                gid=args.group_id, skip=skip, limit=args.batch_size,
            )
            records = [r async for r in result]

            if not records:
                break

            names = [r["name"] for r in records]
            uuids = [r["uuid"] for r in records]
            embeddings = embedder.embed_batch(names)

            for uuid, emb in zip(uuids, embeddings):
                await session.run(
                    "MATCH (e:Entity {uuid: $uuid}) "
                    "SET e.nomic_embedding = $emb",
                    uuid=uuid, emb=emb,
                )

            embedded += len(records)
            skip += args.batch_size
            print(f"  Entities: {embedded}/{total}", flush=True)

        # Now do edges
        result = await session.run(
            "MATCH ()-[r:RELATES_TO]->() WHERE r.group_id = $gid RETURN COUNT(r) AS total",
            gid=args.group_id,
        )
        record = await result.single()
        edge_total = record["total"]
        print(f"\nEdges to embed: {edge_total}", flush=True)

        skip = 0
        edge_embedded = 0
        while skip < edge_total:
            result = await session.run(
                "MATCH ()-[r:RELATES_TO]->() WHERE r.group_id = $gid "
                "RETURN r.uuid AS uuid, r.fact AS fact "
                "ORDER BY r.uuid SKIP $skip LIMIT $limit",
                gid=args.group_id, skip=skip, limit=args.batch_size,
            )
            records = [r async for r in result]

            if not records:
                break

            facts = [r["fact"] or "" for r in records]
            uuids = [r["uuid"] for r in records]
            embeddings = embedder.embed_batch(facts)

            for uuid, emb in zip(uuids, embeddings):
                await session.run(
                    "MATCH ()-[r:RELATES_TO {uuid: $uuid}]->() "
                    "SET r.nomic_embedding = $emb",
                    uuid=uuid, emb=emb,
                )

            edge_embedded += len(records)
            skip += args.batch_size
            print(f"  Edges: {edge_embedded}/{edge_total}", flush=True)

    await driver.close()
    print(f"\nDone. {embedded} entity embeddings + {edge_embedded} edge embeddings added.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
