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


# ═══════════════════════════════════════════════════════════════════════════════
# L3 primitives — pure graph operations, no L4 semantics
#
# These endpoints expose generic Graphiti/Neo4j operations that a product layer
# (MCP server, L4 engine) will compose into user-facing tools. Nothing in this
# section knows about tensions, threads, stall states, or next steps — those
# are L4 concerns that will be rebuilt on top of these primitives.
# ═══════════════════════════════════════════════════════════════════════════════


# ── Models ───────────────────────────────────────────────────────────────────

class StatsResult(BaseModel):
    entity_count: int
    edge_count: int
    episode_count: int
    community_count: int
    orphan_count: int


class NodeResult(BaseModel):
    uuid: str
    name: str
    labels: list[str] = []
    summary: str | None = None
    created_at: str | None = None


class NodesSearchRequest(BaseModel):
    query: str
    num_results: int = 10
    group_ids: list[str] | None = None


class ExpandRequest(BaseModel):
    max_edges: int = 20
    include_invalidated: bool = False


class EdgeResult(BaseModel):
    uuid: str
    source_uuid: str
    target_uuid: str
    source_name: str | None = None
    target_name: str | None = None
    fact: str | None = None
    valid_at: str | None = None
    invalid_at: str | None = None
    expired_at: str | None = None
    episodes: list[str] = []


class ExpandResult(BaseModel):
    center: NodeResult
    nodes: list[NodeResult]
    edges: list[EdgeResult]


class EdgesBetweenRequest(BaseModel):
    node_uuids: list[str]
    as_of: str | None = None
    include_invalidated: bool = False


class HistoryRequest(BaseModel):
    query: str
    as_of: str | None = None
    num_results: int = 10


class HistoryResult(BaseModel):
    current: list[SearchResult]
    superseded: list[SearchResult]


class ConnectedEntity(BaseModel):
    uuid: str
    name: str


class EpisodeResult(BaseModel):
    uuid: str
    name: str | None = None
    content: str | None = None
    source_description: str | None = None
    source: str | None = None
    reference_time: str | None = None
    created_at: str | None = None
    group_id: str | None = None
    connected_entities: list[ConnectedEntity] = []


# ── Raw Cypher helper ────────────────────────────────────────────────────────


async def run_cypher(query: str, **params) -> list[dict]:
    """Execute a raw Cypher query via Graphiti's Neo4j driver.

    Graphiti wraps the neo4j AsyncDriver. This helper reaches through the
    wrapper (if present) and executes a session query, returning records as
    dicts for easy Pydantic mapping.
    """
    if not graphiti:
        raise HTTPException(503, "Graphiti not initialized")

    driver = getattr(graphiti.driver, "driver", graphiti.driver)
    async with driver.session() as session:
        result = await session.run(query, **params)
        return [record.data() async for record in result]


def _iso_or_none(v) -> str | None:
    """Convert a Neo4j datetime/string to ISO format, or return None."""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    try:
        return v.isoformat()
    except AttributeError:
        return str(v)


# ── Endpoints ────────────────────────────────────────────────────────────────


@app.get("/stats", response_model=StatsResult)
async def get_stats():
    """Graph quality snapshot: entity, edge, episode, community, orphan counts."""
    rows = await run_cypher("""
        CALL {
            MATCH (n:Entity) RETURN count(n) AS entity_count
        }
        CALL {
            MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS edge_count
        }
        CALL {
            MATCH (e:Episodic) RETURN count(e) AS episode_count
        }
        CALL {
            MATCH (c:Community) RETURN count(c) AS community_count
        }
        CALL {
            MATCH (n:Entity)
            WHERE NOT (n)-[:RELATES_TO]-()
            RETURN count(n) AS orphan_count
        }
        RETURN entity_count, edge_count, episode_count, community_count, orphan_count
    """)

    if not rows:
        return StatsResult(
            entity_count=0, edge_count=0, episode_count=0,
            community_count=0, orphan_count=0,
        )

    r = rows[0]
    return StatsResult(
        entity_count=r.get("entity_count", 0),
        edge_count=r.get("edge_count", 0),
        episode_count=r.get("episode_count", 0),
        community_count=r.get("community_count", 0),
        orphan_count=r.get("orphan_count", 0),
    )


@app.post("/nodes/search", response_model=list[NodeResult])
async def search_nodes(req: NodesSearchRequest):
    """Node-level hybrid search.

    Distinct from /search which returns edges (facts). This returns entity
    nodes, useful when the product layer needs to seed a traversal or display
    a list of relevant entities rather than relationships.
    """
    if not graphiti:
        raise HTTPException(503, "Graphiti not initialized")

    # Graphiti's search_() with a node-focused recipe returns node results in
    # the `.nodes` field of the SearchResults object. We try to use that
    # recipe; if unavailable in the installed graphiti-core version, fall back
    # to the combined recipe and pull the nodes field.
    try:
        from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF
        config = NODE_HYBRID_SEARCH_RRF
    except ImportError:
        config = COMBINED_HYBRID_SEARCH_RRF

    results = await graphiti.search_(
        query=req.query,
        config=config,
        group_ids=req.group_ids,
    )
    nodes = (results.nodes or []) if results else []

    return [
        NodeResult(
            uuid=str(n.uuid),
            name=n.name,
            labels=list(getattr(n, "labels", []) or []),
            summary=getattr(n, "summary", None),
            created_at=_iso_or_none(getattr(n, "created_at", None)),
        )
        for n in nodes[: req.num_results]
    ]


@app.get("/nodes/{uuid}", response_model=NodeResult)
async def get_node(uuid: str):
    """Fetch a single entity node by UUID."""
    rows = await run_cypher("""
        MATCH (n:Entity {uuid: $uuid})
        RETURN
            n.uuid AS uuid,
            n.name AS name,
            labels(n) AS labels,
            n.summary AS summary,
            n.created_at AS created_at
    """, uuid=uuid)

    if not rows:
        raise HTTPException(404, f"Node {uuid} not found")

    r = rows[0]
    return NodeResult(
        uuid=r.get("uuid") or uuid,
        name=r.get("name") or "",
        labels=[lbl for lbl in (r.get("labels") or []) if lbl != "Entity"],
        summary=r.get("summary"),
        created_at=_iso_or_none(r.get("created_at")),
    )


@app.post("/nodes/{uuid}/expand", response_model=ExpandResult)
async def expand_node(uuid: str, req: ExpandRequest):
    """BFS 1-hop from a node: return neighboring nodes and connecting edges.

    For the product layer, this is the primitive that enables thread detection,
    tension surfacing, and any "show me what connects to X" workflow. The L4
    engine (when it's built) will compose multiple expansions to walk wider.
    """
    rows = await run_cypher("""
        MATCH (center:Entity {uuid: $uuid})
        OPTIONAL MATCH (center)-[r:RELATES_TO]-(neighbor:Entity)
        WHERE ($include_invalidated OR r.expired_at IS NULL)
        WITH center, r, neighbor
        LIMIT $max_edges
        RETURN
            center.uuid AS center_uuid,
            center.name AS center_name,
            labels(center) AS center_labels,
            center.summary AS center_summary,
            center.created_at AS center_created_at,
            neighbor.uuid AS neighbor_uuid,
            neighbor.name AS neighbor_name,
            labels(neighbor) AS neighbor_labels,
            neighbor.summary AS neighbor_summary,
            neighbor.created_at AS neighbor_created_at,
            r.uuid AS edge_uuid,
            startNode(r).uuid AS source_uuid,
            endNode(r).uuid AS target_uuid,
            startNode(r).name AS source_name,
            endNode(r).name AS target_name,
            r.fact AS fact,
            r.valid_at AS valid_at,
            r.invalid_at AS invalid_at,
            r.expired_at AS expired_at,
            r.episodes AS episodes
    """, uuid=uuid, max_edges=req.max_edges, include_invalidated=req.include_invalidated)

    if not rows:
        raise HTTPException(404, f"Node {uuid} not found")

    first = rows[0]
    center = NodeResult(
        uuid=first.get("center_uuid") or uuid,
        name=first.get("center_name") or "",
        labels=[lbl for lbl in (first.get("center_labels") or []) if lbl != "Entity"],
        summary=first.get("center_summary"),
        created_at=_iso_or_none(first.get("center_created_at")),
    )

    nodes_by_uuid: dict[str, NodeResult] = {}
    edges: list[EdgeResult] = []

    for r in rows:
        if not r.get("neighbor_uuid"):
            continue
        nuid = r["neighbor_uuid"]
        if nuid not in nodes_by_uuid:
            nodes_by_uuid[nuid] = NodeResult(
                uuid=nuid,
                name=r.get("neighbor_name") or "",
                labels=[lbl for lbl in (r.get("neighbor_labels") or []) if lbl != "Entity"],
                summary=r.get("neighbor_summary"),
                created_at=_iso_or_none(r.get("neighbor_created_at")),
            )
        if r.get("edge_uuid"):
            edges.append(EdgeResult(
                uuid=str(r["edge_uuid"]),
                source_uuid=str(r.get("source_uuid") or ""),
                target_uuid=str(r.get("target_uuid") or ""),
                source_name=r.get("source_name"),
                target_name=r.get("target_name"),
                fact=r.get("fact"),
                valid_at=_iso_or_none(r.get("valid_at")),
                invalid_at=_iso_or_none(r.get("invalid_at")),
                expired_at=_iso_or_none(r.get("expired_at")),
                episodes=[str(ep) for ep in (r.get("episodes") or [])],
            ))

    return ExpandResult(
        center=center,
        nodes=list(nodes_by_uuid.values()),
        edges=edges,
    )


@app.post("/edges/between", response_model=list[EdgeResult])
async def edges_between(req: EdgesBetweenRequest):
    """Return all edges where both endpoints are in the given UUID set.

    This is the primitive the L4 engine will use for thread enrichment —
    once a candidate cluster of entities has been identified (via expand,
    search, or community detection), this query reveals the internal
    relationship structure of that cluster.
    """
    if not req.node_uuids:
        return []

    rows = await run_cypher("""
        MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
        WHERE a.uuid IN $uuids AND b.uuid IN $uuids
            AND ($include_invalidated OR r.invalid_at IS NULL)
            AND (
                $as_of IS NULL
                OR (
                    r.valid_at <= datetime($as_of)
                    AND (r.invalid_at IS NULL OR r.invalid_at > datetime($as_of))
                )
            )
        RETURN
            r.uuid AS uuid,
            a.uuid AS source_uuid,
            b.uuid AS target_uuid,
            a.name AS source_name,
            b.name AS target_name,
            r.fact AS fact,
            r.valid_at AS valid_at,
            r.invalid_at AS invalid_at,
            r.expired_at AS expired_at,
            r.episodes AS episodes
    """, uuids=req.node_uuids, include_invalidated=req.include_invalidated, as_of=req.as_of)

    return [
        EdgeResult(
            uuid=str(r.get("uuid") or ""),
            source_uuid=str(r.get("source_uuid") or ""),
            target_uuid=str(r.get("target_uuid") or ""),
            source_name=r.get("source_name"),
            target_name=r.get("target_name"),
            fact=r.get("fact"),
            valid_at=_iso_or_none(r.get("valid_at")),
            invalid_at=_iso_or_none(r.get("invalid_at")),
            expired_at=_iso_or_none(r.get("expired_at")),
            episodes=[str(ep) for ep in (r.get("episodes") or [])],
        )
        for r in rows
    ]


@app.post("/history", response_model=HistoryResult)
async def history(req: HistoryRequest):
    """Bitemporal point-in-time search.

    Runs a hybrid search and splits results into "current" (edges valid at
    as_of, or valid now if as_of is omitted) and "superseded" (edges that
    were valid at some point but are now invalidated). The product layer
    uses this to answer "what did the graph think about X on date Y" and to
    track how beliefs have evolved.
    """
    if not graphiti:
        raise HTTPException(503, "Graphiti not initialized")

    edges = await graphiti.search(
        query=req.query,
        num_results=req.num_results * 3,  # overfetch for post-filter
    )

    as_of_dt = datetime.fromisoformat(req.as_of) if req.as_of else None
    current: list[SearchResult] = []
    superseded: list[SearchResult] = []

    def to_result(e) -> SearchResult:
        return SearchResult(
            uuid=str(e.uuid),
            name=e.name,
            fact=e.fact,
            source_node_name=getattr(e, "source_node_name", None),
            target_node_name=getattr(e, "target_node_name", None),
            created_at=_iso_or_none(e.created_at),
            valid_at=_iso_or_none(e.valid_at),
            invalid_at=_iso_or_none(e.invalid_at),
            expired_at=_iso_or_none(e.expired_at),
            episodes=[str(ep) for ep in (e.episodes or [])],
        )

    for e in edges:
        valid_at = e.valid_at
        invalid_at = e.invalid_at

        if as_of_dt is not None:
            # Point-in-time query: was this edge valid at as_of?
            is_valid_at_asof = (
                (valid_at is None or valid_at <= as_of_dt)
                and (invalid_at is None or invalid_at > as_of_dt)
            )
            if is_valid_at_asof:
                current.append(to_result(e))
            elif invalid_at is not None and valid_at is not None and valid_at <= as_of_dt:
                # Was valid before as_of, got invalidated before as_of
                superseded.append(to_result(e))
        else:
            # No as_of: current = live edges, superseded = invalidated edges
            if invalid_at is None:
                current.append(to_result(e))
            else:
                superseded.append(to_result(e))

    return HistoryResult(
        current=current[: req.num_results],
        superseded=superseded[: req.num_results],
    )


@app.get("/episodes/{uuid}", response_model=EpisodeResult)
async def get_episode(uuid: str):
    """Fetch a single Episodic node by UUID, including connected entities.

    Returns the episode's content, source metadata, and reference time alongside
    a list of Entity nodes connected to this episode via any relationship type.
    Used by the L4 engine to reconstruct the raw evidence behind a given belief
    or to audit what entities a specific ingestion event extracted.
    """
    rows = await run_cypher("""
        MATCH (ep:Episodic {uuid: $uuid})
        OPTIONAL MATCH (ep)--(e:Entity)
        RETURN
            ep.uuid            AS uuid,
            ep.name            AS name,
            ep.content         AS content,
            ep.source_description AS source_description,
            ep.source          AS source,
            ep.reference_time  AS reference_time,
            ep.created_at      AS created_at,
            ep.group_id        AS group_id,
            collect(DISTINCT {uuid: e.uuid, name: e.name}) AS connected_entities
    """, uuid=uuid)

    if not rows:
        raise HTTPException(404, f"Episode {uuid} not found")

    r = rows[0]
    raw_entities = r.get("connected_entities") or []
    entities = [
        ConnectedEntity(uuid=ent["uuid"], name=ent["name"])
        for ent in raw_entities
        if ent.get("uuid") and ent.get("name")
    ]

    return EpisodeResult(
        uuid=r.get("uuid") or uuid,
        name=r.get("name"),
        content=r.get("content"),
        source_description=r.get("source_description"),
        source=str(r["source"]) if r.get("source") is not None else None,
        reference_time=_iso_or_none(r.get("reference_time")),
        created_at=_iso_or_none(r.get("created_at")),
        group_id=r.get("group_id"),
        connected_entities=entities,
    )
