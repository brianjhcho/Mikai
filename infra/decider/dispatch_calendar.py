"""
dispatch_calendar.py — write a daily MIKAI brief into macOS Calendar.app.

The "daily brief" is FIGS' persistent surface: a calendar event written
once per day with the top-N candidates from FIGS' slate as the body.
Brian reads this when he opens Calendar (which he does daily for work
scheduling). Per `FIGS_SURFACE_DECISION.md`, this is one of the V1
shipping surfaces alongside ntfy.sh and macOS native notifications.

Implementation: AppleScript writes an event into the default calendar.

Idempotency: a brief for the same date is rewritten in-place rather than
duplicated. The event is given a known title prefix (`MIKAI brief:`) to
locate later.

Failure modes:
- AppleScript permission denied → returns False with an error message.
  Brian needs to grant Terminal/Python access to Calendar in
  System Settings → Privacy & Security → Calendars.
- Calendar.app not present (non-macOS) → returns False gracefully.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta


# Title prefix to identify the daily brief event for idempotent overwrite.
BRIEF_TITLE_PREFIX = "MIKAI brief"

# Where in the day to schedule the event. Brian sees Calendar morning;
# 7am-7:30am gives the event a visible morning slot.
BRIEF_HOUR = 7
BRIEF_DURATION_MINUTES = 30


def _build_applescript(title: str, body: str, target_date: datetime) -> str:
    """Build the AppleScript that creates (or updates) the calendar event.

    Idempotency: deletes any existing event whose summary starts with
    BRIEF_TITLE_PREFIX on the target date, then creates the new one.
    """
    # AppleScript-escape the body and title
    safe_title = title.replace('"', '\\"').replace("\n", " ")
    safe_body = body.replace('"', '\\"').replace("\n", "\\n")

    # Build target date components for AppleScript
    year = target_date.year
    month = target_date.month
    day = target_date.day

    return f'''
    tell application "Calendar"
        set targetCal to first calendar
        try
            set targetCal to calendar "Calendar"
        end try

        -- Build the start and end dates
        set startDate to (current date)
        set year of startDate to {year}
        set month of startDate to {month}
        set day of startDate to {day}
        set hours of startDate to {BRIEF_HOUR}
        set minutes of startDate to 0
        set seconds of startDate to 0
        set endDate to startDate + ({BRIEF_DURATION_MINUTES} * minutes)

        -- Idempotency: delete any existing MIKAI brief events on this date
        try
            set dayStart to startDate - (hours of startDate) * hours
            set dayEnd to dayStart + 1 * days
            set existing to (every event of targetCal whose start date ≥ dayStart and start date < dayEnd and summary starts with "{BRIEF_TITLE_PREFIX}")
            repeat with ev in existing
                delete ev
            end repeat
        on error
            -- Ignore deletion errors; we still create the new one
        end try

        -- Create the new event
        make new event at end of events of targetCal with properties {{summary:"{safe_title}", start date:startDate, end date:endDate, description:"{safe_body}"}}
    end tell
    '''


def write_daily_brief(
    top_candidates: list[dict],
    target_date: datetime | None = None,
) -> tuple[bool, str]:
    """Write the daily brief into Calendar.app.

    `top_candidates` is a list of {"title", "next_step", "source"} dicts —
    typically the top 3 from FIGS' slate (needs registry items + wiki
    threads), already sorted by surface_priority.

    Returns (success, message). On failure, FIGS still operates — the
    daily brief is a parallel surface, not the primary path.
    """
    if not top_candidates:
        return False, "no candidates supplied; skipping brief"

    target = target_date or datetime.now()

    title = f"{BRIEF_TITLE_PREFIX}: today's top {min(len(top_candidates), 3)}"

    body_lines = []
    for idx, cand in enumerate(top_candidates[:3], start=1):
        cand_title = cand.get("title", "?")
        cand_step = (cand.get("next_step") or "").strip()
        cand_source = cand.get("source", "?")
        body_lines.append(f"{idx}. [{cand_source}] {cand_title}")
        if cand_step:
            body_lines.append(f"   → {cand_step[:200]}")
        body_lines.append("")
    body_lines.append("(Mark progress: `mikai mark-acted <id>` from terminal)")

    body = "\n".join(body_lines)

    script = _build_applescript(title, body, target)
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return False, "osascript not available (non-macOS?)"
    except subprocess.TimeoutExpired:
        return False, "osascript timed out (Calendar permission dialog may be blocking?)"

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()[:300]
        return False, f"AppleScript failed: {stderr}"

    return True, f"brief written for {target.strftime('%Y-%m-%d')}"


# ── Standalone smoke test ───────────────────────────────────────────────


if __name__ == "__main__":
    fake_candidates = [
        {
            "title": "Reactivate MSP — need to prove BC residence",
            "next_step": "Gather two BC residency proofs (driver's licence + utility bill).",
            "source": "needs",
        },
        {
            "title": "Buy proposal ring stone + book vacation venue",
            "next_step": "Decide stone shape and budget; pick Atacama vs Ladakh.",
            "source": "needs",
        },
        {
            "title": "Find AI job or commit to startup",
            "next_step": "Spend 90 minutes deciding: is MIKAI the startup?",
            "source": "needs",
        },
    ]
    target_arg = None
    if len(sys.argv) > 1:
        try:
            target_arg = datetime.strptime(sys.argv[1], "%Y-%m-%d")
        except ValueError:
            print(f"Usage: {sys.argv[0]} [YYYY-MM-DD]")
            sys.exit(2)
    ok, msg = write_daily_brief(fake_candidates, target_date=target_arg)
    print(f"{'✓' if ok else '✗'} {msg}")
    sys.exit(0 if ok else 1)
