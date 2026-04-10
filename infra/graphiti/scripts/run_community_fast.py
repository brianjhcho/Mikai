"""
Fast community detection for MIKAI Graphiti graph.

Bypasses Graphiti's slow per-entity query loop by building
the adjacency projection in a single Cypher query, then
running label propagation + LLM summaries.

Usage:
    python scripts/run_community_fast.py
"""

import asyncio
import json
import logging
import os
import sys
import typing
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

# Load env
env_path = Path("/Users/briancho/Desktop/MIKAI/.env.local")
for line in env_path.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    key, _, val = line.partition('=')
    if key and val and key not in os.environ:
        os.environ[key] = val

from graphiti_core import Graphiti
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.llm_client.config import LLMConfig, ModelSize, DEFAULT_MAX_TOKENS
from graphiti_core.llm_client.client import Message
from graphiti_core.embedder.voyage import VoyageAIEmbedder, VoyageAIEmbedderConfig
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.utils.maintenance.community_operations import label_propagation, Neighbor, build_community
from graphiti_core.nodes import EntityNode
from graphiti_core.helpers import semaphore_gather

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("community-fast")


class DeepSeekClient(OpenAIGenericClient):
    async def _generate_response(self, messages, response_model=None, max_tokens=8192, model_size=ModelSize.medium):
        from openai.types.chat import ChatCompletionMessageParam
        openai_messages = []
        for m in messages:
            m.content = self._clean_input(m.content)
            if m.role == 'user': openai_messages.append({'role': 'user', 'content': m.content})
            elif m.role == 'system': openai_messages.append({'role': 'system', 'content': m.content})
        if response_model is not None:
            schema = response_model.model_json_schema()
            for i, msg in enumerate(openai_messages):
                if msg['role'] == 'system':
                    openai_messages[i] = {'role': 'system', 'content': str(msg['content']) + f"\n\nRespond with valid JSON matching this schema:\n```json\n{json.dumps(schema, indent=2)}\n```\nRespond ONLY with the JSON object."}
                    break
            else:
                openai_messages.insert(0, {'role': 'system', 'content': f"Respond with valid JSON:\n```json\n{json.dumps(schema, indent=2)}\n```"})
        response = await self.client.chat.completions.create(model=self.model, messages=openai_messages, temperature=self.temperature, max_tokens=self.max_tokens, response_format={'type': 'json_object'})
        return json.loads(response.choices[0].message.content or '{}')


class PassthroughReranker(CrossEncoderClient):
    async def rank(self, query, passages):
        return [(p, 1.0 - i * 0.01) for i, p in enumerate(passages)]


async def main():
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    voyage_key = os.environ.get("VOYAGE_API_KEY")

    llm = DeepSeekClient(
        config=LLMConfig(api_key=deepseek_key, model="deepseek-chat", small_model="deepseek-chat", base_url="https://api.deepseek.com"),
        max_tokens=8192,
    )
    embedder = VoyageAIEmbedder(config=VoyageAIEmbedderConfig(api_key=voyage_key, model="voyage-3"))

    graphiti = Graphiti("bolt://localhost:7687", "neo4j", "mikai-local-dev",
                        llm_client=llm, embedder=embedder, cross_encoder=PassthroughReranker())
    await graphiti.build_indices_and_constraints()
    driver = graphiti.driver

    group_id = "mikai-default"

    # Step 1: Count orphans before
    result = await driver.execute_query(
        "MATCH (e:Entity {group_id: $gid}) WHERE NOT EXISTS { (e)-[:RELATES_TO]-() } RETURN COUNT(e) AS orphans",
        gid=group_id,
    )
    orphans_before = result.records[0]['orphans']
    logger.info(f"Orphans before: {orphans_before}")

    # Step 2: Build adjacency projection in ONE query (not 7,677 queries)
    logger.info("Building adjacency projection (single Cypher query)...")
    result = await driver.execute_query(
        """
        MATCH (n:Entity {group_id: $gid})-[e:RELATES_TO]-(m:Entity {group_id: $gid})
        RETURN n.uuid AS source, m.uuid AS target, COUNT(e) AS weight
        """,
        gid=group_id,
    )

    # Build projection dict
    projection: dict[str, list[Neighbor]] = defaultdict(list)

    # First get ALL entity UUIDs (including orphans with no edges)
    all_result = await driver.execute_query(
        "MATCH (n:Entity {group_id: $gid}) RETURN n.uuid AS uuid",
        gid=group_id,
    )
    for record in all_result.records:
        projection[record['uuid']] = []

    # Add edges
    for record in result.records:
        projection[record['source']].append(
            Neighbor(node_uuid=record['target'], edge_count=record['weight'])
        )

    logger.info(f"Projection built: {len(projection)} entities, {sum(len(v) for v in projection.values())} edge entries")

    # Step 3: Run label propagation
    logger.info("Running label propagation...")
    cluster_uuids = label_propagation(projection)
    logger.info(f"Label propagation found {len(cluster_uuids)} clusters")

    # Filter: keep clusters with 2-100 entities (singletons useless, mega-clusters too expensive)
    useful_clusters = [c for c in cluster_uuids if 2 <= len(c) <= 100]
    mega_clusters = [c for c in cluster_uuids if len(c) > 100]
    singletons = [c for c in cluster_uuids if len(c) == 1]
    logger.info(f"Clusters: {len(useful_clusters)} useful (2-100), {len(mega_clusters)} mega (>100, skipped), {len(singletons)} singletons")
    for mc in mega_clusters:
        logger.info(f"  Skipped mega-cluster: {len(mc)} entities")

    # Sort by size descending, cap at 50
    useful_clusters.sort(key=len, reverse=True)
    clusters_to_summarize = useful_clusters[:50]
    logger.info(f"Summarizing {len(clusters_to_summarize)} clusters...")

    # Step 4: Fetch entity data for each cluster
    community_results = []
    for i, cluster in enumerate(clusters_to_summarize):
        try:
            entities = await EntityNode.get_by_uuids(driver, cluster)
            if len(entities) < 2:
                continue

            logger.info(f"  Cluster {i+1}/{len(clusters_to_summarize)}: {len(entities)} entities — {', '.join(e.name for e in entities[:5])}...")

            # Build community using Graphiti's LLM summary
            community_node, community_edges = await build_community(llm, entities)

            # Embed community name before saving (required by Neo4j vector property)
            if not community_node.name_embedding:
                community_node.name_embedding = await embedder.create(community_node.name)

            # Save to Neo4j
            await community_node.save(driver)
            for edge in community_edges:
                await edge.save(driver)

            community_results.append({
                'name': community_node.name,
                'summary': community_node.summary[:200] if community_node.summary else '',
                'members': len(entities),
                'member_names': [e.name for e in entities[:10]],
            })

            logger.info(f"    → Community: '{community_node.name}' ({len(entities)} members)")

        except Exception as e:
            logger.warning(f"  Cluster {i+1} failed: {e}")
            continue

        # Rate limit between LLM calls
        await asyncio.sleep(2)

    # Step 5: Count orphans after
    result = await driver.execute_query(
        "MATCH (c:Community)-[:HAS_MEMBER]->(e:Entity {group_id: $gid}) RETURN COUNT(DISTINCT e) AS connected",
        gid=group_id,
    )
    connected = result.records[0]['connected'] if result.records else 0

    result = await driver.execute_query(
        "MATCH (c:Community) WHERE c.group_id = $gid RETURN COUNT(c) AS communities",
        gid=group_id,
    )
    total_communities = result.records[0]['communities'] if result.records else 0

    await graphiti.close()

    # Report
    print(f"\n{'='*60}", flush=True)
    print("COMMUNITY DETECTION RESULTS", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Total clusters found:       {len(cluster_uuids)}", flush=True)
    print(f"Multi-entity clusters:      {len(multi_clusters)}", flush=True)
    print(f"Communities created (top 50): {total_communities}", flush=True)
    print(f"Entities in communities:    {connected}", flush=True)
    print(f"Orphans before:             {orphans_before}", flush=True)
    print(f"", flush=True)
    print(f"Top communities:", flush=True)
    for c in community_results[:15]:
        print(f"  '{c['name']}' ({c['members']} members): {c['summary'][:100]}", flush=True)
        print(f"    Members: {', '.join(c['member_names'][:5])}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
