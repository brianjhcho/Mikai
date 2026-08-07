"""Cockpit snapshot tracking — server-side thread-state diff.

Every full build writes a compact per-thread snapshot to
`~/.mikai/brain/state/cockpit_last_snapshot.json`. On the next build,
we load the prior snapshot, compare it against the fresh one, and emit
up to 3 transitions as the "delta strip" (item 2 of the ranked build
list in `docs/COCKPIT_CONTENT_STRATEGY.md`).

Not a live event log — one row per thread, overwritten each build.
When nothing changed the delta strip stays empty and is hidden.
"""

from __future__ import annotations

import json
from pathlib import Path


def snapshot_from_departments(departments: list[dict]) -> dict:
    """Compact per-thread state for the diff. One row per slug."""
    snap: dict[str, dict] = {}
    for d in departments:
        for t in d["threads"]:
            snap[t["slug"]] = {
                "title": t.get("title", t["slug"]),
                "state": t.get("state", ""),
                "overdue": bool(t.get("overdue")),
                "overdue_days": int(t.get("overdue_days") or 0),
                "state_since": t.get("state_since", ""),
                "next_step_due": t.get("next_step_due", ""),
            }
    return snap


def load_prior(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_snapshot(path: Path, snap: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def compute_deltas(prior: dict | None, current: dict, cap: int = 3) -> list[dict]:
    """Return up to `cap` deltas since the prior snapshot.

    Kinds (in preference order): state-transition > new > became-overdue.
    A repeated overdue is not a delta on its own — only the transition
    from not-overdue → overdue registers. If prior is None (first-ever
    build), no deltas are emitted.
    """
    if not prior:
        return []

    diffs: list[dict] = []
    for slug, now in current.items():
        was = prior.get(slug)
        if was is None:
            diffs.append({
                "slug": slug, "title": now["title"], "kind": "new",
                "desc": f"new ({now['state']})",
            })
            continue

        if now["state"] != was.get("state"):
            diffs.append({
                "slug": slug, "title": now["title"], "kind": "transition",
                "from": was.get("state", ""), "to": now["state"],
                "desc": f'{was.get("state", "")} → {now["state"]}',
            })
            continue

        if now["overdue"] and not was.get("overdue"):
            od = now["overdue_days"]
            diffs.append({
                "slug": slug, "title": now["title"], "kind": "overdue",
                "desc": (f"overdue+{od}d" if od > 0 else "overdue"),
            })

    # transition first, then new, then overdue — most informative first
    _order = {"transition": 0, "new": 1, "overdue": 2}
    diffs.sort(key=lambda d: _order.get(d["kind"], 9))
    return diffs[:cap]
