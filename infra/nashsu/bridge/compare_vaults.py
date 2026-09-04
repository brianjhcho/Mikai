"""compare_vaults.py — analyze two nashsu-produced wiki vaults.

Phase 11 of fuzzy-shimmying-wreath plan. Answers: does the headless port
produce equivalent wiki quality to the desktop app, accounting for known
confounds (template mismatch, version drift, outputLanguage bug)?

No re-ingest — reads existing vault output only.

Metrics computed:

A. Clean surfaces (comparable despite confounds):
   - Source-summary word / wikilink counts (distributional)
   - Source-summary wikilink target Jaccard (per shared source)
   - Frontmatter parity (per shared source)
   - Concept/entity slug Jaccard (overall + English-source filtered)

B. Confounded surfaces (reported with label):
   - Page-type distribution (template mismatch)
   - Non-English page count (outputLanguage bug on headless)

C. Nondeterminism reference:
   - Overall concept Jaccard vs the ~7% baseline from parallelism A/B

Usage:
  python compare_vaults.py \\
    --vault-a ~/.mikai/wiki-golden \\
    --vault-b "/Users/briancho/Desktop/Golden-wiki comparison" \\
    --report eval/reports/vault_comparison_2026-08-18.md
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Iterable

WIKI_SUBDIRS = [
    "concepts", "entities", "sources", "queries", "journal",
    "goals", "habits", "reflections", "comparisons", "synthesis", "media",
]

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?(?:#[^\]]+)?\]\]")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def read_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter-dict, body). Stdlib-only, so YAML parsing is
    hand-rolled for the specific field shapes nashsu emits (scalars,
    inline lists like [a, b, c], quoted strings)."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_raw, body = m.group(1), m.group(2)
    fm: dict = {}
    for line in fm_raw.splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            fm[k] = [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
        else:
            fm[k] = v.strip('"').strip("'")
    return fm, body


def wikilinks_in(text: str) -> set[str]:
    return {m.strip().lower() for m in WIKILINK_RE.findall(text)}


def word_count(text: str) -> int:
    return len(text.split())


def non_ascii_ratio(text: str) -> float:
    if not text:
        return 0.0
    non_ascii = sum(1 for c in text if ord(c) > 127)
    return non_ascii / len(text)


def enumerate_pages(vault: Path) -> dict[str, list[Path]]:
    """Return {subdir_name: [page paths]}. Skips missing subdirs."""
    result: dict[str, list[Path]] = {}
    for sub in WIKI_SUBDIRS:
        d = vault / "wiki" / sub
        if not d.is_dir():
            result[sub] = []
            continue
        result[sub] = sorted(p for p in d.iterdir() if p.suffix == ".md" and p.name != "index.md")
    return result


def raw_source_names(vault: Path) -> set[str]:
    d = vault / "raw" / "sources"
    if not d.is_dir():
        return set()
    return {p.name for p in d.iterdir() if p.suffix == ".md"}


def concept_slugs(pages: list[Path]) -> set[str]:
    return {p.stem.lower() for p in pages}


def is_english_only_source(text: str) -> bool:
    """Heuristic: source body has < 2% non-ASCII characters."""
    return non_ascii_ratio(text) < 0.02


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def compare_shared_sources(
    vault_a: Path, vault_b: Path, shared_srcs: Iterable[str]
) -> tuple[list[dict], set[str]]:
    """For each shared source (by raw filename), find its wiki/sources/
    summary in each vault and compute per-page metrics. Also returns the
    set of shared sources that are English-only (for downstream filtering
    of the concept-Jaccard on clean subset)."""
    rows: list[dict] = []
    english_only: set[str] = set()
    for srcname in sorted(shared_srcs):
        pa = vault_a / "wiki" / "sources" / srcname
        pb = vault_b / "wiki" / "sources" / srcname
        raw_a = (vault_a / "raw" / "sources" / srcname).read_text(encoding="utf-8", errors="replace")
        if is_english_only_source(raw_a):
            english_only.add(srcname)
        if not pa.exists() or not pb.exists():
            continue
        ta = pa.read_text(encoding="utf-8", errors="replace")
        tb = pb.read_text(encoding="utf-8", errors="replace")
        fma, body_a = read_frontmatter(ta)
        fmb, body_b = read_frontmatter(tb)
        wa = wikilinks_in(body_a)
        wb = wikilinks_in(body_b)
        rows.append({
            "source": srcname,
            "english_only": srcname in english_only,
            "words_a": word_count(body_a),
            "words_b": word_count(body_b),
            "wikilinks_a": len(wa),
            "wikilinks_b": len(wb),
            "wikilink_jaccard": jaccard(wa, wb),
            "same_title": fma.get("title") == fmb.get("title"),
            "same_tags_set": set(fma.get("tags") or []) == set(fmb.get("tags") or []),
            "same_related_set": set(fma.get("related") or []) == set(fmb.get("related") or []),
            "non_ascii_a": non_ascii_ratio(body_a),
            "non_ascii_b": non_ascii_ratio(body_b),
        })
    return rows, english_only


def concepts_from_english_sources(
    vault: Path, english_only: set[str]
) -> set[str]:
    """Return concept slugs whose frontmatter `sources:` list intersects
    the English-only source name set."""
    concepts_dir = vault / "wiki" / "concepts"
    result: set[str] = set()
    if not concepts_dir.is_dir():
        return result
    for p in concepts_dir.iterdir():
        if p.suffix != ".md":
            continue
        fm, _ = read_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
        srcs = set(fm.get("sources") or [])
        if srcs & english_only:
            result.add(p.stem.lower())
    return result


def count_non_english_concepts(vault: Path) -> tuple[int, list[str]]:
    concepts_dir = vault / "wiki" / "concepts"
    if not concepts_dir.is_dir():
        return 0, []
    flagged: list[str] = []
    for p in concepts_dir.iterdir():
        if p.suffix != ".md":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        _, body = read_frontmatter(text)
        if non_ascii_ratio(body) > 0.05:
            flagged.append(p.name)
    return len(flagged), sorted(flagged)


QUOTE_LINE_RE = re.compile(r'^>\s+"[^"]')
ATTR_LINE_RE = re.compile(r"^>\s+—\s+from\s+\[\[")


def wisdom_stats(vault: Path) -> dict:
    """Per-page and aggregate stats for wiki/wisdom/*.md pages."""
    wdir = vault / "wiki" / "wisdom"
    pages: list[dict] = []
    if not wdir.is_dir():
        return {"pages": [], "total_pages": 0, "total_quotes": 0,
                "median_quotes": 0, "p90_quotes": 0,
                "weak_pages": [], "unattributed_pages": []}
    for p in sorted(wdir.iterdir()):
        if p.suffix != ".md" or p.name == "index.md":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        _, body = read_frontmatter(text)
        lines = body.splitlines()
        quote_lines = sum(1 for L in lines if QUOTE_LINE_RE.match(L))
        attr_lines = sum(1 for L in lines if ATTR_LINE_RE.match(L))
        pages.append({
            "slug": p.stem,
            "quotes": quote_lines,
            "attributions": attr_lines,
        })
    totals = [pg["quotes"] for pg in pages] or [0]
    n = len(pages)
    return {
        "pages": pages,
        "total_pages": n,
        "total_quotes": sum(totals),
        "median_quotes": statistics.median(totals) if totals else 0,
        "p90_quotes": sorted(totals)[max(0, int(0.9 * n) - 1)] if n else 0,
        "weak_pages": [pg["slug"] for pg in pages if pg["quotes"] < 5],
        "unattributed_pages": [pg["slug"] for pg in pages if pg["attributions"] == 0],
    }


def find_adjacent_concept_pairs(only_a: set[str], only_b: set[str],
                                 min_shared_tokens: int = 1) -> list[tuple[str, str, str]]:
    """Cheap semantic-adjacency heuristic: two slugs from opposite sides are
    'adjacent' when they share a hyphen-split token of length >= 4 (skip
    stopwords), OR one is a substring of the other. Returns list of
    (slug_a, slug_b, reason) tuples."""
    STOP = {"the", "and", "for", "with", "from", "into", "over", "your",
            "this", "that", "what", "have", "been", "are"}
    def tokens(slug: str) -> set[str]:
        return {t for t in slug.split("-") if len(t) >= 4 and t not in STOP}
    pairs: list[tuple[str, str, str]] = []
    tok_a = {s: tokens(s) for s in only_a}
    tok_b = {s: tokens(s) for s in only_b}
    for sa in sorted(only_a):
        ta = tok_a[sa]
        for sb in sorted(only_b):
            reason = None
            if sa in sb or sb in sa:
                reason = "substring"
            else:
                shared = ta & tok_b[sb]
                if len(shared) >= min_shared_tokens:
                    reason = f"shared:{','.join(sorted(shared))}"
            if reason:
                pairs.append((sa, sb, reason))
    return pairs


def pick_sample_sources(shared_srcs: set[str], raw_dir_a: Path) -> list[str]:
    """Deterministic picker: one light (< 20KB), one medium (20-100KB),
    one heavy (>= 100KB). First-alpha in each bucket. Skip sources under
    500 bytes — those are Apple Notes ingest truncations, not real content."""
    MIN_USEFUL_BYTES = 500
    buckets: dict[str, list[tuple[int, str]]] = {"light": [], "medium": [], "heavy": []}
    for name in shared_srcs:
        f = raw_dir_a / name
        if not f.exists():
            continue
        size = f.stat().st_size
        if size < MIN_USEFUL_BYTES:
            continue
        if size < 20 * 1024:
            buckets["light"].append((size, name))
        elif size < 100 * 1024:
            buckets["medium"].append((size, name))
        else:
            buckets["heavy"].append((size, name))
    picked: list[str] = []
    for k in ("light", "medium", "heavy"):
        if buckets[k]:
            picked.append(sorted(buckets[k])[0][1])
    return picked


def qualitative_sample(vault_a: Path, vault_b: Path,
                       shared_srcs: set[str],
                       label_a: str, label_b: str,
                       max_body_chars: int = 2500) -> str:
    """Render side-by-side sample of source-summary pages for a
    light/medium/heavy triple. Also lists concept and wisdom pages that
    each vault attributed to each source (via reverse frontmatter lookup)."""
    picks = pick_sample_sources(shared_srcs, vault_a / "raw" / "sources")
    if not picks:
        return "_No shared sources with readable raw files; skipping qualitative sample._\n"

    # Build reverse index: source-filename -> {concepts, wisdom} per vault
    def reverse_index(vault: Path) -> dict[str, dict[str, list[str]]]:
        idx: dict[str, dict[str, list[str]]] = {}
        for sub in ("concepts", "wisdom"):
            d = vault / "wiki" / sub
            if not d.is_dir():
                continue
            for p in d.iterdir():
                if p.suffix != ".md" or p.name == "index.md":
                    continue
                fm, _ = read_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
                srcs = fm.get("sources") or []
                for s in srcs:
                    idx.setdefault(s, {"concepts": [], "wisdom": []})
                    idx[s][sub].append(p.stem)
        return idx

    rev_a = reverse_index(vault_a)
    rev_b = reverse_index(vault_b)

    out: list[str] = []
    for srcname in picks:
        raw = vault_a / "raw" / "sources" / srcname
        size_kb = raw.stat().st_size / 1024 if raw.exists() else 0
        bucket = "light" if size_kb < 20 else ("medium" if size_kb < 100 else "heavy")
        out.append(f"\n### Sample — `{srcname}` ({bucket}, {size_kb:.1f}KB)\n")

        pa = vault_a / "wiki" / "sources" / srcname
        pb = vault_b / "wiki" / "sources" / srcname
        body_a = ""
        body_b = ""
        if pa.exists():
            _, body_a = read_frontmatter(pa.read_text(encoding="utf-8", errors="replace"))
        if pb.exists():
            _, body_b = read_frontmatter(pb.read_text(encoding="utf-8", errors="replace"))
        excerpt_a = body_a[:max_body_chars].strip()
        excerpt_b = body_b[:max_body_chars].strip()

        out.append(f"**{label_a} source-summary body (first {max_body_chars} chars):**\n")
        out.append("```\n" + (excerpt_a or "_MISSING PAGE_") + "\n```\n")
        out.append(f"**{label_b} source-summary body (first {max_body_chars} chars):**\n")
        out.append("```\n" + (excerpt_b or "_MISSING PAGE_") + "\n```\n")

        # Also lookup with / without .md — nashsu sometimes stores either
        keys = {srcname, srcname.removesuffix(".md")}
        def merge_lookup(rev: dict, kind: str) -> list[str]:
            merged: list[str] = []
            for k in keys:
                merged.extend(rev.get(k, {}).get(kind, []))
            return sorted(set(merged))

        con_a = merge_lookup(rev_a, "concepts")
        con_b = merge_lookup(rev_b, "concepts")
        wis_a = merge_lookup(rev_a, "wisdom")
        wis_b = merge_lookup(rev_b, "wisdom")

        out.append(f"**Concept pages attributed to this source**\n")
        out.append(f"- {label_a}: `{', '.join(con_a) if con_a else '—'}`")
        out.append(f"- {label_b}: `{', '.join(con_b) if con_b else '—'}`\n")
        out.append(f"**Wisdom pages attributed to this source**\n")
        out.append(f"- {label_a}: `{', '.join(wis_a) if wis_a else '—'}`")
        out.append(f"- {label_b}: `{', '.join(wis_b) if wis_b else '—'}`\n")

    return "\n".join(out)


def mk_report(
    vault_a: Path, vault_b: Path,
    pages_a: dict[str, list[Path]], pages_b: dict[str, list[Path]],
    shared_srcs: set[str], only_a: set[str], only_b: set[str],
    src_rows: list[dict], english_only: set[str],
    concept_jaccard_all: float, concept_jaccard_english: float,
    entity_jaccard: float,
    non_en_a: int, non_en_a_files: list[str],
    non_en_b: int, non_en_b_files: list[str],
    label_a: str = "Vault A (headless port)",
    label_b: str = "Vault B (desktop app 0.6.8)",
    concepts_a_set: set[str] | None = None,
    concepts_b_set: set[str] | None = None,
    wisdom_a: dict | None = None,
    wisdom_b: dict | None = None,
    qualitative: str = "",
    confound_mode: str = "phase-11",
) -> str:
    """Emit markdown report."""
    lines: list[str] = []
    lines.append(f"# Vault comparison report\n")
    lines.append(f"- **{label_a}**: `{vault_a}`")
    lines.append(f"- **{label_b}**: `{vault_b}`\n")

    lines.append("## Page-type distribution\n")
    lines.append(f"| type | {label_a} | {label_b} | delta | confound |")
    lines.append("|------|---------|---------|-------|----------|")
    template_dirs = {"journal", "goals", "habits", "reflections"}
    show_template_confound = confound_mode == "phase-11"
    for sub in WIKI_SUBDIRS:
        na, nb = len(pages_a[sub]), len(pages_b[sub])
        confound = "**template mismatch**" if (sub in template_dirs and show_template_confound) else ""
        lines.append(f"| `{sub}` | {na} | {nb} | {na - nb:+d} | {confound} |")
    total_a = sum(len(v) for v in pages_a.values())
    total_b = sum(len(v) for v in pages_b.values())
    lines.append(f"| **total** | **{total_a}** | **{total_b}** | **{total_a - total_b:+d}** | |")
    lines.append("")

    lines.append("## Source coverage\n")
    lines.append(f"- Shared sources (same filename in both `raw/sources/`): **{len(shared_srcs)}**")
    lines.append(f"- Only in {label_a}: **{len(only_a)}**")
    lines.append(f"- Only in {label_b}: **{len(only_b)}**")
    if only_a:
        lines.append(f"  - `{', '.join(sorted(only_a))}`")
    if only_b:
        lines.append(f"  - `{', '.join(sorted(only_b))}`")
    lines.append(f"- Of shared sources, English-only (< 2% non-ASCII): **{len(english_only)}** ({100*len(english_only)/max(len(shared_srcs),1):.0f}%)")
    lines.append("")

    lines.append("## Source-summary page comparison (clean surface — Surface A)\n")
    if src_rows:
        wa = [r["words_a"] for r in src_rows]
        wb = [r["words_b"] for r in src_rows]
        la = [r["wikilinks_a"] for r in src_rows]
        lb = [r["wikilinks_b"] for r in src_rows]
        wj = [r["wikilink_jaccard"] for r in src_rows]
        title_agree = sum(1 for r in src_rows if r["same_title"])
        tags_agree = sum(1 for r in src_rows if r["same_tags_set"])
        rel_agree = sum(1 for r in src_rows if r["same_related_set"])
        n = len(src_rows)
        lines.append("### Body richness (words per source-summary)\n")
        lines.append(f"| stat | {label_a} | {label_b} | ratio A/B |")
        lines.append("|------|---------|---------|-----------|")
        lines.append(f"| median | {statistics.median(wa):.0f} | {statistics.median(wb):.0f} | {statistics.median(wa)/max(statistics.median(wb),1):.2f} |")
        lines.append(f"| mean   | {statistics.mean(wa):.0f} | {statistics.mean(wb):.0f} | {statistics.mean(wa)/max(statistics.mean(wb),1):.2f} |")
        lines.append(f"| p90    | {sorted(wa)[int(0.9*n)-1]} | {sorted(wb)[int(0.9*n)-1]} | — |")
        lines.append("")
        lines.append("### Wikilink density (outgoing links per source-summary)\n")
        lines.append(f"| stat | {label_a} | {label_b} | ratio A/B |")
        lines.append("|------|---------|---------|-----------|")
        lines.append(f"| median | {statistics.median(la):.0f} | {statistics.median(lb):.0f} | {statistics.median(la)/max(statistics.median(lb),1):.2f} |")
        lines.append(f"| mean   | {statistics.mean(la):.1f} | {statistics.mean(lb):.1f} | {statistics.mean(la)/max(statistics.mean(lb),1):.2f} |")
        lines.append(f"| p90    | {sorted(la)[int(0.9*n)-1]} | {sorted(lb)[int(0.9*n)-1]} | — |")
        lines.append("")
        lines.append("### Per-source wikilink target overlap\n")
        lines.append(f"- Median Jaccard: **{statistics.median(wj):.2f}**")
        lines.append(f"- Mean Jaccard:   **{statistics.mean(wj):.2f}**")
        lines.append(f"- Sources with ≥ 50% overlap: **{sum(1 for x in wj if x >= 0.5)} / {n}**")
        lines.append("")
        lines.append("### Frontmatter agreement\n")
        lines.append(f"- Same `title`:   **{title_agree} / {n}** ({100*title_agree/n:.0f}%)")
        lines.append(f"- Same `tags` (set-equal):   **{tags_agree} / {n}** ({100*tags_agree/n:.0f}%)")
        lines.append(f"- Same `related` (set-equal): **{rel_agree} / {n}** ({100*rel_agree/n:.0f}%)")
        lines.append("")

    lines.append("## Concept-slug overlap (Surface A + C)\n")
    lines.append(f"- **Full concept Jaccard**: {concept_jaccard_all:.2%}")
    lines.append(f"- **Concept Jaccard on English-only sources**: {concept_jaccard_english:.2%}")
    lines.append(f"- **Entity Jaccard**: {entity_jaccard:.2%}")
    lines.append(f"- Reference nondeterminism baseline (same pipeline, two runs, historical): **~7%**")
    lines.append("")

    # Concept-slug set differences (Session-9 addition)
    if concepts_a_set is not None and concepts_b_set is not None:
        only_ca = concepts_a_set - concepts_b_set
        only_cb = concepts_b_set - concepts_a_set
        lines.append("## Concept-slug differences (not just Jaccard percent)\n")
        lines.append(f"- Concepts only in {label_a}: **{len(only_ca)}**")
        if only_ca:
            lines.append(f"  - `{', '.join(sorted(only_ca))}`")
        lines.append(f"- Concepts only in {label_b}: **{len(only_cb)}**")
        if only_cb:
            lines.append(f"  - `{', '.join(sorted(only_cb))}`")
        adjacent = find_adjacent_concept_pairs(only_ca, only_cb)
        lines.append(f"- Semantically-adjacent pairs across the two sides "
                     f"(substring or shared ≥4-char token): **{len(adjacent)}**")
        if adjacent:
            lines.append(f"  _If most of the \"only in\" concepts pair up here, the "
                         f"apparent concept-count difference is mostly re-slugging, not "
                         f"genuine consolidation._\n")
            lines.append("  | " + label_a + " | " + label_b + " | reason |")
            lines.append("  |---|---|---|")
            for sa, sb, reason in adjacent[:40]:
                lines.append(f"  | `{sa}` | `{sb}` | {reason} |")
            if len(adjacent) > 40:
                lines.append(f"  _(truncated at 40; {len(adjacent) - 40} more pairs)_")
        lines.append("")

    # Wisdom capture (Session-9 addition — ship-gate criterion)
    if wisdom_a is not None and wisdom_b is not None:
        lines.append("## Wisdom capture (ship-gate criterion: ≥5 attributed quotes per page)\n")
        lines.append(f"| stat | {label_a} | {label_b} |")
        lines.append("|------|---------|---------|")
        lines.append(f"| Wisdom pages | {wisdom_a['total_pages']} | {wisdom_b['total_pages']} |")
        lines.append(f"| Total attributed quotes | {wisdom_a['total_quotes']} | {wisdom_b['total_quotes']} |")
        lines.append(f"| Median quotes/page | {wisdom_a['median_quotes']} | {wisdom_b['median_quotes']} |")
        lines.append(f"| p90 quotes/page | {wisdom_a['p90_quotes']} | {wisdom_b['p90_quotes']} |")
        lines.append(f"| Weak pages (< 5 quotes) | {len(wisdom_a['weak_pages'])} | {len(wisdom_b['weak_pages'])} |")
        lines.append(f"| Pages with zero attribution | {len(wisdom_a['unattributed_pages'])} | {len(wisdom_b['unattributed_pages'])} |")
        lines.append("")
        if wisdom_a['weak_pages']:
            lines.append(f"- {label_a} weak pages: `{', '.join(wisdom_a['weak_pages'])}`")
        if wisdom_b['weak_pages']:
            lines.append(f"- {label_b} weak pages: `{', '.join(wisdom_b['weak_pages'])}`")
        if wisdom_a['unattributed_pages']:
            lines.append(f"- {label_a} unattributed pages: `{', '.join(wisdom_a['unattributed_pages'])}`")
        if wisdom_b['unattributed_pages']:
            lines.append(f"- {label_b} unattributed pages: `{', '.join(wisdom_b['unattributed_pages'])}`")
        lines.append("")

    # Qualitative side-by-side (Session-9 addition)
    if qualitative:
        lines.append("## Qualitative side-by-side (3 shared sources: light / medium / heavy)\n")
        lines.append(qualitative)
        lines.append("")

    # Language check — only meaningful in phase-11 mode (Session-9 applied outputLanguage fix to both)
    if confound_mode == "phase-11":
        lines.append("## Language check (Surface B — confounded)\n")
        lines.append(f"- Concept pages with > 5% non-ASCII body content — **{label_a}: {non_en_a}, {label_b}: {non_en_b}**")
        lines.append(f"- Root cause on {label_a}: headless CLI never seeds `outputLanguage: \"en\"`. Fix identified; not yet applied.")
        if non_en_a_files:
            lines.append(f"- {label_a} flagged files (first 10): `{', '.join(non_en_a_files[:10])}`")
        if non_en_b_files:
            lines.append(f"- {label_b} flagged files (first 10): `{', '.join(non_en_b_files[:10])}`")
        lines.append("")

    lines.append("## Confound ledger\n")
    if confound_mode == "session-9":
        lines.append("_Same code, same corpus, same template. Only variable: `--workers 1` vs `--workers 8`._\n")
        lines.append("| # | confound | affected surface | status |")
        lines.append("|---|---|---|---|")
        lines.append("| 1 | LLM nondeterminism (`claude -p` has no temperature/seed) | any measure of exact overlap | inherent; ~7% baseline Jaccard applies |")
        lines.append("| 2 | Warm-index effect (serial sees accumulated wiki, parallel workers don't) | concept consolidation vs fragmentation | **phenomenon under study**, not a confound |")
        lines.append("| 3 | 1 source dropped from serial vault | source coverage | flagged in coverage section; parallel is superset there |")
    else:
        lines.append("| # | confound | affected surface | status |")
        lines.append("|---|---|---|---|")
        lines.append(f"| 1 | Template mismatch (Personal Growth vs Generic) | page-type distribution — journal/goals/habits/reflections | reported above; not port bug |")
        lines.append(f"| 2 | Version drift (0.6.9 vendored vs 0.6.8 desktop) | unknown per-release prompt diffs | small; treat as noise floor |")
        lines.append(f"| 3 | outputLanguage drift on headless | non-English concept pages on {label_a} | fix identified in `mikai-cli/ingest.ts`; not applied yet |")
        lines.append(f"| 4 | `.obsidian/` empty seeding on headless | future vault initialization only | **fixed 2026-08-18** in `init-project.ts` |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault-a", type=Path, required=True)
    ap.add_argument("--vault-b", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--json", type=Path, help="also emit machine-readable JSON")
    ap.add_argument("--label-a", default="Vault A (headless port)",
                    help="Human-readable label for vault A in the report")
    ap.add_argument("--label-b", default="Vault B (desktop app 0.6.8)",
                    help="Human-readable label for vault B in the report")
    ap.add_argument("--obsidian-copy", action="append", type=Path, default=[],
                    help="Also drop the report at <VAULT>/wiki/comparisons/<REPORT_NAME>. "
                         "Pass once per vault; wikilinks in the report resolve within that vault.")
    ap.add_argument("--confounds", choices=["phase-11", "session-9"], default="phase-11",
                    help="Which confound ledger to emit. phase-11 = headless vs desktop, "
                         "session-9 = serial vs parallel with same code path.")
    args = ap.parse_args()

    if not args.vault_a.is_dir():
        print(f"vault-a not a dir: {args.vault_a}", file=sys.stderr)
        sys.exit(2)
    if not args.vault_b.is_dir():
        print(f"vault-b not a dir: {args.vault_b}", file=sys.stderr)
        sys.exit(2)

    pages_a = enumerate_pages(args.vault_a)
    pages_b = enumerate_pages(args.vault_b)

    raw_a = raw_source_names(args.vault_a)
    raw_b = raw_source_names(args.vault_b)
    shared = raw_a & raw_b
    only_a = raw_a - raw_b
    only_b = raw_b - raw_a

    src_rows, english_only = compare_shared_sources(args.vault_a, args.vault_b, shared)

    concepts_a = concept_slugs(pages_a["concepts"])
    concepts_b = concept_slugs(pages_b["concepts"])
    entities_a = concept_slugs(pages_a["entities"])
    entities_b = concept_slugs(pages_b["entities"])

    concept_j_all = jaccard(concepts_a, concepts_b)
    entity_j = jaccard(entities_a, entities_b)

    concepts_en_a = concepts_from_english_sources(args.vault_a, english_only)
    concepts_en_b = concepts_from_english_sources(args.vault_b, english_only)
    concept_j_en = jaccard(concepts_en_a, concepts_en_b)

    non_en_a, non_en_a_files = count_non_english_concepts(args.vault_a)
    non_en_b, non_en_b_files = count_non_english_concepts(args.vault_b)

    wisdom_a = wisdom_stats(args.vault_a)
    wisdom_b = wisdom_stats(args.vault_b)
    qualitative = qualitative_sample(
        args.vault_a, args.vault_b, shared,
        args.label_a, args.label_b,
    )

    report = mk_report(
        args.vault_a, args.vault_b,
        pages_a, pages_b,
        shared, only_a, only_b,
        src_rows, english_only,
        concept_j_all, concept_j_en, entity_j,
        non_en_a, non_en_a_files,
        non_en_b, non_en_b_files,
        label_a=args.label_a, label_b=args.label_b,
        concepts_a_set=concepts_a, concepts_b_set=concepts_b,
        wisdom_a=wisdom_a, wisdom_b=wisdom_b,
        qualitative=qualitative,
        confound_mode=args.confounds,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(f"[compare] wrote {args.report} ({len(report)} bytes)")

    for vpath in args.obsidian_copy:
        if not vpath.is_dir():
            print(f"[compare] skip obsidian-copy — not a dir: {vpath}", file=sys.stderr)
            continue
        dest = vpath / "wiki" / "comparisons" / args.report.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(report, encoding="utf-8")
        print(f"[compare] obsidian-copy → {dest}")

    if args.json:
        only_ca = sorted(concepts_a - concepts_b)
        only_cb = sorted(concepts_b - concepts_a)
        adjacent = find_adjacent_concept_pairs(set(only_ca), set(only_cb))
        args.json.write_text(json.dumps({
            "vault_a": str(args.vault_a),
            "vault_b": str(args.vault_b),
            "label_a": args.label_a,
            "label_b": args.label_b,
            "page_counts_a": {k: len(v) for k, v in pages_a.items()},
            "page_counts_b": {k: len(v) for k, v in pages_b.items()},
            "shared_sources": len(shared),
            "only_in_a_sources": sorted(only_a),
            "only_in_b_sources": sorted(only_b),
            "english_only_sources": len(english_only),
            "concept_jaccard_all": concept_j_all,
            "concept_jaccard_english": concept_j_en,
            "entity_jaccard": entity_j,
            "concepts_only_in_a": only_ca,
            "concepts_only_in_b": only_cb,
            "adjacent_concept_pairs": [
                {"a": a, "b": b, "reason": r} for a, b, r in adjacent
            ],
            "non_english_concepts_a": non_en_a,
            "non_english_concepts_b": non_en_b,
            "wisdom_a": wisdom_a,
            "wisdom_b": wisdom_b,
            "source_summary_rows": src_rows,
        }, indent=2), encoding="utf-8")
        print(f"[compare] wrote {args.json}")


if __name__ == "__main__":
    main()
