"""R5 dedup report — deterministic body-Jaccard candidate finder.

Report-only. No writes to the vault. Implements Fable's 3 modifications:
  1. Retire-not-delete — emits merge PROPOSALS with `retire_to:` targets,
     never mutates pages.
  2. Confidence-banded — HIGH (Jaccard >= 0.5) / MEDIUM (0.3-0.5) /
     LOW (0.15-0.3). Low is flagged manual-review-only.
  3. Feed bodies, not descriptions — parses `## Overview` + `## Notes`
     from each concept page and Jaccards on that.

Candidate pairs are formed by cheap similarity heuristics on slug:
  (a) shared root token (kebab-split, intersection >= 1 non-stop token)
  (b) edit-distance <= 3 on the slug
  (c) shared substring of length >= 8 chars

Stubs (body < 200 chars) are skipped on both sides.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path


_STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
    "vs", "is", "as", "at", "by", "how", "why", "what", "when", "from",
    "it", "its", "this", "that", "be", "not", "no",
}

_HEADING_RX = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_FRONTMATTER_RX = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_page(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _FRONTMATTER_RX.match(text)
    body = text[m.end():] if m else text
    sections = split_sections(body)
    overview = sections.get("overview", "")
    notes = sections.get("notes", "")
    focus_body = f"{overview}\n\n{notes}".strip() or body.strip()
    return {
        "slug": path.stem,
        "path": str(path),
        "body": focus_body,
        "body_len": len(focus_body),
    }


def split_sections(body: str) -> dict:
    positions = [(m.start(), m.group(1).strip().lower()) for m in _HEADING_RX.finditer(body)]
    out: dict = {}
    for i, (start, name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(body)
        seg = body[start:end]
        seg = _HEADING_RX.sub("", seg, count=1).strip()
        out[name] = seg
    return out


_TOKEN_RX = re.compile(r"[A-Za-z][A-Za-z0-9']+")


def tokenize(text: str) -> set:
    return {t.lower() for t in _TOKEN_RX.findall(text) if len(t) >= 3 and t.lower() not in _STOP}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def slug_tokens(slug: str) -> set:
    return {t for t in slug.split("-") if len(t) >= 3 and t not in _STOP}


def edit_distance(a: str, b: str, cap: int = 4) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def shared_substring(a: str, b: str, min_len: int = 8) -> bool:
    if len(a) < min_len or len(b) < min_len:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    for start in range(len(short) - min_len + 1):
        if short[start:start + min_len] in long_:
            return True
    return False


def form_candidate_pairs(pages: list) -> set:
    by_root = defaultdict(list)
    for p in pages:
        for tok in slug_tokens(p["slug"]):
            by_root[tok].append(p["slug"])
    pairs: set = set()
    for slugs in by_root.values():
        if len(slugs) < 2:
            continue
        for a, b in combinations(sorted(set(slugs)), 2):
            pairs.add((a, b))
    slug_list = [p["slug"] for p in pages]
    for a, b in combinations(sorted(slug_list), 2):
        if (a, b) in pairs:
            continue
        if edit_distance(a, b) <= 3 or shared_substring(a, b):
            pairs.add((a, b))
    return pairs


def band(j: float) -> str | None:
    if j >= 0.5:
        return "HIGH"
    if j >= 0.3:
        return "MEDIUM"
    if j >= 0.15:
        return "LOW"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--concepts-dir",
        default=str(Path.home() / ".mikai" / "wiki-mikai-parallel-test" / "wiki" / "concepts"),
    )
    ap.add_argument(
        "--report",
        default="eval/reports/dedup_r5_2026-08-31.md",
    )
    ap.add_argument(
        "--json",
        default="eval/reports/dedup_r5_2026-08-31.json",
    )
    ap.add_argument("--stub-threshold", type=int, default=200)
    args = ap.parse_args()

    concepts_dir = Path(args.concepts_dir)
    md_paths = sorted(concepts_dir.glob("*.md"))
    pages_raw = [parse_page(p) for p in md_paths]
    pages = [p for p in pages_raw if p["body_len"] >= args.stub_threshold]
    stubs = len(pages_raw) - len(pages)

    for p in pages:
        p["tokens"] = tokenize(p["body"])
    by_slug = {p["slug"]: p for p in pages}

    pairs = form_candidate_pairs(pages)

    banded = {"HIGH": [], "MEDIUM": [], "LOW": []}
    for a_slug, b_slug in sorted(pairs):
        a, b = by_slug.get(a_slug), by_slug.get(b_slug)
        if not a or not b:
            continue
        j = jaccard(a["tokens"], b["tokens"])
        b_ = band(j)
        if not b_:
            continue
        banded[b_].append({
            "a": a_slug,
            "b": b_slug,
            "jaccard": round(j, 3),
            "body_a": a["body_len"],
            "body_b": b["body_len"],
            "retire_to": a_slug if a["body_len"] >= b["body_len"] else b_slug,
            "retire": b_slug if a["body_len"] >= b["body_len"] else a_slug,
        })
    for k in banded:
        banded[k].sort(key=lambda r: r["jaccard"], reverse=True)

    payload = {
        "vault": str(concepts_dir),
        "total_pages": len(pages_raw),
        "analyzed_pages": len(pages),
        "stubs_skipped": stubs,
        "candidate_pairs": len(pairs),
        "banded_counts": {k: len(v) for k, v in banded.items()},
        "pairs": banded,
    }

    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(payload, indent=2))

    lines = []
    lines.append("# R5 Dedup Report — deterministic body-Jaccard\n")
    lines.append(f"- **Vault**: `{concepts_dir}`")
    lines.append(f"- **Concept pages total**: {len(pages_raw)}")
    lines.append(f"- **Pages analyzed (body ≥ {args.stub_threshold} chars)**: {len(pages)}")
    lines.append(f"- **Stubs skipped**: {stubs}")
    lines.append(f"- **Candidate pairs considered**: {len(pairs)}")
    lines.append("")
    lines.append("## Fable's 3 modifications")
    lines.append("1. **Retire-not-delete** — every proposal names `retire` (smaller/weaker) + `retire_to` (larger/canonical). Nothing mutated.")
    lines.append("2. **Confidence-banded** — HIGH ≥ 0.5, MEDIUM 0.3–0.5, LOW 0.15–0.3.")
    lines.append("3. **Feed bodies** — Jaccards computed on `## Overview` + `## Notes` tokens (min length 3, stopwords removed).")
    lines.append("")
    lines.append(f"## Band counts")
    for k in ("HIGH", "MEDIUM", "LOW"):
        lines.append(f"- **{k}**: {len(banded[k])}")
    lines.append("")

    for k in ("HIGH", "MEDIUM", "LOW"):
        rows = banded[k]
        lines.append(f"## {k} ({len(rows)} pairs)")
        if k == "LOW":
            lines.append("> ⚠️ Manual review only — deterministic signal at this band is weak.")
        lines.append("")
        if not rows:
            lines.append("_none_\n")
            continue
        lines.append("| retire | retire_to | jaccard | body_lens |")
        lines.append("|---|---|---:|---|")
        show = rows if k != "LOW" else rows[:40]
        for r in show:
            lines.append(f"| `{r['retire']}` | `{r['retire_to']}` | {r['jaccard']:.3f} | {r['body_a']} / {r['body_b']} |")
        if k == "LOW" and len(rows) > 40:
            lines.append(f"\n_… {len(rows) - 40} more LOW pairs elided; see JSON._")
        lines.append("")

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(lines))
    print(f"wrote {args.report}")
    print(f"wrote {args.json}")
    print(f"HIGH={len(banded['HIGH'])} MEDIUM={len(banded['MEDIUM'])} LOW={len(banded['LOW'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
