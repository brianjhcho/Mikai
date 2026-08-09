"""WikiFTS — SQLite FTS5 companion index to WikiIndex.

Ranking layer of the retrieval stack (docs/RETRIEVAL_STACK.md): WikiIndex
answers "where does each section live" (byte offsets, metadata filters);
WikiFTS answers "which sections best match these words" (BM25). Together
they give the LLM consumer the best ~10 sections for a keyword query
instead of all 300 mentions.

Properties:
- **Derived + disposable.** The DB (~/.mikai/wiki/wiki.fts.db, override
  via MIKAI_WIKI_FTS_DB) is fully reconstructible from wiki.md + the
  WikiIndex. Deleting it loses nothing; `rebuild_if_stale()` regrows it.
  wiki.md / wiki.index remain the sources of truth for content and
  section boundaries — FTS is additive.
- **No vectors, no services.** stdlib sqlite3 only. If the interpreter's
  SQLite lacks the FTS5 extension (rare), `WikiFTS.available()` is False
  and callers degrade to the WikiIndex metadata path.
- **Row shape.** One row per wiki section. `name` + `body` are the
  FTS-indexed text; `slug` / `header_ts` / `source` / `byte_start` ride
  along UNINDEXED for filtering and for mapping hits back to WikiIndex
  records. `slug` is the composite header identity
  (header_ts|source|name) and doubles as the idempotency key.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from pathlib import Path

from sidecar.l3.wiki_index import WikiIndex, _parse_ts

logger = logging.getLogger("mikai-graphiti.wiki-fts")

TABLE = "wiki_fts"

_CREATE_SQL = (
    f"CREATE VIRTUAL TABLE IF NOT EXISTS {TABLE} USING fts5("
    "name, body, "
    "slug UNINDEXED, header_ts UNINDEXED, source UNINDEXED, "
    "byte_start UNINDEXED)"
)

_INGESTED_COMMENT_RE = re.compile(r"^<!--\s*ingested=")

_FTS5_AVAILABLE: bool | None = None


def default_db_path() -> Path:
    """Resolve the FTS database path: MIKAI_WIKI_FTS_DB env override,
    else ~/.mikai/wiki/wiki.fts.db."""
    env = os.environ.get("MIKAI_WIKI_FTS_DB")
    if env:
        return Path(env)
    return Path.home() / ".mikai" / "wiki" / "wiki.fts.db"


def _section_body(section_text: str) -> str:
    """Episode body of a section: everything after the header line and
    the optional `<!-- ingested=… -->` comment (mirrors
    wiki_index._section_content_bytes)."""
    lines = section_text.split("\n")
    body_start = 1  # skip header line
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    if body_start < len(lines) and _INGESTED_COMMENT_RE.match(lines[body_start]):
        body_start += 1
    return "\n".join(lines[body_start:]).strip()


def _slug(record: dict) -> str:
    return (
        f"{record.get('header_ts', '?')}|{record.get('source', '?')}|"
        f"{record.get('name', '?')}"
    )


def _sanitize_query(query: str) -> str:
    """Turn arbitrary text into a safe FTS5 query. Used as a fallback
    when the raw query is not valid FTS5 syntax (unbalanced quotes,
    stray operators, hyphens, CJK punctuation, …): every token with at
    least one word character becomes a quoted phrase, OR-joined —
    forgiving on junk tokens, still BM25-ranked."""
    tokens = [
        t.replace('"', '""')
        for t in query.split()
        if any(c.isalnum() for c in t)
    ]
    return " OR ".join(f'"{t}"' for t in tokens)


class WikiFTS:
    """FTS5 index over wiki sections. All content is derived; the DB can
    be deleted at any time and rebuilt from wiki.md + WikiIndex."""

    def __init__(self, db_path: Path, conn: sqlite3.Connection) -> None:
        self.db_path = db_path
        self._conn = conn

    # ── Availability ─────────────────────────────────────────────────────

    @staticmethod
    def available() -> bool:
        """True if this interpreter's SQLite has FTS5 compiled in."""
        global _FTS5_AVAILABLE
        if _FTS5_AVAILABLE is None:
            try:
                probe = sqlite3.connect(":memory:")
                try:
                    probe.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
                    _FTS5_AVAILABLE = True
                finally:
                    probe.close()
            except sqlite3.Error:
                _FTS5_AVAILABLE = False
                logger.warning(
                    "SQLite FTS5 extension unavailable in this Python — "
                    "WikiFTS disabled; retrieval falls back to WikiIndex "
                    "metadata matching"
                )
        return _FTS5_AVAILABLE

    # ── Construction ─────────────────────────────────────────────────────

    @classmethod
    def _connect(cls, db_path: Path) -> sqlite3.Connection:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.execute(_CREATE_SQL)
        return conn

    @classmethod
    def load(cls, db_path: Path | None = None) -> "WikiFTS | None":
        """Open an existing (or empty-new) FTS DB. Returns None if FTS5
        is unavailable."""
        if not cls.available():
            return None
        path = db_path or default_db_path()
        return cls(path, cls._connect(path))

    @classmethod
    def build(
        cls,
        wiki_index: WikiIndex,
        wiki_path: Path,
        db_path: Path | None = None,
    ) -> "WikiFTS | None":
        """One-shot rebuild: drop any existing rows and re-insert every
        section from the WikiIndex, bodies read via windowed
        `read_section` seeks (never a whole-file read)."""
        if not cls.available():
            return None
        path = db_path or default_db_path()
        fts = cls(path, cls._connect(path))
        conn = fts._conn
        # Slug dedup during rebuild: wiki.md occasionally holds two
        # sections with the same header identity (pre-2026-08-07 truncated
        # re-ingest bug; see wiki_adapter.ingest_episode dedup notes).
        # WikiIndex records both, but the FTS table has no unique-slug
        # constraint (FTS5 virtual tables don't support them). Deduping
        # here — keep the FIRST occurrence per slug — prevents a truncated
        # copy from out-ranking the original at BM25 time.
        seen: set[str] = set()
        def _rows():
            for record in wiki_index.records:
                slug = _slug(record)
                if slug in seen:
                    continue
                seen.add(slug)
                text = wiki_index.read_section(wiki_path, record)
                yield (
                    record.get("name", ""),
                    _section_body(text),
                    slug,
                    record.get("header_ts", ""),
                    record.get("source", ""),
                    record.get("byte_start", -1),
                )

        with conn:
            conn.execute(f"DELETE FROM {TABLE}")
            conn.executemany(
                f"INSERT INTO {TABLE} "
                "(name, body, slug, header_ts, source, byte_start) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                _rows(),
            )
        logger.info(
            "wiki.fts rebuilt: %d unique / %d total sections → %s",
            len(seen), len(wiki_index.records), path,
        )
        return fts

    @classmethod
    def rebuild_if_stale(
        cls,
        wiki_index: WikiIndex,
        wiki_path: Path,
        db_path: Path | None = None,
    ) -> "WikiFTS | None":
        """Load the DB and compare its row count against the WikiIndex
        section count; on drift (or a missing/deleted DB file) do a full
        rebuild. Cheap when in sync — one COUNT(*) query."""
        if not cls.available():
            return None
        path = db_path or default_db_path()
        if not path.exists():
            return cls.build(wiki_index, wiki_path, path)
        fts = cls.load(path)
        if fts is None:
            return None
        # Compare against unique-slug count, not raw record count: build()
        # dedups duplicate slugs, so a wiki.index with N records where M
        # are duplicates produces N-M FTS rows. Comparing against N would
        # rebuild every call. Cheap enough at 8K-section scale to compute
        # the unique set per adapter load.
        expected = len({_slug(r) for r in wiki_index.records})
        if fts.count() != expected:
            logger.info(
                "wiki.fts stale (%d rows vs %d unique sections) — rebuilding",
                fts.count(), expected,
            )
            fts.close()
            return cls.build(wiki_index, wiki_path, path)
        return fts

    # ── Write ────────────────────────────────────────────────────────────

    def append_section(self, record: dict, body: str) -> bool:
        """Insert one just-ingested section. Idempotent: a row whose
        slug already exists is skipped. Returns True if inserted."""
        slug = _slug(record)
        cur = self._conn.execute(
            f"SELECT 1 FROM {TABLE} WHERE slug = ? LIMIT 1", (slug,)
        )
        if cur.fetchone() is not None:
            return False
        with self._conn:
            self._conn.execute(
                f"INSERT INTO {TABLE} "
                "(name, body, slug, header_ts, source, byte_start) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.get("name", ""),
                    body.strip(),
                    slug,
                    record.get("header_ts", ""),
                    record.get("source", ""),
                    record.get("byte_start", -1),
                ),
            )
        return True

    # ── Read ─────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        since=None,
        until=None,
        source: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """BM25-ranked FTS5 query with optional metadata filters
        (inclusive header_ts window; case-insensitive source substring).
        Returns [{slug, header_ts, source, name, snippet, rank,
        byte_start}] best-first. Empty/blank queries return []."""
        q = query.strip()
        if not q:
            return []

        where = [f"{TABLE} MATCH ?"]
        params: list = [q]
        since_dt, until_dt = _parse_ts(since), _parse_ts(until)
        # header_ts values are ISO-8601 with UTC offset; normalizing the
        # bounds to the same form makes lexicographic comparison correct.
        if since_dt is not None:
            where.append("header_ts >= ?")
            params.append(since_dt.isoformat())
        if until_dt is not None:
            where.append("header_ts <= ?")
            params.append(until_dt.isoformat())
        if source is not None:
            where.append("lower(source) LIKE ?")
            params.append(f"%{source.lower()}%")

        sql = (
            f"SELECT slug, header_ts, source, name, "
            f"snippet({TABLE}, -1, '**', '**', '…', 20) AS snip, "
            f"rank, byte_start "
            f"FROM {TABLE} WHERE {' AND '.join(where)} "
            f"ORDER BY rank LIMIT ?"
        )
        try:
            cur = self._conn.execute(sql, (*params, limit))
        except sqlite3.OperationalError:
            # Raw text wasn't valid FTS5 syntax — retry with each token
            # quoted as a phrase (implicit AND).
            safe = _sanitize_query(q)
            if not safe:
                return []
            params[0] = safe
            try:
                cur = self._conn.execute(sql, (*params, limit))
            except sqlite3.OperationalError as exc:
                logger.warning("wiki.fts query failed (%r): %s", q, exc)
                return []
        return [
            {
                "slug": slug,
                "header_ts": header_ts,
                "source": src,
                "name": name,
                "snippet": snip,
                "rank": rank,
                "byte_start": byte_start,
            }
            for slug, header_ts, src, name, snip, rank, byte_start in cur
        ]

    def count(self) -> int:
        return self._conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass
