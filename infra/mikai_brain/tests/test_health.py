"""Tests for infra.mikai_brain.health — the cron-fleet heartbeat.

All I/O mocked: rows are passed in (no progress.jsonl read), launchctl
is replaced by an explicit loaded-label set, ntfy + ledger writes are
patched. `check()` is pure; `run_check()` is exercised end-to-end with
mocks.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from infra.mikai_brain import health

NOW = datetime(2026, 8, 6, 15, 0, tzinfo=timezone.utc)

ALL_LABELS = {c.plist_label for c in health.EXPECTED}


def row(mode: str, hours_ago: float) -> dict:
    ts = (NOW - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    return {"ts": ts, "mode": mode, "did": "x"}


def fresh_rows() -> list[dict]:
    """One recent row per expected mode — everything green."""
    return [row(c.mode, 1.0) for c in health.EXPECTED]


class TestCheck(unittest.TestCase):
    def test_all_fresh_is_green(self):
        stale, green, skipped = health.check(fresh_rows(), ALL_LABELS, now=NOW)
        self.assertEqual(stale, [])
        self.assertEqual(len(green), len(health.EXPECTED))
        self.assertEqual(skipped, [])

    def test_stale_job_triggers(self):
        rows = [r for r in fresh_rows() if r["mode"] != "ingestion"]
        rows.append(row("ingestion", 20.0))  # max 12h — over the window
        stale, green, _ = health.check(rows, ALL_LABELS, now=NOW)
        self.assertEqual([f.mode for f in stale], ["ingestion"])
        self.assertIn("20.0h ago; max 12h", stale[0].line())

    def test_fresh_within_window_not_stale(self):
        rows = [r for r in fresh_rows() if r["mode"] != "claude-threads"]
        rows.append(row("claude-threads", 29.0))  # max 30h — still inside
        stale, _, _ = health.check(rows, ALL_LABELS, now=NOW)
        self.assertEqual(stale, [])

    def test_never_seen_counts_as_stale(self):
        rows = [r for r in fresh_rows() if r["mode"] != "dream-weekly"]
        stale, _, _ = health.check(rows, ALL_LABELS, now=NOW)
        self.assertEqual([f.mode for f in stale], ["dream-weekly"])
        self.assertIsNone(stale[0].last_ts)
        self.assertIn("never seen", stale[0].line())

    def test_unloaded_plist_skipped(self):
        rows = [r for r in fresh_rows() if r["mode"] != "dream-nightly"]
        loaded = ALL_LABELS - {"com.mikai.dream-nightly"}
        stale, _, skipped = health.check(rows, loaded, now=NOW)
        self.assertEqual(stale, [])  # missing rows for an unloaded job: fine
        self.assertEqual(skipped, ["dream-nightly"])

    def test_newest_row_wins_over_old_rows(self):
        rows = fresh_rows() + [row("consolidate", 900.0)]  # old row, fresh exists
        stale, _, _ = health.check(rows, ALL_LABELS, now=NOW)
        self.assertEqual(stale, [])


class TestRunCheck(unittest.TestCase):
    def test_stale_dispatches_and_self_logs(self):
        rows = [r for r in fresh_rows() if r["mode"] != "ingestion"]
        with mock.patch.object(health, "dispatch_ntfy",
                               return_value=(True, "http_200")) as ntfy, \
             mock.patch.object(health.ledger, "run") as led:
            rc = health.run_check(rows=rows, loaded=ALL_LABELS, now=NOW)
        self.assertEqual(rc, 0)
        ntfy.assert_called_once()
        title, body = ntfy.call_args[0]
        self.assertEqual(title, "MIKAI health: 1 job(s) silent")
        self.assertIn("ingestion", body)
        led.assert_called_once()
        self.assertEqual(led.call_args.kwargs["mode"], "health-check")
        self.assertIn("ingestion", led.call_args.kwargs["did"])

    def test_all_green_no_ntfy_but_self_logs(self):
        with mock.patch.object(health, "dispatch_ntfy") as ntfy, \
             mock.patch.object(health.ledger, "run") as led:
            rc = health.run_check(rows=fresh_rows(), loaded=ALL_LABELS, now=NOW)
        self.assertEqual(rc, 0)
        ntfy.assert_not_called()
        led.assert_called_once_with(mode="health-check", did=mock.ANY)
        self.assertIn("all green", led.call_args.kwargs["did"])

    def test_dry_run_never_dispatches_or_writes(self):
        rows = []  # everything stale — worst case
        with mock.patch.object(health, "dispatch_ntfy") as ntfy, \
             mock.patch.object(health.ledger, "run") as led:
            rc = health.run_check(rows=rows, loaded=ALL_LABELS, now=NOW,
                                  dry_run=True)
        self.assertEqual(rc, 0)
        ntfy.assert_not_called()
        led.assert_not_called()


if __name__ == "__main__":
    unittest.main()
