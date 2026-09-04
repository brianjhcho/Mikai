"""dream ingest-source — compile-on-ingest concept page updater.

Karpathy's "one URL, 5-15 pages touched" operation. For each new
wiki.md section (since last run), one LLM call:

- Given: the source text + the current list of concept pages (slugs +
  TL;DRs from ~/.mikai/wiki/concepts/index.md)
- Ask: which concepts does this source touch? For each, append a
  source line to the concept's Sources section. If the source
  discusses a topic that doesn't have a page yet, list it as a
  suggested new concept.

Never auto-creates concept pages (mint requires human approval to
avoid the confabulation loop — suggested new pages land in
~/.mikai/wiki/concept-inbox.md for user review). Only APPENDS to
existing pages.

State tracked at ~/.mikai/wiki/.ingest-source-state.json:
    {"last_processed_ts": "2026-08-09T15:00:00+00:00",
     "processed_count": 342}

Usage:
    python3 -m infra.graphiti.ingest_source
    python3 -m infra.graphiti.ingest_source --since-days 7
    python3 -m infra.graphiti.ingest_source --dry-run --verbose
    python3 -m infra.graphiti.ingest_source --max-sources 20

Cost: 1 LLM call per source. Typical ~50 sources/week → ~50 calls/week
on the interactive tier (Max sub, tools disabled).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from infra.graphiti.dream_bootstrap import (  # noqa: E402
    Budget,
    WikiIndex,
    excerpt,
    load_index,
    parse_ts,
    strip_json_fences,
    _ledger_trace,
    WIKI_MD,
    WIKI_DIR,
)

CONCEPTS_DIR = WIKI_DIR / "concepts"
INDEX_MD = CONCEPTS_DIR / "index.md"
LOG_MD = CONCEPTS_DIR / "log.md"
CONCEPT_INBOX = WIKI_DIR / "concept-inbox.md"
STATE_FILE = WIKI_DIR / ".ingest-source-state.json"

MAX_CONCEPTS_IN_PROMPT = 80    # concept-list length cap for the prompt
MAX_SOURCE_EXCERPT_CHARS = 3500  # source body window sent to LLM
DEFAULT_MAX_SOURCES_PER_RUN = 30  # LLM budget cap per invocation


# ── State ────────────────────────────────────────────────────────────────


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {"last_processed_ts": None, "processed_count": 0}
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {"last_processed_ts": None, "processed_count": 0}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ── Concept-page directory ──────────────────────────────────────────────


def _load_concept_directory() -> list[dict]:
    """Read every concept page, extract slug + title + TL;DR line.
    Returns list ordered by salience (descending) — the prompt then caps
    at MAX_CONCEPTS_IN_PROMPT so top-salience concepts are always shown."""
    if not CONCEPTS_DIR.exists():
        return []
    entries = []
    for p in sorted(CONCEPTS_DIR.glob("*.md")):
        if p.stem in ("index", "log"):
            continue
        text = p.read_text(encoding="utf-8")
        title = p.stem
        salience = 0.0
        tldr = ""
        # frontmatter parse
        fm = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
        if fm:
            for line in fm.group(1).splitlines():
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                k, v = k.strip(), v.strip()
                if k == "title":
                    title = v or title
                elif k == "salience":
                    try:
                        salience = float(v)
                    except ValueError:
                        pass
        # TL;DR
        m = re.search(r"##\s*TL;DR\s*\n(.+?)(?:\n\n|\n##)", text, re.DOTALL)
        if m:
            tldr = " ".join(m.group(1).split())[:160]
        entries.append({
            "slug": p.stem,
            "title": title,
            "salience": salience,
            "tldr": tldr,
        })
    entries.sort(key=lambda e: -e["salience"])
    return entries


def _format_concept_directory(entries: list[dict]) -> str:
    """Render concept directory as compact bullets for the LLM prompt."""
    lines = []
    for e in entries[:MAX_CONCEPTS_IN_PROMPT]:
        tldr = e["tldr"] or "_(no TL;DR yet)_"
        lines.append(f"- **{e['slug']}** (S={e['salience']:.1f}): {tldr}")
    if len(entries) > MAX_CONCEPTS_IN_PROMPT:
        lines.append(f"- _(...and {len(entries) - MAX_CONCEPTS_IN_PROMPT} "
                     f"lower-salience concepts omitted from this prompt)_")
    return "\n".join(lines)


# ── Section iteration ──────────────────────────────────────────────────


def _new_sections_since(idx: WikiIndex, last_ts: str | None,
                         since_days: int | None,
                         max_sources: int) -> list[dict]:
    """Return index records to process. Filter: after last_ts (state) AND
    within since_days if given. Cap at max_sources."""
    cutoff: datetime | None = None
    if last_ts:
        try:
            cutoff = parse_ts(last_ts)
        except Exception:  # noqa: BLE001
            cutoff = None
    if since_days is not None:
        window_cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        cutoff = max(cutoff, window_cutoff) if cutoff else window_cutoff
    out = []
    for rec in idx.records:
        try:
            ts = parse_ts(rec.get("header_ts", ""))
        except Exception:  # noqa: BLE001
            continue
        if cutoff and ts <= cutoff:
            continue
        out.append(rec)
    # chronological order — process oldest first so state advances monotonically
    out.sort(key=lambda r: r.get("header_ts", ""))
    if max_sources and len(out) > max_sources:
        out = out[:max_sources]
    return out


def _catchup_sections(idx: WikiIndex, state: dict,
                      max_sources: int) -> list[dict]:
    """Build 6: process-inbox catchup — iterate OLDEST unprocessed sections,
    advancing catchup_ts monotonically. Skips anything the forward-mode
    already covered (>= state.last_processed_ts).

    State fields used:
    - catchup_ts: cursor for catchup mode (start = earliest section)
    - last_processed_ts: forward-mode cursor (upper bound for catchup)

    Catchup is complete when catchup_ts >= last_processed_ts."""
    catchup_start = state.get("catchup_ts")
    forward_cursor = state.get("last_processed_ts")
    start_after: datetime | None = None
    if catchup_start:
        try:
            start_after = parse_ts(catchup_start)
        except Exception:  # noqa: BLE001
            start_after = None
    forward_dt: datetime | None = None
    if forward_cursor:
        try:
            forward_dt = parse_ts(forward_cursor)
        except Exception:  # noqa: BLE001
            forward_dt = None

    out = []
    for rec in idx.records:
        try:
            ts = parse_ts(rec.get("header_ts", ""))
        except Exception:  # noqa: BLE001
            continue
        if start_after and ts <= start_after:
            continue
        if forward_dt and ts >= forward_dt:
            # already covered by forward mode
            continue
        out.append(rec)
    out.sort(key=lambda r: r.get("header_ts", ""))
    if max_sources and len(out) > max_sources:
        out = out[:max_sources]
    return out


# ── LLM prompt + parse ────────────────────────────────────────────────


_PROMPT = """You are helping Brian maintain his personal wiki. He captures
material from Apple Notes, Claude threads, Perplexity searches, and coding
sessions. His wiki has concept pages that synthesize recurring topics.

Your task: read ONE source below. Identify which of Brian's existing concept
pages this source TOUCHES (adds evidence to). For each touched concept, give
a one-line reason why. If the source discusses a topic that doesn't have a
page yet AND seems durable (not a passing mention), suggest a new page slug.

Be conservative:
- Only mark a concept as touched if the source clearly evidences that topic
- Do NOT invent connections — if a concept is only tangentially mentioned,
  skip it
- Suggest a NEW page only when the topic recurs or has clear future weight;
  don't mint pages for one-off references
- Prefer 0-5 touches over 10 shallow ones

## Brian's current concept pages

{concept_directory}

## Source

- Date: {source_date}
- Stream: {source_stream}
- Title: {source_name}

---
{source_body}
---

## Return JSON, no prose

Return ONLY valid JSON in this exact shape:

{{
  "touches": [
    {{"slug": "existing-slug-here", "why": "one-line reason"}}
  ],
  "suggests_new": [
    {{"slug": "kebab-case-slug", "why": "one-line reason", "recurring": true}}
  ]
}}

If nothing touches, return {{"touches": [], "suggests_new": []}}.
"""


def _build_prompt(section_text: str, section_rec: dict,
                  concept_directory_md: str) -> str:
    """Assemble the per-source prompt."""
    body = excerpt(section_text, MAX_SOURCE_EXCERPT_CHARS)
    ts = section_rec.get("header_ts", "?")
    source_full = section_rec.get("source", "?")
    stream = source_full.split(":")[0].strip() if ":" in source_full else source_full
    name = section_rec.get("name", "?")
    return _PROMPT.format(
        concept_directory=concept_directory_md,
        source_date=ts[:10],
        source_stream=stream,
        source_name=name,
        source_body=body,
    )


def _parse_llm_response(text: str) -> dict:
    """Parse LLM JSON response. Returns {"touches": [], "suggests_new": []}
    on any parse failure — never raises. Malformed responses just contribute
    nothing that pass."""
    if not text:
        return {"touches": [], "suggests_new": []}
    try:
        obj = json.loads(strip_json_fences(text))
    except json.JSONDecodeError:
        return {"touches": [], "suggests_new": []}
    if not isinstance(obj, dict):
        return {"touches": [], "suggests_new": []}
    return {
        "touches": obj.get("touches", []) if isinstance(obj.get("touches"), list) else [],
        "suggests_new": obj.get("suggests_new", []) if isinstance(obj.get("suggests_new"), list) else [],
    }


# ── Page + inbox writes ────────────────────────────────────────────────


def _append_source_to_page(slug: str, source_line: str, why: str) -> bool:
    """Append a new bullet to the target page's Sources section.
    Idempotent: skips if the exact source_line is already present.
    Returns True if the page was modified."""
    page = CONCEPTS_DIR / f"{slug}.md"
    if not page.exists():
        return False
    text = page.read_text(encoding="utf-8")
    if source_line in text:
        return False
    # Insert before "## Referenced by" if present, else at end
    ref_marker = "\n## Referenced by"
    new_bullet = f"{source_line}   _(via ingest-source: {why})_\n"
    if ref_marker in text:
        text = text.replace(ref_marker,
                            f"{new_bullet.rstrip()}\n{ref_marker}", 1)
    else:
        text = text.rstrip() + "\n" + new_bullet
    page.write_text(text, encoding="utf-8")
    return True


def _log_suggested_new(inbox: list[dict], suggested: list[dict],
                       section_rec: dict) -> None:
    """Extend the in-memory inbox list. Written to CONCEPT_INBOX at end."""
    for s in suggested:
        slug = s.get("slug", "").strip()
        if not slug:
            continue
        inbox.append({
            "slug": slug,
            "why": s.get("why", ""),
            "recurring": bool(s.get("recurring")),
            "from_source_ts": section_rec.get("header_ts", ""),
            "from_source_name": section_rec.get("name", ""),
        })


def _write_inbox(inbox: list[dict]) -> None:
    """Append inbox entries to concept-inbox.md (dedup by slug + source)."""
    if not inbox:
        return
    # Group by slug
    by_slug: dict[str, list[dict]] = {}
    for entry in inbox:
        by_slug.setdefault(entry["slug"], []).append(entry)
    existing = ""
    if CONCEPT_INBOX.exists():
        existing = CONCEPT_INBOX.read_text(encoding="utf-8")
    lines = [existing.rstrip()] if existing else ["# Concept Inbox", "",
                                                   "_Suggested new concept pages. "
                                                   "Review + `dream promote` "
                                                   "the ones that earn it._", ""]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("")
    lines.append(f"## Ingest run — {ts}")
    for slug, entries in sorted(by_slug.items()):
        # dedup exact identical entries
        seen = set()
        dedup: list[dict] = []
        for e in entries:
            key = (e["from_source_ts"], e["why"])
            if key in seen:
                continue
            seen.add(key)
            dedup.append(e)
        lines.append("")
        rec_flag = "✓ recurring" if any(e["recurring"] for e in dedup) else "?"
        lines.append(f"### `{slug}` ({rec_flag}, {len(dedup)} source(s))")
        for e in dedup:
            lines.append(f"- {e['from_source_ts'][:10]} · "
                         f"{e['from_source_name'][:80]} — {e['why']}")
    CONCEPT_INBOX.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_log(msg: str) -> None:
    """Log a line to concepts/log.md — matches Build 4's pattern."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    line = f"- **{ts}** — {msg}\n"
    if not LOG_MD.exists():
        LOG_MD.write_text("# Concepts — Log\n\n", encoding="utf-8")
    with LOG_MD.open("a", encoding="utf-8") as f:
        f.write(line)


# ── Runner ──────────────────────────────────────────────────────────────


def run_ingest_source(idx: WikiIndex, budget: Budget, since_days: int | None,
                     max_sources: int, dry_run: bool, verbose: bool,
                     catchup: bool = False) -> str:
    """Main loop. Build 5 = forward mode (default). Build 6 = catchup mode
    (--catchup): iterate oldest-first through the backlog that predates
    the forward-mode cursor."""
    state = _load_state()
    concept_dir = _load_concept_directory()
    if not concept_dir:
        print("[ingest] no concept pages yet — nothing to update. "
              "Run `dream promote` first to seed pages.")
        return "no concept pages"
    print(f"[ingest] loaded {len(concept_dir)} concept pages "
          f"(top-{min(MAX_CONCEPTS_IN_PROMPT, len(concept_dir))} shown to LLM)")

    concept_dir_md = _format_concept_directory(concept_dir)
    concept_slugs = {e["slug"] for e in concept_dir}

    if catchup:
        new_sections = _catchup_sections(idx, state, max_sources)
        mode = "catchup"
        cursor_key = "catchup_ts"
    else:
        last_ts = state.get("last_processed_ts")
        new_sections = _new_sections_since(idx, last_ts, since_days, max_sources)
        mode = "forward"
        cursor_key = "last_processed_ts"

    if not new_sections:
        if catchup:
            print(f"[ingest:{mode}] no backlog remaining "
                  f"(catchup_ts={state.get('catchup_ts')!r}, "
                  f"caught up to last_processed_ts="
                  f"{state.get('last_processed_ts')!r})")
        else:
            print(f"[ingest:{mode}] no new sections since "
                  f"last_ts={state.get('last_processed_ts')!r}")
        return f"no {mode} sections"
    print(f"[ingest:{mode}] {len(new_sections)} source(s) to process "
          f"(oldest {new_sections[0]['header_ts'][:16]}, "
          f"newest {new_sections[-1]['header_ts'][:16]})")

    total_touches = 0
    total_pages_updated = 0
    total_suggested_new = 0
    inbox_entries: list[dict] = []
    latest_ts = state.get(cursor_key)

    for i, rec in enumerate(new_sections, 1):
        section_text = WikiIndex.read_section(WIKI_MD, rec)
        prompt = _build_prompt(section_text, rec, concept_dir_md)
        label = f"ingest[{i}/{len(new_sections)}]:{rec.get('name', '?')[:40]}"

        if dry_run:
            if verbose:
                print(f"  [dry] would LLM-call {label} "
                      f"(prompt={len(prompt)}ch)")
            continue

        response = budget.chat(prompt, label)
        parsed = _parse_llm_response(response or "")
        touches = parsed["touches"]
        suggests = parsed["suggests_new"]

        # Filter touches to concepts that actually exist (LLM may hallucinate)
        valid_touches = [t for t in touches
                         if t.get("slug", "").strip() in concept_slugs]
        invalid_touches = [t for t in touches
                           if t.get("slug", "").strip() not in concept_slugs]
        if invalid_touches and verbose:
            names = ", ".join(t.get("slug", "?") for t in invalid_touches[:3])
            print(f"    [warn] {len(invalid_touches)} nonexistent slug(s) "
                  f"in LLM response: {names}")

        source_line = (f"- {rec['header_ts'][:10]} · "
                       f"`{rec.get('source', '?').split(':')[0].strip()}` · "
                       f"{rec.get('name', '?')[:80]}")
        pages_updated_this = 0
        for t in valid_touches:
            slug = t["slug"].strip()
            why = str(t.get("why", "")).strip() or "(no reason given)"
            if _append_source_to_page(slug, source_line, why):
                pages_updated_this += 1
        total_touches += len(valid_touches)
        total_pages_updated += pages_updated_this

        if suggests:
            _log_suggested_new(inbox_entries, suggests, rec)
            total_suggested_new += len(suggests)

        latest_ts = rec["header_ts"]
        if verbose:
            print(f"  {i:>3}/{len(new_sections)} {rec['header_ts'][:16]} "
                  f"{rec.get('name','?')[:60]} → "
                  f"touched {len(valid_touches)}, suggested {len(suggests)}")

    if not dry_run and inbox_entries:
        _write_inbox(inbox_entries)
        print(f"[ingest] {total_suggested_new} suggested new concept(s) "
              f"-> {CONCEPT_INBOX}")

    prior_cursor = state.get(cursor_key)
    if not dry_run and latest_ts and latest_ts != prior_cursor:
        state[cursor_key] = latest_ts
        state["processed_count"] = state.get("processed_count", 0) + \
            len(new_sections)
        _save_state(state)
        print(f"[ingest:{mode}] state advanced -> {cursor_key}={latest_ts[:16]}")

    summary = (f"ingest-source ({mode}): {len(new_sections)} sources, "
               f"{total_touches} touches, {total_pages_updated} pages updated, "
               f"{total_suggested_new} suggested new")
    if not dry_run:
        _append_log(summary)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(prog="ingest-source")
    ap.add_argument("--since-days", type=int, default=None,
                    help="only process sections newer than N days "
                         "(default: use state file's last_processed_ts)")
    ap.add_argument("--max-sources", type=int,
                    default=DEFAULT_MAX_SOURCES_PER_RUN,
                    help=f"cap sources per run (default {DEFAULT_MAX_SOURCES_PER_RUN})")
    ap.add_argument("--max-calls", type=int, default=100)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--reset-state", action="store_true",
                    help="clear state file (reprocess everything from scratch — expensive)")
    ap.add_argument("--catchup", action="store_true",
                    help="Build 6 process-inbox mode: iterate the OLDEST "
                         "unprocessed sections (backlog before forward "
                         "cursor). Advances catchup_ts monotonically toward "
                         "last_processed_ts. Complementary to forward mode "
                         "— both cursors track independently.")
    args = ap.parse_args()

    if args.reset_state:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        print(f"[ingest] state file reset")

    if not WIKI_MD.exists():
        sys.exit(f"{WIKI_MD} not found")

    idx = load_index()
    budget = Budget(args.max_calls)

    try:
        summary = run_ingest_source(
            idx, budget,
            since_days=args.since_days,
            max_sources=args.max_sources,
            dry_run=args.dry_run,
            verbose=args.verbose,
            catchup=args.catchup,
        )
    finally:
        print(f"[done] LLM calls: {budget.calls} "
              f"({budget.failures} failed)")

    print(summary)


if __name__ == "__main__":
    main()
