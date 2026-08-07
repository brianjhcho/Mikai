"""Inspector CLI.

  python -m infra.inspector.main                # build tensions.json + inspector.html
  python -m infra.inspector.main --refresh-only # write tensions.json only, no HTML
  python -m infra.inspector.main --dry-run      # summarize, write nothing
  python -m infra.inspector.main --output PATH  # override the HTML path
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .build import build_state, summarize, write_outputs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="inspector",
                                 description="MIKAI Inspector builder")
    ap.add_argument("--dry-run", action="store_true",
                    help="collect + summarize, write nothing")
    ap.add_argument("--refresh-only", action="store_true",
                    help="write only state/tensions.json, skip the HTML")
    ap.add_argument("--output", type=Path, default=None,
                    help="override the inspector.html output path")
    args = ap.parse_args(argv)

    state = build_state()
    print(summarize(state))
    if args.dry_run:
        print("dry-run: nothing written")
        return 0
    for p in write_outputs(state, html_path=args.output,
                           refresh_only=args.refresh_only):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
