"""Tests for WikiFTS (SQLite FTS5 companion to WikiIndex) and the
WikiAdapter FTS routing (BM25-first search, metadata fallback, ingest
append, stale rebuild, kill switch).

Stdlib unittest; fixtures are hand-crafted wikis in tempdirs — the real
~/.mikai/wiki is never touched. All FTS tests skip cleanly when the
interpreter's SQLite lacks the FTS5 extension.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sidecar.l3 import wiki_adapter
from sidecar.l3.port import Episode, SearchQuery
from sidecar.l3.wiki_adapter import WikiAdapter
from sidecar.l3.wiki_fts import WikiFTS
from sidecar.l3.wiki_index import WikiIndex

FTS5_OK = WikiFTS.available()

PREAMBLE = "## Who\nBrian — test preamble, not a dated section.\n"

# Six hand-crafted sections in the exact shape WikiAdapter writes.
# - Section 2 has "monstera" in the NAME and 5× in the body (BM25 heavy).
# - Section 3 mentions "monstera" once, in the body only.
# - Sections 4 and 6 both mention "fern" (time-window filter tests);
#   section 4 is the only gmail-sourced one (source filter tests).
SECTIONS = [
    (
        "\n\n### 2026-07-01T10:00:00+00:00 — apple-notes: Groceries — Groceries\n"
        "<!-- ingested=2026-08-05T00:00:00+00:00 group_id=mikai-default -->\n\n"
        "Buy oat milk and coffee beans.\n"
    ),
    (
        "\n\n### 2026-07-03T12:30:00+00:00 — claude-code — Monstera care plan\n"
        "<!-- ingested=2026-08-05T00:00:01+00:00 group_id=mikai-default -->\n\n"
        "Repot the monstera; monstera aerial roots need a moss pole. "
        "Water the monstera weekly. The monstera prefers bright shade. "
        "Fertilize the monstera monthly.\n"
    ),
    (
        "\n\n### 2026-07-10T08:15:00+00:00 — apple-notes: Plants — Watering log\n"
        "<!-- ingested=2026-08-05T00:00:02+00:00 group_id=mikai-default -->\n\n"
        "Watered the pothos and the monstera today.\n"
    ),
    (
        "\n\n### 2026-07-20T18:00:00+00:00 — gmail — Flight confirmation\n"
        "<!-- ingested=2026-08-05T00:00:03+00:00 group_id=mikai-default -->\n\n"
        "YVR to NRT. Bring the fern book for the flight.\n"
    ),
    (
        "\n\n### 2026-07-28T09:45:00+00:00 — claude-code — Wiki index design\n"
        "<!-- ingested=2026-08-05T00:00:04+00:00 group_id=mikai-default -->\n\n"
        "Per-section byte offsets; JSONL sidecar file.\n"
    ),
    (
        "\n\n### 2026-08-01T14:00:00+00:00 — apple-notes: Plants — Fern repotting\n"
        "<!-- ingested=2026-08-05T00:00:05+00:00 group_id=mikai-default -->\n\n"
        "Moved the fern to a bigger pot near the north window.\n"
    ),
]


def make_wiki(dirpath: Path) -> Path:
    wiki = dirpath / "wiki.md"
    wiki.write_text(PREAMBLE + "".join(SECTIONS), encoding="utf-8")
    return wiki


@unittest.skipUnless(FTS5_OK, "SQLite FTS5 extension not available")
class WikiFTSTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.wiki = make_wiki(self.dir)
        self.db = self.dir / "wiki.fts.db"
        self.idx = WikiIndex.build(self.wiki)
        self.fts = WikiFTS.build(self.idx, self.wiki, self.db)
        self.addCleanup(self.fts.close)

    def test_build_indexes_every_section(self) -> None:
        self.assertEqual(self.fts.count(), 6)

    def test_bm25_ordering_name_and_frequency_win(self) -> None:
        """The section with 'monstera' in the name and 5× in the body
        outranks the section with a single body mention."""
        hits = self.fts.search("monstera")
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["name"], "Monstera care plan")
        self.assertEqual(hits[1]["name"], "Watering log")
        # BM25 rank: more negative = better; strictly ordered.
        self.assertLess(hits[0]["rank"], hits[1]["rank"])
        # snippet() produced a highlighted excerpt.
        self.assertIn("**monstera**", hits[0]["snippet"].lower())

    def test_empty_query_returns_empty(self) -> None:
        self.assertEqual(self.fts.search(""), [])
        self.assertEqual(self.fts.search("   "), [])

    def test_metadata_filters_combine_with_match(self) -> None:
        """since/until/source AND together with the FTS match."""
        # 'fern' appears in sections 4 (07-20, gmail) and 6 (08-01).
        self.assertEqual(len(self.fts.search("fern")), 2)
        hits = self.fts.search("fern", since="2026-07-25T00:00:00+00:00")
        self.assertEqual([h["name"] for h in hits], ["Fern repotting"])
        hits = self.fts.search("fern", until="2026-07-25T00:00:00+00:00")
        self.assertEqual([h["name"] for h in hits], ["Flight confirmation"])
        hits = self.fts.search("fern", source="gmail")
        self.assertEqual([h["name"] for h in hits], ["Flight confirmation"])
        # All three combined can eliminate everything.
        self.assertEqual(
            self.fts.search(
                "fern", since="2026-07-25T00:00:00+00:00", source="gmail"
            ),
            [],
        )

    def test_append_section_idempotent(self) -> None:
        record = {
            "header_ts": "2026-08-02T09:00:00+00:00",
            "source": "test-daemon",
            "name": "Fresh note",
            "byte_start": 99_999,
            "byte_end": 100_100,
            "content_bytes": 30,
        }
        self.assertTrue(self.fts.append_section(record, "A zebra crossed."))
        self.assertEqual(self.fts.count(), 7)
        self.assertEqual(self.fts.search("zebra")[0]["name"], "Fresh note")
        # Same slug again: skipped, no duplicate row.
        self.assertFalse(self.fts.append_section(record, "A zebra crossed."))
        self.assertEqual(self.fts.count(), 7)
        self.assertEqual(len(self.fts.search("zebra")), 1)

    def test_malformed_query_degrades_to_sanitized(self) -> None:
        """Raw FTS5 syntax errors (unbalanced quotes/operators) retry as
        quoted-phrase tokens instead of raising."""
        hits = self.fts.search('monstera AND ("')
        self.assertTrue(any(h["name"] == "Monstera care plan" for h in hits))


@unittest.skipUnless(FTS5_OK, "SQLite FTS5 extension not available")
class WikiAdapterFTSTest(unittest.TestCase):
    """Adapter routing: FTS-first search, ingest append, stale rebuild,
    kill switch, metadata fallback."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        make_wiki(self.root)
        self._orig_root = wiki_adapter.WIKI_ROOT
        wiki_adapter.WIKI_ROOT = self.root
        self.addCleanup(setattr, wiki_adapter, "WIKI_ROOT", self._orig_root)
        os.environ.pop("MIKAI_WIKI_FTS_DISABLED", None)
        os.environ.pop("MIKAI_WIKI_FTS_DB", None)

    def _episode(self) -> Episode:
        return Episode(
            content="The quetzal sighting happened at dawn near the volcano.",
            source_description="test-daemon",
            reference_time=datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
            name="Quetzal sighting",
        )

    def test_search_routes_through_fts(self) -> None:
        """A body-only term in an OLD section: the legacy metadata path
        can't see bodies (it would fall back to the most-recent fill),
        so getting the right section back proves the FTS route."""
        adapter = WikiAdapter()
        edges = asyncio.run(
            adapter.search(SearchQuery(text="moss pole", num_results=2))
        )
        self.assertTrue(edges)
        self.assertIn("Monstera care plan", edges[0].source_name)
        self.assertTrue((self.root / "wiki.fts.db").exists())

    def test_hitless_query_falls_back_to_metadata_path(self) -> None:
        """FTS returns nothing for gibberish — the legacy most-recent
        fill still gives the caller substrate (old-behavior parity)."""
        adapter = WikiAdapter()
        edges = asyncio.run(
            adapter.search(SearchQuery(text="zzqqxxplasma", num_results=3))
        )
        self.assertEqual(len(edges), 3)

    def test_ingest_appends_to_fts_immediately(self) -> None:
        adapter = WikiAdapter()
        asyncio.run(adapter.ingest_episode(self._episode()))
        hits = adapter.search_fts("quetzal volcano")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["name"], "Quetzal sighting")
        # Re-ingest (duplicate) leaves a single FTS row.
        asyncio.run(adapter.ingest_episode(self._episode()))
        self.assertEqual(len(adapter.search_fts("quetzal volcano")), 1)

    def test_rebuild_when_db_deleted(self) -> None:
        """Deleting the (disposable) DB is transparently repaired on the
        next call — even on an adapter that already had FTS loaded."""
        adapter = WikiAdapter()
        self.assertTrue(adapter.search_fts("monstera"))
        (self.root / "wiki.fts.db").unlink()
        hits = adapter.search_fts("monstera")
        self.assertEqual(len(hits), 2)
        self.assertTrue((self.root / "wiki.fts.db").exists())

    def test_kill_switch_disables_fts(self) -> None:
        os.environ["MIKAI_WIKI_FTS_DISABLED"] = "1"
        self.addCleanup(os.environ.pop, "MIKAI_WIKI_FTS_DISABLED", None)
        adapter = WikiAdapter()
        self.assertEqual(adapter.search_fts("monstera"), [])
        # Legacy metadata search still works…
        edges = asyncio.run(
            adapter.search(SearchQuery(text="Groceries", num_results=2))
        )
        self.assertTrue(any("Groceries" in e.source_name for e in edges))
        # …and no FTS DB is ever created.
        self.assertFalse((self.root / "wiki.fts.db").exists())


if __name__ == "__main__":
    unittest.main()
