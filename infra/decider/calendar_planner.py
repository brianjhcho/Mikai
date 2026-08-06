"""
MIKAI calendar planner (D-055).

Once per tick:
  1. Fetch today's editable calendar blocks from iCloud CalDAV.
     Editable = sole-attendee, ≥90-min duration, on a calendar under
     the user's own home set.
  2. Gather a candidate pool of "what needs to be built or discussed
     this week" from:
        - Recent git activity on this repo (branch, uncommitted, log)
        - docs/OPEN.md (architectural open questions)
        - ~/.mikai/inflight.md (Brian-curated manual override)
        - FIGS life candidates (needs registry)
  3. Ask the interactive-tier LLM (mikai_llm shim → claude -p) to pick
     2-3 items per block
     and produce a proposed title + description.
  4. Store each proposal in the calendar_proposals table (PROPOSED).
  5. Dispatch an ntfy card with Approve / Reject action URLs pointing at
     the tap-endpoint's /approve/{id} and /reject/{id} routes.

Nothing is written to the calendar in this module — the approval loop
lives in tap_endpoint.py. A proposal that isn't tapped within 4h gets
marked EXPIRED by a downstream expiry sweep (piggybacks on
dismissal_inference.py, or a dedicated cron; see D-055).

Runs as com.mikai.calendar-planner LaunchAgent, once a day at 08:00
local, plus manual --force for on-demand refresh.

WRITES BACK (SPEC §5.1 — an action that leaves no trace never happened):
- `calendar_proposals` table in `~/.mikai/notification_log.db` — one
  PROPOSED row per dispatched proposal (the mutation this module owns;
  the actual calendar write happens later in tap_endpoint.py).
- ntfy topic — one Approve/Reject card per proposal.
- `~/.mikai/brain/state/progress.jsonl` — one `mode="calendar_planner"`
  entry per run that dispatched >= 1 proposal. Dry runs, LLM failures,
  and zero-dispatch ticks log nothing.
- Thread log lines under `~/.mikai/brain/threads/` when a proposal's
  title/description clearly names a thread (conservative heuristic match
  on slug / title / distinctive slug component).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib import request as urlreq

# Reuse mikai_decide's DB helper + ntfy dispatch + tap-URL resolution so we
# stay consistent with the FIGS feedback-loop wiring.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mikai_decide as md  # noqa: E402
from caldav_client import ICloudCalDAV, CalDAVError, Event  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from infra.mikai_llm import chat as llm_chat  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
INFLIGHT_PATH = Path.home() / ".mikai" / "inflight.md"
OPEN_MD_PATH = REPO / "docs" / "OPEN.md"
NEEDS_MD_PATH = REPO / "docs" / "USER_NEEDS_REGISTRY.md"

MIN_BLOCK_MINUTES = int(os.environ.get("MIKAI_PLANNER_MIN_MINUTES", "90"))

# Comma-separated substring match on event titles. Case-insensitive.
# Default targets Brian's known editable blocks. Set to empty string to
# disable the filter (edit any sole-attendee ≥90min block).
DEFAULT_TITLE_PATTERNS = "Recommendations,Noonchi,Sumimasen,MIKAI,Focus,Deep work"
TITLE_PATTERNS = [p.strip().lower() for p in os.environ.get(
    "MIKAI_PLANNER_TITLE_INCLUDE", DEFAULT_TITLE_PATTERNS,
).split(",") if p.strip()]

def _title_matches(title: str) -> bool:
    """True if title matches any configured pattern, or if patterns are
    empty (no filter). Case-insensitive substring."""
    if not TITLE_PATTERNS:
        return True
    t = (title or "").lower()
    return any(p in t for p in TITLE_PATTERNS)


# ── Candidate gathering ────────────────────────────────────────────────


def _git(*args: str, cap: int = 4000) -> str:
    try:
        out = subprocess.check_output(
            ["git", *args], cwd=REPO, text=True,
            stderr=subprocess.DEVNULL, timeout=8,
        )
        return out[:cap]
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError):
        return ""


def gather_git_context() -> dict:
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").strip()
    uncommitted = _git("status", "--short", "--untracked-files=no").strip() \
        + "\n" + _git("status", "--short", "--", ".").strip()
    log = _git("log", "--since=7 days ago", "--pretty=format:%h %s", "--no-merges")
    branches = _git("branch", "--sort=-committerdate", "--format=%(refname:short)  %(committerdate:relative)")
    return {
        "branch": branch,
        "uncommitted": uncommitted.strip(),
        "recent_commits": log.strip(),
        "recent_branches": branches.strip(),
    }


def gather_open_questions(cap: int = 3000) -> str:
    if not OPEN_MD_PATH.exists():
        return ""
    return OPEN_MD_PATH.read_text(errors="replace")[:cap]


def gather_inflight(cap: int = 2000) -> str:
    if not INFLIGHT_PATH.exists():
        return ""
    return INFLIGHT_PATH.read_text(errors="replace")[:cap]


def gather_needs_registry(cap: int = 2000) -> str:
    if not NEEDS_MD_PATH.exists():
        return ""
    return NEEDS_MD_PATH.read_text(errors="replace")[:cap]


# ── LLM (mikai_llm shim, tier=interactive) ─────────────────────────────


def _prompt(current_title: str, current_desc: str, dt_range: str,
            git_ctx: dict, open_q: str, inflight: str, needs: str) -> str:
    return f"""You are MIKAI's calendar-planner. The user has a work block titled:

  "{current_title}"

scheduled today ({dt_range}). Rewrite its title and description so the block
reflects the top 2-3 highest-leverage items from the candidate pool below.
The user has explicitly asked for both engineering items AND life items —
give preference to whatever is genuinely at the top of what needs to be
built or discussed THIS WEEK, not the whole quarter.

## Current description (may be empty)
{current_desc or "(empty)"}

## Candidate pool

### Recent git activity on this repo
- Active branch: {git_ctx["branch"]}
- Uncommitted / untracked files:
{git_ctx["uncommitted"] or "(clean tree)"}

- Recent commit subjects (last 7 days):
{git_ctx["recent_commits"] or "(none)"}

- Recently touched branches:
{git_ctx["recent_branches"] or "(none)"}

### Open architectural questions (docs/OPEN.md, truncated)
{open_q or "(empty)"}

### Manual inflight override (~/.mikai/inflight.md — user-curated)
{inflight or "(empty)"}

### FIGS user needs registry
{needs or "(empty)"}

## Output

Return ONLY valid JSON. No prose before or after.

{{
  "title": "<compact title, 40-70 chars; name the SINGLE top pick clearly, e.g. 'Docker RAM fix + Memory decision'>",
  "description": "<multi-line: line 1-3 = top 2-3 picks each with a 1-line 'why now', blank line, then any branch/file/doc refs>",
  "picks": [
    {{"item": "<short name>", "source": "git|open_q|inflight|needs|life", "why_now": "<1 sentence>"}},
    ...
  ],
  "rationale": "<one sentence: why this set fits today specifically>"
}}
"""


# tier=interactive: user-facing copy — the proposal title/description land in
# Brian's calendar and ntfy card after a tap. Low volume (≤ a few blocks/day),
# so it fits the Max-sub claude -p path; not bulk background extraction.
def call_llm(prompt: str, timeout: float = 300.0) -> dict:
    raw = llm_chat(prompt, tier="interactive", json_mode=True, timeout=timeout)
    return json.loads(_strip_fences(raw))


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


# ── Proposal storage ───────────────────────────────────────────────────


def _minutes_between(dtstart: str, dtend: str) -> int:
    """Parse iCal DTSTART/DTEND strings and return minutes. Returns 0 if
    the shapes don't match — the caller treats 0 as "not enough info,
    skip"."""
    fmts = ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d")
    for f in fmts:
        try:
            a = datetime.strptime(dtstart[:len(f) if "T" in f else 8], f)
            b = datetime.strptime(dtend[:len(f) if "T" in f else 8], f)
            return int((b - a).total_seconds() // 60)
        except ValueError:
            continue
    return 0


def _human_range(dtstart: str, dtend: str) -> str:
    """Return like '10:00 → 16:00'."""
    def hm(v: str) -> str:
        m = re.match(r"^(\d{8})T(\d{2})(\d{2})", v)
        return f"{m.group(2)}:{m.group(3)}" if m else v[:8]
    return f"{hm(dtstart)} → {hm(dtend)}"


def insert_proposal(
    conn: sqlite3.Connection,
    proposal_id: str,
    event: Event,
    pick_title: str,
    pick_description: str,
    candidates_json: str,
    llm_rationale: str,
) -> None:
    conn.execute(
        """
        INSERT INTO calendar_proposals
            (proposal_id, event_uid, calendar_url, event_href, event_etag,
             status, proposed_at, current_title, current_description,
             proposed_title, proposed_description, candidates_json, llm_rationale)
        VALUES (?, ?, ?, ?, ?, 'PROPOSED', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            proposal_id, event.uid, event.calendar_href, event.event_href,
            event.etag,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            event.title, event.description,
            pick_title, pick_description, candidates_json, llm_rationale,
        ),
    )
    conn.commit()


# ── Ntfy dispatch with Approve/Reject actions ──────────────────────────


def dispatch_proposal(proposal_id: str, current: str, proposed_title: str,
                      proposed_description: str, dt_range: str) -> tuple[bool, str]:
    """Send the ntfy card with Approve + Reject action URLs. Reuses
    mikai_decide.dispatch_via_ntfy for the base send; adds an Actions
    header on top so the buttons render in Notification Center.
    """
    tap_base = md.resolve_tap_base_url()
    if not tap_base:
        return False, "MIKAI_TAP_BASE_URL not configured; approve/reject URLs unresolvable"

    approve_url = f"{tap_base}/approve/{proposal_id}"
    reject_url = f"{tap_base}/reject/{proposal_id}"

    # Body — keep under 2KB to avoid ntfy truncation on iOS.
    desc_preview = proposed_description
    if len(desc_preview) > 700:
        desc_preview = desc_preview[:700].rsplit("\n", 1)[0] + "\n[…truncated]"
    body = (
        f"CURRENT: {current}\n"
        f"NEW: {proposed_title}\n"
        f"WHEN: {dt_range}\n\n"
        f"{desc_preview}\n\n"
        f"Approve: {approve_url}\n"
        f"Reject:  {reject_url}"
    )

    # Actions header — ntfy pipe-syntax: view label,url; view label,url
    # Newer ntfy also supports the JSON-formatted X-Actions header. Simple
    # `view` action opens the URL when tapped (works on iOS and web).
    actions = f"view, Approve, {approve_url}; view, Reject, {reject_url}"

    if not md.NTFY_TOPIC:
        return False, "MIKAI_NTFY_TOPIC not set"
    url = f"{md.NTFY_BASE_URL}/{md.NTFY_TOPIC}"
    headers = {
        "Title": "MIKAI: rewrite today's block?",
        "Priority": "4",
        "Tags": "mikai,calendar",
        "Actions": actions,
    }
    req = urlreq.Request(url, data=body.encode("utf-8"), method="POST", headers=headers)
    try:
        with urlreq.urlopen(req, timeout=10) as resp:
            return True, f"http_{resp.status}"
    except Exception as e:
        return False, f"ntfy_error: {e}"


# ── Brain write-back (SPEC §5.1) ───────────────────────────────────────


def _write_back(dispatched: list[tuple[str, str, str]]) -> None:
    """Record dispatched proposals into the brain substrate.

    `dispatched` is [(proposal_id, title, description), ...] for proposals
    that were BOTH stored and successfully sent via ntfy. Never raises —
    a write-back failure must not break a completed tick. Thread appends
    are conservative: no clear match → no append."""
    try:
        from infra.mikai_brain import ledger
        from infra.mikai_brain import threads as thread_mod

        titles = "; ".join(t for _, t, _ in dispatched)
        did = (f"Proposed {len(dispatched)} calendar block rewrite(s) "
               f"for approval: {titles}")[:300]

        all_threads = thread_mod.load_all()
        touched: dict[str, tuple] = {}
        for pid, title, desc in dispatched:
            for th in thread_mod.match_threads_in_text(f"{title}\n{desc}", all_threads):
                touched.setdefault(th.slug, (th, []))[1].append((pid, title))

        ledger.run(mode="calendar_planner", did=did,
                   threads_touched=sorted(touched),
                   extra={"proposal_ids": [p for p, _, _ in dispatched]})

        for slug in sorted(touched):
            th, hits = touched[slug]
            for pid, title in hits:
                thread_mod.append_log_line(
                    th,
                    f"[calendar_planner] Proposed block rewrite {pid}: "
                    f"{title!r} (awaiting approval)",
                )
    except Exception as exc:  # noqa: BLE001 — write-back must never kill the tick
        print(f"WARN: brain write-back failed: {exc}", file=sys.stderr)


# ── Main tick ──────────────────────────────────────────────────────────


def _dedupe_key(event: Event) -> str:
    return f"{event.uid}::{datetime.now(timezone.utc).date().isoformat()}"


def already_proposed_today(conn: sqlite3.Connection, event: Event) -> bool:
    """Skip if we've already sent a proposal for this event today,
    regardless of the proposal's status. Prevents re-firing after Reject.
    """
    row = conn.execute(
        """
        SELECT 1 FROM calendar_proposals
        WHERE event_uid = ?
          AND date(proposed_at) = date('now')
        LIMIT 1
        """,
        (event.uid,),
    ).fetchone()
    return row is not None


def run_once(dry_run: bool = False, force: bool = False) -> int:
    user = os.environ.get("MIKAI_ICLOUD_USER", "")
    pw = os.environ.get("MIKAI_ICLOUD_APP_PASSWORD", "")
    if not user or not pw:
        print("ERROR: set MIKAI_ICLOUD_USER and MIKAI_ICLOUD_APP_PASSWORD "
              "(app-specific password from appleid.apple.com).", file=sys.stderr)
        return 2

    conn = md.db_connect()
    client = ICloudCalDAV(user, pw)

    try:
        events = client.todays_events(sole_attendee_only=True)
    except CalDAVError as e:
        print(f"ERROR: CalDAV discovery failed: {e}", file=sys.stderr)
        return 3

    editable = [
        e for e in events
        if _minutes_between(e.dtstart, e.dtend) >= MIN_BLOCK_MINUTES
        and _title_matches(e.title)
    ]

    if not editable:
        print(f"OK: no editable blocks today (found {len(events)} sole-attendee "
              f"events; filter ≥{MIN_BLOCK_MINUTES}min + title in {TITLE_PATTERNS or 'ANY'}).")
        return 0

    git_ctx = gather_git_context()
    open_q = gather_open_questions()
    inflight = gather_inflight()
    needs = gather_needs_registry()

    fired = 0
    dispatched: list[tuple[str, str, str]] = []
    for event in editable:
        if not force and already_proposed_today(conn, event):
            print(f"  ⏭  already proposed today: {event.title!r}")
            continue

        dt_range = _human_range(event.dtstart, event.dtend)
        prompt = _prompt(event.title, event.description, dt_range,
                         git_ctx, open_q, inflight, needs)

        try:
            resp = call_llm(prompt)
        except Exception as e:
            print(f"  ✗ LLM call failed for {event.title!r}: {e}", file=sys.stderr)
            continue

        new_title = str(resp.get("title", "")).strip()
        new_desc = str(resp.get("description", "")).strip()
        picks = resp.get("picks", [])
        rationale = str(resp.get("rationale", "")).strip()

        if not new_title or not new_desc:
            print(f"  ✗ LLM returned incomplete proposal for {event.title!r}",
                  file=sys.stderr)
            continue

        proposal_id = uuid.uuid4().hex[:12]

        if dry_run:
            print(f"[DRY-RUN] event uid={event.uid}")
            print(f"  current : {event.title!r}")
            print(f"  proposed: {new_title!r}")
            print(f"  desc    :\n    {new_desc.replace(chr(10), chr(10) + '    ')}")
            print(f"  picks   : {json.dumps(picks, indent=2)}")
            print(f"  rationale: {rationale}")
            print()
            continue

        insert_proposal(
            conn, proposal_id, event, new_title, new_desc,
            candidates_json=json.dumps(picks),
            llm_rationale=rationale,
        )

        ok, msg = dispatch_proposal(
            proposal_id, current=event.title,
            proposed_title=new_title, proposed_description=new_desc,
            dt_range=dt_range,
        )
        if ok:
            fired += 1
            dispatched.append((proposal_id, new_title, new_desc))
            print(f"  ✓ proposal {proposal_id}: {new_title!r} ({msg})")
        else:
            print(f"  ✗ dispatch failed for {proposal_id}: {msg}", file=sys.stderr)

    # Write-back: the brain must know this happened (SPEC §5.1).
    # Only successfully dispatched proposals count; zero dispatched → no row.
    if dispatched and not dry_run:
        _write_back(dispatched)

    if fired == 0 and not dry_run:
        print("OK: 0 proposals dispatched this tick.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Show proposals without inserting or dispatching.")
    ap.add_argument("--force", action="store_true",
                    help="Re-propose even for events already handled today.")
    args = ap.parse_args()
    return run_once(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
