#!/usr/bin/env python3
"""
wrap_bare_mentions.py — CANON-8 deterministic bare-mention wrapping pass.

CANON-7 measured 51.78% referential integrity: half the mentions of known
canonicals across the vault sit as bare text, not wikilinks. Fable's audit
correctly removed the per-page LLM enrichment (enrichWithWikilinks) as too
expensive; the deterministic replacement is this: mechanical, LLM-free,
batched sweep that wraps unambiguous whole-word matches.

Rules:
  - Whole-word case-insensitive match against canonical titles + aliases
  - Skip inside fenced code blocks (```...```) and inline code (`...`)
  - Skip inside existing wikilinks [[...]]
  - Skip inside YAML frontmatter (never rewrite metadata)
  - Skip inside H1-H6 header lines (headers shouldn't carry wikilinks)
  - Preserve original text casing inside the wikilink using aliased form
  - Ambiguous matches (token maps to >1 canonical) → skip (leave for
    a future LLM-disambiguation pass)
  - Cap N wraps per (page × canonical) to avoid oversaturation
    (a page mentioning "Kenya" 25 times doesn't need 25 wikilinks)

Every wrap is logged to `.link-wrap-log.jsonl` with a snapshot in
`.link-wrap-archive/` for revert.

Usage:
    # Dry-run report — no writes
    python wrap_bare_mentions.py --vault ~/.mikai/wiki-mikai-parallel-test --dry-run

    # Apply
    python wrap_bare_mentions.py --vault ~/.mikai/wiki-mikai-parallel-test --apply
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
HEADER_RE = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)

SWEEP_KINDS = ("sources", "concepts", "entities", "wisdom")
CANONICAL_KINDS = ("concepts", "entities", "wisdom")

DEFAULT_MAX_WRAPS_PER_PAGE_PER_CANONICAL = 3
MIN_KEY_LENGTH = 5  # skip trivial short strings ("mikai" survives; "graph" doesn't)

LOG_FILE = ".link-wrap-log.jsonl"
ARCHIVE_DIR = ".link-wrap-archive"


def parse_frontmatter(text: str) -> tuple[dict, int]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, 0
    fields: dict = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.startswith("#") or ":" not in line or line.startswith(" "):
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if val.startswith("[") and val.endswith("]"):
            fields[key] = [x.strip().strip("\"'") for x in val[1:-1].split(",") if x.strip()]
        else:
            fields[key] = val
    return fields, m.end()


def build_lookup(vault: Path) -> dict[str, str]:
    """key (lowercased whole-word form) → 'kind/slug' canonical target.
    Ambiguous keys (multiple canonicals) are marked with the sentinel value
    '__AMBIGUOUS__' and skipped during wrap.
    """
    tmp: dict[str, set[str]] = defaultdict(set)
    for kind in CANONICAL_KINDS:
        d = vault / "wiki" / kind
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fields, _ = parse_frontmatter(text)
            if not fields or fields.get("retired_to"):
                continue
            slug = p.stem
            kinded = f"{kind}/{slug}"
            keys: set[str] = set()
            keys.add(slug.lower())
            keys.add(slug.replace("-", " ").lower())
            title = fields.get("title")
            if isinstance(title, str) and title.strip():
                keys.add(title.strip().lower())
            aliases = fields.get("aliases") or []
            if isinstance(aliases, list):
                for a in aliases:
                    if isinstance(a, str):
                        keys.add(a.strip().lower())
                        keys.add(a.replace("-", " ").strip().lower())
            for k in keys:
                if len(k) < MIN_KEY_LENGTH:
                    continue
                tmp[k].add(kinded)

    lookup: dict[str, str] = {}
    for k, canonicals in tmp.items():
        if len(canonicals) == 1:
            lookup[k] = next(iter(canonicals))
        else:
            lookup[k] = "__AMBIGUOUS__"
    return lookup


def mask_protected_regions(body: str) -> tuple[str, list[tuple[int, int]]]:
    """Replace protected regions (code fences, inline code, existing wikilinks,
    headers) with placeholder chars so their positions don't match wraps.
    Return (masked_body, spans) where spans is a list of (start, end) tuples
    of protected regions in the ORIGINAL body.
    """
    spans: list[tuple[int, int]] = []
    for rx in (CODE_FENCE_RE, INLINE_CODE_RE, WIKILINK_RE, HEADER_RE):
        for m in rx.finditer(body):
            spans.append((m.start(), m.end()))
    spans.sort()

    # Coalesce overlapping
    merged: list[tuple[int, int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    masked = list(body)
    for s, e in merged:
        for i in range(s, e):
            masked[i] = "\x00"  # NUL — won't match \b\w patterns
    return "".join(masked), merged


def wrap_page(
    path: Path,
    lookup: dict[str, str],
    max_wraps_per_canonical: int,
) -> tuple[str | None, list[dict]]:
    """Return (new_body, wraps) — new_body is None if no changes made."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, []
    fields, end = parse_frontmatter(text)
    if fields.get("retired_to"):
        return None, []
    fm_block = text[:end]
    body = text[end:]

    masked, spans = mask_protected_regions(body)

    # Build (key, canonical) sorted by descending key length so that
    # longer matches take precedence (e.g. "personal intent graph" before
    # "intent graph")
    self_slug = f"{path.parent.name}/{path.stem}"
    candidate_keys: list[tuple[str, str]] = [
        (k, v) for k, v in lookup.items()
        if v != "__AMBIGUOUS__" and v != self_slug
    ]
    candidate_keys.sort(key=lambda t: -len(t[0]))

    wraps: list[dict] = []
    counts: Counter[str] = Counter()

    # We rebuild body with replacements. Track offsets carefully.
    # Simplest approach: walk keys longest-first; for each, find all matches
    # in the CURRENT masked view; wrap the first N in the OUTPUT text (which
    # we mutate); then re-mask the mutated text for the next key so we don't
    # double-wrap.
    output = body
    output_masked = masked

    for key, canonical in candidate_keys:
        pattern = re.compile(r"\b" + re.escape(key) + r"\b", flags=re.IGNORECASE)
        # Find matches in the masked view (protects code/wikilinks/headers)
        for m in list(pattern.finditer(output_masked)):
            if counts[canonical] >= max_wraps_per_canonical:
                break
            start, end_ = m.start(), m.end()
            original = output[start:end_]
            replacement = f"[[{canonical}|{original}]]"
            # Apply on output + output_masked at the same positions
            output = output[:start] + replacement + output[end_:]
            # Mask the newly-wrapped region so no future key matches inside it
            output_masked = output_masked[:start] + "\x00" * len(replacement) + output_masked[end_:]
            wraps.append({
                "key": key,
                "canonical": canonical,
                "at": start,
                "wrapped": original,
            })
            counts[canonical] += 1

    if not wraps:
        return None, []
    return fm_block + output, wraps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-per-canonical", type=int,
                    default=DEFAULT_MAX_WRAPS_PER_PAGE_PER_CANONICAL,
                    help="cap wraps per (page × canonical) to avoid oversaturation")
    ap.add_argument("--out", default="/tmp/wrap-bare-mentions.json")
    args = ap.parse_args()

    if not (args.dry_run or args.apply):
        print("must pass --dry-run OR --apply")
        return 2

    vault = Path(args.vault).expanduser().resolve()
    print(f"[wrap] building lookup...", flush=True)
    lookup = build_lookup(vault)
    unambiguous = sum(1 for v in lookup.values() if v != "__AMBIGUOUS__")
    ambiguous = sum(1 for v in lookup.values() if v == "__AMBIGUOUS__")
    print(f"[wrap] lookup: {len(lookup)} keys ({unambiguous} unambiguous, "
          f"{ambiguous} ambiguous — skipped)", flush=True)

    # Sweep all pages
    pages: list[Path] = []
    for kind in SWEEP_KINDS:
        d = vault / "wiki" / kind
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            pages.append(p)

    print(f"[wrap] sweeping {len(pages)} pages "
          f"(max wraps per canonical per page: {args.max_per_canonical})...", flush=True)

    total_wraps = 0
    pages_changed = 0
    per_page: list[dict] = []
    archive_dir = vault / ARCHIVE_DIR

    stamp = int(time.time() * 1000)
    for i, p in enumerate(pages, 1):
        new_body, wraps = wrap_page(p, lookup, args.max_per_canonical)
        if not wraps:
            continue
        pages_changed += 1
        total_wraps += len(wraps)
        per_page.append({
            "path": str(p.relative_to(vault)),
            "wraps": len(wraps),
            "targets": Counter(w["canonical"] for w in wraps).most_common(5),
        })
        if args.apply and new_body is not None:
            archive_dir.mkdir(parents=True, exist_ok=True)
            (archive_dir / f"{p.stem}.{stamp}.md").write_text(
                p.read_text(encoding="utf-8"), encoding="utf-8"
            )
            p.write_text(new_body, encoding="utf-8")
            with (vault / LOG_FILE).open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "path": str(p.relative_to(vault)),
                    "wraps": wraps,
                    "archive": f"{ARCHIVE_DIR}/{p.stem}.{stamp}.md",
                }, sort_keys=True) + "\n")
        if i % 100 == 0:
            print(f"[wrap] {i}/{len(pages)} scanned...", flush=True)

    Path(args.out).write_text(
        json.dumps({
            "summary": {
                "pages_swept": len(pages),
                "pages_changed": pages_changed,
                "total_wraps": total_wraps,
                "unambiguous_keys": unambiguous,
                "ambiguous_keys_skipped": ambiguous,
                "dry_run": args.dry_run,
            },
            "per_page_top50": sorted(per_page, key=lambda x: -x["wraps"])[:50],
        }, indent=2),
        encoding="utf-8",
    )
    print(f"[wrap] pages_changed={pages_changed} total_wraps={total_wraps}", flush=True)
    print(f"[wrap] full report: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
