"""State-writing helpers — append-only.

progress.json  → one row per run (interactive session, standup, triage,
                 consolidate, or headless heartbeat).
delivery_events.jsonl → one row per surfaced item, with the user's
                        eventual response (acted / dismissed / ignored /
                        deferred). This is the Sumimasen ledger.

Both files are the single source of truth between sessions. Nothing
else may serve as cross-session memory of what happened.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import PROGRESS_LOG, DELIVERY_LOG, STATE_DIR


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


# ── progress.json (run log) ──────────────────────────────────────────────


@dataclass
class RunEntry:
    ts: str
    mode: str                       # interactive | standup | triage | consolidate | heartbeat
    did: str                        # one-line human-readable summary
    threads_touched: list[str] = field(default_factory=list)
    surfaced: int = 0
    acted: int = 0
    dismissed: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def append_run(entry: RunEntry) -> None:
    _ensure_state_dir()
    rows = read_runs()
    rows.append(asdict(entry))
    PROGRESS_LOG.write_text(json.dumps(rows, indent=2) + "\n")


def read_runs() -> list[dict]:
    if not PROGRESS_LOG.exists():
        return []
    try:
        return json.loads(PROGRESS_LOG.read_text())
    except json.JSONDecodeError:
        return []


def run(mode: str, did: str, **kw: Any) -> RunEntry:
    """Shorthand for building + appending a run entry in one call."""
    entry = RunEntry(ts=_now(), mode=mode, did=did, **kw)
    append_run(entry)
    return entry


# ── delivery_events.jsonl (Sumimasen ledger) ─────────────────────────────


@dataclass
class DeliveryEvent:
    ts: str
    thread: str
    kind: str                       # stall | overdue | transition | insight
    response: str = "pending"       # pending | acted | dismissed | ignored | deferred
    note: str = ""


def surface(thread: str, kind: str, note: str = "") -> DeliveryEvent:
    _ensure_state_dir()
    ev = DeliveryEvent(ts=_now(), thread=thread, kind=kind, response="pending", note=note)
    with DELIVERY_LOG.open("a") as f:
        f.write(json.dumps(asdict(ev)) + "\n")
    return ev


def read_events() -> list[DeliveryEvent]:
    if not DELIVERY_LOG.exists():
        return []
    out: list[DeliveryEvent] = []
    for line in DELIVERY_LOG.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        out.append(DeliveryEvent(
            ts=row.get("ts", ""),
            thread=row.get("thread", ""),
            kind=row.get("kind", ""),
            response=row.get("response", "pending"),
            note=row.get("note", ""),
        ))
    return out


def dismiss_rate(days: int = 7) -> float:
    """Fraction of recent surfaced items with response=='dismissed'.
    Excludes pending. Returns 0.0 with no events."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    events = read_events()
    considered: list[DeliveryEvent] = []
    for ev in events:
        try:
            ts = datetime.fromisoformat(ev.ts)
        except ValueError:
            continue
        if ts >= cutoff and ev.response != "pending":
            considered.append(ev)
    if not considered:
        return 0.0
    dismissed = sum(1 for ev in considered if ev.response == "dismissed")
    return dismissed / len(considered)
