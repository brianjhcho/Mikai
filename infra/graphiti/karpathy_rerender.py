"""Karpathy-shape concept page renderer (Build 4).

Rewrites every file in ~/.mikai/wiki/concepts/*.md into the Karpathy
LLM Wiki shape: brief (~40 lines), TL;DR / Why / Notes / Sources
sections, basename-based `[[wikilinks]]` between concept pages.

Does NOT rerun the salience math. Reads:
- ~/.mikai/wiki/wiki-salience.md — for scores + goal-matches + rank
- ~/.mikai/wiki/concepts/*.md — for existing LLM summaries + mentions

Writes:
- ~/.mikai/wiki/concepts/*.md — rewritten in Karpathy shape
- ~/.mikai/wiki/concepts/index.md — top-level TOC with 1-line descriptions
- ~/.mikai/wiki/concepts/log.md — one line per rerender/promotion/demotion

Also injects backlinks: after all pages rewritten, scans every
`[[link]]` and adds a "Referenced by" section to each target that has
incoming edges.

Usage:
    python3 -m infra.graphiti.karpathy_rerender             # rerender all
    python3 -m infra.graphiti.karpathy_rerender --dry-run
    python3 -m infra.graphiti.karpathy_rerender --one <slug>
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
LEDGER_MD = WIKI_DIR / "wiki-salience.md"
INDEX_MD = CONCEPTS_DIR / "index.md"
LOG_MD = CONCEPTS_DIR / "log.md"


# ── Existing-page parsing (extract summary + mentions we already paid for) ──


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def parse_existing_page(path: Path) -> dict:
    """Extract what we need from a v001/v003-shape concept page:
    LLM summary paragraph, mention entries, aliases, existing S/G scores."""
    text = path.read_text(encoding="utf-8")
    out: dict = {"path": path, "slug": path.stem, "summary": "",
                 "mentions": [], "aliases": [], "salience": 0.0,
                 "g_score": 0.0, "best_goal": None, "kind": "concept",
                 "streams": []}

    m = _FRONTMATTER_RE.match(text)
    if m:
        for line in m.group(1).splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if k == "salience_score" or k == "salience":
                try:
                    out["salience"] = float(v)
                except ValueError:
                    pass
            elif k == "kind":
                out["kind"] = v or "concept"
            elif k == "aliases":
                # crude "[a, b, c]" parse
                v = v.strip("[]")
                out["aliases"] = [a.strip() for a in v.split(",") if a.strip()]
        body = text[m.end():]
    else:
        body = text

    # LLM summary = first non-empty paragraph after the # H1 title,
    # before the "## Salience breakdown" section (or "## Mentions" for
    # v001 pages that lacked "## Salience breakdown" header depth).
    heading_re = re.compile(r"^#\s+.+?$", re.MULTILINE)
    m1 = heading_re.search(body)
    if m1:
        after_h1 = body[m1.end():].strip()
    else:
        after_h1 = body.strip()
    stop = re.search(r"^##\s+(Salience breakdown|Mentions)", after_h1,
                     re.MULTILINE)
    summary_block = after_h1[:stop.start()].strip() if stop else ""
    # Skip name-echo lines like "Brian Cho" (from broken frontmatter)
    lines = [ln for ln in summary_block.splitlines() if ln.strip()]
    if lines:
        out["summary"] = " ".join(lines).strip()

    # Best-goal from breakdown line
    bg = re.search(r"best match:\s*`([^`]+)`", body)
    if bg:
        out["best_goal"] = bg.group(1).strip()
    gm = re.search(r"\*\*G\s*=\s*([\d.]+)\*\*", body)
    if gm:
        try:
            out["g_score"] = float(gm.group(1))
        except ValueError:
            pass
    sm_ = re.search(r"source streams\):\s*\d+\s*—\s*([^\n]+)", body)
    if sm_:
        out["streams"] = [s.strip() for s in sm_.group(1).split(",")]

    # Mentions: parse the "## Mentions" section list
    men_start = re.search(r"^##\s+Mentions", body, re.MULTILINE)
    if men_start:
        mention_body = body[men_start.end():]
        for line in mention_body.splitlines():
            line = line.strip()
            if not line.startswith("- [["):
                continue
            # Parse: - [[<ts> — <section name>]]  _(source: <stream>)_
            mm = re.match(r"- \[\[(\S+?) — (.+?)\]\](?:\s+_\(source:\s*(\S+?)\)_)?",
                          line)
            if mm:
                out["mentions"].append({
                    "header_ts": mm.group(1),
                    "section_name": mm.group(2),
                    "source_stream": (mm.group(3) or "").strip(),
                })
    return out


# ── Ledger parsing (for pretty title + goal-match) ──────────────────────────


def parse_ledger() -> dict:
    """slug -> {rank, S, G, best_goal, name}."""
    if not LEDGER_MD.exists():
        return {}
    raw = LEDGER_MD.read_text()
    section = re.search(r"##\s+Ranked candidates\s*\n(.*?)(?=^##\s|\Z)",
                        raw, re.DOTALL | re.MULTILINE)
    if not section:
        return {}
    out: dict = {}
    for line in section.group(1).splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or cells[0].lower().startswith("rank"):
            continue
        try:
            rank = int(cells[0])
        except ValueError:
            continue
        name = cells[1]
        slug = _slugify(name)
        out[slug] = {
            "rank": rank,
            "name": name,
            "S": _tryfloat(cells[2]) if len(cells) > 2 else 0.0,
            "G": _tryfloat(cells[6]) if len(cells) > 6 else 0.0,
            "best_goal": cells[7] if len(cells) > 7 else "",
        }
    return out


def _tryfloat(s: str) -> float:
    try:
        return float(s)
    except ValueError:
        return 0.0


def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unknown"


# ── Karpathy page rendering ─────────────────────────────────────────────────


def render_karpathy_page(page: dict, ledger_row: dict,
                         all_slugs: set[str]) -> str:
    """Render one Karpathy-shape page. Returns full markdown text."""
    slug = page["slug"]
    title = ledger_row.get("name", slug) if ledger_row else slug
    aliases = page.get("aliases", [])
    tags = [page.get("kind", "concept")]
    if ledger_row and ledger_row.get("best_goal"):
        tags.append("goal-matched")

    # TL;DR: first sentence of the LLM summary, capped.
    tldr = ""
    if page["summary"]:
        first = re.split(r"(?<=[.!?])\s+", page["summary"], 1)[0].strip()
        tldr = (first[:280] + "…") if len(first) > 280 else first
    if not tldr:
        tldr = f"_(no summary — {len(page['mentions'])} mentions in the wiki)_"

    # Why: derived from streams + goal alignment (no LLM call).
    # L3/L4 boundary: goal names are L4 metadata (which Surface Engine
    # signal promoted this) and MUST NOT appear as [[wikilinks]] in the
    # L3 page body — they're not L3 nodes. Goal name goes in
    # frontmatter (annotation only). Body prose can quote the goal name
    # in backticks; that's L3-safe display, not a wikilink promise.
    why_parts = []
    if page["streams"]:
        stream_list = ", ".join(f"`{s}`" for s in page["streams"][:5])
        why_parts.append(f"Recurs across {stream_list}")
    if ledger_row and ledger_row.get("best_goal"):
        goal_name = ledger_row["best_goal"]
        why_parts.append(f"aligns with goal `{goal_name}`")
    if ledger_row and ledger_row.get("rank"):
        why_parts.append(f"rank #{ledger_row['rank']} by recurrence score")
    why = ". ".join(why_parts) + "." if why_parts else \
          "Recurring pattern in the corpus."

    # Notes: cross-links to OTHER concept pages only. Aliases live in
    # frontmatter (rendered above) — do not re-emit as `[[alias]]`
    # wikilinks in Notes because those targets don't exist as pages
    # (they were folded INTO this page, so they resolve to /dev/null).
    # Verified 2026-08-10 lint: prior version emitted [[assistants]],
    # [[projects]], [[rights]], [[sessions]] — all broken links pointing
    # at pluralized alias keys that don't map to any actual file.
    notes_lines: list[str] = []
    my_tokens = {t for t in re.findall(r"[a-z]{4,}", slug + " " + title.lower())
                 if len(t) >= 4}
    related: list[str] = []
    for other in sorted(all_slugs):
        if other == slug:
            continue
        other_tokens = {t for t in re.findall(r"[a-z]{4,}", other)}
        if my_tokens & other_tokens:
            related.append(other)
    for r in related[:6]:
        notes_lines.append(f"- [[{r}]] — related concept")

    # Sources: last 12, date + stream + section name (not raw byte-timestamps)
    src_lines: list[str] = []
    seen_dates: set[str] = set()
    for m in page["mentions"][:40]:
        date = m["header_ts"][:10]
        stream = m.get("source_stream", "?")
        section = m.get("section_name", "")[:80]
        # dedupe same-day-same-source-same-section entries
        key = (date, stream, section)
        if key in seen_dates:
            continue
        seen_dates.add(key)
        src_lines.append(f"- {date} · `{stream}` · {section}")
        if len(src_lines) >= 12:
            break

    lines = [
        "---",
        f"title: {title}",
        f"tags: [{', '.join(tags)}]",
    ]
    if aliases:
        lines.append(f"aliases: [{', '.join(_slugify(a) for a in aliases)}]")
    if ledger_row:
        lines.append(f"salience: {ledger_row.get('S', 0):.2f}")
        lines.append(f"g_score: {ledger_row.get('G', 0):.2f}")
        if ledger_row.get("best_goal"):
            lines.append(f"best_goal: \"{ledger_row['best_goal']}\"")
    lines.append(
        f"rerendered: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    )
    lines.append("---")
    lines.append("")
    lines.append("## TL;DR")
    lines.append(tldr)
    lines.append("")
    lines.append("## Why")
    lines.append(why)
    lines.append("")
    lines.append("## Notes")
    lines.extend(notes_lines or ["- _(no cross-links yet)_"])
    lines.append("")
    total = len(page["mentions"])
    lines.append(f"## Sources ({total})")
    lines.extend(src_lines or ["- _(no sources captured)_"])
    if total > len(src_lines):
        lines.append(f"- _(and {total - len(src_lines)} more)_")
    return "\n".join(lines) + "\n"


# ── Backlink injection (pass 2, after all pages written) ────────────────────


def inject_backlinks() -> None:
    """Scan every concept page's [[links]] and add 'Referenced by' section
    to each target that has incoming edges."""
    pages = [p for p in CONCEPTS_DIR.glob("*.md")
             if p.stem not in ("index", "log")]
    incoming: dict[str, set[str]] = defaultdict(set)
    for p in pages:
        text = p.read_text(encoding="utf-8")
        for m in re.finditer(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]", text):
            target = _slugify(m.group(1))
            if target != p.stem:
                incoming[target].add(p.stem)
    for target_slug, sources in incoming.items():
        target_path = CONCEPTS_DIR / f"{target_slug}.md"
        if not target_path.exists():
            continue
        text = target_path.read_text(encoding="utf-8")
        # remove any prior Referenced-by section
        text = re.sub(r"\n## Referenced by.*?(?=\n## |\Z)", "", text,
                      flags=re.DOTALL)
        block = ["", "## Referenced by"]
        for s in sorted(sources)[:20]:
            block.append(f"- [[{s}]]")
        if len(sources) > 20:
            block.append(f"- _(and {len(sources) - 20} more)_")
        target_path.write_text(
            text.rstrip() + "\n" + "\n".join(block) + "\n", encoding="utf-8"
        )


# ── Index + log ─────────────────────────────────────────────────────────────


def write_index(ledger_by_slug: dict) -> None:
    """Top-level TOC: title, 1-line TL;DR, salience, goal-match."""
    pages = sorted(
        (p for p in CONCEPTS_DIR.glob("*.md")
         if p.stem not in ("index", "log")),
        key=lambda p: -ledger_by_slug.get(p.stem, {}).get("S", 0.0),
    )
    lines = [
        "# Concepts — Index",
        "",
        f"_{len(pages)} concept pages, sorted by salience. Auto-generated by "
        "`karpathy_rerender.py`. Every page is Karpathy-shape (TL;DR / Why "
        "/ Notes / Sources) with basename `[[wikilinks]]`._",
        "",
        f"_Regenerated: "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        "| Concept | Salience | Goal-match | TL;DR |",
        "|---|---|---|---|",
    ]
    for p in pages:
        row = ledger_by_slug.get(p.stem, {})
        # extract the TL;DR line from the page
        text = p.read_text(encoding="utf-8")
        m = re.search(r"##\s*TL;DR\s*\n(.+?)(?:\n\n|\n##)", text, re.DOTALL)
        tldr = " ".join(m.group(1).split()) if m else ""
        tldr = (tldr[:140] + "…") if len(tldr) > 140 else tldr
        s_val = row.get("S", 0.0)
        goal = row.get("best_goal", "") or "—"
        goal_disp = (goal[:32] + "…") if len(goal) > 32 else goal
        lines.append(
            f"| [[{p.stem}]] | {s_val:.2f} | {goal_disp} | {tldr} |"
        )
    INDEX_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_log(msg: str) -> None:
    """Append one dated line to log.md."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    line = f"- **{ts}** — {msg}\n"
    if not LOG_MD.exists():
        LOG_MD.write_text("# Concepts — Log\n\n", encoding="utf-8")
    with LOG_MD.open("a", encoding="utf-8") as f:
        f.write(line)


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--one", type=str,
                    help="rerender only <slug>, skip index/log/backlinks")
    args = ap.parse_args()

    if not CONCEPTS_DIR.exists():
        sys.exit(f"{CONCEPTS_DIR} not found — nothing to rerender")

    ledger_by_slug = parse_ledger()
    print(f"[rerender] ledger has {len(ledger_by_slug)} entries")

    files = sorted(CONCEPTS_DIR.glob("*.md"))
    files = [f for f in files if f.stem not in ("index", "log")]
    if args.one:
        files = [f for f in files if f.stem == args.one]
        if not files:
            sys.exit(f"no page found for slug={args.one!r}")

    all_slugs = {f.stem for f in files}
    print(f"[rerender] {len(files)} concept page(s)")
    skipped_authored = 0
    for f in files:
        # Protect hand-authored pages: any page with `authored: hand`
        # in its frontmatter is skipped. This bug bit us 2026-08-10 —
        # `posture-and-workout.md` got wiped by a rerender because
        # `parse_existing_page` didn't understand its Karpathy-shape
        # layout and fell back to empty. Hand pages are ground truth
        # for topics the extraction pipeline still misses.
        head = f.read_text(encoding="utf-8")[:800]
        if re.search(r"^authored:\s*hand\s*$", head, re.MULTILINE):
            skipped_authored += 1
            if args.dry_run:
                print(f"[dry-run] {f.name}: SKIP (authored: hand)")
            else:
                print(f"[rerender] {f.name}: SKIP (authored: hand)")
            continue
        page = parse_existing_page(f)
        ledger_row = ledger_by_slug.get(f.stem, {})
        new_text = render_karpathy_page(page, ledger_row, all_slugs)
        if args.dry_run:
            print(f"[dry-run] {f.name}: {len(new_text)} chars, "
                  f"{new_text.count(chr(10))+1} lines")
            if args.one:
                print("---")
                print(new_text)
        else:
            f.write_text(new_text, encoding="utf-8")
            print(f"[rerender] {f.name} ({len(new_text)}B, "
                  f"{new_text.count(chr(10))+1} lines)")

    if args.dry_run or args.one:
        return

    print("[rerender] injecting backlinks...")
    inject_backlinks()
    print("[rerender] writing index...")
    write_index(ledger_by_slug)
    append_log(f"rerendered {len(files)} pages in Karpathy shape (Build 4)")
    print(f"[rerender] index -> {INDEX_MD}")
    print(f"[rerender] log   -> {LOG_MD}")


if __name__ == "__main__":
    main()
