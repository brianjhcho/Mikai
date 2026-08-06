"""Executor-layer tests (infra.mikai_exec).

Doctrine under test:
  - nothing executes without the approval dialog (dry-run never spawns a
    claude subprocess, never opens a dialog, never writes state)
  - Cancel → delivery event (exec_dismissed), NO thread log, NO run row
  - Execute → both ledger.run row (mode="exec") and thread log line
  - every channel is scoped: --allowedTools carries exactly the action
    type's whitelist; `message` never touches claude at all (pbcopy)
  - browse is skipped with a pointer to Playwright MCP; unknown types raise

Every test runs against a throwaway brain: HOME is repointed at a temp
dir AND MIKAI_BRAIN_ROOT is set under it, then infra.mikai_brain is
reloaded so the constants rebind. All LLM calls, dialogs, and subprocess
spawns (claude, pbcopy, osascript) are mocked — nothing here may touch
the real brain, the real clipboard, or any network/MCP server.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from infra.mikai_exec import core  # noqa: E402


PROPOSAL = {
    "intent": "nudge Sam about proposal timing",
    "prompt_to_claude_for_execution": "Hey Sam — checking in on the proposal timing. Can we lock a date this week?",
    "safety_check": "verify the recipient and tone before sending",
}


def _proc(stdout: str = "done") -> mock.Mock:
    return mock.Mock(returncode=0, stdout=stdout, stderr="")


class ExecTestCase(unittest.TestCase):
    """Base: temp HOME + MIKAI_BRAIN_ROOT + reloaded brain modules."""

    ENV_KEYS = ("HOME", "MIKAI_BRAIN_ROOT")

    def setUp(self) -> None:
        self._env = {k: os.environ.get(k) for k in self.ENV_KEYS}
        self.home = tempfile.mkdtemp(prefix="mikai-exec-test-")
        os.environ["HOME"] = self.home
        os.environ["MIKAI_BRAIN_ROOT"] = str(Path(self.home) / "brain")

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

        # Belt and braces: no test may spawn a real subprocess or LLM call.
        self.subproc = mock.patch.object(
            core.subprocess, "run", return_value=_proc()).start()
        self.chat = mock.patch.object(
            core.mikai_llm, "chat", return_value=json.dumps(PROPOSAL)).start()
        self.confirm_three = mock.patch.object(
            core.dialogs, "confirm_three", return_value="Cancel").start()
        self.prompt_text = mock.patch.object(
            core.dialogs, "prompt_text", return_value=None).start()
        mock.patch.object(core.dialogs, "notify").start()
        mock.patch.object(core.shutil, "which",
                          return_value="/fake/claude").start()
        self.addCleanup(mock.patch.stopall)

    def tearDown(self) -> None:
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.home, ignore_errors=True)
        importlib.reload(self.brain)
        importlib.reload(self.threads)
        importlib.reload(self.ledger)

    # ── helpers ──────────────────────────────────────────────────────────

    def seed_thread(self, slug: str = "proposal-timing") -> Path:
        path = self.brain.THREADS_DIR / f"{slug}.md"
        path.write_text(
            f"---\nslug: {slug}\ntitle: {slug.replace('-', ' ')}\n"
            f"state: acting\nlast_activity: 2026-08-01\n---\n\n"
            f"## Log\n- 2026-08-01 opened\n")
        return path

    def run_exec(self, slug: str, action_type: str, dry_run: bool = False) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = core.execute(slug, action_type, dry_run=dry_run)
        return rc, out.getvalue()

    def log_lines(self, slug: str) -> list[str]:
        return self.threads.parse_thread(
            self.brain.THREADS_DIR / f"{slug}.md").log_lines

    def claude_calls(self) -> list[mock.call]:
        return [c for c in self.subproc.call_args_list
                if c.args and c.args[0] and c.args[0][0] == "claude"]

    def pbcopy_calls(self) -> list[mock.call]:
        return [c for c in self.subproc.call_args_list
                if c.args and c.args[0] == ["pbcopy"]]


class TestGuards(ExecTestCase):

    def test_invalid_action_type_raises(self) -> None:
        self.seed_thread()
        with self.assertRaises(ValueError):
            core.execute("proposal-timing", "teleport")
        self.chat.assert_not_called()
        self.subproc.assert_not_called()

    def test_browse_prints_skip_and_exits_zero(self) -> None:
        rc, out = self.run_exec("proposal-timing", "browse")
        self.assertEqual(rc, 0)
        self.assertIn("Playwright MCP", out)
        self.assertIn("claude mcp install playwright", out)
        self.chat.assert_not_called()
        self.subproc.assert_not_called()

    def test_dry_run_no_subprocess_no_dialog_no_writes(self) -> None:
        self.seed_thread()
        rc, out = self.run_exec("proposal-timing", "email", dry_run=True)
        self.assertEqual(rc, 0)
        self.chat.assert_called_once()          # proposal only
        self.subproc.assert_not_called()        # no claude, no pbcopy
        self.confirm_three.assert_not_called()  # no dialog
        self.assertIn(PROPOSAL["intent"], out)
        self.assertEqual(self.ledger.read_runs(), [])
        self.assertEqual(self.ledger.read_events(), [])
        self.assertEqual(self.log_lines("proposal-timing"),
                         ["- 2026-08-01 opened"])


class TestCancel(ExecTestCase):

    def test_cancel_logs_dismissal_not_thread(self) -> None:
        self.seed_thread()
        self.confirm_three.return_value = "Cancel"
        rc, _ = self.run_exec("proposal-timing", "email")
        self.assertEqual(rc, 0)
        events = self.ledger.read_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, "exec_dismissed")
        self.assertEqual(events[0].thread, "proposal-timing")
        self.assertEqual(events[0].note, PROPOSAL["intent"])
        self.assertEqual(self.ledger.read_runs(), [])          # no run row
        self.assertEqual(self.log_lines("proposal-timing"),    # no log line
                         ["- 2026-08-01 opened"])
        self.subproc.assert_not_called()                       # nothing ran


class TestExecute(ExecTestCase):

    def test_execute_writes_ledger_run_and_thread_log(self) -> None:
        self.seed_thread()
        self.confirm_three.return_value = "Execute"
        rc, _ = self.run_exec("proposal-timing", "shell")
        self.assertEqual(rc, 0)
        runs = self.ledger.read_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["mode"], "exec")
        self.assertEqual(runs[0]["did"], f"shell: {PROPOSAL['intent']}")
        self.assertEqual(runs[0]["threads_touched"], ["proposal-timing"])
        lines = self.log_lines("proposal-timing")
        self.assertEqual(len(lines), 2)
        self.assertIn(f"[exec:shell] {PROPOSAL['intent']}", lines[1])
        # shell channel: claude scoped to Bash+Read, prompt via stdin
        calls = self.claude_calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[0],
                         ["claude", "-p", "--allowedTools", "Bash,Read"])
        self.assertEqual(calls[0].kwargs["input"],
                         PROPOSAL["prompt_to_claude_for_execution"])

    def test_email_scopes_to_gmail_mcp_only(self) -> None:
        self.seed_thread()
        self.confirm_three.return_value = "Execute"
        rc, _ = self.run_exec("proposal-timing", "email")
        self.assertEqual(rc, 0)
        calls = self.claude_calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[0],
                         ["claude", "-p", "--allowedTools", "mcp__claude_ai_Gmail"])

    def test_message_fallback_copies_to_clipboard(self) -> None:
        self.seed_thread()
        self.confirm_three.return_value = "Execute"
        rc, out = self.run_exec("proposal-timing", "message")
        self.assertEqual(rc, 0)
        self.assertEqual(self.claude_calls(), [])   # never touches claude
        pb = self.pbcopy_calls()
        self.assertEqual(len(pb), 1)
        self.assertEqual(pb[0].kwargs["input"],
                         PROPOSAL["prompt_to_claude_for_execution"])
        self.assertIn("clipboard", out)
        # write-back still applies — message send is a real action
        runs = self.ledger.read_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["did"], f"message: {PROPOSAL['intent']}")
        self.assertIn(f"[exec:message] {PROPOSAL['intent']}",
                      self.log_lines("proposal-timing")[1])

    def test_edit_path_executes_edited_payload(self) -> None:
        self.seed_thread()
        self.confirm_three.return_value = "Edit"
        self.prompt_text.return_value = "edited: shorter, warmer nudge"
        rc, _ = self.run_exec("proposal-timing", "message")
        self.assertEqual(rc, 0)
        pb = self.pbcopy_calls()
        self.assertEqual(len(pb), 1)
        self.assertEqual(pb[0].kwargs["input"], "edited: shorter, warmer nudge")
        self.assertEqual(len(self.ledger.read_runs()), 1)

    def test_edit_then_cancel_is_a_dismissal(self) -> None:
        self.seed_thread()
        self.confirm_three.return_value = "Edit"
        self.prompt_text.return_value = None       # cancelled the edit dialog
        rc, _ = self.run_exec("proposal-timing", "message")
        self.assertEqual(rc, 0)
        self.assertEqual(self.subproc.call_count, 0)
        events = self.ledger.read_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, "exec_dismissed")
        self.assertEqual(self.ledger.read_runs(), [])


if __name__ == "__main__":
    unittest.main()
