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
import json
import logging
import os
import typing
from pathlib import Path

from dotenv import load_dotenv

# Load env vars from .env.local
env_path = Path("/Users/briancho/Desktop/MIKAI/.env.local")
load_dotenv(env_path)

from graphiti_core import Graphiti
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.llm_client.config import LLMConfig, ModelSize, DEFAULT_MAX_TOKENS
from graphiti_core.llm_client.client import Message
from graphiti_core.embedder.voyage import VoyageAIEmbedder, VoyageAIEmbedderConfig
from graphiti_core.cross_encoder.client import CrossEncoderClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("community-detection")


class DeepSeekClient(OpenAIGenericClient):
    """DeepSeek-compatible client that uses json_object mode instead of json_schema."""

    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, typing.Any]:
        from openai.types.chat import ChatCompletionMessageParam

        openai_messages: list[ChatCompletionMessageParam] = []
        for m in messages:
            m.content = self._clean_input(m.content)
            if m.role == "user":
                openai_messages.append({"role": "user", "content": m.content})
            elif m.role == "system":
                openai_messages.append({"role": "system", "content": m.content})

        if response_model is not None:
            schema = response_model.model_json_schema()
            schema_instruction = (
                f"\n\nYou MUST respond with valid JSON matching this exact schema:\n"
                f"```json\n{json.dumps(schema, indent=2)}\n```\n"
                f"Respond ONLY with the JSON object, no other text."
            )
            injected = False
            for i, msg in enumerate(openai_messages):
                if msg["role"] == "system":
                    openai_messages[i] = {
                        "role": "system",
                        "content": str(msg["content"]) + schema_instruction,
                    }
                    injected = True
                    break
            if not injected:
                openai_messages.insert(0, {"role": "system", "content": schema_instruction})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
            )
            result = response.choices[0].message.content or "{}"
            return json.loads(result)
        except Exception as e:
            logger.error(f"DeepSeek error: {e}")
            raise


class PassthroughReranker(CrossEncoderClient):
    """No-op reranker — avoids OpenAI dependency."""

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        return [(p, 1.0 - i * 0.01) for i, p in enumerate(passages)]


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
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    voyage_key = os.environ.get("VOYAGE_API_KEY")

    if not deepseek_key:
        raise RuntimeError("DEEPSEEK_API_KEY not found in environment")
    if not voyage_key:
        raise RuntimeError("VOYAGE_API_KEY not found in environment")

    neo4j_uri = "bolt://localhost:7687"
    neo4j_user = "neo4j"
    neo4j_password = "mikai-local-dev"

    llm_client = DeepSeekClient(
        config=LLMConfig(
            api_key=deepseek_key,
            model="deepseek-chat",
            small_model="deepseek-chat",
            base_url="https://api.deepseek.com",
        ),
        max_tokens=8192,
    )

    embedder = VoyageAIEmbedder(
        config=VoyageAIEmbedderConfig(
            api_key=voyage_key,
            model="voyage-3",
        )
    )

    graphiti = Graphiti(
        neo4j_uri,
        neo4j_user,
        neo4j_password,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=PassthroughReranker(),
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
