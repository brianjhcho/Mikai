"""
Fast community detection for MIKAI Graphiti graph.

Bypasses Graphiti's slow per-entity query loop by building
the adjacency projection in a single Cypher query, then
running label propagation + LLM summaries.

Usage:
    python scripts/run_community_fast.py
"""

import asyncio
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

# Load env
env_path = Path("/Users/briancho/Desktop/MIKAI/.env.local")
for line in env_path.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    key, _, val = line.partition('=')
    if key and val and key not in os.environ:
        os.environ[key] = val

# Make sibling `sidecar` package importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphiti_core.utils.maintenance.community_operations import label_propagation, Neighbor, build_community
from graphiti_core.nodes import EntityNode

from sidecar.client import build_graphiti

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("community-fast")


async def main():
    graphiti = build_graphiti()
    llm = graphiti.llm_client
    embedder = graphiti.embedder
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
