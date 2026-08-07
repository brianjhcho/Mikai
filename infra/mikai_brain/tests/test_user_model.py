"""Tests for the UserModel compiler (post Fable §3 migration).

Two sections (Durable, Current). 2,048-byte cap. `source_signals` emit
to the audit log, not the injected file. Downstream (latent-threads)
scores against `current` — the merged themes-plus-unresolved list.

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

# Post-migration shape: two sections. `source_signals` still requested
# from the LLM (routed to audit log, stripped from the injected file).
_STUB_JSON = {
    "durable": [
        "ships fast, asks for pushback",
        "prefers propose-to-inbox over autonomous overwrite",
    ],
    "current": [
        "dry-eye ophthalmology",
        "plant care (monstera)",
        "China proposal for Germaine",
        "specify province for the China proposal",
    ],
    "source_signals": [
        "dry-eye ← perplexity + claude-thread",
        "china-proposal ← wiki narrative",
    ],
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

    # ── build() — two-section shape ────────────────────────────────────

    def test_build_structures_response_two_sections(self) -> None:
        model = self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        self.assertIn("ships fast, asks for pushback", model.durable)
        self.assertIn("dry-eye ophthalmology", model.current)
        self.assertTrue(model.updated_at)
        self.assertTrue(model.within_cap())
        self.assertFalse(hasattr(model, "themes"),
                         "themes attribute must be gone post-Fable §3")
        self.assertFalse(hasattr(model, "values"),
                         "values attribute must be gone post-Fable §3")

    def test_build_tolerates_code_fence(self) -> None:
        raw = "```json\n" + json.dumps(_STUB_JSON) + "\n```"
        model = self.user_model.build(chat_fn=lambda p: raw)
        self.assertEqual(len(model.current), 4)

    def test_markdown_has_only_durable_and_current_sections(self) -> None:
        model = self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        md = model.to_markdown()
        self.assertIn("## Durable", md)
        self.assertIn("## Current", md)
        # Everything Fable killed:
        for banned in ("## Values", "## Themes", "## Preferences",
                       "## Unresolved", "## Source signals"):
            self.assertNotIn(banned, md, f"banned section leaked: {banned}")

    def test_markdown_stays_within_2kb_cap(self) -> None:
        model = self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        self.assertLessEqual(
            len(model.to_markdown().encode("utf-8")),
            self.user_model.MARKDOWN_BYTE_CAP,
        )
        self.assertEqual(self.user_model.MARKDOWN_BYTE_CAP, 2048,
                         "Fable §3 mandates 2,048-byte cap; the 4,000 bump is reverted")

    def test_build_errors_on_over_cap_output(self) -> None:
        bloated = {**_STUB_JSON, "current": ["x" * 200 for _ in range(30)]}
        with self.assertRaises(RuntimeError):
            self.user_model.build(chat_fn=lambda p: json.dumps(bloated))

    def test_build_errors_on_non_json(self) -> None:
        with self.assertRaises(RuntimeError):
            self.user_model.build(chat_fn=lambda p: "not json at all")

    # ── source_signals → audit log, NOT the injected file ─────────────

    def test_source_signals_appended_to_audit_log_not_markdown(self) -> None:
        self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        log = self.user_model.USER_MODEL_SIGNALS_LOG
        self.assertTrue(log.exists(), "signals audit log not written")
        row = json.loads(log.read_text().splitlines()[0])
        self.assertIn("dry-eye ← perplexity + claude-thread", row["signals"])
        self.assertIn("ts", row)

    def test_source_signals_absent_from_markdown_and_persisted_json(self) -> None:
        model = self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        md_path, json_path = self.user_model.save(model)
        self.assertNotIn("source_signals", md_path.read_text())
        self.assertNotIn("Source signals", md_path.read_text())
        self.assertNotIn("source_signals", json_path.read_text(),
                         "source_signals persisted into user_model.json — "
                         "should live in audit log only")

    def test_audit_log_appends_across_multiple_builds(self) -> None:
        self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        log = self.user_model.USER_MODEL_SIGNALS_LOG
        self.assertEqual(len(log.read_text().splitlines()), 2)

    # ── save() / load() ────────────────────────────────────────────────

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
        self.assertEqual(loaded.current, model.current)
        self.assertEqual(loaded.durable, model.durable)

    def test_backup_written_on_second_save(self) -> None:
        m1 = self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        self.user_model.save(m1)
        m2 = self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        self.user_model.save(m2)
        md_backups = list(self.brain.BRAIN_ROOT.glob("USER_MODEL.md.bak-*"))
        json_backups = list(self.brain.STATE_DIR.glob("user_model.json.bak-*"))
        self.assertEqual(len(md_backups), 1)
        self.assertEqual(len(json_backups), 1,
                         "user_model.json also gets backed up now")

    def test_legacy_json_shape_migrates_on_load(self) -> None:
        # A stale user_model.json from before the migration still loads:
        # values+preferences fold into durable; themes+unresolved into current.
        self.brain.STATE_DIR.mkdir(parents=True, exist_ok=True)
        legacy = {
            "values": ["ships fast"],
            "themes": ["dry-eye"],
            "preferences": ["propose to inbox"],
            "unresolved": ["china province"],
            "source_signals": ["irrelevant"],
            "updated_at": "2026-08-06T00:00:00+00:00",
        }
        self.user_model.USER_MODEL_JSON.write_text(json.dumps(legacy))
        loaded = self.user_model.load()
        self.assertIsNotNone(loaded)
        self.assertIn("ships fast", loaded.durable)
        self.assertIn("propose to inbox", loaded.durable)
        self.assertIn("dry-eye", loaded.current)
        self.assertIn("china province", loaded.current)

    # ── downstream consumers pick up `current` ─────────────────────────

    def test_latent_threads_promotes_current_aligned_candidates(self) -> None:
        # Without a UserModel, ranking is frequency-only; theme_match is
        # empty on every candidate that surfaces.
        candidates_before = self.latent_threads.select_candidates()
        self.assertTrue(all(c.theme_match == "" for c in candidates_before))

        # Compile + save UserModel; `current` includes "dry-eye
        # ophthalmology" so the dry-eye entity now carries a match
        # citation and its ranker score climbs.
        m = self.user_model.build(chat_fn=lambda p: json.dumps(_STUB_JSON))
        self.user_model.save(m)

        candidates_after = self.latent_threads.select_candidates()
        slugs_after = [c.slug for c in candidates_after]
        self.assertIn("dry-eye", slugs_after)
        winning = next(c for c in candidates_after if c.slug == "dry-eye")
        self.assertTrue(winning.theme_match,
                        "expected theme_match to be set from `current`")
        self.assertIn("current", winning.reason,
                      "reason must cite the merged `current` slot, not `themes`")


if __name__ == "__main__":
    unittest.main()
