"""Write-back obligation tests (SPEC §5.1) for the three action scenarios:

  - infra/mikai_shell/organize.py       (mode="shell")
  - infra/decider/calendar_planner.py   (mode="calendar_planner")
  - infra/decider/week_planner.py       (mode="week_planner")

Doctrine under test: an action that leaves no trace never happened.
  - successful mutation  → exactly one progress.jsonl row, correct mode
  - failed / dry / preview run → zero progress.jsonl growth
  - thread log line appended only on a clear, conservative match

Every test runs against a throwaway brain: HOME is repointed at a temp
dir AND MIKAI_BRAIN_ROOT is set under it, then infra.mikai_brain is
reloaded so the constants rebind. All LLM calls, CalDAV/network I/O,
ntfy dispatch, sqlite, and file moves are mocked — nothing here may
touch the real brain, real Desktop, iCloud, or any network.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "infra" / "mikai_shell"))
sys.path.insert(0, str(REPO / "infra" / "decider"))

import organize  # noqa: E402
from planner import OrganizationPlan, ProposedMove  # noqa: E402
import calendar_planner as cp  # noqa: E402
import week_planner as wp  # noqa: E402


class WritebackTestCase(unittest.TestCase):
    """Base: temp HOME + MIKAI_BRAIN_ROOT + reloaded brain modules."""

    ENV_KEYS = ("HOME", "MIKAI_BRAIN_ROOT",
                "MIKAI_ICLOUD_USER", "MIKAI_ICLOUD_APP_PASSWORD")

    def setUp(self) -> None:
        self._env = {k: os.environ.get(k) for k in self.ENV_KEYS}
        self.home = tempfile.mkdtemp(prefix="mikai-writeback-test-")
        os.environ["HOME"] = self.home
        os.environ["MIKAI_BRAIN_ROOT"] = str(Path(self.home) / "brain")
        os.environ["MIKAI_ICLOUD_USER"] = "test@example.com"
        os.environ["MIKAI_ICLOUD_APP_PASSWORD"] = "not-a-real-password"

        import infra.mikai_brain as brain_pkg
        importlib.reload(brain_pkg)
        from infra.mikai_brain import ledger, threads
        importlib.reload(threads)
        importlib.reload(ledger)
        self.brain, self.ledger, self.threads = brain_pkg, ledger, threads

        self.assertTrue(str(brain_pkg.BRAIN_ROOT).startswith(self.home),
                        "brain root escaped the temp HOME — refusing to run")
        for d in (brain_pkg.THREADS_DIR, brain_pkg.STATE_DIR):
            d.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.home, ignore_errors=True)
        # Re-point brain modules at the real root for later imports.
        importlib.reload(self.brain)
        importlib.reload(self.threads)
        importlib.reload(self.ledger)

    # ── helpers ──────────────────────────────────────────────────────────

    def seed_thread(self, slug: str, title: str | None = None) -> Path:
        path = self.brain.THREADS_DIR / f"{slug}.md"
        path.write_text(
            f"---\nslug: {slug}\ntitle: {title or slug.replace('-', ' ')}\n"
            f"state: acting\nlast_activity: 2026-08-01\n---\n\n"
            f"## Log\n- 2026-08-01 opened\n"
        )
        return path

    def runs(self) -> list[dict]:
        return self.ledger.read_runs()

    def log_lines(self, slug: str) -> list[str]:
        return self.threads.parse_thread(self.brain.THREADS_DIR / f"{slug}.md").log_lines


# ── thread-match heuristic ───────────────────────────────────────────────


class TestThreadMatchHeuristic(WritebackTestCase):

    def test_slug_dehyphenated_and_title_forms_match(self):
        self.seed_thread("proposal-timing", title="ring proposal timing")
        threads = self.threads.load_all()
        for text in ("touches proposal-timing directly",
                     "about the proposal timing question",
                     "re: Ring Proposal Timing next steps"):
            hit = self.threads.match_threads_in_text(text, threads)
            self.assertEqual([t.slug for t in hit], ["proposal-timing"], text)
        self.assertEqual(
            self.threads.match_threads_in_text("random screenshots cleanup", threads), [])

    def test_ambiguous_component_never_matches(self):
        """'proposal' alone is a tie between two proposal-* threads → no match."""
        self.seed_thread("proposal-timing")
        self.seed_thread("proposal-jeweler")
        threads = self.threads.load_all()
        self.assertEqual(
            self.threads.match_threads_in_text("photos for the proposal", threads), [])
        # A unique >=6-char component still matches by whole word...
        self.assertEqual(
            [t.slug for t in self.threads.match_threads_in_text(
                "call the jeweler about sizing", threads)],
            ["proposal-jeweler"])
        # ...but short components (<6 chars) never do, even when unique.
        self.seed_thread("visa-renewal")
        self.assertEqual(
            self.threads.match_threads_in_text("check the visa box",
                                               self.threads.load_all()), [])


# ── organize.py (mode="shell") ───────────────────────────────────────────


class TestOrganizeWriteback(WritebackTestCase):

    def _plan(self, moves: list[ProposedMove]) -> OrganizationPlan:
        return OrganizationPlan(scope="~/tmp-root", moves=moves,
                                taxonomy=[], rationale="test plan")

    def _run(self, moves, execute_side_effect=None, dry_run=False):
        plan_obj = self._plan(moves)
        batch = mock.Mock(batch_id="cafe12beef34")
        with mock.patch.object(organize, "plan", return_value=plan_obj), \
             mock.patch.object(organize, "validate", return_value=[]), \
             mock.patch.object(organize, "start_batch", return_value=batch) as sb, \
             mock.patch.object(organize, "execute_move",
                               side_effect=execute_side_effect) as em, \
             mock.patch.object(organize, "finish_batch") as fb, \
             mock.patch.object(organize, "notify") as nt, \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            rc = organize.run(root=str(Path(self.home) / "sandbox"),
                              prompt="tidy up", dry_run=dry_run,
                              yes=True, interactive=False)
        return rc, em, sb, fb, nt

    MOVES = [
        ProposedMove(src="/x/a.png", dst="/x/Screenshots/a.png", rationale="old screenshot"),
        ProposedMove(src="/x/b.png", dst="/x/Screenshots/b.png", rationale="old screenshot"),
        ProposedMove(src="/x/ring.pdf", dst="/x/Domestic/ring.pdf", rationale="quote for the ring"),
    ]

    def test_successful_run_logs_one_shell_row(self):
        rc, em, *_ = self._run(self.MOVES)
        self.assertEqual(rc, 0)
        self.assertEqual(em.call_count, 3)
        runs = self.runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["mode"], "shell")
        self.assertIn("Moved 3 file(s)", runs[0]["did"])
        self.assertIn("Screenshots×2", runs[0]["did"])
        self.assertEqual(runs[0]["extra"]["batch_id"], "cafe12beef34")

    def test_failed_run_logs_nothing(self):
        rc, *_ = self._run(self.MOVES, execute_side_effect=OSError("disk full"))
        self.assertEqual(rc, 1)
        self.assertEqual(self.runs(), [])

    def test_partial_failure_still_logs_with_honest_did(self):
        effects = [None, OSError("locked"), None]
        rc, *_ = self._run(self.MOVES, execute_side_effect=effects)
        self.assertEqual(rc, 1)
        runs = self.runs()
        self.assertEqual(len(runs), 1)
        self.assertIn("Moved 2 file(s)", runs[0]["did"])
        self.assertIn("(1 failed)", runs[0]["did"])

    def test_dry_run_logs_nothing_and_moves_nothing(self):
        rc, em, *_ = self._run(self.MOVES, dry_run=True)
        self.assertEqual(rc, 0)
        em.assert_not_called()
        self.assertEqual(self.runs(), [])

    def test_thread_append_on_rationale_match(self):
        self.seed_thread("proposal-timing")
        moves = [ProposedMove(src="/x/ring.pdf", dst="/x/Domestic/ring.pdf",
                              rationale="jeweler quote for the proposal ring")]
        rc, *_ = self._run(moves)
        self.assertEqual(rc, 0)
        self.assertEqual(self.runs()[0]["threads_touched"], ["proposal-timing"])
        lines = self.log_lines("proposal-timing")
        self.assertTrue(any("[shell:organize] Moved 1 file(s)" in ln for ln in lines),
                        lines)

    def test_no_thread_append_without_match(self):
        self.seed_thread("proposal-timing")
        before = self.log_lines("proposal-timing")
        rc, *_ = self._run([ProposedMove(src="/x/a.png", dst="/x/Screenshots/a.png",
                                         rationale="old screenshot")])
        self.assertEqual(rc, 0)
        self.assertEqual(self.runs()[0]["threads_touched"], [])
        self.assertEqual(self.log_lines("proposal-timing"), before)


# ── calendar_planner.py (mode="calendar_planner") ────────────────────────


LLM_PROPOSAL = {
    "title": "Docker RAM fix + Memory decision",
    "description": "1. Fix docker RAM cap\n2. Decide memory store",
    "picks": [{"item": "docker", "source": "git", "why_now": "blocking"}],
    "rationale": "top of the stack today",
}


class TestCalendarPlannerWriteback(WritebackTestCase):

    def _event(self, title="Deep work block", desc=""):
        return cp.Event(
            calendar_href="https://caldav.example/cal/",
            event_href="https://caldav.example/cal/e1.ics",
            etag="e1", uid="uid-1", title=title, description=desc,
            dtstart="20260805T100000", dtend="20260805T153000",
        )

    def _run(self, llm=LLM_PROPOSAL, llm_raises=False,
             dispatch_ok=True, dry_run=False, events=None):
        client = mock.Mock()
        client.todays_events.return_value = (
            [self._event()] if events is None else events)
        llm_mock = (mock.Mock(side_effect=RuntimeError("llm down"))
                    if llm_raises else mock.Mock(return_value=llm))
        with mock.patch.object(cp.md, "db_connect",
                               return_value=sqlite3.connect(":memory:")), \
             mock.patch.object(cp, "ICloudCalDAV", return_value=client), \
             mock.patch.object(cp, "already_proposed_today", return_value=False), \
             mock.patch.object(cp, "insert_proposal") as ins, \
             mock.patch.object(cp, "dispatch_proposal",
                               return_value=(dispatch_ok,
                                             "http_200" if dispatch_ok else "ntfy_error")) as disp, \
             mock.patch.object(cp, "call_llm", llm_mock), \
             mock.patch.object(cp, "gather_git_context", return_value={
                 "branch": "b", "uncommitted": "", "recent_commits": "",
                 "recent_branches": ""}), \
             mock.patch.object(cp, "gather_open_questions", return_value=""), \
             mock.patch.object(cp, "gather_inflight", return_value=""), \
             mock.patch.object(cp, "gather_needs_registry", return_value=""), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            rc = cp.run_once(dry_run=dry_run)
        return rc, ins, disp

    def test_dispatched_proposal_logs_one_row(self):
        rc, ins, disp = self._run()
        self.assertEqual(rc, 0)
        ins.assert_called_once()
        disp.assert_called_once()
        runs = self.runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["mode"], "calendar_planner")
        self.assertIn("Proposed 1 calendar block rewrite(s)", runs[0]["did"])
        self.assertIn("Docker RAM fix", runs[0]["did"])
        self.assertEqual(len(runs[0]["extra"]["proposal_ids"]), 1)

    def test_failed_dispatch_logs_nothing(self):
        rc, ins, _ = self._run(dispatch_ok=False)
        self.assertEqual(rc, 0)
        ins.assert_called_once()   # stored, but never reached the user
        self.assertEqual(self.runs(), [])

    def test_llm_failure_logs_nothing(self):
        rc, ins, disp = self._run(llm_raises=True)
        self.assertEqual(rc, 0)
        ins.assert_not_called()
        disp.assert_not_called()
        self.assertEqual(self.runs(), [])

    def test_dry_run_logs_nothing(self):
        rc, ins, disp = self._run(dry_run=True)
        self.assertEqual(rc, 0)
        ins.assert_not_called()
        disp.assert_not_called()
        self.assertEqual(self.runs(), [])

    def test_thread_append_when_proposal_names_thread(self):
        self.seed_thread("proposal-timing")
        llm = dict(LLM_PROPOSAL,
                   title="Proposal venue research + timing",
                   description="Shortlist venues for proposal-timing thread")
        rc, *_ = self._run(llm=llm)
        self.assertEqual(rc, 0)
        self.assertEqual(self.runs()[0]["threads_touched"], ["proposal-timing"])
        lines = self.log_lines("proposal-timing")
        self.assertTrue(any("[calendar_planner] Proposed block rewrite" in ln
                            for ln in lines), lines)

    def test_no_thread_append_without_match(self):
        self.seed_thread("proposal-timing")
        before = self.log_lines("proposal-timing")
        rc, *_ = self._run()   # default LLM proposal: docker/memory, unrelated
        self.assertEqual(rc, 0)
        self.assertEqual(self.runs()[0]["threads_touched"], [])
        self.assertEqual(self.log_lines("proposal-timing"), before)


# ── week_planner.py (mode="week_planner") ────────────────────────────────


MASTER_ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
    "BEGIN:VEVENT\r\nUID:46BF1457-63C5-464A-9C48-4D629B0AC7CC\r\n"
    "SEQUENCE:11\r\nSUMMARY:Recommendations\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


class TestWeekPlannerWriteback(WritebackTestCase):

    def _plan_dict(self, desc_extra=""):
        days = wp.week_workdays()
        return {
            "week_rationale": "ship the brain",
            "days": [
                {"date": d.isoformat(), "weekday": d.strftime("%A"),
                 "title": f"Day {i} engineering theme",
                 "description": f"work items {desc_extra}",
                 "rationale": "fits", "primary_branch": "feat/pure-file-brain"}
                for i, d in enumerate(days)
            ],
        }

    def _run(self, apply=True, put_fails=False, plan=None):
        put_exc = wp.CalDAVError("412 precondition failed")

        def fake_request(method, href, user, pw, body=None, headers=None):
            if method == "GET":
                return 200, {"ETag": '"abc"'}, MASTER_ICS.encode()
            if put_fails:
                raise put_exc
            return 201, {"ETag": '"def"'}, b""

        argv = ["week_planner.py"] + (["--apply"] if apply else [])
        patches = [
            mock.patch.object(wp, "_request", side_effect=fake_request),
            mock.patch.object(wp, "call_llm",
                              return_value=plan or self._plan_dict()),
            mock.patch.object(wp, "gather_workspace_branches",
                              return_value="- feat/pure-file-brain (today)"),
            mock.patch.object(wp, "gather_uncommitted_across_worktrees",
                              return_value="(all worktrees clean)"),
            mock.patch.object(cp, "gather_open_questions", return_value=""),
            mock.patch.object(sys, "argv", argv),
        ]
        if put_fails:
            # The failure path dumps a debug .ics to /tmp — keep tests hermetic.
            patches.append(mock.patch.object(wp, "Path"))
        with contextlib.ExitStack() as stack:
            mocks = [stack.enter_context(p) for p in patches]
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            rc = wp.main()
        return rc, mocks[0]  # (rc, _request mock)

    def test_apply_success_logs_one_row(self):
        rc, req = self._run(apply=True)
        self.assertEqual(rc, 0)
        self.assertEqual(req.call_count, 2)  # GET + PUT
        self.assertEqual(req.call_args_list[1].args[0], "PUT")
        runs = self.runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["mode"], "week_planner")
        self.assertIn("Wrote 5 week-plan overrides to iCloud", runs[0]["did"])
        self.assertEqual(len(runs[0]["extra"]["dates"]), 5)

    def test_failed_put_logs_nothing(self):
        rc, req = self._run(apply=True, put_fails=True)
        self.assertEqual(rc, 6)
        self.assertEqual(self.runs(), [])

    def test_preview_mode_neither_puts_nor_logs(self):
        rc, req = self._run(apply=False)
        self.assertEqual(rc, 0)
        self.assertEqual(req.call_count, 1)  # GET only, never PUT
        self.assertEqual(self.runs(), [])

    def test_thread_append_when_day_plan_names_thread(self):
        self.seed_thread("proposal-timing")
        rc, _ = self._run(apply=True,
                          plan=self._plan_dict(desc_extra="incl. proposal-timing prep"))
        self.assertEqual(rc, 0)
        self.assertEqual(self.runs()[0]["threads_touched"], ["proposal-timing"])
        lines = self.log_lines("proposal-timing")
        self.assertEqual(sum("[week_planner] Planned" in ln for ln in lines), 5)

    def test_no_thread_append_without_match(self):
        self.seed_thread("proposal-timing")
        before = self.log_lines("proposal-timing")
        rc, _ = self._run(apply=True)
        self.assertEqual(rc, 0)
        self.assertEqual(self.runs()[0]["threads_touched"], [])
        self.assertEqual(self.log_lines("proposal-timing"), before)


if __name__ == "__main__":
    unittest.main()
