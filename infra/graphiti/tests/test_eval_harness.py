"""
tests/test_eval_harness.py — Unit tests for the Stage-6 eval harness.

Tests cover:
  - JSONL schema round-trip (EntityCandidate, EdgeCandidate)
  - Metric computation (precision, recall, noise_rate)
  - Resumability: interrupt mid-label, restart, verify state is preserved
  - run_l3_eval.py exit-code logic (pass / fail thresholds)
  - Scorecard rendering

These tests run fully offline — no Neo4j, no sidecar, no network calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Put repo root on path so `eval` package imports work.
# File is at infra/graphiti/tests/test_eval_harness.py → .parent×4 = repo root.
# conftest.py adds infra/graphiti/ already; we need the repo root for eval/.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.schemas import EdgeCandidate, EntityCandidate, load_edge_jsonl, load_entity_jsonl
from eval.run_l3_eval import (
    compute_edge_metrics,
    compute_entity_metrics,
    render_scorecard,
    CRITERIA,
    _pass_fail,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_entity(
    node_uuid: str = "uuid-1",
    entity_type: str = "Person",
    name: str = "Martin",
    is_valid: bool | None = None,
) -> EntityCandidate:
    return EntityCandidate(
        node_uuid=node_uuid,
        entity_type=entity_type,
        name=name,
        summary="A coffee farmer in Kenya.",
        source_excerpt="Martin runs the Ngacha farm in Nyeri.",
        source_tag="apple_note",
        is_valid=is_valid,
    )


def _make_edge(
    edge_uuid: str = "edge-1",
    edge_type: str = "SUPPORTS",
    is_valid: bool | None = None,
) -> EdgeCandidate:
    return EdgeCandidate(
        edge_uuid=edge_uuid,
        edge_type=edge_type,
        source_name="Martin",
        source_type="Person",
        target_name="Ngacha Farm",
        target_type="Place",
        fact="Martin supports the Ngacha Farm project.",
        confidence=0.9,
        source_excerpt="Martin runs the farm.",
        source_tag="apple_note",
        is_valid=is_valid,
    )


# ── Schema round-trip ─────────────────────────────────────────────────────────


class TestEntityCandidateSchema:
    def test_round_trip_null_label(self):
        rec = _make_entity(is_valid=None)
        dumped = rec.model_dump_json()
        loaded = EntityCandidate.model_validate(json.loads(dumped))
        assert loaded.is_valid is None
        assert loaded.name == "Martin"

    def test_round_trip_true_label(self):
        rec = _make_entity(is_valid=True)
        loaded = EntityCandidate.model_validate(json.loads(rec.model_dump_json()))
        assert loaded.is_valid is True

    def test_round_trip_false_label(self):
        rec = _make_entity(is_valid=False)
        loaded = EntityCandidate.model_validate(json.loads(rec.model_dump_json()))
        assert loaded.is_valid is False

    def test_source_tag_default(self):
        rec = EntityCandidate(
            node_uuid="x",
            entity_type="Concept",
            name="Test",
            summary="A test",
            source_excerpt="",
        )
        assert rec.source_tag == "unknown"


class TestEdgeCandidateSchema:
    def test_round_trip_null_label(self):
        rec = _make_edge(is_valid=None)
        loaded = EdgeCandidate.model_validate(json.loads(rec.model_dump_json()))
        assert loaded.is_valid is None

    def test_confidence_default(self):
        rec = EdgeCandidate(
            edge_uuid="e",
            edge_type="CONTRADICTS",
            source_name="A",
            source_type="Belief",
            target_name="B",
            target_type="Belief",
            fact="A contradicts B.",
        )
        assert rec.confidence == 1.0


# ── JSONL file I/O ────────────────────────────────────────────────────────────


class TestJsonlIO:
    def test_load_entity_jsonl(self, tmp_path):
        path = tmp_path / "entities.jsonl"
        recs = [
            _make_entity("u1", is_valid=True),
            _make_entity("u2", is_valid=None),
            _make_entity("u3", is_valid=False),
        ]
        with path.open("w") as fh:
            for r in recs:
                fh.write(r.model_dump_json() + "\n")

        loaded = load_entity_jsonl(str(path))
        assert len(loaded) == 3
        assert loaded[0].is_valid is True
        assert loaded[1].is_valid is None
        assert loaded[2].is_valid is False

    def test_load_edge_jsonl(self, tmp_path):
        path = tmp_path / "edges.jsonl"
        recs = [_make_edge("e1", is_valid=True), _make_edge("e2", is_valid=None)]
        with path.open("w") as fh:
            for r in recs:
                fh.write(r.model_dump_json() + "\n")

        loaded = load_edge_jsonl(str(path))
        assert len(loaded) == 2
        assert loaded[0].is_valid is True


# ── Metric computation ────────────────────────────────────────────────────────


class TestEntityMetrics:
    def test_all_valid(self):
        records = [_make_entity(f"u{i}", is_valid=True) for i in range(10)]
        m = compute_entity_metrics(records)
        assert m["entity_precision"] == 1.0
        assert m["entity_recall"] == 1.0
        assert m["noise_rate"] == 0.0

    def test_all_invalid(self):
        records = [_make_entity(f"u{i}", is_valid=False) for i in range(10)]
        m = compute_entity_metrics(records)
        assert m["entity_precision"] == 0.0
        assert m["noise_rate"] == 1.0

    def test_mixed(self):
        # 8 valid, 2 invalid out of 10 labeled; 0 unlabeled
        records = (
            [_make_entity(f"u{i}", is_valid=True) for i in range(8)]
            + [_make_entity(f"u{i+8}", is_valid=False) for i in range(2)]
        )
        m = compute_entity_metrics(records)
        assert m["entity_precision"] == pytest.approx(0.8, abs=0.01)
        assert m["noise_rate"] == pytest.approx(0.2, abs=0.01)

    def test_with_unlabeled(self):
        # 8 valid labeled, 2 unlabeled — recall should be 8/10
        records = [_make_entity(f"u{i}", is_valid=True) for i in range(8)]
        records += [_make_entity(f"u{i+8}", is_valid=None) for i in range(2)]
        m = compute_entity_metrics(records)
        assert m["entity_precision"] == 1.0  # all labeled are valid
        assert m["entity_recall"] == pytest.approx(0.8, abs=0.01)  # 8/10

    def test_no_labeled(self):
        records = [_make_entity(f"u{i}", is_valid=None) for i in range(5)]
        m = compute_entity_metrics(records)
        assert m["entity_precision"] == 0.0
        assert m["entity_recall"] == 0.0
        assert m["n_labeled"] == 0


class TestEdgeMetrics:
    def test_all_valid(self):
        records = [_make_edge(f"e{i}", is_valid=True) for i in range(10)]
        m = compute_edge_metrics(records)
        assert m["edge_precision"] == 1.0
        assert m["edge_recall"] == 1.0

    def test_partial(self):
        records = (
            [_make_edge(f"e{i}", is_valid=True) for i in range(7)]
            + [_make_edge(f"e{i+7}", is_valid=False) for i in range(3)]
        )
        m = compute_edge_metrics(records)
        assert m["edge_precision"] == pytest.approx(0.7, abs=0.01)


# ── Pass/fail logic ───────────────────────────────────────────────────────────


class TestPassFail:
    def test_threshold_pass(self):
        assert _pass_fail(0.90, {"threshold": 0.85}) == "PASS"

    def test_threshold_fail(self):
        assert _pass_fail(0.80, {"threshold": 0.85}) == "FAIL"

    def test_threshold_exact(self):
        assert _pass_fail(0.85, {"threshold": 0.85}) == "PASS"

    def test_max_pass(self):
        assert _pass_fail(0.08, {"max": 0.10}) == "PASS"

    def test_max_fail(self):
        assert _pass_fail(0.12, {"max": 0.10}) == "FAIL"

    def test_max_exact(self):
        assert _pass_fail(0.10, {"max": 0.10}) == "PASS"


# ── Scorecard rendering ───────────────────────────────────────────────────────


class TestScorecardRendering:
    def _make_passing_metrics(self) -> dict:
        return {
            "entity_precision": 0.90,
            "entity_recall": 0.80,
            "noise_rate": 0.05,
            "edge_precision": 0.85,
            "edge_recall": 0.70,
            "n_labeled": 180,
            "n_valid": 162,
            "n_invalid": 18,
            "n_total_candidates": 200,
            "edge_n_labeled": 160,
            "edge_n_valid": 136,
            "edge_n_invalid": 24,
            "edge_n_total_candidates": 200,
        }

    def test_passing_scorecard_contains_pass(self):
        metrics = self._make_passing_metrics()
        scorecard = render_scorecard(metrics, latency_skipped=True, timestamp="2026-05-21")
        assert "PASS" in scorecard
        assert "FAIL" not in scorecard

    def test_failing_scorecard_contains_fail(self):
        metrics = self._make_passing_metrics()
        metrics["entity_precision"] = 0.70  # below 0.85 threshold
        scorecard = render_scorecard(metrics, latency_skipped=True, timestamp="2026-05-21")
        assert "FAIL" in scorecard

    def test_scorecard_has_header(self):
        metrics = self._make_passing_metrics()
        scorecard = render_scorecard(metrics, latency_skipped=True, timestamp="2026-05-21")
        assert "Stage-6 L3 eval scorecard" in scorecard

    def test_latency_skipped_shows_dash(self):
        metrics = self._make_passing_metrics()
        scorecard = render_scorecard(metrics, latency_skipped=True, timestamp="2026-05-21")
        assert "skipped" in scorecard

    def test_latency_present_shows_value(self):
        metrics = self._make_passing_metrics()
        metrics["ingestion_latency_p95_ms"] = 3200.0
        metrics["query_latency_p95_ms"] = 280.0
        scorecard = render_scorecard(metrics, latency_skipped=False, timestamp="2026-05-21")
        assert "3200" in scorecard
        assert "280" in scorecard


# ── Resumability ──────────────────────────────────────────────────────────────


class TestResumability:
    """
    Simulate an interrupted labeling session.

    The labeling tool writes after each decision via _rewrite_jsonl.
    We test that:
      1. A partial label run preserves already-labeled records.
      2. Reloading the file after simulated interrupt picks up where it left off.
      3. Unlabeled records (is_valid == None) are unchanged after interrupt.
    """

    def test_partial_label_preserved_on_reload(self, tmp_path):
        """Write 10 candidates; simulate labeling 5; verify 5 are labeled on reload."""
        from eval.label import _rewrite_jsonl

        path = tmp_path / "entities.jsonl"
        records = [_make_entity(f"u{i}", is_valid=None) for i in range(10)]
        with path.open("w") as fh:
            for r in records:
                fh.write(r.model_dump_json() + "\n")

        # Simulate labeling first 5 records
        for i in range(5):
            records[i].is_valid = True if i % 2 == 0 else False
        _rewrite_jsonl(path, records)

        # "Interrupt" — reload from disk
        reloaded = load_entity_jsonl(str(path))
        assert len(reloaded) == 10
        assert sum(1 for r in reloaded if r.is_valid is not None) == 5
        assert sum(1 for r in reloaded if r.is_valid is None) == 5

    def test_resume_skips_already_labeled(self, tmp_path):
        """After partial label, unlabeled count matches expected."""
        from eval.label import _rewrite_jsonl

        path = tmp_path / "edges.jsonl"
        records = [_make_edge(f"e{i}", is_valid=None) for i in range(20)]
        with path.open("w") as fh:
            for r in records:
                fh.write(r.model_dump_json() + "\n")

        # Label 12
        for i in range(12):
            records[i].is_valid = True
        _rewrite_jsonl(path, records)

        reloaded = load_edge_jsonl(str(path))
        unlabeled = [r for r in reloaded if r.is_valid is None]
        assert len(unlabeled) == 8

    def test_write_is_atomic(self, tmp_path):
        """_rewrite_jsonl uses a temp file so the original is never left half-written."""
        from eval.label import _rewrite_jsonl

        path = tmp_path / "entities.jsonl"
        records = [_make_entity(f"u{i}", is_valid=True) for i in range(5)]
        with path.open("w") as fh:
            for r in records:
                fh.write(r.model_dump_json() + "\n")

        # Rewrite — should succeed; tmp file should not remain
        _rewrite_jsonl(path, records)
        tmp = path.with_suffix(".jsonl.tmp")
        assert not tmp.exists()
        assert path.exists()
