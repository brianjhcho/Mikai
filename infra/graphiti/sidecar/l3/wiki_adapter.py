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
- `ingest_episode` appends to ~/.mikai/wiki/wiki-episodes.log (JSONL) so
  new episodes are captured without a graph — dream loops or future
  wiki-regen can consume this log to rebuild the wiki.
- All node/edge/community primitives return sensible empty or
  wiki-derived defaults. The wiki has no bitemporal edge structure, so
  history() returns empty superseded lists.

Load-bearing insight: at wiki scale (~50KB = ~15K tokens), any modern
LLM holds the whole wiki in context on every FIGS tick. Search is
delegated to the LLM reading the concatenated wiki, not to a database.
Graph substrate is over-engineered for solo-user, curated-wiki scale
and becomes appropriate at 100K+ episodes.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict
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

logger = logging.getLogger("mikai-graphiti.wiki-adapter")

WIKI_ROOT = Path(
    os.environ.get("MIKAI_WIKI_ROOT", str(Path.home() / ".mikai" / "wiki"))
)
EPISODE_LOG = WIKI_ROOT / "wiki-episodes.log"
MAX_WIKI_CHARS = int(os.environ.get("MIKAI_WIKI_MAX_CHARS", "120000"))

# Files the adapter concatenates as the "wiki bundle." Order matters —
# wiki-ontology-v1.md (structured 9-dim) leads, wiki.md (Who/Now/Wants)
# follows. Both are optional; missing files are silently skipped.
WIKI_FILES = ("wiki-ontology-v1.md", "wiki.md")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _read_wiki_bundle() -> str:
    """Concatenate all present wiki files into one string, capped at
    MAX_WIKI_CHARS. Truncation prefers keeping the head (structured
    ontology) over the tail."""
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
    if not EPISODE_LOG.exists():
        return 0
    try:
        with EPISODE_LOG.open("r") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _match_wiki_sections(query: str, k: int = 5) -> list[tuple[str, str]]:
    """Return up to k (heading, body-preview) pairs for wiki sections
    whose heading or body substring-matches the query (case-insensitive).
    Sections are `###`-level headings; if none match, returns the top-N
    sections verbatim so the caller always has substrate to reason from.
    """
    bundle = _read_wiki_bundle()
    # Split into `###`-level sections; keep their heading text.
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
        # Fallback: return the top-N sections so the LLM has something.
        return sections[:k]
    return matches[:k]


def _dimensions() -> list[Community]:
    """Return the 9 life dimensions as communities so callers that ask
    for community structure receive the wiki's organizing groups."""
    # Heading-based extraction: any `### N. <name>` line in the wiki
    # becomes a community. Falls back to a hardcoded 9-dim list if the
    # wiki has no headings.
    bundle = _read_wiki_bundle()
    names: list[str] = []
    for line in bundle.splitlines():
        m = re.match(r"^###\s+(\d+)\.\s+(.+?)\s*$", line)
        if m:
            names.append(m.group(2).strip())
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


# ── Adapter ──────────────────────────────────────────────────────────────────


class WikiAdapter(L3Backend):
    """L3 substrate reading from ~/.mikai/wiki/*.md. No graph, no Docker,
    no sidecar boot required. Selected via MIKAI_L3_BACKEND=wiki."""

    # ── Write ──

    async def ingest_episode(self, episode: Episode) -> IngestResult:
        """Append the episode to the JSONL log. No extraction; no
        entities or edges are produced — hence zeros in the result."""
        EPISODE_LOG.parent.mkdir(parents=True, exist_ok=True)
        row = asdict(episode)
        # datetime → ISO string for JSON serialization
        if isinstance(row.get("reference_time"), datetime):
            row["reference_time"] = row["reference_time"].isoformat()
        try:
            with EPISODE_LOG.open("a") as f:
                f.write(json.dumps(row) + "\n")
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
        sections = _match_wiki_sections(query.text, k=query.num_results)
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
                valid_at=_wiki_mtime() or now,
                invalid_at=None,
                expired_at=None,
                created_at=_wiki_mtime() or now,
                episodes=[],
                confidence=None,
                score=None,
            )
            for i, (heading, body) in enumerate(sections)
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
        sections = _match_wiki_sections(query.text, k=query.num_results)
        now = datetime.now(timezone.utc)
        return [
            Node(
                uuid=f"wiki-node-{i}",
                name=heading,
                labels=["WikiSection"],
                summary=body[:200] if body else None,
                created_at=_wiki_mtime() or now,
            )
            for i, (heading, body) in enumerate(sections)
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
        sections = _match_wiki_sections(query, k=num_results)
        return [
            SourceEpisode(
                uuid=f"wiki-source-{i}",
                content=body.strip(),
                source=heading,
                source_description="wiki-adapter",
                valid_at=_wiki_mtime(),
                score=None,
            )
            for i, (heading, body) in enumerate(sections)
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
        # Nothing to release — the adapter holds no long-lived handles.
        return None
