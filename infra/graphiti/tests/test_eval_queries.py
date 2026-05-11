"""
Tests for scripts/eval_queries.py — the Stage 4 retrieval-groundedness rater.

Same shape as test_eval_nodes.py: pure helpers tested against fixtures, the
GraphProbe protocol tested with a fake driver, the interactive rating UI
not tested (requires a human).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import eval_queries as eq  # noqa: E402  type: ignore


# ── Fakes ────────────────────────────────────────────────────────────────────


class FakeProbe:
    """In-memory GraphProbe for tests. Returns canned rows per-query and a
    fixed episode body keyed by episode_uuid."""

    def __init__(
        self,
        rows_by_query: dict[str, list[dict]] | None = None,
        episodes: dict[str, dict] | None = None,
    ):
        self._rows = rows_by_query or {}
        self._episodes = episodes or {}
        self.search_calls: list[tuple[str, int]] = []
        self.episode_lookups: list[str] = []

    async def search(self, query: str, top_k: int) -> list[dict]:
        self.search_calls.append((query, top_k))
        return list(self._rows.get(query, []))

    async def fetch_citation_episode(self, episode_uuid: str) -> dict | None:
        self.episode_lookups.append(episode_uuid)
        return self._episodes.get(episode_uuid)


def _row(rank: int, *, fact: str = "", src: str = "", tgt: str = "",
         valid: str | None = None, episodes: list[str] | None = None) -> dict:
    return {
        "rank": rank,
        "fact": fact,
        "source_node_name": src,
        "target_node_name": tgt,
        "valid_at": valid,
        "episodes": episodes or [],
    }


# ── to_hit ───────────────────────────────────────────────────────────────────


def test_to_hit_with_episode():
    row = _row(1, fact="X plays poker", src="Brian", tgt="Poker",
               episodes=["ep-1"])
    ep = {"uuid": "ep-1", "name": "thread-2024-01", "content": "long content"}
    hit = eq.to_hit(row, ep)
    assert hit.rank == 1
    assert hit.fact == "X plays poker"
    assert hit.source_node_name == "Brian"
    assert hit.target_node_name == "Poker"
    assert hit.episode_uuid == "ep-1"
    assert hit.episode_content == "long content"


def test_to_hit_without_episode():
    row = _row(2, fact="orphan fact")
    hit = eq.to_hit(row, None)
    assert hit.episode_uuid is None
    assert hit.episode_content is None
    assert hit.fact == "orphan fact"


# ── format_query_card ────────────────────────────────────────────────────────


def test_format_query_card_renders_hits():
    run = eq.QueryRun(
        query="poker strategy",
        hits=[
            eq.SearchHit(rank=1, fact="X uses GTO opens", source_node_name="X",
                         target_node_name="GTO", valid_at="2024-01-01",
                         episode_uuid="e1", episode_content="we discussed GTO"),
        ],
    )
    out = eq.format_query_card(run)
    assert "Query:   poker strategy" in out
    assert "X → GTO" in out
    assert "[2024-01-01]" in out
    assert "we discussed GTO" in out


def test_format_query_card_handles_zero_hits():
    run = eq.QueryRun(query="absolutely nothing", hits=[])
    out = eq.format_query_card(run)
    assert "(no results)" in out
    assert "Hits:    0" in out


def test_format_query_card_truncates_long_episode():
    long_body = "a" * 2000
    run = eq.QueryRun(
        query="q",
        hits=[
            eq.SearchHit(rank=1, fact="f", source_node_name="s",
                         target_node_name="t", valid_at=None,
                         episode_uuid="e1", episode_content=long_body),
        ],
    )
    out = eq.format_query_card(run, max_episode_chars=100)
    assert "a" * 100 in out
    assert "+1900 chars" in out


# ── render_results_md ────────────────────────────────────────────────────────


def _rating(query: str, *, rel: int, gnd: int, hits: int = 1, note: str = "") -> eq.QueryRating:
    run = eq.QueryRun(
        query=query,
        hits=[
            eq.SearchHit(rank=i + 1, fact="", source_node_name="",
                         target_node_name="", valid_at=None,
                         episode_uuid=None, episode_content=None)
            for i in range(hits)
        ],
    )
    return eq.QueryRating(run=run, relevance_at_k=rel, groundedness=gnd, note=note)


def test_render_results_md_includes_run_header_and_means():
    ratings = [
        _rating("poker", rel=8, gnd=4),
        _rating("trading", rel=4, gnd=3),
    ]
    out = eq.render_results_md(
        ratings, when=date(2026, 4, 29), backend="graphiti", top_k=10,
    )
    assert "## Run — 2026-04-29 (graphiti, queries=2, k=10)" in out
    assert "| 1 | poker | 8/10 | 4 |" in out
    assert "| 2 | trading | 4/10 | 3 |" in out
    assert "relevance=6.00/10" in out
    assert "groundedness=3.50" in out


def test_render_results_md_escapes_pipes_in_query_and_note():
    ratings = [_rating("a|b", rel=1, gnd=1, note="line1\nline2|piped")]
    out = eq.render_results_md(
        ratings, when=date(2026, 4, 29), backend="graphiti", top_k=10,
    )
    # Pipes are escaped, newlines flattened
    assert "a\\|b" in out
    assert "line1 line2\\|piped" in out


def test_render_results_md_handles_empty_set():
    out = eq.render_results_md(
        [], when=date(2026, 4, 29), backend="graphiti", top_k=10,
    )
    assert "queries=0" in out
    # No "Run mean" line when there's nothing to mean over
    assert "Run mean" not in out


# ── append_results_md ────────────────────────────────────────────────────────


def test_append_writes_header_on_first_run(tmp_path: Path):
    target = tmp_path / "queries-2026-04-29.md"
    eq.append_results_md(
        target, "BODY-1\n", when=date(2026, 4, 29), backend="graphiti",
    )
    content = target.read_text()
    assert "# Query-retrieval eval — 2026-04-29" in content
    assert "BODY-1" in content


def test_append_appends_on_subsequent_runs(tmp_path: Path):
    target = tmp_path / "queries-2026-04-29.md"
    eq.append_results_md(
        target, "BODY-1\n", when=date(2026, 4, 29), backend="graphiti",
    )
    eq.append_results_md(
        target, "BODY-2\n", when=date(2026, 4, 29), backend="graphiti",
    )
    content = target.read_text()
    # Header written once; both bodies present in order
    assert content.count("# Query-retrieval eval") == 1
    assert content.index("BODY-1") < content.index("BODY-2")


# ── collect_runs ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_collect_runs_resolves_first_cited_episode():
    probe = FakeProbe(
        rows_by_query={
            "poker": [_row(1, fact="X plays", episodes=["e1", "e9"])],
        },
        episodes={"e1": {"uuid": "e1", "content": "chat about poker"}},
    )
    runs = await eq.collect_runs(probe, ["poker"], top_k=5)
    assert len(runs) == 1
    [hit] = runs[0].hits
    assert hit.episode_content == "chat about poker"
    assert probe.search_calls == [("poker", 5)]
    assert probe.episode_lookups == ["e1"]  # only first episode resolved


@pytest.mark.asyncio
async def test_collect_runs_handles_hit_with_no_episodes():
    probe = FakeProbe(
        rows_by_query={"q": [_row(1, fact="orphan", episodes=[])]},
    )
    runs = await eq.collect_runs(probe, ["q"], top_k=5)
    [hit] = runs[0].hits
    assert hit.episode_content is None
    # Don't waste a lookup when there's no episode to fetch
    assert probe.episode_lookups == []


@pytest.mark.asyncio
async def test_collect_runs_handles_empty_search_result():
    probe = FakeProbe(rows_by_query={})
    runs = await eq.collect_runs(probe, ["unmapped"], top_k=5)
    assert runs[0].hits == []
    assert probe.search_calls == [("unmapped", 5)]


@pytest.mark.asyncio
async def test_collect_runs_preserves_query_order():
    probe = FakeProbe(rows_by_query={
        "first": [_row(1)],
        "second": [_row(1)],
    })
    runs = await eq.collect_runs(probe, ["second", "first"], top_k=3)
    assert [r.query for r in runs] == ["second", "first"]


# ── starter QUERIES sanity ───────────────────────────────────────────────────


def test_starter_queries_are_non_empty_and_unique():
    """The shipped query set must be non-trivial and not have duplicates —
    duplicates would make the per-query mean unreliable."""
    assert len(eq.QUERIES) >= 5
    assert all(q.strip() for q in eq.QUERIES)
    assert len(set(eq.QUERIES)) == len(eq.QUERIES)
