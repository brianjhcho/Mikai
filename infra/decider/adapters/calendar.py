"""
Calendar adapter — reads ~/Library/Calendars/Calendar.sqlitedb directly.

Primary path is SQLite (works because Python already has Full Disk Access).
Falls back to icalbuddy if SQLite read fails, then osascript as a last resort.

iCloud / Google / Exchange — Calendar.app aggregates all of them into the
same database, so this adapter picks up everything regardless of source.

Requires Calendar sync enabled in System Settings → Apple ID → iCloud →
Apps Using iCloud → Calendars (or via Google account in Internet Accounts).

Cocoa epoch: dates are stored as seconds since 2001-01-01 00:00:00 UTC.
Add 978307200 to convert to Unix epoch.
"""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

CALENDAR_DB = Path.home() / "Library" / "Calendars" / "Calendar.sqlitedb"
COCOA_EPOCH_OFFSET = 978307200

# entity_type in CalendarItem: 1 = Reminder, 2 = Event. We want events only.
ENTITY_TYPE_EVENT = 2


def _try_sqlite(hours: int = 72, limit: int = 50) -> list[dict] | None:
    """Primary: read CalendarItem table directly. Fast, no permissions hassle."""
    if not CALENDAR_DB.exists():
        return None

    now_apple = time.time() - COCOA_EPOCH_OFFSET
    future_apple = now_apple + hours * 3600

    try:
        conn = sqlite3.connect(f"file:{CALENDAR_DB}?mode=ro&immutable=1", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT
                ci.summary,
                ci.start_date,
                ci.end_date,
                ci.all_day,
                ci.has_attendees,
                c.title AS calendar_name
            FROM CalendarItem ci
            LEFT JOIN Calendar c ON ci.calendar_id = c.ROWID
            WHERE ci.start_date > ?
              AND ci.start_date < ?
              AND ci.summary IS NOT NULL
              AND COALESCE(ci.junk_status, 0) = 0
              AND COALESCE(ci.hidden, 0) = 0
              AND ci.entity_type = ?
            ORDER BY ci.start_date ASC
            LIMIT ?
            """,
            (now_apple, future_apple, ENTITY_TYPE_EVENT, limit),
        )
        rows = cur.fetchall()
        conn.close()
    except sqlite3.OperationalError:
        return None

    events = []
    for r in rows:
        try:
            start_unix = float(r["start_date"]) + COCOA_EPOCH_OFFSET
            start_str = datetime.fromtimestamp(start_unix).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            start_str = "?"

        end_str = ""
        if r["end_date"] is not None:
            try:
                end_unix = float(r["end_date"]) + COCOA_EPOCH_OFFSET
                end_str = datetime.fromtimestamp(end_unix).strftime("%Y-%m-%d %H:%M")
            except (TypeError, ValueError):
                pass

        events.append({
            "source": "calendar",
            "title": r["summary"],
            "when": start_str,
            "end_time": end_str,
            "all_day": bool(r["all_day"]),
            "has_attendees": bool(r["has_attendees"]),
            "calendar_name": r["calendar_name"] or "?",
            "is_action_required": True,
        })
    return events


def _try_icalbuddy(hours: int = 72) -> list[dict] | None:
    """Fallback 1: icalbuddy CLI. Requires Calendar permission grant on first run."""
    if not shutil.which("icalbuddy"):
        return None

    days = max(1, (hours + 23) // 24)
    try:
        result = subprocess.run(
            ["icalbuddy",
             "-nc",
             "-eep", "url,notes,location,attendees,uid",
             "-iep", "title,datetime",
             "-b", "* ",
             f"eventsToday+{days}"],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode != 0 or "No calendars" in result.stdout or "No calendars" in result.stderr:
        return None

    events = []
    current: dict = {}
    for line in result.stdout.split("\n"):
        line = line.strip()
        if line.startswith("* "):
            if current.get("title"):
                events.append(current)
            current = {
                "source": "calendar",
                "title": line[2:].strip(),
                "is_action_required": True,
            }
        elif line and current:
            current.setdefault("when", line)
    if current.get("title"):
        events.append(current)
    return events if events else None


def _try_osascript(hours: int = 72) -> list[dict]:
    """Fallback 2: AppleScript. Slow; only used if everything else fails."""
    script = f'''
    set output to ""
    set targetEnd to (current date) + ({hours} * hours)
    tell application "Calendar"
        try
            repeat with cal in calendars
                try
                    set theseEvents to (every event of cal whose start date > (current date) and start date < targetEnd)
                    repeat with e in theseEvents
                        set output to output & (summary of e) & "||" & ((start date of e) as string) & "||" & (title of cal as string) & linefeed
                    end repeat
                end try
            end repeat
        end try
    end tell
    return output
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return [{"source": "calendar", "error": "all paths failed (sqlite, icalbuddy, osascript)"}]

    if result.returncode != 0:
        return [{"source": "calendar", "error": f"AppleScript failed: {(result.stderr or '').strip()[:200]}"}]

    events = []
    for line in result.stdout.strip().split("\n"):
        parts = line.split("||")
        if len(parts) >= 3:
            events.append({
                "source": "calendar",
                "title": parts[0].strip(),
                "when": parts[1].strip(),
                "calendar_name": parts[2].strip(),
                "is_action_required": True,
            })
    return events


def upcoming_events(hours: int = 72) -> list[dict]:
    """Return events in the next N hours. Tries SQLite first, falls back."""
    via_sqlite = _try_sqlite(hours)
    if via_sqlite is not None:
        return via_sqlite

    via_icalbuddy = _try_icalbuddy(hours)
    if via_icalbuddy is not None:
        return via_icalbuddy

    return _try_osascript(hours)


if __name__ == "__main__":
    import json
    import sys
    events = upcoming_events(hours=72)
    print(json.dumps(events[:15], indent=2, default=str))
    print(f"\nTotal upcoming events (next 72h): {len(events)}", file=sys.stderr)
