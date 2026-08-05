"""Cockpit CLI.

  python -m infra.cockpit.main                # build json + html
  python -m infra.cockpit.main --dry-run      # print summary, write nothing
  python -m infra.cockpit.main --refresh-only # write dashboard.json only
  python -m infra.cockpit.main --output PATH  # override the HTML path
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .build import build_dashboard, summarize, write_outputs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cockpit", description="Second Brain cockpit builder")
    ap.add_argument("--dry-run", action="store_true",
                    help="collect + summarize, write nothing")
    ap.add_argument("--output", type=Path, default=None,
                    help="override the cockpit.html output path")
    ap.add_argument("--refresh-only", action="store_true",
                    help="write only state/dashboard.json, skip the HTML")
    args = ap.parse_args(argv)

    dashboard = build_dashboard()
    print(summarize(dashboard))
    if args.dry_run:
        print("dry-run: nothing written")
        return 0
    for p in write_outputs(dashboard, html_path=args.output,
                           refresh_only=args.refresh_only):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
