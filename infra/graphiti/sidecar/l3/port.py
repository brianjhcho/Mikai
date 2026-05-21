"""L3Backend port — the contract product code depends on.

Per ARCH-024: "no infrastructure nouns." Domain types only — nothing in
this module imports from graphiti_core, Neo4j drivers, or any specific
adapter. Adapters translate to their own machinery.

Per ARCH-025: a future LocalAdapter implements this same interface and
is selected at startup via MIKAI_L3_BACKEND=local.

Per D-041: L3 exposes graph primitives only. Tension detection, thread
detection, state classification, next-step inference all belong to L4
and are built ON TOP of these primitives — not behind them.

All methods are async because every current backend's storage I/O is
async. Synchronous adapters can still implement these by returning
already-resolved coroutines.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

# ── Domain types ─────────────────────────────────────────────────────────────


@dataclass
class Episode:
    """A single piece of source content being ingested into the graph."""

    content: str
    source_description: str  # e.g. "apple-notes", "claude-code", "gmail"
    reference_time: datetime
    group_id: str = "mikai-default"
    name: str | None = None  # optional display name; defaults to source_description


@dataclass
class IngestResult:
    episode_uuid: str
    entities_extracted: int
    edges_extracted: int


@dataclass
class Node:
    uuid: str
    name: str
    labels: list[str] = field(default_factory=list)
    summary: str | None = None
    created_at: datetime | None = None


@dataclass
class Edge:
    """A fact connecting two entities, with bitemporal validity."""

    uuid: str
    source_uuid: str
    target_uuid: str
    source_name: str | None
    target_name: str | None
    name: str  # edge type name — "RELATES_TO" for untyped, e.g. "CONTRADICTS" for epistemic
    fact: str | None
    valid_at: datetime | None
    invalid_at: datetime | None
    expired_at: datetime | None
    created_at: datetime | None
    episodes: list[str] = field(default_factory=list)
    confidence: float | None = None  # Stage 6 epistemic edges
    score: float | None = None  # search-time relevance (None if not from a search)


@dataclass
class SourceEpisode:
    """Raw episode content matching a query — the prose that grounded an extraction."""

    uuid: str
    content: str
    source: str
    source_description: str
    valid_at: datetime | None
    score: float | None = None


@dataclass
class Subgraph:
    """A center node plus its 1-hop neighborhood."""

    center: Node
    nodes: list[Node]
    edges: list[Edge]


@dataclass
class HistoryResult:
    """Bitemporal split: current vs superseded facts at a point in time."""

    current: list[Edge]
    superseded: list[Edge]


@dataclass
class Community:
    uuid: str
    name: str
    summary: str | None = None


@dataclass
class GraphStats:
    entities: int
    edges: int
    episodes: int
    communities: int
    orphans: int


@dataclass
class SearchQuery:
    """The shape of any read query against the graph."""

    text: str
    num_results: int = 10
    group_ids: list[str] | None = None


# ── Port ──────────────────────────────────────────────────────────────────────


class L3Backend(ABC):
    """The L3 port. Product code depends on this; adapters implement it.

    Implementations: GraphitiAdapter (production), LocalAdapter (ARCH-025).
    """

    # ── Write ──

    @abstractmethod
    async def ingest_episode(self, episode: Episode) -> IngestResult:
        """Write a new episode to the graph. The adapter handles extraction,
        entity resolution, and (where applicable) bitemporal invalidation."""

    # ── Read — edges ──

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[Edge]:
        """Hybrid edge search. Returns facts ranked by relevance."""

    @abstractmethod
    async def history(
        self, query: SearchQuery, as_of: datetime | None = None
    ) -> HistoryResult:
        """Point-in-time edge search. Splits current vs superseded facts.
        as_of=None means 'right now'."""

    @abstractmethod
    async def edges_between(
        self,
        node_uuids: list[str],
        *,
        as_of: datetime | None = None,
        include_invalidated: bool = False,
    ) -> list[Edge]:
        """Return all edges whose endpoints are both in the given UUID set.
        The primitive for cluster-internal structure inspection."""

    # ── Read — nodes ──

    @abstractmethod
    async def search_nodes(self, query: SearchQuery) -> list[Node]:
        """Node-level search (distinct from edge search). Useful for seeding
        traversals or surfacing entities directly."""

    @abstractmethod
    async def get_node(self, uuid: str) -> Node | None:
        """Fetch a single node by UUID. None if not found."""

    @abstractmethod
    async def expand(
        self,
        uuid: str,
        *,
        max_edges: int = 20,
        include_invalidated: bool = False,
    ) -> Subgraph:
        """BFS one hop from a node. Returns the center, its neighbors, and
        the connecting edges. Raises KeyError if the center doesn't exist."""

    # ── Read — episodes (raw source) ──

    @abstractmethod
    async def get_source(
        self, query: str, num_results: int = 5
    ) -> list[SourceEpisode]:
        """Full-text search over raw episode content. Returns the prose that
        grounded the extracted facts — what `search` compresses into edges."""

    # ── Read — global ──

    @abstractmethod
    async def stats(self) -> GraphStats:
        """Graph snapshot — entity / edge / episode / community / orphan counts."""

    @abstractmethod
    async def communities(self) -> list[Community]:
        """Detected communities (e.g. from Graphiti's community-detection pass)."""

    # ── Lifecycle ──

    @abstractmethod
    async def close(self) -> None:
        """Release storage handles. Safe to call multiple times."""
