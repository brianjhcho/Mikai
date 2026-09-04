"""dream_apply — execute human-approved merge proposals from concept-inbox.md.

Reads concept-inbox.md, finds `## dream-consolidate proposals` sections,
parses individual proposal blocks (### merge: / ### tension:), executes
APPROVE-marked proposals.

For each APPROVED merge:
  1. Load canonical + loser pages
  2. Rewrite canonical:
     - update aliases frontmatter with loser's slug + loser's own aliases
     - update TL;DR to the proposed merged version
     - append loser's Sources citations to canonical's Sources
     - bump last_rerender frontmatter
  3. Move loser to concepts/_retired/<slug>.md with `superseded_by: <canonical>`
     frontmatter breadcrumb — DOES NOT DELETE (rohitg00 v2 supersession pattern)
  4. Rewrite wikilinks throughout the vault: [[loser]] → [[canonical]]
  5. Log delta to log.md

For each APPROVED tension: adds a `## Tensions` section (with a cross-reference)
to both pages, no merge.

Idempotent: proposals marked APPLIED after execution; second run skips them.
Never deletes anything — retirement moves to _retired/, breadcrumb preserved.

Reference: docs/DREAM_PASS.md § Phase D (Prune & Index).
"""

from __future__ import annotations

import re
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

WIKI_DIR = Path.home() / ".mikai" / "wiki"
CONCEPTS_DIR = WIKI_DIR / "concepts"
RETIRED_DIR = CONCEPTS_DIR / "_retired"
SOURCES_DIR = WIKI_DIR / "sources"
INBOX = WIKI_DIR / "concept-inbox.md"
LOG_MD = WIKI_DIR / "log.md"

# Parse proposal block header:
# ### merge: [[canonical]] ← absorbs [[loser]]  (jaccard=0.42, LLM-conf=0.88)
MERGE_HEADER_RE = re.compile(
    r"^###\s+merge:\s+\[\[([a-z0-9-]+)\]\]\s+←\s+absorbs\s+\[\[([a-z0-9-]+)\]\]"
)
TENSION_HEADER_RE = re.compile(
    r"^###\s+tension:\s+\[\[([a-z0-9-]+)\]\]\s+↔\s+\[\[([a-z0-9-]+)\]\]"
)


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def parse_inbox_proposals() -> list[dict]:
    """Extract APPROVE-marked merge and tension proposals from inbox."""
    if not INBOX.exists():
        return []
    text = INBOX.read_text(encoding="utf-8")
    # Split by ### headers so each proposal is one block
    blocks = re.split(r"(?=^###\s+(?:merge|tension):)", text, flags=re.MULTILINE)
    proposals = []
    for block in blocks:
        if not block.strip().startswith("###"):
            continue
        first_line = block.splitlines()[0]
        m_merge = MERGE_HEADER_RE.match(first_line)
        m_tension = TENSION_HEADER_RE.match(first_line)
        # Check APPROVE marker (must be exact — case-sensitive, uppercase)
        approved = bool(re.search(r"\*\*APPROVE\*\*|^APPROVE\b|APPROVE\s*$",
                                  block, re.MULTILINE))
        approved_tension = bool(re.search(r"\*\*APPROVE-tension\*\*|APPROVE-tension",
                                          block))
        applied = "**APPLIED**" in block or "**APPLIED-tension**" in block
        if applied:
            continue
        if m_merge and approved:
            proposals.append({
                "type": "merge",
                "canonical": m_merge.group(1),
                "loser": m_merge.group(2),
                "block": block,
                "aliases": _extract_field_list(block, "Aliases to add to canonical"),
                "merged_tldr": _extract_multiline(block, "Proposed merged TL;DR"),
            })
        elif m_tension and approved_tension:
            proposals.append({
                "type": "tension",
                "a": m_tension.group(1),
                "b": m_tension.group(2),
                "block": block,
                "why": _extract_field(block, "Why"),
            })
    return proposals


def _extract_field(block: str, key: str) -> str:
    m = re.search(rf"\*\*{re.escape(key)}:\*\*\s*(.+?)(?:\n\*\*|\n\n|\Z)", block, re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_field_list(block: str, key: str) -> list[str]:
    raw = _extract_field(block, key)
    if not raw:
        return []
    # Parse ['a', 'b'] or [a, b]
    raw = raw.strip("[]")
    return [x.strip().strip('"').strip("'") for x in raw.split(",") if x.strip()]


def _extract_multiline(block: str, key: str) -> str:
    m = re.search(rf"\*\*{re.escape(key)}:\*\*\s*\n?>?\s*(.+?)(?:\n\*\*|\n###|\Z)",
                  block, re.DOTALL)
    return m.group(1).strip().lstrip(">").strip() if m else ""


# ── Merge execution ─────────────────────────────────────────────────

def read_page(slug: str) -> tuple[str, str] | None:
    """Return (frontmatter, body) or None if missing."""
    p = CONCEPTS_DIR / f"{slug}.md"
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    m = re.match(r"\A---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not m:
        return None
    return m.group(1), m.group(2)


def extract_sources_section(body: str) -> str:
    m = re.search(r"(##\s*Sources[^\n]*\n.*?)(?=\n##\s|\Z)", body, re.DOTALL)
    return m.group(1).rstrip() if m else ""


def merge_frontmatter(fm: str, new_aliases: list[str], new_tldr: str = "") -> str:
    """Update aliases + last_rerender in frontmatter."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Existing aliases
    m = re.search(r"^aliases:\s*\[(.*?)\]", fm, re.MULTILINE)
    existing = []
    if m:
        existing = [a.strip().strip('"').strip("'")
                    for a in m.group(1).split(",") if a.strip()]
    merged_aliases = sorted(set(existing + new_aliases))
    aliases_line = "aliases: [" + ", ".join(merged_aliases) + "]"
    if m:
        fm = re.sub(r"^aliases:.*$", aliases_line, fm, count=1, flags=re.MULTILINE)
    else:
        fm += f"\n{aliases_line}"
    # last_rerender
    if re.search(r"^last_rerender:", fm, re.MULTILINE):
        fm = re.sub(r"^last_rerender:.*$", f"last_rerender: {today}",
                    fm, count=1, flags=re.MULTILINE)
    else:
        fm += f"\nlast_rerender: {today}"
    return fm


def execute_merge(prop: dict) -> bool:
    canonical, loser = prop["canonical"], prop["loser"]
    log(f"  merge: [[{canonical}]] ← absorbs [[{loser}]]")

    can_read = read_page(canonical)
    loser_read = read_page(loser)
    if not can_read:
        log(f"    SKIP: canonical page missing: {canonical}")
        return False
    if not loser_read:
        log(f"    SKIP: loser page missing: {loser}")
        return False

    can_fm, can_body = can_read
    loser_fm, loser_body = loser_read

    # Update canonical frontmatter
    new_aliases = [loser] + prop.get("aliases", [])
    can_fm_new = merge_frontmatter(can_fm, new_aliases)

    # Append loser's Sources into canonical's Sources
    loser_sources = extract_sources_section(loser_body)
    can_body_new = can_body
    if loser_sources:
        # Strip the "## Sources" header from loser's block, keep only bullets
        loser_bullets = "\n".join(loser_sources.splitlines()[1:]).strip()
        if loser_bullets:
            can_sources = extract_sources_section(can_body)
            if can_sources:
                # Insert loser bullets before end of canonical Sources section
                can_body_new = can_body_new.replace(
                    can_sources,
                    can_sources.rstrip() + "\n" + loser_bullets + "\n",
                    1,
                )
            else:
                can_body_new = (can_body_new.rstrip()
                                + f"\n\n## Sources\n{loser_bullets}\n")

    # Update TL;DR if a merged version was provided
    merged_tldr = prop.get("merged_tldr", "").strip()
    if merged_tldr:
        can_body_new = re.sub(
            r"(##\s*TL;DR\s*\n)(.+?)(\n\n|\n##)",
            r"\1" + merged_tldr + r"\3",
            can_body_new,
            count=1,
            flags=re.DOTALL,
        )

    # Write canonical
    (CONCEPTS_DIR / f"{canonical}.md").write_text(
        f"---\n{can_fm_new}\n---\n{can_body_new}", encoding="utf-8"
    )
    log(f"    wrote canonical: {canonical}.md")

    # Retire loser
    RETIRED_DIR.mkdir(parents=True, exist_ok=True)
    loser_new_fm = loser_fm
    if re.search(r"^superseded_by:", loser_new_fm, re.MULTILINE):
        loser_new_fm = re.sub(r"^superseded_by:.*$",
                              f"superseded_by: {canonical}",
                              loser_new_fm, count=1, flags=re.MULTILINE)
    else:
        loser_new_fm += f"\nsuperseded_by: {canonical}"
    loser_new_fm += f"\nretired_at: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    (RETIRED_DIR / f"{loser}.md").write_text(
        f"---\n{loser_new_fm}\n---\n{loser_body}", encoding="utf-8"
    )
    (CONCEPTS_DIR / f"{loser}.md").unlink()
    log(f"    retired: {loser}.md → _retired/")

    # Rewrite wikilinks: [[loser]] → [[canonical]] across concepts/ and sources/
    rewrite_count = 0
    for md_path in list(CONCEPTS_DIR.rglob("*.md")) + list(SOURCES_DIR.rglob("*.md")):
        if md_path == RETIRED_DIR / f"{loser}.md":
            continue
        try:
            t = md_path.read_text(encoding="utf-8")
        except Exception:
            continue
        # Rewrite [[loser]] and [[loser|display]] variants
        new_t, n = re.subn(rf"\[\[{re.escape(loser)}(\||\]\])",
                           f"[[{canonical}\\1", t)
        if n > 0:
            md_path.write_text(new_t, encoding="utf-8")
            rewrite_count += n
    log(f"    rewrote {rewrite_count} wikilinks: [[{loser}]] → [[{canonical}]]")
    return True


def execute_tension(prop: dict) -> bool:
    a, b = prop["a"], prop["b"]
    why = prop.get("why", "overlap with tension")
    log(f"  tension: [[{a}]] ↔ [[{b}]]")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for slug, other in [(a, b), (b, a)]:
        read = read_page(slug)
        if not read:
            log(f"    SKIP: page missing: {slug}")
            continue
        fm, body = read
        if f"[[{other}]]" in body:
            continue  # already cross-linked
        tension_addition = (
            f"\n\n## Tensions\n"
            f"- {today} · dream_pass surfaced overlap with [[{other}]]: {why}\n"
        )
        # Append tensions section if not present
        if "## Tensions" not in body:
            body_new = body.rstrip() + tension_addition
        else:
            # Append bullet to existing tensions section
            body_new = re.sub(
                r"(##\s*Tensions[^\n]*\n)((?:(?!\n##).)*?)(?=\n##|\Z)",
                r"\1\2" + f"- {today} · overlap with [[{other}]]: {why}\n",
                body, count=1, flags=re.DOTALL,
            )
        (CONCEPTS_DIR / f"{slug}.md").write_text(f"---\n{fm}\n---\n{body_new}",
                                                  encoding="utf-8")
    log(f"    added cross-references between {a} and {b}")
    return True


def mark_applied(prop: dict) -> None:
    """Replace APPROVE with APPLIED in the inbox for this proposal."""
    text = INBOX.read_text(encoding="utf-8")
    old_block = prop["block"]
    if prop["type"] == "merge":
        new_block = re.sub(r"\*\*APPROVE\*\*", "**APPLIED**", old_block, count=1)
        new_block = re.sub(r"^APPROVE\b", "APPLIED", new_block, count=1,
                           flags=re.MULTILINE)
    else:
        new_block = re.sub(r"\*\*APPROVE-tension\*\*", "**APPLIED-tension**",
                           old_block, count=1)
        new_block = re.sub(r"APPROVE-tension", "APPLIED-tension",
                           new_block, count=1)
    if new_block != old_block:
        text = text.replace(old_block, new_block, 1)
        INBOX.write_text(text, encoding="utf-8")


def append_log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with LOG_MD.open("a", encoding="utf-8") as f:
        f.write(f"\n## dream_apply — {ts}\n{msg}\n")


def main(dry_run: bool = False) -> None:
    log(f"dream_apply start (dry_run={dry_run})")
    proposals = parse_inbox_proposals()
    log(f"found {len(proposals)} APPROVED proposals in inbox")
    if not proposals:
        log("nothing to apply — no APPROVED proposals found")
        return

    merged, tensioned, failed = 0, 0, 0
    for prop in proposals:
        if dry_run:
            log(f"[dry-run] would apply {prop['type']}: "
                f"{prop.get('canonical', prop.get('a'))} "
                f"{'←' if prop['type']=='merge' else '↔'} "
                f"{prop.get('loser', prop.get('b'))}")
            continue
        try:
            if prop["type"] == "merge":
                if execute_merge(prop):
                    mark_applied(prop)
                    merged += 1
                else:
                    failed += 1
            elif prop["type"] == "tension":
                if execute_tension(prop):
                    mark_applied(prop)
                    tensioned += 1
                else:
                    failed += 1
        except Exception as e:
            log(f"  FAIL {prop.get('canonical', '?')}: {e}")
            failed += 1

    summary = f"merged={merged}, tensions={tensioned}, failed={failed}"
    log(f"dream_apply complete: {summary}")
    if not dry_run:
        append_log(summary)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="dream_apply")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        main(dry_run=args.dry_run)
    except Exception:
        print("FATAL:\n" + traceback.format_exc())
        sys.exit(1)
