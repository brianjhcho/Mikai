"""Tests for the Surface Engine's file-based context and evidence validation.

Temp dirs only — no network, no LLM, no real brain or wiki.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import brain_context as bc  # noqa: E402
import mikai_decide as md  # noqa: E402

THREAD = """---
slug: proposal-timing
title: Proposal — timing, venue, ring
state: exploring
state_since: 2026-06-30
last_activity: 2026-10-01
next_step: "Research venue shortlist (2-3 candidates)"
entities: [germaine, kenya-trip]
department: love
---

## Context

No external forcing function.
"""

BLOCK_LIST_THREAD = """---
slug: monstera-moss-pole
title: Monstera moss pole
state: Stalled
last_activity: 2026-08-05
entities:
  - monstera
---
body
"""

CLOSED_THREAD = """---
slug: old-thing
title: Old thing
state: completed
last_activity: 2025-01-01
---
"""


class _Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.brain = root / "brain"
        self.wiki = root / "wiki-vault"
        (self.brain / "threads").mkdir(parents=True)
        for kind in ("concepts", "entities", "wisdom"):
            (self.wiki / "wiki" / kind).mkdir(parents=True)
        (self.brain / "threads" / "proposal-timing.md").write_text(THREAD)
        (self.brain / "threads" / "monstera-moss-pole.md").write_text(BLOCK_LIST_THREAD)
        (self.brain / "threads" / "old-thing.md").write_text(CLOSED_THREAD)
        (self.brain / "threads" / "proposal-timing.md.bak-old").write_text(THREAD)
        (self.brain / "BRAIN.md").write_text("# BRAIN\nIdentity")
        (self.wiki / "wiki" / "entities" / "germaine.md").write_text(
            "---\ntitle: Germaine\n---\nGermaine is Brian's partner.\n")
        (self.wiki / "wiki" / "concepts" / "kenya-trip.md").write_text(
            "---\ntitle: Kenya trip\nretired_to: kenya-travel\n---\nstub\n")
        self.env = mock.patch.dict(os.environ, {
            "MIKAI_BRAIN_ROOT": str(self.brain),
            "MIKAI_WIKI_ROOT": str(self.wiki),
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self._tmp.cleanup()


class ThreadReaderTests(_Fixture):
    def test_reads_frontmatter_and_body(self):
        threads = {t.slug: t for t in bc.load_threads()}
        t = threads["proposal-timing"]
        self.assertEqual(t.state, "exploring")
        self.assertEqual(t.next_step, "Research venue shortlist (2-3 candidates)")
        self.assertEqual(t.entities, ["germaine", "kenya-trip"])
        self.assertEqual(t.department, "love")
        self.assertIn("No external forcing function", t.body)

    def test_ignores_backup_files(self):
        self.assertEqual(len(bc.load_threads()), 3)

    def test_block_list_and_state_case(self):
        t = {t.slug: t for t in bc.load_threads()}["monstera-moss-pole"]
        self.assertEqual(t.entities, ["monstera"])
        self.assertEqual(t.state, "stalled")

    def test_rank_puts_open_quietest_first_and_closed_last(self):
        ranked = bc.rank_threads(bc.load_threads(), today=date(2026, 10, 13))
        self.assertEqual([t.slug for t in ranked],
                         ["monstera-moss-pole", "proposal-timing", "old-thing"])

    def test_missing_dir_returns_empty(self):
        self.assertEqual(bc.load_threads(Path(self._tmp.name) / "nope"), [])

    def test_wiki_snippets_follow_entities_and_skip_retired(self):
        snippets = bc.load_wiki_snippets(bc.load_threads())
        self.assertEqual([s["slug"] for s in snippets], ["entities/germaine"])
        self.assertIn("partner", snippets[0]["snippet"])


class CitationTests(_Fixture):
    def test_thread_and_wiki_slugs_exist(self):
        for cite in ("proposal-timing", "threads/proposal-timing", "germaine",
                     "entities/germaine", "[entities/germaine]"):
            self.assertTrue(bc.citation_exists(cite), cite)

    def test_unknown_or_unsafe_slugs_rejected(self):
        for cite in ("made-up", "entities/nobody", "../../etc/passwd",
                     "concepts/../threads/x", "", "1a2b3c4d"):
            self.assertFalse(bc.citation_exists(cite), cite)


def _notif(**over):
    n = {
        "title": "Venue shortlist never started",
        "body": "Pick 2-3 candidates tonight.",
        "priority": "active",
        "decision_point": "Which venues make the shortlist?",
        "evidence": ["proposal-timing", "entities/germaine"],
        "thread_slug": "proposal-timing",
    }
    n.update(over)
    return n


class ValidateDecisionTests(_Fixture):
    ctx = {"needs_ranked": [{"slug": "msp-renewal"}]}

    def test_valid_notification_passes(self):
        ok, msg = md.validate_decision({"notifications": [_notif()]}, self.ctx)
        self.assertTrue(ok, msg)

    def test_silence_needs_reason(self):
        self.assertFalse(md.validate_decision({"notifications": []}, self.ctx)[0])
        self.assertTrue(md.validate_decision(
            {"notifications": [], "silent_reason": "nothing stalled"}, self.ctx)[0])

    def test_invented_citation_fails(self):
        ok, msg = md.validate_decision(
            {"notifications": [_notif(evidence=["made-up-thread"])]}, self.ctx)
        self.assertFalse(ok)
        self.assertIn("made-up-thread", msg)

    def test_no_citation_fails(self):
        ok, _ = md.validate_decision({"notifications": [_notif(evidence=[])]}, self.ctx)
        self.assertFalse(ok)

    def test_unknown_thread_slug_fails(self):
        ok, _ = md.validate_decision(
            {"notifications": [_notif(thread_slug="ghost")]}, self.ctx)
        self.assertFalse(ok)

    def test_needs_slug_accepted_only_from_registry(self):
        ok, msg = md.validate_decision({"notifications": [_notif(
            thread_slug=None, needs_slug="msp-renewal", evidence=["msp-renewal"])]}, self.ctx)
        self.assertTrue(ok, msg)
        ok, _ = md.validate_decision({"notifications": [_notif(
            thread_slug=None, needs_slug="invented", evidence=["invented"])]}, self.ctx)
        self.assertFalse(ok)

    def test_legacy_field_names_still_accepted(self):
        n = _notif()
        n["evidence_edge_uuids"] = n.pop("evidence")
        n["wiki_thread_slug"] = n.pop("thread_slug")
        ok, msg = md.validate_decision({"notifications": [n]}, self.ctx)
        self.assertTrue(ok, msg)

    def test_duplicate_thread_rejected_and_slate_capped(self):
        self.assertFalse(md.validate_decision(
            {"notifications": [_notif(), _notif()]}, self.ctx)[0])
        too_many = [_notif(thread_slug=None) for _ in range(md.SLATE_MAX + 1)]
        self.assertFalse(md.validate_decision({"notifications": too_many}, self.ctx)[0])


class PromptTests(_Fixture):
    def test_prompt_builds_from_files_without_graph(self):
        ctx = {
            "threads": bc.rank_threads(bc.load_threads()),
            "brain_docs": bc.load_brain_docs(),
            "wiki_snippets": bc.load_wiki_snippets(bc.load_threads()),
            "realtime": [],
            "needs_registry": None,
            "needs_ranked": [],
        }
        prompt = md.build_prompt(ctx, [])
        self.assertIn("[proposal-timing] state=exploring", prompt)
        self.assertIn("[entities/germaine]", prompt)
        self.assertIn("Default is SILENCE", prompt)
        self.assertNotIn("GRAPH STATE", prompt)
        self.assertNotIn("MUST include at least one item", prompt)


if __name__ == "__main__":
    unittest.main()
