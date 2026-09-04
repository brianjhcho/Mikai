"""dream lint — health checks over ~/.mikai/wiki/concepts/*.md.

Karpathy's `/lint-wiki`. Scans:

1. **Broken wikilinks** — `[[foo]]` where `foo.md` doesn't exist in
   concepts/. Suggests: create the page, or accept it as noise +
   remove the bracket.
2. **Orphan pages** — pages with zero incoming backlinks AND not in
   index.md's TOC. Suggests: cross-link from a hub page, or demote.
3. **Goal gaps** — for each goal in ~/.mikai/brain/GOALS.md, is there
   any concept page whose title tokens overlap the goal? If not, the
   goal is declared-but-uncovered — a research gap the wiki suggests
   pursuing next.
4. **Concept-inbox review needs** — count of suggested-new concepts in
   ~/.mikai/wiki/concept-inbox.md that haven't been minted yet.

Contradictions detection deferred to v0.2 (requires pairwise LLM calls,
expensive at N² concepts).

Report → ~/.mikai/wiki/concepts/lint-report-YYYY-MM-DD.md
Non-destructive; makes no changes to any file.

Usage:
    python3 -m infra.graphiti.dream_lint
    python3 -m infra.graphiti.dream_lint --verbose
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

WIKI_DIR = Path.home() / ".mikai" / "wiki"
CONCEPTS_DIR = WIKI_DIR / "concepts"
INDEX_MD = CONCEPTS_DIR / "index.md"
LOG_MD = CONCEPTS_DIR / "log.md"
CONCEPT_INBOX = WIKI_DIR / "concept-inbox.md"
GOALS_MD = Path.home() / ".mikai" / "brain" / "GOALS.md"


_EXTRA_STOP = frozenset({
    "matters", "finding", "taking", "starting", "care", "and", "or",
    "of", "to", "for", "with", "the", "your", "our", "my",
})


def _tokenize(text: str, minlen: int = 4) -> set[str]:
    return {t for t in re.findall(rf"[a-z][a-z0-9]{{{minlen-1},}}", text.lower())
            if t not in _EXTRA_STOP}


def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unknown"


# ── Data collection ────────────────────────────────────────────────────


def collect_pages() -> dict[str, dict]:
    """slug -> {path, text, title, wikilinks: set[str], salience: float,
    best_goal: str, tags: list[str], aliases: list[str]}."""
    pages: dict = {}
    for p in sorted(CONCEPTS_DIR.glob("*.md")):
        if p.stem in ("index", "log"):
            continue
        text = p.read_text(encoding="utf-8")
        entry = {
            "path": p, "text": text, "title": p.stem, "wikilinks": set(),
            "salience": 0.0, "best_goal": None, "tags": [], "aliases": [],
        }
        fm = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
        if fm:
            for line in fm.group(1).splitlines():
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                k, v = k.strip(), v.strip()
                if k == "title":
                    entry["title"] = v or p.stem
                elif k == "salience":
                    try:
                        entry["salience"] = float(v)
                    except ValueError:
                        pass
                elif k == "best_goal":
                    entry["best_goal"] = v.strip('"\'')
                elif k == "tags":
                    entry["tags"] = [t.strip() for t in v.strip("[]").split(",")
                                     if t.strip()]
                elif k == "aliases":
                    entry["aliases"] = [
                        _slugify(a.strip().strip('"').strip("'"))
                        for a in v.strip("[]").split(",") if a.strip()
                    ]
        for m in re.finditer(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]", text):
            target = _slugify(m.group(1))
            if target != p.stem:
                entry["wikilinks"].add(target)
        pages[p.stem] = entry
    return pages


def read_index_slugs() -> set[str]:
    """Slugs referenced from the top-level index.md."""
    if not INDEX_MD.exists():
        return set()
    text = INDEX_MD.read_text(encoding="utf-8")
    return {_slugify(m.group(1))
            for m in re.finditer(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]", text)}


def load_goals() -> list[dict]:
    """[{name, tokens}] from GOALS.md (H2-per-goal, title tokens only)."""
    if not GOALS_MD.exists():
        return []
    raw = GOALS_MD.read_text()
    out = []
    for m in re.finditer(r"^##\s+(.+?)\s*$(.*?)(?=^##\s|\Z)", raw,
                         re.MULTILINE | re.DOTALL):
        title = m.group(1).strip()
        toks = _tokenize(title, minlen=3)
        if toks:
            out.append({"name": title, "tokens": toks})
    return out


def count_inbox_suggestions() -> int:
    """Rough count of `### slug` entries in concept-inbox.md."""
    if not CONCEPT_INBOX.exists():
        return 0
    return len(re.findall(r"^###\s+`([^`]+)`", CONCEPT_INBOX.read_text(),
                          re.MULTILINE))


# ── Lint checks ────────────────────────────────────────────────────────


def find_broken_links(pages: dict[str, dict]) -> list[tuple[str, str]]:
    """[(source_slug, target_slug)] where target doesn't exist as a page.
    Ignores goal-slug wikilinks (goals aren't concept pages)."""
    valid = set(pages.keys())
    broken = []
    for slug, entry in pages.items():
        for target in entry["wikilinks"]:
            if target not in valid:
                broken.append((slug, target))
    return sorted(broken)


def find_orphans(pages: dict[str, dict], index_slugs: set[str]) -> list[str]:
    """Pages with zero incoming wikilinks AND not in index.md."""
    incoming = defaultdict(int)
    for entry in pages.values():
        for target in entry["wikilinks"]:
            incoming[target] += 1
    return sorted(slug for slug in pages
                  if incoming[slug] == 0 and slug not in index_slugs)


def find_goal_gaps(pages: dict[str, dict], goals: list[dict]) -> list[dict]:
    """For each goal, list pages whose title-tokens overlap the goal's
    tokens. Goals with 0 matches = gaps."""
    results = []
    for g in goals:
        matches = []
        for slug, entry in pages.items():
            page_tokens = _tokenize(entry["title"] + " " + slug, minlen=3)
            overlap = g["tokens"] & page_tokens
            if overlap:
                matches.append((slug, len(overlap)))
        matches.sort(key=lambda x: -x[1])
        results.append({
            "goal": g["name"],
            "n_matches": len(matches),
            "top_matches": [m[0] for m in matches[:3]],
        })
    return results


# ── Report ─────────────────────────────────────────────────────────────


def write_report(pages: dict, broken: list, orphans: list,
                 goal_gaps: list, inbox_count: int, index_slugs: set,
                 out_path: Path) -> None:
    ts = datetime.now(timezone.utc)
    date = ts.strftime("%Y-%m-%d")
    lines = [
        f"# Lint Report — {date}",
        "",
        f"_Generated: {ts.strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "## Summary",
        "",
        f"- **{len(pages)}** concept pages scanned",
        f"- **{len(broken)}** broken wikilinks",
        f"- **{len(orphans)}** orphan pages",
        f"- **{sum(1 for g in goal_gaps if g['n_matches'] == 0)}** "
        f"of {len(goal_gaps)} goals have zero matching concept page",
        f"- **{inbox_count}** concept suggestions in `concept-inbox.md` "
        f"awaiting review",
        f"- **{len(index_slugs)}** concept pages referenced from `index.md`",
        "",
    ]

    lines += ["## Broken wikilinks", ""]
    if broken:
        lines.append("Every `[[target]]` below points to a concept page that "
                     "doesn't exist. Either create the page, remove the link, "
                     "or accept as intended (aspirational).")
        lines.append("")
        lines.append("| Source page | Broken target |")
        lines.append("|---|---|")
        by_target: dict = defaultdict(list)
        for src, tgt in broken:
            by_target[tgt].append(src)
        for tgt in sorted(by_target.keys()):
            sources = ", ".join(f"[[{s}]]" for s in by_target[tgt][:5])
            more = f" (+{len(by_target[tgt]) - 5})" if len(by_target[tgt]) > 5 else ""
            lines.append(f"| {sources}{more} | `{tgt}` |")
    else:
        lines.append("_None. Every wikilink resolves to an existing page._")
    lines.append("")

    lines += ["## Orphan pages", ""]
    if orphans:
        lines.append("Pages with zero incoming wikilinks AND not referenced "
                     "from `index.md`. Candidates for demotion or "
                     "cross-linking from a hub page.")
        lines.append("")
        for slug in orphans:
            title = pages[slug]["title"]
            sal = pages[slug]["salience"]
            lines.append(f"- [[{slug}]] — {title} (salience {sal:.2f})")
    else:
        lines.append("_None. Every page is either linked or in the index._")
    lines.append("")

    lines += ["## Goal-evidence gaps", ""]
    empty = [g for g in goal_gaps if g["n_matches"] == 0]
    if empty:
        lines.append("Goals from `~/.mikai/brain/GOALS.md` with **no matching "
                     "concept page** by title-token overlap. These are "
                     "research gaps — topics you declared care about but "
                     "the wiki has no dedicated page for.")
        lines.append("")
        for g in empty:
            lines.append(f"- **{g['goal']}** — no concept page found")
    else:
        lines.append("_Every goal has at least one matching concept page._")
    lines.append("")

    lines += ["## Goal coverage (all goals)", ""]
    lines.append("| Goal | # matching pages | Top matches |")
    lines.append("|---|---|---|")
    for g in goal_gaps:
        matches_disp = ", ".join(f"[[{s}]]" for s in g["top_matches"]) or "—"
        lines.append(f"| {g['goal'][:50]} | {g['n_matches']} | {matches_disp} |")
    lines.append("")

    lines += ["## Concept inbox", ""]
    if inbox_count > 0:
        lines.append(f"**{inbox_count}** suggested new concepts in "
                     f"`~/.mikai/wiki/concept-inbox.md` awaiting your review.")
        lines.append("")
        lines.append("Action: skim the inbox, decide which are worth minting "
                     "as concept pages. Rerun `dream promote` after minting "
                     "so their salience formula runs.")
    else:
        lines.append("_No pending suggestions in `concept-inbox.md`._")
    lines.append("")

    lines += ["## Next-action punchlist", ""]
    n_items = 0
    if broken:
        lines.append(f"- Fix or accept **{len(broken)}** broken wikilinks")
        n_items += 1
    if orphans:
        lines.append(f"- Cross-link or demote **{len(orphans)}** orphan pages")
        n_items += 1
    if empty:
        lines.append(f"- Research/promote pages for **{len(empty)}** "
                     f"goal-evidence gaps")
        n_items += 1
    if inbox_count > 0:
        lines.append(f"- Review **{inbox_count}** inbox suggestions")
        n_items += 1
    if n_items == 0:
        lines.append("- _(none — wiki is healthy)_")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── --fix mode (opt-in deterministic auto-repair) ─────────────────────
#
# Bounded, safe operations only. Matches kytmanov/obsidian-llm-wiki-local
# `olw maintain --fix` pattern: alias-rewrite + bounded stub creation.
# Never uses LLM. Never merges concepts. Never deletes.

MAX_STUBS_PER_RUN = 5    # kytmanov cap — bounded blast radius
MIN_REFS_FOR_STUB = 3    # only create stubs for targets referenced ≥3×


def build_alias_map(pages: dict[str, dict]) -> dict[str, str]:
    """Return {alias_slug: canonical_slug}. Ambiguous aliases (same alias
    on two pages) are excluded — we only auto-rewrite unambiguous matches."""
    alias_counts: dict[str, list[str]] = {}
    for canonical, entry in pages.items():
        for alias in entry.get("aliases", []):
            if alias == canonical:
                continue
            alias_counts.setdefault(alias, []).append(canonical)
    return {alias: cans[0] for alias, cans in alias_counts.items() if len(cans) == 1}


def fix_via_alias(pages: dict[str, dict], alias_map: dict[str, str],
                   broken: list[tuple[str, str]], dry_run: bool) -> int:
    """For each broken (source, target) pair where target matches an alias,
    rewrite [[target]] → [[canonical]] in the source page. Returns count fixed."""
    fixed = 0
    per_source: dict[str, list[tuple[str, str]]] = {}
    for src, tgt in broken:
        if tgt in alias_map:
            per_source.setdefault(src, []).append((tgt, alias_map[tgt]))

    for src, rewrites in per_source.items():
        page = pages.get(src)
        if not page:
            continue
        text = page["text"]
        original = text
        for tgt, canonical in rewrites:
            # Rewrite [[tgt]] and [[tgt|display]] → [[canonical]] / [[canonical|display]]
            text = re.sub(
                rf"\[\[{re.escape(tgt)}(\||\]\])",
                f"[[{canonical}\\1",
                text,
            )
        if text != original:
            n_fixes = len(rewrites)
            if dry_run:
                print(f"  [dry] would rewrite in {src}.md: "
                      + ", ".join(f"[[{t}]]→[[{c}]]" for t, c in rewrites))
            else:
                page["path"].write_text(text, encoding="utf-8")
                page["text"] = text
                print(f"  fixed {src}.md: "
                      + ", ".join(f"[[{t}]]→[[{c}]]" for t, c in rewrites))
            fixed += n_fixes
    return fixed


def create_stubs(broken: list[tuple[str, str]], dry_run: bool,
                  max_stubs: int = MAX_STUBS_PER_RUN,
                  min_refs: int = MIN_REFS_FOR_STUB) -> list[str]:
    """Create stub .md files for broken targets referenced ≥min_refs times.
    Capped at max_stubs per run. Stubs are marked with a placeholder callout.
    Returns list of slugs stubbed. NEVER creates a stub if the file already exists."""
    ref_counts: dict[str, int] = {}
    ref_sources: dict[str, set[str]] = {}
    for src, tgt in broken:
        ref_counts[tgt] = ref_counts.get(tgt, 0) + 1
        ref_sources.setdefault(tgt, set()).add(src)

    candidates = sorted(
        [(tgt, n) for tgt, n in ref_counts.items() if n >= min_refs],
        key=lambda x: -x[1],
    )[:max_stubs]

    if not candidates:
        print(f"  no stub candidates (need ≥{min_refs} refs; max {max_stubs}/run)")
        return []

    stubbed = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for slug, n_refs in candidates:
        stub_path = CONCEPTS_DIR / f"{slug}.md"
        if stub_path.exists():
            continue
        sources = sorted(ref_sources[slug])
        content = f"""---
title: {slug.replace('-', ' ').title()}
slug: {slug}
tags: [concept, stub, lint-created]
authored: stub
minted: {today}
touch_count: 0
salience: 0.0
best_goal: ""
---

> [!warning] Stub — created by lint --fix
> This page was created because {n_refs} other concept pages reference
> `[[{slug}]]` but the page did not exist. Awaiting synthesis.

## TL;DR
_(no synthesis yet — this stub was auto-created by lint --fix on {today}
because {n_refs} pages linked to it; will be populated by a future ingest
run or dream-pass consolidation.)_

## Referenced by
""" + "\n".join(f"- [[{s}]]" for s in sources) + "\n"

        if dry_run:
            print(f"  [dry] would create stub: {slug}.md ({n_refs} refs)")
        else:
            stub_path.write_text(content, encoding="utf-8")
            print(f"  created stub: {slug}.md ({n_refs} refs)")
        stubbed.append(slug)
    return stubbed


def _append_log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not LOG_MD.exists():
        LOG_MD.write_text("# Concepts — Log\n\n", encoding="utf-8")
    with LOG_MD.open("a", encoding="utf-8") as f:
        f.write(f"- **{ts}** — {msg}\n")


def main() -> None:
    ap = argparse.ArgumentParser(prog="dream-lint")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument(
        "--fix", action="store_true",
        help="deterministic auto-repair mode: alias-rewrites + bounded stub "
             "creation (kytmanov `olw maintain --fix` pattern). NO LLM. "
             "Never merges concepts. Never deletes.",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="preview --fix actions without writing to disk",
    )
    args = ap.parse_args()

    if not CONCEPTS_DIR.exists():
        sys.exit(f"{CONCEPTS_DIR} not found — no concept pages to lint")

    pages = collect_pages()
    print(f"[lint] {len(pages)} concept pages")
    index_slugs = read_index_slugs()
    print(f"[lint] {len(index_slugs)} slugs referenced from index.md")
    goals = load_goals()
    print(f"[lint] {len(goals)} goals from GOALS.md")
    inbox_count = count_inbox_suggestions()
    print(f"[lint] {inbox_count} suggestions in concept-inbox.md")

    broken = find_broken_links(pages)
    orphans = find_orphans(pages, index_slugs)
    goal_gaps = find_goal_gaps(pages, goals)

    n_gaps = sum(1 for g in goal_gaps if g["n_matches"] == 0)
    print(f"[lint] broken={len(broken)}  orphans={len(orphans)}  "
          f"goal-gaps={n_gaps}/{len(goals)}")

    if args.verbose:
        if broken:
            print("  broken (first 5):")
            for src, tgt in broken[:5]:
                print(f"    [[{src}]] -> [[{tgt}]]  (target missing)")
        if orphans:
            print(f"  orphans (first 5): {', '.join(orphans[:5])}")
        for g in goal_gaps:
            if g["n_matches"] == 0:
                print(f"  gap: {g['goal']}")

    # ── --fix mode (opt-in) ────────────────────────────────────────
    if args.fix or args.dry_run:
        dry = args.dry_run and not args.fix
        mode = "dry-run" if dry else "live"
        print(f"\n[fix:{mode}] running deterministic auto-repair")

        alias_map = build_alias_map(pages)
        print(f"  alias-map: {len(alias_map)} unambiguous aliases available")

        n_alias_fixed = fix_via_alias(pages, alias_map, broken, dry_run=dry)
        print(f"  alias-rewrites: {n_alias_fixed}")

        stubbed = create_stubs(broken, dry_run=dry)
        print(f"  stubs created: {len(stubbed)}")

        if not dry:
            print(f"[fix:live] complete — re-run lint (without --fix) "
                  f"to confirm reduced broken-link count")

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = CONCEPTS_DIR / f"lint-report-{date}.md"
    write_report(pages, broken, orphans, goal_gaps, inbox_count,
                 index_slugs, out)
    print(f"[lint] report -> {out}")
    _append_log(
        f"lint: {len(broken)} broken, {len(orphans)} orphans, "
        f"{n_gaps} goal-gaps, {inbox_count} inbox items"
        + (f" [--fix applied: {n_alias_fixed} rewrites, {len(stubbed)} stubs]"
           if args.fix else "")
    )


if __name__ == "__main__":
    main()
