"""Cockpit — data collection for the Second Brain constellation view.

Reads the pure-file brain substrate (threads, decisions, delivery
ledger) via `infra.mikai_brain` and assembles a JSON-serializable
dashboard dict. Strictly read-only over threads/, decisions/,
entities/, inbox/; writes land only in state/ and cockpit.html
(handled by build.py).

Honors MIKAI_BRAIN_ROOT via infra.mikai_brain's path binding.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from infra.mikai_brain import DECISIONS_LOG
from infra.mikai_brain import ledger, threads

# Canonical departments. Order is render order around the constellation.
# (id, display name, tier, sub-label)
#
# Ids match thread frontmatter vocabulary (body, love, domestic, ai_work —
# see docs/ENTITY_MODEL.md); "domestic" displays as "Home". The former
# Signal/Cortex/Threshold infrastructure hubs were removed 2026-08-05:
# they held zero threads and rendered as chrome, and Threshold's content
# (gate status, dismiss rate, pending) already lives on the center
# Surface node. Re-add an infrastructure hub only when it has a real,
# always-available data source behind it.
DEPARTMENTS: list[tuple[str, str, str, str]] = [
    ("ai_work", "AI Work", "primary", "product · shipping · code · ideas"),
    ("body", "Body", "primary", "breathing · posture · movement · sleep"),
    ("domestic", "Home", "primary", "monstera · marble table · chairs · space"),
    ("love", "Love", "primary", "Germaine · ring · venue · vow"),
]

MISC = ("misc", "Misc", "misc", "unfiled · awaiting a department")

# Active-thread priority for "top next step" (highest first).
_STATE_PRIORITY = ["acting", "stalled", "decided", "evaluating", "exploring", "completed"]


def _today() -> date:
    return date.today()


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s.strip())
    except (ValueError, AttributeError):
        return None


def _days_since(s: str) -> int | None:
    d = _parse_date(s)
    return (_today() - d).days if d else None


# ── threads ──────────────────────────────────────────────────────────────


def thread_dict(t: threads.Thread, reason: str | None) -> dict:
    due = _parse_date(t.next_step_due)
    overdue = bool(due and due < _today() and t.state not in ("completed",))
    log = list(t.log_lines)
    return {
        "slug": t.slug,
        "title": t.title,
        "state": t.state if t.state in threads.STATES else "exploring",
        "department": t.department,
        "state_since": t.state_since,
        "last_activity": t.last_activity,
        "days_since": _days_since(t.last_activity),
        "next_step": t.next_step,
        "next_step_due": t.next_step_due,
        "overdue": overdue,
        "log_recent": log[-3:],
        "log_full": log,
        "last_log": log[-1] if log else "",
        "reason": reason or "",
        "entities": list(t.entities),
    }


def collect_entity_edges(departments: list[dict]) -> list[dict]:
    """Cross-thread entanglement: two threads share an edge when their
    `entities` frontmatter sets intersect. One edge per unordered pair,
    emitted with slug_a < slug_b and the shared entity names in `via`."""
    ts = sorted(
        (t for d in departments for t in d["threads"]),
        key=lambda t: t["slug"],
    )
    edges: list[dict] = []
    for i, a in enumerate(ts):
        ea = set(a["entities"])
        if not ea:
            continue
        for b in ts[i + 1:]:
            via = sorted(ea & set(b["entities"]))
            if via:
                edges.append({"a": a["slug"], "b": b["slug"], "via": via})
    return edges


def latest_note_by_thread(events: list[ledger.DeliveryEvent]) -> dict[str, str]:
    """Most recent non-empty delivery-event note per thread slug."""
    notes: dict[str, str] = {}
    for ev in events:  # file is append-only; later lines win
        if ev.note:
            notes[ev.thread] = ev.note
    return notes


# ── decisions ────────────────────────────────────────────────────────────

_DECISION_RE = re.compile(
    r"^##\s+(D-op-\d+)\s+·\s+(\d{4}-\d{2}-\d{2})\s+·\s+(.+)$", re.MULTILINE
)


def parse_decisions() -> list[dict]:
    """Split decisions/LOG.md into {id, date, summary, body} entries."""
    if not DECISIONS_LOG.exists():
        return []
    text = DECISIONS_LOG.read_text()
    matches = list(_DECISION_RE.finditer(text))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append({
            "id": m.group(1),
            "date": m.group(2),
            "summary": m.group(3).strip(),
            "body": text[m.end():end],
        })
    return out


def decisions_for_thread(slug: str, decisions: list[dict], cap: int = 4) -> list[dict]:
    """Decisions whose summary or body mentions this thread's slug,
    newest first, capped. Anytype-style linked references for the panel."""
    out: list[dict] = []
    for d in reversed(decisions):
        if slug in (d["summary"] + d["body"]):
            out.append({"id": d["id"], "date": d["date"], "summary": d["summary"]})
            if len(out) >= cap:
                break
    return out


def decision_for_department(dept_id: str, slugs: list[str], decisions: list[dict]) -> dict | None:
    """Most recent decision that mentions the department id or any of its
    thread slugs in summary or body."""
    needles = [dept_id] + slugs
    for d in reversed(decisions):
        hay = (d["summary"] + d["body"]).lower()
        if any(n and n.lower() in hay for n in needles):
            return {"id": d["id"], "date": d["date"], "summary": d["summary"]}
    return None


# ── departments ──────────────────────────────────────────────────────────


def _breakdown(counts: dict[str, int]) -> str:
    parts = [f"{n} {state}" for state in _STATE_PRIORITY if (n := counts.get(state))]
    return " · ".join(parts) if parts else "quiet — no threads"


def _top_next_step(ts: list[dict]) -> dict | None:
    active = [t for t in ts if t["state"] != "completed" and t["next_step"]]
    if not active:
        return None
    active.sort(key=lambda t: (
        not t["overdue"],
        _STATE_PRIORITY.index(t["state"]),
        -(t["days_since"] if t["days_since"] is not None else 0),
    ))
    top = active[0]
    return {"title": top["title"], "next_step": top["next_step"], "slug": top["slug"]}


def collect_departments() -> list[dict]:
    all_threads = threads.load_all()
    events = ledger.read_events()
    notes = latest_note_by_thread(events)
    decisions = parse_decisions()
    known_ids = {d[0] for d in DEPARTMENTS}

    by_dept: dict[str, list[dict]] = {d[0]: [] for d in DEPARTMENTS}
    by_dept["misc"] = []
    for t in all_threads:
        td = thread_dict(t, notes.get(t.slug))
        td["decisions"] = decisions_for_thread(t.slug, decisions)
        key = t.department if t.department in known_ids else "misc"
        by_dept[key].append(td)

    defs = list(DEPARTMENTS)
    if by_dept["misc"]:
        defs.append(MISC)

    out = []
    for dept_id, name, tier, sub in defs:
        ts = sorted(by_dept[dept_id], key=lambda t: t["slug"])
        counts: dict[str, int] = {}
        for t in ts:
            counts[t["state"]] = counts.get(t["state"], 0) + 1
        out.append({
            "id": dept_id,
            "name": name,
            "tier": tier,
            "sub": sub,
            "threads": ts,
            "counts": counts,
            "breakdown": _breakdown(counts),
            "recent_decision": decision_for_department(
                dept_id, [t["slug"] for t in ts], decisions),
            "top_next_step": _top_next_step(ts),
        })
    return out


# ── center node (Surface gate) ───────────────────────────────────────────


def collect_center() -> dict:
    events = ledger.read_events()
    pending = [e for e in events if e.response == "pending"]
    responded_7d = 0
    cutoff = datetime.now(timezone.utc).timestamp() - 7 * 86400
    for e in events:
        try:
            ts = datetime.fromisoformat(e.ts).timestamp()
        except ValueError:
            continue
        if ts >= cutoff and e.response != "pending":
            responded_7d += 1

    last = events[-1] if events else None
    last_surface = None
    if last:
        days_ago = None
        try:
            days_ago = (datetime.now(timezone.utc) - datetime.fromisoformat(last.ts)).days
        except ValueError:
            pass
        last_surface = {
            "ts": last.ts, "thread": last.thread, "kind": last.kind,
            "note": last.note, "response": last.response, "days_ago": days_ago,
        }

    if pending:
        gate = f"active: {len(pending)} pending"
    elif last_surface and last_surface["days_ago"] is not None:
        gate = f"silence held: last surface {last_surface['days_ago']}d ago"
    else:
        gate = "silence held: no surfaces recorded"

    return {
        "dismiss_rate": ledger.dismiss_rate(days=7),
        "window_days": 7,
        "responded": responded_7d,
        "pending": len(pending),
        "last_surface": last_surface,
        "gate_status": gate,
    }
