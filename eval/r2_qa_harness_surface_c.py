"""R2 QA harness — Surface C: nashsu-backend retrieval + composition.

Runs the same 8 QUESTIONS as eval/r2_qa_harness.py across the same two
vaults, but through `infra.mikai_ask.nashsu_backend`: retrieval prunes
the vault to a composed prompt, then `claude -p` answers from that
prompt (no CWD tricks, no MCP tools). Emits a side-by-side markdown
report + machine-readable JSON.

Usage:
    python eval/r2_qa_harness_surface_c.py

Outputs:
    eval/reports/R2_surface_c_2026-08-30.md
    eval/reports/R2_surface_c_2026-08-30.json
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from eval.r2_qa_harness import QUESTIONS  # noqa: E402
from infra.mikai_ask import nashsu_backend  # noqa: E402

VAULTS = [
    ("parallel", Path.home() / ".mikai" / "wiki-mikai-parallel-test"),
    ("serial",   Path.home() / ".mikai" / "wiki-mikai-new"),
]

REPORT_MD = _REPO / "eval" / "reports" / f"R2_surface_c_{date.today().isoformat()}.md"
REPORT_JSON = _REPO / "eval" / "reports" / f"R2_surface_c_{date.today().isoformat()}.json"


def _run_one(vault: Path, question: str) -> dict:
    if not (vault / "wiki").is_dir():
        return {
            "answer": f"_ERROR: vault {vault} has no wiki/ subdir._",
            "stats": {},
            "elapsed_s": 0.0,
        }
    t0 = time.time()
    answer, stats = nashsu_backend.ask(question, vault, timeout_s=600)
    return {
        "answer": answer,
        "stats": stats,
        "elapsed_s": round(time.time() - t0, 2),
    }


def main() -> None:
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    md: list[str] = []
    md.append("# R2 Surface C — nashsu-backend retrieval\n")
    md.append(f"- **Date**: {date.today()}")
    md.append(f"- **Backend**: `infra.mikai_ask.nashsu_backend` "
              "(BM25-lite → wikilink/related expand → composed prompt → "
              "`claude -p`)")
    md.append(f"- **Vaults tested**: parallel (`wiki-mikai-parallel-test`), "
              "serial (`wiki-mikai-new`)")
    md.append("- **Lane C**: paste Claude.ai MIKA TECH project answers "
              "manually into the placeholder cells")
    md.append("")

    started = time.time()
    for i, q in enumerate(QUESTIONS, 1):
        print(f"[Q{i}/{len(QUESTIONS)}] {q}", file=sys.stderr)
        md.append(f"## Q{i}. {q}\n")
        entry: dict = {"n": i, "question": q, "lanes": {}}
        for label, vpath in VAULTS:
            print(f"  → lane={label}", file=sys.stderr)
            res = _run_one(vpath, q)
            entry["lanes"][label] = res
            stats = res["stats"]
            top = ", ".join(stats.get("top_slugs", [])[:3]) or "-"
            md.append(f"### Lane A/B ({label}) — surface C\n")
            md.append(
                f"_retrieved: {stats.get('hits', 0)} hits + "
                f"{stats.get('wikilink_expansions', 0)} wikilink "
                f"+ {stats.get('related_expansions', 0)} related · "
                f"prompt={stats.get('prompt_chars', 0)}ch · "
                f"top: {top} · elapsed {res['elapsed_s']}s_\n"
            )
            md.append("```")
            md.append(res["answer"])
            md.append("```")
            md.append("")
            print(f"    ok ({res['elapsed_s']}s, "
                  f"{len(res['answer'])}ch)", file=sys.stderr)
        md.append("### Lane C (Claude.ai MIKA TECH)\n")
        md.append("_(paste answer here)_\n")
        md.append("---\n")
        results.append(entry)

    total = round(time.time() - started, 2)
    md.append(f"\n_Total wall time: {total}s_\n")

    REPORT_MD.write_text("\n".join(md), encoding="utf-8")
    REPORT_JSON.write_text(json.dumps({
        "date": date.today().isoformat(),
        "backend": "nashsu_backend",
        "total_elapsed_s": total,
        "questions": results,
    }, default=str, indent=2), encoding="utf-8")

    print(f"\n[harness] wrote {REPORT_MD}", file=sys.stderr)
    print(f"[harness] wrote {REPORT_JSON}", file=sys.stderr)
    print(f"[harness] total: {total}s", file=sys.stderr)


if __name__ == "__main__":
    main()
