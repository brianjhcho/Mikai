"""wiki_md_to_raw_sources.py — MIKAI wiki-raw → nashsu raw/sources/ bridge.

Note on month-year regex helpers:
  MONTH_ANY_PAT matches any monthly-journal title form used across Brian's
  Apple Notes journals. Full names (January), 3-letter abbrevs (Jan), the
  'Sept' variant (both Sep and Sept), + optional title suffixes (' - X',
  ' // X', ' || X'). Session-5 discovered the original regex missed 17
  journals because it required full month names only.


Extracts sections from ~/.mikai/wiki-raw/wiki.md (MIKAI's append-only
capture) into individual markdown files under a nashsu project's
raw/sources/ directory. Nashsu then ingests each file as a source.

Nashsu expects one file per source in raw/sources/. MIKAI stores all
sources as delimited sections in a single 57MB wiki.md indexed by JSONL.
This bridge is the one-time (or per-golden-set) conversion.

Usage examples:

  # Extract the 100 oldest sections (skip 0, take 100):
  python wiki_md_to_raw_sources.py \\
    --dest ~/.mikai/wiki-golden/raw/sources \\
    --skip 0 --take 100

  # Extract sections matching a title regex (case-insensitive):
  python wiki_md_to_raw_sources.py \\
    --dest ~/.mikai/wiki-golden/raw/sources \\
    --search "kenya|frostpunk|founding thesis"

  # Extract from a curated list (one section identifier per line;
  # identifier = "<iso-timestamp>|<source>|<name>" or a name substring):
  python wiki_md_to_raw_sources.py \\
    --dest ~/.mikai/wiki-golden/raw/sources \\
    --list curated-sources.txt

Design decisions:
  - Filename: <YYYY-MM-DD>-<title-slug>-<hash6>.md   (matches MIKAI
    convention; nashsu doesn't care about naming, only content).
  - File body: raw section text as-is. No frontmatter added — nashsu
    creates its own source-summary page during ingest.
  - Dry-run supported (default OFF; --dry-run to preview).
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

# Reuse MIKAI's WikiIndex — direct standalone load (same trick as
# dream_bootstrap.py:69-82). Avoids sidecar/l3/__init__.py's package
# imports (which would drag in graphiti-core etc.). wiki_index.py is
# stdlib-only and safe to load in isolation.
import importlib.util
_REPO = Path(__file__).resolve().parents[3]
_wiki_index_path = _REPO / "infra" / "graphiti" / "sidecar" / "l3" / "wiki_index.py"
_spec = importlib.util.spec_from_file_location("_wiki_index_standalone", _wiki_index_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
WikiIndex = _mod.WikiIndex


DEFAULT_WIKI_MD = Path.home() / ".mikai" / "wiki-raw" / "wiki.md"
DEFAULT_WIKI_INDEX = Path.home() / ".mikai" / "wiki-raw" / "wiki.index"


def slugify(text: str, max_len: int = 60) -> str:
    """Filesystem-safe kebab-case slug. Preserves ASCII lowercase +
    digits + hyphens; collapses everything else to single hyphens."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:max_len].rstrip("-") or "untitled"


def filename_for(record: dict) -> str:
    date = str(record.get("header_ts", "unknown"))[:10]
    name_slug = slugify(str(record.get("name", "unnamed")))
    hash_key = f"{record.get('source', '?')}|{record.get('name', '?')}"
    h6 = hashlib.sha1(hash_key.encode("utf-8")).hexdigest()[:6]
    return f"{date}-{name_slug}-{h6}.md"


# ── Claude-thread grouping ────────────────────────────────────────────
# Claude threads in wiki-raw are stored per-turn: one section per turn,
# named "claude-thread::<title>::<index>::<role>". Bridging each turn
# individually would produce N tiny sources per thread instead of one
# coherent conversation. This function collapses all turns of a thread
# into a single reconstructed markdown file.


def is_claude_thread_turn(record: dict) -> bool:
    src = str(record.get("source", ""))
    name = str(record.get("name", ""))
    return src.startswith("claude-thread") and name.count("::") >= 3


def parse_thread_turn(record: dict) -> tuple[str, int, str]:
    """Return (thread_title, turn_index, role). Name format:
    'claude-thread::<title>::<index>::<role>'."""
    parts = str(record.get("name", "")).split("::")
    title = parts[1] if len(parts) > 1 else "unknown"
    try:
        idx = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        idx = 0
    role = parts[3] if len(parts) > 3 else "unknown"
    return title, idx, role


def reconstruct_thread(wiki_md: Path, thread_title: str, turns: list[dict]) -> tuple[str, str]:
    """Sort turns by index, concatenate bodies with role headers. Return
    (filename, content). Uses the earliest turn's timestamp for the
    filename date."""
    turns_sorted = sorted(turns, key=lambda r: parse_thread_turn(r)[1])
    earliest_ts = str(turns_sorted[0].get("header_ts", "unknown"))[:10]
    latest_ts = str(turns_sorted[-1].get("header_ts", "unknown"))[:10]
    slug = slugify(thread_title)
    hash_key = f"claude-thread|{thread_title}"
    h6 = hashlib.sha1(hash_key.encode("utf-8")).hexdigest()[:6]
    filename = f"{earliest_ts}-{slug}-{h6}.md"

    lines = [
        f"# {thread_title}",
        "",
        f"> **Source:** claude-thread, {len(turns_sorted)} turns",
        f"> **Span:** {earliest_ts} → {latest_ts}",
        "",
    ]
    for rec in turns_sorted:
        _, idx, role = parse_thread_turn(rec)
        body = WikiIndex.read_section(wiki_md, rec)
        # Strip the section header line if present (starts with "### ")
        if body.startswith("### "):
            body = body.split("\n", 1)[1] if "\n" in body else ""
        lines.append(f"## Turn {idx:03d} — {role}")
        lines.append("")
        lines.append(body.strip())
        lines.append("")
    return filename, "\n".join(lines) + "\n"


def load_curated_list(path: Path) -> list[str]:
    """Read a curated source list. Each non-empty non-comment line is
    a match pattern (regex or substring, applied to name)."""
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return lines


def resolve_curated(index: WikiIndex, patterns: list[str]) -> list[dict]:
    """Match each pattern via sections_matching(name_pattern=...). If a
    pattern matches multiple sections, all are included. De-dup by
    (header_ts, source, name) tuple."""
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for pat in patterns:
        matches = index.sections_matching(name_pattern=pat)
        if not matches:
            print(f"[bridge] warn: no match for pattern: {pat!r}", file=sys.stderr)
            continue
        for r in matches:
            key = (str(r.get("header_ts")), str(r.get("source")), str(r.get("name")))
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="MIKAI wiki-raw → nashsu raw/sources/ bridge")
    ap.add_argument("--wiki-md", type=Path, default=DEFAULT_WIKI_MD, help="path to wiki.md")
    ap.add_argument("--wiki-index", type=Path, default=DEFAULT_WIKI_INDEX, help="path to wiki.index")
    ap.add_argument("--dest", type=Path, required=True, help="destination raw/sources/ dir")
    ap.add_argument("--dry-run", action="store_true", help="preview only, no writes")

    # Filter args (mutually exclusive)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--skip", type=int, help="SKIP_N (used with --take)")
    g.add_argument("--search", type=str, help="case-insensitive regex against section name")
    g.add_argument("--list", type=Path, help="file with one match-pattern per line")
    ap.add_argument("--take", type=int, default=100, help="TAKE_N when using --skip")

    args = ap.parse_args()

    # Load index
    if not args.wiki_index.exists():
        print(f"[bridge] wiki.index not found at {args.wiki_index}; run WikiIndex.build first", file=sys.stderr)
        sys.exit(2)
    index = WikiIndex.load(args.wiki_index)
    print(f"[bridge] loaded {len(index.records)} sections from {args.wiki_index}")

    # Select records
    if args.skip is not None:
        records = index.records[args.skip : args.skip + args.take]
        print(f"[bridge] window: SKIP={args.skip} TAKE={args.take} → {len(records)} sections")
    elif args.search:
        records = index.sections_matching(name_pattern=args.search)
        print(f"[bridge] search {args.search!r} → {len(records)} matches")
    else:  # --list
        patterns = load_curated_list(args.list)
        records = resolve_curated(index, patterns)
        print(f"[bridge] curated list ({len(patterns)} patterns) → {len(records)} sections")

    if not records:
        print("[bridge] no sections selected — exiting")
        sys.exit(0)

    # Prep destination
    args.dest.mkdir(parents=True, exist_ok=True)

    # Separate Claude thread turns (grouped by thread) from everything
    # else (individual per-section). Claude threads are stored per-turn
    # in wiki-raw; bridging each turn as its own source would produce
    # incoherent tiny sources. Grouping = one file per thread.
    thread_groups: dict[str, list[dict]] = {}
    other_records: list[dict] = []
    for r in records:
        if is_claude_thread_turn(r):
            title, _, _ = parse_thread_turn(r)
            thread_groups.setdefault(title, []).append(r)
        else:
            other_records.append(r)

    if thread_groups:
        print(f"[bridge] grouped {sum(len(t) for t in thread_groups.values())} claude-thread turns into {len(thread_groups)} threads:")
        for title, turns in sorted(thread_groups.items(), key=lambda x: -len(x[1])):
            print(f"[bridge]   {len(turns):4d} turns  {title}")

    # Write files
    written = 0
    skipped_existing = 0

    # 1) Grouped Claude threads
    for title, turns in thread_groups.items():
        fname, content = reconstruct_thread(args.wiki_md, title, turns)
        dest_path = args.dest / fname
        if args.dry_run:
            print(f"[dry-run] would write THREAD {fname} ({len(content)}B, {len(turns)} turns)")
            continue
        if dest_path.exists():
            skipped_existing += 1
            continue
        dest_path.write_text(content, encoding="utf-8")
        written += 1

    # 2) Individual sections (apple-notes, perplexity, etc.)
    for r in other_records:
        fname = filename_for(r)
        dest_path = args.dest / fname
        if args.dry_run:
            body_preview = WikiIndex.read_section(args.wiki_md, r)[:80].replace("\n", " ")
            print(f"[dry-run] would write {fname} ({r.get('content_bytes', '?')}B): {body_preview}…")
            continue
        if dest_path.exists():
            skipped_existing += 1
            continue
        body = WikiIndex.read_section(args.wiki_md, r)
        dest_path.write_text(body, encoding="utf-8")
        written += 1

    if args.dry_run:
        total = len(thread_groups) + len(other_records)
        print(f"[bridge] dry-run complete: {total} files would be written ({len(thread_groups)} grouped threads + {len(other_records)} individual sections)")
    else:
        print(f"[bridge] wrote {written} files to {args.dest}")
        if skipped_existing > 0:
            print(f"[bridge]   ({skipped_existing} skipped — already existed)")


if __name__ == "__main__":
    main()
