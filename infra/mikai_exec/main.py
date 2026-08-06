"""CLI for the executor layer.

Usage (both forms accepted; Makefile uses the flag form):

    python -m infra.mikai_exec SLUG TYPE [--dry-run]
    python -m infra.mikai_exec --slug=SLUG --type=TYPE [--dry-run]
"""

from __future__ import annotations

import argparse
import sys

from .core import ACTION_POLICIES, execute


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m infra.mikai_exec",
        description="Act on a surfaced thread through an approved, scoped channel.")
    parser.add_argument("slug_pos", nargs="?", metavar="SLUG",
                        help="thread slug (filename stem under brain/threads/)")
    parser.add_argument("type_pos", nargs="?", metavar="TYPE",
                        help=f"action type: {', '.join(sorted(ACTION_POLICIES))}, browse")
    parser.add_argument("--slug", dest="slug_flag", default=None)
    parser.add_argument("--type", dest="type_flag", default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="show the proposal; no dialog, no execution, no writes")
    args = parser.parse_args(argv)

    slug = args.slug_flag or args.slug_pos
    action_type = args.type_flag or args.type_pos
    if not slug or not action_type:
        parser.error("need a thread SLUG and action TYPE "
                     "(positional or --slug/--type)")

    try:
        return execute(slug, action_type, dry_run=args.dry_run)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        print(f"mikai_exec: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
