"""Surfacing CLI.

  python -m infra.surfacing.main              # rebuild surfacing.html
  python -m infra.surfacing.main --dry-run    # print summary, write nothing
  python -m infra.surfacing.main --output P   # override the HTML path
"""

from __future__ import annotations

import argparse
from pathlib import Path

from infra.mikai_brain import BRAIN_ROOT

from .collect import collect_view
from .render import render_html

SURFACING_HTML = BRAIN_ROOT / "surfacing.html"


def _summarize(view: dict) -> str:
    att = view["attention"]
    head = att["head"]
    lines = [f"surfacing: as of {view['generated_at_human']}"]
    if head:
        lines.append(
            f"  head: {head['slug']} [{head['state']}] "
            f"score={int(head['score'])} — {head['reason']}"
        )
    else:
        lines.append("  head: quiet — nothing owed")
    lines.append(f"  scored>0: {len(att['scored'])} thread(s)")
    lines.append(f"  deliveries (last 10): {len(view['deliveries'])}")
    lines.append(f"  transitions (last 10): {len(view['transitions'])}")
    ticks = view["engine_ticks"] or view["standup_ticks"]
    lines.append(f"  engine ticks: {len(ticks)} shown")
    lines.append(f"  quiet threads: {len(att['quiet'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="surfacing",
                                 description="L4-surfacing text-first view")
    ap.add_argument("--dry-run", action="store_true",
                    help="collect + summarize, write nothing")
    ap.add_argument("--output", type=Path, default=None,
                    help="override the surfacing.html output path")
    args = ap.parse_args(argv)

    view = collect_view()
    print(_summarize(view))
    if args.dry_run:
        print("dry-run: nothing written")
        return 0
    target = args.output or SURFACING_HTML
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(view), encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
