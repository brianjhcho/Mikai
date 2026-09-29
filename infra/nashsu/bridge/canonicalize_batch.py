#!/usr/bin/env python3
"""
canonicalize_batch.py — dry-run canonicalization across a random sample
of existing knowledge pages. Measures how many merges the tier-1/2/3
pipeline would find on the current vault WITHOUT applying any changes.

Comparable baseline: R5 pairwise dedup at cosine ≥0.88 found 7 real
merges from 33 HIGH candidate pairs. This measures the same yield question
from the canonicalization angle (per-page 3-tier resolution).
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

CANONICALIZE_SCRIPT = Path(__file__).parent / "canonicalize.py"


def find_knowledge_pages(project: Path) -> list[Path]:
    pages: list[Path] = []
    for kind in ("concepts", "entities", "wisdom"):
        d = project / "wiki" / kind
        if not d.is_dir():
            continue
        for p in d.glob("*.md"):
            try:
                head = p.read_text(encoding="utf-8", errors="replace")[:400]
            except OSError:
                continue
            if "retired_to:" in head:
                continue
            pages.append(p)
    return pages


def run_canonicalize_dry(project: Path, page: Path) -> dict:
    proc = subprocess.run(
        [
            "python3",
            str(CANONICALIZE_SCRIPT),
            "--project", str(project),
            "--page", str(page.relative_to(project)),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        return {"error": f"exit {proc.returncode}: {proc.stderr[:200]}"}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return {"error": f"parse: {e}", "raw": proc.stdout[:200]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--n", type=int, default=20, help="sample size")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="/tmp/canonicalize-batch-report.json")
    args = ap.parse_args()

    project = Path(args.project).expanduser().resolve()
    pages = find_knowledge_pages(project)
    random.seed(args.seed)
    sample = random.sample(pages, min(args.n, len(pages)))

    print(f"[batch] sampling {len(sample)} of {len(pages)} pages", flush=True)
    verdicts: list[dict] = []
    tally = {"mint": 0, "merge": 0, "rename": 0, "error": 0,
             "tier1": 0, "tier2": 0, "tier3": 0}

    for i, p in enumerate(sample, 1):
        result = run_canonicalize_dry(project, p)
        result["_page"] = str(p.relative_to(project))
        verdicts.append(result)
        if "error" in result:
            tally["error"] += 1
            print(f"[{i}/{len(sample)}] {p.name} ERR: {result['error'][:80]}", flush=True)
            continue
        applied = result.get("applied", "")
        action = applied.split(":", 1)[-1] if ":" in applied else applied
        if action in tally:
            tally[action] += 1
        tier = result.get("tier", 0)
        tally[f"tier{tier}"] = tally.get(f"tier{tier}", 0) + 1
        summary = result.get("verdict", {}).get("action", "?")
        canonical = result.get("verdict", {}).get("canonical", "-")
        print(f"[{i}/{len(sample)}] {p.name} → {summary} (tier={tier}, canonical={canonical})",
              flush=True)

    Path(args.out).write_text(
        json.dumps({"tally": tally, "verdicts": verdicts}, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n[batch] tally: {json.dumps(tally, sort_keys=True)}", flush=True)
    print(f"[batch] full report: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
