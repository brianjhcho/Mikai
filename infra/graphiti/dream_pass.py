"""dream_pass — semantic consolidation for the concept-page layer.

Implements Phase A + B + C of the DREAM_PASS.md spec:
- Phase A (Orient): compute fingerprints for all concept pages (no LLM)
- Phase B (Gather Signal): pairwise Jaccard prefilter → LLM verification of candidates
- Phase C (Consolidate): write merge proposals to concept-inbox.md

Never mutates concept pages directly. Never auto-merges. Proposals only.
Human approves via inbox → dream_apply.py executes approved merges.

Reference: docs/DREAM_PASS.md (design), docs/LINT_PASS.md (structural pass — runs before this).
"""

from __future__ import annotations

import json
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/Users/briancho/.superset/worktrees/MIKAI/pear-seashore")
sys.path.insert(0, str(REPO))

from infra.mikai_llm import chat  # noqa: E402

WIKI_DIR = Path.home() / ".mikai" / "wiki"
CONCEPTS_DIR = WIKI_DIR / "concepts"
INBOX = WIKI_DIR / "concept-inbox.md"
LOG_MD = WIKI_DIR / "log.md"
DREAM_LOG = Path("/tmp/mikai_dream.log")

# Phase B thresholds (see DREAM_PASS.md § "Threshold-banded action")
JACCARD_PREFILTER = 0.30         # below this → skip (too noisy to LLM-verify)
JACCARD_HIGH_CONFIDENCE = 0.45   # above this → strong merge candidate
LLM_CONFIDENCE_MIN = 0.7         # LLM must be this confident to propose merge
MAX_PAIRS_TO_VERIFY = 100        # cap LLM verify calls per run — safety limit
N_WORKERS = 8


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with DREAM_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── Phase A — Orient ──────────────────────────────────────────────────

def parse_concept_page(path: Path) -> dict | None:
    """Extract fingerprint fields for one concept page."""
    if path.stem in ("index", "log"):
        return None
    text = path.read_text(encoding="utf-8")
    fm_match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm_match:
        return None
    fm = fm_match.group(1)
    fields = {}
    for line in fm.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        fields[k.strip()] = v.strip()
    # Parse aliases (list or comma-separated)
    aliases_str = fields.get("aliases", "[]").strip("[]")
    aliases = [a.strip().strip('"').strip("'") for a in aliases_str.split(",") if a.strip()]
    # TL;DR
    tldr_match = re.search(r"##\s*TL;DR\s*\n(.+?)(?:\n\n|\n##)", text, re.DOTALL)
    tldr = " ".join(tldr_match.group(1).split())[:400] if tldr_match else ""
    # Notes (first 800 chars for fingerprint)
    notes_match = re.search(r"##\s*Notes[^\n]*\n(.+?)(?:\n##|\Z)", text, re.DOTALL)
    notes_excerpt = " ".join(notes_match.group(1).split())[:800] if notes_match else ""
    # Skip authored: hand pages entirely — dream never proposes their merger
    authored = fields.get("authored", "").strip()
    return {
        "path": path,
        "slug": path.stem,
        "title": fields.get("title", path.stem),
        "aliases": aliases,
        "salience": float(fields.get("salience", "0") or 0),
        "authored": authored,
        "tldr": tldr,
        "notes_excerpt": notes_excerpt,
        "size": path.stat().st_size,
    }


def phase_a_orient() -> list[dict]:
    """Read all concept pages, extract fingerprints. Skip index/log/hand-authored."""
    fingerprints = []
    for p in sorted(CONCEPTS_DIR.glob("*.md")):
        fp = parse_concept_page(p)
        if fp is None:
            continue
        if fp["authored"] == "hand":
            continue  # never propose merges against hand-authored anchors
        fingerprints.append(fp)
    return fingerprints


# ── Phase B — Gather Signal ────────────────────────────────────────────

def _tokens(text: str) -> set[str]:
    """Lowercase token set for Jaccard."""
    return set(re.findall(r"[a-z][a-z0-9-]{2,}", text.lower()))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def prefilter_pairs(fingerprints: list[dict]) -> list[tuple[dict, dict, float]]:
    """Pairwise Jaccard on (slug + title + aliases + tldr). Return pairs above
    JACCARD_PREFILTER threshold. Order pairs so higher-salience = 'A' side."""
    # Build token sets once
    for fp in fingerprints:
        blob = " ".join([
            fp["slug"].replace("-", " "),
            fp["title"],
            " ".join(fp["aliases"]),
            fp["tldr"],
        ])
        fp["_tokens"] = _tokens(blob)

    pairs = []
    for i in range(len(fingerprints)):
        for j in range(i + 1, len(fingerprints)):
            a, b = fingerprints[i], fingerprints[j]
            j_score = jaccard(a["_tokens"], b["_tokens"])
            if j_score >= JACCARD_PREFILTER:
                # Order: higher salience first (or bigger size if salience tied)
                if a["salience"] < b["salience"] or (
                    a["salience"] == b["salience"] and a["size"] < b["size"]
                ):
                    a, b = b, a
                pairs.append((a, b, j_score))
    pairs.sort(key=lambda p: -p[2])  # highest jaccard first
    return pairs


_LLM_PROMPT = """You are analyzing two concept pages from Brian's personal wiki.
Determine if they capture the SAME UNDERLYING CONCEPT or DIFFERENT concepts.

Same concept examples:
- "diaphragm-first" and "diaphragm-primacy" — same idea, different phrasing
- "typing-paralysis" and "mbti-analysis-paralysis" — same pattern
- "faith-and-spirituality" and "faith-and-meaning" — same domain

Different concept examples (do NOT merge):
- "consumer-groups-and-political-economics" and "sell-the-work-not-the-tool" — related career/product themes but distinct
- Two pages that touch the same subject but from opposed angles → return tension_flag=true

## Page A (canonical candidate — higher salience/size)
- Slug: {slug_a}
- Title: {title_a}
- Aliases: {aliases_a}
- TL;DR: {tldr_a}
- Notes excerpt: {notes_a}

## Page B (loser candidate)
- Slug: {slug_b}
- Title: {title_b}
- Aliases: {aliases_b}
- TL;DR: {tldr_b}
- Notes excerpt: {notes_b}

Jaccard prefilter score: {jaccard:.2f}

Return ONLY this JSON, no prose, no fences:
{{
  "same_concept": true|false,
  "confidence": 0.0-1.0,
  "why": "one-line reason",
  "tension_flag": true|false,
  "canonical_slug": "{slug_a}",
  "aliases_to_absorb": ["{slug_b}"],
  "merged_tldr": "one-paragraph merged TL;DR under 150 words if same_concept=true, else empty"
}}
"""


def llm_verify_pair(pair: tuple[dict, dict, float], i: int, total: int) -> dict:
    a, b, j = pair
    prompt = _LLM_PROMPT.format(
        slug_a=a["slug"], title_a=a["title"],
        aliases_a=", ".join(a["aliases"]) or "(none)",
        tldr_a=a["tldr"][:400] or "(no TL;DR)",
        notes_a=a["notes_excerpt"][:600] or "(no notes)",
        slug_b=b["slug"], title_b=b["title"],
        aliases_b=", ".join(b["aliases"]) or "(none)",
        tldr_b=b["tldr"][:400] or "(no TL;DR)",
        notes_b=b["notes_excerpt"][:600] or "(no notes)",
        jaccard=j,
    )
    start = time.time()
    label = f"[{i}/{total}] {a['slug']} ↔ {b['slug']} (j={j:.2f})"
    try:
        response = chat(prompt, tier="interactive", json_mode=True, timeout=120.0)
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r"^```[a-zA-Z]*\n", "", response)
            response = re.sub(r"\n```\s*$", "", response)
        parsed = json.loads(response)
        elapsed = time.time() - start
        verdict = "SAME" if parsed.get("same_concept") else "DIFF"
        if parsed.get("tension_flag"):
            verdict = "TENSION"
        _log(f"OK {label} {elapsed:.1f}s → {verdict} conf={parsed.get('confidence',0)}")
        return {"ok": True, "pair": pair, "parsed": parsed, "elapsed": elapsed}
    except Exception as e:
        elapsed = time.time() - start
        _log(f"FAIL {label} {elapsed:.1f}s: {type(e).__name__}: {str(e)[:100]}")
        return {"ok": False, "pair": pair, "error": str(e), "elapsed": elapsed}


# ── Phase C — Consolidate (proposals) ────────────────────────────────

def write_proposal(inbox_lines: list[str], result: dict) -> None:
    """Format one merge proposal as markdown for the inbox."""
    a, b, j = result["pair"]
    p = result["parsed"]
    canonical = p.get("canonical_slug", a["slug"])
    aliases = p.get("aliases_to_absorb", [b["slug"]])
    conf = p.get("confidence", 0)
    why = p.get("why", "")
    merged_tldr = p.get("merged_tldr", "")

    if p.get("tension_flag"):
        inbox_lines.append(
            f"\n### tension: [[{a['slug']}]] ↔ [[{b['slug']}]]"
            f"  (jaccard={j:.2f}, LLM-conf={conf})\n"
            f"**Verdict:** overlapping but tension present — do NOT merge.\n"
            f"**Why:** {why}\n"
            f"**Suggested action:** add cross-reference in both pages' Notes; "
            f"consider adding `## Tensions` section to each.\n"
            f"**APPROVE-tension / REJECT** (edit this line)\n"
        )
    elif p.get("same_concept") and conf >= LLM_CONFIDENCE_MIN:
        inbox_lines.append(
            f"\n### merge: [[{canonical}]] ← absorbs [[{b['slug']}]]"
            f"  (jaccard={j:.2f}, LLM-conf={conf})\n"
            f"**Why:** {why}\n"
            f"**Aliases to add to canonical:** {aliases}\n"
            f"**Proposed merged TL;DR:**\n> {merged_tldr}\n"
            f"**Citations union:** {a['size']}B + {b['size']}B → merged\n"
            f"**APPROVE / REJECT** (edit this line)\n"
        )
    # else: LLM said "different" or confidence too low — no proposal written


def phase_c_write_proposals(results: list[dict]) -> int:
    """Append merge proposals to concept-inbox.md. Return count of proposals written."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    inbox_lines = [f"\n## dream-consolidate proposals — {ts}\n"]
    before_len = len(inbox_lines)
    for r in results:
        if not r.get("ok"):
            continue
        write_proposal(inbox_lines, r)
    written = len(inbox_lines) - before_len
    if written == 0:
        _log("no proposals worth writing (all pairs were DIFF or low confidence)")
        return 0
    with INBOX.open("a", encoding="utf-8") as f:
        f.write("\n".join(inbox_lines) + "\n")
    return written


def append_delta(summary: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with LOG_MD.open("a", encoding="utf-8") as f:
        f.write(f"\n## dream_pass — {ts}\n{summary}\n")


# ── Main ──────────────────────────────────────────────────────────────

def main(dry_run: bool = False) -> None:
    DREAM_LOG.write_text("")
    _log(f"dream_pass start (dry_run={dry_run})")

    _log("phase A — Orient (fingerprinting concept pages)")
    fingerprints = phase_a_orient()
    _log(f"phase A: {len(fingerprints)} pages fingerprinted (hand-authored skipped)")

    _log("phase B — Gather Signal (jaccard prefilter + LLM verify)")
    pairs = prefilter_pairs(fingerprints)
    _log(f"prefilter: {len(pairs)} candidate pairs above jaccard {JACCARD_PREFILTER}")

    if len(pairs) > MAX_PAIRS_TO_VERIFY:
        _log(f"capping to top-{MAX_PAIRS_TO_VERIFY} pairs by jaccard score "
             f"(discarding {len(pairs) - MAX_PAIRS_TO_VERIFY} lower-score pairs)")
        pairs = pairs[:MAX_PAIRS_TO_VERIFY]

    if not pairs:
        _log("no candidate pairs — nothing to consolidate")
        append_delta("0 pairs found, 0 proposals written")
        return

    if dry_run:
        _log("[dry-run] would fire LLM verify on:")
        for a, b, j in pairs[:20]:
            _log(f"  {j:.2f}  {a['slug']}  ↔  {b['slug']}")
        return

    _log(f"firing LLM verify — parallel workers={N_WORKERS}")
    results = []
    with ThreadPoolExecutor(max_workers=N_WORKERS) as ex:
        futs = {ex.submit(llm_verify_pair, p, i + 1, len(pairs)): p
                for i, p in enumerate(pairs)}
        for fut in as_completed(futs):
            results.append(fut.result())

    ok_count = sum(1 for r in results if r.get("ok"))
    same_count = sum(1 for r in results if r.get("ok") and r["parsed"].get("same_concept"))
    tension_count = sum(1 for r in results if r.get("ok") and r["parsed"].get("tension_flag"))
    _log(f"phase B done: {ok_count}/{len(results)} LLM calls ok, "
         f"{same_count} same-concept, {tension_count} tensions")

    _log("phase C — writing proposals to concept-inbox.md")
    written = phase_c_write_proposals(results)
    _log(f"phase C: {written} proposals written")

    summary = (f"{len(fingerprints)} pages, {len(pairs)} candidate pairs, "
               f"{ok_count} verified, {same_count} same, {tension_count} tensions, "
               f"{written} proposals to inbox")
    append_delta(summary)
    _log(f"dream_pass complete: {summary}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="dream_pass")
    ap.add_argument("--dry-run", action="store_true",
                    help="show candidate pairs without firing LLM verify")
    args = ap.parse_args()
    try:
        main(dry_run=args.dry_run)
    except Exception:
        _log("FATAL:\n" + traceback.format_exc())
        sys.exit(1)
