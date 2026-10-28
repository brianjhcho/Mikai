"""Tests for eval/dismiss_rate.py against temp SQLite fixtures (never the real DB).

Run: python3 -m unittest eval/test_dismiss_rate.py
"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import dismiss_rate  # noqa: E402

LOG_SCHEMA = """
CREATE TABLE notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tick_ts TEXT NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0,
    title TEXT,
    user_response TEXT,
    response_at TEXT,
    not_sent_reason TEXT,
    notif_id TEXT
);
"""
EVENTS_SCHEMA = """
CREATE TABLE notification_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notif_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_ts TEXT NOT NULL
);
"""


class DismissRateTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(LOG_SCHEMA + EVENTS_SCHEMA)

    def tearDown(self):
        self.conn.close()
        os.remove(self.path)

    def log(self, tick, sent, notif_id=None, reason=None, response=None, title="t"):
        self.conn.execute(
            "INSERT INTO notification_log (tick_ts, sent, title, notif_id, not_sent_reason, user_response)"
            " VALUES (?,?,?,?,?,?)", (tick, sent, title, notif_id, reason, response))

    def event(self, notif_id, etype, ts):
        self.conn.execute("INSERT INTO notification_events (notif_id, event_type, event_ts) VALUES (?,?,?)",
                          (notif_id, etype, ts))

    def run_compute(self, **kw):
        self.conn.commit()
        return dismiss_rate.compute(self.path, **kw)

    def test_counts_and_rate(self):
        self.log("2026-08-01T00:00:00", 1, "a")
        self.log("2026-08-01T00:00:00", 1, "b")
        self.log("2026-08-01T00:00:00", 1, "c")
        self.log("2026-08-01T00:00:00", 1, "d")
        self.log("2026-08-01T01:00:00", 0, reason="llm_chose_silent")
        self.log("2026-08-01T02:00:00", 0, reason="claude_invocation_failed")
        for n in "abcd":
            self.event(n, "SENT", "2026-08-01T00:00:01")
        self.event("a", "TAPPED", "2026-08-01T03:00:00")
        self.event("b", "DISMISSED_INFERRED", "2026-08-02T03:00:00")
        self.event("c", "SNOOZED", "2026-08-01T04:00:00")
        r = self.run_compute()
        self.assertEqual(r["decisions"], 6)
        self.assertEqual(r["sent"], 4)
        self.assertEqual(r["silent_breakdown"], {"silent_by_choice": 1, "failed": 1})
        self.assertEqual(r["outcomes"], {"positive": 1, "negative": 1, "neutral": 1, "no_signal": 1})
        self.assertAlmostEqual(r["dismiss_rate"], 0.5)
        self.assertEqual(r["rated_items"], 2)

    def test_explicit_label_beats_inferred(self):
        self.log("2026-08-01", 1, "a")
        self.event("a", "DISMISSED_INFERRED", "2026-08-02")
        self.event("a", "ACTED", "2026-08-01T12:00")
        r = self.run_compute()
        self.assertEqual(r["outcomes"]["positive"], 1)
        self.assertEqual(r["dismiss_rate"], 0.0)
        self.assertEqual(r["explicit"]["labels"], {"ACTED": 1})
        self.assertEqual(r["inferred"]["labels"], {})

    def test_replies_in_feedback_table_count_as_explicit(self):
        self.conn.execute(
            "CREATE TABLE notification_feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, notif_id TEXT,"
            " thread_slug TEXT, label TEXT NOT NULL, note TEXT, source TEXT NOT NULL, event_ts TEXT NOT NULL)")
        self.log("2026-10-24", 1, "a")
        self.log("2026-10-24", 1, "b")
        self.event("a", "DISMISSED_INFERRED", "2026-10-25")
        for nid, label in (("a", "ACTED"), ("b", "NOT_RELEVANT"), (None, "SNOOZED")):
            self.conn.execute(
                "INSERT INTO notification_feedback (notif_id, thread_slug, label, source, event_ts)"
                " VALUES (?, ?, ?, 'hermes-imessage', '2026-10-24T12:00')", (nid, "x" if nid is None else None, label))
        r = self.run_compute()
        self.assertEqual(r["outcomes"]["positive"], 1)
        self.assertEqual(r["outcomes"]["negative"], 1)
        self.assertEqual(r["explicit"]["labels"], {"ACTED": 1, "NOT_RELEVANT": 1})

    def test_tap_beats_inferred_dismissal(self):
        self.log("2026-08-01", 1, "a")
        self.event("a", "TAPPED", "2026-08-01T05:00")
        self.event("a", "DISMISSED_INFERRED", "2026-08-02")
        r = self.run_compute()
        self.assertEqual(r["outcomes"]["positive"], 1)

    def test_not_relevant_counts_negative_and_explicit_split(self):
        self.log("2026-08-01", 1, "a")
        self.log("2026-08-01", 1, "b")
        self.event("a", "NOT_RELEVANT", "2026-08-01T05:00")
        self.event("b", "DISMISSED_INFERRED", "2026-08-02")
        r = self.run_compute()
        self.assertEqual(r["dismiss_rate"], 1.0)
        self.assertEqual(r["explicit"]["dismiss_rate"], 1.0)
        self.assertEqual(r["explicit"]["rated"], 1)

    def test_sent_without_notif_id_is_no_signal(self):
        self.log("2026-07-01", 1)  # pre-instrumentation send
        r = self.run_compute()
        self.assertEqual(r["sent"], 1)
        self.assertEqual(r["outcomes"]["no_signal"], 1)
        self.assertIsNone(r["dismiss_rate"])

    def test_user_response_column_is_an_explicit_label(self):
        self.log("2026-08-01", 1, "a", response="done")
        r = self.run_compute()
        self.assertEqual(r["outcomes"]["positive"], 1)
        self.assertEqual(r["explicit"]["labels"], {"ACTED": 1})

    def test_sent_event_without_log_row_is_counted(self):
        self.event("hermes-1", "SENT", "2026-10-13T08:00")
        self.event("hermes-1", "DISMISSED", "2026-10-13T09:00")
        r = self.run_compute()
        self.assertEqual(r["sent"], 1)
        self.assertEqual(r["outcomes"]["negative"], 1)

    def test_time_window(self):
        self.log("2026-07-01", 1, "old")
        self.log("2026-09-01", 1, "new")
        self.event("old", "DISMISSED_INFERRED", "2026-07-02")
        self.event("new", "ACTED", "2026-09-01T05:00")
        r = self.run_compute(since="2026-08-01")
        self.assertEqual(r["sent"], 1)
        self.assertEqual(r["dismiss_rate"], 0.0)
        self.assertEqual(r["window"], {"since": "2026-08-01", "until": None})

    def test_gate(self):
        for i in range(20):
            nid = f"n{i}"
            self.log("2026-08-01", 1, nid)
            self.event(nid, "ACTED" if i < 15 else "DISMISSED", "2026-08-01T05:00")
        r = self.run_compute()
        self.assertTrue(r["gate"]["sample_sufficient"])
        self.assertTrue(r["gate"]["passes"])  # 5/20 = 25%

    def test_gate_not_evaluable_below_sample(self):
        self.log("2026-08-01", 1, "a")
        self.event("a", "ACTED", "2026-08-01T05:00")
        r = self.run_compute()
        self.assertFalse(r["gate"]["sample_sufficient"])
        self.assertIn("NOT EVALUABLE", dismiss_rate.render(r))

    def test_real_schema_check_constraint_is_readable(self):
        """The production table restricts event_type; the reader must not care."""
        self.conn.executescript("""
            DROP TABLE notification_events;
            CREATE TABLE notification_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notif_id TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK (event_type IN ('SENT','TAPPED','DISMISSED_INFERRED')),
                event_ts TEXT NOT NULL);
        """)
        self.log("2026-08-01", 1, "a")
        self.event("a", "SENT", "2026-08-01")
        self.event("a", "DISMISSED_INFERRED", "2026-08-02")
        r = self.run_compute()
        self.assertEqual(r["dismiss_rate"], 1.0)

    def test_opens_read_only(self):
        self.conn.commit()
        before = os.path.getmtime(self.path)
        dismiss_rate.compute(self.path)
        self.assertEqual(os.path.getmtime(self.path), before)


if __name__ == "__main__":
    unittest.main()
