"""WikiIndex — per-section byte-offset index over the Karpathy wiki.

The wiki (~/.mikai/wiki/wiki.md) is an append-only file of dated sections
written by WikiAdapter.ingest_episode():

    ### <iso-ts> — <source_description> — <name>
    <!-- ingested=<iso-ts> group_id=<gid> -->

    <content>

At 27MB / 8,000+ sections the old "read the first 120KB" strategy sees
<1% of the file. This index records, per section, the byte range it
occupies in wiki.md so consumers can seek + read only the sections they
need. No database — an in-memory list over a JSONL sidecar file
(~/.mikai/wiki/wiki.index) is plenty at this scale, and JSONL append is
atomic enough for the ingest path (same pattern as progress.jsonl).

Record shape (one JSON object per line, chronological file order):

    {"header_ts": "2026-08-05T…+00:00", "source": "apple-notes: …",
     "name": "…", "byte_start": 123, "byte_end": 456,
     "content_bytes": 300}

- byte_start points at the `#` of the section's header line.
- byte_end is the offset where the next section's header starts (or EOF
  for the last section) — sections tile the file from the first header
  to EOF; any preamble before the first header is not indexed.
- content_bytes is len(content.rstrip().encode("utf-8")) — the episode
  body excluding header/comment lines. Used for idempotency checks
  (same key the backfill script's guard uses: header identity + size).

All offsets are BYTE offsets (the file is scanned in binary mode) —
CJK / emoji content does not skew them.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("mikai-graphiti.wiki-index")

# A dated section header as written by WikiAdapter.ingest_episode().
# Parsing note: `source` and `name` are split on " — " (em dash); a
# source_description that itself contains " — " would misparse (name
# absorbs the surplus). Acceptable: filters are substring/regex matches
# over both fields, and byte offsets are unaffected.
_HEADER_RE = re.compile(
    r"^### (?P<ts>\d{4}-\d{2}-\d{2}T\S+) — (?P<rest>.+)$"
)
_INGESTED_COMMENT_RE = re.compile(r"^<!--\s*ingested=")


def _parse_header(line: str) -> dict | None:
    """Parse a decoded header line into {header_ts, source, name}."""
    m = _HEADER_RE.match(line.rstrip("\n"))
    if not m:
        return None
    rest = m.group("rest")
    parts = rest.split(" — ")
    source = parts[0]
    name = " — ".join(parts[1:]) if len(parts) > 1 else source
    return {"header_ts": m.group("ts"), "source": source, "name": name}


def _parse_ts(value) -> datetime | None:
    """ISO string or datetime → aware datetime (naive assumed UTC)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _section_content_bytes(section_text: str) -> int:
    """Byte length of a section's episode body: everything after the
    header line and the optional `<!-- ingested=… -->` comment,
    stripped — mirrors len(episode.content.rstrip().encode()) at
    ingest time so build-derived and append-derived records agree."""
    lines = section_text.split("\n")
    body_start = 1  # skip header line
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    if body_start < len(lines) and _INGESTED_COMMENT_RE.match(lines[body_start]):
        body_start += 1
    body = "\n".join(lines[body_start:]).strip()
    return len(body.encode("utf-8"))


class WikiIndex:
    """Byte-offset index over wiki.md sections. Chronological (file)
    order is preserved: `records` matches wiki.md's actual order."""

    def __init__(
        self,
        records: list[dict] | None = None,
        index_path: Path | None = None,
    ) -> None:
        self.records: list[dict] = records or []
        self.index_path: Path | None = index_path
        # How far into wiki.md this index has scanned. Distinct from the
        # last record's byte_end because a preamble-only wiki scans to
        # EOF yet yields no records.
        self.scanned_bytes: int = (
            self.records[-1]["byte_end"] if self.records else 0
        )

    # ── Construction ─────────────────────────────────────────────────────

    @classmethod
    def build(cls, wiki_path: Path) -> "WikiIndex":
        """Scan wiki.md once (binary, byte-accurate) and index every
        dated section."""
        idx = cls()
        idx.refresh(wiki_path)
        return idx

    def refresh(self, wiki_path: Path) -> int:
        """Incrementally scan wiki.md from `scanned_bytes` to EOF and
        append any new sections. If the file shrank (rewrite/compaction),
        falls back to a full rebuild. Returns the number of records
        added (full rebuilds return the new total). The wiki is
        append-only in normal operation, so this is cheap."""
        if not wiki_path.exists():
            return 0
        size = wiki_path.stat().st_size
        if size < self.scanned_bytes:
            logger.info("wiki.md shrank (%d < %d) — full index rebuild",
                        size, self.scanned_bytes)
            self.records = []
            self.scanned_bytes = 0
        if size == self.scanned_bytes:
            return 0

        added = 0
        with wiki_path.open("rb") as f:
            f.seek(self.scanned_bytes)
            offset = self.scanned_bytes
            open_start: int | None = None
            open_meta: dict | None = None
            for raw in f:
                if raw.startswith(b"### "):
                    line = raw.decode("utf-8", errors="replace")
                    meta = _parse_header(line)
                    if meta is not None:
                        if open_meta is not None:
                            self._close_section(
                                wiki_path, open_meta, open_start, offset
                            )
                            added += 1
                        open_start, open_meta = offset, meta
                offset += len(raw)
            if open_meta is not None:
                self._close_section(wiki_path, open_meta, open_start, offset)
                added += 1
        self.scanned_bytes = size
        return added

    def _close_section(
        self, wiki_path: Path, meta: dict, byte_start: int, byte_end: int
    ) -> None:
        record = dict(meta)
        record["byte_start"] = byte_start
        record["byte_end"] = byte_end
        record["content_bytes"] = _section_content_bytes(
            self.read_section(wiki_path, record)
        )
        self.records.append(record)

    # ── Persistence (JSONL — append-friendly) ────────────────────────────

    def save(self, index_path: Path) -> None:
        """Persist as newline-delimited JSON, one row per section, in
        chronological (file) order. Written to a temp file then renamed
        so a crash never leaves a torn index."""
        index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = index_path.with_suffix(index_path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for record in self.records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        os.replace(tmp, index_path)
        self.index_path = index_path

    @classmethod
    def load(cls, index_path: Path) -> "WikiIndex":
        records: list[dict] = []
        with index_path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(
                        "wiki.index:%d — malformed row skipped", lineno
                    )
        return cls(records=records, index_path=index_path)

    def append_section(self, record: dict) -> None:
        """Record a just-appended section: extend the in-memory list and
        append one JSONL row to the index file (atomic append — no
        rewrite of the existing rows)."""
        self.records.append(record)
        end = record.get("byte_end")
        if isinstance(end, int) and end > self.scanned_bytes:
            self.scanned_bytes = end
        if self.index_path is not None:
            try:
                with self.index_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except OSError as exc:
                logger.warning("wiki.index append failed: %s", exc)

    # ── Queries ──────────────────────────────────────────────────────────

    def has_section(
        self,
        header_ts: str,
        source: str,
        name: str,
        content_bytes: int | None = None,
    ) -> bool:
        """Idempotency check: does a section with this exact header
        identity (and, when both sides know it, byte count) already
        exist? Mirrors the backfill script's double guard."""
        for r in self.records:
            if (
                r.get("header_ts") == header_ts
                and r.get("source") == source
                and r.get("name") == name
            ):
                known = r.get("content_bytes")
                if (
                    content_bytes is None
                    or known is None
                    or known == content_bytes
                ):
                    return True
        return False

    def sections_matching(
        self,
        *,
        since=None,
        until=None,
        source: str | None = None,
        name_pattern: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Filter the index. All filters AND together; records return in
        chronological (file) order. `since`/`until` are inclusive bounds
        on header_ts (datetime or ISO string; naive = UTC). `source` is
        a case-insensitive substring match. `name_pattern` is a
        case-insensitive regex searched against both name and source
        (backfilled sections carry the title in both). `limit` keeps the
        LAST — most recent — N matches."""
        since_dt, until_dt = _parse_ts(since), _parse_ts(until)
        pat = (
            re.compile(name_pattern, re.IGNORECASE)
            if name_pattern is not None
            else None
        )
        src = source.lower() if source is not None else None

        out: list[dict] = []
        for r in self.records:
            if since_dt is not None or until_dt is not None:
                ts = _parse_ts(r.get("header_ts"))
                if ts is None:
                    continue
                if since_dt is not None and ts < since_dt:
                    continue
                if until_dt is not None and ts > until_dt:
                    continue
            if src is not None and src not in str(r.get("source", "")).lower():
                continue
            if pat is not None and not (
                pat.search(str(r.get("name", "")))
                or pat.search(str(r.get("source", "")))
            ):
                continue
            out.append(r)
        if limit is not None and len(out) > limit:
            out = out[-limit:]
        return out

    # ── Windowed read ────────────────────────────────────────────────────

    @staticmethod
    def read_section(wiki_path: Path, record: dict) -> str:
        """Seek to the section's byte range and read exactly that slice.
        This is the windowed read — never the whole file."""
        start, end = record["byte_start"], record["byte_end"]
        with wiki_path.open("rb") as f:
            f.seek(start)
            data = f.read(end - start)
        return data.decode("utf-8", errors="replace")
