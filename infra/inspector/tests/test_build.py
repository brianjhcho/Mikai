"""Tests for the Inspector build pipeline.

Points ``MIKAI_BRAIN_ROOT`` at a tempdir before importing the inspector
modules so nothing under ``~/.mikai`` is touched. Verifies:

  * build_state() produces the expected shape (tensions, user_model,
    substrate),
  * write_outputs() creates both files,
  * embedded JSON in inspector.html is valid + contains our data,
  * the deleted canned-query panels stay deleted (regression guard).
"""

from __future__ import annotations

import importlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path


class BuildOutputsTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.brain_root = Path(self.tmp.name) / "brain"
        (self.brain_root / "state").mkdir(parents=True)
        (self.brain_root / "entities").mkdir(parents=True)
        (self.brain_root / "threads" / "example-thread").mkdir(parents=True)
        (self.brain_root / "USER_MODEL.md").write_text(
            "# USER_MODEL.md\n\n## Durable\n\n- ships vertical slices\n"
            "\n## Current\n\n- feat/pure-file-brain merged\n",
            encoding="utf-8")

        # Fake wiki
        self.wiki_dir = Path(self.tmp.name) / "wiki"
        self.wiki_dir.mkdir()
        (self.wiki_dir / "wiki.md").write_text(
            "## Tensions\n"
            "- **Fixture A:** small body.\n"
            "- **Fixture B:** another body.\n",
            encoding="utf-8")
        (self.wiki_dir / "wiki-narrative.md").write_text("narrative\n",
                                                          encoding="utf-8")

        # Console prototype state — empty
        self.console_dir = Path(self.tmp.name) / "console"
        self.console_dir.mkdir()
        (self.console_dir / "tensions.json").write_text("{}", encoding="utf-8")

        # Point env vars before import
        os.environ["MIKAI_BRAIN_ROOT"] = str(self.brain_root)

        # Reload modules with the new root
        import infra.mikai_brain as mb
        importlib.reload(mb)
        from infra import inspector
        importlib.reload(inspector)
        # Now patch the wiki + console constants to our temp fixture
        inspector.WIKI_DIR = self.wiki_dir
        inspector.WIKI_MD = self.wiki_dir / "wiki.md"
        inspector.CONSOLE_DIR = self.console_dir
        inspector.CONSOLE_TENSIONS_JSON = self.console_dir / "tensions.json"
        inspector.INSPECTOR_HTML = self.brain_root / "inspector.html"
        inspector.TENSIONS_JSON = self.brain_root / "state" / "tensions.json"

        from infra.inspector import tensions as T, build as B, render as R
        importlib.reload(T)
        importlib.reload(R)
        importlib.reload(B)
        # Re-patch after reload
        T.WIKI_MD = self.wiki_dir / "wiki.md"
        T.CONSOLE_TENSIONS_JSON = self.console_dir / "tensions.json"
        T.TENSIONS_JSON = self.brain_root / "state" / "tensions.json"
        B.WIKI_DIR = self.wiki_dir
        B.WIKI_MD = self.wiki_dir / "wiki.md"
        B.INSPECTOR_HTML = self.brain_root / "inspector.html"
        B.TENSIONS_JSON = self.brain_root / "state" / "tensions.json"
        B.USER_MODEL_MD = self.brain_root / "USER_MODEL.md"
        B.WIKI_NARRATIVE = self.wiki_dir / "wiki-narrative.md"
        self.B = B
        self.R = R

    def tearDown(self):
        os.environ.pop("MIKAI_BRAIN_ROOT", None)
        self.tmp.cleanup()

    def test_build_state_shape(self):
        st = self.B.build_state()
        self.assertIn("tensions", st)
        self.assertEqual(st["tensions_count"], 2)
        self.assertGreater(len(st["user_model"]["text"]), 0)
        self.assertIn("substrate", st)
        # The four canned-query panels are gone — regression guard so
        # they don't sneak back in as UI tabs (they belong in the ASK
        # bar, not as pre-taxonomized panels).
        self.assertNotIn("queries", st)
        # substrate has the expected keys
        for key in ("wiki_bytes", "thread_count", "entity_count",
                    "tensions_count", "attention_last"):
            self.assertIn(key, st["substrate"])
        # L4 SIGNALS + WIKI are wired
        self.assertIn("l4_signals", st)
        self.assertIn("source", st["l4_signals"])
        self.assertIn("wiki", st)
        self.assertIn("files", st["wiki"])

    def test_write_outputs_creates_both_files(self):
        st = self.B.build_state()
        written = self.B.write_outputs(st)
        paths = {p.name for p in written}
        self.assertIn("tensions.json", paths)
        self.assertIn("inspector.html", paths)
        # tensions JSON is valid
        data = json.loads((self.brain_root / "state" / "tensions.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(data["count"], 2)

    def test_html_has_embedded_state(self):
        st = self.B.build_state()
        self.B.write_outputs(st)
        html = (self.brain_root / "inspector.html").read_text(encoding="utf-8")
        # HTML has toggle link back to cockpit
        self.assertIn("cockpit.html", html)
        # HTML embeds the JSON payload
        m = re.search(r"window\.__INSPECTOR__\s*=\s*(.+?);\n", html)
        self.assertIsNotNone(m, "inline state assignment not found")
        embedded = json.loads(m.group(1))
        self.assertEqual(embedded["tensions_count"], 2)
        self.assertIn("Fixture A", embedded["tensions"][0]["title"])
        # canned-query panels are gone — page must not carry them
        self.assertNotIn("queries", embedded)
        # HTML rail must NOT reference the deleted panels
        for gone in ("Obsessions", "Aphorisms", "Ideas", "Expertise"):
            self.assertNotIn(gone, html)
        # The five real-data panels must be wired
        for label in ("Tensions", "User Model", "L4 Signals",
                      "Wiki", "Substrate"):
            self.assertIn(label, html)
        # Release button is present on tension cards
        self.assertIn("release-btn", html)


if __name__ == "__main__":
    unittest.main()
