"""Tests for mirroring Surface Engine notifications to iMessage via Hermes.

No real sends: the subprocess runner is faked and the DB is a temp file.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import imessage_dispatch as imd  # noqa: E402
import mikai_decide as md  # noqa: E402


def fake_runner(returncode=0, stdout="", stderr="", raises=None, calls=None):
    def run(cmd, **kwargs):
        if calls is not None:
            calls.append((cmd, kwargs))
        if raises:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
    return run


class FormatTests(unittest.TestCase):
    def test_layout(self):
        text = imd.format_message(" Monstera pole ", "Pick one tonight.\n", "abc123def456")
        self.assertEqual(
            text,
            "Monstera pole\n\nPick one tonight.\n\nReply: done · snooze · not relevant\nref: abc123def456",
        )

    def test_ref_is_last_line(self):
        self.assertEqual(imd.format_message("t", "b", "n1").splitlines()[-1], "ref: n1")


class FlagTests(unittest.TestCase):
    def test_off_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(imd.imessage_enabled())

    def test_on_only_for_1(self):
        with mock.patch.dict(os.environ, {"MIKAI_IMESSAGE": "1"}):
            self.assertTrue(imd.imessage_enabled())
        with mock.patch.dict(os.environ, {"MIKAI_IMESSAGE": "true"}):
            self.assertFalse(imd.imessage_enabled())

    def test_copy_is_noop_when_off(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(imd, "send") as send:
            ok, status = md.send_imessage_copy({"title": "t", "body": "b"}, "n1")
        self.assertEqual((ok, status), (False, "off"))
        send.assert_not_called()


class SendTests(unittest.TestCase):
    def test_success_uses_hermes_send_with_stdin(self):
        calls = []
        with mock.patch.dict(os.environ, {"MIKAI_HERMES_BIN": "/x/hermes"}, clear=True):
            ok, msg = imd.send("hello", runner=fake_runner(calls=calls))
        self.assertEqual((ok, msg), (True, "imessage_sent"))
        cmd, kwargs = calls[0]
        self.assertEqual(cmd, ["/x/hermes", "send", "--to", "photon", "--quiet", "--file", "-"])
        self.assertEqual(kwargs["input"], "hello")

    def test_target_override(self):
        calls = []
        with mock.patch.dict(os.environ, {"MIKAI_IMESSAGE_TARGET": "photon:any;-;+15550000000"}):
            imd.send("x", runner=fake_runner(calls=calls))
        self.assertIn("photon:any;-;+15550000000", calls[0][0])

    def test_nonzero_exit_reports_last_stderr_line(self):
        ok, msg = imd.send("x", runner=fake_runner(returncode=2, stderr="warn\nno live sidecar"))
        self.assertFalse(ok)
        self.assertEqual(msg, "hermes_send_exit_2: no live sidecar")

    def test_missing_binary(self):
        ok, msg = imd.send("x", runner=fake_runner(raises=FileNotFoundError()))
        self.assertFalse(ok)
        self.assertTrue(msg.startswith("hermes_not_found"))

    def test_timeout(self):
        ok, msg = imd.send("x", runner=fake_runner(raises=subprocess.TimeoutExpired("hermes", 30)))
        self.assertFalse(ok)
        self.assertTrue(msg.startswith("hermes_send_timeout"))


class LogColumnTests(unittest.TestCase):
    def test_imessage_status_is_logged(self):
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(md, "DB_PATH", Path(d) / "log.db"):
            conn = md.db_connect()
            notif = {"title": "t", "body": "b", "priority": "active", "evidence": ["x"]}
            md.log_sent(conn, "2026-10-24T00:00:00+00:00", "prompt", notif,
                        slate_index=0, slate_size=1, notif_id="n1",
                        imessage_status="failed: hermes_send_exit_1: boom")
            row = conn.execute(
                "SELECT imessage_status FROM notification_log WHERE notif_id='n1'"
            ).fetchone()
            conn.close()
        self.assertEqual(row[0], "failed: hermes_send_exit_1: boom")


class OutboxTests(unittest.TestCase):
    def test_record_outbox_creates_table_and_upserts(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "log.db"
            imd.record_outbox(db, "n1", "first", kind="test")
            imd.record_outbox(db, "n1", "second")
            rows = sqlite3.connect(db).execute("SELECT ref, text, kind FROM imessage_outbox").fetchall()
        self.assertEqual(rows, [("n1", "second", "surface")])

    def test_copy_records_outbox_only_on_success(self):
        import sqlite3
        notif = {"title": "t", "body": "b"}
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict(os.environ, {"MIKAI_IMESSAGE": "1"}), \
             mock.patch.object(md, "DB_PATH", Path(d) / "log.db"):
            with mock.patch.object(imd, "send", return_value=(False, "hermes_send_exit_1: boom")):
                md.send_imessage_copy(notif, "fail1")
            with mock.patch.object(imd, "send", return_value=(True, "imessage_sent")):
                ok, _ = md.send_imessage_copy(notif, "ok1")
            refs = [r[0] for r in sqlite3.connect(Path(d) / "log.db").execute("SELECT ref FROM imessage_outbox")]
        self.assertTrue(ok)
        self.assertEqual(refs, ["ok1"])


if __name__ == "__main__":
    unittest.main()
