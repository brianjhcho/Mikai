"""
Community detection for MIKAI Graphiti graph.

Clusters related entities into communities using label propagation,
generating LLM summaries for each community cluster.

Reports:
  - Number of communities created
  - Sample community names + summaries
  - How many previously-orphan entities got connected
"""

import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load env vars from .env.local
env_path = Path("/Users/briancho/Desktop/MIKAI/.env.local")
load_dotenv(env_path)

# Make sibling `sidecar` package importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sidecar.client import build_graphiti

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("community-detection")


async def count_orphans_before(driver) -> int:
    """Count entities with zero RELATES_TO edges (orphans)."""
    records, _, _ = await driver.execute_query(
        """
        MATCH (n:Entity {group_id: $group_id})
        WHERE NOT (n)-[:RELATES_TO]-()
        RETURN count(n) AS orphan_count
        """,
        group_id="mikai-default",
    )
    return records[0]["orphan_count"] if records else 0


async def count_orphans_in_communities(driver) -> int:
    """Count formerly-orphan entities now in a community."""
    records, _, _ = await driver.execute_query(
        """
        MATCH (c:Community)-[:HAS_MEMBER]->(n:Entity {group_id: $group_id})
        WHERE NOT (n)-[:RELATES_TO]-()
        RETURN count(DISTINCT n) AS count
        """,
        group_id="mikai-default",
    )
    return records[0]["count"] if records else 0


async def main():
    graphiti = build_graphiti(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="mikai-local-dev",
    )

    try:
        logger.info("Initializing Graphiti and building indices...")
        await graphiti.build_indices_and_constraints()

        driver = graphiti.clients.driver

        # Count orphans before community detection
        logger.info("Counting orphan entities before community detection...")
        orphans_before = await count_orphans_before(driver)
        logger.info(f"Orphan entities (zero edges): {orphans_before}")

        # Run community detection
        logger.info("Running community detection on group: mikai-default ...")
        community_nodes, community_edges = await graphiti.build_communities(
            group_ids=["mikai-default"]
        )

        # Count orphans now in communities
        orphans_connected = await count_orphans_in_communities(driver)

        # Report results
        print("\n" + "=" * 60)
        print("COMMUNITY DETECTION RESULTS")
        print("=" * 60)
        print(f"Communities created:        {len(community_nodes)}")
        print(f"Community edges created:    {len(community_edges)}")
        print(f"Orphan entities before:     {orphans_before}")
        print(f"Orphans now in community:   {orphans_connected}")
        print()

        # Sample up to 10 communities
        sample_size = min(10, len(community_nodes))
        print(f"Sample communities (showing {sample_size} of {len(community_nodes)}):")
        print("-" * 60)
        for node in community_nodes[:sample_size]:
            summary_preview = (node.summary or "")[:200].replace("\n", " ")
            if len(node.summary or "") > 200:
                summary_preview += "..."
            print(f"  Name:    {node.name}")
            print(f"  Summary: {summary_preview}")
            print()

        # Show size distribution
        if community_edges:
            from collections import Counter
            community_member_counts: Counter = Counter()
            for edge in community_edges:
                # CommunityEdge has source_node_uuid (community) and target_node_uuid (entity)
                community_member_counts[edge.source_node_uuid] += 1

            sizes = list(community_member_counts.values())
            sizes.sort(reverse=True)
            print(f"Community size distribution (members per community):")
            print(f"  Largest:  {sizes[0] if sizes else 0}")
            print(f"  Smallest: {sizes[-1] if sizes else 0}")
            print(f"  Median:   {sizes[len(sizes)//2] if sizes else 0}")
            print(f"  Top 5:    {sizes[:5]}")
            print()

    finally:
        await graphiti.close()
        logger.info("Graphiti connection closed")


if __name__ == "__main__":
    asyncio.run(main())
