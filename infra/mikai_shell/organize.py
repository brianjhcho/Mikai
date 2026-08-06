"""The 'organize my desktop' scenario — the first shell command.

End-to-end flow:
  1. Prompt user for what they want (or take prompt as arg)
  2. Scan target root (default: ~/Desktop)
  3. Ask the LLM planner for a taxonomy + move manifest
  4. Show inline approval dialog (batch summary)
  5. If approved, execute moves via shutil with rollback log
  6. Show confirmation with undo hint

Every mutation is journalled; nothing is destroyed; the batch_id is
printed so `mikai_shell undo <batch_id>` works. The `--dry-run` flag
runs the whole pipeline without touching disk — useful for verifying
LLM output quality before the first real run.

WRITES BACK (SPEC §5.1 — an action that leaves no trace never happened):
- Files under the chosen root — the moves themselves (via rollback.py).
- `~/.mikai/rollback.log` — one JSONL row per executed move (undo journal).
- `~/.mikai/brain/state/progress.jsonl` — one `mode="shell"` entry per run
  that moved at least one file. Failed/cancelled/dry runs log nothing.
- Thread log lines under `~/.mikai/brain/threads/` when a move's rationale
  or destination clearly implicates a specific thread (conservative
  heuristic match on slug / title / distinctive slug component).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dialogs import (  # noqa: E402
    prompt_text, confirm_three, message, notify,
)
from planner import plan, validate  # noqa: E402
from rollback import start_batch, execute_move, finish_batch  # noqa: E402

DEFAULT_ROOT = str(Path.home() / "Desktop")
DEFAULT_PROMPT = "Organize this folder in a way that matches how I actually think about my life and work."


def _preview_text(plan_obj) -> str:
    """Human-readable summary of a plan for the approval dialog."""
    lines = [
        f"MIKAI proposes reorganizing {plan_obj.scope}:",
        "",
        plan_obj.rationale.strip() if plan_obj.rationale else "(no overall rationale returned)",
        "",
        f"Proposed folders ({len(plan_obj.taxonomy)}):",
    ]
    for t in plan_obj.taxonomy[:10]:
        lines.append(f"  • {Path(t).name}")
    if len(plan_obj.taxonomy) > 10:
        lines.append(f"  … and {len(plan_obj.taxonomy) - 10} more")

    lines.extend([
        "",
        f"Proposed moves: {len(plan_obj.moves)}",
        f"Files left in place: {len(plan_obj.unclassified)}",
    ])

    if plan_obj.moves:
        lines.append("")
        lines.append("First few moves:")
        for m in plan_obj.moves[:5]:
            src_name = Path(m.src).name
            dst_folder = Path(m.dst).parent.name
            lines.append(f"  • {src_name}  →  {dst_folder}/")
        if len(plan_obj.moves) > 5:
            lines.append(f"  … and {len(plan_obj.moves) - 5} more")

    return "\n".join(lines)


def _print_plan_text(plan_obj) -> None:
    """Full text dump for --dry-run mode (no dialog, just stdout)."""
    print(f"\n=== PLAN for {plan_obj.scope} ===\n")
    print(plan_obj.rationale)
    print("\n--- taxonomy ---")
    for t in plan_obj.taxonomy:
        print(f"  {t}")
    print(f"\n--- moves ({len(plan_obj.moves)}) ---")
    for m in plan_obj.moves:
        print(f"  {Path(m.src).name}")
        print(f"    → {m.dst}")
        print(f"    reason: {m.rationale}")
    print(f"\n--- unclassified ({len(plan_obj.unclassified)}) ---")
    for u in plan_obj.unclassified[:20]:
        print(f"  {Path(u).name}")
    if len(plan_obj.unclassified) > 20:
        print(f"  ... and {len(plan_obj.unclassified) - 20} more")


def _write_back(root: str, batch, moved: list, fail_count: int) -> None:
    """Record what this run did into the brain substrate (SPEC §5.1).

    Never raises — a failed write-back must not break a completed organize
    run (the rollback journal is intact either way). Thread appends are
    conservative: a move's rationale/destination must clearly name a
    thread; no match → no append."""
    try:
        from infra.mikai_brain import ledger
        from infra.mikai_brain import threads as thread_mod

        dest_counts: dict[str, int] = {}
        for m in moved:
            name = Path(m.dst).parent.name
            dest_counts[name] = dest_counts.get(name, 0) + 1
        top = ", ".join(
            f"{name}×{n}" for name, n in
            sorted(dest_counts.items(), key=lambda kv: -kv[1])[:4]
        )
        did = f"Moved {len(moved)} file(s) under {root}"
        if fail_count:
            did += f" ({fail_count} failed)"
        if top:
            did += f": {top}"

        all_threads = thread_mod.load_all()
        per_thread: dict[str, int] = {}
        by_slug: dict[str, object] = {}
        for m in moved:
            text = f"{m.rationale} {Path(m.dst).parent.name}"
            for th in thread_mod.match_threads_in_text(text, all_threads):
                per_thread[th.slug] = per_thread.get(th.slug, 0) + 1
                by_slug[th.slug] = th

        ledger.run(mode="shell", did=did,
                   threads_touched=sorted(per_thread),
                   extra={"batch_id": batch.batch_id})

        for slug in sorted(by_slug):
            thread_mod.append_log_line(
                by_slug[slug],
                f"[shell:organize] Moved {per_thread[slug]} file(s) under "
                f"{root} (batch {batch.batch_id})",
            )
    except Exception as exc:  # noqa: BLE001 — write-back must never kill the run
        print(f"WARN: brain write-back failed: {exc}", file=sys.stderr)


def run(
    root: str = DEFAULT_ROOT,
    prompt: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    interactive: bool = True,
) -> int:
    """Run one end-to-end organize invocation.

    - `interactive=True` shows native dialogs for input + approval
    - `interactive=False` runs headless (needs `prompt` and `yes` to proceed)
    - `dry_run=True` computes the plan but never touches disk
    - `yes=True` skips the approval dialog (careful — mutates without confirm)
    """
    # 1. Get the user prompt
    if prompt is None:
        if interactive:
            prompt = prompt_text(
                "What do you want MIKAI to do?",
                default=DEFAULT_PROMPT,
                ok_label="Plan",
            )
            if prompt is None:
                print("cancelled")
                return 0
        else:
            prompt = DEFAULT_PROMPT

    # 2 + 3. Scan and plan
    print(f"planning against {root}...")
    plan_obj = plan(root, prompt)

    issues = validate(plan_obj)
    critical = [i for i in issues if i.startswith("CRITICAL")]
    if critical:
        msg = "MIKAI's plan has safety issues:\n\n" + "\n".join(critical[:5])
        print(msg, file=sys.stderr)
        if interactive:
            message(msg, title="MIKAI — plan rejected")
        return 2

    if dry_run:
        _print_plan_text(plan_obj)
        print("\n[dry-run] no files moved.")
        return 0

    # 4. Approval
    if not yes:
        preview = _preview_text(plan_obj)
        if interactive:
            choice = confirm_three(
                preview,
                approve_label="Approve all",
                review_label="Cancel",
                reject_label="Cancel",
            )
            if choice != "Approve all":
                print("cancelled at approval")
                return 0
        else:
            print(preview)
            print("\nHeadless mode: pass --yes to execute without dialog.")
            return 0

    # 5. Execute
    print(f"executing {len(plan_obj.moves)} moves...")
    batch = start_batch(prompt=prompt, scope=root)
    ok_count = 0
    fail_count = 0
    moved: list = []
    try:
        for m in plan_obj.moves:
            try:
                execute_move(batch, m.src, m.dst, rationale=m.rationale)
                ok_count += 1
                moved.append(m)
            except OSError as exc:
                print(f"  ✗ {m.src}: {exc}", file=sys.stderr)
                fail_count += 1
        finish_batch(batch)
    except Exception as exc:
        finish_batch(batch, aborted=True, reason=str(exc))
        raise

    # 6. Write-back: the brain must know this happened (SPEC §5.1).
    #    Only successful mutation gets a ledger row — zero moves, no row.
    if ok_count:
        _write_back(root, batch, moved, fail_count)

    # 7. Confirmation
    summary = (
        f"MIKAI moved {ok_count} file{'s' if ok_count != 1 else ''}"
        + (f" ({fail_count} failed)" if fail_count else "")
        + f".\n\nUndo: mikai_shell undo {batch.batch_id}"
    )
    print(summary)
    if interactive:
        notify(title="MIKAI — organized", body=f"{ok_count} moved · undo {batch.batch_id}")
    return 0 if fail_count == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="MIKAI Shell — organize a folder")
    ap.add_argument("--root", default=DEFAULT_ROOT, help=f"folder to organize (default: {DEFAULT_ROOT})")
    ap.add_argument("--prompt", default=None, help="user prompt (skips input dialog when set)")
    ap.add_argument("--dry-run", action="store_true", help="plan without touching disk")
    ap.add_argument("--yes", action="store_true", help="skip approval dialog (dangerous)")
    ap.add_argument("--headless", action="store_true", help="no dialogs — for testing")
    args = ap.parse_args()

    return run(
        root=args.root,
        prompt=args.prompt,
        dry_run=args.dry_run,
        yes=args.yes,
        interactive=not args.headless,
    )


if __name__ == "__main__":
    sys.exit(main())
