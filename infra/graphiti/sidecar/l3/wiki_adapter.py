"""WikiAdapter — an L3Backend implementation backed by wiki files at
~/.mikai/wiki/*.md instead of a graph store.

Selected via MIKAI_L3_BACKEND=wiki. Enables MIKAI to run without Docker,
Neo4j, or the Graphiti sidecar — a latency-first, simplicity-first
substrate for testing higher layers (Sumimasen timing gate, calendar
planner, feedback loop, life-tier config) against a real user context
without dragging graph infrastructure along.

Design commitment (ARCH-024 port, D-041 primitives-only):
- Only the port methods are implemented; no MIKAI-side reasoning leaks in.
- `search` and `get_source` return wiki sections as pseudo-Edges /
  SourceEpisodes so downstream FIGS code that already speaks the port
  contract keeps working unchanged.
- `ingest_episode` appends the episode verbatim to ~/.mikai/wiki/wiki.md
  as a dated, source-tagged section (Karpathy design: verbatim capture
  with metadata, no entity resolution — the LLM resolves at query time),
  plus a one-line audit entry in ~/.mikai/wiki/wiki-episodes.log
  ("<iso-ts> <source> <byte-count>") and a byte-offset row in
  ~/.mikai/wiki/wiki.index. Re-ingesting an already-indexed episode
  (same header identity + content byte count) is a no-op.
- All node/edge/community primitives return sensible empty or
  wiki-derived defaults. The wiki has no bitemporal edge structure, so
  history() returns empty superseded lists.

Scale note (2026-08-05 historical backfill): wiki.md is now ~27MB /
8,000+ dated sections. The original design read the whole file capped at
120KB — blind to 99% of the content. Reads now go through WikiIndex
(sidecar/l3/wiki_index.py): a JSONL byte-offset index over the dated
`### <iso-ts> — <source> — <name>` sections. Queries filter the index
(header timestamp / source / name regex) and seek-read only the matching
sections. A safety net caps the total bytes returned to any caller
(MIKAI_WIKI_MAX_RETURN_BYTES, default 1MB) so LLM callers never receive
27MB by accident. The legacy whole-bundle path survives only as a
fallback for wikis with no dated sections.

Ranking layer (docs/RETRIEVAL_STACK.md): free-text queries route through
WikiFTS (sidecar/l3/wiki_fts.py) — a disposable SQLite FTS5 companion at
~/.mikai/wiki/wiki.fts.db giving BM25-ranked full-text hits over section
name+body — then fall back to the index-metadata match when FTS is
unavailable, disabled (MIKAI_WIKI_FTS_DISABLED=1), or hitless. WikiIndex
stays the source of truth for section boundaries; FTS rows map back to
index records by byte_start before any content is read.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from sidecar.l3.port import (
    Community,
    Edge,
    Episode,
    GraphStats,
    HistoryResult,
    IngestResult,
    L3Backend,
    Node,
    SearchQuery,
    SourceEpisode,
    Subgraph,
)
from sidecar.l3.wiki_fts import WikiFTS
from sidecar.l3.wiki_index import WikiIndex, _parse_ts

logger = logging.getLogger("mikai-graphiti.wiki-adapter")

WIKI_ROOT = Path(
    os.environ.get("MIKAI_WIKI_ROOT", str(Path.home() / ".mikai" / "wiki"))
)
# Raw append-only capture (wiki.md + wiki.index + wiki.fts.db) lives
# OUTSIDE the vault so Obsidian's indexer doesn't stat/scan the 57MB
# markdown file on every open. Vault-side stays at WIKI_ROOT for
# concepts/, sources/, ontology, etc. Overridable via env for tests.
WIKI_RAW = Path(
    os.environ.get("MIKAI_WIKI_RAW", str(Path.home() / ".mikai" / "wiki-raw"))
)

# Legacy cap for the whole-bundle fallback path only (wikis with no
# dated sections). Selective reads are governed by MAX_RETURN_BYTES.
MAX_WIKI_CHARS = int(os.environ.get("MIKAI_WIKI_MAX_CHARS", "120000"))

# Safety net: maximum total bytes any single call returns to a caller,
# tunable per call via the max_bytes argument on read_sections().
MAX_RETURN_BYTES = int(
    os.environ.get("MIKAI_WIKI_MAX_RETURN_BYTES", str(1_048_576))
)

# Files the adapter concatenates as the legacy "wiki bundle." Order
# matters — wiki-ontology-v1.md (structured 9-dim) leads, wiki.md
# (Who/Now/Wants) follows. Both are optional; missing files are skipped.
WIKI_FILES = ("wiki-ontology-v1.md", "wiki.md")

ONTOLOGY_FILE = "wiki-ontology-v1.md"


# ── Path helpers (resolved at call time so tests can repoint WIKI_ROOT) ──────


def _wiki_md() -> Path:
    return WIKI_RAW / "wiki.md"


def _index_path() -> Path:
    return WIKI_RAW / "wiki.index"


def _episode_log() -> Path:
    return WIKI_ROOT / "wiki-episodes.log"


def _fts_db() -> Path:
    env = os.environ.get("MIKAI_WIKI_FTS_DB")
    if env:
        return Path(env)
    return WIKI_RAW / "wiki.fts.db"


def _fts_disabled() -> bool:
    """Kill switch: MIKAI_WIKI_FTS_DISABLED=1 skips all FTS paths and
    restores pure index-metadata retrieval."""
    return os.environ.get("MIKAI_WIKI_FTS_DISABLED", "") == "1"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _read_wiki_bundle() -> str:
    """LEGACY fallback: concatenate all present wiki files into one
    string, capped at MAX_WIKI_CHARS. Only used when the wiki has no
    dated sections to index (pre-backfill layout); all indexed reads go
    through WikiIndex windowed reads instead."""
    parts: list[str] = []
    for name in WIKI_FILES:
        p = WIKI_ROOT / name
        if p.exists():
            try:
                parts.append(f"# === {name} ===\n{p.read_text(errors='replace')}")
            except OSError as exc:
                logger.warning("wiki file unreadable: %s (%s)", p, exc)
    if not parts:
        return "(wiki empty — no files at MIKAI_WIKI_ROOT)"
    bundle = "\n\n".join(parts)
    if len(bundle) > MAX_WIKI_CHARS:
        bundle = bundle[:MAX_WIKI_CHARS] + "\n\n[…truncated at MIKAI_WIKI_MAX_CHARS]"
    return bundle


def _wiki_bytes() -> int:
    return sum(
        (WIKI_ROOT / n).stat().st_size for n in WIKI_FILES if (WIKI_ROOT / n).exists()
    )


def _wiki_mtime() -> datetime | None:
    latest: float | None = None
    for n in WIKI_FILES:
        p = WIKI_ROOT / n
        if p.exists():
            m = p.stat().st_mtime
            latest = m if latest is None else max(latest, m)
    if latest is None:
        return None
    return datetime.fromtimestamp(latest, tz=timezone.utc)


def _episode_count() -> int:
    log = _episode_log()
    if not log.exists():
        return 0
    try:
        with log.open("r") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _match_wiki_sections_bundle(query: str, k: int = 5) -> list[tuple[str, str]]:
    """LEGACY fallback matcher over the capped bundle — used only when
    the index has no dated sections. Returns up to k (heading,
    body-preview) pairs whose heading or body substring-matches the
    query (case-insensitive); if none match, returns the top-N sections
    verbatim so the caller always has substrate to reason from."""
    bundle = _read_wiki_bundle()
    sections: list[tuple[str, str]] = []
    current_heading = "(intro)"
    current_body: list[str] = []
    for line in bundle.splitlines():
        if line.startswith("### "):
            if current_body:
                sections.append((current_heading, "\n".join(current_body)))
            current_heading = line.strip("# ").strip()
            current_body = []
        else:
            current_body.append(line)
    if current_body:
        sections.append((current_heading, "\n".join(current_body)))

    q = query.lower().strip()
    if not q:
        return sections[:k]
    matches = [
        (h, b) for h, b in sections
        if q in h.lower() or q in b.lower()
    ]
    if not matches:
        return sections[:k]
    return matches[:k]


def _dimensions() -> list[Community]:
    """Return the 9 life dimensions as communities so callers that ask
    for community structure receive the wiki's organizing groups."""
    # Heading-based extraction from the (small) ontology file: any
    # `### N. <name>` line becomes a community. Falls back to a
    # hardcoded 9-dim list. Deliberately does NOT scan wiki.md — that
    # file is 27MB of episodes, not ontology.
    names: list[str] = []
    ontology = WIKI_ROOT / ONTOLOGY_FILE
    if ontology.exists():
        try:
            for line in ontology.read_text(errors="replace").splitlines():
                m = re.match(r"^###\s+(\d+)\.\s+(.+?)\s*$", line)
                if m:
                    names.append(m.group(2).strip())
        except OSError as exc:
            logger.warning("ontology file unreadable: %s (%s)", ontology, exc)
    if not names:
        names = [
            "AI Career / MIKAI Build",
            "Where to Live",
            "Business Opportunities",
            "Relationship with Germaine",
            "Family Obligations",
            "Health / Body",
            "Craft / Hobbies",
            "Financial / Trading",
            "Recurring Themes",
        ]
    return [
        Community(uuid=f"wiki-dim-{i+1}", name=n, summary=None)
        for i, n in enumerate(names)
    ]


def _section_heading(record: dict) -> str:
    return (
        f"{record.get('header_ts', '?')} — {record.get('source', '?')} — "
        f"{record.get('name', '?')}"
    )


def _section_body(text: str) -> str:
    """Section text minus its header line (and stripped)."""
    _, _, rest = text.partition("\n")
    return rest.strip()


# ── Adapter ──────────────────────────────────────────────────────────────────


class WikiAdapter(L3Backend):
    """L3 substrate reading from ~/.mikai/wiki/*.md. No graph, no Docker,
    no sidecar boot required. Selected via MIKAI_L3_BACKEND=wiki.

    Reads are windowed: a WikiIndex over wiki.md's dated sections lets
    every query seek-read only the sections it needs."""

    def __init__(self) -> None:
        self._index: WikiIndex | None = None
        self._fts: WikiFTS | None = None
        self._fts_synced: bool = False

    # ── Index plumbing ──

    def _get_index(self) -> WikiIndex:
        """Load (or build) the byte-offset index, then bring it up to
        date if wiki.md grew since the last scan. The wiki is
        append-only in normal operation, so freshness is a size check
        plus an incremental tail scan — never a full re-read."""
        wiki = _wiki_md()
        if self._index is None:
            idx_path = _index_path()
            if idx_path.exists():
                self._index = WikiIndex.load(idx_path)
            elif wiki.exists():
                logger.info("wiki.index missing — building from %s", wiki)
                self._index = WikiIndex.build(wiki)
                self._index.save(idx_path)
            else:
                self._index = WikiIndex(index_path=idx_path)
        size = wiki.stat().st_size if wiki.exists() else 0
        if size != self._index.scanned_bytes and wiki.exists():
            self._index.refresh(wiki)
            self._index.save(_index_path())
        return self._index

    def _get_fts(self) -> WikiFTS | None:
        """Load (build if missing, rebuild if stale) the FTS5 companion
        index. Returns None when the kill switch is set or FTS5 is
        unavailable in this interpreter — callers then fall back to
        index-metadata retrieval. The staleness check (row count vs
        index section count, plus a deleted-DB check) runs once per
        adapter instance; our own ingests keep the DB in sync after
        that."""
        if _fts_disabled():
            return None
        if not WikiFTS.available():
            return None
        idx = self._get_index()
        db = _fts_db()
        if self._fts is not None and not db.exists():
            # DB deleted out from under us — force a rebuild.
            self._fts.close()
            self._fts, self._fts_synced = None, False
        if self._fts is None or not self._fts_synced:
            try:
                self._fts = WikiFTS.rebuild_if_stale(idx, _wiki_md(), db)
                self._fts_synced = self._fts is not None
            except Exception as exc:  # derived artifact — never fatal
                logger.warning("wiki.fts unavailable: %s", exc)
                self._fts, self._fts_synced = None, False
        return self._fts

    def search_fts(
        self,
        query: str,
        limit: int = 10,
        since=None,
        until=None,
        source: str | None = None,
    ) -> list[dict]:
        """BM25-ranked keyword search over wiki sections (internal
        surface — the port API is unchanged). Returns WikiFTS hit dicts
        ({slug, header_ts, source, name, snippet, rank, byte_start})
        best-first; [] when FTS is disabled/unavailable or nothing
        matches."""
        fts = self._get_fts()
        if fts is None:
            return []
        return fts.search(
            query, since=since, until=until, source=source, limit=limit
        )

    def _materialize_records(
        self, matched: list[dict]
    ) -> list[tuple[str, str, datetime | None]]:
        """Windowed-read the given index records into (heading, body,
        valid_at) triples, total bytes capped at MAX_RETURN_BYTES."""
        wiki = _wiki_md()
        out: list[tuple[str, str, datetime | None]] = []
        budget = MAX_RETURN_BYTES
        for r in matched:
            span = r["byte_end"] - r["byte_start"]
            if span > budget:
                if not out:  # single oversize section: hard-truncate
                    text = WikiIndex.read_section(wiki, r)
                    body = _section_body(text)[:budget]
                    out.append(
                        (
                            _section_heading(r),
                            body + "\n[…truncated at MIKAI_WIKI_MAX_RETURN_BYTES]",
                            _parse_ts(r.get("header_ts")),
                        )
                    )
                break
            text = WikiIndex.read_section(wiki, r)
            out.append(
                (
                    _section_heading(r),
                    _section_body(text),
                    _parse_ts(r.get("header_ts")),
                )
            )
            budget -= span
        return out

    def _select_sections(
        self, query: str, k: int
    ) -> list[tuple[str, str, datetime | None]]:
        """Resolve a free-text query to up to k wiki sections. Primary
        path: BM25-ranked FTS5 over full section text (name + body).
        Fallback (FTS disabled/unavailable/no hits): the legacy
        index-metadata match — exact-phrase on header metadata, then
        per-token, then most-recent fill. Either way the result is
        windowed reads only, total bytes capped at MAX_RETURN_BYTES."""
        idx = self._get_index()
        if not idx.records:
            # Pre-backfill layout (no dated sections): legacy bundle path.
            return [
                (h, b, _wiki_mtime())
                for h, b in _match_wiki_sections_bundle(query, k=k)
            ]

        q = query.strip()

        # ── Primary: FTS5 BM25 ranking ──
        if q:
            hits = self.search_fts(q, limit=k)
            if hits:
                by_start = {r.get("byte_start"): r for r in idx.records}
                ranked = [
                    by_start[h["byte_start"]]
                    for h in hits
                    if h["byte_start"] in by_start
                ]
                if ranked:
                    return self._materialize_records(ranked)

        # ── Fallback: legacy index-metadata match ──
        matched: list[dict] = []
        seen: set[int] = set()

        def _add(records: list[dict]) -> None:
            for r in records:
                key = r.get("byte_start", id(r))
                if key not in seen:
                    seen.add(key)
                    matched.append(r)

        if q:
            _add(idx.sections_matching(name_pattern=re.escape(q), limit=k))
            if len(matched) < k:
                for token in q.split():
                    if len(matched) >= k:
                        break
                    _add(
                        idx.sections_matching(
                            name_pattern=re.escape(token), limit=k
                        )
                    )
        if len(matched) < k:
            # Fill with the most recent sections so the caller always
            # has substrate to reason from (old-behavior parity).
            _add(idx.sections_matching(limit=k))
        matched = matched[:k]
        return self._materialize_records(matched)

    # ── Selective read (new surface; additive, used by future callers) ──

    def read_sections(
        self,
        *,
        since=None,
        until=None,
        source: str | None = None,
        name_pattern: str | None = None,
        limit: int | None = None,
        max_bytes: int | None = None,
    ) -> str:
        """Windowed replacement for the old whole-bundle read: return
        the concatenated text of sections matching the given hints
        (header-timestamp window, source substring, name regex), capped
        at max_bytes (default MIKAI_WIKI_MAX_RETURN_BYTES). Sections
        come back in chronological order."""
        idx = self._get_index()
        cap = MAX_RETURN_BYTES if max_bytes is None else max_bytes
        if not idx.records:
            bundle = _read_wiki_bundle()
            return bundle[:cap]
        records = idx.sections_matching(
            since=since,
            until=until,
            source=source,
            name_pattern=name_pattern,
            limit=limit,
        )
        wiki = _wiki_md()
        parts: list[str] = []
        used = 0
        for r in records:
            span = r["byte_end"] - r["byte_start"]
            if used + span > cap:
                parts.append("[…truncated at max_bytes]")
                break
            parts.append(WikiIndex.read_section(wiki, r).strip("\n"))
            used += span
        return "\n\n".join(parts)

    # ── Write ──

    async def ingest_episode(self, episode: Episode) -> IngestResult:
        """Verbatim capture (Karpathy wiki design): append the episode to
        wiki.md as a dated, source-tagged `###` section, plus a one-line
        audit entry in wiki-episodes.log and a byte-offset row in
        wiki.index. No extraction, no entity resolution (the LLM
        resolves at query time). Idempotent: an episode whose header
        identity (reference_time + source + name) and content byte
        count already appear in the index is skipped entirely — neither
        wiki.md nor the index is touched."""
        WIKI_ROOT.mkdir(parents=True, exist_ok=True)
        wiki_md = _wiki_md()
        ingested_at = datetime.now(timezone.utc)
        ref = episode.reference_time
        ref_iso = ref.isoformat() if isinstance(ref, datetime) else str(ref)
        title = episode.name or "(untitled)"
        content_bytes = len(episode.content.rstrip().encode("utf-8"))

        idx = self._get_index()
        # Identity-only dedup: (reference_time, source, name). Passing
        # content_bytes here would allow duplicate writes whenever the
        # same episode is re-ingested with a different body — the exact
        # scenario that produced truncated-duplicate sections when
        # claude-threads re-fetched a turn whose export payload shrank
        # (see wiki.md before the 2026-08-07 cleanup: TSA 2.0::006::human
        # appeared twice, second copy truncated mid-sentence). If the
        # body legitimately changed for a real reason, that belongs in a
        # separate "revise section" path, not a silent second append.
        if idx.has_section(
            ref_iso, episode.source_description, title
        ):
            logger.info(
                "wiki ingest skipped (duplicate): %s — %s — %s",
                ref_iso, episode.source_description, title,
            )
            return IngestResult(
                episode_uuid=f"wiki-ep-{_episode_count():06d}-dup",
                entities_extracted=0,
                edges_extracted=0,
            )

        section = (
            f"\n\n### {ref_iso} — {episode.source_description} — {title}\n"
            f"<!-- ingested={ingested_at.isoformat()} "
            f"group_id={episode.group_id} -->\n\n"
            f"{episode.content.rstrip()}\n"
        )
        pre_size = wiki_md.stat().st_size if wiki_md.exists() else 0
        # wiki.md append is the write of record — a failure here must
        # surface to the caller so daemons don't mark content ingested.
        with wiki_md.open("a") as f:
            f.write(section)
        # Index row: byte_start points at the header line (skip the two
        # leading newlines the section string carries).
        section_bytes = len(section.encode("utf-8"))
        record = {
            "header_ts": ref_iso,
            "source": episode.source_description,
            "name": title,
            "byte_start": pre_size + 2,
            "byte_end": pre_size + section_bytes,
            "content_bytes": content_bytes,
        }
        idx.append_section(record)
        # FTS companion row (derived, idempotent by slug — failures are
        # non-fatal; rebuild_if_stale reconciles on the next adapter).
        fts = self._get_fts()
        if fts is not None:
            try:
                fts.append_section(record, episode.content.rstrip())
            except Exception as exc:
                logger.warning("wiki.fts append failed: %s", exc)
                self._fts_synced = False
        # Audit log: "<iso-ts> <source> <byte-count>", one line per episode.
        n_bytes = len(episode.content.encode("utf-8"))
        try:
            with _episode_log().open("a") as f:
                f.write(
                    f"{ingested_at.isoformat()} "
                    f"{episode.source_description} {n_bytes}\n"
                )
        except OSError as exc:
            logger.warning("wiki episode log write failed: %s", exc)
        # Stable synthetic uuid — line number in the log.
        return IngestResult(
            episode_uuid=f"wiki-ep-{_episode_count():06d}",
            entities_extracted=0,
            edges_extracted=0,
        )

    # ── Read — edges ──

    async def search(self, query: SearchQuery) -> list[Edge]:
        """Return matched wiki sections as pseudo-Edges. FIGS's prompt
        builder concatenates edge `fact` strings, so packaging wiki text
        as facts keeps the downstream code path unchanged.
        """
        sections = self._select_sections(query.text, k=query.num_results)
        now = datetime.now(timezone.utc)
        return [
            Edge(
                uuid=f"wiki-section-{i}",
                source_uuid=f"wiki-section-{i}",
                target_uuid=f"wiki-section-{i}",
                source_name=heading,
                target_name=heading,
                name="WIKI_SECTION",
                fact=body.strip(),
                valid_at=valid_at or _wiki_mtime() or now,
                invalid_at=None,
                expired_at=None,
                created_at=valid_at or _wiki_mtime() or now,
                episodes=[],
                confidence=None,
                score=None,
            )
            for i, (heading, body, valid_at) in enumerate(sections)
        ]

    async def history(
        self, query: SearchQuery, as_of: datetime | None = None
    ) -> HistoryResult:
        """Wiki has no bitemporal edge history. Return current-only
        (from search) with empty superseded — safe default for callers."""
        current = await self.search(query)
        return HistoryResult(current=current, superseded=[])

    async def edges_between(
        self,
        node_uuids: list[str],
        *,
        as_of: datetime | None = None,
        include_invalidated: bool = False,
    ) -> list[Edge]:
        return []

    # ── Read — nodes ──

    async def search_nodes(self, query: SearchQuery) -> list[Node]:
        """Return wiki-section headings as nodes. Useful for callers that
        want a list of dimension names or thread topics."""
        sections = self._select_sections(query.text, k=query.num_results)
        now = datetime.now(timezone.utc)
        return [
            Node(
                uuid=f"wiki-node-{i}",
                name=heading,
                labels=["WikiSection"],
                summary=body[:200] if body else None,
                created_at=valid_at or _wiki_mtime() or now,
            )
            for i, (heading, body, valid_at) in enumerate(sections)
        ]

    async def get_node(self, uuid: str) -> Node | None:
        return None

    async def expand(
        self,
        uuid: str,
        *,
        max_edges: int = 20,
        include_invalidated: bool = False,
    ) -> Subgraph:
        # No expansion in a flat wiki. Raise per port contract when the
        # center doesn't exist; here nothing exists, so raise consistently.
        raise KeyError(f"WikiAdapter: node {uuid} not found (no graph)")

    # ── Read — episodes ──

    async def get_source(
        self, query: str, num_results: int = 5
    ) -> list[SourceEpisode]:
        """Return matched wiki sections as SourceEpisode entries. This is
        the primitive FIGS uses when it wants raw prose behind a fact."""
        sections = self._select_sections(query, k=num_results)
        return [
            SourceEpisode(
                uuid=f"wiki-source-{i}",
                content=body.strip(),
                source=heading,
                source_description="wiki-adapter",
                valid_at=valid_at or _wiki_mtime(),
                score=None,
            )
            for i, (heading, body, valid_at) in enumerate(sections)
        ]

    # ── Read — global ──

    async def stats(self) -> GraphStats:
        """Wiki-scale approximations: entities ~ dimensions, edges 0
        (no graph edges exist), episodes = log count, communities = 9
        (or discovered heading count), orphans 0."""
        dims = _dimensions()
        return GraphStats(
            entities=len(dims),
            edges=0,
            episodes=_episode_count(),
            communities=len(dims),
            orphans=0,
        )

    async def communities(self) -> list[Community]:
        return _dimensions()

    # ── Lifecycle ──

    async def close(self) -> None:
        if self._fts is not None:
            self._fts.close()
            self._fts, self._fts_synced = None, False
        return None
