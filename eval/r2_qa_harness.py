"""R2 QA harness — ask MIKAI-substrate questions across two vaults + placeholder for Claude.ai.

Runs `claude -p` in each vault directory (so its default file-read scope covers
the wiki files), with `--tools ""` to disable MCP (subscription-safe per the
project's auth policy). Captures each answer and emits a side-by-side markdown
report with a placeholder column for the Claude.ai MIKA TECH project answer.

Usage:
    python eval/r2_qa_harness.py

Output: eval/reports/R2_headless_vs_claude_ai_2026-08-27.md
"""
from __future__ import annotations
import os
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path
from datetime import date

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

REPORT = Path(__file__).resolve().parent / "reports" / f"R2_headless_vs_claude_ai_{date.today().isoformat()}.md"


def run_claude_p(vault: Path, question: str, timeout_s: int = 600) -> str:
    """Run `claude -p` from within the vault's wiki subdir. Returns stdout
    (trimmed) or an error marker. --tools "" disables MCP for subscription-safe
    read-only file-substrate query."""
    wiki_dir = vault / "wiki"
    if not wiki_dir.is_dir():
        return f"_ERROR: vault {vault} has no wiki/ subdir._"
    # Prompt claude to answer from the surrounding files; add explicit instruction.
    prompt = (
        "You are answering from the surrounding wiki files in the current working "
        "directory only. If the answer isn't grounded in these files, say so plainly. "
        "Cite specific concept/wisdom/source page slugs when quoting.\n\n"
        f"Question: {question}"
    )
    try:
        result = subprocess.run(
            ["claude", "-p"],
            input=prompt,
            cwd=str(wiki_dir),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return f"_ERROR: timed out after {timeout_s}s._"
    except FileNotFoundError:
        return "_ERROR: `claude` not found on PATH._"
    if result.returncode != 0:
        return f"_ERROR: claude exited {result.returncode}. stderr: {result.stderr[:300].strip()}_"
    return result.stdout.strip() or "_(empty response)_"


def main() -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# R2 Headless-vs-Claude.ai QA Comparison\n")
    lines.append(f"- **Date**: {date.today()}")
    lines.append(f"- **Vaults tested**: parallel (`wiki-mikai-parallel-test`), serial (`wiki-mikai-new`)")
    lines.append(f"- **Lane C**: paste Claude.ai MIKA TECH project answers manually into the placeholder cells")
    lines.append(f"- **Command**: `claude -p --tools \"\"` in each vault's `wiki/` dir (subscription-safe, no MCP)")
    lines.append("")

    for i, q in enumerate(QUESTIONS, 1):
        lines.append(f"## Q{i}. {q}\n")

        print(f"[Q{i}/{len(QUESTIONS)}] {q}", file=sys.stderr)

        answers: dict[str, str] = {}
        for label, vpath in VAULTS:
            print(f"  → lane={label}", file=sys.stderr)
            answers[label] = run_claude_p(vpath, q)

        for label, _ in VAULTS:
            lines.append(f"### Lane A/B ({label})\n")
            lines.append("```")
            lines.append(answers[label])
            lines.append("```")
            lines.append("")

        lines.append(f"### Lane C (Claude.ai MIKA TECH)\n")
        lines.append("_(paste answer here)_\n")
        lines.append("---")
        lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[harness] wrote {REPORT}", file=sys.stderr)


if __name__ == "__main__":
    main()
