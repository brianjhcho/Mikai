"""State-writing helpers — append-only.

progress.jsonl → one row per run (interactive session, standup, triage,
                 consolidate, or headless heartbeat). One JSON object
                 per line; append via O_APPEND (atomic at the OS level
                 for line-sized writes). Grows freely; compaction, if
                 ever needed, is a separate rewrite pass.
delivery_events.jsonl → one row per surfaced item, with the user's
                        eventual response (acted / dismissed / ignored /
                        deferred). This is the Sumimasen ledger.

Both files are the single source of truth between sessions. Nothing
else may serve as cross-session memory of what happened.

Legacy note: progress.json (single JSON array) is auto-migrated to
progress.jsonl on first append. The old file is renamed to
progress.migrated-<ts>.json and left in place — safe to delete after
review.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import PROGRESS_LOG, LEGACY_PROGRESS_LOG, DELIVERY_LOG, STATE_DIR


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


def _migrate_legacy_if_needed() -> None:
    """One-shot: on first use, if the legacy progress.json array exists and
    progress.jsonl does not, convert. Old file is renamed, never deleted."""
    if not LEGACY_PROGRESS_LOG.exists() or PROGRESS_LOG.exists():
        return
    try:
        rows = json.loads(LEGACY_PROGRESS_LOG.read_text())
    except json.JSONDecodeError:
        # Corrupt legacy file — quarantine and start fresh.
        backup = LEGACY_PROGRESS_LOG.with_name(
            f"progress.corrupt-{_now().replace(':', '')}.json"
        )
        LEGACY_PROGRESS_LOG.rename(backup)
        print(f"WARN: legacy progress.json unparseable — moved to {backup.name}, starting fresh")
        return
    if not isinstance(rows, list):
        rows = []
    with PROGRESS_LOG.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    migrated = LEGACY_PROGRESS_LOG.with_name(
        f"progress.migrated-{_now().replace(':', '').replace('-', '')[:15]}.json"
    )
    LEGACY_PROGRESS_LOG.rename(migrated)
    print(f"migrated {len(rows)} run(s) from progress.json → progress.jsonl "
          f"(legacy file renamed to {migrated.name})")


def append_run(entry: RunEntry) -> None:
    """Append one JSONL row. O_APPEND is atomic at the OS level for writes
    ≤ PIPE_BUF (typically 4KB–64KB); a run row is ~200 bytes, well under."""
    _ensure_state_dir()
    _migrate_legacy_if_needed()
    line = json.dumps(asdict(entry))
    if len(line) + 1 > 4096:
        # Extreme safety: if a row is ever bigger than the small-write atomic
        # ceiling, fall through to a lock-free append anyway — the OS still
        # guarantees atomicity per single write() call on most FSes, but this
        # is where you'd add a lockfile if concurrent writes become a real
        # concern. Flag it so we notice if this ever fires.
        print(f"WARN: progress.jsonl row is {len(line)}b — over the 4KB atomic-write ceiling")
    with PROGRESS_LOG.open("a") as f:
        f.write(line + "\n")


def read_runs() -> list[dict]:
    """Parse the JSONL log, tolerating a partial trailing line from a crash
    mid-append (skips malformed rows silently — recovery-on-load)."""
    _migrate_legacy_if_needed()
    if not PROGRESS_LOG.exists():
        return []
    rows: list[dict] = []
    for line in PROGRESS_LOG.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


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
