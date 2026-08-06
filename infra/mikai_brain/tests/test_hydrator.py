"""Tests for the L3 → L4 hydrator (wiki-ontology → inbox entity proposals)
and the triage entity-proposal extension.

Same isolation pattern as test_end_to_end.py: repoint HOME at a temp dir
and reload the package so every path constant rebinds. ~/.mikai is never
touched; no LLM calls are possible on these code paths.
"""

from __future__ import annotations

import importlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path

FIXTURE_ONTOLOGY = """\
# Wiki Ontology — as of 2026-08-06

_Bootstrap: extracted from all sections._

| entity | type | mentions | first_seen | last_seen | sources |
|---|---|---|---|---|---|
| germaine | person | 84 | 2017-10-18 | 2026-08-06 | apple-notes, claude-thread |
| noonchi | concept | 50 | 2026-03-19 | 2026-08-06 | claude-code |
| claude-md ⚠ | thing | 42 | 2026-03-19 | 2026-08-05 | apple-notes |
| newco | org | 12 | 2026-01-01 | 2026-08-01 | claude-code, gmail |
| davide | person | 7 | 2026-02-01 | 2026-08-01 | claude-thread |
| rare-thing | thing | 2 | 2026-03-19 | 2026-03-19 | perplexity |

## ⚠ Possibly inferred (name not found verbatim in wiki.md)

Flagged, not stripped — triage manually: `claude-md`

_6 entities kept._
"""


class HydratorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_home = os.environ.get("HOME")
        self._orig_wiki = os.environ.pop("MIKAI_WIKI_ONTOLOGY", None)
        self._orig_root = os.environ.pop("MIKAI_BRAIN_ROOT", None)
        self.home = tempfile.mkdtemp(prefix="mikai-hydrator-test-")
        os.environ["HOME"] = self.home

        import infra.mikai_brain as brain_pkg
        importlib.reload(brain_pkg)
        from infra.mikai_brain import hydrator, ledger, threads, triage
        for module in (threads, ledger, triage, hydrator):
            importlib.reload(module)
        self.brain = brain_pkg
        self.hydrator = hydrator
        self.triage = triage

        # Fixture ontology at $HOME/.mikai/wiki/wiki-ontology.md
        self.ontology = Path(self.home) / ".mikai" / "wiki" / "wiki-ontology.md"
        self.ontology.parent.mkdir(parents=True)
        self.ontology.write_text(FIXTURE_ONTOLOGY)

        # One existing entity (germaine) + ignored variant files
        brain_pkg.ENTITIES_DIR.mkdir(parents=True)
        (brain_pkg.ENTITIES_DIR / "germaine.md").write_text(
            "---\nname: germaine\ntype: person\nstatus: active\nowner_thread: \n---\n"
        )
        (brain_pkg.ENTITIES_DIR / "bethany.md.hallucinated-2026-08-05").write_text("x")
        (brain_pkg.ENTITIES_DIR / "monstera.md.bak-fable-1").write_text("x")

    def tearDown(self) -> None:
        if self._orig_home is not None:
            os.environ["HOME"] = self._orig_home
        if self._orig_wiki is not None:
            os.environ["MIKAI_WIKI_ONTOLOGY"] = self._orig_wiki
        if self._orig_root is not None:
            os.environ["MIKAI_BRAIN_ROOT"] = self._orig_root
        shutil.rmtree(self.home, ignore_errors=True)

    def _proposals(self) -> list[Path]:
        if not self.brain.INBOX_DIR.exists():
            return []
        return sorted(self.brain.INBOX_DIR.glob("proposed-entity-*.md"))

    # ── hydrator ────────────────────────────────────────────────────────

    def test_dry_run_writes_nothing(self) -> None:
        candidates = self.hydrator.run(dry_run=True, verbose=False)
        self.assertEqual([e.slug for e in candidates], ["newco", "davide"])
        self.assertEqual(self._proposals(), [])

    def test_only_valid_candidates_proposed(self) -> None:
        # germaine → existing; claude-md → flagged; noonchi → abstract type;
        # rare-thing → below threshold. Only newco + davide land.
        self.hydrator.run(verbose=False)
        names = [p.name for p in self._proposals()]
        self.assertEqual(
            names, ["proposed-entity-davide.md", "proposed-entity-newco.md"]
        )

    def test_frontmatter_well_formed(self) -> None:
        self.hydrator.run(verbose=False)
        text = (self.brain.INBOX_DIR / "proposed-entity-newco.md").read_text()
        meta = self.triage._entity_proposal_meta(text)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["proposal_kind"], "entity")
        self.assertEqual(meta["slug"], "newco")
        self.assertEqual(meta["type"], "org")
        self.assertEqual(meta["mentions"], "12")
        self.assertEqual(meta["first_seen"], "2026-01-01")
        self.assertEqual(meta["last_seen"], "2026-08-01")
        self.assertIn("claude-code, gmail", meta["sources"])
        self.assertIn("# Proposed entity: newco", text)

    def test_idempotent_second_run(self) -> None:
        self.hydrator.run(verbose=False)
        first = {p.name: p.read_text() for p in self._proposals()}
        second_candidates = self.hydrator.run(verbose=False)
        self.assertEqual(second_candidates, [])
        self.assertEqual({p.name: p.read_text() for p in self._proposals()}, first)

    def test_min_mentions_and_limit(self) -> None:
        # Lower threshold pulls rare-thing in; limit=1 keeps only the top one.
        candidates = self.hydrator.run(
            dry_run=True, min_mentions=1, limit=1, verbose=False
        )
        self.assertEqual([e.slug for e in candidates], ["newco"])

    # ── triage extension ───────────────────────────────────────────────

    def test_triage_holds_proposal_without_accept(self) -> None:
        self.hydrator.run(verbose=False)
        self.triage.run(use_llm=False, verbose=False)
        # Proposals stay in inbox; no entity files created.
        self.assertEqual(len(self._proposals()), 2)
        self.assertFalse((self.brain.ENTITIES_DIR / "newco.md").exists())
        self.assertFalse((self.brain.ENTITIES_DIR / "davide.md").exists())

    def test_triage_auto_accept_creates_entity_and_archives(self) -> None:
        self.hydrator.run(verbose=False)
        self.triage.run(
            use_llm=False, verbose=False, auto_accept_entities={"newco"}
        )
        entity = self.brain.ENTITIES_DIR / "newco.md"
        self.assertTrue(entity.exists())
        self.assertIn("name: newco", entity.read_text())
        self.assertIn("type: org", entity.read_text())
        # newco archived to processed; davide still held in inbox.
        self.assertEqual(
            [p.name for p in self._proposals()], ["proposed-entity-davide.md"]
        )
        processed = list(self.brain.INBOX_PROCESSED.glob("*proposed-entity-newco.md"))
        self.assertEqual(len(processed), 1)


if __name__ == "__main__":
    unittest.main()
