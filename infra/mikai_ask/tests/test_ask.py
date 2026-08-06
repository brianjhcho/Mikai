"""Tests for mikai_ask — composer, retrieval, trimming, logging.

Same pattern as infra/mikai_brain/tests/test_end_to_end.py: every test
runs against a throwaway HOME with a temp brain + wiki tree; the brain
package and its submodules are reloaded so their import-time path
constants rebind. All LLM calls are patched — nothing here may reach
the network or spawn `claude`.
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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


def _iso(days_ago: float = 0) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(days=days_ago)
    ).isoformat(timespec="seconds")


class AskTestCase(unittest.TestCase):
    """Base: temp HOME with brain + wiki fixtures, reloaded modules."""

    def setUp(self) -> None:
        self._orig_home = os.environ.get("HOME")
        self.home = tempfile.mkdtemp(prefix="mikai-ask-test-")
        os.environ["HOME"] = self.home

        import infra.mikai_brain as brain_pkg
        importlib.reload(brain_pkg)
        from infra.mikai_brain import ledger, threads
        importlib.reload(threads)
        importlib.reload(ledger)
        import infra.mikai_ask.core as core
        importlib.reload(core)

        self.brain = brain_pkg
        self.threads = threads
        self.ledger = ledger
        self.core = core

        self.assertTrue(str(brain_pkg.BRAIN_ROOT).startswith(self.home),
                        "brain root escaped the temp HOME — refusing to run")

        for d in (brain_pkg.THREADS_DIR, brain_pkg.ENTITIES_DIR,
                  brain_pkg.STATE_DIR):
            d.mkdir(parents=True, exist_ok=True)
        brain_pkg.BRAIN_MD.write_text(
            "# Brian's brain\n\nIntro.\n\n"
            "## Current priorities\n\nPRIORITIES-MARKER body.\n\n"
            "## Departments\n\nlove, mikai\n"
        )
        (brain_pkg.BRAIN_ROOT / "PROFILE.md").write_text(
            "# PROFILE\n\nPROFILE-MARKER identity paragraph.\n"
        )

    def tearDown(self) -> None:
        if self._orig_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._orig_home
        shutil.rmtree(self.home, ignore_errors=True)
        importlib.reload(self.brain)
        importlib.reload(self.threads)
        importlib.reload(self.ledger)
        importlib.reload(self.core)

    # ── fixtures ─────────────────────────────────────────────────────────

    def write_wiki(self, sections) -> None:
        """sections: iterable of (ts, source, name, body)."""
        wiki_dir = Path(self.home) / ".mikai" / "wiki"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        text = "".join(
            f"### {ts} — {source} — {name}\n\n{body}\n\n"
            for ts, source, name, body in sections
        )
        (wiki_dir / "wiki.md").write_text(text)

    def write_entity(self, slug: str, body: str) -> None:
        (self.brain.ENTITIES_DIR / f"{slug}.md").write_text(body)

    def write_thread(self, slug: str, *, state: str = "acting",
                     body_extra: str = "", log_line: str = "opened") -> None:
        fm = (
            f"slug: {slug}\ntitle: {slug.replace('-', ' ')}\n"
            f"state: {state}\nstate_since: 2026-08-01\n"
            f"last_activity: 2026-08-05\nnext_step: \"do the thing\"\n"
            f"entities: []\ndepartment: mikai"
        )
        (self.brain.THREADS_DIR / f"{slug}.md").write_text(
            f"---\n{fm}\n---\n\n{body_extra}\n## Log\n- 2026-08-05 {log_line}\n"
        )

    def progress_rows(self) -> list[dict]:
        log = self.brain.PROGRESS_LOG
        if not log.exists():
            return []
        return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]

    def fake_hit(self, name: str, snippet: str) -> dict:
        return {"slug": f"2026-08-05T00:00:00+00:00|test|{name}",
                "header_ts": "2026-08-05T00:00:00+00:00", "source": "test",
                "name": name, "snippet": snippet, "rank": -1.0}


class TestAsk(AskTestCase):

    def test_ask_dry_run_returns_prompt_without_llm_call(self):
        with mock.patch("infra.mikai_llm.chat",
                        side_effect=AssertionError("LLM called on dry-run")):
            with contextlib.redirect_stderr(io.StringIO()):
                prompt = self.core.ask("what about the monstera?", dry_run=True)
        self.assertIn("what about the monstera?", prompt)
        self.assertIn("PROFILE-MARKER", prompt)
        self.assertEqual(self.progress_rows(), [],
                         "dry-run must not log to progress.jsonl")

    def test_ask_composes_profile_priorities_fts_entities_threads_in_order(self):
        self.write_wiki([
            (_iso(2), "apple-notes: research", "blackforest research",
             "FTS-MARKER blackforest labs flux notes."),
        ])
        self.write_entity("monstera", "ENTITY-MARKER the loft monstera.")
        self.write_thread("some-build", log_line="THREAD-LOG-MARKER")
        with mock.patch("infra.mikai_llm.chat",
                        side_effect=AssertionError("no LLM in compose test")):
            with contextlib.redirect_stderr(io.StringIO()):
                prompt = self.core.ask("blackforest monstera plans", dry_run=True)
        order = [prompt.index("PROFILE-MARKER"),
                 prompt.index("PRIORITIES-MARKER"),
                 prompt.index("FTS-MARKER"),
                 prompt.index("ENTITY-MARKER"),
                 prompt.index("THREAD-LOG-MARKER"),
                 prompt.index("## Question")]
        self.assertEqual(order, sorted(order),
                         "sections out of order: profile → priorities → "
                         "fts → entities → threads → question")

    def test_ask_respects_prompt_size_cap(self):
        hits = [self.fake_hit(f"hit-{i}", f"FTSBLOCK-{i} " + "x" * 150)
                for i in range(8)]
        self.write_entity("monstera", "ENTITY-KEEP " + "e" * 400)
        self.write_thread("some-build", log_line="THREAD-KEEP")
        base_len = 0
        with mock.patch.object(self.core, "_fts_hits", return_value=hits):
            with contextlib.redirect_stderr(io.StringIO()):
                full, _ = self.core.compose("monstera plans")
                base_len = len(full)
                # Cap below the full prompt but with room for entities +
                # threads once FTS goes: FTS must be dropped first.
                cap = base_len - 300
                with mock.patch.object(self.core, "PROMPT_CHAR_CAP", cap):
                    prompt, stats = self.core.compose("monstera plans")
        self.assertLessEqual(len(prompt), cap)
        self.assertGreater(stats["trimmed"]["fts"], 0, "FTS not trimmed first")
        self.assertEqual(stats["trimmed"]["entities"], 0)
        self.assertEqual(stats["trimmed"]["threads"], 0)
        self.assertIn("ENTITY-KEEP", prompt)
        self.assertIn("THREAD-KEEP", prompt)
        self.assertIn("PROFILE-MARKER", prompt)
        self.assertIn("PRIORITIES-MARKER", prompt)

    def test_ask_size_cap_trims_entities_before_threads(self):
        hits = [self.fake_hit("hit-0", "small fts")]
        self.write_entity("monstera", "ENTITY-BIG " + "e" * 5000)
        self.write_thread("some-build", log_line="THREAD-KEEP")
        with mock.patch.object(self.core, "_fts_hits", return_value=hits):
            with mock.patch.object(self.core, "PROMPT_CHAR_CAP", 2500):
                prompt, stats = self.core.compose("monstera plans")
        self.assertLessEqual(len(prompt), 2500)
        self.assertEqual(stats["trimmed"]["entities"], 1,
                         "oversized entity should be trimmed")
        self.assertEqual(stats["trimmed"]["threads"], 0)
        self.assertIn("THREAD-KEEP", prompt)
        self.assertIn("PROFILE-MARKER", prompt)
        self.assertIn("PRIORITIES-MARKER", prompt)

    def test_ask_falls_back_to_windowed_read_when_fts_thin(self):
        self.write_wiki([
            (_iso(40), "apple-notes: old", "stale section", "too old to fill"),
            (_iso(3), "apple-notes: recent", "recent-one", "WINDOW-A body"),
            (_iso(1), "apple-notes: recent", "recent-two", "WINDOW-B body"),
        ])
        one_hit = [self.fake_hit("solo", "the only fts hit")]
        with mock.patch.object(self.core, "_fts_hits", return_value=one_hit):
            prompt, stats = self.core.compose("anything at all")
        self.assertIn("(recent-window fill)", prompt)
        self.assertIn("WINDOW-A", prompt)
        self.assertIn("WINDOW-B", prompt)
        self.assertNotIn("too old to fill", prompt)
        self.assertEqual(stats["fallback_fill"], 2)

    def test_ask_pulls_entities_matching_query_slug(self):
        self.write_entity("germaine", "GERMAINE-BODY partner facts here.")
        self.write_entity("monstera", "MONSTERA-BODY plant facts here.")
        with mock.patch.object(self.core, "_fts_hits", return_value=[]):
            prompt, stats = self.core.compose("how is Germaine doing?")
        self.assertIn("GERMAINE-BODY", prompt)
        self.assertNotIn("MONSTERA-BODY", prompt)
        self.assertEqual(stats["entities"], ["germaine"])

    def test_ask_pulls_entities_matching_top_fts_hit(self):
        self.write_entity("germaine", "GERMAINE-BODY partner facts here.")
        hits = [self.fake_hit("venue notes", "checked germaine availability")]
        with mock.patch.object(self.core, "_fts_hits", return_value=hits):
            prompt, _ = self.core.compose("venue shortlist status")
        self.assertIn("GERMAINE-BODY", prompt)

    def test_ask_active_threads_only_frontmatter(self):
        self.write_thread("active-one", state="acting",
                          body_extra="## Context\nSECRET-THREAD-BODY\n",
                          log_line="FIRST-LOG-LINE")
        self.write_thread("dormant-one", state="exploring",
                          log_line="DORMANT-LOG")
        with mock.patch.object(self.core, "_fts_hits", return_value=[]):
            prompt, stats = self.core.compose("what am I in the middle of?")
        self.assertIn("slug: active-one", prompt)
        self.assertIn("FIRST-LOG-LINE", prompt)
        self.assertNotIn("SECRET-THREAD-BODY", prompt,
                         "thread body leaked — only frontmatter + first log allowed")
        self.assertNotIn("DORMANT-LOG", prompt,
                         "non-active thread included")
        self.assertEqual(stats["threads"], 1)

    def test_ask_logs_run_to_progress_jsonl(self):
        with mock.patch("infra.mikai_llm.chat", return_value="the answer"):
            with mock.patch.object(self.core, "_fts_hits", return_value=[]):
                answer = self.core.ask("log me please")
        self.assertEqual(answer, "the answer")
        rows = self.progress_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["mode"], "ask")
        self.assertIn("log me please", rows[0]["did"])
        self.assertIn("prompt_chars", rows[0]["extra"])

    def test_ask_stdin_input_works(self):
        from infra.mikai_ask import main as ask_main
        with mock.patch("infra.mikai_llm.chat", return_value="STDIN-ANSWER"):
            with mock.patch.object(self.core, "_fts_hits", return_value=[]):
                stdout = io.StringIO()
                with mock.patch.object(sys, "stdin",
                                       io.StringIO("what about monstera?")):
                    with contextlib.redirect_stdout(stdout):
                        rc = ask_main.main([])
        self.assertEqual(rc, 0)
        self.assertIn("STDIN-ANSWER", stdout.getvalue())
        rows = self.progress_rows()
        self.assertEqual(len(rows), 1)
        self.assertIn("what about monstera?", rows[0]["did"])


if __name__ == "__main__":
    unittest.main()
