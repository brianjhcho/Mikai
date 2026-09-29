#!/usr/bin/env python3
"""
build_aliases.py — Phase 1 of Wikipedia-redirect canonicalization for MIKAI wiki.

Walks a vault, harvests loser→canonical mappings from existing `retired_to:`
frontmatter, groups by canonical, and writes:

  1. `aliases:` frontmatter (append-only, sorted, dedup'd) on each canonical
     page that has at least one inbound retire stub. Values: the retired
     slug plus the retired page's `title:` slugified.
  2. `wiki/.aliases-index.json` — flat `{alias_slug: canonical_slug}` map for
     runtime resolution lookups.

CONSOLIDATION_ARCHITECTURE.md §5a: "one canonical slug per concept, an
append-only aliases: list in frontmatter, and a mandatory resolution pass
before any mint."

Usage:
    python build_aliases.py --vault ~/.mikai/wiki-mikai-parallel-test --dry-run
    python build_aliases.py --vault ~/.mikai/wiki-mikai-parallel-test --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
LIST_INLINE_RE = re.compile(r"^\[(.*)\]$")


@dataclass
class PageInfo:
    path: Path
    slug: str
    kind: str  # concepts | entities | wisdom
    frontmatter_raw: str
    frontmatter_end: int  # byte offset in file where frontmatter block ends (after closing ---\n)
    title: str | None
    retired_to: str | None
    aliases: list[str]


@dataclass
class AliasProposal:
    canonical_slug: str
    canonical_path: Path
    new_aliases: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)  # alias → retire-stub slug


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def parse_frontmatter(text: str) -> tuple[dict[str, str | list[str]], int]:
    """Minimal YAML-ish parser sufficient for MIKAI page frontmatter.

    Returns (fields, end_offset). end_offset is the byte position immediately
    after the closing `---\\n` line, i.e. where the body starts.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, 0
    body = m.group(1)
    fields: dict[str, str | list[str]] = {}
    for line in body.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        # only care about top-level `key: value` — no nested structures in our schema
        if ":" not in line or line.startswith(" "):
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # strip enclosing quotes
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        # inline list `[a, b, c]`
        lm = LIST_INLINE_RE.match(val)
        if lm:
            items = [x.strip().strip("\"'") for x in lm.group(1).split(",") if x.strip()]
            fields[key] = items
        else:
            fields[key] = val
    return fields, m.end()


def load_page(path: Path) -> PageInfo | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    fields, end = parse_frontmatter(text)
    if not fields:
        return None
    slug = path.stem
    kind = path.parent.name
    title = fields.get("title") if isinstance(fields.get("title"), str) else None
    retired_to = fields.get("retired_to") if isinstance(fields.get("retired_to"), str) else None
    raw_aliases = fields.get("aliases", [])
    aliases: list[str] = raw_aliases if isinstance(raw_aliases, list) else []
    frontmatter_raw = text[: end]
    return PageInfo(
        path=path,
        slug=slug,
        kind=kind,
        frontmatter_raw=frontmatter_raw,
        frontmatter_end=end,
        title=title,
        retired_to=retired_to,
        aliases=aliases,
    )


def walk_vault(vault: Path) -> list[PageInfo]:
    kinds = ("concepts", "entities", "wisdom")
    pages: list[PageInfo] = []
    for kind in kinds:
        d = vault / "wiki" / kind
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            info = load_page(p)
            if info is not None:
                pages.append(info)
    return pages


def build_proposals(pages: Iterable[PageInfo]) -> tuple[list[AliasProposal], dict[str, str]]:
    by_slug: dict[str, PageInfo] = {p.slug: p for p in pages}
    proposals: dict[str, AliasProposal] = {}
    index: dict[str, str] = {}

    for p in pages:
        if not p.retired_to:
            continue
        canonical_slug = p.retired_to.strip()
        canonical_page = by_slug.get(canonical_slug)
        if canonical_page is None:
            # Dangling redirect — canonical missing. Skip; log to stderr.
            print(
                f"[warn] retire stub {p.path.name} → {canonical_slug} but canonical missing",
                file=sys.stderr,
            )
            continue

        prop = proposals.setdefault(
            canonical_slug,
            AliasProposal(canonical_slug=canonical_slug, canonical_path=canonical_page.path),
        )
        candidates = {p.slug}
        if p.title:
            candidates.add(slugify(p.title))
        # exclude canonical itself and existing aliases
        existing = set(canonical_page.aliases)
        for alias in sorted(candidates):
            if alias == canonical_slug or alias in existing or alias in prop.new_aliases:
                continue
            prop.new_aliases.append(alias)
            prop.provenance[alias] = p.slug
            index[alias] = canonical_slug

    # also include existing aliases → canonical mappings in the index for downstream lookups
    for p in pages:
        if p.retired_to:
            continue
        for a in p.aliases:
            index.setdefault(a, p.slug)
        # self-map for exact-slug lookups
        index.setdefault(p.slug, p.slug)

    # Also include the retire-stub slug → canonical direct entries (may already be there via new_aliases)
    for p in pages:
        if p.retired_to and p.retired_to.strip() in by_slug:
            index[p.slug] = p.retired_to.strip()

    ordered = sorted(proposals.values(), key=lambda x: x.canonical_slug)
    return ordered, index


def render_report(proposals: list[AliasProposal], vault: Path) -> str:
    lines = ["# Alias-table bootstrap report", ""]
    lines.append(f"Vault: `{vault}`")
    lines.append(f"Canonical pages receiving new aliases: **{len(proposals)}**")
    total_aliases = sum(len(p.new_aliases) for p in proposals)
    lines.append(f"Total new alias entries: **{total_aliases}**")
    lines.append("")
    lines.append("## Per-canonical proposals")
    lines.append("")
    for prop in proposals:
        lines.append(f"### `{prop.canonical_slug}` — `{prop.canonical_path.name}`")
        for alias in prop.new_aliases:
            source = prop.provenance.get(alias, "(bootstrap)")
            lines.append(f"- `{alias}` ← retire stub `{source}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def render_aliases_frontmatter_line(aliases: list[str]) -> str:
    items = ", ".join(sorted(set(aliases)))
    return f"aliases: [{items}]"


def apply_proposal(prop: AliasProposal) -> None:
    text = prop.canonical_path.read_text(encoding="utf-8")
    fields, end = parse_frontmatter(text)
    if not fields:
        raise RuntimeError(f"no frontmatter in canonical page {prop.canonical_path}")

    existing_aliases = fields.get("aliases", [])
    existing_list = existing_aliases if isinstance(existing_aliases, list) else []
    merged = sorted(set(existing_list) | set(prop.new_aliases))

    frontmatter_block = text[:end]
    body = text[end:]

    new_line = render_aliases_frontmatter_line(merged)
    if re.search(r"^aliases:\s*", frontmatter_block, re.MULTILINE):
        frontmatter_block = re.sub(
            r"^aliases:\s*.*$",
            new_line,
            frontmatter_block,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        # insert before closing ---
        frontmatter_block = re.sub(
            r"(\n)---\n$",
            rf"\1{new_line}\n---\n",
            frontmatter_block,
            count=1,
        )

    prop.canonical_path.write_text(frontmatter_block + body, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True, help="path to vault root (contains wiki/)")
    ap.add_argument("--dry-run", action="store_true", help="report only; no writes")
    ap.add_argument("--apply", action="store_true", help="write aliases: frontmatter + .aliases-index.json")
    ap.add_argument(
        "--report",
        default="eval/reports/aliases_bootstrap_2026-09-13.md",
        help="path to write the report",
    )
    args = ap.parse_args()

    if not (args.dry_run or args.apply):
        print("must pass --dry-run OR --apply", file=sys.stderr)
        return 2

    vault = Path(args.vault).expanduser()
    if not (vault / "wiki").is_dir():
        print(f"no wiki/ under {vault}", file=sys.stderr)
        return 2

    pages = walk_vault(vault)
    proposals, index = build_proposals(pages)

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(render_report(proposals, vault), encoding="utf-8")
    print(f"[dry-run] report written: {args.report}")
    print(f"[dry-run] canonicals receiving aliases: {len(proposals)}")
    print(f"[dry-run] total new alias entries:      {sum(len(p.new_aliases) for p in proposals)}")

    if args.apply:
        applied = 0
        for prop in proposals:
            if not prop.new_aliases:
                continue
            apply_proposal(prop)
            applied += 1
        index_path = vault / "wiki" / ".aliases-index.json"
        index_path.write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"[apply] wrote aliases: to {applied} canonical pages")
        print(f"[apply] index written: {index_path} ({len(index)} entries)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
