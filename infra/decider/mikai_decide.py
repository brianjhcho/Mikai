#!/usr/bin/env python3
"""
mikai_decide.py — LLM-only notification decider for MIKAI.

Compatible with Python 3.8+.

Per tick:
  1. Reads task-state thread files (~/.mikai/brain/threads, override
     MIKAI_BRAIN_ROOT), BRAIN/GOALS/USER_MODEL docs, and the wiki pages those
     threads name (MIKAI_WIKI_ROOT, read-only). See brain_context.py.
  2. Reads last N decisions from the local SQLite log.
  3. Asks Claude (via `claude -p`, Max-legitimate first-party OAuth) for a
     JSON decision: default silence, or 1-3 notifications.
  4. Validates the decision (cited slugs exist on disk, length bounds).
  5. If send: dispatches via ntfy.sh.
  6. Logs everything to ~/.mikai/notification_log.db.

Run modes:
  --init        Initialize the SQLite schema and exit
  --test-ntfy   Send a static test notification to ntfy. Verifies path. No context read, no Claude.
  --dry-run     Build prompt, get decision, validate. Do NOT dispatch, do NOT log.
  --force       Ignore cooldown.
  (no flag)     Real tick. Cooldown enforced. Logs to SQLite.

Setup (one-time):
  brew install nothing-required
  pip install nothing-required
  export MIKAI_NTFY_TOPIC="<pick a long random topic name>"
  # On iPhone: install the "ntfy" app and subscribe to your topic.
  python infra/decider/mikai_decide.py --init
  python infra/decider/mikai_decide.py --test-ntfy
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import request as urlreq

# Make sibling `adapters/` importable regardless of CWD
sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters import imessage, calendar as cal_adapter, gmail  # noqa: E402
import brain_context  # noqa: E402
import needs_lens  # noqa: E402
import dispatch_calendar  # noqa: E402
import imessage_dispatch  # noqa: E402

# Life-dimensions ontology (see docs/DIMENSIONS.md). Loaded verbatim into the
# prompt as the top-level frame — dimensions are the schema FIGS uses to
# route candidates into meaningful surfacing rather than flat-density rank.
DIMENSIONS_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "DIMENSIONS.md"

def load_dimensions() -> str:
    if not DIMENSIONS_PATH.exists():
        return "(DIMENSIONS.md not found — falling back to flat needs+wiki ranking)"
    return DIMENSIONS_PATH.read_text()


# Life-tier config (~/.mikai/life-tier.json). Declares Brian's current top-4
# themes as an overlay above the 9-dim ontology. See docs/COMPARISON.md — the
# declarative top-tier is one of MIKAI's differentiators over Hermes/OpenClaw.
# Missing file = fall back to pure-ontology ranking (no top-4 bias).
LIFE_TIER_PATH = Path.home() / ".mikai" / "life-tier.json"


def load_life_tier() -> str:
    """Return the life-tier config as a prompt-shaped markdown block.
    Empty string when the config is missing so build_prompt() can degrade
    gracefully — the FRAME + wiki still work without top-4 bias."""
    if not LIFE_TIER_PATH.exists():
        return "(no life-tier config at ~/.mikai/life-tier.json — falling back to pure-ontology ranking)"
    try:
        cfg = json.loads(LIFE_TIER_PATH.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return f"(life-tier config unreadable: {exc})"

    lines: list[str] = []
    lines.append(
        "Brian has declared the following as his TOP-TIER life themes for the "
        "current period. When an item clears the interruption bar, prefer "
        "items from these themes; they outrank the 9-dim ontology's raw "
        "ordering — dimensions are the classifier, top-tier is the ranker. "
        "A theme with nothing worth an interruption stays silent."
    )
    lines.append("")
    lines.append(f"Life-tier config version {cfg.get('version', '?')} "
                 f"(updated {cfg.get('updated_at', '?')}):")
    lines.append("")
    for i, tier in enumerate(cfg.get("top_tier", []), 1):
        lines.append(f"{i}. **{tier['name']}** (weight {tier.get('weight', 1.0)})")
        srcs = ", ".join(tier.get("sources", []))
        if srcs:
            lines.append(f"   - Sources: {srcs}")
        also = tier.get("also_pull_from")
        if also:
            lines.append(f"   - Also pull from: {', '.join(also)}")
        filts = tier.get("filter_goals", [])
        if filts:
            lines.append(f"   - Include goals matching: {', '.join(repr(f) for f in filts)}")
        rejs = tier.get("reject_goals", [])
        if rejs:
            lines.append(f"   - Reject goals matching: {', '.join(repr(r) for r in rejs)}")
        why = tier.get("why_now")
        if why:
            lines.append(f"   - Why now: {why}")
        lines.append("")

    resolved = cfg.get("resolved", [])
    if resolved:
        lines.append("RESOLVED (do not surface — user has closed these):")
        for r in resolved:
            lines.append(f"  - {r}")
        lines.append("")

    reject = cfg.get("reject_universally", [])
    if reject:
        lines.append(
            "REJECT UNIVERSALLY (never surface as a top-tier item — these are "
            "MIKAI's own tooling, not the user's life): "
            + ", ".join(repr(r) for r in reject)
        )
        lines.append("")

    guardrails = cfg.get("guardrails", {})
    if guardrails:
        lines.append("Guardrails:")
        for k, v in guardrails.items():
            if k == "notes":
                continue
            lines.append(f"  - {k}: {v}")
        if guardrails.get("notes"):
            lines.append(f"  Notes: {guardrails['notes']}")

    return "\n".join(lines)

# ── Config ─────────────────────────────────────────────────────────────

NTFY_BASE_URL = os.environ.get("MIKAI_NTFY_BASE", "https://ntfy.sh")
NTFY_TOPIC = os.environ.get("MIKAI_NTFY_TOPIC", "")

DB_PATH = Path(os.environ.get("MIKAI_DB_PATH", str(Path.home() / ".mikai" / "notification_log.db")))
COOLDOWN_HOURS = float(os.environ.get("MIKAI_COOLDOWN_HOURS", "2"))
RECENT_DECISIONS_N = 15

# Tap-redirect base URL. Every ntfy Click URL is rewritten to
# `${TAP_BASE_URL}/t/${notif_id}` so we can log the tap event before
# 302-ing to the real destination. Resolution order:
#   1. env MIKAI_TAP_BASE_URL (explicit override)
#   2. ~/.mikai/tap_base_url (written by cloudflared runner on tunnel start)
#   3. empty → dispatch raw URLs untracked (feedback loop off)
TAP_BASE_FILE = Path.home() / ".mikai" / "tap_base_url"


def resolve_tap_base_url() -> str:
    env = os.environ.get("MIKAI_TAP_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    if TAP_BASE_FILE.exists():
        try:
            v = TAP_BASE_FILE.read_text().strip().rstrip("/")
            if v:
                return v
        except OSError:
            pass
    return ""

CLAUDE_TIMEOUT_S = 360

# ── DB ─────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tick_ts TEXT NOT NULL,
    prompt_hash TEXT,
    decision_json TEXT,
    sent INTEGER NOT NULL DEFAULT 0,
    title TEXT,
    body TEXT,
    priority TEXT,
    evidence_edge_uuids TEXT,
    reasoning TEXT,
    user_response TEXT,
    response_at TEXT,
    not_sent_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_notification_log_tick ON notification_log(tick_ts);
CREATE INDEX IF NOT EXISTS idx_notification_log_sent ON notification_log(sent);

-- Event stream for the feedback loop. Each notification generates a SENT
-- row at dispatch, then a TAPPED row when the redirect endpoint hits, or
-- a DISMISSED_INFERRED row if the hourly job finds no tap within 24h.
-- The next_step_url is stored server-side only so the real destination
-- never leaves this DB; ntfy only ever sees the tap-redirect URL.
CREATE TABLE IF NOT EXISTS notification_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notif_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('SENT','TAPPED','DISMISSED_INFERRED')),
    event_ts TEXT NOT NULL,
    dimension TEXT,
    action_type TEXT,
    source_ids TEXT,
    next_step_url TEXT
);

CREATE INDEX IF NOT EXISTS idx_notification_events_notif ON notification_events(notif_id);
CREATE INDEX IF NOT EXISTS idx_notification_events_type_ts ON notification_events(event_type, event_ts);

-- Calendar rewrite proposals (D-055). Kept in a separate table from
-- notification_events because (a) SQLite can't ALTER a CHECK constraint,
-- and (b) proposals have a different lifecycle (PROPOSED → APPLIED |
-- REJECTED | EXPIRED) than the append-only event stream.
--
-- A proposal represents: MIKAI wants to rewrite iCloud CalDAV event
-- `event_uid` on calendar `calendar_url` from (current_title, current_description)
-- to (proposed_title, proposed_description). It sits PROPOSED until the user
-- taps Approve or Reject (via tap-endpoint /approve/{proposal_id} or
-- /reject/{proposal_id}), or the hourly expiry job marks it EXPIRED at 4h.
CREATE TABLE IF NOT EXISTS calendar_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id TEXT NOT NULL UNIQUE,
    event_uid TEXT NOT NULL,
    calendar_url TEXT NOT NULL,
    event_href TEXT NOT NULL,
    event_etag TEXT,
    status TEXT NOT NULL CHECK (status IN ('PROPOSED','APPLIED','REJECTED','EXPIRED')),
    proposed_at TEXT NOT NULL,
    resolved_at TEXT,
    current_title TEXT,
    current_description TEXT,
    proposed_title TEXT,
    proposed_description TEXT,
    candidates_json TEXT,
    llm_rationale TEXT,
    apply_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_calendar_proposals_status ON calendar_proposals(status, proposed_at);
CREATE INDEX IF NOT EXISTS idx_calendar_proposals_pid ON calendar_proposals(proposal_id);
"""

# Columns added after the initial schema landed. SQLite doesn't support
# ADD COLUMN IF NOT EXISTS, so we attempt + swallow OperationalError per col.
EXTRA_COLUMNS = [
    ("decision_point", "TEXT"),
    ("slate_index", "INTEGER"),
    ("slate_size", "INTEGER"),
    ("next_step_url", "TEXT"),
    ("action_type", "TEXT"),
    ("notif_id", "TEXT"),
    ("candidate_source", "TEXT"),
    ("candidate_slug", "TEXT"),
    ("imessage_status", "TEXT"),
]


def db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for col, decl in EXTRA_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE notification_log ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass  # already added
    # Index on the newly-added notif_id column (idempotent).
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_log_notif ON notification_log(notif_id)"
    )
    conn.commit()
    return conn


# ── File context ───────────────────────────────────────────────────────

def gather_context() -> dict:
    # PRIMARY: thread files (task-state) + priority docs + the wiki pages
    # those threads name. All read-only, all on disk.
    threads = brain_context.rank_threads(brain_context.load_threads())
    brain_docs = brain_context.load_brain_docs()
    wiki_snippets = brain_context.load_wiki_snippets(threads)

    # PRIORITY NEEDS — Brian-curated registry. Highest-priority lens.
    needs_registry = needs_lens.parse_registry()
    needs_ranked: list[dict] = []
    if needs_registry.available:
        for score, n in needs_lens.ranked_needs(needs_registry):
            needs_ranked.append({
                "slug": n.slug,
                "title": n.title,
                "state": n.state,
                "urgency": n.urgency,
                "domain": n.domain,
                "next_step": n.next_step,
                "blockers": n.blockers,
                "last_movement": n.last_movement,
                "score": score,
            })

    # Live events from Mac/cloud sources. Each adapter degrades gracefully:
    # on failure, returns a one-item list with an `error` key that gets
    # passed through to the prompt so Claude knows the source is unavailable.
    realtime: list[dict] = []
    try:
        realtime.extend(imessage.recent_events(hours=24, limit=60))
    except Exception as e:
        realtime.append({"source": "imessage", "error": f"adapter exception: {e}"})
    try:
        realtime.extend(cal_adapter.upcoming_events(hours=72))
    except Exception as e:
        realtime.append({"source": "calendar", "error": f"adapter exception: {e}"})
    try:
        realtime.extend(gmail.recent_emails(hours=24, limit=30))
    except Exception as e:
        realtime.append({"source": "gmail", "error": f"adapter exception: {e}"})

    return {
        "threads": threads,
        "brain_docs": brain_docs,
        "wiki_snippets": wiki_snippets,
        "realtime": realtime,
        "needs_registry": needs_registry,
        "needs_ranked": needs_ranked,
    }


def gather_recent_decisions(conn: sqlite3.Connection, n: int = RECENT_DECISIONS_N) -> list[dict]:
    cur = conn.execute(
        """
        SELECT tick_ts, sent, title, body, priority, user_response, response_at, not_sent_reason, reasoning
        FROM notification_log ORDER BY id DESC LIMIT ?
        """,
        (n,),
    )
    return [dict(row) for row in cur.fetchall()]


# ── Cooldown ────────────────────────────────────────────────────────────

def in_cooldown(conn: sqlite3.Connection, hours: float = COOLDOWN_HOURS) -> bool:
    cur = conn.execute(
        "SELECT tick_ts FROM notification_log WHERE sent=1 ORDER BY id DESC LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        return False
    try:
        last = datetime.fromisoformat(row["tick_ts"])
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - last) < timedelta(hours=hours)


# ── Prompt build ───────────────────────────────────────────────────────

DECIDE_PROMPT = """\
You are MIKAI, Brian's notification decider. Your job this tick: decide whether anything in Brian's life is worth interrupting him about RIGHT NOW. Default is SILENCE. An interruption costs Brian attention; send only when a nudge would change what he does today. When you do send, send 1 to {slate_max} distinct notifications, each picking up a real thread at the exact decision point he last paused on.

CURRENT TIME: {now} (UTC), {weekday}, hour {hour} UTC

== TOP-TIER — Brian's declared life-tier themes (OUTRANKS ontology ordering) ==
{life_tier_content}

== FRAME — Brian's life-dimensions ontology ==
Below is Brian's personal ontology: 9 dimensions of his life. Use it to classify
each candidate (the `dimension` field) and to keep a multi-item slate from
stacking under one dimension. Dimension 1 (AI Career / MIKAI Build) is mostly
tooling noise: do NOT surface MIKAI/Claude Code/infra items unless a CONCRETE
decision point crystallizes (founder-vs-employee commitment, ship milestone,
funding move).

{dimensions_content}

== PRIMARY LENS — Brian's threads (task-state files, ~/.mikai/brain/threads) ==
Each thread is something Brian is actively carrying, with its current state
(exploring → evaluating → decided → acting → stalled → completed), when that
state began, when it last moved, and its next step. Ordered quietest-first.
These are the canonical surfacing candidates. Cite them by slug.

{threads_summary}

== PRIORITIES — BRAIN.md / GOALS.md / USER_MODEL.md (hand-maintained) ==
{brain_docs_summary}

== WIKI CONTEXT — knowledge pages linked from the threads (read-only) ==
Supporting detail only. Cite a page by the slug in brackets, e.g. [entities/germaine].
{wiki_snippets_summary}

== Brian-curated PRIORITY NEEDS ==
Hand-curated load-bearing needs (financial admin, health admin, career decisions)
that may not show up in his conversations. Eligible alongside threads.

NEEDS REGISTRY (ranked by state × urgency × tension × detail):
{needs_summary}

== LIVE EVENTS FROM SOURCES (iMessage / Calendar / Gmail, last 24-72h) ==
{realtime_summary}

BRIAN'S RECENT NOTIFICATIONS AND HIS RESPONSES (newest first):
{recent_decisions_summary}

RULES YOU MUST FOLLOW:

1. **Default to silence.** Return zero notifications unless an item clears the bar in rule 2. Newsletters, marketing email, auto-receipts, system messages and meta-references to MIKAI itself are never worth an interruption. Silence is a correct, common answer.

2. **The 4-factor bar.** surface_priority = thread_state × staleness × delivery_value × delivery_cost⁻¹
   - thread_state: stalled > acting with a due next_step > evaluating > exploring. Completed threads are never surfaced.
   - staleness: a thread quiet for days with an unresolved next_step is the canonical MIKAI case ("you started this and never followed through").
   - delivery_value: would surfacing this CHANGE what Brian does today? An acting thread with fresh momentum = low value (he's on it).
   - delivery_cost⁻¹: time of day (workday = higher bar) and recent responses (never repeat a topic he ignored or dismissed recently).

3. **Thread files are the source of truth.** If a live event or wiki page disagrees with a thread file's state or next_step, trust the thread file.

4. **Pick up the conversation. Don't open a new one.** For every notification:
   (a) identify the decision point Brian last paused at (the thread's next_step and state are your ground truth);
   (b) write the body so it RESUMES from that point, not from the topic in general.
   - BAD: "Proposal planning — still open?" (vague, no pickup)
   - GOOD: "Venue shortlist never started. Pick 2-3 candidates tonight and check her availability for each." (exact unresolved beat + smallest next move)
   If you can't name a concrete decision point, skip the item.

5. **Diversify a multi-item slate.** At most 1 notification per thread_slug and per needs_slug, and no more than 2 items from the same dimension.

6. **Time of day matters.** UTC hour {hour}; Brian is typically Pacific. Late night = only time-sensitive items. Morning = the best window for at most {slate_max}.

7. **Voice:** brief, Brian-voiced, second-person, present-tense. NOT: "There is an outstanding response required for the Kenya thread."

8. **Citation:** every notification must cite at least one thread slug, wiki slug or needs slug in `evidence`, exactly as shown above. Never invent a slug; uncited or unknown slugs fail validation.

9. **Classify then route.** For every notification, name the `action_type`, then choose `next_step_url` for that type.

Action types (pick exactly one per notification):
- `transaction` — do it inside a specific portal
- `communication` — send a message to a specific person (email draft, iMessage draft)
- `search` — the pickup is "look up more info"
- `capture` — add a calendar event / log a decision
- `decision` — the action is thinking; the destination is a calendar time-block carrying the context bundle
- `physical` — offline action
- `user_response` — Brian's own meta-action on a prior notification

Routing by action_type:
(a) `transaction` → a deep-link portal URL from DIMENSIONS.md's Per-Dimension Destination Templates.
(b) `communication` → `googlegmail://co?to=<addr>&subject=<url-encoded>&body=<url-encoded>` draft. For iMessage: `sms:<phone>&body=<url-encoded>`.
(c) `search` → `https://www.perplexity.ai/search?q=<url-encoded query>`.
(d) `capture` → Google Calendar quick-add URL with `text=`, `dates=` (30-min block in the next 3-5 days) and a brief `details=`.
(e) `decision` → Google Calendar quick-add URL whose `details=` is the full context bundle: the thread's state and next_step, up to 5 prior beats, and 3-5 research URLs.
(f) `physical` → `next_step_url: null` (or `tel:+1...` for a call).
(g) `user_response` → `next_step_url: null`.
Never invent URLs — use only DIMENSIONS.md templates or well-known schemes.

OUTPUT FORMAT: Return STRICTLY valid JSON, no markdown code fence, no commentary. Just the JSON object:

{{
  "notifications": [
    {{
      "title": "<<= 55 chars; topic + state, not a question>",
      "body": "<<= 220 chars; last beat in 4-10 words, then the concrete pickup move in 8-20 words>",
      "priority": "passive|active|timeSensitive",
      "decision_point": "<one sentence: the EXACT unresolved question or choice Brian last paused at>",
      "evidence": ["<thread slug | wiki slug like entities/germaine | needs slug>", ...],
      "thread_slug": "<thread slug from PRIMARY LENS if applicable, else null>",
      "needs_slug": "<needs registry slug if applicable, else null>",
      "action_type": "<transaction | communication | search | capture | decision | physical | user_response>",
      "next_step_url": "<URL routed by action_type; null only for physical/user_response>",
      "dimension": "<dim_1 .. dim_9>",
      "reasoning": "<one sentence: why this item, why now, naming the 4 factors>"
    }}
  ],
  "silent_reason": "<required when notifications is empty: one sentence on why silence is right>",
  "considered": [
    {{"slug": "...", "rank": 1, "source": "thread|needs|wiki|live", "selected": true, "note": "..."}}
  ]
}}

REQUIRED: "considered" lists every thread slug and needs slug you ranked, selected or not, in priority order with a 1-line note each. This is how the Surface Engine audits coverage.
"""


def build_prompt(context: dict, recent_decisions: list[dict]) -> str:
    now = datetime.now(timezone.utc)
    return DECIDE_PROMPT.format(
        now=now.isoformat(timespec="minutes"),
        weekday=now.strftime("%A"),
        hour=now.hour,
        slate_max=SLATE_MAX,
        threads_summary=format_threads(context.get("threads", [])),
        brain_docs_summary=format_brain_docs(context.get("brain_docs", {})),
        wiki_snippets_summary=format_wiki_snippets(context.get("wiki_snippets", [])),
        realtime_summary=format_realtime(context.get("realtime", [])),
        recent_decisions_summary=format_decisions(recent_decisions),
        needs_summary=format_needs(context.get("needs_ranked", []), context.get("needs_registry")),
        dimensions_content=load_dimensions(),
        life_tier_content=load_life_tier(),
    )


def format_needs(ranked: list[dict], registry) -> str:
    if not registry or not getattr(registry, "available", False):
        return "(needs registry not available — docs/USER_NEEDS_REGISTRY.md missing or unparsable)"
    if not ranked:
        return "(no live needs — all marked done?)"
    lines = []
    for n in ranked:
        lines.append(
            f"- [{n['slug']}] state={n['state']} urgency={n['urgency']} "
            f"domain={n['domain']} score={n['score']:.2f}: {n['title']}"
        )
        if n.get("next_step"):
            lines.append(f"     next_step: {n['next_step'][:240]}")
        if n.get("blockers"):
            blockers = " ".join(n["blockers"].split())
            lines.append(f"     blockers: {blockers[:240]}")
        if n.get("last_movement"):
            lines.append(f"     last_movement: {n['last_movement']}")
    return "\n".join(lines)


def format_threads(threads: list) -> str:
    if not threads:
        return "(no thread files found — check MIKAI_BRAIN_ROOT/threads)"
    lines = []
    for t in threads:
        quiet = t.days_quiet()
        quiet_tag = f"quiet {quiet}d" if quiet is not None else "last activity unknown"
        lines.append(
            f"- [{t.slug}] state={t.state} since={t.state_since or '?'} "
            f"({quiet_tag}) dept={t.department or '?'}: {t.title}"
        )
        if t.next_step:
            lines.append(f"     next_step: {t.next_step[:240]}")
        if t.entities:
            lines.append(f"     entities: {', '.join(t.entities)}")
        body = " ".join((t.body or "").split())
        if body:
            lines.append(f"     context: {body[:400]}")
    return "\n".join(lines)


def format_brain_docs(docs: dict) -> str:
    if not docs:
        return "(no BRAIN.md / GOALS.md / USER_MODEL.md found)"
    return "\n\n".join(f"--- {name} ---\n{text.strip()}" for name, text in docs.items())


def format_wiki_snippets(snippets: list) -> str:
    if not snippets:
        return "(no wiki pages linked from current threads)"
    return "\n".join(
        f"- [{w['slug']}] (thread {w['thread']}) {w['title']}: {w['snippet']}"
        for w in snippets
    )


def format_realtime(events: list[dict]) -> str:
    if not events:
        return "(no live events — adapters returned nothing)"
    by_source: dict[str, list[dict]] = {}
    for e in events:
        by_source.setdefault(e.get("source", "unknown"), []).append(e)

    out = []
    for src, items in by_source.items():
        # Adapter errors get their own line
        errors = [i for i in items if i.get("error")]
        good = [i for i in items if not i.get("error")]
        if errors:
            out.append(f"  {src}: ⚠ adapter error: {errors[0]['error'][:200]}")
            continue
        if not good:
            out.append(f"  {src}: (none)")
            continue

        out.append(f"  {src} ({len(good)}):")
        for i in good[:12]:
            if src == "imessage":
                action = " [unread, action-required]" if i.get("is_action_required") else ""
                chat = i.get("chat", "?")
                sender = i.get("sender", "?")
                content = (i.get("content") or "").replace("\n", " ")[:160]
                ts = i.get("timestamp", "?")
                out.append(f"    - {ts} [{chat}] {sender}: {content}{action}")
            elif src == "calendar":
                when = i.get("when", "?")
                title = i.get("title", "?")
                out.append(f"    - {when} :: {title}")
            elif src == "gmail":
                unread = " [UNREAD]" if i.get("is_unread") else ""
                sender = (i.get("sender") or "?")[:60]
                subject = (i.get("subject") or "?")[:90]
                ts = i.get("timestamp", "?")
                out.append(f"    - {ts} {sender} → \"{subject}\"{unread}")
            else:
                out.append(f"    - {json.dumps(i)[:200]}")
        if len(good) > 12:
            out.append(f"    ... and {len(good) - 12} more")
    return "\n".join(out) if out else "(empty)"


def format_decisions(decisions: list[dict]) -> str:
    if not decisions:
        return "(no prior decisions logged — this is Brian's first tick)"
    lines = []
    for d in decisions:
        ts_raw = d.get("tick_ts") or "?"
        ts = ts_raw[:16] if isinstance(ts_raw, str) else "?"
        if d.get("sent"):
            resp = d.get("user_response") or "@no_response_yet"
            title = (d.get("title") or "").strip()
            lines.append(f"- {ts} SENT \"{title}\" -> {resp}")
        else:
            reason = d.get("not_sent_reason") or d.get("reasoning") or "silence"
            lines.append(f"- {ts} SILENT ({reason})")
    return "\n".join(lines)


# ── Claude invocation ──────────────────────────────────────────────────

# tier=interactive: the decide tick drafts user-facing notification copy —
# best-model territory. Already claude -p before the shim existed; routing
# through mikai_llm centralizes provider policy (and the shim strips
# ANTHROPIC_API_KEY from the subprocess env, which the launchd runner
# previously had to do by hand).
def invoke_claude(prompt: str) -> str | None:
    try:
        from infra.mikai_llm import chat as _chat
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from infra.mikai_llm import chat as _chat
    try:
        return _chat(prompt, tier="interactive", timeout=CLAUDE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        print(f"ERROR: LLM call timed out after {CLAUDE_TIMEOUT_S}s", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR: LLM call failed: {e}", file=sys.stderr)
        return None


def parse_decision(raw: str) -> dict | None:
    """Parse Claude's response. Tolerant of markdown code fences and preamble."""
    if not raw:
        return None
    s = raw.strip()

    # Strip markdown code fences if present
    if s.startswith("```"):
        first_newline = s.find("\n")
        if first_newline > -1:
            s = s[first_newline + 1:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()

    # Find the first { and last } and extract the JSON object
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end < start:
        print(f"ERROR: No JSON object found in response", file=sys.stderr)
        print(f"--- raw ---\n{raw[:1000]}\n---", file=sys.stderr)
        return None
    candidate = s[start:end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON parse failed: {e}", file=sys.stderr)
        print(f"--- candidate ---\n{candidate[:1000]}\n---", file=sys.stderr)
        return None


# ── Validation ─────────────────────────────────────────────────────────

VALID_PRIORITIES = {"passive", "active", "timeSensitive", "critical"}

SLATE_MAX = 3


def normalize_decision(decision: dict | None) -> dict | None:
    """Coerce legacy single-shape output into the new list-shape so dispatch
    has one path. Returns the normalized dict or None if the input is junk.

    Legacy single shape: {"send": bool, "title": ..., "body": ..., ...}
    New shape:           {"notifications": [...], "silent_reason": ..., "considered": [...]}
    """
    if not isinstance(decision, dict):
        return None

    if "notifications" in decision:
        if not isinstance(decision["notifications"], list):
            return None
        return decision

    # Legacy fallback — wrap a single send/silent into the new shape.
    if decision.get("send") is True:
        single = {k: decision.get(k) for k in (
            "title", "body", "priority", "decision_point",
            "evidence", "evidence_edge_uuids", "thread_slug", "wiki_thread_slug",
            "needs_slug", "next_step_url", "action_type", "reasoning",
        )}
        return {
            "notifications": [single],
            "silent_reason": None,
            "considered": decision.get("considered", []),
        }
    if decision.get("send") is False:
        return {
            "notifications": [],
            "silent_reason": decision.get("reasoning") or "legacy silent",
            "considered": decision.get("considered", []),
        }
    return None


def notif_evidence(n: dict) -> list:
    """Citations for a notification. `evidence` is current; the older
    `evidence_edge_uuids` name is still accepted from cached/legacy output."""
    cites = n.get("evidence")
    if cites is None:
        cites = n.get("evidence_edge_uuids")
    if isinstance(cites, str):
        cites = [cites]
    return [str(c) for c in (cites or []) if str(c).strip()]


def notif_thread_slug(n: dict) -> str | None:
    return n.get("thread_slug") or n.get("wiki_thread_slug") or None


def _known_slugs(context: dict) -> set:
    """Slugs that were in the prompt but don't live on disk as thread/wiki
    files (the needs registry is a doc, not per-slug files)."""
    return {n["slug"] for n in (context.get("needs_ranked") or []) if n.get("slug")}


def validate_decision(decision: dict | None, context: dict) -> tuple[bool, str]:
    if not isinstance(decision, dict):
        return False, "decision is not a dict"
    if "notifications" not in decision:
        return False, "missing 'notifications' field (post-normalization)"
    notifs = decision["notifications"]
    if not isinstance(notifs, list):
        return False, "'notifications' must be a list"

    if len(notifs) == 0:
        if not decision.get("silent_reason"):
            return False, "empty notifications requires silent_reason"
        return True, "silent ok"

    if len(notifs) > SLATE_MAX:
        return False, f"too many notifications ({len(notifs)} > {SLATE_MAX})"

    known = _known_slugs(context)
    thread_slugs = set()
    needs_slugs = set()

    for i, n in enumerate(notifs):
        if not isinstance(n, dict):
            return False, f"notification[{i}] is not a dict"
        for field in ("title", "body", "priority", "decision_point"):
            if not n.get(field):
                return False, f"notification[{i}] missing required field: {field}"
        if n["priority"] not in VALID_PRIORITIES:
            return False, f"notification[{i}] invalid priority: {n['priority']}"
        if len(n["title"]) > 80:
            return False, f"notification[{i}] title too long ({len(n['title'])} > 80)"
        if len(n["body"]) > 300:
            return False, f"notification[{i}] body too long ({len(n['body'])} > 300)"

        ts = notif_thread_slug(n)
        if ts:
            if ts in thread_slugs:
                return False, f"notification[{i}] duplicate thread_slug '{ts}'"
            if not brain_context.citation_exists(ts):
                return False, f"notification[{i}] thread_slug '{ts}' has no thread file"
            thread_slugs.add(ts)
        ns = n.get("needs_slug")
        if ns:
            if ns in needs_slugs:
                return False, f"notification[{i}] duplicate needs_slug '{ns}'"
            if ns not in known:
                return False, f"notification[{i}] needs_slug '{ns}' not in registry"
            needs_slugs.add(ns)

        # Citations must resolve to a thread file or wiki page on disk, or a
        # needs-registry slug that was in the prompt. No citation = no send.
        cites = notif_evidence(n)
        if not cites:
            return False, f"notification[{i}] cites no evidence"
        for c in cites:
            if c not in known and not brain_context.citation_exists(c):
                return False, f"notification[{i}] cited evidence '{c}' not found on disk"

    return True, "ok"


# ── Feedback loop primitives ───────────────────────────────────────────
#
# Every dispatched notification carries a short `notif_id` (12-char uuid).
# The ntfy Click URL is rewritten from the raw destination
# (e.g. https://mail.google.com/...) to `${TAP_BASE_URL}/t/${notif_id}`
# so we can log the TAPPED event before 302-ing to the real URL.
# The raw URL never leaves the local DB.
#
# If TAP_BASE_URL is empty (no tunnel running yet), we fall back to the
# raw URL — the feedback loop is off but the notification still works.


def new_notif_id() -> str:
    return uuid.uuid4().hex[:12]


# Match "dim 3", "dim_3", "dimension 3", "dim-3" — the LLM tends to phrase
# dimensions loosely in reasoning even when the explicit field is empty.
_DIM_RE = re.compile(r"\bdim(?:ension)?[\s_\-]*([1-9])\b", re.IGNORECASE)


def infer_dimension(notif: dict) -> str | None:
    """Return the life-dimension slug (dim_1..dim_9) for a notification,
    or None. Prefers the explicit `dimension` field; falls back to a
    regex over `reasoning` for the tail case where the LLM omitted it.
    """
    explicit = (notif.get("dimension") or "").strip().lower()
    if explicit.startswith("dim_") or explicit.startswith("dim-"):
        # Normalize to dim_N form.
        digits = "".join(c for c in explicit if c.isdigit())
        if digits:
            return f"dim_{digits}"
    m = _DIM_RE.search(notif.get("reasoning", "") or "")
    if m:
        return f"dim_{m.group(1)}"
    return None


def build_tap_url(notif_id: str, real_url: str) -> str:
    """Wrap real_url in the tap-redirect endpoint, or return raw if no base."""
    base = resolve_tap_base_url()
    if not base:
        return real_url
    return f"{base}/t/{notif_id}"


def log_sent_event(
    conn: sqlite3.Connection,
    notif_id: str,
    notif: dict,
    real_url: str | None,
) -> None:
    """Insert a SENT event. Called BEFORE ntfy dispatch so a crash mid-loop
    still leaves a redirectable row — a stale SENT is a rare, self-heals via
    DISMISSED_INFERRED at 24h.
    """
    conn.execute(
        """
        INSERT INTO notification_events
            (notif_id, event_type, event_ts, dimension, action_type,
             source_ids, next_step_url)
        VALUES (?, 'SENT', ?, ?, ?, ?, ?)
        """,
        (
            notif_id,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            infer_dimension(notif),
            notif.get("action_type"),
            json.dumps(notif_evidence(notif)),
            real_url,
        ),
    )
    conn.commit()


# ── ntfy dispatch ──────────────────────────────────────────────────────

# ntfy priority levels: 1 (min) to 5 (max); default 3
NTFY_PRIORITY_MAP = {
    "passive": "2",
    "active": "3",
    "timeSensitive": "4",
    "critical": "5",
}


def dispatch_via_ntfy(
    title: str,
    body: str,
    priority: str = "active",
    next_step_url: str | None = None,
) -> tuple[bool, str]:
    if not NTFY_TOPIC:
        return False, "MIKAI_NTFY_TOPIC env var not set"

    url = f"{NTFY_BASE_URL}/{NTFY_TOPIC}"
    ntfy_priority = NTFY_PRIORITY_MAP.get(priority, "3")

    # Title and Tags must be ASCII-safe header values. ntfy supports UTF-8 in
    # the body. For the title, fall back to a stripped variant if it has
    # non-ASCII chars.
    try:
        title.encode("ascii")
        title_for_header = title
    except UnicodeEncodeError:
        title_for_header = title.encode("ascii", errors="replace").decode("ascii")

    headers = {
        "Title": title_for_header,
        "Priority": ntfy_priority,
        "Tags": "mikai",
    }
    # Click header — the URL the notification opens when tapped. ntfy passes
    # this through to the iOS/Android app which then hands it to the OS.
    # Must be ASCII-safe. Skip if URL contains characters ntfy rejects
    # (they'd trigger a 400 and drop the whole notification).
    if next_step_url:
        try:
            next_step_url.encode("ascii")
            headers["Click"] = next_step_url
        except UnicodeEncodeError:
            pass  # silently drop malformed URL rather than fail the send

    req = urlreq.Request(
        url,
        data=body.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlreq.urlopen(req, timeout=10) as resp:
            return True, f"http_{resp.status}"
    except Exception as e:
        return False, f"ntfy_error: {e}"


def send_imessage_copy(notif: dict, notif_id: str) -> tuple[bool, str]:
    """Mirror a notification to iMessage via Hermes. Returns (ok, status);
    status is "off" when MIKAI_IMESSAGE is unset. Never raises."""
    if not imessage_dispatch.imessage_enabled():
        return False, "off"
    text = imessage_dispatch.format_message(notif["title"], notif["body"], notif_id)
    ok, status = imessage_dispatch.send(text)
    if ok:
        try:
            imessage_dispatch.record_outbox(DB_PATH, notif_id, text)
        except Exception as e:
            print(f"WARN: imessage sent but outbox write failed for {notif_id}: {e}", file=sys.stderr)
    return ok, status


# ── Logging helpers ────────────────────────────────────────────────────

def log_silent(conn: sqlite3.Connection, tick_ts: str, prompt: str,
               decision: dict | None, reason: str) -> None:
    conn.execute(
        """
        INSERT INTO notification_log
            (tick_ts, prompt_hash, decision_json, sent, not_sent_reason, reasoning)
        VALUES (?, ?, ?, 0, ?, ?)
        """,
        (
            tick_ts,
            hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
            json.dumps(decision) if decision else None,
            reason,
            (decision or {}).get("reasoning", ""),
        ),
    )
    conn.commit()


def log_sent(conn: sqlite3.Connection, tick_ts: str, prompt: str,
             notif: dict, slate_index: int, slate_size: int,
             notif_id: str | None = None,
             imessage_status: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO notification_log
            (tick_ts, prompt_hash, decision_json, sent, title, body, priority,
             evidence_edge_uuids, reasoning, decision_point,
             slate_index, slate_size, next_step_url, action_type, notif_id,
             candidate_source, candidate_slug, imessage_status)
        VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tick_ts,
            hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
            json.dumps(notif),
            notif["title"],
            notif["body"],
            notif["priority"],
            json.dumps(notif_evidence(notif)),
            notif.get("reasoning", ""),
            notif.get("decision_point", ""),
            slate_index,
            slate_size,
            notif.get("next_step_url"),
            notif.get("action_type"),
            notif_id,
            "thread" if notif_thread_slug(notif) else ("needs" if notif.get("needs_slug") else None),
            notif_thread_slug(notif) or notif.get("needs_slug"),
            imessage_status,
        ),
    )
    conn.commit()


# ── Main ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="MIKAI notification decider tick")
    parser.add_argument("--init", action="store_true",
                        help="Initialize SQLite schema and exit")
    parser.add_argument("--test-ntfy", action="store_true",
                        help="Send a static test notification to verify ntfy path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build prompt + show decision, but don't dispatch or log")
    parser.add_argument("--force", action="store_true",
                        help="Ignore cooldown")
    parser.add_argument("--show-prompt", action="store_true",
                        help="Print the full prompt before invoking Claude")
    parser.add_argument("--show-slate", action="store_true",
                        help="Print the candidate slate (needs + wiki + lenses) WITHOUT invoking Claude. Pure diagnostic.")
    parser.add_argument("--write-brief", action="store_true",
                        help="Write today's MIKAI brief into macOS Calendar with the top 3 candidates")
    args = parser.parse_args()

    # Surface Engine toggle (formerly FIGS).
    # Unattended dispatches are OFF by default — MIKAI stays silent until Brian
    # turns Surface on. Interactive diagnostics still work.
    # To enable: `export MIKAI_SURFACE_ENABLED=1` in ~/.mikai/launchd.env, then
    # `launchctl kickstart -k gui/$(id -u)/com.mikai.figs-decide`.
    _diagnostic = any([args.init, args.test_ntfy, args.dry_run,
                       args.show_prompt, args.show_slate, args.force])
    _enabled = os.environ.get("MIKAI_SURFACE_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
    if not _enabled and not _diagnostic:
        print("Surface Engine disabled — set MIKAI_SURFACE_ENABLED=1 to enable "
              "(or pass --dry-run / --force / --show-slate for diagnostics).")
        return 0

    conn = db_connect()

    if args.init:
        print(f"OK: SQLite schema initialized at {DB_PATH}")
        return 0

    if args.test_ntfy:
        if not NTFY_TOPIC:
            print("ERROR: set MIKAI_NTFY_TOPIC first.", file=sys.stderr)
            return 2
        print(f"Sending test notification to ntfy topic '{NTFY_TOPIC}'...")
        ok, msg = dispatch_via_ntfy(
            "MIKAI test",
            "If you see this on iPhone or Mac, ntfy is working. Swipe to dismiss.",
            "passive",
        )
        if ok:
            print(f"✓ Sent: {msg}")
            return 0
        else:
            print(f"✗ Failed: {msg}", file=sys.stderr)
            return 1

    if args.show_slate:
        # Pure diagnostic — show the full candidate slate without invoking Claude.
        print("=== FIGS candidate slate ===")
        print(f"  (date: {datetime.now(timezone.utc).isoformat(timespec='minutes')})")
        print()
        context = gather_context()
        print(f"--- Threads ({len(context['threads'])}) ---")
        for t in context["threads"]:
            quiet = t.days_quiet()
            print(f"  [{t.state:<10}] quiet {quiet if quiet is not None else '?'}d  {t.title}")
            if t.next_step:
                print(f"        next: {t.next_step[:120]}")
        print()
        print(f"--- Needs Registry ({len(context.get('needs_ranked', []))}) ---")
        for n in context.get("needs_ranked", []):
            print(f"  {n['score']:.2f} [{n['state']:<10}/{n['urgency']:<8}] {n['title']}")
        print()
        print(f"--- Wiki pages linked from threads ({len(context['wiki_snippets'])}) ---")
        for w in context["wiki_snippets"]:
            print(f"  [{w['slug']}] for {w['thread']}: {w['title']}")
        print()
        print(f"--- Live events (iMessage/Calendar/Gmail): {len(context.get('realtime', []))} items ---")
        for src in ("imessage", "calendar", "gmail"):
            items = [e for e in context.get("realtime", []) if e.get("source") == src]
            print(f"  {src}: {len(items)} items")
        print()
        recent = gather_recent_decisions(conn, n=10)
        print(f"--- Recent decisions (last {len(recent)}) ---")
        for d in recent:
            status = "SENT" if d.get("sent") else "silent"
            resp = d.get("user_response") or "—"
            print(f"  {(d.get('tick_ts') or '')[:16]} {status:<6} {resp:<8} {(d.get('title') or '—')[:60]}")
        return 0

    if args.write_brief:
        print("=== Writing MIKAI brief to macOS Calendar ===")
        context = gather_context()
        # Build top-3 from needs (highest priority) then fill from wiki if needed
        top3 = []
        for n in context.get("needs_ranked", [])[:3]:
            top3.append({
                "title": n["title"],
                "next_step": n.get("next_step", ""),
                "source": "need",
            })
        if len(top3) < 3:
            for t in context.get("threads", []):
                if len(top3) >= 3:
                    break
                if t.state in brain_context.CLOSED_STATES:
                    continue
                top3.append({
                    "title": t.title,
                    "next_step": t.next_step[:200],
                    "source": "thread",
                })
        if not top3:
            print("(no candidates to brief)")
            return 1
        ok, msg = dispatch_calendar.write_daily_brief(top3)
        print(f"{'✓' if ok else '✗'} {msg}")
        return 0 if ok else 1

    now_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Cooldown
    if not args.force and not args.dry_run and in_cooldown(conn):
        reason = f"cooldown ({COOLDOWN_HOURS}h since last send)"
        conn.execute(
            "INSERT INTO notification_log (tick_ts, sent, not_sent_reason) VALUES (?, 0, ?)",
            (now_ts, reason),
        )
        conn.commit()
        print(f"COOLDOWN: {reason}")
        return 0

    # Context
    print("Reading context from thread files + wiki…")
    context = gather_context()
    print(f"  threads: {len(context['threads'])} "
          f"(brain root {brain_context.brain_root()}), "
          f"wiki pages: {len(context['wiki_snippets'])}")
    recent = gather_recent_decisions(conn)
    print(f"  log: {len(recent)} prior decisions")

    prompt = build_prompt(context, recent)
    if args.show_prompt or args.dry_run:
        print("\n=== PROMPT START ===")
        print(prompt)
        print("=== PROMPT END ===\n")

    # Claude
    print("Invoking Claude (this can take up to a minute)…")
    raw = invoke_claude(prompt)
    if raw is None:
        print("FAILED: Claude invocation failed", file=sys.stderr)
        if not args.dry_run:
            log_silent(conn, now_ts, prompt, None, "claude_invocation_failed")
        return 1

    decision = parse_decision(raw)
    if decision is None:
        print("FAILED: Could not parse decision", file=sys.stderr)
        if not args.dry_run:
            log_silent(conn, now_ts, prompt, {"raw": raw[:500]}, "parse_failed")
        return 1

    decision = normalize_decision(decision)
    if decision is None:
        print("FAILED: Could not normalize decision into slate shape", file=sys.stderr)
        if not args.dry_run:
            log_silent(conn, now_ts, prompt, {"raw": raw[:500]}, "normalize_failed")
        return 1

    print(f"DECISION:\n{json.dumps(decision, indent=2)}")

    # Validate
    ok, msg = validate_decision(decision, context)
    if not ok:
        print(f"VALIDATION FAILED: {msg}", file=sys.stderr)
        if not args.dry_run:
            log_silent(conn, now_ts, prompt, decision, f"validation_failed: {msg}")
        return 1

    notifs = decision["notifications"]

    if not notifs:
        if not args.dry_run:
            log_silent(conn, now_ts, prompt, decision,
                       f"llm_chose_silent: {decision.get('silent_reason', '')}")
        print(f"SILENT (all): {decision.get('silent_reason', '(no reason)')}")
        return 0

    if args.dry_run:
        for i, n in enumerate(notifs):
            print(f"DRY-RUN [{i+1}/{len(notifs)}]: title='{n['title']}', "
                  f"body='{n['body']}', priority={n['priority']}")
            print(f"                evidence: {notif_evidence(n)}")
            print(f"                action_type: {n.get('action_type', '?')}")
            print(f"                decision_point: {n.get('decision_point', '')}")
            print(f"                next_step_url: {n.get('next_step_url')}")
        return 0

    print(f"Dispatching {len(notifs)} notification(s) via ntfy ('{NTFY_TOPIC}')…")
    slate_size = len(notifs)
    fail_count = 0

    tap_base = resolve_tap_base_url()
    if not tap_base:
        print("NOTE: MIKAI_TAP_BASE_URL not set — feedback loop OFF; "
              "ntfy will get raw next_step_url (no TAPPED tracking).",
              file=sys.stderr)

    for i, n in enumerate(notifs):
        notif_id = new_notif_id()
        real_url = n.get("next_step_url") or None
        # Log SENT before dispatch so the redirect can serve the tap even
        # if we crash between here and log_sent below.
        if real_url:
            log_sent_event(conn, notif_id, n, real_url)
        dispatch_url = build_tap_url(notif_id, real_url) if real_url else None

        sent_ok, dispatch_msg = dispatch_via_ntfy(
            n["title"], n["body"], n["priority"],
            next_step_url=dispatch_url,
        )
        imessage_ok, imessage_status = send_imessage_copy(n, notif_id)
        if not imessage_ok and imessage_status != "off":
            print(f"  ✗ [{i+1}/{slate_size}] iMessage FAILED (notif_id={notif_id}): "
                  f"{imessage_status}", file=sys.stderr)
        if sent_ok or imessage_ok:
            if not sent_ok:
                imessage_status = f"{imessage_status} (ntfy failed: {dispatch_msg})"
                print(f"  ⚠ [{i+1}/{slate_size}] ntfy FAILED, delivered by iMessage only: "
                      f"{dispatch_msg}", file=sys.stderr)
            log_sent(conn, now_ts, prompt, n, slate_index=i,
                     slate_size=slate_size, notif_id=notif_id,
                     imessage_status=imessage_status)
            print(f"  ✓ [{i+1}/{slate_size}] SENT: {n['title']} "
                  f"(notif_id={notif_id}, imessage={imessage_status})")
        else:
            log_silent(conn, now_ts, prompt, n,
                       f"dispatch_failed: {dispatch_msg}; imessage: {imessage_status}")
            print(f"  ✗ [{i+1}/{slate_size}] FAILED: {dispatch_msg}", file=sys.stderr)
            fail_count += 1
        # iOS bundles APNs alerts that arrive in the same window. A small gap
        # keeps each notification visually distinct in Notification Center.
        if i < slate_size - 1:
            time.sleep(1.5)

    if fail_count == slate_size:
        print("✗ ALL DISPATCHES FAILED", file=sys.stderr)
        return 1
    if fail_count:
        print(f"⚠  {fail_count}/{slate_size} dispatches failed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
