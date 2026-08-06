"""Tests for the latent-thread detector.

Same isolation pattern as test_hydrator.py: HOME repointed to a temp
dir, brain package + modules reloaded so every path constant rebinds.
~/.mikai is never touched. WikiFTS + mikai_llm.chat are both patched;
no LLM call and no wiki I/O can escape.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock


def _iso(n_days_ago: int) -> str:
    return (date.today() - timedelta(days=n_days_ago)).isoformat()


# Ontology exercises each filter path:
#   dry-eyes       — valid (accepted)
#   plant-care     — valid (accepted)
#   germaine       — primary of existing thread proposal-timing → skip
#   china          — stale last_seen (200 days ago) → skip
#   perl           — low mentions (5 < 30) → skip
#   ancient-place  — abstract type (concept) → skip
#   already-here   — proposal already in inbox → skip
def _fixture_ontology() -> str:
    rows = [
        f"| dry-eyes | thing | 528 | 2026-01-01 | {_iso(2)} | apple-notes, claude-thread |",
        f"| plant-care | thing | 420 | 2026-02-01 | {_iso(5)} | claude-thread, gmail |",
        f"| germaine | person | 84 | 2017-10-18 | {_iso(1)} | apple-notes |",
        f"| china | place | 300 | 2017-10-18 | {_iso(200)} | apple-notes |",
        f"| perl | thing | 5 | 2026-03-01 | {_iso(10)} | claude-code |",
        f"| some-concept | concept | 100 | 2026-03-01 | {_iso(10)} | claude-code |",
        f"| already-here | thing | 200 | 2026-03-01 | {_iso(3)} | claude-code |",
    ]
    return (
        "# Wiki Ontology\n\n"
        "| entity | type | mentions | first_seen | last_seen | sources |\n"
        "|---|---|---|---|---|---|\n"
        + "\n".join(rows) + "\n"
    )


class LatentThreadsTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self._orig_home = os.environ.get("HOME")
        self._orig_wiki = os.environ.pop("MIKAI_WIKI_ONTOLOGY", None)
        self._orig_root = os.environ.pop("MIKAI_BRAIN_ROOT", None)
        self.home = tempfile.mkdtemp(prefix="mikai-latent-test-")
        os.environ["HOME"] = self.home

        import infra.mikai_brain as brain_pkg
        importlib.reload(brain_pkg)
        from infra.mikai_brain import (
            hydrator, latent_threads, ledger, threads, triage,
        )
        for m in (threads, ledger, triage, hydrator, latent_threads):
            importlib.reload(m)
        self.brain = brain_pkg
        self.lt = latent_threads
        self.threads = threads

        # Seed the temp brain tree.
        for d in (brain_pkg.THREADS_DIR, brain_pkg.INBOX_DIR,
                  brain_pkg.INBOX_PROCESSED, brain_pkg.STATE_DIR):
            d.mkdir(parents=True, exist_ok=True)

        # Fixture ontology under $HOME/.mikai/wiki/.
        self.ontology = Path(self.home) / ".mikai" / "wiki" / "wiki-ontology.md"
        self.ontology.parent.mkdir(parents=True)
        self.ontology.write_text(_fixture_ontology())

        # Existing thread with germaine as primary entity.
        (brain_pkg.THREADS_DIR / "proposal-timing.md").write_text(
            "---\n"
            "slug: proposal-timing\n"
            "title: Proposal timing\n"
            "state: exploring\n"
            "state_since: 2026-06-30\n"
            "last_activity: 2026-07-20\n"
            'next_step: "narrow venue"\n'
            "entities: [germaine]\n"
            "department: love\n"
            "---\n\n"
            "## Log\n- 2026-07-20 opened\n"
        )

        # Pre-existing proposal to test idempotency filter.
        (brain_pkg.INBOX_DIR / "proposed-thread-already-here.md").write_text(
            "---\nproposal_kind: thread\nslug: already-here\n---\nprior\n"
        )

    def tearDown(self) -> None:
        if self._orig_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._orig_home
        if self._orig_wiki is not None:
            os.environ["MIKAI_WIKI_ONTOLOGY"] = self._orig_wiki
        if self._orig_root is not None:
            os.environ["MIKAI_BRAIN_ROOT"] = self._orig_root
        shutil.rmtree(self.home, ignore_errors=True)

    def _proposals(self) -> list[Path]:
        return sorted(self.brain.INBOX_DIR.glob("proposed-thread-*.md"))

    # ── selection (no LLM) ─────────────────────────────────────────────

    def test_pre_llm_filters_leave_only_valid_candidates(self):
        # Patch _fts_search so it doesn't try to touch a real wiki (not
        # strictly needed here — no LLM path — but keeps intent clear).
        with mock.patch.object(self.lt, "_fts_search", return_value=[]):
            candidates = self.lt.select_candidates()
        slugs = [e.slug for e in candidates]
        # dry-eyes + plant-care survive; everything else is filtered.
        self.assertEqual(set(slugs), {"dry-eyes", "plant-care"})
        # And the sort is mentions-desc.
        self.assertEqual(slugs, ["dry-eyes", "plant-care"])

    def test_limit_respected(self):
        with mock.patch.object(self.lt, "_fts_search", return_value=[]):
            candidates = self.lt.select_candidates(limit=1)
        self.assertEqual([e.slug for e in candidates], ["dry-eyes"])

    # ── classify + write path ──────────────────────────────────────────

    def _accept_verdict(self, slug: str) -> str:
        return json.dumps({
            "is_thread_shaped": True,
            "why": f"{slug} shows ongoing decision-making",
            "state": "evaluating",
            "next_step": f"decide how to handle {slug}",
            "department": "body",
            "confidence": 0.85,
            "title": f"{slug.title()} — active management",
        })

    def _reject_verdict(self, slug: str) -> str:
        return json.dumps({
            "is_thread_shaped": False,
            "why": "reads as reference material, no pending action",
            "state": "exploring",
            "next_step": "",
            "department": "misc",
            "confidence": 0.3,
            "title": "",
        })

    def _low_confidence_verdict(self, slug: str) -> str:
        return json.dumps({
            "is_thread_shaped": True,
            "why": "maybe thread-shaped, unclear",
            "state": "exploring",
            "next_step": "think about it",
            "department": "misc",
            "confidence": 0.45,
            "title": f"{slug} — tentative",
        })

    def test_only_valid_candidates_reach_the_llm(self):
        """The pre-LLM filter is the whole point of the cost gate —
        germaine / china / perl / some-concept / already-here must never
        trigger a chat() call."""
        calls: list[str] = []

        def fake_chat(prompt, tier="interactive", **kw):
            # Extract the slug line from the prompt so we can assert.
            for line in prompt.splitlines():
                if line.startswith("Candidate entity:"):
                    calls.append(line.split(":", 1)[1].strip())
                    break
            return self._accept_verdict(calls[-1])

        with mock.patch.object(self.lt, "_fts_search", return_value=[]), \
             mock.patch("infra.mikai_llm.chat", side_effect=fake_chat):
            stats = self.lt.run(verbose=False)

        self.assertEqual(sorted(calls), ["dry-eyes", "plant-care"])
        self.assertEqual(stats["accepted"], 2)
        self.assertEqual(stats["rejected"], 0)

    def test_llm_rejection_skips_proposal(self):
        with mock.patch.object(self.lt, "_fts_search", return_value=[]), \
             mock.patch("infra.mikai_llm.chat",
                        side_effect=lambda p, **kw: self._reject_verdict("x")):
            stats = self.lt.run(verbose=False)
        self.assertEqual(stats["accepted"], 0)
        self.assertEqual(stats["rejected"], 2)
        # Only the pre-existing sentinel remains.
        self.assertEqual([p.name for p in self._proposals()],
                         ["proposed-thread-already-here.md"])

    def test_low_confidence_skips_proposal(self):
        with mock.patch.object(self.lt, "_fts_search", return_value=[]), \
             mock.patch("infra.mikai_llm.chat",
                        side_effect=lambda p, **kw: self._low_confidence_verdict("x")):
            stats = self.lt.run(verbose=False)
        self.assertEqual(stats["accepted"], 0)
        self.assertEqual(stats["rejected"], 2)

    def test_accepted_candidate_writes_well_formed_proposal(self):
        snippets = [
            {"header_ts": "2026-07-01T00:00:00+00:00",
             "name": "morning notes", "source": "apple-notes",
             "snippet": "eye drops running low, order more"},
            {"header_ts": "2026-06-30T00:00:00+00:00",
             "name": "claude session", "source": "claude-thread",
             "snippet": "researched dry-eye protocols"},
        ]
        with mock.patch.object(self.lt, "_fts_search", return_value=snippets), \
             mock.patch("infra.mikai_llm.chat",
                        side_effect=lambda p, **kw: self._accept_verdict("dry-eyes")):
            stats = self.lt.run(limit=1, verbose=False)

        self.assertEqual(stats["accepted"], 1)
        self.assertEqual(stats["proposed"], ["dry-eyes"])

        proposal = self.brain.INBOX_DIR / "proposed-thread-dry-eyes.md"
        self.assertTrue(proposal.exists())
        text = proposal.read_text()
        # Frontmatter shape.
        self.assertIn("proposal_kind: thread", text)
        self.assertIn("slug: dry-eyes", text)
        self.assertIn("state: evaluating", text)
        self.assertIn("department: body", text)
        self.assertIn("confidence: 0.85", text)
        self.assertIn("entities: [dry-eyes]", text)
        self.assertIn("mentions: 528", text)
        # Body carries evidence.
        self.assertIn("# Proposed thread:", text)
        self.assertIn("## Evidence", text)
        self.assertIn("eye drops running low", text)
        # Ledger row written.
        runs = self.brain.ledger.read_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["mode"], "latent-threads")
        self.assertIn("proposed 1 threads", runs[0]["did"])

    def test_second_run_does_not_repropose(self):
        """After a proposal lands, the idempotency filter must skip it
        on the next pass — no second LLM call either."""
        call_count = {"n": 0}

        def fake_chat(prompt, **kw):
            call_count["n"] += 1
            return self._accept_verdict("dry-eyes")

        with mock.patch.object(self.lt, "_fts_search", return_value=[]), \
             mock.patch("infra.mikai_llm.chat", side_effect=fake_chat):
            first = self.lt.run(limit=1, verbose=False)
            second = self.lt.run(limit=1, verbose=False)

        self.assertEqual(first["accepted"], 1)
        self.assertEqual(first["proposed"], ["dry-eyes"])
        # Second run: dry-eyes is filtered before classify(), plant-care
        # takes its place under limit=1 → one new LLM call, one accept.
        self.assertEqual(call_count["n"], 2)
        self.assertEqual(second["proposed"], ["plant-care"])
        self.assertEqual(sorted(p.name for p in self._proposals()), [
            "proposed-thread-already-here.md",
            "proposed-thread-dry-eyes.md",
            "proposed-thread-plant-care.md",
        ])

    def test_unparseable_llm_response_rejects_gracefully(self):
        with mock.patch.object(self.lt, "_fts_search", return_value=[]), \
             mock.patch("infra.mikai_llm.chat",
                        side_effect=lambda p, **kw: "Sure! Here's my answer: nothing."):
            stats = self.lt.run(verbose=False)
        self.assertEqual(stats["accepted"], 0)
        self.assertEqual(stats["unparseable"], 2)
        self.assertEqual(stats["rejected"], 2)
        # No proposal files apart from the pre-existing sentinel.
        self.assertEqual([p.name for p in self._proposals()],
                         ["proposed-thread-already-here.md"])

    def test_dry_run_writes_nothing(self):
        with mock.patch.object(self.lt, "_fts_search", return_value=[]), \
             mock.patch("infra.mikai_llm.chat",
                        side_effect=lambda p, **kw: self._accept_verdict("dry-eyes")):
            stats = self.lt.run(dry_run=True, verbose=False)
        self.assertEqual(stats["accepted"], 2)
        # Nothing landed on disk.
        self.assertEqual([p.name for p in self._proposals()],
                         ["proposed-thread-already-here.md"])
        # No ledger row either.
        self.assertEqual(self.brain.ledger.read_runs(), [])


if __name__ == "__main__":
    unittest.main()
