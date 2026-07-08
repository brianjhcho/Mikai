"""
sumimasen_watcher.py — Sumimasen Phase B: catches MIKAI-created calendar
blocks 15 min before they fire and sends a rich ntfy notification with
the context bundle upfront.

Called every 5 min by com.mikai.sumimasen.plist. For each MIKAI-signature
event firing in the next SUMIMASEN_LEAD_MIN minutes that hasn't been
dispatched yet:

  1. Read title + description from Calendar.sqlitedb (aggregates iCloud +
     Google + Exchange automatically because Calendar.app does).
  2. Send ntfy notification: title = event title, body = first ~250 chars
     of description (the actionable frame), Click = Google Calendar deep-
     link back to the event so the full context bundle is one tap away.
  3. Log dispatch so we don't re-fire the same event on subsequent ticks.

MIKAI-signature detection: MIKAI-created events (via full_corpus_dream +
mikai_decide's `decision`/`capture` action_types) always have a description
starting with `Dim <N>` (dimension anchor). We match that pattern; any
event with that leading token is treated as a MIKAI block.

Dedup table lives in ~/.mikai/sumimasen.db as a new SQLite database,
keyed on (event_start_apple, event_summary) — Calendar's internal IDs
aren't stable across syncs, but the combination of exact start time and
title is reliable.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import parse as urlparse
from urllib import request as urlreq

# ── Config ────────────────────────────────────────────────────────────

CALENDAR_DB = Path.home() / "Library" / "Calendars" / "Calendar.sqlitedb"
COCOA_EPOCH_OFFSET = 978307200
ENTITY_TYPE_EVENT = 2

MIKAI_DIR = Path.home() / ".mikai"
DEDUP_DB = MIKAI_DIR / "sumimasen.db"
LOG_PATH = MIKAI_DIR / "logs" / "sumimasen.log"

NTFY_BASE_URL = os.environ.get("MIKAI_NTFY_BASE", "https://ntfy.sh")
NTFY_TOPIC = os.environ.get("MIKAI_NTFY_TOPIC", "")

# How far ahead of an event's start we fire the preparatory notification.
SUMIMASEN_LEAD_MIN = int(os.environ.get("SUMIMASEN_LEAD_MIN", "15"))
# How wide the "firing now" window is (catches events we might have missed
# on the previous tick if the runner was slow). LaunchAgent tick is 5 min,
# so a 20-min window gives 4× coverage per event.
SUMIMASEN_WINDOW_MIN = int(os.environ.get("SUMIMASEN_WINDOW_MIN", "20"))

# MIKAI signature — first line of the description on any MIKAI-created
# event starts with "Dim " (dimension anchor from DIMENSIONS.md).
MIKAI_SIGNATURE_PREFIX = "Dim "

BODY_PREVIEW_CHARS = 250   # how much of the description we put in the
                           # ntfy body (the actionable frame). The user
                           # can tap for the full description in Calendar.

# ── SQLite: dedup table ───────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS dispatched (
    fingerprint TEXT PRIMARY KEY,
    event_summary TEXT NOT NULL,
    event_start_iso TEXT NOT NULL,
    dispatched_at TEXT NOT NULL,
    ntfy_status TEXT
);
"""


def dedup_connect() -> sqlite3.Connection:
    DEDUP_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DEDUP_DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def event_fingerprint(summary: str, start_apple: float) -> str:
    """Stable per-event ID — hash of (summary + rounded-to-second start).
    Calendar sync sometimes tweaks internal ROWIDs; the (title, start_time)
    pair is stable across syncs."""
    payload = f"{summary}|{int(round(start_apple))}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def already_dispatched(conn: sqlite3.Connection, fingerprint: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM dispatched WHERE fingerprint = ?",
        (fingerprint,),
    ).fetchone()
    return row is not None


def mark_dispatched(
    conn: sqlite3.Connection,
    fingerprint: str,
    summary: str,
    start_iso: str,
    ntfy_status: str,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO dispatched "
        "(fingerprint, event_summary, event_start_iso, dispatched_at, ntfy_status) "
        "VALUES (?, ?, ?, ?, ?)",
        (fingerprint, summary, start_iso,
         datetime.now(timezone.utc).isoformat(timespec="seconds"),
         ntfy_status),
    )
    conn.commit()


# ── Calendar read ─────────────────────────────────────────────────────

def _sqlite_read_events(fire_start: float, fire_end: float) -> list[dict] | None:
    """Primary path — direct read from Calendar.sqlitedb. Requires Full Disk
    Access on the invoking Python binary. Returns None when TCC blocks the
    read (so caller falls back to osascript)."""
    if not CALENDAR_DB.exists():
        return None
    try:
        conn = sqlite3.connect(
            f"file:{CALENDAR_DB}?mode=ro&immutable=1", uri=True,
        )
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT ci.summary, ci.description, ci.start_date,
                   ci.end_date, c.title AS calendar_name
            FROM CalendarItem ci
            LEFT JOIN Calendar c ON ci.calendar_id = c.ROWID
            WHERE ci.start_date BETWEEN ? AND ?
              AND ci.summary IS NOT NULL
              AND COALESCE(ci.junk_status, 0) = 0
              AND COALESCE(ci.hidden, 0) = 0
              AND ci.entity_type = ?
            ORDER BY ci.start_date ASC
            LIMIT 100
            """,
            (fire_start, fire_end, ENTITY_TYPE_EVENT),
        ).fetchall()
        conn.close()
    except Exception as e:
        msg = str(e).lower()
        if "authoriz" in msg or "permission" in msg or "denied" in msg:
            # TCC block — caller should fall back to osascript.
            log(f"NOTE: SQLite path denied by TCC; falling back to osascript")
            return None
        log(f"ERROR: Calendar SQLite read failed: {e}")
        return None

    out: list[dict] = []
    for r in rows:
        out.append({
            "summary": r["summary"] or "",
            "description": r["description"] or "",
            "start_apple": r["start_date"] or 0,
            "calendar_name": r["calendar_name"] or "",
        })
    return out


# osascript that returns pipe-delimited event rows for events starting
# within N minutes. Fields: iso-start | summary | description (newlines
# escaped as \\n so we can round-trip through shell). This path needs
# Calendar Automation permission — macOS prompts once, then works.
OSA_SCRIPT = r"""
on run argv
    set leadEnd to (item 1 of argv) as integer
    set windowStart to (item 2 of argv) as integer
    set nowD to (current date)
    set fireStart to nowD + windowStart * minutes
    set fireEnd to nowD + leadEnd * minutes
    set output to ""
    tell application "Calendar"
        set allCals to calendars
        repeat with cal in allCals
            try
                set evts to (every event of cal whose start date is greater than fireStart and start date is less than fireEnd)
                repeat with e in evts
                    set eSummary to summary of e
                    set eDescription to ""
                    try
                        set eDescription to description of e
                    end try
                    if eDescription is missing value then set eDescription to ""
                    set eStart to start date of e
                    set eStartStr to (year of eStart as string) & "-" & (my pad(month of eStart as integer)) & "-" & (my pad(day of eStart)) & "T" & (my pad(hours of eStart)) & ":" & (my pad(minutes of eStart)) & ":00"
                    set escapedDesc to my esc(eDescription)
                    set output to output & eStartStr & "|" & eSummary & "|" & escapedDesc & linefeed
                end repeat
            end try
        end repeat
    end tell
    return output
end run

on pad(n)
    set s to (n as integer) as string
    if length of s < 2 then set s to "0" & s
    return s
end pad

on esc(s)
    set AppleScript's text item delimiters to linefeed
    set parts to text items of (s as text)
    set AppleScript's text item delimiters to "\n"
    set out to parts as text
    set AppleScript's text item delimiters to ""
    return out
end esc
"""


def _osascript_read_events(lead_min: int, window_min: int) -> list[dict]:
    """Fallback path — drive Calendar.app via osascript. Requires the
    Calendar Automation permission (macOS prompts once when a launchd
    process first runs this against Calendar)."""
    lead_end = lead_min
    window_start = lead_min - window_min  # can be negative
    try:
        result = subprocess.run(
            ["osascript", "-e", OSA_SCRIPT, "--",
             str(lead_end), str(window_start)],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        log("ERROR: osascript binary not found")
        return []
    except subprocess.TimeoutExpired:
        log("ERROR: osascript timed out after 30s")
        return []

    if result.returncode != 0:
        log(f"ERROR: osascript exit {result.returncode}: {result.stderr[:200]}")
        return []

    out: list[dict] = []
    for line in (result.stdout or "").splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        iso_start, summary, desc = parts
        desc = desc.replace("\\n", "\n").strip()
        # Convert ISO to Cocoa-epoch seconds so downstream logic matches
        # the SQLite path.
        try:
            dt = datetime.fromisoformat(iso_start).replace(tzinfo=None)
            # Treat AppleScript local time as UTC-naive; convert to
            # Cocoa epoch seconds by taking UTC timestamp diff.
            unix_ts = dt.replace(tzinfo=timezone.utc).timestamp()
            start_apple = unix_ts - COCOA_EPOCH_OFFSET
        except ValueError:
            continue
        out.append({
            "summary": summary,
            "description": desc,
            "start_apple": start_apple,
            "calendar_name": "",
        })
    return out


def upcoming_mikai_events(
    lead_min: int,
    window_min: int,
) -> list[dict]:
    """Read Calendar for events starting in the near-future window whose
    description carries the MIKAI signature. Tries SQLite (fast, no
    Automation prompt) first; falls back to osascript when TCC blocks
    the SQLite read (which is the case under launchd unless the invoking
    Python binary has Full Disk Access)."""
    now_apple = time.time() - COCOA_EPOCH_OFFSET
    fire_start = now_apple + (lead_min - window_min) * 60
    fire_end = now_apple + lead_min * 60

    raw = _sqlite_read_events(fire_start, fire_end)
    if raw is None:
        raw = _osascript_read_events(lead_min, window_min)

    out: list[dict] = []
    for r in raw:
        desc = (r.get("description") or "").strip()
        if not desc or not desc.startswith(MIKAI_SIGNATURE_PREFIX):
            continue
        start_ts = (r.get("start_apple") or 0) + COCOA_EPOCH_OFFSET
        start_iso = datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(
            timespec="minutes"
        )
        out.append({
            "summary": r.get("summary") or "(untitled event)",
            "description": desc,
            "start_apple": r.get("start_apple") or 0,
            "start_iso": start_iso,
            "calendar_name": r.get("calendar_name") or "",
        })
    return out


# ── ntfy dispatch ─────────────────────────────────────────────────────

NTFY_PRIORITY = "4"  # timeSensitive — this fires just before the block


def dispatch_ntfy(title: str, body: str, click_url: str | None) -> tuple[bool, str]:
    if not NTFY_TOPIC:
        return False, "MIKAI_NTFY_TOPIC not set"

    url = f"{NTFY_BASE_URL}/{NTFY_TOPIC}"
    try:
        title.encode("ascii")
        title_h = title
    except UnicodeEncodeError:
        title_h = title.encode("ascii", errors="replace").decode("ascii")

    headers = {
        "Title": title_h,
        "Priority": NTFY_PRIORITY,
        "Tags": "sumimasen,mikai",
    }
    if click_url:
        try:
            click_url.encode("ascii")
            headers["Click"] = click_url
        except UnicodeEncodeError:
            pass

    req = urlreq.Request(url, data=body.encode("utf-8"),
                         headers=headers, method="POST")
    try:
        with urlreq.urlopen(req, timeout=10) as resp:
            return True, f"http_{resp.status}"
    except Exception as e:
        return False, f"ntfy_error: {e}"


def calendar_deep_link(event: dict) -> str:
    """Build a Google Calendar search URL that lands on the event. Since
    we don't have event IDs (only start-time + title), the most reliable
    tap-target is a Google Calendar search for the title, opening on the
    day of the event."""
    title = event["summary"]
    return (
        "https://calendar.google.com/calendar/u/0/r/search?q="
        + urlparse.quote(title)
    )


# ── Logging ───────────────────────────────────────────────────────────

def log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    line = f"[{stamp}] {msg}\n"
    print(line, end="", file=sys.stderr)
    with LOG_PATH.open("a") as f:
        f.write(line)


# ── Main ──────────────────────────────────────────────────────────────

def build_ntfy_body(event: dict) -> str:
    """First N chars of description = actionable frame. If truncated,
    append the ellipsis marker so the user knows to tap for the full
    context bundle."""
    desc = event["description"].replace("\r\n", "\n")
    # Skip the leading "Dim ..." line — the ntfy title already covers
    # what this is about. The body should carry the actionable content.
    if "\n" in desc:
        rest = desc.split("\n", 1)[1].lstrip()
    else:
        rest = desc
    preview = rest[:BODY_PREVIEW_CHARS]
    if len(rest) > BODY_PREVIEW_CHARS:
        preview += " […tap for full context]"
    # Include how many minutes until the event fires.
    fire_at = event.get("start_iso", "")
    return f"{preview}\n\n▶ starts {fire_at[:16]}"


def process_event(conn: sqlite3.Connection, event: dict, *, dry_run: bool) -> bool:
    fp = event_fingerprint(event["summary"], event["start_apple"])
    if already_dispatched(conn, fp):
        return False

    title = f"Sumimasen · {event['summary'][:60]}"
    body = build_ntfy_body(event)
    click = calendar_deep_link(event)

    if dry_run:
        log(f"DRY-RUN would dispatch: {title}")
        log(f"  body: {body[:120]}")
        log(f"  click: {click}")
        return True

    ok, msg = dispatch_ntfy(title, body, click)
    if ok:
        mark_dispatched(conn, fp, event["summary"], event["start_iso"], msg)
        log(f"DISPATCHED · {event['summary'][:60]} · start={event['start_iso']} · {msg}")
    else:
        log(f"FAILED · {event['summary'][:60]} · {msg}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sumimasen watcher — catch MIKAI calendar blocks before they fire."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan + log candidate events; do not send ntfy.")
    parser.add_argument("--lead-min", type=int, default=SUMIMASEN_LEAD_MIN,
                        help=f"Lead time before event start (default {SUMIMASEN_LEAD_MIN}).")
    parser.add_argument("--window-min", type=int, default=SUMIMASEN_WINDOW_MIN,
                        help=f"Firing window width in minutes (default {SUMIMASEN_WINDOW_MIN}).")
    parser.add_argument("--fire-test", action="store_true",
                        help="Dispatch a synthetic test notification and exit "
                             "(bypasses Calendar + dedup). For pipeline smoke-testing.")
    args = parser.parse_args()

    if args.fire_test:
        test_event = {
            "summary": "MIKAI · Sumimasen pipeline test",
            "description": (
                "Dim 6 Health — synthetic Sumimasen test event.\n\n"
                "This is the 15-min-before-fire notification you'd get when a "
                "real MIKAI-scheduled decision block approaches on your calendar. "
                "The body carries the actionable frame; tap opens the calendar "
                "event for the full context bundle.\n\n"
                "Prior beats:\n"
                "- 2026-07-06: Sumimasen Phase A shipped (calendar block with context)\n"
                "- 2026-07-08: Phase B (watcher) synthetic test dispatched"
            ),
            "start_apple": time.time() - COCOA_EPOCH_OFFSET + 15 * 60,
            "start_iso": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "calendar_name": "TEST",
        }
        title = f"Sumimasen · {test_event['summary'][:60]}"
        body = build_ntfy_body(test_event)
        click = calendar_deep_link(test_event)
        log(f"FIRE-TEST · dispatching synthetic Sumimasen notification")
        ok, msg = dispatch_ntfy(title, body, click)
        log(f"FIRE-TEST · result: {msg}")
        return 0 if ok else 1

    events = upcoming_mikai_events(args.lead_min, args.window_min)
    if not events:
        log(f"tick · no MIKAI events firing in next {args.lead_min - args.window_min} → {args.lead_min} min")
        return 0

    log(f"tick · {len(events)} candidate MIKAI event(s) in fire window")
    conn = dedup_connect()
    dispatched = 0
    for ev in events:
        if process_event(conn, ev, dry_run=args.dry_run):
            dispatched += 1
    conn.close()
    log(f"tick done · dispatched {dispatched}/{len(events)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
