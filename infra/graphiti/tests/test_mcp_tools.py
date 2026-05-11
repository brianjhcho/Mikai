"""
Tests for the four MCP tool handlers exposed by sidecar/mcp_server.py.

These handlers are the surface Claude Desktop calls into. Bugs here show up
as malformed tool responses, silent "Graphiti not initialized" answers, or
dropped data — all of which are hard to notice without a test.

The real graphiti client requires Neo4j + DeepSeek + Voyage credentials. We
replace it with a small fake object that records the calls each tool made.
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


# ── Fake Graphiti ────────────────────────────────────────────────────────────


@dataclass
class _FakeEdge:
    """Shape-compatible with what graphiti.search returns inside sidecar."""
    uuid: str = "edge-1"
    name: str = "edge-1"
    fact: str | None = "Brian writes code"
    source_node_name: str | None = "Brian"
    target_node_name: str | None = "code"
    valid_at: datetime | None = None
    invalid_at: datetime | None = None
    created_at: datetime | None = None
    expired_at: datetime | None = None
    episodes: list = field(default_factory=list)


@dataclass
class _FakeEpisode:
    uuid: str = "episode-1"


@dataclass
class _FakeAddResult:
    episode: _FakeEpisode = field(default_factory=_FakeEpisode)
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)


class FakeGraphiti:
    """Records every call the tool handlers make against graphiti."""

    def __init__(self, *, search_edges: list | None = None,
                 add_result: _FakeAddResult | None = None):
        self._search_edges = search_edges or []
        self._add_result = add_result or _FakeAddResult()
        self.search_calls: list[dict] = []
        self.add_calls: list[dict] = []

    async def search(self, *, query, num_results=10, **_kw):
        self.search_calls.append({"query": query, "num_results": num_results})
        return self._search_edges

    async def add_episode(self, **kwargs):
        self.add_calls.append(kwargs)
        return self._add_result


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def install_graphiti(monkeypatch):
    """Swap in a FakeGraphiti as the module-level `graphiti` global."""
    def _install(fake: FakeGraphiti) -> FakeGraphiti:
        monkeypatch.setattr(mcp_server, "graphiti", fake)
        return fake
    return _install


# ── Search tool ──────────────────────────────────────────────────────────────


class TestSearchTool:
    async def test_returns_not_initialized_when_graphiti_is_none(self, monkeypatch):
        monkeypatch.setattr(mcp_server, "graphiti", None)
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
        monkeypatch.setattr(mcp_server, "graphiti", None)
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
        add_result = _FakeAddResult(
            episode=_FakeEpisode(uuid="ep-abc"),
            nodes=[object(), object(), object()],
            edges=[object(), object()],
        )
        fake = install_graphiti(FakeGraphiti(add_result=add_result))
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
        monkeypatch.setattr(mcp_server, "graphiti", None)
        result = await mcp_server._tool_add_note({"content": "anything"})
        assert "not initialized" in result[0].text.lower()


# ── Stats tool ───────────────────────────────────────────────────────────────


class TestStatsTool:
    async def test_renders_counts_as_markdown_table(self, monkeypatch, install_graphiti):
        # The stats tool runs a Cypher query via run_cypher(). Stub that out.
        install_graphiti(FakeGraphiti())  # graphiti non-None

        async def fake_run_cypher(_query, **_kwargs):
            return [{
                "entity_count": 6990,
                "edge_count": 12345,
                "episode_count": 999,
                "community_count": 42,
                "orphan_count": 350,
            }]

        monkeypatch.setattr(mcp_server, "run_cypher", fake_run_cypher)

        result = await mcp_server._tool_get_stats()
        text = result[0].text
        assert "6,990" in text
        assert "12,345" in text
        assert "999" in text
        assert "42" in text
        # Orphan percentage: 350/6990 ≈ 5.0%
        assert "5.0" in text

    async def test_handles_empty_cypher_response(self, monkeypatch, install_graphiti):
        install_graphiti(FakeGraphiti())

        async def fake_run_cypher(*_a, **_kw):
            return []

        monkeypatch.setattr(mcp_server, "run_cypher", fake_run_cypher)
        result = await mcp_server._tool_get_stats()
        assert "Could not fetch" in result[0].text

    async def test_handles_zero_entity_edge_case(self, monkeypatch, install_graphiti):
        install_graphiti(FakeGraphiti())

        async def fake_run_cypher(*_a, **_kw):
            return [{
                "entity_count": 0, "edge_count": 0, "episode_count": 0,
                "community_count": 0, "orphan_count": 0,
            }]

        monkeypatch.setattr(mcp_server, "run_cypher", fake_run_cypher)
        # 0/0 must not raise.
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
