"""
Tests for scripts/eval_nodes.py — the Stage 4 extraction-quality rater.

The interactive rating UI is not tested (requires a human). Tests cover the
data-fetching / formatting / persistence path: pure helpers (`pick_nodes`,
`to_sample`, `format_node_card`, `render_results_md`, `append_results_md`)
and the orchestrator `collect_samples` against an in-memory GraphProbe.

Same Humble Object discipline as test_sync.py / test_mcp_ingest.py (D-047):
production code accepts collaborators as injectable; tests pass fakes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

# Make the scripts/ directory importable from the test runner. infra/graphiti
# is already on sys.path via conftest.py; we just add the repo-level scripts/.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import eval_nodes


# ── Fakes ────────────────────────────────────────────────────────────────────


@dataclass
class FakeProbe:
    """In-memory GraphProbe. Records every call so tests can assert ordering."""
    entity_count: int = 0
    entity_rows: list[dict] | None = None
    episode_by_uuid: dict[str, dict] | None = None

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.entity_rows = self.entity_rows or []
        self.episode_by_uuid = self.episode_by_uuid or {}

    async def total_entity_count(self) -> int:
        self.calls.append(("count", ()))
        return self.entity_count

    async def fetch_random_entities(self, n: int) -> list[dict]:
        self.calls.append(("entities", (n,)))
        return list(self.entity_rows[:n])

    async def fetch_source_episode(self, entity_uuid: str) -> dict | None:
        self.calls.append(("episode", (entity_uuid,)))
        return self.episode_by_uuid.get(entity_uuid)


def make_entity_row(uuid: str, name: str, **extra) -> dict:
    base = {
        "uuid": uuid,
        "name": name,
        "labels": ["Entity"],
        "summary": f"summary of {name}",
        "props": {"uuid": uuid, "name": name, "summary": f"summary of {name}"},
    }
    base.update(extra)
    return base


def make_episode_row(uuid: str, name: str, content: str,
                     source: str = "apple-notes") -> dict:
    return {
        "uuid": uuid,
        "name": name,
        "content": content,
        "source_description": source,
        "valid_at": "2026-01-01T00:00:00",
    }


# ── pick_nodes ───────────────────────────────────────────────────────────────


class TestPickNodes:
    def test_returns_all_when_under_limit(self):
        rows = [make_entity_row(f"u{i}", f"n{i}") for i in range(3)]
        assert eval_nodes.pick_nodes(rows, 5) == rows

    def test_returns_exact_n_when_over(self):
        import random
        rows = [make_entity_row(f"u{i}", f"n{i}") for i in range(10)]
        sampled = eval_nodes.pick_nodes(rows, 4, rng=random.Random(42))
        assert len(sampled) == 4
        # No duplicates
        assert len({r["uuid"] for r in sampled}) == 4

    def test_handles_empty(self):
        assert eval_nodes.pick_nodes([], 5) == []


# ── to_sample ────────────────────────────────────────────────────────────────


class TestToSample:
    def test_combines_node_and_episode(self):
        node = make_entity_row("u1", "Coffee Origin",
                               props={"uuid": "u1", "name": "Coffee Origin",
                                      "summary": "...", "category": "topic",
                                      "name_embedding": [0.1, 0.2]})
        ep = make_episode_row("e1", "apple-notes::Notes", "Some Coffee Origin notes.")
        s = eval_nodes.to_sample(node, ep)
        assert s.uuid == "u1"
        assert s.name == "Coffee Origin"
        assert s.episode_uuid == "e1"
        assert s.episode_content == "Some Coffee Origin notes."
        assert s.episode_source_description == "apple-notes"
        # Structural keys stripped from the user-visible attribute view.
        assert "uuid" not in s.attributes
        assert "name_embedding" not in s.attributes
        assert s.attributes.get("category") == "topic"

    def test_handles_missing_episode(self):
        node = make_entity_row("u1", "Orphan")
        s = eval_nodes.to_sample(node, None)
        assert s.episode_uuid is None
        assert s.episode_content is None
        assert s.episode_source_description is None

    def test_handles_missing_props(self):
        node = {"uuid": "u1", "name": "x", "labels": ["Entity"], "summary": ""}
        # No `props` key at all — to_sample should not crash.
        s = eval_nodes.to_sample(node, None)
        assert s.attributes == {}


# ── format_node_card ─────────────────────────────────────────────────────────


class TestFormatNodeCard:
    def test_includes_name_uuid_labels(self):
        node = make_entity_row("u1", "Brian", labels=["Entity", "Person"])
        ep = make_episode_row("e1", "ep", "Hi Brian.")
        out = eval_nodes.format_node_card(eval_nodes.to_sample(node, ep))
        assert "Brian" in out
        assert "u1" in out
        assert "Entity, Person" in out
        assert "Hi Brian." in out

    def test_truncates_long_episode_body(self):
        body = "x" * 5000
        node = make_entity_row("u1", "n1")
        ep = make_episode_row("e1", "ep", body)
        out = eval_nodes.format_node_card(
            eval_nodes.to_sample(node, ep), max_episode_chars=100,
        )
        assert "+4900 chars" in out
        # Body should not appear in full
        assert body not in out

    def test_no_episode_message(self):
        node = make_entity_row("u1", "n1")
        out = eval_nodes.format_node_card(eval_nodes.to_sample(node, None))
        assert "(none — orphan or community-only)" in out


# ── render_results_md / append_results_md ───────────────────────────────────


class TestRenderResults:
    def test_renders_table_with_means(self):
        node = make_entity_row("u1", "Coffee")
        ep = make_episode_row("e1", "ep", "...")
        sample = eval_nodes.to_sample(node, ep)
        ratings = [
            eval_nodes.NodeRating(sample=sample, accuracy=4, non_obviousness=3,
                                  note="solid"),
            eval_nodes.NodeRating(sample=sample, accuracy=2, non_obviousness=5,
                                  note=""),
        ]
        out = eval_nodes.render_results_md(
            ratings, when=date(2026, 4, 23), backend="graphiti",
        )
        assert "## Run — 2026-04-23 (graphiti, n=2)" in out
        assert "| Coffee |" in out
        # Means: accuracy=(4+2)/2=3.00, non-obv=(3+5)/2=4.00
        assert "accuracy=3.00" in out
        assert "non-obviousness=4.00" in out

    def test_escapes_pipe_in_node_name(self):
        node = make_entity_row("u1", "weird | name")
        ep = make_episode_row("e1", "ep", "x")
        sample = eval_nodes.to_sample(node, ep)
        rating = eval_nodes.NodeRating(sample=sample, accuracy=3,
                                       non_obviousness=3, note="a | b")
        out = eval_nodes.render_results_md(
            [rating], when=date(2026, 4, 23), backend="graphiti",
        )
        # Both pipe occurrences must be escaped
        assert "weird \\| name" in out
        assert "a \\| b" in out


class TestAppendResultsMd:
    def test_creates_file_with_header_then_appends(self, tmp_path: Path):
        path = tmp_path / "nodes-2026-04-23.md"
        node = make_entity_row("u1", "n1")
        sample = eval_nodes.to_sample(node, None)
        rating = eval_nodes.NodeRating(sample=sample, accuracy=4,
                                       non_obviousness=4, note="")

        body1 = eval_nodes.render_results_md(
            [rating], when=date(2026, 4, 23), backend="graphiti",
        )
        eval_nodes.append_results_md(
            path, body1, when=date(2026, 4, 23), backend="graphiti",
        )
        first = path.read_text(encoding="utf-8")
        assert first.startswith("# Node-extraction eval — 2026-04-23")
        assert "## Run — 2026-04-23" in first

        # Second invocation on the same day appends, doesn't overwrite.
        body2 = eval_nodes.render_results_md(
            [rating], when=date(2026, 4, 23), backend="graphiti",
        )
        eval_nodes.append_results_md(
            path, body2, when=date(2026, 4, 23), backend="graphiti",
        )
        second = path.read_text(encoding="utf-8")
        # Header should appear exactly once (only created on first write)
        assert second.count("# Node-extraction eval — 2026-04-23") == 1
        # Two run sections now
        assert second.count("## Run — 2026-04-23") == 2


# ── collect_samples ──────────────────────────────────────────────────────────


class TestCollectSamples:
    async def test_combines_entities_with_episodes(self):
        rows = [make_entity_row("u1", "n1"), make_entity_row("u2", "n2")]
        eps = {
            "u1": make_episode_row("e1", "ep1", "body 1"),
            "u2": make_episode_row("e2", "ep2", "body 2"),
        }
        probe = FakeProbe(entity_count=10, entity_rows=rows,
                          episode_by_uuid=eps)
        samples = await eval_nodes.collect_samples(probe, 2)
        assert [s.name for s in samples] == ["n1", "n2"]
        assert [s.episode_content for s in samples] == ["body 1", "body 2"]

    async def test_zero_entities_short_circuits(self):
        probe = FakeProbe(entity_count=0)
        samples = await eval_nodes.collect_samples(probe, 5)
        assert samples == []
        # Only the count was queried — no entity / episode fetch.
        assert probe.calls == [("count", ())]

    async def test_caps_n_at_graph_size(self):
        rows = [make_entity_row("u1", "n1")]
        probe = FakeProbe(entity_count=1, entity_rows=rows)
        samples = await eval_nodes.collect_samples(probe, 5)
        # Only one entity exists; n was clamped.
        assert len(samples) == 1
        assert ("entities", (1,)) in probe.calls

    async def test_node_with_no_episode_yields_sample_with_none(self):
        rows = [make_entity_row("u1", "orphan")]
        probe = FakeProbe(entity_count=1, entity_rows=rows, episode_by_uuid={})
        samples = await eval_nodes.collect_samples(probe, 1)
        assert samples[0].episode_content is None


# ── Backend dispatch ─────────────────────────────────────────────────────────


class TestOpenProbe:
    async def test_local_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            await eval_nodes.open_probe("local")

    async def test_unknown_raises_value_error(self):
        with pytest.raises(ValueError):
            await eval_nodes.open_probe("pinecone")
