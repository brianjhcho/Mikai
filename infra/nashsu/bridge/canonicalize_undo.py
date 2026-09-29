#!/usr/bin/env python3
"""
canonicalize_undo.py — Phase 4 of Wikipedia-redirect canonicalization.

Reverses individual entries in .canonicalization-log.jsonl:
  1. Restore the loser file from .canonicalization-archive/<slug>.<stamp>.md
  2. Strip the fenced body-append block from the canonical page
     (bounded by MIKAI-CANONICALIZE-MERGE-FROM / MERGE-END markers)
  3. Remove the loser slug from the canonical's aliases: frontmatter
     (leaves the aliases: line if any others remain)
  4. Remove the loser slug from wiki/.aliases-index.json

Reversibility validation: run canonicalize_undo.py on the last N entries,
then re-run canonicalize.py on the restored pages; the same N verdicts
should re-propose. Round-trip proves the merge is fully reversible.

Usage:
    # Undo one specific entry by proposed_slug
    python canonicalize_undo.py --project ~/.mikai/wiki-mikai-parallel-test \
      --slug tier1-alias-test-canary

    # Undo the last N log entries (destructive; use --dry-run first)
    python canonicalize_undo.py --project ~/.mikai/wiki-mikai-parallel-test \
      --last 5 --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
LIST_INLINE_RE = re.compile(r"^\[(.*)\]$")

MERGE_FENCE_OPEN_TMPL = "<!-- MIKAI-CANONICALIZE-MERGE-FROM: {slug} -->"
MERGE_FENCE_CLOSE_TMPL = "<!-- MIKAI-CANONICALIZE-MERGE-END: {slug} -->"

LOG_FILE = ".canonicalization-log.jsonl"
ARCHIVE_DIR = ".canonicalization-archive"
ALIASES_INDEX = "wiki/.aliases-index.json"


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def aliases_to_remove(entry: dict) -> list[str]:
    """Prefer the aliases_added field written by canonicalize.py; fall
    back to reconstructing (proposed_slug + slugify(proposed_title)) for
    older log entries that predate that field."""
    explicit = entry.get("aliases_added")
    if isinstance(explicit, list) and explicit:
        return [a for a in explicit if isinstance(a, str)]
    reconstructed: list[str] = []
    ps = entry.get("proposed_slug")
    if isinstance(ps, str):
        reconstructed.append(ps)
    pt = entry.get("proposed_title")
    if isinstance(pt, str):
        pts = slugify(pt)
        if pts and pts not in reconstructed:
            reconstructed.append(pts)
    return reconstructed


def read_log(project: Path) -> list[dict]:
    p = project / LOG_FILE
    if not p.exists():
        return []
    entries: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def write_log(project: Path, entries: list[dict]) -> None:
    p = project / LOG_FILE
    if not entries:
        if p.exists():
            p.unlink()
        return
    p.write_text("\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n", encoding="utf-8")


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
        lm = LIST_INLINE_RE.match(val)
        if lm:
            fields[key] = [x.strip().strip("\"'") for x in lm.group(1).split(",") if x.strip()]
        else:
            fields[key] = val
    return fields, m.end()


def render_list(items: list[str]) -> str:
    return "[" + ", ".join(sorted(set(items))) + "]"


def undo_entry(project: Path, entry: dict, dry_run: bool) -> dict:
    proposed_slug = entry.get("proposed_slug")
    kind = entry.get("kind")
    canonical_path_rel = entry.get("canonical_path")
    archive_rel = entry.get("archive")
    applied = entry.get("applied")

    result: dict = {"proposed_slug": proposed_slug, "applied": applied, "steps": [], "dry_run": dry_run}

    if applied not in ("merge", "rename"):
        result["skipped"] = f"nothing to undo (applied={applied})"
        return result

    if not (proposed_slug and kind and canonical_path_rel and archive_rel):
        result["error"] = "log entry missing required fields"
        return result

    loser_path = project / "wiki" / kind / f"{proposed_slug}.md"
    canonical_path = project / canonical_path_rel
    archive_path = project / archive_rel

    # Step 1: restore loser file from archive
    if not archive_path.exists():
        result["error"] = f"archive missing: {archive_rel}"
        return result
    if not dry_run:
        loser_path.write_text(archive_path.read_text(encoding="utf-8"), encoding="utf-8")
    result["steps"].append(f"restore {loser_path.name} from archive")

    # Step 2: strip fenced merge block from canonical
    if not canonical_path.exists():
        result["error"] = f"canonical missing: {canonical_path_rel}"
        return result
    text = canonical_path.read_text(encoding="utf-8")
    open_marker = MERGE_FENCE_OPEN_TMPL.format(slug=proposed_slug)
    close_marker = MERGE_FENCE_CLOSE_TMPL.format(slug=proposed_slug)
    # match with surrounding blank lines/newlines eaten
    pattern = re.compile(
        r"\n*"
        + re.escape(open_marker)
        + r".*?"
        + re.escape(close_marker)
        + r"\n*",
        re.DOTALL,
    )
    if not pattern.search(text):
        result["error"] = f"merge fence for {proposed_slug} not found in canonical"
        return result
    stripped = pattern.sub("\n", text)
    if not dry_run:
        canonical_path.write_text(stripped, encoding="utf-8")
    result["steps"].append(f"strip merge-fence for {proposed_slug} from {canonical_path.name}")

    # Determine the exact alias set canonicalize.py added for this entry
    to_remove = aliases_to_remove(entry)

    # Step 3: remove those aliases from canonical's aliases: field
    fields, end = parse_frontmatter(stripped)
    aliases = fields.get("aliases", [])
    if isinstance(aliases, list) and any(a in aliases for a in to_remove):
        remaining = [a for a in aliases if a not in to_remove]
        fm_block = stripped[:end]
        body = stripped[end:]
        if remaining:
            new_line = f"aliases: {render_list(remaining)}"
            fm_block = re.sub(
                r"^aliases:\s*.*$", new_line, fm_block, count=1, flags=re.MULTILINE
            )
        else:
            fm_block = re.sub(r"^aliases:\s*.*\n", "", fm_block, count=1, flags=re.MULTILINE)
        if not dry_run:
            canonical_path.write_text(fm_block + body, encoding="utf-8")
        result["steps"].append(
            f"remove aliases {to_remove} from canonical ({len(remaining)} remain)"
        )

    # Step 4: remove from .aliases-index.json — mirror the exact set
    idx_path = project / ALIASES_INDEX
    if idx_path.exists():
        try:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            idx = {}
        dropped: list[str] = []
        for alias in to_remove:
            if alias in idx:
                dropped.append(alias)
                if not dry_run:
                    del idx[alias]
        if dropped and not dry_run:
            idx_path.write_text(
                json.dumps(idx, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        if dropped:
            result["steps"].append(f"drop {dropped} from aliases-index")

    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--slug", help="undo the log entry with proposed_slug=SLUG")
    ap.add_argument("--last", type=int, help="undo the last N merge entries")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--strip-log-on-undo", action="store_true",
                    help="also remove undone entries from .canonicalization-log.jsonl")
    args = ap.parse_args()

    if not (args.slug or args.last):
        print("must pass --slug SLUG or --last N", file=sys.stderr)
        return 2

    project = Path(args.project).expanduser().resolve()
    entries = read_log(project)
    if not entries:
        print("no log entries — nothing to undo")
        return 0

    if args.slug:
        targets = [e for e in entries if e.get("proposed_slug") == args.slug]
        if not targets:
            print(f"no log entry found with proposed_slug={args.slug}", file=sys.stderr)
            return 1
    else:
        merge_entries = [e for e in entries if e.get("applied") == "merge"]
        targets = merge_entries[-args.last :]

    results = []
    undone_slugs: set[str] = set()
    for entry in targets:
        r = undo_entry(project, entry, args.dry_run)
        results.append(r)
        if not r.get("error") and not r.get("skipped") and not args.dry_run:
            undone_slugs.add(entry.get("proposed_slug"))

    print(json.dumps(results, indent=2, sort_keys=True))

    if args.strip_log_on_undo and not args.dry_run and undone_slugs:
        remaining = [e for e in entries if e.get("proposed_slug") not in undone_slugs]
        write_log(project, remaining)
        print(f"[undo] removed {len(entries) - len(remaining)} entries from log")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
