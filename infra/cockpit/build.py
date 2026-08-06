"""Cockpit build — assemble dashboard state and write outputs.

Outputs:
  ~/.mikai/brain/state/dashboard.json   full dashboard state (T2 fetch target)
  ~/.mikai/brain/cockpit.html           standalone snapshot (T1), with the
                                        same state embedded inline

The cockpit is a portrait, not a live feed: it shows real state at
snapshot time, stamped in the footer. `python -m infra.cockpit.build`
runs a default build; the argparse CLI lives in main.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from infra.mikai_brain import BRAIN_ROOT, STATE_DIR

from . import (collect_center, collect_departments, collect_entity_edges,
               compute_attention)
from .render import render_html
from .snapshot import (compute_deltas, load_prior, save_snapshot,
                       snapshot_from_departments)

DASHBOARD_JSON = STATE_DIR / "dashboard.json"
COCKPIT_HTML = BRAIN_ROOT / "cockpit.html"
LAST_SNAPSHOT_JSON = STATE_DIR / "cockpit_last_snapshot.json"


def build_dashboard() -> dict:
    now = datetime.now(timezone.utc)
    departments = collect_departments()
    center = collect_center()

    # Attention head + salience budget (items 1 & 2 of the ranked build
    # list in docs/COCKPIT_CONTENT_STRATEGY.md). Both live on `center` per
    # the spec — the same dict already carries Surface gate status, and
    # the render layer treats center as the "what is today for" node.
    att = compute_attention(departments)
    center["attention_head"] = att["attention_head"]
    center["loud_slugs"] = att["loud_slugs"]

    # Delta strip (item 3). Diff against the last snapshot written by a
    # prior full build; if no prior snapshot exists we emit an empty list
    # and the strip stays hidden on-screen.
    current_snap = snapshot_from_departments(departments)
    prior_snap = load_prior(LAST_SNAPSHOT_JSON)
    center["delta_strip"] = compute_deltas(prior_snap, current_snap)

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "generated_at_human": now.strftime("%Y-%m-%d %H:%M UTC"),
        "departments": departments,
        "entity_edges": collect_entity_edges(departments),
        "center": center,
        # Absolute paths the static page can only reference, never write:
        # the "mark done" affordance copies a shell append targeting this
        # file; triage (or a future apply-actions) is the consumer.
        "paths": {
            "pending_actions": str(STATE_DIR / "pending_actions.jsonl"),
        },
    }


def write_outputs(dashboard: dict, html_path: Path | None = None,
                  refresh_only: bool = False) -> list[Path]:
    """Write dashboard.json (always) and cockpit.html (unless refresh_only).
    Returns the paths written.

    Full builds (not refresh_only) also rewrite the snapshot file so the
    next build's delta strip diffs from now, not from an older baseline.
    """
    written: list[Path] = []
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dashboard, ensure_ascii=False, indent=2)
    DASHBOARD_JSON.write_text(payload + "\n", encoding="utf-8")
    written.append(DASHBOARD_JSON)
    if not refresh_only:
        target = html_path or COCKPIT_HTML
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_html(dashboard), encoding="utf-8")
        written.append(target)
        # Update the snapshot after a successful HTML write so a rerun
        # after a crash still shows the same deltas.
        save_snapshot(LAST_SNAPSHOT_JSON,
                      snapshot_from_departments(dashboard["departments"]))
    return written


def summarize(dashboard: dict) -> str:
    depts = dashboard["departments"]
    n_threads = sum(len(d["threads"]) for d in depts)
    lines = [f"cockpit: {n_threads} thread(s) across {len(depts)} department(s)"]
    for d in depts:
        lines.append(f"  {d['id']:<10} {d['breakdown']}")
    c = dashboard["center"]
    lines.append(f"  gate: {c['gate_status']} · dismiss_rate(7d)="
                 f"{c['dismiss_rate']:.0%} of {c['responded']} responded")
    return "\n".join(lines)


def main() -> None:
    dashboard = build_dashboard()
    written = write_outputs(dashboard)
    print(summarize(dashboard))
    for p in written:
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
