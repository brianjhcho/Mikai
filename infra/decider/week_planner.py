"""
Week planner — override 5 workday instances of the recurring
Recommendations block with per-day themed engineering + life plans.

RFC 5545 pattern: insert override VEVENTs into the master's .ics, each
with the same UID and a distinct RECURRENCE-ID matching the original
instance's DTSTART. The master's RRULE is preserved untouched; only the
5 targeted instances get overridden. Every other week continues to
render the generic "Recommendations" title.

Usage:
    make week                               # print plan (default: safe)
    make week-apply                         # print plan, confirm, then PUT

    python3 week_planner.py                 # print plan (default: safe)
    python3 week_planner.py --dry-run       # print plan (explicit)
    python3 week_planner.py --apply         # PUT overrides after a typed y
    python3 week_planner.py --apply --yes   # skip the prompt (owns the risk)

--apply asks for confirmation at the keyboard before writing; that typed
`y` is this path's equivalent of the ntfy Approve tap the unattended daily
planner requires (D-055). A non-TTY stdin aborts rather than proceeding.

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

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
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

# Which recurring event to rewrite. Overridable by env so the
# account-specific href isn't a hardcoded constant in a tracked file.
#
# Everything ELSE about the block — start time, end time, timezone,
# sequence — is read off the master .ics at runtime by _parse_master().
# It used to be four more constants, which silently rotted the moment the
# block was recreated: the old UID's series had an RRULE ending
# 2026-07-15, so overrides were being aimed at instances that no longer
# existed. The calendar is the ground truth; don't keep a second copy.
_DEFAULT_TARGET_UID = "AB6210F8-6CDA-4A03-B950-0BDF5E71C682"
TARGET_UID = os.environ.get("MIKAI_WEEKPLAN_UID", _DEFAULT_TARGET_UID)
TARGET_HREF = os.environ.get(
    "MIKAI_WEEKPLAN_HREF",
    "https://p137-caldav.icloud.com:443/1369754264/"
    f"calendars/work/{_DEFAULT_TARGET_UID}.ics",
)

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
            # 400 chars used to cut pear-seashore's status off after ~10 of
            # 30 lines, hiding untracked dirs (which sort last) entirely —
            # including a whole subproject under active development.
            out.append(f"  {branch} ({Path(wt).name}):\n    "
                       + status.replace("\n", "\n    ")[:1500])
    joined = "\n".join(out)[:5000]
    return joined or "(all worktrees clean)"


def build_prompt(days: list[date_type], workspace_branches: str,
                 uncommitted_worktrees: str, open_q: str,
                 inflight: str = "") -> str:
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

2. Every pick MUST be traceable to something listed below — an IN FLIGHT
   item, a branch in the MIKAI WORKSPACE list, an uncommitted path, or an
   open question. If you can't tie a pick to one of those, DROP IT. Do
   NOT invent a branch, file, or commit hash. Do NOT reference a branch
   not in the list.

   Note that active work does NOT always have a branch: untracked
   directories and design docs are real work too. An IN FLIGHT item
   citing a file path is a perfectly good citation — do not skip it for
   lacking a commit.

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

## IN FLIGHT — what the user says he is actually working on (authoritative)

This is hand-written by the user and outranks everything below it. If it
is non-empty, the week's plan should be built around it, and the items
here should appear with the granularity they are written at — if an item
names a file, a function, or a time estimate, carry that into the day's
description rather than restating it abstractly. Git history is a lagging
indicator of this; when the two disagree, this section wins.

{inflight or "(empty — falling back to git activity below)"}

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


class MasterShape(NamedTuple):
    """The facts about the recurring series that overrides must match."""
    tzid: str
    start_time: str      # HHMMSS, local to tzid
    end_time: str        # HHMMSS
    sequence: int
    until: date_type | None   # RRULE UNTIL, if the series is bounded
    bydays: set[str]          # e.g. {"MO","TU","WE","TH","FR"}


_ICS_DAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _parse_master(ics: str) -> MasterShape:
    """Read the recurring series' own shape out of the master .ics.

    An override VEVENT only binds to an instance if its RECURRENCE-ID
    matches that instance's start exactly — same clock time, same TZID.
    Deriving those from the master (rather than hardcoding them) is what
    keeps this correct when the block is edited or recreated.

    Only the master VEVENT is read: the one carrying RRULE and no
    RECURRENCE-ID. Existing override VEVENTs in the same .ics are skipped.
    """
    body = ics.replace("\r\n", "\n")
    # Isolate the master VEVENT — the block with an RRULE but no RECURRENCE-ID.
    master_block = None
    for block in re.findall(r"BEGIN:VEVENT\n(.*?)END:VEVENT", body, re.S):
        if "RRULE:" in block and "RECURRENCE-ID" not in block:
            master_block = block
            break
    if master_block is None:
        raise ValueError("no master VEVENT (RRULE, no RECURRENCE-ID) in .ics")

    def _dt(prop: str) -> tuple[str, str]:
        m = re.search(rf"^{prop};TZID=([^:]+):(\d{{8}})T(\d{{6}})$",
                      master_block, re.M)
        if not m:
            raise ValueError(f"{prop} missing or not TZID-qualified in master")
        return m.group(1), m.group(3)

    tzid, start_time = _dt("DTSTART")
    _, end_time = _dt("DTEND")

    rrule = re.search(r"^RRULE:(.+)$", master_block, re.M).group(1)
    parts = dict(p.split("=", 1) for p in rrule.split(";") if "=" in p)
    until = None
    if "UNTIL" in parts:
        until = datetime.strptime(parts["UNTIL"][:8], "%Y%m%d").date()
    bydays = set(parts.get("BYDAY", "").split(",")) - {""}

    seq_m = re.search(r"^SEQUENCE:(\d+)$", master_block, re.M)
    return MasterShape(tzid, start_time, end_time,
                       int(seq_m.group(1)) if seq_m else 0, until, bydays)


def check_days_covered(shape: MasterShape, days: list[date_type]) -> str | None:
    """Return an error string if the target days aren't real instances of
    the series, else None.

    Without this the planner will happily PUT overrides whose
    RECURRENCE-IDs point at instances that don't exist — which is exactly
    what a stale hardcoded UID caused: the old series' RRULE ended
    2026-07-15 and every override aimed past it was junk.
    """
    if shape.until and days[-1] > shape.until:
        return (f"the recurring series ends {shape.until.isoformat()}, but this "
                f"week runs to {days[-1].isoformat()}. There are no instances "
                f"left to override — the block likely got recreated under a new "
                f"UID. Point MIKAI_WEEKPLAN_UID / MIKAI_WEEKPLAN_HREF at the "
                f"current event.")
    if shape.bydays:
        allowed = {_ICS_DAYS[d] for d in shape.bydays if d in _ICS_DAYS}
        missing = [d.isoformat() for d in days if d.weekday() not in allowed]
        if missing:
            return (f"the series only recurs on {sorted(shape.bydays)}; these "
                    f"target days have no instance: {', '.join(missing)}")
    return None


def render_override_vevent(day_date: date_type, title: str,
                           description: str, sequence: int,
                           shape: MasterShape) -> str:
    """Build a single override VEVENT string, ready to splice into the
    master's VCALENDAR. Every override carries the master's UID plus a
    RECURRENCE-ID pinpointing which instance it replaces.
    """
    d = day_date.strftime("%Y%m%d")
    dt_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VEVENT",
        f"UID:{TARGET_UID}",
        f"RECURRENCE-ID;TZID={shape.tzid}:{d}T{shape.start_time}",
        f"DTSTART;TZID={shape.tzid}:{d}T{shape.start_time}",
        f"DTEND;TZID={shape.tzid}:{d}T{shape.end_time}",
        f"DTSTAMP:{dt_stamp}",
        f"LAST-MODIFIED:{dt_stamp}",
        f"SEQUENCE:{sequence}",
        _fold(f"SUMMARY:{_escape_text(title)}"),
        _fold(f"DESCRIPTION:{_escape_text(description)}"),
        "TRANSP:OPAQUE",
        "END:VEVENT",
    ]
    return "\r\n".join(lines)


def _recurrence_ids(vevent: str) -> set[str]:
    return set(re.findall(r"^RECURRENCE-ID[^:]*:(\S+)$", vevent, re.M))


def splice_overrides(master_ics: str, overrides: list[str]) -> str:
    """Insert override VEVENT blocks before END:VCALENDAR, replacing any
    existing override for the same instance.

    Replacement matters: two VEVENTs sharing a UID *and* a RECURRENCE-ID
    are the same instance declared twice, which RFC 5545 doesn't define
    and clients resolve inconsistently. Appending blindly meant a second
    run in the same week stacked a duplicate on every day. Overrides for
    *other* weeks are left untouched — they're real history.
    """
    body = master_ics.replace("\r\n", "\n")
    incoming = set()
    for o in overrides:
        incoming |= _recurrence_ids(o.replace("\r\n", "\n"))

    def _superseded(block: str) -> bool:
        return bool(_recurrence_ids(block) & incoming)

    kept = []
    for match in re.finditer(r"BEGIN:VEVENT\n.*?END:VEVENT\n?", body, re.S):
        if _superseded(match.group(0)):
            kept.append(match.span())
    for start, end in reversed(kept):
        body = body[:start] + body[end:]

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


ENV_FILE = Path.home() / ".mikai" / "launchd.env"


def load_launchd_env(path: Path = ENV_FILE) -> None:
    """Source KEY=VALUE pairs from launchd.env. Existing environment
    variables win.

    The LaunchAgent runners source this file in shell before exec'ing
    python; a `make week` from an ordinary terminal does not, and would
    otherwise fail the iCloud credential check for no good reason. Same
    helper shape as backfill_to_wiki.load_launchd_env.
    """
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _confirm(days: list[date_type]) -> bool:
    """Ask at the keyboard before writing to a real calendar.

    This is the approval gate D-055 requires. The unattended 08:00 path
    (calendar_planner.py) gets its approval from an ntfy Approve tap; the
    typed path gets it here, from someone who has just read the preview
    above. Anything that isn't an interactive `y` aborts — a non-TTY stdin
    (pipe, cron, CI) has no one present to approve, so it must not proceed.
    """
    span = f"{days[0].isoformat()} → {days[-1].isoformat()}"
    print()
    print(f"This will REWRITE {len(days)} calendar blocks on iCloud ({span}).")
    if not sys.stdin.isatty():
        print("ABORT: stdin is not a TTY — no one is here to approve. "
              "Re-run in a terminal, or pass --yes if you own this call.",
              file=sys.stderr)
        return False
    try:
        answer = input("Apply these overrides? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        print("ABORT: no confirmation received.", file=sys.stderr)
        return False
    if answer not in ("y", "yes"):
        print("ABORT: not applied.")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="week_planner",
        description="Theme this week's 5 recurring Recommendations blocks "
                    "from live MIKAI-workspace engineering activity.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true",
                      help="write the 5 overrides to iCloud (asks first)")
    mode.add_argument("--dry-run", action="store_true",
                      help="print the plan and stop (default)")
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt; only with --apply")
    args = parser.parse_args()

    if args.yes and not args.apply:
        parser.error("--yes is meaningless without --apply")

    load_launchd_env()
    user = os.environ.get("MIKAI_ICLOUD_USER", "")
    pw = os.environ.get("MIKAI_ICLOUD_APP_PASSWORD", "")
    if not (user and pw):
        print(f"ERROR: MIKAI_ICLOUD_USER / MIKAI_ICLOUD_APP_PASSWORD not set "
              f"(looked in the environment and {ENV_FILE}).", file=sys.stderr)
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

    # 2. Enumerate this week's Mon-Fri, and confirm they're real instances
    #    of this series BEFORE spending 20-60s on an LLM call.
    days = week_workdays()
    try:
        shape = _parse_master(master_ics)
    except ValueError as e:
        print(f"ERROR: could not read the recurring series: {e}", file=sys.stderr)
        return 3
    print(f"block: {shape.start_time[:2]}:{shape.start_time[2:4]}–"
          f"{shape.end_time[:2]}:{shape.end_time[2:4]} {shape.tzid} "
          f"on {','.join(sorted(shape.bydays)) or '(no BYDAY)'}")
    problem = check_days_covered(shape, days)
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 7
    print(f"target days: {', '.join(d.isoformat() for d in days)}")
    # Surface the repo the candidate pool is drawn from — MIKAI_REPO defaults
    # to ~/Desktop/MIKAI while the installed runner works out of a worktree,
    # so a wrong-repo run should be obvious rather than silently thin.
    print(f"candidate repo: {MIKAI_REPO}")
    print()

    # 3. Gather ENGINEERING-only candidate pool from the full MIKAI workspace
    workspace_branches = gather_workspace_branches()
    uncommitted_wt = gather_uncommitted_across_worktrees()
    open_q = cp.gather_open_questions()
    # Brian-curated override. Reuses calendar_planner's reader so both
    # planners see the same file. Generous cap: this is the channel for
    # work that has no branch yet, so it carries the detail git can't.
    inflight = cp.gather_inflight(cap=6000)
    print(f"in-flight: {len(inflight)} chars"
          if inflight else
          f"in-flight: (empty — {cp.INFLIGHT_PATH} not found; git activity only)")

    prompt = build_prompt(days, workspace_branches, uncommitted_wt, open_q,
                          inflight)

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
    if not args.apply:
        print()
        print("↑ Preview only. Re-run with --apply to write these 5 overrides to iCloud.")
        return 0

    # 6b. Explicit approval before any mutation (D-055).
    if not args.yes and not _confirm(days):
        return 0

    # 6c. Re-fetch the master immediately before the PUT. The GET above
    #     happened before a 20-60s LLM call, and iCloud may have bumped the
    #     etag in that window — a stale If-Match would 412. Same refetch the
    #     tap-endpoint's /approve route does for the daily proposals.
    try:
        _, headers, body = _request("GET", TARGET_HREF, user, pw)
    except CalDAVError as e:
        print(f"ERROR: CalDAV re-GET before PUT failed: {e}", file=sys.stderr)
        return 3
    fresh_ics = body.decode("utf-8", errors="replace")
    fresh_etag = (headers.get("ETag") or headers.get("Etag") or "").strip().strip('"')
    if fresh_etag != etag:
        print(f"note: etag moved during planning ({etag!r} → {fresh_etag!r}); "
              f"splicing into the fresh master.")
    master_ics, etag = fresh_ics, fresh_etag

    # 7. Build overrides + splice + PUT. Re-parse: the re-GET above may have
    #    returned a master edited since step 2.
    shape = _parse_master(master_ics)
    overrides = []
    for i, d in enumerate(plan["days"]):
        day_date = datetime.strptime(d["date"], "%Y-%m-%d").date()
        overrides.append(render_override_vevent(
            day_date, d["title"], d["description"], shape.sequence + 1 + i,
            shape,
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
        if "412" in str(e):
            print("  412 Precondition Failed — the event changed on iCloud "
                  "between the re-GET and this PUT. Nothing was written. "
                  "Re-run to plan against the current version.", file=sys.stderr)
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
