"""Daily heartbeat over the cron fleet — reads progress.jsonl, asserts
each scheduled job has left a ledger trace within its expected window,
alerts via ntfy on gaps.

Every scheduled job that calls `ledger.run(mode=..., did=...)` leaves a
row in ~/.mikai/brain/state/progress.jsonl. This check is the meta-cron:
if a job dies silently (unloaded plist, crashed runner, expired cookie),
the silence itself becomes a notification.

Rules:
- Expected cadences are hardcoded (v0). A mode is STALE when its newest
  ledger row is older than max_gap_hours — or when it has no row at all.
- Modes whose launchd plist is not currently loaded are SKIPPED (a job
  deliberately unloaded should not page).
- Stale jobs -> one ntfy POST: title "MIKAI health: N job(s) silent",
  body listing each stale job + last-seen timestamp.
- All green -> silent (no ntfy), but the check self-logs a
  ledger.run(mode="health-check", did="all green") row so the heartbeat
  itself has a trace (and can be watched by a future meta-meta check).

CLI:
    python3 -m infra.mikai_brain.health [--dry-run] [--verbose]

--dry-run prints what would be reported without dispatching ntfy or
writing the ledger. Scheduled via com.mikai.health-check (08:15 daily,
15 min after the Sunday consolidate window). See docs/HEALTH_CHECK.md.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib import request as urlreq

from . import ledger

NTFY_BASE_URL = os.environ.get("MIKAI_NTFY_BASE", "https://ntfy.sh")
NTFY_TOPIC = os.environ.get("MIKAI_NTFY_TOPIC", "")


# ── Expected cadences (v0: hardcoded — promote to a config file only if
#    this table starts churning) ──────────────────────────────────────────


@dataclass(frozen=True)
class Cadence:
    mode: str            # `mode` value the job writes via ledger.run()
    max_gap_hours: float  # alert when the newest row is older than this
    plist_label: str     # launchd label; unloaded label -> mode skipped


EXPECTED: list[Cadence] = [
    Cadence("consolidate",    200, "com.mikai.consolidate"),     # Sun 08:00 weekly
    Cadence("dream-weekly",   200, "com.mikai.dream-weekly"),    # Sun 06:00 weekly
    Cadence("dream-monthly",  800, "com.mikai.dream-monthly"),   # 1st 05:00 monthly
    Cadence("dream-nightly",   28, "com.mikai.dream-nightly"),   # 03:00 daily
    Cadence("ingestion",       12, "com.mikai.ingestion"),       # continuous daemon
    Cadence("claude-threads",  30, "com.mikai.claude-threads"),  # daily pass
]


# ── Pieces (pure where possible, for tests) ──────────────────────────────


@dataclass
class Finding:
    mode: str
    max_gap_hours: float
    last_ts: str | None   # newest ledger row ts, or None = never seen
    age_hours: float | None

    def line(self) -> str:
        if self.last_ts is None:
            return (f"- {self.mode}: never seen in progress.jsonl "
                    f"(max {self.max_gap_hours:g}h)")
        return (f"- {self.mode}: last seen {self.last_ts} "
                f"({self.age_hours:.1f}h ago; max {self.max_gap_hours:g}h)")


def loaded_labels() -> set[str]:
    """Labels currently known to launchd (`launchctl list`, 3rd column)."""
    try:
        out = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=15,
        ).stdout
    except Exception as exc:
        print(f"WARN: launchctl list failed ({exc}) — assuming all loaded",
              file=sys.stderr)
        return {c.plist_label for c in EXPECTED}
    labels: set[str] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            labels.add(parts[2])
    return labels


def latest_by_mode(rows: list[dict]) -> dict[str, str]:
    """mode -> newest ts. Rows arrive in append order; keep the max ts to
    tolerate any historical reordering."""
    out: dict[str, str] = {}
    for r in rows:
        mode, ts = r.get("mode"), r.get("ts")
        if not mode or not ts:
            continue
        if mode not in out or ts > out[mode]:
            out[mode] = ts
    return out


def _age_hours(ts: str, now: datetime) -> float | None:
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 3600.0


def check(
    rows: list[dict],
    loaded: set[str],
    now: datetime | None = None,
) -> tuple[list[Finding], list[Finding], list[str]]:
    """Pure core: -> (stale, green, skipped_modes)."""
    now = now or datetime.now(timezone.utc)
    latest = latest_by_mode(rows)
    stale: list[Finding] = []
    green: list[Finding] = []
    skipped: list[str] = []
    for c in EXPECTED:
        if c.plist_label not in loaded:
            skipped.append(c.mode)
            continue
        ts = latest.get(c.mode)
        age = _age_hours(ts, now) if ts else None
        f = Finding(c.mode, c.max_gap_hours, ts, age)
        # never-seen, unparseable ts, or over the window -> stale
        if ts is None or age is None or age > c.max_gap_hours:
            stale.append(f)
        else:
            green.append(f)
    return stale, green, skipped


def dispatch_ntfy(title: str, body: str) -> tuple[bool, str]:
    """Existing dispatch pattern (sumimasen_watcher): direct POST to
    https://ntfy.sh/<MIKAI_NTFY_TOPIC>."""
    if not NTFY_TOPIC:
        return False, "MIKAI_NTFY_TOPIC not set"
    url = f"{NTFY_BASE_URL}/{NTFY_TOPIC}"
    try:
        title.encode("ascii")
        title_h = title
    except UnicodeEncodeError:
        title_h = title.encode("ascii", errors="replace").decode("ascii")
    req = urlreq.Request(
        url,
        data=body.encode("utf-8"),
        headers={"Title": title_h, "Priority": "high", "Tags": "warning,mikai,health"},
        method="POST",
    )
    try:
        with urlreq.urlopen(req, timeout=10) as resp:
            return True, f"http_{resp.status}"
    except Exception as e:
        return False, f"ntfy_error: {e}"


# ── Orchestration ────────────────────────────────────────────────────────


def run_check(
    *,
    dry_run: bool = False,
    verbose: bool = False,
    now: datetime | None = None,
    loaded: set[str] | None = None,
    rows: list[dict] | None = None,
) -> int:
    rows = ledger.read_runs() if rows is None else rows
    loaded = loaded_labels() if loaded is None else loaded
    stale, green, skipped = check(rows, loaded, now=now)

    if verbose or dry_run:
        for f in green:
            print(f"[ok]      {f.line()[2:]}")
        for m in skipped:
            print(f"[skipped] {m}: plist not loaded")

    if not stale:
        msg = (f"all green ({len(green)} job(s) checked"
               + (f", {len(skipped)} skipped: {', '.join(skipped)}" if skipped else "")
               + ")")
        print(f"[health] {msg}")
        if dry_run:
            print("[health] dry-run: no ledger write")
        else:
            ledger.run(mode="health-check", did=msg)
        return 0

    title = f"MIKAI health: {len(stale)} job(s) silent"
    body = "\n".join(f.line() for f in stale)
    print(f"[health] {title}")
    print(body)
    if dry_run:
        print("[health] dry-run: no ntfy dispatch, no ledger write")
        return 0
    ok, status = dispatch_ntfy(title, body)
    print(f"[health] ntfy dispatch: {status}")
    ledger.run(
        mode="health-check",
        did=f"{len(stale)} stale: " + ", ".join(f.mode for f in stale),
        extra={"ntfy": status},
    )
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="health",
        description="Cron-fleet heartbeat over progress.jsonl.",
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be reported; no ntfy, no ledger write")
    ap.add_argument("--verbose", action="store_true",
                    help="also print green/skipped modes")
    args = ap.parse_args()
    sys.exit(run_check(dry_run=args.dry_run, verbose=args.verbose))


if __name__ == "__main__":
    main()
