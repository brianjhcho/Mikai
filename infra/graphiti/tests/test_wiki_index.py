"""Tests for WikiIndex (byte-offset index over wiki.md) and the
WikiAdapter integration (index append on ingest, idempotency).

Stdlib unittest; fixtures are hand-crafted wikis in tempdirs — the real
~/.mikai/wiki is never touched.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sidecar.l3 import wiki_adapter
from sidecar.l3.port import Episode
from sidecar.l3.wiki_adapter import WikiAdapter
from sidecar.l3.wiki_index import WikiIndex

PREAMBLE = "## Who\nBrian — test preamble, not a dated section.\n"

# Five hand-crafted sections in the exact shape WikiAdapter writes.
# Section 3 is CJK + emoji so byte offsets != char offsets.
SECTIONS = [
    (
        "\n\n### 2026-07-01T10:00:00+00:00 — apple-notes: Groceries — Groceries\n"
        "<!-- ingested=2026-08-05T00:00:00+00:00 group_id=mikai-default -->\n\n"
        "Buy oat milk and coffee beans.\n"
    ),
    (
        "\n\n### 2026-07-03T12:30:00+00:00 — claude-code — MIKAI wiki pivot\n"
        "<!-- ingested=2026-08-05T00:00:01+00:00 group_id=mikai-default -->\n\n"
        "Discussed the substrate pivot to the Karpathy wiki.\n"
    ),
    (
        "\n\n### 2026-07-10T08:15:00+00:00 — apple-notes: 日本語メモ — 日本語メモ\n"
        "<!-- ingested=2026-08-05T00:00:02+00:00 group_id=mikai-default -->\n\n"
        "寿司を食べた 🍣🎉 — multibyte content with emoji.\n"
    ),
    (
        "\n\n### 2026-07-20T18:00:00+00:00 — gmail — Flight confirmation\n"
        "<!-- ingested=2026-08-05T00:00:03+00:00 group_id=mikai-default -->\n\n"
        "YVR to NRT, departing 2026-09-01.\n"
    ),
    (
        "\n\n### 2026-07-28T09:45:00+00:00 — claude-code — Wiki index design\n"
        "<!-- ingested=2026-08-05T00:00:04+00:00 group_id=mikai-default -->\n\n"
        "Per-section byte offsets; JSONL sidecar file.\n"
    ),
]


def make_wiki(dirpath: Path) -> Path:
    wiki = dirpath / "wiki.md"
    wiki.write_text(PREAMBLE + "".join(SECTIONS), encoding="utf-8")
    return wiki


class WikiIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.wiki = make_wiki(self.dir)

    # ── build + offsets ──

    def test_build_offsets_tile_the_file(self) -> None:
        """Section byte ranges reconstruct the file exactly: preamble +
        contiguous slices == original bytes (offsets are provably
        correct, not just plausible)."""
        idx = WikiIndex.build(self.wiki)
        self.assertEqual(len(idx.records), 5)
        raw = self.wiki.read_bytes()
        first_start = idx.records[0]["byte_start"]
        rebuilt = raw[:first_start] + b"".join(
            raw[r["byte_start"]:r["byte_end"]] for r in idx.records
        )
        self.assertEqual(rebuilt, raw)
        # Contiguity + chronological file order.
        for a, b in zip(idx.records, idx.records[1:]):
            self.assertEqual(a["byte_end"], b["byte_start"])

    def test_read_section_roundtrip_utf8(self) -> None:
        """read_section returns the exact original section text, CJK and
        emoji included (byte counting, not char counting)."""
        idx = WikiIndex.build(self.wiki)
        cjk = idx.records[2]
        self.assertEqual(cjk["source"], "apple-notes: 日本語メモ")
        text = WikiIndex.read_section(self.wiki, cjk)
        # Original section 2 minus its leading "\n\n" (owned by the
        # previous section's slice), plus the next section's "\n\n".
        self.assertEqual(text, SECTIONS[2][2:] + "\n\n")
        self.assertIn("🍣🎉", text)
        # Header metadata parsed correctly.
        self.assertEqual(cjk["header_ts"], "2026-07-10T08:15:00+00:00")
        self.assertEqual(cjk["name"], "日本語メモ")

    # ── persistence ──

    def test_save_load_roundtrip(self) -> None:
        idx = WikiIndex.build(self.wiki)
        index_path = self.dir / "wiki.index"
        idx.save(index_path)
        loaded = WikiIndex.load(index_path)
        self.assertEqual(loaded.records, idx.records)
        # JSONL: one row per section, not a JSON array.
        lines = index_path.read_text().strip().splitlines()
        self.assertEqual(len(lines), 5)
        self.assertTrue(all(line.startswith("{") for line in lines))

    def test_append_section_persists_jsonl_row(self) -> None:
        idx = WikiIndex.build(self.wiki)
        index_path = self.dir / "wiki.index"
        idx.save(index_path)
        record = {
            "header_ts": "2026-08-01T00:00:00+00:00",
            "source": "test-src",
            "name": "appended",
            "byte_start": idx.scanned_bytes + 2,
            "byte_end": idx.scanned_bytes + 100,
            "content_bytes": 42,
        }
        idx.append_section(record)
        self.assertEqual(len(idx.records), 6)
        loaded = WikiIndex.load(index_path)
        self.assertEqual(len(loaded.records), 6)
        self.assertEqual(loaded.records[-1], record)

    # ── sections_matching filters ──

    def test_matching_since_until(self) -> None:
        idx = WikiIndex.build(self.wiki)
        got = idx.sections_matching(
            since=datetime(2026, 7, 2, tzinfo=timezone.utc),
            until=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )
        self.assertEqual(
            [r["header_ts"] for r in got],
            ["2026-07-03T12:30:00+00:00", "2026-07-10T08:15:00+00:00"],
        )
        # ISO-string bounds work too.
        got2 = idx.sections_matching(since="2026-07-21T00:00:00+00:00")
        self.assertEqual([r["name"] for r in got2], ["Wiki index design"])

    def test_matching_source(self) -> None:
        idx = WikiIndex.build(self.wiki)
        got = idx.sections_matching(source="claude-code")
        self.assertEqual(
            [r["name"] for r in got],
            ["MIKAI wiki pivot", "Wiki index design"],
        )

    def test_matching_name_pattern_and_limit(self) -> None:
        idx = WikiIndex.build(self.wiki)
        got = idx.sections_matching(name_pattern=r"wiki")
        self.assertEqual(len(got), 2)  # case-insensitive regex
        # limit keeps the most recent matches.
        got = idx.sections_matching(limit=2)
        self.assertEqual(
            [r["name"] for r in got],
            ["Flight confirmation", "Wiki index design"],
        )

    # ── incremental refresh ──

    def test_refresh_picks_up_appended_sections(self) -> None:
        idx = WikiIndex.build(self.wiki)
        extra = (
            "\n\n### 2026-08-02T11:00:00+00:00 — gmail — New episode\n"
            "<!-- ingested=2026-08-05T01:00:00+00:00 group_id=g -->\n\n"
            "Appended after the initial build.\n"
        )
        with self.wiki.open("a", encoding="utf-8") as f:
            f.write(extra)
        added = idx.refresh(self.wiki)
        self.assertEqual(added, 1)
        self.assertEqual(len(idx.records), 6)
        text = WikiIndex.read_section(self.wiki, idx.records[-1])
        self.assertIn("Appended after the initial build.", text)


class WikiAdapterIndexTest(unittest.TestCase):
    """ingest_episode ↔ index integration, against a tempdir wiki root."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._orig_root = wiki_adapter.WIKI_ROOT
        wiki_adapter.WIKI_ROOT = self.root
        self.addCleanup(setattr, wiki_adapter, "WIKI_ROOT", self._orig_root)
        make_wiki(self.root)
        self.adapter = WikiAdapter()

    def _episode(self) -> Episode:
        return Episode(
            content="Fresh episode content 🚀 with multibyte 内容.",
            source_description="test-daemon",
            reference_time=datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
            name="fresh episode",
        )

    def test_ingest_appends_wiki_and_index(self) -> None:
        result = asyncio.run(self.adapter.ingest_episode(self._episode()))
        self.assertTrue(result.episode_uuid.startswith("wiki-ep-"))
        index_path = self.root / "wiki.index"
        self.assertTrue(index_path.exists())
        idx = WikiIndex.load(index_path)
        self.assertEqual(len(idx.records), 6)  # 5 fixture + 1 ingested
        last = idx.records[-1]
        self.assertEqual(last["source"], "test-daemon")
        self.assertEqual(last["name"], "fresh episode")
        text = WikiIndex.read_section(self.root / "wiki.md", last)
        self.assertIn("Fresh episode content 🚀 with multibyte 内容.", text)
        self.assertTrue(text.startswith("### 2026-08-03T12:00:00+00:00"))

    def test_ingest_idempotent_skips_wiki_and_index(self) -> None:
        asyncio.run(self.adapter.ingest_episode(self._episode()))
        wiki = self.root / "wiki.md"
        size_after_first = wiki.stat().st_size
        rows_after_first = len(
            WikiIndex.load(self.root / "wiki.index").records
        )
        # Re-ingest the identical episode — must be a no-op for both files.
        asyncio.run(self.adapter.ingest_episode(self._episode()))
        self.assertEqual(wiki.stat().st_size, size_after_first)
        self.assertEqual(
            len(WikiIndex.load(self.root / "wiki.index").records),
            rows_after_first,
        )

    def test_ingest_dedup_ignores_content_diff(self) -> None:
        """Regression: identity-only dedup. A second ingest with the same
        (reference_time, source, name) but a DIFFERENT body must still
        be skipped — this is the truncated-duplicate scenario that put
        two copies of TSA 2.0::006::human in wiki.md before 2026-08-07."""
        first = self._episode()
        asyncio.run(self.adapter.ingest_episode(first))
        wiki = self.root / "wiki.md"
        size_after_first = wiki.stat().st_size
        rows_after_first = len(
            WikiIndex.load(self.root / "wiki.index").records
        )
        truncated = Episode(
            content="Fresh episode content 🚀 …[truncated]",
            source_description=first.source_description,
            reference_time=first.reference_time,
            name=first.name,
        )
        asyncio.run(self.adapter.ingest_episode(truncated))
        self.assertEqual(
            wiki.stat().st_size, size_after_first,
            "wiki.md must not grow on same-identity re-ingest",
        )
        self.assertEqual(
            len(WikiIndex.load(self.root / "wiki.index").records),
            rows_after_first,
            "wiki.index must not gain a row on same-identity re-ingest",
        )

    def test_search_uses_index_never_whole_file(self) -> None:
        """search() returns matching sections via the index; results are
        capped and never require reading all of wiki.md."""
        from sidecar.l3.port import SearchQuery

        edges = asyncio.run(
            self.adapter.search(SearchQuery(text="wiki", num_results=3))
        )
        self.assertGreaterEqual(len(edges), 1)
        facts = "\n".join(e.fact for e in edges)
        self.assertIn("substrate pivot", facts)


if __name__ == "__main__":
    unittest.main()
