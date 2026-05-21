"""Tests for the L3Backend port (ARCH-024).

These exercise the port shape + GraphitiAdapter's translation logic against
mocks. Live Graphiti behavior is covered by the existing sidecar suite once
product code is refactored to use the port — those tests still talk to a
real Graphiti instance.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sidecar.l3 import (
    L3Backend,
    GraphitiAdapter,
    Episode,
    Edge,
    Node,
    SearchQuery,
)
from sidecar.l3.graphiti_adapter import _edge_from_graphiti, _parse_dt


# ── Port shape ────────────────────────────────────────────────────────────────


PORT_METHODS = [
    "ingest_episode",
    "search",
    "search_nodes",
    "get_node",
    "expand",
    "edges_between",
    "history",
    "get_source",
    "stats",
    "communities",
    "close",
]


def test_l3backend_is_abstract():
    """You cannot instantiate the port directly."""
    with pytest.raises(TypeError):
        L3Backend()  # type: ignore[abstract]


def test_port_advertises_every_primitive():
    for m in PORT_METHODS:
        attr = getattr(L3Backend, m, None)
        assert attr is not None, f"L3Backend missing required method: {m}"
        assert getattr(attr, "__isabstractmethod__", False), (
            f"L3Backend.{m} is not abstract — implementations could skip it"
        )


def test_graphiti_adapter_implements_every_method():
    for m in PORT_METHODS:
        assert hasattr(GraphitiAdapter, m), f"GraphitiAdapter missing {m}"
    # also confirm signatures are async — they should all be coroutines
    for m in PORT_METHODS:
        fn = getattr(GraphitiAdapter, m)
        assert inspect.iscoroutinefunction(fn), (
            f"GraphitiAdapter.{m} must be async (storage I/O is async)"
        )


# ── Domain types are immutable-ish dataclasses with sensible defaults ──────


def test_episode_minimum_fields():
    ep = Episode(
        content="hi", source_description="claude-code",
        reference_time=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )
    assert ep.group_id == "mikai-default"
    assert ep.name is None


def test_edge_carries_confidence_field_for_stage6():
    """Stage 6 epistemic edges put confidence on every edge."""
    e = Edge(
        uuid="e1", source_uuid="s", target_uuid="t",
        source_name=None, target_name=None,
        name="CONTRADICTS", fact="...",
        valid_at=None, invalid_at=None, expired_at=None, created_at=None,
        confidence=0.8,
    )
    assert e.confidence == 0.8


def test_search_query_defaults():
    q = SearchQuery(text="kenya coffee")
    assert q.num_results == 10
    assert q.group_ids is None


# ── Translation helpers ──────────────────────────────────────────────────────


def test_parse_dt_handles_datetime_iso_and_none():
    dt = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)
    assert _parse_dt(dt) == dt
    assert _parse_dt(dt.isoformat()) == dt
    assert _parse_dt(None) is None
    assert _parse_dt("not a date") is None


def test_edge_from_graphiti_preserves_fields():
    """The translator pulls everything the port needs off a graphiti EntityEdge."""
    g_edge = SimpleNamespace(
        uuid="e-1",
        source_node_uuid="s-1",
        target_node_uuid="t-1",
        source_node_name="Brian",
        target_node_name="Project",
        name="DEPENDS_ON",
        fact="Brian depends on Project",
        valid_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        invalid_at=None,
        expired_at=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        episodes=["ep-1", "ep-2"],
        confidence=0.7,
    )
    out = _edge_from_graphiti(g_edge, score=1.5)
    assert out.uuid == "e-1"
    assert out.source_uuid == "s-1"
    assert out.target_uuid == "t-1"
    assert out.source_name == "Brian"
    assert out.name == "DEPENDS_ON"
    assert out.fact == "Brian depends on Project"
    assert out.episodes == ["ep-1", "ep-2"]
    assert out.confidence == 0.7
    assert out.score == 1.5


def test_edge_from_graphiti_defaults_untyped_name_to_relates_to():
    """Pre-Stage-6 edges have no `name` attribute populated — port should fall
    back to the canonical relationship label."""
    g_edge = SimpleNamespace(
        uuid="e-2", source_node_uuid="s", target_node_uuid="t",
        source_node_name=None, target_node_name=None,
        name=None, fact=None,
        valid_at=None, invalid_at=None, expired_at=None, created_at=None,
        episodes=None,
    )
    assert _edge_from_graphiti(g_edge).name == "RELATES_TO"


# ── GraphitiAdapter — happy-path translation with a mock Graphiti ──────────


@pytest.fixture
def mock_graphiti():
    """A Graphiti with the methods the adapter touches, all async-mocked."""
    g = MagicMock()
    g.search = AsyncMock(return_value=[])
    g.search_ = AsyncMock(return_value=SimpleNamespace(nodes=[], communities=[]))
    g.add_episode = AsyncMock()
    g.add_episode_bulk = AsyncMock()
    g.close = AsyncMock()
    g.driver = MagicMock()
    return g


@pytest.mark.asyncio
async def test_adapter_search_returns_port_edges(mock_graphiti):
    mock_graphiti.search.return_value = [
        SimpleNamespace(
            uuid="e-1", source_node_uuid="s", target_node_uuid="t",
            source_node_name="A", target_node_name="B",
            name="SUPPORTS", fact="A supports B",
            valid_at=None, invalid_at=None, expired_at=None, created_at=None,
            episodes=[], confidence=0.9,
        ),
    ]
    adapter = GraphitiAdapter(mock_graphiti)
    edges = await adapter.search(SearchQuery(text="anything"))
    assert len(edges) == 1
    assert isinstance(edges[0], Edge)
    assert edges[0].name == "SUPPORTS"
    assert edges[0].confidence == 0.9
    # the underlying call was made with the unwrapped fields
    mock_graphiti.search.assert_awaited_once_with(
        query="anything", group_ids=None, num_results=10,
    )


@pytest.mark.asyncio
async def test_adapter_close_is_idempotent(mock_graphiti):
    adapter = GraphitiAdapter(mock_graphiti)
    await adapter.close()
    await adapter.close()  # should not blow up or double-call
    assert mock_graphiti.close.await_count == 1


@pytest.mark.asyncio
async def test_make_backend_default_is_graphiti(monkeypatch):
    """MIKAI_L3_BACKEND unset → factory chooses GraphitiAdapter (we won't
    actually init Graphiti here; just confirm the routing branch)."""
    from sidecar.l3 import make_backend

    called: dict[str, Any] = {}

    async def fake_init():
        called["init"] = True
        return MagicMock()

    monkeypatch.setattr("sidecar.client.init_graphiti", fake_init)
    monkeypatch.delenv("MIKAI_L3_BACKEND", raising=False)

    backend = await make_backend()
    assert isinstance(backend, GraphitiAdapter)
    assert called["init"] is True


@pytest.mark.asyncio
async def test_make_backend_local_not_yet_implemented(monkeypatch):
    from sidecar.l3 import make_backend

    monkeypatch.setenv("MIKAI_L3_BACKEND", "local")
    with pytest.raises(NotImplementedError):
        await make_backend()


@pytest.mark.asyncio
async def test_make_backend_unknown_raises(monkeypatch):
    from sidecar.l3 import make_backend

    monkeypatch.setenv("MIKAI_L3_BACKEND", "nope")
    with pytest.raises(ValueError):
        await make_backend()
