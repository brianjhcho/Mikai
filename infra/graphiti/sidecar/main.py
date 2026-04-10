"""
MIKAI Graphiti Sidecar — FastAPI service wrapping graphiti-core.

LLM: DeepSeek V3 via OpenAI-compatible API (cheap, fast, no rate limit issues)
Embeddings: Voyage AI voyage-3 (1024-dim)
Reranker: Passthrough (no OpenAI dependency)

Endpoints:
  GET  /health              — Liveness check
  POST /search              — Hybrid search (vec + BM25 + RRF)
  POST /episode             — Add single episode
  POST /episode/bulk        — Bulk import (add_episode_bulk)
  POST /communities         — Get community summaries
"""

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from graphiti_core import Graphiti
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.llm_client.config import LLMConfig, ModelSize, DEFAULT_MAX_TOKENS
from graphiti_core.llm_client.client import Message
import json
import typing
from graphiti_core.embedder.voyage import VoyageAIEmbedder, VoyageAIEmbedderConfig
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.nodes import EpisodeType
from graphiti_core.graphiti import RawEpisode
from graphiti_core.search.search_config_recipes import COMBINED_HYBRID_SEARCH_RRF

logger = logging.getLogger("mikai-graphiti")
logging.basicConfig(level=logging.INFO)


class DeepSeekClient(OpenAIGenericClient):
    """DeepSeek-compatible client that uses json_object mode instead of json_schema.

    DeepSeek supports structured JSON output but not OpenAI's json_schema
    response_format type. This client puts the schema in the system prompt
    and uses json_object mode instead.
    """

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
            if m.role == 'user':
                openai_messages.append({'role': 'user', 'content': m.content})
            elif m.role == 'system':
                openai_messages.append({'role': 'system', 'content': m.content})

        # If a response model is provided, inject the schema into the system prompt
        # and use json_object mode (DeepSeek-compatible) instead of json_schema
        if response_model is not None:
            schema = response_model.model_json_schema()
            schema_instruction = (
                f"\n\nYou MUST respond with valid JSON matching this exact schema:\n"
                f"```json\n{json.dumps(schema, indent=2)}\n```\n"
                f"Respond ONLY with the JSON object, no other text."
            )
            # Append schema to the last system message, or add a new one
            injected = False
            for i, msg in enumerate(openai_messages):
                if msg['role'] == 'system':
                    openai_messages[i] = {
                        'role': 'system',
                        'content': str(msg['content']) + schema_instruction,
                    }
                    injected = True
                    break
            if not injected:
                openai_messages.insert(0, {'role': 'system', 'content': schema_instruction})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={'type': 'json_object'},
            )
            result = response.choices[0].message.content or '{}'
            return json.loads(result)
        except Exception as e:
            logger.error(f'DeepSeek error: {e}')
            raise


class PassthroughReranker(CrossEncoderClient):
    """No-op reranker — avoids OpenAI dependency."""
    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        return [(p, 1.0 - i * 0.01) for i, p in enumerate(passages)]


# ── Graphiti client ──────────────────────────────────────────────────────────

graphiti: Graphiti | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global graphiti

    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "mikai-local-dev")

    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    voyage_key = os.environ.get("VOYAGE_API_KEY")

    if not deepseek_key:
        raise RuntimeError("DEEPSEEK_API_KEY required")
    if not voyage_key:
        raise RuntimeError("VOYAGE_API_KEY required")

    logger.info(f"Connecting to Neo4j at {neo4j_uri}")
    logger.info("LLM: DeepSeek V3 | Embeddings: Voyage AI voyage-3")

    llm_client = DeepSeekClient(
        config=LLMConfig(
            api_key=deepseek_key,
            model="deepseek-chat",
            small_model="deepseek-chat",
            base_url="https://api.deepseek.com",
        ),
        max_tokens=8192,
    )

    embedder = VoyageAIEmbedder(config=VoyageAIEmbedderConfig(
        api_key=voyage_key,
        model="voyage-3",
    ))

    graphiti = Graphiti(
        neo4j_uri, neo4j_user, neo4j_password,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=PassthroughReranker(),
    )

    try:
        await graphiti.build_indices_and_constraints()
        logger.info("Graphiti initialized, indices ready")
        yield
    finally:
        if graphiti:
            await graphiti.close()
            logger.info("Graphiti connection closed")


app = FastAPI(title="MIKAI Graphiti Sidecar", version="2.0.0", lifespan=lifespan)


# ── Models ───────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    group_ids: list[str] | None = None
    num_results: int = 10


class SearchResult(BaseModel):
    uuid: str
    name: str
    fact: str
    source_node_name: str | None = None
    target_node_name: str | None = None
    created_at: str | None = None
    valid_at: str | None = None
    invalid_at: str | None = None
    expired_at: str | None = None
    episodes: list[str] = []


class EpisodeRequest(BaseModel):
    content: str
    source_description: str = "mikai-import"
    episode_type: str = "text"
    reference_time: str | None = None
    group_id: str = "mikai-default"


class BulkEpisodeItem(BaseModel):
    content: str
    name: str = "untitled"
    source_description: str = "apple-notes"
    episode_type: str = "text"
    reference_time: str | None = None


class BulkEpisodeRequest(BaseModel):
    episodes: list[BulkEpisodeItem]
    group_id: str = "mikai-default"


class CommunityResult(BaseModel):
    uuid: str
    name: str
    summary: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "backend": "graphiti-deepseek", "neo4j": graphiti is not None}


@app.post("/search", response_model=list[SearchResult])
async def search(req: SearchRequest):
    """Hybrid search via Graphiti (vec + BM25 + RRF)."""
    if not graphiti:
        raise HTTPException(503, "Graphiti not initialized")

    edges = await graphiti.search(
        query=req.query,
        group_ids=req.group_ids,
        num_results=req.num_results,
    )

    return [
        SearchResult(
            uuid=str(e.uuid),
            name=e.name,
            fact=e.fact,
            source_node_name=getattr(e, "source_node_name", None),
            target_node_name=getattr(e, "target_node_name", None),
            created_at=e.created_at.isoformat() if e.created_at else None,
            valid_at=e.valid_at.isoformat() if e.valid_at else None,
            invalid_at=e.invalid_at.isoformat() if e.invalid_at else None,
            expired_at=e.expired_at.isoformat() if e.expired_at else None,
            episodes=[str(ep) for ep in (e.episodes or [])],
        )
        for e in edges
    ]


@app.post("/episode")
async def add_episode(req: EpisodeRequest):
    """Add a single episode."""
    if not graphiti:
        raise HTTPException(503, "Graphiti not initialized")

    episode_type = EpisodeType(req.episode_type) if req.episode_type else EpisodeType.text
    ref_time = datetime.fromisoformat(req.reference_time) if req.reference_time else datetime.now()

    result = await graphiti.add_episode(
        name=req.source_description,
        episode_body=req.content,
        source=episode_type,
        source_description=req.source_description,
        reference_time=ref_time,
        group_id=req.group_id,
    )

    return {
        "status": "ok",
        "episode_id": str(result.episode.uuid) if result and result.episode else None,
        "nodes_created": len(result.nodes) if result and result.nodes else 0,
        "edges_created": len(result.edges) if result and result.edges else 0,
    }


@app.post("/episode/bulk")
async def add_episode_bulk(req: BulkEpisodeRequest):
    """Bulk import episodes via Graphiti's add_episode_bulk.

    Processes all episodes in one batch — shared context for extraction
    and dedup. Much cheaper than per-episode import.

    Note: Skips edge invalidation (can run separately after).
    """
    if not graphiti:
        raise HTTPException(503, "Graphiti not initialized")

    raw_episodes = []
    for ep in req.episodes:
        ref_time = datetime.fromisoformat(ep.reference_time) if ep.reference_time else datetime.now()
        raw_episodes.append(RawEpisode(
            name=ep.name,
            content=ep.content,
            source=EpisodeType(ep.episode_type),
            source_description=ep.source_description,
            reference_time=ref_time,
        ))

    logger.info(f"Bulk importing {len(raw_episodes)} episodes...")

    result = await graphiti.add_episode_bulk(
        bulk_episodes=raw_episodes,
        group_id=req.group_id,
    )

    episode_count = len(result.episodes) if result and result.episodes else 0
    node_count = len(result.nodes) if result and result.nodes else 0
    edge_count = len(result.edges) if result and result.edges else 0
    community_count = len(result.communities) if result and result.communities else 0

    logger.info(f"Bulk import done: {episode_count} episodes, {node_count} nodes, {edge_count} edges, {community_count} communities")

    return {
        "status": "ok",
        "episodes_created": episode_count,
        "nodes_created": node_count,
        "edges_created": edge_count,
        "communities_created": community_count,
    }


@app.post("/communities", response_model=list[CommunityResult])
async def get_communities():
    """Get community summaries."""
    if not graphiti:
        raise HTTPException(503, "Graphiti not initialized")

    try:
        results = await graphiti.search_(query="", config=COMBINED_HYBRID_SEARCH_RRF)
        communities = results.communities if results.communities else []
        return [
            CommunityResult(uuid=str(c.uuid), name=c.name, summary=c.summary or "")
            for c in communities
        ]
    except Exception as e:
        logger.warning(f"Community fetch failed: {e}")
        return []
