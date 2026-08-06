"""
Week planner — override 5 workday instances of the recurring
Recommendations block with per-day themed engineering + life plans.

RFC 5545 pattern: insert override VEVENTs into the master's .ics, each
with the same UID and a distinct RECURRENCE-ID matching the original
instance's DTSTART. The master's RRULE is preserved untouched; only the
5 targeted instances get overridden. Every other week continues to
render the generic "Recommendations" title.

Usage:
    python3 week_planner.py                 # print plan (default: safe)
    python3 week_planner.py --dry-run       # print plan (explicit)
    python3 week_planner.py --apply         # PUT overrides to iCloud

Once this proves the mechanism, the logic folds into calendar_planner.py
as the recurring-block path.

WRITES BACK (SPEC §5.1 — an action that leaves no trace never happened):
- The master Recommendations .ics on iCloud (CalDAV PUT, --apply only) —
  5 override VEVENTs spliced in.
- `/tmp/mikai_weekplan_failed.ics` — debug dump, only on a failed PUT.
- `~/.mikai/brain/state/progress.jsonl` — one `mode="week_planner"` entry
  per successful --apply PUT. Preview runs, LLM failures, and failed PUTs
  log nothing.
- Thread log lines under `~/.mikai/brain/threads/` when a day plan's
  title/description/branch clearly names a thread (conservative heuristic
  match on slug / title / distinctive slug component).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import request as urlreq

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from caldav_client import (  # noqa: E402
    ICloudCalDAV, CalDAVError, _request, _escape_text, _fold,
)
import calendar_planner as cp  # noqa: E402

# The canonical MIKAI repo (all worktrees fold back to this one's ref DB).
MIKAI_REPO = Path(os.environ.get("MIKAI_REPO", str(Path.home() / "Desktop" / "MIKAI")))
BRANCH_ACTIVITY_DAYS = int(os.environ.get("MIKAI_BRANCH_ACTIVITY_DAYS", "30"))
BRANCH_MAX = int(os.environ.get("MIKAI_BRANCH_MAX", "12"))

# Ground truth from GETting the master .ics.
TARGET_UID = "46BF1457-63C5-464A-9C48-4D629B0AC7CC"
TARGET_HREF = (
    "https://p137-caldav.icloud.com:443/1369754264/"
    "calendars/work/46BF1457-63C5-464A-9C48-4D629B0AC7CC.ics"
)
DTSTART_TIME = "100000"   # 10:00 local
DTEND_TIME = "153000"     # 15:30 local
TZID = "America/Vancouver"

def week_workdays(anchor: date_type | None = None) -> list[date_type]:
    """Return Mon-Fri dates for the current work week. If today is
    Sat/Sun, return next week's Mon-Fri instead."""
    if anchor is None:
        anchor = datetime.now().astimezone().date()
    if anchor.weekday() >= 5:  # Sat or Sun
        days_to_mon = 7 - anchor.weekday()
        monday = anchor + timedelta(days=days_to_mon)
    else:
        monday = anchor - timedelta(days=anchor.weekday())
    return [monday + timedelta(days=i) for i in range(5)]


def _humanize_age(delta: timedelta) -> str:
    days = int(delta.total_seconds() // 86400)
    if days == 0:
        return "today"
    if days == 1:
        return "1d ago"
    if days < 7:
        return f"{days}d ago"
    if days < 30:
        return f"{days // 7}w ago"
    return f"{days // 30}mo ago"


def gather_workspace_branches() -> str:
    """Enumerate branches across the MIKAI workspace (all worktrees fold
    back to the same ref DB). For each recently-active branch, include
    the last few commit subjects so the LLM has concrete context, not
    just branch names.
    """
    if not MIKAI_REPO.exists():
        return f"(MIKAI_REPO={MIKAI_REPO} not found)"

    try:
        raw = subprocess.check_output(
            ["git", "-C", str(MIKAI_REPO), "for-each-ref", "refs/heads",
             "--sort=-committerdate",
             "--format=%(committerdate:iso-strict)|%(refname:short)|%(subject)"],
            text=True, timeout=10, stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return f"(git for-each-ref failed: {e})"

    now = datetime.now().astimezone()
    cutoff = now - timedelta(days=BRANCH_ACTIVITY_DAYS)

    blocks: list[str] = []
    for line in raw.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        date_str, branch, tip_subject = parts
        try:
            dt = datetime.fromisoformat(date_str)
        except ValueError:
            continue
        if dt < cutoff:
            break  # sorted DESC — everything after this is older still
        if len(blocks) >= BRANCH_MAX:
            break

        age = _humanize_age(now - dt)
        # Pull the last 5 commit subjects on this branch — cheap and
        # gives the LLM real signal about what the branch is about.
        try:
            log = subprocess.check_output(
                ["git", "-C", str(MIKAI_REPO), "log", "-5",
                 "--pretty=format:%h %s", branch, "--"],
                text=True, timeout=6, stderr=subprocess.DEVNULL,
            ).strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            log = tip_subject

        indented = "\n    ".join(log.splitlines())
        blocks.append(f"- {branch} ({age}):\n    {indented}")

    return "\n".join(blocks) if blocks else "(no branches active in the last "
    f"{BRANCH_ACTIVITY_DAYS} days)"


def gather_uncommitted_across_worktrees() -> str:
    """List uncommitted / untracked files across all MIKAI worktrees.
    Concise; caps at ~1500 chars.
    """
    if not MIKAI_REPO.exists():
        return ""
    try:
        wt_raw = subprocess.check_output(
            ["git", "-C", str(MIKAI_REPO), "worktree", "list", "--porcelain"],
            text=True, timeout=6, stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""

    worktrees = [
        line.split(" ", 1)[1] for line in wt_raw.splitlines()
        if line.startswith("worktree ")
    ]

    out: list[str] = []
    for wt in worktrees:
        try:
            branch = subprocess.check_output(
                ["git", "-C", wt, "rev-parse", "--abbrev-ref", "HEAD"],
                text=True, timeout=4, stderr=subprocess.DEVNULL,
            ).strip()
            status = subprocess.check_output(
                ["git", "-C", wt, "status", "--short"],
                text=True, timeout=4, stderr=subprocess.DEVNULL,
            ).strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        if status:
            # Only include worktrees that HAVE uncommitted state.
            out.append(f"  {branch} ({Path(wt).name}):\n    "
                       + status.replace("\n", "\n    ")[:400])
    joined = "\n".join(out)[:1500]
    return joined or "(all worktrees clean)"


def build_prompt(days: list[date_type], workspace_branches: str,
                 uncommitted_worktrees: str, open_q: str) -> str:
    """ENGINEERING-ONLY prompt for the Recommendations block.

    Life items (proposal, ocean farming, MSP, etc.) are deliberately
    excluded — this block is Brian's coding + technical-decision window.
    Life items belong in a separate block if we widen the pattern later.
    """
    days_lines = "\n".join(f"  - {d.strftime('%A, %Y-%m-%d')}" for d in days)
    return f"""You are MIKAI's week planner. The user has 5 recurring
"Recommendations: Noonchi + Sumimasen" work blocks THIS WEEK, each
10:00-15:30 Pacific. This block is the ENGINEERING window — no life
items, no personal admin, no relationship / health / travel picks.
Rewrite each day's block with ONE focused engineering theme drawn from
active MIKAI-workspace branches.

## HARD CONSTRAINTS

1. ENGINEERING ONLY. No proposal ring, no MSP, no ocean farming, no
   personal admin. Only work drawn from the branches / open questions /
   uncommitted files listed below.

2. Every pick MUST cite a specific branch name from the MIKAI WORKSPACE
   list below. If you can't tie a pick to a listed branch or open
   question, DROP IT. Do NOT invent a branch, file, or commit hash. Do
   NOT reference a branch not in the list.

3. ONE tight theme per day. Pick 1-3 tightly related items — a
   coherent block of work, not a checklist.

4. No two days cover the same headline theme. If two branches are
   closely related (e.g. calendar work spanning multiple worktrees),
   fold them into ONE day; use the other days for distinct topics.

5. Prefer an arc — hardest engineering early (Mon-Tue), integration /
   review mid-week (Wed), infra / cleanup late (Thu-Fri). Not
   mandatory but preferred when it fits the actual work.

6. Title MUST name the day's ONE headline pick clearly. 40-70 chars.

## DAYS
{days_lines}

## MIKAI WORKSPACE — active branches (last {BRANCH_ACTIVITY_DAYS} days)

{workspace_branches or "(no active branches)"}

## Uncommitted state across worktrees

{uncommitted_worktrees}

## Open architectural questions (docs/OPEN.md, truncated)

{open_q or "(empty)"}

## OUTPUT

Return ONLY valid JSON, no prose before or after:

{{
  "week_rationale": "<one sentence: the arc of the week>",
  "days": [
    {{
      "date": "YYYY-MM-DD",
      "weekday": "Monday" | "Tuesday" | ...,
      "title": "<compact 40-70 chars, names the headline pick>",
      "description": "<3-6 lines: 1-3 focused items with 1-line why each, blank line, references (branch names, commit hashes, file paths from the pool above)>",
      "rationale": "<one sentence: why THIS day for this theme>",
      "primary_branch": "<the single branch name this day maps to>"
    }},
    ...5 total, in date order
  ]
}}
"""


# tier=interactive: user-facing copy — 5 themed day-plan titles/descriptions
# land on Brian's calendar. Runs weekly, so volume is trivial for the Max-sub
# claude -p path; not bulk background extraction.
def call_llm(prompt: str, timeout: float = 300.0) -> dict:
    from infra.mikai_llm import chat as _chat
    raw = _chat(prompt, tier="interactive", json_mode=True, timeout=timeout)
    t = raw.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return json.loads(t.strip())


def render_override_vevent(day_date: date_type, title: str,
                           description: str, sequence: int) -> str:
    """Build a single override VEVENT string, ready to splice into the
    master's VCALENDAR. Every override carries the master's UID plus a
    RECURRENCE-ID pinpointing which instance it replaces.
    """
    d = day_date.strftime("%Y%m%d")
    dt_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VEVENT",
        f"UID:{TARGET_UID}",
        f"RECURRENCE-ID;TZID={TZID}:{d}T{DTSTART_TIME}",
        f"DTSTART;TZID={TZID}:{d}T{DTSTART_TIME}",
        f"DTEND;TZID={TZID}:{d}T{DTEND_TIME}",
        f"DTSTAMP:{dt_stamp}",
        f"LAST-MODIFIED:{dt_stamp}",
        f"SEQUENCE:{sequence}",
        _fold(f"SUMMARY:{_escape_text(title)}"),
        _fold(f"DESCRIPTION:{_escape_text(description)}"),
        "TRANSP:OPAQUE",
        "END:VEVENT",
    ]
    return "\r\n".join(lines)


def splice_overrides(master_ics: str, overrides: list[str]) -> str:
    """Insert the override VEVENT blocks immediately before END:VCALENDAR."""
    body = master_ics.replace("\r\n", "\n")
    idx = body.rfind("END:VCALENDAR")
    if idx == -1:
        raise ValueError("no END:VCALENDAR marker in master .ics")
    head = body[:idx].rstrip("\n") + "\n"
    tail = body[idx:]
    inserted_block = "\n".join(o.replace("\r\n", "\n") for o in overrides) + "\n"
    return (head + inserted_block + tail).replace("\n", "\r\n")


def _preview_desc(desc: str, width: int = 80) -> str:
    return "\n".join("    " + ln for ln in desc.splitlines())


def _write_back(plan: dict, days: list[date_type]) -> None:
    """Record a successful --apply PUT into the brain substrate (SPEC §5.1).

    Never raises — a write-back failure must not undo the fact that the
    calendar was already written. Thread appends are conservative: a day
    plan must clearly name a thread; no match → no append."""
    try:
        from infra.mikai_brain import ledger
        from infra.mikai_brain import threads as thread_mod

        day_rows = plan.get("days", [])
        titles = "; ".join(
            f"{d.get('weekday', '?')[:3]} {d.get('title', '?')}" for d in day_rows
        )
        did = (f"Wrote {len(day_rows)} week-plan overrides to iCloud "
               f"({days[0].isoformat()}→{days[-1].isoformat()}): {titles}")[:400]

        all_threads = thread_mod.load_all()
        touched: dict[str, tuple] = {}
        for d in day_rows:
            text = (f"{d.get('title', '')}\n{d.get('description', '')}\n"
                    f"{d.get('primary_branch', '')}")
            for th in thread_mod.match_threads_in_text(text, all_threads):
                touched.setdefault(th.slug, (th, []))[1].append(d)

        ledger.run(mode="week_planner", did=did,
                   threads_touched=sorted(touched),
                   extra={"uid": TARGET_UID,
                          "dates": [d.get("date", "") for d in day_rows]})

        for slug in sorted(touched):
            th, hits = touched[slug]
            for d in hits:
                thread_mod.append_log_line(
                    th,
                    f"[week_planner] Planned {d.get('weekday', '?')} "
                    f"{d.get('date', '?')}: {d.get('title', '?')!r}",
                )
    except Exception as exc:  # noqa: BLE001 — write-back must never kill the run
        print(f"WARN: brain write-back failed: {exc}", file=sys.stderr)


def main() -> int:
    user = os.environ.get("MIKAI_ICLOUD_USER", "")
    pw = os.environ.get("MIKAI_ICLOUD_APP_PASSWORD", "")
    if not (user and pw):
        print("ERROR: MIKAI_ICLOUD_USER / MIKAI_ICLOUD_APP_PASSWORD not set.",
              file=sys.stderr)
        return 2

    # 1. Fetch the master .ics (need its bytes + etag for optimistic PUT)
    try:
        status, headers, body = _request("GET", TARGET_HREF, user, pw)
    except CalDAVError as e:
        print(f"ERROR: CalDAV GET failed: {e}", file=sys.stderr)
        return 3
    master_ics = body.decode("utf-8", errors="replace")
    etag = (headers.get("ETag") or headers.get("Etag") or "").strip().strip('"')
    print(f"fetched master ({len(master_ics)} bytes, etag={etag!r})")

    # 2. Enumerate this week's Mon-Fri
    days = week_workdays()
    print(f"target days: {', '.join(d.isoformat() for d in days)}")
    print()

    # 3. Gather ENGINEERING-only candidate pool from the full MIKAI workspace
    workspace_branches = gather_workspace_branches()
    uncommitted_wt = gather_uncommitted_across_worktrees()
    open_q = cp.gather_open_questions()

    prompt = build_prompt(days, workspace_branches, uncommitted_wt, open_q)

    # 4. LLM call
    print("calling interactive-tier LLM (may take 20-60s)…")
    try:
        plan = call_llm(prompt)
    except Exception as e:
        print(f"ERROR: LLM call failed: {e}", file=sys.stderr)
        return 4

    if "days" not in plan or len(plan["days"]) != 5:
        print(f"ERROR: LLM returned {len(plan.get('days', []))} days, "
              f"expected 5. Raw: {json.dumps(plan)[:400]}", file=sys.stderr)
        return 5

    # 5. Print the plan
    print()
    print("=" * 70)
    print(f"WEEK PLAN — {plan.get('week_rationale', '')}")
    print("=" * 70)
    for d in plan["days"]:
        print()
        print(f"  {d['weekday']}, {d['date']}")
        print(f"  TITLE : {d['title']}")
        print(f"  DESC  :")
        print(_preview_desc(d["description"]))
        print(f"  WHY   : {d.get('rationale', '(no rationale)')}")

    # 6. If not --apply, stop here
    apply = "--apply" in sys.argv
    if not apply:
        print()
        print("↑ Preview only. Re-run with --apply to write these 5 overrides to iCloud.")
        return 0

    # 7. Build overrides + splice + PUT
    seq_match = re.search(r"^SEQUENCE:(\d+)$", master_ics, re.MULTILINE)
    master_seq = int(seq_match.group(1)) if seq_match else 10
    overrides = []
    for i, d in enumerate(plan["days"]):
        day_date = datetime.strptime(d["date"], "%Y-%m-%d").date()
        overrides.append(render_override_vevent(
            day_date, d["title"], d["description"], master_seq + 1 + i,
        ))
    new_ics = splice_overrides(master_ics, overrides)

    put_headers = {
        "Content-Type": "text/calendar; charset=utf-8",
    }
    if etag:
        put_headers["If-Match"] = f'"{etag}"'
    try:
        status, resp_headers, _ = _request(
            "PUT", TARGET_HREF, user, pw,
            body=new_ics.encode("utf-8"), headers=put_headers,
        )
    except CalDAVError as e:
        print(f"ERROR: CalDAV PUT failed: {e}", file=sys.stderr)
        # Save the composite .ics for debugging
        Path("/tmp/mikai_weekplan_failed.ics").write_text(new_ics)
        print("Saved failing .ics to /tmp/mikai_weekplan_failed.ics", file=sys.stderr)
        return 6

    new_etag = (resp_headers.get("ETag") or resp_headers.get("Etag")
                or "").strip().strip('"')
    print()
    print(f"✓ PUT status={status} new_etag={new_etag}")
    print("  5 overrides applied. Check iPhone Calendar in a few seconds "
          "(pull-to-refresh may help).")

    # 8. Write-back: the brain must know this happened (SPEC §5.1).
    #    Only reached after a successful PUT — failures return above.
    _write_back(plan, days)
    return 0


if __name__ == "__main__":
    sys.exit(main())
