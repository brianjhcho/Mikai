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


if __name__ == "__main__":
    unittest.main()
