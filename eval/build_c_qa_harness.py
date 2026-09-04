"""Build C QA harness — Surface C (mikai_ask against the nashsu wiki substrate).

Runs the same 8 questions used in eval/r2_qa_harness.py through
`mikai_ask.core.ask_from_nashsu_wiki` for both the parallel and serial
vaults. Emits a 3-lane side-by-side report (parallel, serial, Claude.ai
MIKA TECH placeholder). Also drops copies into each vault's
wiki/comparisons/ so the report renders in Obsidian with clickable
wikilinks.

Surface C is the MIKAI-product surface: retrieval + composition happen in
mikai_ask, then mikai_llm.chat() calls Claude via subscription-safe path.
No MCP, no --tools override, no API keys — same policy as ask() in prod.

Usage:
    python eval/build_c_qa_harness.py

Output:
    eval/reports/build_c_qa_<DATE>.md
    ~/.mikai/wiki-mikai-parallel-test/wiki/comparisons/build_c_qa_<DATE>.md
    ~/.mikai/wiki-mikai-new/wiki/comparisons/build_c_qa_<DATE>.md
"""
from __future__ import annotations

import shutil
import sys
import time
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from infra.mikai_ask.core import ask_from_nashsu_wiki  # noqa: E402

QUESTIONS = [
    "What is the Sumimasen intervention pattern and where does it apply?",
    "What did Brian decide about mem.ai vs Obsidian for MIKAI's substrate?",
    "How does the L4 task-state machine classify threads (exploring / decided / acting / stalled)?",
    "What are the memory-architecture generations (pre-LLM through RAG through memory products) and where does MIKAI sit in that progression?",
    "What is the noonchi concept and how does it differ from a standard notification system?",
    "Which neural network architectures beyond LLMs might MIKAI use for graph inference?",
    "What are Peter Thiel's monopoly mechanisms and how do they apply to MIKAI's positioning?",
    "What's the difference between agent memory (persistent) and context management (per-session)?",
]

VAULTS = [
    ("parallel", Path.home() / ".mikai" / "wiki-mikai-parallel-test"),
    ("serial",   Path.home() / ".mikai" / "wiki-mikai-new"),
]

TODAY = date.today().isoformat()
REPORT_NAME = f"build_c_qa_{TODAY}.md"
REPORT = _REPO / "eval" / "reports" / REPORT_NAME


def _ask(vault: Path, q: str, timeout_s: int = 300) -> tuple[str, float, bool]:
    """Returns (answer_text, elapsed_seconds, ok)."""
    t0 = time.time()
    try:
        # ask_from_nashsu_wiki delegates to mikai_llm.chat with a 300s
        # provider-level timeout; we still wrap in try/except so one bad
        # call doesn't kill the harness.
        ans = ask_from_nashsu_wiki(q, vault)
        return (ans.strip() or "_(empty response)_", time.time() - t0, True)
    except Exception as exc:  # noqa: BLE001 — capture for report
        return (f"_ERROR: {type(exc).__name__}: {exc}_", time.time() - t0, False)


def main() -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# Build C QA — Surface C (mikai_ask against nashsu wiki substrate)\n")
    lines.append(f"- **Date**: {TODAY}")
    lines.append(f"- **Lane A**: `ask_from_nashsu_wiki(q, ~/.mikai/wiki-mikai-parallel-test)`")
    lines.append(f"- **Lane B**: `ask_from_nashsu_wiki(q, ~/.mikai/wiki-mikai-new)`")
    lines.append(f"- **Lane C**: paste Claude.ai MIKA TECH project answers manually into the placeholder cells")
    lines.append(f"- **Retrieval**: token-overlap search over `wiki/**/*.md`, wikilink expansion, top-8 hits + up to 3 expansions, full body cap 4KB per hit, prompt cap {150_000}ch")
    lines.append(f"- **LLM**: `mikai_llm.chat(prompt, tier=\"interactive\")` → Claude via `claude -p` (subscription-safe)")
    lines.append("")

    total_calls = 0
    total_ok = 0
    total_err = 0
    t_start = time.time()

    for i, q in enumerate(QUESTIONS, 1):
        lines.append(f"## Q{i}. {q}\n")
        print(f"[Q{i}/{len(QUESTIONS)}] {q}", file=sys.stderr)

        per_lane: dict[str, tuple[str, float, bool]] = {}
        for label, vpath in VAULTS:
            print(f"  → lane={label}", file=sys.stderr)
            per_lane[label] = _ask(vpath, q)
            total_calls += 1
            if per_lane[label][2]:
                total_ok += 1
            else:
                total_err += 1
            ans, elapsed, ok = per_lane[label]
            status = "OK" if ok else "ERR"
            print(f"    {status} {elapsed:.1f}s ({len(ans)}ch)", file=sys.stderr)

        for label, _vpath in VAULTS:
            ans, elapsed, ok = per_lane[label]
            tag = "OK" if ok else "ERR"
            lines.append(f"### Lane {'A' if label == 'parallel' else 'B'} — {label}  _({tag}, {elapsed:.1f}s, {len(ans)}ch)_\n")
            lines.append(ans)
            lines.append("")

        lines.append(f"### Lane C — Claude.ai MIKA TECH\n")
        lines.append("_(paste answer here)_\n")
        lines.append("---")
        lines.append("")

    wall = time.time() - t_start
    summary = (f"\n---\n\n## Harness summary\n\n"
               f"- **Calls**: {total_calls} ({total_ok} OK, {total_err} ERR)\n"
               f"- **Wall clock**: {wall:.1f}s\n"
               f"- **Avg per call**: {wall / max(total_calls, 1):.1f}s\n")
    lines.append(summary)

    text = "\n".join(lines)
    REPORT.write_text(text, encoding="utf-8")
    print(f"\n[harness] wrote {REPORT} ({len(text)} bytes)", file=sys.stderr)

    # Copy into each vault so Obsidian can view with clickable wikilinks
    for _label, vpath in VAULTS:
        dest = vpath / "wiki" / "comparisons" / REPORT_NAME
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy(REPORT, dest)
            print(f"[harness] obsidian-copy → {dest}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"[harness] WARN could not write {dest}: {exc}", file=sys.stderr)

    print(f"\n[harness] summary: {total_ok}/{total_calls} OK, {wall:.1f}s wall", file=sys.stderr)


if __name__ == "__main__":
    main()
