"""Weekly rewriter for BRAIN.md.

Reads:
- last 7 days of progress.json entries
- current thread frontmatter (state, next_step, last_activity)
- LOG.md tail

Sends one LLM call (interactive tier) that produces a new "Current
priorities" section (≤300 words). The rest of BRAIN.md is preserved.

One LLM call per invocation. Designed to run weekly, not daily. The
"living, not loaded" contract from SPEC §3.1.
"""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import BRAIN_MD, DECISIONS_LOG, ledger
from . import threads as thread_mod


PRIORITIES_HEADER = "## Current priorities"


PROMPT_TEMPLATE = """You are MIKAI's weekly brain consolidator.

Rewrite the "Current priorities" section of Brian's BRAIN.md. Do NOT
touch the rest of BRAIN.md. Return ONLY the new "Current priorities"
section body — no header, no fences.

Constraints:
- ≤ 300 words. Under is better.
- First-person from Brian's perspective ("I'm shipping…", "I'm waiting on…").
- Concrete: name the actual threads by their titles, name concrete next
  steps or blockers. Do not summarize in generalities.
- If a thread is stalled or overdue, say so. Silence is not a virtue here.
- End with 3-4 bullet points naming the highest-signal decisions of the
  week (the D-op-XXX numbers).

--- Threads (current state) ---
{threads_block}

--- Last 7 days of activity (progress.json tail) ---
{progress_block}

--- Recent decisions (LOG.md tail) ---
{decisions_block}
"""


def _threads_block() -> str:
    lines = []
    for t in thread_mod.load_all():
        marker = {
            "stalled": "⚠",
            "acting": "→",
            "decided": "✓",
            "evaluating": "?",
            "exploring": "…",
            "completed": "◼",
        }.get(t.state, "·")
        lines.append(
            f"- {marker} {t.title}  [{t.state}, since {t.state_since or '?'}, "
            f"last activity {t.last_activity or '?'}]\n"
            f"    next: {t.next_step or '(none set)'}"
            + (f"  (due {t.next_step_due})" if t.next_step_due else "")
        )
    return "\n".join(lines) if lines else "(no threads yet)"


def _progress_block(days: int = 7) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = ledger.read_runs()
    kept: list[str] = []
    for row in rows:
        try:
            ts = datetime.fromisoformat(row.get("ts", ""))
        except ValueError:
            continue
        if ts < cutoff:
            continue
        kept.append(f"- {ts.date().isoformat()} [{row.get('mode', '?')}] {row.get('did', '')}")
    return "\n".join(kept) if kept else "(no runs in the window)"


def _decisions_block(n: int = 10) -> str:
    if not DECISIONS_LOG.exists():
        return "(no decisions logged yet)"
    text = DECISIONS_LOG.read_text()
    entries = re.findall(r"^## D-op-\d+.*$", text, flags=re.MULTILINE)
    return "\n".join(entries[-n:]) if entries else "(no D-op entries)"


def _splice_priorities(existing: str, new_body: str) -> str:
    """Replace the ## Current priorities section body. Creates the section
    if it doesn't exist (appended near the top, before the first ## after
    identity)."""
    lines = existing.splitlines()
    header_idx: int | None = None
    next_h2_idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip().lower() == PRIORITIES_HEADER.lower():
            header_idx = i
            continue
        if header_idx is not None and line.startswith("## "):
            next_h2_idx = i
            break

    if header_idx is None:
        # No section — insert after the first paragraph.
        insert_at = 0
        for i, line in enumerate(lines):
            if not line.strip() and i > 3:
                insert_at = i + 1
                break
        block = [PRIORITIES_HEADER, "", new_body.rstrip(), ""]
        return "\n".join(lines[:insert_at] + block + lines[insert_at:])

    end = next_h2_idx if next_h2_idx is not None else len(lines)
    block = [lines[header_idx], "", new_body.rstrip(), ""]
    return "\n".join(lines[:header_idx] + block + lines[end:])


def _write_diff_summary(before: str, after: str) -> str:
    """Cheap one-line summary of what changed."""
    b_lines = set(before.splitlines())
    a_lines = set(after.splitlines())
    added = len(a_lines - b_lines)
    removed = len(b_lines - a_lines)
    return f"BRAIN.md priorities rewritten (+{added} lines, -{removed} lines)"


def run(*, dry_run: bool = False, verbose: bool = True) -> int:
    from infra import mikai_llm

    if not BRAIN_MD.exists():
        print("BRAIN.md missing — nothing to consolidate. Seed it first.")
        return 2

    prompt = PROMPT_TEMPLATE.format(
        threads_block=_threads_block(),
        progress_block=_progress_block(),
        decisions_block=_decisions_block(),
    )

    if verbose:
        print(f"consolidate: routing to {mikai_llm.which('interactive')}...")

    new_body = mikai_llm.chat(prompt, tier="interactive")
    existing = BRAIN_MD.read_text()
    updated = _splice_priorities(existing, new_body)

    if dry_run:
        print("\n--- new 'Current priorities' body ---\n")
        print(new_body)
        print("\n[dry-run] BRAIN.md not written.")
        return 0

    BRAIN_MD.write_text(updated)
    summary = _write_diff_summary(existing, updated)
    ledger.run(mode="consolidate", did=summary)
    if verbose:
        print(summary)
    return 0


def _cli() -> int:
    ap = argparse.ArgumentParser(prog="mikai_brain.consolidate", description="Weekly BRAIN.md rewriter")
    ap.add_argument("--dry-run", action="store_true", help="Print the rewrite without saving")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    return run(dry_run=args.dry_run, verbose=not args.quiet)


if __name__ == "__main__":
    raise SystemExit(_cli())
