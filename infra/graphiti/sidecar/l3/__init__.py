"""MIKAI L3 — knowledge graph layer.

Product code (MCP tools, REST endpoints, ingestion daemon) imports the
L3Backend port from this package — never graphiti-core directly. The
composition root (`sidecar/main.py` lifespan) picks an adapter based on
MIKAI_L3_BACKEND env var.

See ARCH-024 (port introduced), ARCH-025 (LocalAdapter as first-class
alternate), D-041 (port primitives only — no L4 semantics).
"""

import os
import logging

from sidecar.l3.port import (
    L3Backend,
    Episode,
    IngestResult,
    Node,
    Edge,
    SearchQuery,
    Subgraph,
    HistoryResult,
    Community,
    GraphStats,
    SourceEpisode,
)
from sidecar.l3.graphiti_adapter import GraphitiAdapter

logger = logging.getLogger("mikai-graphiti")


async def make_backend() -> L3Backend:
    """Composition root entry point. Read MIKAI_L3_BACKEND, build the
    chosen adapter, return it as L3Backend.

    Defaults to "graphiti". "local" is reserved for ARCH-025's LocalAdapter
    and raises NotImplementedError today.
    """
    choice = (os.environ.get("MIKAI_L3_BACKEND") or "graphiti").strip().lower()
    if choice == "graphiti":
        # Lazy-import the Graphiti wiring helper to keep this module's
        # import cost low for environments that select "local" (future).
        from sidecar.client import init_graphiti as _init_graphiti
        graphiti = await _init_graphiti()
        logger.info("L3 backend: GraphitiAdapter (Neo4j + DeepSeek + Voyage)")
        return GraphitiAdapter(graphiti)
    if choice == "local":
        raise NotImplementedError(
            "MIKAI_L3_BACKEND=local: LocalAdapter (ARCH-025) is not yet built. "
            "Use 'graphiti' or unset for the current default."
        )
    raise ValueError(
        f"MIKAI_L3_BACKEND={choice!r} unknown — expected 'graphiti' or 'local'"
    )


__all__ = [
    "L3Backend",
    "GraphitiAdapter",
    "make_backend",
    "Episode",
    "IngestResult",
    "Node",
    "Edge",
    "SearchQuery",
    "Subgraph",
    "HistoryResult",
    "Community",
    "GraphStats",
    "SourceEpisode",
]
