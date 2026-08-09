"""Context composer + entry point for mikai_ask.

Assembles ONE prompt per query, ordered system-context → retrieved
context → question:

  1. PROFILE.md verbatim (≤1 page, inviolate)
  2. BRAIN.md "Current priorities" section only (inviolate)
  3. FTS5 top-k=8 wiki sections (WikiFTS; WikiIndex 30-day window fill
     when FTS returns <3)
  4. Entity files whose slug appears in the query or in the top-3 wiki
     hits (full body, cap 5)
  5. Active-thread frontmatter + first log line (state in acting /
     decided / evaluating)
  6. The query itself

Total prompt capped at ~150K chars. Over budget, trimming order is
FTS → entities → threads; PROFILE and priorities are never trimmed.

WikiIndex / WikiFTS are loaded standalone from their files (same trick
as dream_bootstrap.py) because importing them via `sidecar.l3` would
drag in graphiti_core, which only exists in the sidecar venv.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import infra.mikai_llm as mikai_llm  # noqa: E402
import infra.mikai_brain as brain  # noqa: E402
from infra.mikai_brain import ledger, threads as brain_threads  # noqa: E402

PROMPT_CHAR_CAP = 150_000
FTS_TOP_K = 8
ENTITY_CAP = 5
SNIPPET_CHARS = 200
FALLBACK_WINDOW_DAYS = 30
ACTIVE_STATES = ("acting", "decided", "evaluating")
SEP = "\n---\n"

_PREAMBLE = (
    "You are MIKAI, Brian's personal task-state awareness engine. Answer "
    "his question using the context assembled from his own substrate "
    "below (profile, priorities, wiki sections, entities, active "
    "threads). Ground every claim in that context; where the substrate "
    "is silent, say so plainly instead of inventing. Match his "
    "communication style as described in the profile."
)


# ── Wiki module loading (standalone, no sidecar package import) ──────────

_wiki_index_mod = None
_wiki_fts_mod = None


def _load_wiki_modules():
    """Load wiki_index.py + wiki_fts.py without touching sidecar.l3's
    __init__ (which imports graphiti_core — sidecar-venv only).
    wiki_fts.py does `from sidecar.l3.wiki_index import …`, so the
    standalone wiki_index module is registered in sys.modules under that
    dotted name, with stub parent packages, before wiki_fts executes."""
    global _wiki_index_mod, _wiki_fts_mod
    if _wiki_fts_mod is not None:
        return _wiki_index_mod, _wiki_fts_mod

    l3 = _REPO / "infra" / "graphiti" / "sidecar" / "l3"

    def _load(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    if "sidecar.l3.wiki_index" in sys.modules:
        _wiki_index_mod = sys.modules["sidecar.l3.wiki_index"]
    else:
        _wiki_index_mod = _load("sidecar.l3.wiki_index", l3 / "wiki_index.py")
        sidecar_pkg = sys.modules.setdefault("sidecar", types.ModuleType("sidecar"))
        l3_pkg = sys.modules.setdefault("sidecar.l3", types.ModuleType("sidecar.l3"))
        sidecar_pkg.l3 = l3_pkg
        l3_pkg.wiki_index = _wiki_index_mod

    _wiki_fts_mod = _load("_mikai_ask_wiki_fts", l3 / "wiki_fts.py")
    return _wiki_index_mod, _wiki_fts_mod


def _wiki_dir() -> Path:
    return Path.home() / ".mikai" / "wiki"


# ── Retrieval pieces ─────────────────────────────────────────────────────


def _profile_text() -> str:
    p = brain.BRAIN_ROOT / "PROFILE.md"
    if p.exists():
        return p.read_text().strip()
    return "(no PROFILE.md — profile not yet seeded)"


def _user_model_text() -> str:
    """USER_MODEL.md — the compiled observed-model layer above PROFILE.md.
    Byte-capped at ~2KB by the compiler (see infra/mikai_brain/user_model.py),
    so it always fits in the composed prompt. Empty string when the model
    hasn't been built yet — the composer skips the section entirely rather
    than injecting a placeholder that would eat context for nothing."""
    p = brain.BRAIN_ROOT / "USER_MODEL.md"
    if p.exists():
        return p.read_text().strip()
    return ""


def _priorities_text() -> str:
    if not brain.BRAIN_MD.exists():
        return "(no BRAIN.md)"
    m = re.search(
        r"^## Current priorities\s*$(.*?)(?=^## |\Z)",
        brain.BRAIN_MD.read_text(),
        re.MULTILINE | re.DOTALL,
    )
    return m.group(1).strip() if m else "(no Current priorities section in BRAIN.md)"


def _fts_hits(query: str, k: int = FTS_TOP_K) -> list[dict]:
    """BM25 top-k over the wiki. Returns WikiFTS.search() rows. Empty on
    a missing wiki or FTS5-less interpreter — callers fall back to the
    WikiIndex window.

    Recursive-contamination filter: same-day claude-code sections are
    dropped from results by default. Reason: every mikai_ask call over
    a MIKAI-related question is itself ingested (via the claude-thread
    watcher's coverage of active claude-code sessions), and the ingested
    turns contain dense matches for the query's own vocabulary ("key
    insights", "cite specific turns", …). Left unfiltered, retrieval
    for a question about a historical thread returns the CURRENT
    conversation asking the question. Verified 2026-08-07: every hit
    for "Task State Awareness 2.0" came from that morning's own ask
    turns. Filter is skipped when MIKAI_ASK_ALLOW_SAMEDAY_CLAUDECODE=1.
    We overfetch (k * 3) before filtering so the top-k doesn't shrink."""
    wiki_md = _wiki_dir() / "wiki.md"
    if not wiki_md.exists():
        return []
    wiki_index_mod, wiki_fts_mod = _load_wiki_modules()
    idx = _load_index(wiki_index_mod, wiki_md)
    fts = wiki_fts_mod.WikiFTS.rebuild_if_stale(idx, wiki_md)
    if fts is None:
        return []
    try:
        raw = fts.search(query, limit=k * 3)
    finally:
        fts.close()
    if os.environ.get("MIKAI_ASK_ALLOW_SAMEDAY_CLAUDECODE") == "1":
        return raw[:k]
    today_iso = datetime.now(timezone.utc).date().isoformat()
    kept: list[dict] = []
    for h in raw:
        source = str(h.get("source", ""))
        header_ts = str(h.get("header_ts", ""))
        if source.startswith("claude-code") and header_ts.startswith(today_iso):
            continue
        kept.append(h)
        if len(kept) >= k:
            break
    return kept


def _load_index(wiki_index_mod, wiki_md: Path):
    idx_path = _wiki_dir() / "wiki.index"
    if idx_path.exists():
        idx = wiki_index_mod.WikiIndex.load(idx_path)
        idx.refresh(wiki_md)
    else:
        idx = wiki_index_mod.WikiIndex.build(wiki_md)
        idx.save(idx_path)
    return idx


def _section_snippet(section_text: str, limit: int = SNIPPET_CHARS) -> str:
    """First `limit` chars of a section's body (header + ingested
    comment stripped)."""
    lines = section_text.split("\n")
    body_start = 1
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    if body_start < len(lines) and lines[body_start].lstrip().startswith("<!--"):
        body_start += 1
    body = "\n".join(lines[body_start:]).strip()
    return body[:limit] + ("…" if len(body) > limit else "")


def _window_fill(existing: list[dict], k: int = FTS_TOP_K) -> list[dict]:
    """When FTS finds <3 sections, fill candidates from the WikiIndex
    30-day recency window (most recent last per sections_matching)."""
    wiki_md = _wiki_dir() / "wiki.md"
    if not wiki_md.exists():
        return []
    wiki_index_mod, _ = _load_wiki_modules()
    idx = _load_index(wiki_index_mod, wiki_md)
    since = datetime.now(timezone.utc) - timedelta(days=FALLBACK_WINDOW_DAYS)
    have = {h.get("slug") for h in existing}
    out: list[dict] = []
    recent = idx.sections_matching(since=since, limit=k)
    for rec in reversed(recent):  # most recent first
        slug = (
            f"{rec.get('header_ts', '?')}|{rec.get('source', '?')}|"
            f"{rec.get('name', '?')}"
        )
        if slug in have:
            continue
        text = idx.read_section(wiki_md, rec)
        out.append(
            {
                "slug": slug,
                "header_ts": rec.get("header_ts", ""),
                "source": rec.get("source", ""),
                "name": rec.get("name", ""),
                "snippet": _section_snippet(text),
                "fill": "recent-window",
            }
        )
        if len(existing) + len(out) >= k:
            break
    return out


def _format_hit(h: dict) -> str:
    tag = " (recent-window fill)" if h.get("fill") else ""
    snippet = str(h.get("snippet", ""))[: SNIPPET_CHARS + 1]
    return (
        f"[{h.get('header_ts', '?')}] {h.get('name', '?')} "
        f"— source: {h.get('source', '?')}{tag}\n{snippet}"
    )


def _matching_entities(query: str, hits: list[dict]) -> list[tuple[str, str]]:
    """Entity files whose slug appears in the query (case-insensitive)
    or in any of the top-3 wiki hits. Query matches rank first; cap 5.
    Returns (slug, full file body) pairs."""
    ent_dir = brain.ENTITIES_DIR
    if not ent_dir.exists():
        return []
    q = query.lower()
    top3 = " ".join(
        f"{h.get('name', '')} {h.get('snippet', '')} {h.get('source', '')}"
        for h in hits[:3]
    ).lower()
    query_matched: list[tuple[str, str]] = []
    hit_matched: list[tuple[str, str]] = []
    for path in sorted(ent_dir.glob("*.md")):
        slug = path.stem.lower()
        spaced = slug.replace("-", " ")
        if slug in q or spaced in q:
            query_matched.append((path.stem, path.read_text().strip()))
        elif slug in top3 or spaced in top3:
            hit_matched.append((path.stem, path.read_text().strip()))
    return (query_matched + hit_matched)[:ENTITY_CAP]


def _active_thread_summaries() -> list[tuple[str, str]]:
    """(slug, frontmatter + first log line) for every thread in an active
    state. Never the body — this is a 'what Brian is in the middle of'
    signal, not a content dump."""
    out: list[tuple[str, str]] = []
    for t in brain_threads.load_all():
        if t.state not in ACTIVE_STATES:
            continue
        lines = [
            f"slug: {t.slug}",
            f"title: {t.title}",
            f"state: {t.state} (since {t.state_since or '?'})",
            f"last_activity: {t.last_activity or '?'}",
            f"next_step: {t.next_step or '?'}",
        ]
        if t.next_step_due:
            lines.append(f"next_step_due: {t.next_step_due}")
        if t.entities:
            lines.append(f"entities: {', '.join(t.entities)}")
        if t.department:
            lines.append(f"department: {t.department}")
        if t.log_lines:
            lines.append(f"last log: {t.log_lines[0]}")
        out.append((t.slug, "\n".join(lines)))
    return out


# ── Composition ──────────────────────────────────────────────────────────


def _assemble(
    profile: str,
    user_model: str,
    priorities: str,
    fts_blocks: list[str],
    entity_blocks: list[str],
    thread_blocks: list[str],
    query: str,
) -> str:
    # Order: PROFILE (hand-curated identity) → USER_MODEL (observed
    # themes/values/unresolved) → priorities → retrieved. USER_MODEL
    # sits above PROFILE-adjacent content because it's the "MIKAI
    # actually understands me" signal downstream reasoning needs before
    # touching wiki excerpts. Section is omitted entirely when the
    # model hasn't been compiled yet — no placeholder tax on context.
    parts = [
        _PREAMBLE,
        "## Profile\n\n" + profile,
    ]
    if user_model:
        parts.append("# WHAT MIKAI HAS OBSERVED ABOUT YOU\n\n" + user_model)
    parts.extend([
        "## Current priorities (BRAIN.md)\n\n" + priorities,
        "## Retrieved wiki sections\n\n"
        + ("\n\n".join(fts_blocks) if fts_blocks else "(none retrieved)"),
        "## Entities\n\n"
        + ("\n\n".join(entity_blocks) if entity_blocks else "(none matched)"),
        "## Active threads\n\n"
        + ("\n\n".join(thread_blocks) if thread_blocks else "(none active)"),
        "## Question\n\n" + query,
    ])
    return SEP.join(parts)


def compose(query: str) -> tuple[str, dict]:
    """Build the full prompt for one query. Returns (prompt, stats)."""
    profile = _profile_text()
    user_model = _user_model_text()
    priorities = _priorities_text()

    hits = _fts_hits(query)
    fallback_fill = 0
    if len(hits) < 3:
        fill = _window_fill(hits)
        fallback_fill = len(fill)
        hits = hits + fill

    entities = _matching_entities(query, hits)
    thread_pairs = _active_thread_summaries()
    thread_blocks = [block for _, block in thread_pairs]

    fts_blocks = [_format_hit(h) for h in hits]
    entity_blocks = [f"### entity: {slug}\n\n{body}" for slug, body in entities]

    trimmed = {"fts": 0, "entities": 0, "threads": 0}
    prompt = _assemble(profile, user_model, priorities, fts_blocks,
                       entity_blocks, thread_blocks, query)
    # Over budget: trim FTS first, then entities, then threads. PROFILE
    # and priorities are inviolate.
    while len(prompt) > PROMPT_CHAR_CAP:
        if fts_blocks:
            fts_blocks.pop()
            trimmed["fts"] += 1
        elif entity_blocks:
            entity_blocks.pop()
            trimmed["entities"] += 1
        elif thread_blocks:
            thread_blocks.pop()
            trimmed["threads"] += 1
        else:
            break
        prompt = _assemble(profile, user_model, priorities, fts_blocks,
                           entity_blocks, thread_blocks, query)

    stats = {
        "prompt_chars": len(prompt),
        "fts_hits": len(fts_blocks),
        "fallback_fill": fallback_fill,
        "entities": [slug for slug, _ in entities][: len(entity_blocks)],
        "threads": len(thread_blocks),
        "thread_slugs": [slug for slug, _ in thread_pairs][: len(thread_blocks)],
        "trimmed": trimmed,
        "profile_chars": len(profile),
        "user_model_chars": len(user_model),
        "priorities_chars": len(priorities),
    }
    return prompt, stats


# ── Entry point ──────────────────────────────────────────────────────────


def _summarize_query(query: str, limit: int = 60) -> str:
    one_line = " ".join(query.split())
    return one_line[:limit] + ("…" if len(one_line) > limit else "")


def _print_stats(stats: dict, stream=None) -> None:
    stream = stream or sys.stderr
    print(
        f"[mikai_ask] prompt={stats['prompt_chars']}ch "
        f"fts={stats['fts_hits']} (window-fill={stats['fallback_fill']}) "
        f"entities={','.join(stats['entities']) or '-'} "
        f"threads={stats['threads']} trimmed={stats['trimmed']}",
        file=stream,
    )


def ask(
    query: str,
    *,
    verbose: bool = False,
    dry_run: bool = False,
    return_debug: bool = False,
) -> str | dict:
    """One ask: compose the prompt, call the interactive tier, log the
    run. dry_run returns the composed prompt — no LLM call, no log row.

    return_debug=True changes the return type to a dict
    ``{"answer": str, "retrieved": {...}}`` where ``retrieved`` reports
    what the composer actually pulled (wiki_hits, entity slugs, active
    thread slugs, prompt chars). return_debug=False preserves the plain
    string contract for existing callers. dry_run wins over return_debug.
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("empty query")

    prompt, stats = compose(query)

    if verbose or dry_run:
        _print_stats(stats)
    if dry_run:
        return prompt

    answer = mikai_llm.chat(prompt, tier="interactive")

    ledger.run(
        mode="ask",
        did=(
            f"ask: {_summarize_query(query)} | fts={stats['fts_hits']} "
            f"entities={len(stats['entities'])} threads={stats['threads']}"
        ),
        extra={
            "prompt_chars": stats["prompt_chars"],
            "fts_hits": stats["fts_hits"],
            "fallback_fill": stats["fallback_fill"],
            "entities": stats["entities"],
            "threads": stats["threads"],
            "trimmed": stats["trimmed"],
        },
    )
    if return_debug:
        return {
            "answer": answer,
            "retrieved": {
                "wiki_hits": stats["fts_hits"],
                "entities": stats["entities"],
                "threads": stats["thread_slugs"],
                "prompt_chars": stats["prompt_chars"],
            },
        }
    return answer


def _retrieved_from_stats(stats: dict) -> dict:
    return {
        "wiki_hits": stats["fts_hits"],
        "entities": stats["entities"],
        "threads": stats["thread_slugs"],
        "prompt_chars": stats["prompt_chars"],
    }


def ask_stream(
    query: str,
    *,
    verbose: bool = False,
) -> Iterator[dict]:
    """Streaming variant of ask(): compose the prompt, then yield events.

    Event shapes (all dicts, one per yield):
      * ``{"type": "retrieved", "data": {...}}`` — retrieval metadata,
        yielded FIRST so the client can render the "Retrieved N wiki
        sections…" footnote before any Claude tokens arrive.
      * ``{"type": "chunk", "text": "..."}`` — a text delta from the
        interactive-tier provider (Claude today). Emitted zero or more
        times, in order.
      * ``{"type": "done", "answer": "<full>"}`` — sentinel emitted after
        the provider finishes cleanly. ``answer`` is the concatenated
        stream, handy for callers that want both.
      * ``{"type": "error", "error": "<msg>"}`` — provider failure.
        Yielded in place of ``done``. The generator ends after this.

    Also writes a ledger row on successful completion, mirroring ask().
    Errors do not write a ledger row (matches ask() behavior — a raised
    exception in ask() aborts before ledger.run()).
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("empty query")

    prompt, stats = compose(query)
    if verbose:
        _print_stats(stats)

    # First event: retrieval metadata. Client can paint immediately.
    yield {"type": "retrieved", "data": _retrieved_from_stats(stats)}

    chunks: list[str] = []
    try:
        for piece in mikai_llm.chat_stream(prompt, tier="interactive"):
            if not piece:
                continue
            chunks.append(piece)
            yield {"type": "chunk", "text": piece}
    except Exception as exc:  # noqa: BLE001 — surface to the client
        yield {"type": "error", "error": str(exc)}
        return

    answer = "".join(chunks).strip()

    ledger.run(
        mode="ask",
        did=(
            f"ask: {_summarize_query(query)} | fts={stats['fts_hits']} "
            f"entities={len(stats['entities'])} threads={stats['threads']}"
        ),
        extra={
            "prompt_chars": stats["prompt_chars"],
            "fts_hits": stats["fts_hits"],
            "fallback_fill": stats["fallback_fill"],
            "entities": stats["entities"],
            "threads": stats["threads"],
            "trimmed": stats["trimmed"],
            "streamed": True,
        },
    )

    yield {"type": "done", "answer": answer}
