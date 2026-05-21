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
  *    /mcp                 — MCP Streamable HTTP (Claude Desktop/mobile/browser)

D-043: MCP is mounted in-process at /mcp, sharing the Graphiti singleton
with the REST endpoints above. One codebase, one Graphiti connection, one
public URL for all three Claude surfaces.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from sidecar.client import iso_or_none as _iso_or_none
from sidecar.l3 import (
    Episode,
    L3Backend,
    SearchQuery,
    make_backend,
)
from sidecar.mcp_tools import build_mcp
from sidecar.recency import apply_recency_decay
from sidecar.oauth import OAuthConfig, OAuthMiddleware, OAuthProvider

logger = logging.getLogger("mikai-graphiti")
logging.basicConfig(level=logging.INFO)


# ── L3 backend (ARCH-024) ────────────────────────────────────────────────────

backend: L3Backend | None = None

_mcp_bundle = build_mcp(lambda: backend)
mcp = _mcp_bundle.mcp
_mcp_tool_names = _mcp_bundle.tool_names


@asynccontextmanager
async def lifespan(app: FastAPI):
    global backend
    logger.info("Composing L3 backend (selector: MIKAI_L3_BACKEND env var)…")
    backend = await make_backend()
    try:
        # make_backend() runs build_indices_and_constraints inside GraphitiAdapter.
        async with mcp.session_manager.run():
            logger.info("MCP streamable HTTP session manager ready at /mcp")
            yield
    finally:
        if backend:
            await backend.close()
            logger.info("L3 backend closed")


app = FastAPI(title="MIKAI Graphiti Sidecar", version="2.0.0", lifespan=lifespan)
app.mount("/mcp", mcp.streamable_http_app())


# OAuth 2.1 Authorization Server + /mcp token gate (D-048). When
# MIKAI_OAUTH_ENABLED is unset the sidecar keeps its prior behavior:
# open, or static MIKAI_MCP_TOKEN bearer auth. OAuth routes are served at
# the site root (not under the /mcp mount) so discovery works.
oauth = OAuthProvider(OAuthConfig.from_env())
if oauth.enabled:
    app.include_router(oauth.router())
    logger.info("OAuth 2.1 enabled — /mcp requires a bearer access token")
app.add_middleware(OAuthMiddleware, provider=oauth)


class MCPTrailingSlashMiddleware:
    """Rewrite /mcp (no slash) to /mcp/ before routing.

    Starlette's Mount redirects /mcp → /mcp/ with a 307, which MCP clients
    (including Claude.ai's hosted Custom Connector) do not follow for POSTs —
    the JSON-RPC body is lost and the handshake fails. Rewriting the ASGI
    scope in-place avoids the redirect entirely.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
            scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


app.add_middleware(MCPTrailingSlashMiddleware)


@app.get("/mcp-healthcheck")
async def mcp_healthcheck():
    """Public smoke-test endpoint — always reachable even when /mcp requires auth."""
    return {
        "mcp": "ok",
        "graphiti": backend is not None,
        "tools": _mcp_tool_names,
        "auth_required": oauth.active,
        "auth_mode": (
            "oauth" if oauth.enabled
            else "static-token" if oauth.cfg.static_token
            else "open"
        ),
    }


# ── Models ───────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    group_ids: list[str] | None = None
    num_results: int = 10
    recency_decay: bool = True


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
    return {"status": "ok", "backend": "graphiti-deepseek", "neo4j": backend is not None}


# ── Port → REST translation helpers ──────────────────────────────────────────


def _edge_to_result(e) -> "SearchResult":
    """Convert a port Edge dataclass to the REST SearchResult Pydantic model.

    Field names differ where the port chose Pythonic naming (source_name) over
    Graphiti's verbose form (source_node_name); we preserve the HTTP API.
    """
    return SearchResult(
        uuid=str(e.uuid),
        name=e.name or "",
        fact=e.fact or "",
        source_node_name=e.source_name,
        target_node_name=e.target_name,
        created_at=_iso_or_none(e.created_at),
        valid_at=_iso_or_none(e.valid_at),
        invalid_at=_iso_or_none(e.invalid_at),
        expired_at=_iso_or_none(e.expired_at),
        episodes=list(e.episodes or []),
    )


@app.post("/search", response_model=list[SearchResult])
async def search(req: SearchRequest):
    """Hybrid search via the L3 backend (vec + BM25 + RRF on GraphitiAdapter)."""
    if not backend:
        raise HTTPException(503, "L3 backend not initialized")

    edges = await backend.search(SearchQuery(
        text=req.query,
        group_ids=req.group_ids,
        num_results=req.num_results,
    ))
    if req.recency_decay:
        edges = apply_recency_decay(edges, reference_time=datetime.now())

    return [_edge_to_result(e) for e in edges]


@app.post("/episode")
async def add_episode(req: EpisodeRequest):
    """Add a single episode via the L3 backend."""
    if not backend:
        raise HTTPException(503, "L3 backend not initialized")

    ref_time = (
        datetime.fromisoformat(req.reference_time)
        if req.reference_time else datetime.now()
    )

    result = await backend.ingest_episode(Episode(
        content=req.content,
        source_description=req.source_description,
        reference_time=ref_time,
        group_id=req.group_id,
        name=req.source_description,
    ))

    return {
        "status": "ok",
        "episode_id": result.episode_uuid or None,
        "nodes_created": result.entities_extracted,
        "edges_created": result.edges_extracted,
    }


@app.post("/episode/bulk")
async def add_episode_bulk(req: BulkEpisodeRequest):
    """Bulk import episodes — shared-context extraction when the backend
    supports it (GraphitiAdapter delegates to graphiti.add_episode_bulk)."""
    if not backend:
        raise HTTPException(503, "L3 backend not initialized")

    episodes: list[Episode] = []
    for ep in req.episodes:
        ref_time = (
            datetime.fromisoformat(ep.reference_time)
            if ep.reference_time else datetime.now()
        )
        episodes.append(Episode(
            content=ep.content,
            source_description=ep.source_description,
            reference_time=ref_time,
            group_id=req.group_id,
            name=ep.name,
        ))

    logger.info(f"Bulk importing {len(episodes)} episodes…")
    result = await backend.ingest_episode_bulk(episodes)
    logger.info(
        "Bulk import done: %d nodes, %d edges",
        result.entities_extracted, result.edges_extracted,
    )

    return {
        "status": "ok",
        "episodes_created": len(episodes),
        "nodes_created": result.entities_extracted,
        "edges_created": result.edges_extracted,
        # community_count is no longer returned by the port; preserved as 0
        # for response shape compatibility. Bulk import never created
        # communities on its own — that's a separate Graphiti pass.
        "communities_created": 0,
    }


@app.post("/communities", response_model=list[CommunityResult])
async def get_communities():
    """Get community summaries via the L3 backend."""
    if not backend:
        raise HTTPException(503, "L3 backend not initialized")

    communities = await backend.communities()
    return [
        CommunityResult(uuid=c.uuid, name=c.name, summary=c.summary or "")
        for c in communities
    ]


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


# ── Endpoints ────────────────────────────────────────────────────────────────


@app.get("/stats", response_model=StatsResult)
async def get_stats():
    """Graph quality snapshot via the L3 backend."""
    if not backend:
        raise HTTPException(503, "L3 backend not initialized")
    s = await backend.stats()
    return StatsResult(
        entity_count=s.entities,
        edge_count=s.edges,
        episode_count=s.episodes,
        community_count=s.communities,
        orphan_count=s.orphans,
    )


@app.post("/nodes/search", response_model=list[NodeResult])
async def search_nodes(req: NodesSearchRequest):
    """Node-level hybrid search. Distinct from /search which returns edges."""
    if not backend:
        raise HTTPException(503, "L3 backend not initialized")

    nodes = await backend.search_nodes(SearchQuery(
        text=req.query,
        num_results=req.num_results,
        group_ids=req.group_ids,
    ))
    return [
        NodeResult(
            uuid=n.uuid,
            name=n.name,
            labels=list(n.labels or []),
            summary=n.summary,
            created_at=_iso_or_none(n.created_at),
        )
        for n in nodes
    ]


@app.get("/nodes/{uuid}", response_model=NodeResult)
async def get_node(uuid: str):
    """Fetch a single entity node by UUID via the L3 backend."""
    if not backend:
        raise HTTPException(503, "L3 backend not initialized")
    n = await backend.get_node(uuid)
    if not n:
        raise HTTPException(404, f"Node {uuid} not found")
    return NodeResult(
        uuid=n.uuid,
        name=n.name,
        labels=list(n.labels or []),
        summary=n.summary,
        created_at=_iso_or_none(n.created_at),
    )


def _node_to_result(n) -> NodeResult:
    return NodeResult(
        uuid=n.uuid,
        name=n.name,
        labels=list(n.labels or []),
        summary=n.summary,
        created_at=_iso_or_none(n.created_at),
    )


def _edge_to_edge_result(e) -> EdgeResult:
    return EdgeResult(
        uuid=str(e.uuid),
        source_uuid=str(e.source_uuid or ""),
        target_uuid=str(e.target_uuid or ""),
        source_name=e.source_name,
        target_name=e.target_name,
        fact=e.fact,
        valid_at=_iso_or_none(e.valid_at),
        invalid_at=_iso_or_none(e.invalid_at),
        expired_at=_iso_or_none(e.expired_at),
        episodes=list(e.episodes or []),
    )


@app.post("/nodes/{uuid}/expand", response_model=ExpandResult)
async def expand_node(uuid: str, req: ExpandRequest):
    """BFS 1-hop from a node — center + neighbors + connecting edges."""
    if not backend:
        raise HTTPException(503, "L3 backend not initialized")
    try:
        sub = await backend.expand(
            uuid,
            max_edges=req.max_edges,
            include_invalidated=req.include_invalidated,
        )
    except KeyError:
        raise HTTPException(404, f"Node {uuid} not found")

    return ExpandResult(
        center=_node_to_result(sub.center),
        nodes=[_node_to_result(n) for n in sub.nodes],
        edges=[_edge_to_edge_result(e) for e in sub.edges],
    )


@app.post("/edges/between", response_model=list[EdgeResult])
async def edges_between(req: EdgesBetweenRequest):
    """Return all edges where both endpoints are in the given UUID set.

    This is the primitive the L4 engine will use for thread enrichment —
    once a candidate cluster of entities has been identified (via expand,
    search, or community detection), this query reveals the internal
    relationship structure of that cluster.
    """
    if not backend:
        raise HTTPException(503, "L3 backend not initialized")
    if not req.node_uuids:
        return []

    as_of_dt = datetime.fromisoformat(req.as_of) if req.as_of else None
    edges = await backend.edges_between(
        req.node_uuids,
        as_of=as_of_dt,
        include_invalidated=req.include_invalidated,
    )
    return [_edge_to_edge_result(e) for e in edges]


@app.post("/history", response_model=HistoryResult)
async def history(req: HistoryRequest):
    """Bitemporal point-in-time search via the L3 backend."""
    if not backend:
        raise HTTPException(503, "L3 backend not initialized")

    as_of_dt = datetime.fromisoformat(req.as_of) if req.as_of else None
    result = await backend.history(
        SearchQuery(text=req.query, num_results=req.num_results),
        as_of=as_of_dt,
    )
    return HistoryResult(
        current=[_edge_to_result(e) for e in result.current],
        superseded=[_edge_to_result(e) for e in result.superseded],
    )
