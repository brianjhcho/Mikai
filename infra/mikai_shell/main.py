"""CLI entry point for the MIKAI Shell.

Subcommands:
  organize    Analyze and reorganize a folder
  undo        Reverse a batch of moves by batch_id
  batches     List recent batches from the rollback log

Invoked as:  python3 -m infra.mikai_shell <subcommand> [...]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import organize as organize_mod  # noqa: E402
from rollback import read_batches, undo_batch, latest_batch  # noqa: E402


def cmd_organize(args: argparse.Namespace) -> int:
    return organize_mod.run(
        root=args.root,
        prompt=args.prompt,
        dry_run=args.dry_run,
        yes=args.yes,
        interactive=not args.headless,
    )


def cmd_undo(args: argparse.Namespace) -> int:
    if args.batch_id == "latest":
        b = latest_batch()
        if b is None:
            print("no batches in rollback log")
            return 1
        batch_id = b.batch_id
    else:
        batch_id = args.batch_id
    undone, errors = undo_batch(batch_id)
    print(f"undone: {undone} moves")
    for e in errors:
        print(f"  ! {e}", file=sys.stderr)
    return 0 if not errors else 1


def cmd_batches(args: argparse.Namespace) -> int:
    batches = read_batches()
    if not batches:
        print("no batches yet")
        return 0
    for b in batches[-args.limit:]:
        status = "aborted" if b.aborted else ("done" if b.finished_at else "in-flight")
        print(f"{b.batch_id}  {b.started_at}  [{status:^9}]  "
              f"{len(b.records)} moves  scope={b.scope}")
        if args.verbose:
            print(f"    prompt: {b.prompt}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="mikai_shell", description="MIKAI reactive shell")
    subs = ap.add_subparsers(dest="cmd", required=True)

    ap_org = subs.add_parser("organize", help="Analyze and reorganize a folder")
    ap_org.add_argument("--root", default=organize_mod.DEFAULT_ROOT)
    ap_org.add_argument("--prompt", default=None)
    ap_org.add_argument("--dry-run", action="store_true")
    ap_org.add_argument("--yes", action="store_true")
    ap_org.add_argument("--headless", action="store_true")
    ap_org.set_defaults(func=cmd_organize)

    ap_undo = subs.add_parser("undo", help="Reverse a batch of moves")
    ap_undo.add_argument("batch_id", help="batch id from `batches` (or 'latest')")
    ap_undo.set_defaults(func=cmd_undo)

    ap_b = subs.add_parser("batches", help="List recent shell batches")
    ap_b.add_argument("--limit", type=int, default=20)
    ap_b.add_argument("--verbose", "-v", action="store_true")
    ap_b.set_defaults(func=cmd_batches)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
