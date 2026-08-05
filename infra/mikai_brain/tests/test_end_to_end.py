"""End-to-end tests for the file-based brain modules.

Every test runs against a throwaway brain tree. The brain root is derived
from Path.home() at import time, so setUp repoints HOME at a temp dir and
reloads the package (which recomputes the constants) plus every submodule
that captured them via `from . import X`. ~/.mikai is never touched.

All LLM calls are patched. Nothing here may reach the network or spawn
`claude`.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _days_ahead(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


class BrainTestCase(unittest.TestCase):
    """Base: temp brain tree + reloaded modules bound to it."""

    def setUp(self) -> None:
        self._orig_home = os.environ.get("HOME")
        self.home = tempfile.mkdtemp(prefix="mikai-brain-test-")
        os.environ["HOME"] = self.home

        import infra.mikai_brain as brain_pkg
        importlib.reload(brain_pkg)
        from infra.mikai_brain import consolidate, ledger, standup, store, threads, triage
        for module in (threads, ledger, store, standup, triage, consolidate):
            importlib.reload(module)

        self.brain = brain_pkg
        self.threads = threads
        self.ledger = ledger
        self.standup = standup
        self.triage = triage
        self.consolidate = consolidate
        self.store = store

        self.assertTrue(str(brain_pkg.BRAIN_ROOT).startswith(self.home),
                        "brain root escaped the temp HOME — refusing to run")

        for d in (brain_pkg.THREADS_DIR, brain_pkg.INBOX_DIR, brain_pkg.INBOX_PROCESSED,
                  brain_pkg.ENTITIES_DIR, brain_pkg.STATE_DIR,
                  brain_pkg.DECISIONS_LOG.parent):
            d.mkdir(parents=True, exist_ok=True)
        brain_pkg.BRAIN_MD.write_text(
            "# Brian's brain\n\nFirst-node summary.\n\n"
            "## Current priorities\n\nSeeded priorities body.\n\n"
            "## Departments\n\nlove, health, mikai\n"
        )
        (brain_pkg.BRAIN_ROOT / "CLAUDE.md").write_text("# Brain-scope constitution\n")

    def tearDown(self) -> None:
        if self._orig_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._orig_home
        shutil.rmtree(self.home, ignore_errors=True)
        # Re-point the modules at the real brain root so a later import in the
        # same process doesn't inherit a deleted temp path.
        importlib.reload(self.brain)
        for module in (self.threads, self.ledger, self.store, self.standup,
                       self.triage, self.consolidate):
            importlib.reload(module)

    # ── seeding helpers ──────────────────────────────────────────────────

    def write_thread(self, slug: str, *, body: str = "", raw: str = "", **fm: str) -> Path:
        path = self.brain.THREADS_DIR / f"{slug}.md"
        if raw:
            path.write_text(raw)
            return path
        fields = {"slug": slug, "title": slug.replace("-", " "), "state": "exploring",
                  "state_since": _days_ago(30), "last_activity": _days_ago(1),
                  "next_step": '"do the thing"', "entities": "[]", "department": "mikai"}
        fields.update(fm)
        fm_block = "\n".join(f"{k}: {v}" for k, v in fields.items())
        path.write_text(f"---\n{fm_block}\n---\n\n{body or '## Log' + chr(10) + '- ' + _days_ago(1) + ' opened'}\n")
        return path

    def write_delivery_event(self, thread: str, response: str, hours_ago: float,
                             kind: str = "stall") -> None:
        ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
        with self.brain.DELIVERY_LOG.open("a") as f:
            f.write(json.dumps({"ts": ts, "thread": thread, "kind": kind,
                                "response": response, "note": ""}) + "\n")

    def findings(self) -> list:
        all_findings, _ = self.standup.run(write_state=False, verbose=False)
        return all_findings

    def kinds_for(self, slug: str) -> set:
        return {f.kind for f in self.findings() if f.thread_slug == slug}


class TestStandupRules(BrainTestCase):

    def test_standup_on_empty_brain(self):
        """No threads at all: run() completes, reports zero findings, writes a run entry."""
        all_findings, surfaced = self.standup.run(write_state=True, verbose=False)
        self.assertEqual(all_findings, [])
        self.assertEqual(surfaced, [])
        runs = self.ledger.read_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["mode"], "standup")
        self.assertIn("Scanned 0 threads", runs[0]["did"])

    def test_stall_thresholds_by_state(self):
        """decided stalls at 5d, acting only at 7d, and exploring never stalls."""
        self.write_thread("decided-stale", state="decided", last_activity=_days_ago(6))
        self.write_thread("decided-fresh", state="decided", last_activity=_days_ago(2))
        self.write_thread("acting-under", state="acting", last_activity=_days_ago(6))
        self.write_thread("acting-over", state="acting", last_activity=_days_ago(9))
        self.write_thread("exploring-ancient", state="exploring", last_activity=_days_ago(400))

        stalled = {f.thread_slug for f in self.findings() if f.kind == "stall"}
        self.assertEqual(stalled, {"decided-stale", "acting-over"})

    def test_overdue_next_step_due_is_flagged(self):
        """A next_step_due in the past produces an overdue finding naming the step."""
        self.write_thread("late-visa", state="exploring",
                          next_step='"file the renewal"', next_step_due=_days_ago(3))
        overdue = [f for f in self.findings() if f.kind == "overdue"]
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0].thread_slug, "late-visa")
        self.assertIn("overdue by 3d", overdue[0].reason)
        self.assertIn("file the renewal", overdue[0].reason)

    def test_future_next_step_due_is_not_flagged(self):
        """A future due date — and a due date of today — are not overdue."""
        self.write_thread("future-due", state="exploring", next_step_due=_days_ahead(10))
        self.write_thread("due-today", state="exploring", next_step_due=date.today().isoformat())
        self.assertEqual([f for f in self.findings() if f.kind == "overdue"], [])

    def test_completed_evidence_gate(self):
        """completed WITHOUT an evidence keyword is flagged; WITH one it is not."""
        self.write_thread("shipped-thing", state="completed",
                          body="## Log\n- " + _days_ago(2) + " shipped the build to the store\n")
        self.write_thread("vague-thing", state="completed",
                          body="## Log\n- " + _days_ago(2) + " wrapped this up, feeling good\n")

        self.assertEqual(self.kinds_for("shipped-thing"), set())
        self.assertEqual(self.kinds_for("vague-thing"), {"completed_no_evidence"})

    def test_stall_date_edge_cases(self):
        """Unparseable dates never stall; activity *today* never stalls even with old state_since."""
        self.write_thread("bad-dates", state="decided",
                          last_activity="yesterday-ish", state_since="not-a-date")
        self.write_thread("active-today", state="decided",
                          last_activity=date.today().isoformat(), state_since=_days_ago(40))

        self.assertEqual(self.kinds_for("bad-dates"), set())
        # Regression guard: 0 days (activity today) must not fall through to
        # state_since via an `or` chain and report a stall.
        self.assertEqual(self.kinds_for("active-today"), set())

    def test_standup_persists_stall_transition_and_ledger(self):
        """write_state=True rewrites the thread to `stalled` and logs to both state files."""
        path = self.write_thread("drifting", state="decided", last_activity=_days_ago(20))
        _, surfaced = self.standup.run(write_state=True, verbose=False)

        self.assertEqual([f.thread_slug for f in surfaced], ["drifting"])
        reparsed = self.threads.parse_thread(path)
        self.assertEqual(reparsed.state, "stalled")
        self.assertEqual(reparsed.state_since, date.today().isoformat())
        self.assertTrue(any("[decided→stalled]" in line for line in reparsed.log_lines),
                        f"no transition line in log: {reparsed.log_lines}")
        events = self.ledger.read_events()
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].thread, events[0].kind, events[0].response),
                         ("drifting", "stall", "pending"))


class TestMalformedThreads(BrainTestCase):

    def test_corrupt_frontmatter_does_not_crash_standup(self):
        """Unterminated frontmatter parses to safe defaults instead of raising."""
        self.write_thread("broken", raw=(
            "---\n"
            "slug: broken\n"
            "state: decided\n"
            "last_activity: " + _days_ago(90) + "\n"
            "## Log\n- something happened\n"
        ))
        self.write_thread("healthy", state="decided", last_activity=_days_ago(20))

        parsed = self.threads.parse_thread(self.brain.THREADS_DIR / "broken.md")
        self.assertEqual(parsed.state, "exploring")   # default, frontmatter ignored
        self.assertEqual(parsed.title, "broken")
        self.assertEqual(parsed.log_lines, [])

        # Same for a zero-byte file — load_all must not raise on it either.
        (self.brain.THREADS_DIR / "empty.md").write_text("")
        self.assertEqual({t.slug for t in self.threads.load_all()},
                         {"broken", "healthy", "empty"})

        all_findings, _ = self.standup.run(write_state=False, verbose=False)
        self.assertEqual({f.thread_slug for f in all_findings}, {"healthy"})

    def test_thread_without_log_section_is_handled(self):
        """No `## Log` heading: log_lines is empty and completed-without-evidence still fires."""
        self.write_thread("no-log", state="completed",
                          body="## Context\n\nJust prose. No log heading anywhere.\n")
        parsed = self.threads.parse_thread(self.brain.THREADS_DIR / "no-log.md")
        self.assertEqual(parsed.log_lines, [])
        self.assertEqual(self.kinds_for("no-log"), {"completed_no_evidence"})

        # append_log_line must create the section rather than silently dropping the line.
        self.threads.append_log_line(parsed, "backfilled note")
        reparsed = self.threads.parse_thread(parsed.path)
        self.assertEqual(len(reparsed.log_lines), 1)
        self.assertIn("backfilled note", reparsed.log_lines[0])
        self.assertEqual(reparsed.last_activity, date.today().isoformat())


class TestSurfacingGate(BrainTestCase):

    def _stall_finding(self, slug: str):
        return self.standup.Finding(thread_slug=slug, kind="stall", reason="test stall")

    def _thread_stub(self, slug: str):
        return self.threads.Thread(slug=slug, path=self.brain.THREADS_DIR / f"{slug}.md",
                                   state="decided")

    def test_dismissal_cooldown_suppresses_then_expires(self):
        """A dismissal <48h ago suppresses the thread; an older one, or an `acted`, does not."""
        finding = self._stall_finding("alpha")
        by_slug = {"alpha": self._thread_stub("alpha")}

        self.write_delivery_event("alpha", "dismissed", hours_ago=2)
        self.assertEqual(self.standup.gate([finding], by_slug), [])

        self.brain.DELIVERY_LOG.unlink()
        self.write_delivery_event("alpha", "dismissed", hours_ago=72)
        self.assertEqual(self.standup.gate([finding], by_slug), [finding])

        # Only `dismissed` gates — a fresh `acted` response must not suppress.
        self.brain.DELIVERY_LOG.unlink()
        self.write_delivery_event("alpha", "acted", hours_ago=1)
        self.assertEqual(self.standup.gate([finding], by_slug), [finding])

    def test_three_consecutive_dismissals_mute_thread(self):
        """3 dismissals mute the thread even after the cooldown window has passed."""
        finding = self._stall_finding("gamma")
        by_slug = {"gamma": self._thread_stub("gamma")}

        for hours in (300, 250, 200):
            self.write_delivery_event("gamma", "dismissed", hours_ago=hours)
        self.assertEqual(len(self.ledger.read_events()), 3)
        self.assertEqual(self.standup.gate([finding], by_slug), [])

        # Two old dismissals are below the mute threshold and still surface.
        self.brain.DELIVERY_LOG.unlink()
        for hours in (300, 250):
            self.write_delivery_event("gamma", "dismissed", hours_ago=hours)
        self.assertEqual(self.standup.gate([finding], by_slug), [finding])

    def test_surfacing_capped_at_five_per_run(self):
        """Eight findings produce at most MAX_SURFACE_PER_RUN surfaced items."""
        for i in range(8):
            self.write_thread(f"stale-{i}", state="decided", last_activity=_days_ago(30))
        all_findings, surfaced = self.standup.run(write_state=False, verbose=False)
        self.assertEqual(len(all_findings), 8)
        self.assertEqual(len(surfaced), self.standup.MAX_SURFACE_PER_RUN)


class TestTriage(BrainTestCase):

    # Prose that defeats every heuristic branch: >200 chars, no structure markers,
    # no decision language — so classify_heuristic returns None and the LLM is called.
    AMBIGUOUS = (
        "Some notes about the meeting room acoustics from this morning.\n"
        "The echo seems worse near the north wall than it used to be.\n"
        "Maybe the panels came loose, or maybe the carpet got moved around.\n"
        "Someone ought to measure reverb times across the room again.\n"
        "Not sure what to make of any of it yet.\n"
    )

    def test_heuristic_gate_routes_only_ambiguous_shapes_to_the_llm(self):
        """Short notes and long decision-language notes are settled without an LLM call."""
        self.assertEqual(self.triage.classify_heuristic("quick thought about moss poles").kind,
                         "fragment")
        long_decision = "I have decided to go with the smaller venue downtown. " * 6
        self.assertEqual(self.triage.classify_heuristic(long_decision).kind,
                         "processed_reflection")
        self.assertIsNone(self.triage.classify_heuristic(self.AMBIGUOUS))

    def test_triage_llm_classification_moves_item_to_processed(self):
        """Canned JSON from the LLM drives the write-back and archives the inbox file."""
        item = self.brain.INBOX_DIR / "note.md"
        item.write_text(self.AMBIGUOUS)
        canned = json.dumps({"kind": "processed_reflection", "confidence": 0.9,
                             "rationale": "reads as a resolution"})

        with mock.patch("infra.mikai_llm.chat", return_value=canned) as chat:
            n = self.triage.run(use_llm=True, verbose=False)

        self.assertEqual(n, 1)
        chat.assert_called_once()
        self.assertEqual(chat.call_args.kwargs["tier"], "interactive")
        self.assertFalse(item.exists())
        archived = list(self.brain.INBOX_PROCESSED.glob("*note.md"))
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].name, f"{date.today().isoformat()}__note.md")
        self.assertTrue(self.brain.DECISIONS_LOG.exists())
        self.assertIn("D-op-001", self.brain.DECISIONS_LOG.read_text())

    def test_triage_garbage_llm_response_does_not_lose_item(self):
        """Non-JSON from the LLM falls back to `fragment`; the item is archived, not deleted."""
        item = self.brain.INBOX_DIR / "stray.txt"
        item.write_text(self.AMBIGUOUS)
        before = self.brain.BRAIN_MD.read_text()

        with mock.patch("infra.mikai_llm.chat", return_value="Sure! Here's my answer: a fragment."):
            n = self.triage.run(use_llm=True, verbose=False)

        self.assertEqual(n, 1)
        self.assertFalse(item.exists())
        archived = list(self.brain.INBOX_PROCESSED.glob("*stray.txt"))
        self.assertEqual(len(archived), 1, "inbox item vanished on a bad LLM response")
        self.assertEqual(archived[0].read_text(), self.AMBIGUOUS)
        after = self.brain.BRAIN_MD.read_text()
        self.assertIn("## Scratch", after)
        self.assertIn("meeting room acoustics", after)
        self.assertIn("Seeded priorities body.", after, "existing BRAIN.md content was clobbered")
        self.assertNotEqual(before, after)

    def test_triage_ignores_already_processed_items(self):
        """Archived items are not re-triaged, and --no-llm never calls out."""
        (self.brain.INBOX_PROCESSED / "2026-01-01__old.md").write_text("archived note")
        (self.brain.INBOX_DIR / "quiet.md").write_text(self.AMBIGUOUS)

        with mock.patch("infra.mikai_llm.chat", side_effect=AssertionError("LLM must not be called")):
            self.assertEqual(self.triage.run(use_llm=False, verbose=False), 1)
            self.assertEqual(self.triage.run(use_llm=False, verbose=False), 0)

        self.assertTrue((self.brain.INBOX_PROCESSED / "2026-01-01__old.md").exists())
        self.assertEqual(len(list(self.brain.INBOX_PROCESSED.glob("*quiet.md"))), 1)


class TestConsolidate(BrainTestCase):

    def test_consolidate_dry_run_does_not_mutate_brain_md(self):
        """A dry run calls the LLM once and leaves BRAIN.md and the run log untouched."""
        self.write_thread("proposal-timing", state="decided", last_activity=_days_ago(3))
        before = self.brain.BRAIN_MD.read_text()

        with mock.patch("infra.mikai_llm.chat", return_value="I'm shipping the venue shortlist.") as chat:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = self.consolidate.run(dry_run=True, verbose=False)

        self.assertIn("[dry-run] BRAIN.md not written.", out.getvalue())

        self.assertEqual(rc, 0)
        chat.assert_called_once()
        self.assertEqual(self.brain.BRAIN_MD.read_text(), before)
        self.assertEqual(self.ledger.read_runs(), [])

    def test_consolidate_wet_run_splices_only_the_priorities_section(self):
        """A real run replaces the priorities body, keeps other sections, and logs the run."""
        with mock.patch("infra.mikai_llm.chat", return_value="I'm waiting on the jeweler."):
            rc = self.consolidate.run(dry_run=False, verbose=False)

        self.assertEqual(rc, 0)
        after = self.brain.BRAIN_MD.read_text()
        self.assertIn("I'm waiting on the jeweler.", after)
        self.assertNotIn("Seeded priorities body.", after)
        self.assertIn("## Departments", after)
        self.assertIn("love, health, mikai", after)
        runs = self.ledger.read_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["mode"], "consolidate")


if __name__ == "__main__":
    unittest.main()
