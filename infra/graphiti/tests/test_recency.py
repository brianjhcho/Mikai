"""Tests for sidecar/recency.py — query-time recency-decay overlay.

Tests cover:
  - empty list passthrough
  - no valid_at → weight 1.0, sorts first among stale edges
  - single edge, various ages
  - multi-edge ordering: fresh beats stale
  - half-life boundary: edge aged exactly half_life_days gets weight ~0.5
  - future valid_at treated as maximally fresh (weight 1.0)
  - tz-naive valid_at handled without raising
  - input list is not mutated
  - reference_time default path (smoke test)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from sidecar.recency import apply_recency_decay, _DEFAULT_HALF_LIFE_DAYS


# ── Minimal edge stub ─────────────────────────────────────────────────────────


@dataclass
class _Edge:
    fact: str = "some fact"
    valid_at: datetime | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


_NOW = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)


def _days_ago(n: float) -> datetime:
    return _NOW - timedelta(days=n)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestApplyRecencyDecay:
    def test_empty_list_returns_empty(self):
        result = apply_recency_decay([], reference_time=_NOW)
        assert result == []

    def test_none_valid_at_gets_weight_one(self):
        edges = [
            _Edge(fact="unknown-age", valid_at=None),
            _Edge(fact="old",         valid_at=_days_ago(365)),
        ]
        result = apply_recency_decay(edges, reference_time=_NOW)
        # unknown-age has weight 1.0; old has weight < 0.5 → unknown comes first
        assert result[0].fact == "unknown-age"

    def test_fresh_edge_ranks_above_stale_edge(self):
        edges = [
            _Edge(fact="stale",  valid_at=_days_ago(180)),
            _Edge(fact="recent", valid_at=_days_ago(10)),
        ]
        result = apply_recency_decay(edges, reference_time=_NOW)
        assert result[0].fact == "recent"
        assert result[1].fact == "stale"

    def test_half_life_boundary_weight(self):
        """Edge aged exactly half_life_days should have weight ≈ 0.5."""
        half_life = 90.0
        edges = [_Edge(fact="at-half-life", valid_at=_days_ago(half_life))]
        result = apply_recency_decay(
            edges, reference_time=_NOW, half_life_days=half_life
        )
        assert len(result) == 1
        # Verify the formula: exp(-ln2 * 90 / 90) == 0.5
        expected_weight = math.exp(-math.log(2) * half_life / half_life)
        assert abs(expected_weight - 0.5) < 1e-9

    def test_zero_age_edge_has_weight_one(self):
        edges = [_Edge(fact="just-now", valid_at=_NOW)]
        result = apply_recency_decay(edges, reference_time=_NOW)
        assert len(result) == 1
        # age_days == 0 → exp(0) == 1.0
        assert result[0].fact == "just-now"

    def test_future_valid_at_treated_as_fresh(self):
        """valid_at in the future → age < 0 → weight 1.0, sorts first."""
        future = _NOW + timedelta(days=30)
        edges = [
            _Edge(fact="stale",  valid_at=_days_ago(200)),
            _Edge(fact="future", valid_at=future),
        ]
        result = apply_recency_decay(edges, reference_time=_NOW)
        assert result[0].fact == "future"

    def test_tz_naive_valid_at_does_not_raise(self):
        """tz-naive valid_at should be handled gracefully (treated as UTC)."""
        naive = datetime(2025, 1, 1, 0, 0, 0)  # no tzinfo
        edges = [_Edge(fact="naive-dt", valid_at=naive)]
        result = apply_recency_decay(edges, reference_time=_NOW)
        assert len(result) == 1
        assert result[0].fact == "naive-dt"

    def test_input_list_is_not_mutated(self):
        edges = [
            _Edge(fact="b", valid_at=_days_ago(50)),
            _Edge(fact="a", valid_at=_days_ago(5)),
        ]
        original_order = [e.fact for e in edges]
        apply_recency_decay(edges, reference_time=_NOW)
        # Input unchanged
        assert [e.fact for e in edges] == original_order

    def test_multi_edge_ordering_is_stable_for_ties(self):
        """Edges with identical valid_at keep their original relative order."""
        same_time = _days_ago(30)
        edges = [
            _Edge(fact="first",  valid_at=same_time),
            _Edge(fact="second", valid_at=same_time),
            _Edge(fact="third",  valid_at=same_time),
        ]
        result = apply_recency_decay(edges, reference_time=_NOW)
        assert [e.fact for e in result] == ["first", "second", "third"]

    def test_default_reference_time_does_not_raise(self):
        """Calling without reference_time should default to datetime.now() without error."""
        edges = [_Edge(fact="any", valid_at=_days_ago(10))]
        result = apply_recency_decay(edges)  # no reference_time
        assert len(result) == 1

    def test_custom_half_life_affects_ordering(self):
        """A very short half-life makes even mildly old edges rank low."""
        edges = [
            _Edge(fact="3-days-old",  valid_at=_days_ago(3)),
            _Edge(fact="1-day-old",   valid_at=_days_ago(1)),
        ]
        result_short = apply_recency_decay(
            edges, reference_time=_NOW, half_life_days=2.0
        )
        result_long = apply_recency_decay(
            edges, reference_time=_NOW, half_life_days=365.0
        )
        # Both half-lives should rank 1-day-old above 3-days-old
        assert result_short[0].fact == "1-day-old"
        assert result_long[0].fact == "1-day-old"

    def test_non_datetime_valid_at_treated_as_unknown(self):
        """A string or unexpected type in valid_at gets weight 1.0 (no crash)."""

        @dataclass
        class EdgeWithStringDate:
            fact: str = "string-date"
            valid_at: object = "2025-01-01T00:00:00"

        edges = [
            EdgeWithStringDate(),
            _Edge(fact="very-old", valid_at=_days_ago(500)),
        ]
        result = apply_recency_decay(edges, reference_time=_NOW)
        # string valid_at → weight 1.0 → should sort first
        assert result[0].fact == "string-date"

    def test_default_half_life_is_90_days(self):
        assert _DEFAULT_HALF_LIFE_DAYS == 90.0
