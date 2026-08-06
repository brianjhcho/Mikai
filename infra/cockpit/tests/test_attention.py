"""Tests for the cockpit attention head + salience budget + delta strip.

These are pure-function tests: they build synthetic department + thread
dicts (matching the shape `infra.cockpit.thread_dict()` returns) and
call the ranking / snapshot helpers directly. No filesystem, no LLM.
"""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from infra.cockpit import compute_attention, score_attention_owed
from infra.cockpit.snapshot import (compute_deltas, snapshot_from_departments)


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _iso_future(days_ahead: int) -> str:
    return (date.today() + timedelta(days=days_ahead)).isoformat()


def _thread(slug: str, state: str, *, days_since_state: int = 1,
            last_activity_days_ago: int = 1, next_step: str = "",
            next_step_due: str = "", overdue: bool = False,
            overdue_days: int = 0, title: str | None = None) -> dict:
    return {
        "slug": slug,
        "title": title or slug.replace("-", " ").title(),
        "state": state,
        "department": "ai_work",
        "state_since": _iso(days_since_state),
        "last_activity": _iso(last_activity_days_ago),
        "days_since": last_activity_days_ago,
        "days_since_state": days_since_state,
        "next_step": next_step,
        "next_step_due": next_step_due,
        "overdue": overdue,
        "overdue_days": overdue_days,
        "log_recent": [], "log_full": [], "last_log": "",
        "reason": "", "entities": [],
    }


def _dept(threads: list[dict]) -> list[dict]:
    return [{"id": "ai_work", "name": "AI Work", "tier": "primary",
             "sub": "", "threads": threads, "counts": {},
             "breakdown": "", "recent_decision": None,
             "top_next_step": None}]


class ScoreTests(unittest.TestCase):
    def test_overdue_beats_stalled(self):
        overdue = _thread("od", "acting", overdue=True, overdue_days=4)
        stalled = _thread("st", "stalled", days_since_state=5)
        so, _ = score_attention_owed(overdue)
        ss, _ = score_attention_owed(stalled)
        self.assertGreater(so, ss)
        self.assertEqual(so, 40.0)
        self.assertEqual(ss, 25.0)

    def test_acting_due_soon_scores_positive(self):
        t = _thread("act", "acting", next_step_due=_iso_future(2))
        s, r = score_attention_owed(t)
        self.assertEqual(s, 15.0)  # (7 - 2) * 3
        self.assertIn("acting", r)

    def test_acting_due_far_out_scores_zero(self):
        t = _thread("act", "acting", next_step_due=_iso_future(30))
        s, _ = score_attention_owed(t)
        self.assertEqual(s, 0.0)

    def test_decided_no_follow_through(self):
        t = _thread("dec", "decided", days_since_state=8)
        s, r = score_attention_owed(t)
        self.assertEqual(s, 32.0)  # 8 * 4
        self.assertIn("decided", r)

    def test_exploring_quiet_scores_zero(self):
        t = _thread("q", "exploring", days_since_state=40)
        s, _ = score_attention_owed(t)
        self.assertEqual(s, 0.0)


class HeadTests(unittest.TestCase):
    def test_head_picks_top_scorer(self):
        depts = _dept([
            _thread("stall", "stalled", days_since_state=10),
            _thread("od", "acting", overdue=True, overdue_days=6),
            _thread("calm", "exploring"),
        ])
        att = compute_attention(depts)
        self.assertEqual(att["attention_head"]["slug"], "od")
        self.assertFalse(att["attention_head"]["quiet"])
        self.assertEqual(att["attention_head"]["reason"], "overdue by 6d")

    def test_quiet_head_when_nothing_owed(self):
        depts = _dept([
            _thread("a", "exploring"),
            _thread("b", "evaluating"),
        ])
        att = compute_attention(depts)
        self.assertTrue(att["attention_head"]["quiet"])
        self.assertIsNone(att["attention_head"]["slug"])
        self.assertEqual(att["loud_slugs"], [])

    def test_tiebreak_prefers_larger_stall(self):
        # Both stalled 4d → identical score 20; larger stall wins first
        depts = _dept([
            _thread("small", "stalled", days_since_state=4),
            _thread("large", "stalled", days_since_state=10),
        ])
        att = compute_attention(depts)
        # large has bigger score (50 vs 20), verify it's first
        self.assertEqual(att["attention_head"]["slug"], "large")

    def test_completed_ignored(self):
        depts = _dept([
            _thread("done", "completed", days_since_state=1),
            _thread("live", "stalled", days_since_state=3),
        ])
        att = compute_attention(depts)
        self.assertEqual(att["attention_head"]["slug"], "live")
        self.assertNotIn("done", att["loud_slugs"])


class SalienceTests(unittest.TestCase):
    def test_loud_caps_at_four(self):
        # 6 stalled threads with varying stall days
        threads = [_thread(f"t{i}", "stalled", days_since_state=i + 1)
                   for i in range(6)]
        depts = _dept(threads)
        att = compute_attention(depts)
        self.assertEqual(len(att["loud_slugs"]), 4)
        # Highest-scoring (longest stalls) should dominate
        self.assertIn("t5", att["loud_slugs"])
        self.assertIn("t4", att["loud_slugs"])
        # The two shortest-stall threads should not be loud
        self.assertNotIn("t0", att["loud_slugs"])
        self.assertNotIn("t1", att["loud_slugs"])

    def test_head_always_included_in_loud(self):
        threads = [_thread(f"t{i}", "stalled", days_since_state=i + 1)
                   for i in range(4)]
        depts = _dept(threads)
        att = compute_attention(depts)
        self.assertIn(att["attention_head"]["slug"], att["loud_slugs"])

    def test_loud_empty_when_nothing_owed(self):
        depts = _dept([_thread("a", "exploring"),
                       _thread("b", "evaluating")])
        att = compute_attention(depts)
        self.assertEqual(att["loud_slugs"], [])


class DeltaTests(unittest.TestCase):
    def _snap(self, threads):
        return snapshot_from_departments(_dept(threads))

    def test_no_prior_snapshot_no_deltas(self):
        current = self._snap([_thread("a", "acting")])
        self.assertEqual(compute_deltas(None, current), [])

    def test_state_transition_detected(self):
        prior = self._snap([_thread("a", "exploring")])
        current = self._snap([_thread("a", "stalled")])
        d = compute_deltas(prior, current)
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["kind"], "transition")
        self.assertEqual(d[0]["from"], "exploring")
        self.assertEqual(d[0]["to"], "stalled")

    def test_diff_cap_three_items(self):
        prior_threads = [_thread(f"t{i}", "exploring") for i in range(6)]
        current_threads = [_thread(f"t{i}", "stalled") for i in range(6)]
        d = compute_deltas(self._snap(prior_threads),
                           self._snap(current_threads), cap=3)
        self.assertEqual(len(d), 3)

    def test_empty_when_no_change(self):
        threads = [_thread("a", "acting"), _thread("b", "stalled")]
        d = compute_deltas(self._snap(threads), self._snap(threads))
        self.assertEqual(d, [])

    def test_new_thread_appears_as_delta(self):
        prior = self._snap([_thread("a", "acting")])
        current = self._snap([_thread("a", "acting"),
                              _thread("b", "exploring")])
        d = compute_deltas(prior, current)
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["kind"], "new")
        self.assertEqual(d[0]["slug"], "b")

    def test_became_overdue_registers(self):
        prior = self._snap([_thread("a", "acting", overdue=False)])
        current = self._snap([_thread("a", "acting", overdue=True,
                                      overdue_days=2)])
        d = compute_deltas(prior, current)
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["kind"], "overdue")
        self.assertIn("overdue", d[0]["desc"])


if __name__ == "__main__":
    unittest.main()
