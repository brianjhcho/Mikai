"""Tests for the UserModel compiler.

Isolation pattern matches test_hydrator.py / test_end_to_end.py: HOME
repointed at a tempdir, package reloaded so BRAIN_ROOT rebinds. No
real LLM traffic — the build() call is exercised with a stub chat_fn.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


_FIXTURE_ONTOLOGY = """\
# Wiki Ontology — as of 2026-08-06

| entity | type | mentions | first_seen | last_seen | sources |
|---|---|---|---|---|---|
| germaine | person | 84 | 2017-10-18 | 2026-08-06 | apple-notes |
| dry-eye | thing | 6 | 2026-07-01 | 2026-08-05 | perplexity, claude-thread |
| monstera | thing | 8 | 2026-05-01 | 2026-08-01 | apple-notes |
"""

_FIXTURE_NARRATIVE = """\
# Wiki Narrative (2026-08)

Brian spent July on dry-eye ophthalmology research and plant care
(monstera, moss pole). China proposal for Germaine is still open.
"""

_FIXTURE_PROFILE = """\
# PROFILE.md

Brian Cho. Ships fast, asks for pushback. Partner Germaine. Building MIKAI.
"""

_FIXTURE_BRAIN = """\
# BRAIN.md

## Current priorities

- Ship USER_MODEL.md
"""

_STUB_JSON = {
    "values": ["ships fast", "asks for pushback"],
    "themes": ["dry-eye ophthalmology", "plant care (monstera)",
               "China proposal for Germaine"],
    "preferences": ["propose-to-inbox over autonomous overwrite"],
    "unresolved": ["specify province for the China proposal"],
    "source_signals": ["dry-eye ← perplexity + claude-thread",
                       "china-proposal ← wiki narrative"],
}


class UserModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_home = os.environ.get("HOME")
        self._orig_root = os.environ.pop("MIKAI_BRAIN_ROOT", None)
        self._orig_ontology = os.environ.pop("MIKAI_WIKI_ONTOLOGY", None)

        self.home = tempfile.mkdtemp(prefix="mikai-user-model-test-")
        os.environ["HOME"] = self.home

        import infra.mikai_brain as brain_pkg
        importlib.reload(brain_pkg)
        from infra.mikai_brain import user_model, latent_threads, hydrator
        from infra.mikai_brain import ledger, threads, triage
        for mod in (threads, ledger, triage, hydrator, user_model, latent_threads):
            importlib.reload(mod)
        self.brain = brain_pkg
        self.user_model = user_model
        self.latent_threads = latent_threads
        self.hydrator = hydrator

        # Substrate fixture: PROFILE, BRAIN, wiki narrative + ontology.
        brain_pkg.BRAIN_ROOT.mkdir(parents=True, exist_ok=True)
        (brain_pkg.BRAIN_ROOT / "PROFILE.md").write_text(_FIXTURE_PROFILE)
        brain_pkg.BRAIN_MD.write_text(_FIXTURE_BRAIN)
        brain_pkg.ENTITIES_DIR.mkdir(parents=True, exist_ok=True)
        (brain_pkg.ENTITIES_DIR / "germaine.md").write_text(
            "---\nname: germaine\ntype: person\n---\n"
        )
        brain_pkg.STATE_DIR.mkdir(parents=True, exist_ok=True)

        wiki = Path(self.home) / ".mikai" / "wiki"
        wiki.mkdir(parents=True, exist_ok=True)
        (wiki / "wiki-narrative.md").write_text(_FIXTURE_NARRATIVE)
        (wiki / "wiki-ontology.md").write_text(_FIXTURE_ONTOLOGY)

    def tearDown(self) -> None:
        if self._orig_home is not None:
            os.environ["HOME"] = self._orig_home
        if self._orig_root is not None:
            os.environ["MIKAI_BRAIN_ROOT"] = self._orig_root
        if self._orig_ontology is not None:
            os.environ["MIKAI_WIKI_ONTOLOGY"] = self._orig_ontology
        shutil.rmtree(self.home, ignore_errors=True)

    # ── build() ─────────────────────────────────────────────────────────

    def test_build_structures_response(self) -> None:
        model = self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        self.assertIn("ships fast", model.values)
        self.assertIn("dry-eye ophthalmology", model.themes)
        self.assertTrue(model.updated_at)
        self.assertTrue(model.within_cap())

    def test_build_tolerates_code_fence(self) -> None:
        raw = "```json\n" + json.dumps(_STUB_JSON) + "\n```"
        model = self.user_model.build(chat_fn=lambda p: raw)
        self.assertEqual(len(model.themes), 3)

    def test_build_errors_on_over_cap_output(self) -> None:
        bloated = {**_STUB_JSON, "themes": ["x" * 200 for _ in range(30)]}
        with self.assertRaises(RuntimeError):
            self.user_model.build(chat_fn=lambda p: json.dumps(bloated))

    def test_build_errors_on_non_json(self) -> None:
        with self.assertRaises(RuntimeError):
            self.user_model.build(chat_fn=lambda p: "not json at all")

    # ── save() / load() ─────────────────────────────────────────────────

    def test_save_and_load_roundtrip(self) -> None:
        model = self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        md_path, json_path = self.user_model.save(model)
        self.assertTrue(md_path.exists())
        self.assertTrue(json_path.exists())
        # The "# WHAT MIKAI HAS OBSERVED ABOUT YOU" wrapper header lives
        # in the ask-time composer, NOT in the persisted markdown file.
        self.assertNotIn("WHAT MIKAI HAS OBSERVED", md_path.read_text())
        self.assertIn("dry-eye ophthalmology", md_path.read_text())

        loaded = self.user_model.load()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.themes, model.themes)
        self.assertEqual(loaded.values, model.values)

    def test_backup_written_on_second_save(self) -> None:
        m1 = self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        self.user_model.save(m1)
        m2 = self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        self.user_model.save(m2)
        backups = list(self.brain.BRAIN_ROOT.glob("USER_MODEL.md.bak-*"))
        self.assertEqual(len(backups), 1)

    # ── downstream consumers pick it up ─────────────────────────────────

    def test_latent_threads_promotes_theme_aligned_candidates(self) -> None:
        # Without a UserModel, ranking is frequency-only; theme_match is
        # empty on every candidate that surfaces.
        candidates_before = self.latent_threads.select_candidates()
        self.assertTrue(all(c.theme_match == "" for c in candidates_before))

        # Compile + save UserModel, then re-run: dry-eye now carries a
        # theme_match citation and its ranker score climbs above the
        # frequency-only equivalent.
        m = self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        self.user_model.save(m)

        candidates_after = self.latent_threads.select_candidates()
        slugs_after = [c.slug for c in candidates_after]
        self.assertIn("dry-eye", slugs_after)
        winning = next(c for c in candidates_after if c.slug == "dry-eye")
        self.assertTrue(winning.theme_match, "expected theme_match to be set")
        # And its ranker reason cites the theme, not raw frequency.
        self.assertIn("theme", winning.reason)


if __name__ == "__main__":
    unittest.main()
