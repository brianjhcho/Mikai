"""
Tests for the four MCP tool handlers exposed by sidecar/mcp_server.py.

These handlers are the surface Claude Desktop calls into. Bugs here show up
as malformed tool responses, silent "L3 backend not initialized" answers, or
dropped data — all of which are hard to notice without a test.

Post-ARCH-024 the tools call an `L3Backend`, not graphiti-core directly. We
replace the backend with a small fake that records every call the tools
made.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest


# ── Stub the mcp package so sidecar.mcp_server imports without the real SDK ───
#
# The sidecar's MCP server imports `mcp.server`, `mcp.server.stdio`, and
# `mcp.types` at module load time. We only need `mcp.types.TextContent` to
# actually behave, since that's what the tool handlers return.


def _install_mcp_stub() -> None:
    if "mcp.types" in sys.modules:
        return

    mcp = types.ModuleType("mcp")
    mcp_server = types.ModuleType("mcp.server")
    mcp_server_stdio = types.ModuleType("mcp.server.stdio")
    mcp_types = types.ModuleType("mcp.types")

    class _Server:
        def __init__(self, *_a, **_kw):
            pass

        def list_tools(self):
            return lambda fn: fn

        def call_tool(self):
            return lambda fn: fn

        def create_initialization_options(self):
            return None

        async def run(self, *_a, **_kw):
            return None

    mcp_server.Server = _Server

    async def _stub_stdio():
        yield (None, None)

    mcp_server_stdio.stdio_server = _stub_stdio

    @dataclass
    class TextContent:
        type: str
        text: str

    @dataclass
    class Tool:
        name: str
        description: str
        inputSchema: dict

    mcp_types.TextContent = TextContent
    mcp_types.Tool = Tool

    sys.modules["mcp"] = mcp
    sys.modules["mcp.server"] = mcp_server
    sys.modules["mcp.server.stdio"] = mcp_server_stdio
    sys.modules["mcp.types"] = mcp_types


_install_mcp_stub()

from sidecar import mcp_server  # noqa: E402  (after stub is installed)


# ── Fake L3 backend (port-shaped) ────────────────────────────────────────────


from sidecar.l3 import Edge as _PortEdge, GraphStats, HistoryResult, IngestResult


def _FakeEdge(
    *,
    uuid: str = "edge-1",
    name: str = "RELATES_TO",
    fact: str | None = "Brian writes code",
    source_node_name: str | None = "Brian",  # legacy kwarg name, preserved
    target_node_name: str | None = "code",
    valid_at: datetime | None = None,
    invalid_at: datetime | None = None,
    created_at: datetime | None = None,
    expired_at: datetime | None = None,
    episodes: list | None = None,
) -> _PortEdge:
    """Construct a port `Edge`, accepting the legacy `source_node_name` /
    `target_node_name` kwargs for backward-compat with existing test bodies."""
    return _PortEdge(
        uuid=uuid,
        source_uuid="src",
        target_uuid="tgt",
        source_name=source_node_name,
        target_name=target_node_name,
        name=name,
        fact=fact,
        valid_at=valid_at,
        invalid_at=invalid_at,
        expired_at=expired_at,
        created_at=created_at,
        episodes=list(episodes or []),
    )


class FakeGraphiti:
    """Port-shaped fake of an `L3Backend`. Records every tool-driven call.

    Name kept as `FakeGraphiti` to minimise test-body churn during the
    ARCH-024 refactor — the implementation now satisfies L3Backend, not
    the graphiti-core interface.
    """

    def __init__(
        self,
        *,
        search_edges: list | None = None,
        ingest_result: IngestResult | None = None,
    ):
        self._search_edges = search_edges or []
        self._ingest_result = ingest_result or IngestResult(
            episode_uuid="episode-1",
            entities_extracted=0,
            edges_extracted=0,
        )
        self.search_calls: list[dict] = []
        # Maintained for older assertions that look at add_calls[i]["episode_body"]
        self.add_calls: list[dict] = []
        # New port-shaped record (preferred for new tests)
        self.ingest_calls: list[dict] = []

    async def search(self, query):
        self.search_calls.append(
            {"query": query.text, "num_results": query.num_results}
        )
        return list(self._search_edges)

    async def history(self, query, as_of=None):
        edges = list(self._search_edges)
        current = [e for e in edges if e.invalid_at is None]
        superseded = [e for e in edges if e.invalid_at is not None]
        if as_of is not None:
            current = [
                e for e in edges
                if (e.valid_at is None or e.valid_at <= as_of)
                and (e.invalid_at is None or e.invalid_at > as_of)
            ]
            superseded = [
                e for e in edges
                if e.invalid_at is not None
                and (e.valid_at is None or e.valid_at <= as_of)
                and e.invalid_at <= as_of
            ]
        return HistoryResult(
            current=current[: query.num_results],
            superseded=superseded[: query.num_results],
        )

    async def ingest_episode(self, episode):
        # Record under both the legacy and new shapes for assertion flexibility.
        self.ingest_calls.append({
            "name": episode.name,
            "content": episode.content,
            "source_description": episode.source_description,
            "reference_time": episode.reference_time,
            "group_id": episode.group_id,
        })
        self.add_calls.append({
            "name": episode.name,
            "episode_body": episode.content,
            "source_description": episode.source_description,
            "reference_time": episode.reference_time,
            "group_id": episode.group_id,
        })
        return self._ingest_result

    # Used by mcp_server._tool_get_stats. Override per-test via set_stats().
    _stats: GraphStats = GraphStats(0, 0, 0, 0, 0)

    def set_stats(self, **kwargs):
        self._stats = GraphStats(
            entities=kwargs.get("entities", 0),
            edges=kwargs.get("edges", 0),
            episodes=kwargs.get("episodes", 0),
            communities=kwargs.get("communities", 0),
            orphans=kwargs.get("orphans", 0),
        )

    async def stats(self):
        return self._stats


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def install_graphiti(monkeypatch):
    """Swap in a FakeGraphiti as the module-level `backend` global."""
    def _install(fake: FakeGraphiti) -> FakeGraphiti:
        monkeypatch.setattr(mcp_server, "backend", fake)
        return fake
    return _install


# ── Search tool ──────────────────────────────────────────────────────────────


class TestSearchTool:
    async def test_returns_not_initialized_when_graphiti_is_none(self, monkeypatch):
        monkeypatch.setattr(mcp_server, "backend", None)
        result = await mcp_server._tool_search({"query": "anything"})
        assert len(result) == 1
        assert "not initialized" in result[0].text.lower()

    async def test_empty_result_set_returns_no_results_message(self, install_graphiti):
        install_graphiti(FakeGraphiti(search_edges=[]))
        result = await mcp_server._tool_search({"query": "nothing matches"})
        assert len(result) == 1
        assert "no results" in result[0].text.lower()
        assert "nothing matches" in result[0].text

    async def test_formats_edges_as_markdown(self, install_graphiti):
        fake = install_graphiti(FakeGraphiti(search_edges=[
            _FakeEdge(
                fact="Brian writes MIKAI",
                source_node_name="Brian",
                target_node_name="MIKAI",
                valid_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
            ),
        ]))
        result = await mcp_server._tool_search({"query": "brian"})
        text = result[0].text
        assert "Brian → MIKAI" in text
        assert "Brian writes MIKAI" in text
        assert "2026-03-01" in text
        assert fake.search_calls == [{"query": "brian", "num_results": 10}]

    async def test_respects_num_results_argument(self, install_graphiti):
        fake = install_graphiti(FakeGraphiti())
        await mcp_server._tool_search({"query": "q", "num_results": 42})
        assert fake.search_calls[0]["num_results"] == 42

    async def test_marks_invalidated_edges(self, install_graphiti):
        install_graphiti(FakeGraphiti(search_edges=[
            _FakeEdge(
                valid_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                invalid_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
            ),
        ]))
        result = await mcp_server._tool_search({"query": "q"})
        # "Invalidated" label is rendered when invalid_at is non-None.
        assert "Invalidated" in result[0].text


# ── History tool ─────────────────────────────────────────────────────────────


class TestHistoryTool:
    async def test_no_graphiti_returns_error(self, monkeypatch):
        monkeypatch.setattr(mcp_server, "backend", None)
        result = await mcp_server._tool_get_history({"query": "q"})
        assert "not initialized" in result[0].text.lower()

    async def test_splits_current_and_superseded_without_as_of(self, install_graphiti):
        install_graphiti(FakeGraphiti(search_edges=[
            # "current": no invalid_at
            _FakeEdge(fact="still-valid fact", invalid_at=None),
            # "superseded": has invalid_at
            _FakeEdge(
                fact="old fact",
                invalid_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            ),
        ]))
        result = await mcp_server._tool_get_history({"query": "anything"})
        text = result[0].text
        assert "Current facts" in text
        assert "still-valid fact" in text
        assert "Superseded facts" in text
        assert "old fact" in text

    async def test_as_of_filters_to_point_in_time(self, install_graphiti):
        # Edge A was valid from 2025, never invalidated — should count as
        # current for any as_of >= 2025.
        # Edge B was valid from 2025 but invalidated 2026-02-01 — should be
        # superseded for as_of = 2026-03-01, current for as_of = 2026-01-01.
        install_graphiti(FakeGraphiti(search_edges=[
            _FakeEdge(
                fact="always-valid",
                valid_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                invalid_at=None,
            ),
            _FakeEdge(
                fact="short-lived",
                valid_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                invalid_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            ),
        ]))
        result = await mcp_server._tool_get_history({
            "query": "q",
            "as_of": "2026-03-01T00:00:00+00:00",
        })
        text = result[0].text
        # At the 2026-03-01 snapshot, only always-valid is current.
        current_section = text.split("Superseded facts")[0]
        assert "always-valid" in current_section
        assert "short-lived" not in current_section
        # And short-lived should appear in the superseded section.
        assert "short-lived" in text

    async def test_no_matches_returns_fallback_message(self, install_graphiti):
        install_graphiti(FakeGraphiti(search_edges=[]))
        result = await mcp_server._tool_get_history({"query": "absent term"})
        assert "No facts found" in result[0].text
        assert "absent term" in result[0].text


# ── Add note tool ────────────────────────────────────────────────────────────


class TestAddNoteTool:
    async def test_rejects_empty_content_without_hitting_graphiti(self, install_graphiti):
        fake = install_graphiti(FakeGraphiti())
        result = await mcp_server._tool_add_note({"content": "   "})
        assert "Empty note" in result[0].text
        assert fake.add_calls == []

    async def test_persists_content_and_reports_counts(self, install_graphiti):
        fake = install_graphiti(FakeGraphiti(ingest_result=IngestResult(
            episode_uuid="ep-abc",
            entities_extracted=3,
            edges_extracted=2,
        )))
        result = await mcp_server._tool_add_note({
            "content": "Hello, this is a real note.",
            "source_description": "unit-test",
        })
        text = result[0].text
        assert "ep-abc" in text
        assert "Entities extracted: 3" in text
        assert "Relationships created: 2" in text
        # The handler must forward source_description and content verbatim.
        assert fake.add_calls[0]["source_description"] == "unit-test"
        assert fake.add_calls[0]["episode_body"] == "Hello, this is a real note."

    async def test_defaults_to_claude_conversation_source(self, install_graphiti):
        fake = install_graphiti(FakeGraphiti())
        await mcp_server._tool_add_note({"content": "Some substantive note."})
        assert fake.add_calls[0]["source_description"] == "claude-conversation"

    async def test_no_graphiti_returns_error(self, monkeypatch):
        monkeypatch.setattr(mcp_server, "backend", None)
        result = await mcp_server._tool_add_note({"content": "anything"})
        assert "not initialized" in result[0].text.lower()


# ── Stats tool ───────────────────────────────────────────────────────────────


class TestStatsTool:
    async def test_renders_counts_as_markdown_table(self, install_graphiti):
        fake = install_graphiti(FakeGraphiti())
        fake.set_stats(
            entities=6990, edges=12345, episodes=999,
            communities=42, orphans=350,
        )
        result = await mcp_server._tool_get_stats()
        text = result[0].text
        assert "6,990" in text
        assert "12,345" in text
        assert "999" in text
        assert "42" in text
        # Orphan percentage: 350/6990 ≈ 5.0%
        assert "5.0" in text

    async def test_handles_zero_entity_edge_case(self, install_graphiti):
        # Default FakeGraphiti.stats() returns GraphStats(0, 0, 0, 0, 0);
        # the 0/0 orphan-percent path must not raise.
        install_graphiti(FakeGraphiti())
        result = await mcp_server._tool_get_stats()
        assert "0" in result[0].text


# ── call_tool dispatch ───────────────────────────────────────────────────────


class TestCallToolDispatch:
    async def test_unknown_tool_name_returns_message_not_raise(self, install_graphiti):
        install_graphiti(FakeGraphiti())
        result = await mcp_server.call_tool("nonexistent_tool", {})
        assert len(result) == 1
        assert "Unknown tool" in result[0].text

    async def test_none_arguments_treated_as_empty(self, install_graphiti):
        install_graphiti(FakeGraphiti())
        # add_note with None args → should get "Empty note", not TypeError.
        result = await mcp_server.call_tool("add_note", None)
        assert "Empty note" in result[0].text
