"""Tests for the week planner's approval gate and CLI surface.

The gate is the safety-critical part: `--apply` writes five real blocks to
Brian's iCloud calendar, and D-055's invariant is that no calendar write
happens without explicit human approval. The unattended daily planner gets
that approval from an ntfy tap; this path gets it from a typed `y`. These
tests pin the ways that gate must refuse.

No network, no LLM, no CalDAV — `_confirm` is pure I/O over stdin.
"""
from __future__ import annotations

import io
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import week_planner as wp  # noqa: E402


DAYS = [date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 19),
        date(2026, 8, 20), date(2026, 8, 21)]


class _FakeTTY(io.StringIO):
    """StringIO that claims to be a terminal, so _confirm reaches input()."""

    def isatty(self) -> bool:  # noqa: D102
        return True


class ConfirmTests(unittest.TestCase):
    def _confirm_with(self, typed: str) -> bool:
        with mock.patch.object(sys, "stdin", _FakeTTY()), \
             mock.patch("builtins.input", return_value=typed):
            return wp._confirm(DAYS)

    def test_y_approves(self):
        self.assertTrue(self._confirm_with("y"))

    def test_yes_approves(self):
        self.assertTrue(self._confirm_with("yes"))

    def test_case_and_whitespace_tolerated(self):
        self.assertTrue(self._confirm_with("  Y  "))

    def test_n_refuses(self):
        self.assertFalse(self._confirm_with("n"))

    def test_empty_refuses(self):
        """Bare Enter must not approve a calendar write."""
        self.assertFalse(self._confirm_with(""))

    def test_unrecognized_refuses(self):
        """Anything not clearly affirmative is a refusal, not a retry."""
        self.assertFalse(self._confirm_with("sure"))

    def test_non_tty_refuses_without_prompting(self):
        """A pipe/cron/CI stdin has nobody present to approve — abort, and
        never block on input()."""
        with mock.patch.object(sys, "stdin", io.StringIO("y\n")), \
             mock.patch("builtins.input", side_effect=AssertionError(
                 "input() must not be called when stdin is not a TTY")):
            self.assertFalse(wp._confirm(DAYS))

    def test_eof_refuses(self):
        with mock.patch.object(sys, "stdin", _FakeTTY()), \
             mock.patch("builtins.input", side_effect=EOFError):
            self.assertFalse(wp._confirm(DAYS))

    def test_keyboard_interrupt_refuses(self):
        with mock.patch.object(sys, "stdin", _FakeTTY()), \
             mock.patch("builtins.input", side_effect=KeyboardInterrupt):
            self.assertFalse(wp._confirm(DAYS))


class CliTests(unittest.TestCase):
    """main() must reject incoherent flag combinations before it touches
    the network. Each case exits during argparse, well before the iCloud
    credential check."""

    def _main_with(self, argv: list[str]) -> int:
        with mock.patch.object(sys, "argv", ["week_planner.py", *argv]):
            return wp.main()

    def test_yes_without_apply_is_rejected(self):
        with mock.patch.object(sys, "stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                self._main_with(["--yes"])
        self.assertNotEqual(ctx.exception.code, 0)

    def test_apply_and_dry_run_are_mutually_exclusive(self):
        with mock.patch.object(sys, "stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                self._main_with(["--apply", "--dry-run"])
        self.assertNotEqual(ctx.exception.code, 0)

    def test_default_is_dry_run(self):
        """No flags must not imply --apply. Proven by main() bailing on the
        missing-credentials check (rc=2) with no CalDAV call attempted."""
        with mock.patch.dict("os.environ", {"MIKAI_ICLOUD_USER": "",
                                            "MIKAI_ICLOUD_APP_PASSWORD": ""}), \
             mock.patch.object(wp, "_request",
                               side_effect=AssertionError("no network in dry run")), \
             mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(self._main_with([]), 2)


# ── master parsing / instance validation / splice idempotency ──────────


LIVE_MASTER = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
    "BEGIN:VEVENT\r\n"
    "DTEND;TZID=America/Vancouver:20260810T120000\r\n"
    "DTSTART;TZID=America/Vancouver:20260810T070000\r\n"
    "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR\r\n"
    "SEQUENCE:14\r\n"
    "SUMMARY:MIKAI: Noonchi + Sumimasen \r\n"
    "UID:AB6210F8-6CDA-4A03-B950-0BDF5E71C682\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)

# The event week_planner used to hardcode: series ended 2026-07-15.
EXPIRED_MASTER = LIVE_MASTER.replace(
    "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    "RRULE:FREQ=WEEKLY;UNTIL=20260715T065959Z;BYDAY=MO,TU,WE,TH,FR",
)


class ParseMasterTests(unittest.TestCase):
    def test_reads_shape_off_the_calendar(self):
        s = wp._parse_master(LIVE_MASTER)
        self.assertEqual(s.tzid, "America/Vancouver")
        self.assertEqual(s.start_time, "070000")
        self.assertEqual(s.end_time, "120000")
        self.assertEqual(s.sequence, 14)
        self.assertIsNone(s.until)
        self.assertEqual(s.bydays, {"MO", "TU", "WE", "TH", "FR"})

    def test_skips_override_vevents_when_finding_the_master(self):
        """A master .ics accumulates override VEVENTs. The shape must come
        from the one carrying RRULE, not from an override."""
        override = (
            "BEGIN:VEVENT\r\n"
            "DTSTART;TZID=America/Vancouver:20260714T090000\r\n"
            "DTEND;TZID=America/Vancouver:20260714T100000\r\n"
            "RECURRENCE-ID;TZID=America/Vancouver:20260714T070000\r\n"
            "UID:AB6210F8-6CDA-4A03-B950-0BDF5E71C682\r\n"
            "END:VEVENT\r\n"
        )
        s = wp._parse_master(LIVE_MASTER.replace("END:VCALENDAR", override + "END:VCALENDAR"))
        self.assertEqual(s.start_time, "070000")   # not the override's 090000

    def test_no_master_raises(self):
        with self.assertRaises(ValueError):
            wp._parse_master("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")


class CoverageGuardTests(unittest.TestCase):
    """The regression that made this necessary: the planner aimed five
    overrides at a series whose RRULE had expired a month earlier."""

    def test_live_series_covers_this_week(self):
        self.assertIsNone(
            wp.check_days_covered(wp._parse_master(LIVE_MASTER), DAYS))

    def test_expired_series_is_refused(self):
        err = wp.check_days_covered(wp._parse_master(EXPIRED_MASTER), DAYS)
        self.assertIsNotNone(err)
        self.assertIn("2026-07-15", err)

    def test_day_outside_byday_is_refused(self):
        saturday = [date(2026, 8, 22)]   # series is MO-FR
        err = wp.check_days_covered(wp._parse_master(LIVE_MASTER), saturday)
        self.assertIsNotNone(err)
        self.assertIn("2026-08-22", err)


class SpliceTests(unittest.TestCase):
    def _override(self, day: str, title: str) -> str:
        shape = wp._parse_master(LIVE_MASTER)
        return wp.render_override_vevent(
            date(2026, 8, int(day)), title, "body", 15, shape)

    def test_recurrence_id_matches_the_instance_start(self):
        """An override only binds if its RECURRENCE-ID equals the instance's
        start exactly — same clock time, same TZID."""
        out = self._override("17", "Monday plan")
        self.assertIn("RECURRENCE-ID;TZID=America/Vancouver:20260817T070000", out)
        self.assertIn("DTSTART;TZID=America/Vancouver:20260817T070000", out)
        self.assertIn("DTEND;TZID=America/Vancouver:20260817T120000", out)

    def test_rerun_replaces_rather_than_duplicates(self):
        once = wp.splice_overrides(LIVE_MASTER, [self._override("17", "first")])
        twice = wp.splice_overrides(once, [self._override("17", "second")])
        self.assertEqual(twice.count("RECURRENCE-ID;TZID=America/Vancouver:20260817T070000"), 1)
        self.assertIn("second", twice)
        self.assertNotIn("first", twice)

    def test_other_weeks_overrides_are_preserved(self):
        """Overrides for instances we're not rewriting are real history."""
        july = (
            "BEGIN:VEVENT\r\n"
            "RECURRENCE-ID;TZID=America/Vancouver:20260714T070000\r\n"
            "SUMMARY:July work\r\nUID:AB6210F8-6CDA-4A03-B950-0BDF5E71C682\r\n"
            "END:VEVENT\r\n"
        )
        base = LIVE_MASTER.replace("END:VCALENDAR", july + "END:VCALENDAR")
        out = wp.splice_overrides(base, [self._override("17", "August work")])
        self.assertIn("July work", out)
        self.assertIn("August work", out)

    def test_master_vevent_survives_splice(self):
        out = wp.splice_overrides(LIVE_MASTER, [self._override("17", "x")])
        self.assertIn("RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", out)
        self.assertTrue(out.endswith("END:VCALENDAR\r\n"))


if __name__ == "__main__":
    unittest.main()
