"""Tests for the wiki tensions parser.

The wiki file is 33 MB in production; tests use a small in-memory
fixture so they run in milliseconds. State merge is exercised with a
mock console-state JSON so the actual ``~/.mikai/console/tensions.json``
is never touched.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from infra.inspector import tensions as T


WIKI_FIXTURE = """## Who
Brian likes tea.

## Now
- Building things.

## Tensions
- **Trust vs. evidence:** wants to trust the friend but needs data.
- **Aesthetic vs. biology:** wants sculptural plants but they grow their own way.
- Sports coaching philosophy is a coach who confirms you.

## Wants
- Coffee.


### 2026-04-01T10:00:00+00:00 — claude-thread: Deep econ — Deep econ
some episode body.

## Tensions & Open Questions
- **Knowledge vs. Control** — preserve distributed benefits while achieving coordination.
- **Expertise Legitimacy** — how to credential without elitism.

## Frameworks
- foo


### 2026-05-01T12:00:00+00:00 — claude-thread: template — template
## Tensions & Open Questions
List unresolved questions, tradeoffs that were identified but not resolved, or threads worth pulling in future sessions. These are high-value — do not omit them to make the summary feel cleaner.

## What to Discard
- placeholder
"""


class TensionsParseTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.wiki = Path(self.tmp.name) / "wiki.md"
        self.wiki.write_text(WIKI_FIXTURE, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_parses_all_three_bullet_shapes(self):
        parsed = T.parse_wiki_tensions(self.wiki)
        titles = [p["title"] for p in parsed]
        # bold+colon, bold+em-dash, and plain-sentence bullets all land
        self.assertIn("Trust vs. evidence", titles)
        self.assertIn("Knowledge vs. Control", titles)
        self.assertTrue(any(t.startswith("Sports coaching") for t in titles))

    def test_skips_template_placeholder(self):
        parsed = T.parse_wiki_tensions(self.wiki)
        joined = "\n".join(p["body"] for p in parsed)
        # the "List unresolved questions..." template body must NOT be a tension
        self.assertNotIn("high-value", joined.lower().split("provenance", 1)[0])
        for p in parsed:
            self.assertFalse(
                p["title"].lower().startswith("list unresolved"),
                p["title"])

    def test_provenance_and_first_seen(self):
        parsed = T.parse_wiki_tensions(self.wiki)
        by_title = {p["title"]: p for p in parsed}
        # top-narrative tension has no ### header above → coarse fallback
        top = by_title["Trust vs. evidence"]
        self.assertIsNone(top["first_seen_date"])
        # thread-embedded tension picks up the ### episode header date
        econ = by_title["Knowledge vs. Control"]
        self.assertEqual(econ["first_seen_date"], "2026-04-01")
        self.assertIn("Deep econ", econ["provenance"])

    def test_dedupes_by_slug(self):
        wiki2 = self.wiki.parent / "wiki2.md"
        wiki2.write_text(
            "## Tensions\n"
            "- **Duplicate:** first appearance.\n"
            "## Tensions\n"
            "- **Duplicate:** second appearance would collide.\n",
            encoding="utf-8")
        parsed = T.parse_wiki_tensions(wiki2)
        self.assertEqual(len([p for p in parsed if p["slug"] == "duplicate"]), 1)


class ConsoleStateMergeTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.wiki = Path(self.tmp.name) / "wiki.md"
        self.wiki.write_text(WIKI_FIXTURE, encoding="utf-8")
        self.state_path = Path(self.tmp.name) / "console-tensions.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_merge_preserves_prior_notes_and_status(self):
        parsed = T.parse_wiki_tensions(self.wiki)
        slug = parsed[0]["slug"]
        state = {
            slug: {
                "status": "released",
                "releasedAt": "2026-08-01T04:00:00Z",
                "notes": [
                    {"at": "2026-07-30T10:00:00Z", "text": "gave up on this"},
                ],
            }
        }
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        loaded = T.load_console_state(self.state_path)
        merged = T.merge_state(parsed, loaded)
        first = merged[0]
        self.assertEqual(first["status"], "released")
        self.assertEqual(first["released_at"], "2026-08-01T04:00:00Z")
        self.assertEqual(len(first["notes"]), 1)
        # tensions without prior state default to "holding"
        for m in merged[1:]:
            self.assertEqual(m["status"], "holding")
            self.assertEqual(m["notes"], [])

    def test_missing_console_state_yields_empty_dict(self):
        loaded = T.load_console_state(self.state_path / "does-not-exist.json")
        self.assertEqual(loaded, {})

    def test_write_json_shape(self):
        parsed = T.parse_wiki_tensions(self.wiki)
        merged = T.merge_state(parsed, {})
        out_path = Path(self.tmp.name) / "tensions.json"
        T.write_json(merged, out_path=out_path, backup=False)
        data = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertIn("generated_at", data)
        self.assertEqual(data["count"], len(merged))
        self.assertEqual(len(data["tensions"]), len(merged))
        self.assertIn("slug", data["tensions"][0])
        self.assertIn("status", data["tensions"][0])


if __name__ == "__main__":
    unittest.main()
