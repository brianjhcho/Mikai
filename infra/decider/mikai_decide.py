#!/usr/bin/env python3
"""
mikai_decide.py — LLM-only notification decider for MIKAI.

Compatible with Python 3.8+.

Per tick:
  1. Pulls recent state from Graphiti at localhost:8100 (/search + /stats).
  2. Reads last N decisions from the local SQLite log.
  3. Asks Claude (via `claude -p`, Max-legitimate first-party OAuth) for a
     JSON decision: send-or-stay-silent.
  4. Validates the decision (evidence UUIDs exist, length bounds).
  5. If send: dispatches via ntfy.sh.
  6. Logs everything to ~/.mikai/notification_log.db.

Run modes:
  --init        Initialize the SQLite schema and exit
  --test-ntfy   Send a static test notification to ntfy. Verifies path. No Graphiti, no Claude.
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
import wiki_parser  # noqa: E402
import needs_lens  # noqa: E402
import dispatch_calendar  # noqa: E402

# Life-dimensions ontology (see docs/DIMENSIONS.md). Loaded verbatim into the
# prompt as the top-level frame — dimensions are the schema FIGS uses to
# route candidates into meaningful surfacing rather than flat-density rank.
DIMENSIONS_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "DIMENSIONS.md"

# Full-corpus ontology wiki (produced by full_corpus_dream.py on feat-dream-echoes).
# Persistent, LLM-synthesized narrative organized by DIMENSIONS.md schema.
# Overrides the incremental last-7d wiki as PRIMARY lens for FIGS candidates.
ONTOLOGY_WIKI_PATH = Path.home() / ".mikai" / "wiki" / "wiki-ontology-v1.md"


def load_dimensions() -> str:
    if not DIMENSIONS_PATH.exists():
        return "(DIMENSIONS.md not found — falling back to flat needs+wiki ranking)"
    return DIMENSIONS_PATH.read_text()


def load_ontology_wiki() -> str:
    if not ONTOLOGY_WIKI_PATH.exists():
        return "(ontology wiki not yet generated — run full_corpus_dream.py to seed it)"
    return ONTOLOGY_WIKI_PATH.read_text()


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
        "current period. Every FIGS tick MUST include at least one item from "
        "each theme when signal is available; when it isn't, name the theme "
        "and note it as stalled. These outrank the 9-dim ontology's raw "
        "ordering — dimensions are the classifier, top-tier is the ranker."
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

GRAPHITI_URL = os.environ.get("MIKAI_GRAPHITI_URL", "http://localhost:8100")
SIDECAR_TIMEOUT_S = 30

# Neo4j HTTP API — used for time-based queries the /search endpoint doesn't support.
# /search uses semantic similarity (no time awareness). Embeddings can't encode
# "what's new since yesterday" — that requires direct Cypher.
NEO4J_HTTP_URL = os.environ.get("MIKAI_NEO4J_HTTP", "http://localhost:7474")
NEO4J_USER = os.environ.get("MIKAI_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("MIKAI_NEO4J_PASSWORD", "mikai-local-dev")
NEO4J_TIMEOUT_S = 10

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

CLAUDE_TIMEOUT_S = 360  # bumped from 180 — full ontology wiki + graph context
                        # pushes the prompt to ~70K chars, which needs longer
                        # to process on the Claude Max / claude -p path

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


# ── Graphiti context ────────────────────────────────────────────────────

def graphiti_search(query: str, num_results: int = 10) -> list[dict]:
    payload = json.dumps({"query": query, "num_results": num_results}).encode()
    req = urlreq.Request(
        f"{GRAPHITI_URL}/search",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlreq.urlopen(req, timeout=SIDECAR_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"WARN: Graphiti search failed for '{query}': {e}", file=sys.stderr)
        return []


def graphiti_stats() -> dict:
    try:
        with urlreq.urlopen(f"{GRAPHITI_URL}/stats", timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"WARN: Graphiti stats failed: {e}", file=sys.stderr)
        return {}


def neo4j_query(cypher: str, params: dict | None = None) -> list[dict]:
    """Run a Cypher statement against Neo4j's HTTP transaction endpoint.

    Returns a list of {col: value, ...} dicts, one per row. On any error
    returns [] and logs to stderr — never raises.
    """
    payload = json.dumps({
        "statements": [{"statement": cypher, "parameters": params or {}}],
    }).encode()
    auth = base64.b64encode(f"{NEO4J_USER}:{NEO4J_PASSWORD}".encode()).decode()
    req = urlreq.Request(
        f"{NEO4J_HTTP_URL}/db/neo4j/tx/commit",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}",
        },
        method="POST",
    )
    try:
        with urlreq.urlopen(req, timeout=NEO4J_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"WARN: Neo4j query failed: {e}", file=sys.stderr)
        return []

    if data.get("errors"):
        print(f"WARN: Neo4j errors: {data['errors']}", file=sys.stderr)
        return []

    results = data.get("results", [])
    if not results:
        return []
    cols = results[0].get("columns", [])
    rows = results[0].get("data", [])
    return [dict(zip(cols, r["row"])) for r in rows]


# ── Multi-window candidate ranking ─────────────────────────────────────
#
# FIGS pulls candidates from layered time windows (24h / 7d / 30d) and
# ranks them by `recency × importance`. The wider windows give un-acted-on
# items (like a proposal-spot research thread started 5 days ago) a chance
# to surface alongside fresh content.
#
# Today: importance is a stub returning 1.0 — ranking is dominated by
# recency. This is the fix for the "24h window misses load-bearing
# older threads" problem.
#
# Tomorrow (O-049, wiki/dreaming consolidation): `importance_signal()`
# becomes a real function sourced from the consolidated user wiki and
# dreaming-curated memory. An edge connecting concepts the user has
# acted on, written about repeatedly, or that show up as wiki pages
# gets a high score. An edge between noise entities gets a low score.
# Fixed time windows go away — FIGS asks for "top-K candidates ranked
# by importance" and the curator decides what fits.
#
# When that lands, the swap point is `importance_signal()` and the
# weights in `_combined_score()`. Nothing else in FIGS changes.

RECENCY_WINDOWS = [
    # (label, lower_h, upper_h, limit) — DELTA ranges so each window
    # contributes distinct candidates. Without delta ranges, last_7d
    # would entirely overlap last_24h's top-N and add nothing after dedup.
    ("last_24h",  0,  24, 20),    # 0-24h ago: what just happened
    ("last_7d",   24, 168, 20),   # 1-7d ago: in flight, may be stalled
    ("last_30d",  168, 720, 10),  # 7-30d ago: still relevant background
]


def importance_signal(edge: dict) -> float:
    """STUB. Today returns 1.0 for everything.

    Future (O-049): reads from consolidated wiki / dreaming-curated
    memory. Returns 0.0–1.0 reflecting how load-bearing this edge is
    in the user's life. See module-level comment block above for the
    full migration plan.
    """
    return 1.0


def _recency_score(created_at_iso: str, now: datetime) -> float:
    """Logarithmic decay: 1h ago ≈ 1.0, 24h ≈ 0.65, 7d ≈ 0.30, 30d ≈ 0.0."""
    try:
        created = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return 0.0
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    age_hours = max(1.0, (now - created).total_seconds() / 3600.0)
    # log10(720) ≈ 2.857; anything older than 30d clamps to 0
    decay = math.log10(age_hours) / math.log10(720.0)
    return max(0.0, min(1.0, 1.0 - decay))


def _combined_score(edge: dict, now: datetime) -> float:
    """Combine recency + importance.

    Today's weights (recency-dominant because importance is a stub):
        score = 0.7 × recency + 0.3 × importance

    When `importance_signal()` returns real values, these weights
    rebalance — possibly inverting so older-but-important beats
    newer-but-trivial. The weights are tuneable here, not deep in
    the LLM prompt logic.
    """
    recency = _recency_score(edge.get("created_at", ""), now)
    importance = importance_signal(edge)
    return 0.7 * recency + 0.3 * importance


def graphiti_ranked_candidates(total_limit: int = 30) -> list[dict]:
    """Return ranked candidates from layered time windows.

    For each window: query Neo4j for edges created within that span,
    take top-N by created_at, dedupe by uuid across windows (a candidate
    that appears in last_24h also appears in last_7d — keep one copy
    with the closer window label).

    Then score every candidate by `_combined_score()` and sort. Return
    the top `total_limit`.

    This replaces the old single-window `graphiti_recent_edges(hours=24)`
    that buried older-but-still-relevant threads (proposal-spots research
    from 5 days ago, for example).
    """
    all_edges: dict[str, dict] = {}

    for window_label, lower_h, upper_h, limit in RECENCY_WINDOWS:
        cypher = """
            MATCH ()-[r:RELATES_TO]->()
            WHERE r.created_at >  datetime() - duration({hours: $upper})
              AND r.created_at <= datetime() - duration({hours: $lower})
            RETURN r.uuid AS uuid,
                   r.fact AS fact,
                   toString(r.created_at) AS created_at,
                   toString(r.valid_at) AS valid_at
            ORDER BY r.created_at DESC
            LIMIT $limit
        """
        rows = neo4j_query(cypher, {"lower": lower_h, "upper": upper_h, "limit": limit})
        for r in rows:
            uuid = r.get("uuid")
            if not uuid or uuid in all_edges:
                continue  # dedupe — should not happen with delta ranges, defensive
            all_edges[uuid] = {
                "uuid": uuid,
                "fact": r.get("fact") or "",
                "created_at": r.get("created_at") or "",
                "valid_at": r.get("valid_at") or r.get("created_at") or "",
                "_window": window_label,
            }

    now = datetime.now(timezone.utc)
    scored = []
    for edge in all_edges.values():
        edge["_score"] = _combined_score(edge, now)
        scored.append(edge)

    scored.sort(key=lambda e: e.get("_score", 0.0), reverse=True)
    return scored[:total_limit]


PERSONAL_LIFE_KEYWORDS = [
    # Engagement / proposal / wedding
    "proposal spot", "propose to", "engagement ring", "ring shopping",
    "wedding venue", "married", "marry her", "marry him",
    # Travel
    "flight to", "flight from", "trip to", "hotel in", "book a flight",
    "vacation", "travel to",
    # Health
    "doctor appointment", "surgery", "diagnosis", "specialist",
    # Major life decisions
    "job offer", "deadline", "interview at",
    # Specific places that anchor personal threads
    "denver", "red rocks",
]


# Exclude phrases — drop any candidate whose fact text contains any of these
# (case-insensitive). Catches MIKAI-internal noise that survives the keyword
# filter (e.g. "decision IDs ARCH-026", "FIGS depends on MIKAI").
PERSONAL_LIFE_EXCLUDES = [
    "mikai", "figs", "graphiti", "claude.ai", "claude-thread", "ingest",
    "decision id", "arch-", "d-05", "o-05", "o-04",
    "branch", "main's decisions", "node_operations", "neo4j",
    "uses decision", "memory architecture", "consolidation",
]


def graphiti_personal_life_edges(days: int = 30, limit: int = 15) -> list[dict]:
    """Pull edges containing personal-life keywords from the last N days.

    This is a TARGETED retrieval lens. The recency lens treats all edges equally,
    so dense recent conversation noise (architecture discussions, meta-edges)
    can crowd out a 44h-old proposal edge. This lens specifically searches for
    personal-life signal regardless of recency-window crowding.

    When wiki/dreaming (O-049) lands, this becomes redundant — the importance
    signal will surface these naturally. Until then, an explicit keyword filter
    keeps the high-value personal threads in front of the LLM.
    """
    # Build a Cypher OR clause over all keywords. Case-insensitive.
    keyword_clauses = " OR ".join([
        f"toLower(r.fact) CONTAINS '{kw}'"
        for kw in PERSONAL_LIFE_KEYWORDS
    ])
    # Cypher does pre-filtering; Python does final exclude pass + ranking.
    cypher = f"""
        MATCH ()-[r:RELATES_TO]->()
        WHERE r.created_at > datetime() - duration({{days: $days}})
          AND ({keyword_clauses})
        RETURN r.uuid AS uuid,
               r.fact AS fact,
               toString(r.created_at) AS created_at,
               toString(r.valid_at) AS valid_at
        ORDER BY r.created_at DESC
        LIMIT 200
    """
    rows = neo4j_query(cypher, {"days": days})

    # Apply exclude filter
    filtered = []
    for r in rows:
        fact_lower = (r.get("fact") or "").lower()
        if any(exc in fact_lower for exc in PERSONAL_LIFE_EXCLUDES):
            continue
        filtered.append(r)

    # Rank by score-of-the-evidence: dense personal-content edges first
    # rather than newest-first. The 44h-old "Denver has places suitable for
    # proposals" should outrank a 2h-old "user is considering a maroon
    # Alocasia stalk" because the former is anchor-event-like.
    PRIORITY_PHRASES = [
        "denver", "red rocks", "proposal spot", "propose",
        "engagement ring", "wedding venue",
        "flight to", "trip to", "hotel in",
    ]

    def _rank_key(r):
        fact_lower = (r.get("fact") or "").lower()
        # Higher priority match -> earlier in list
        for i, phrase in enumerate(PRIORITY_PHRASES):
            if phrase in fact_lower:
                return (0, i, r.get("created_at") or "")
        return (1, 0, r.get("created_at") or "")

    filtered.sort(key=_rank_key)

    return [
        {
            "uuid": r.get("uuid") or "",
            "fact": r.get("fact") or "",
            "valid_at": r.get("valid_at") or r.get("created_at") or "",
        }
        for r in filtered[:limit]
    ]


def gather_context() -> dict:
    stats = graphiti_stats()
    # Diverse retrieval lenses. The graph contains a lot of MIKAI-internal
    # architecture discussion, so MIKAI-meta queries crowd out life content.
    # These five queries hit different facets of the graph so high-signal
    # personal threads don't get buried.
    threads = graphiti_search(
        "active in-flight decisions personal projects work commitments",
        num_results=10,
    )
    contradictions = graphiti_search(
        "contradiction unresolved tension belief change reversed",
        num_results=5,
    )
    recurring = graphiti_search(
        "recurring pattern across multiple sources weeks months",
        num_results=5,
    )
    urgent = graphiti_search(
        "urgent deadline upcoming booking time-sensitive decision needed soon",
        num_results=10,
    )
    personal = graphiti_search(
        "personal life relationship family travel proposal engagement event milestone",
        num_results=10,
    )
    # Time-based ranked lens — pulls candidates from layered windows
    # (24h / 7d / 30d) and ranks by recency × importance. Today importance
    # is a stub so recency wins; when wiki/dreaming consolidation lands
    # (O-049), this lens automatically surfaces older-but-still-load-bearing
    # threads without any FIGS code change. See `graphiti_ranked_candidates`
    # docstring.
    fresh = graphiti_ranked_candidates(total_limit=30)
    # Targeted personal-life lens — kept for fallback when wiki is unavailable.
    personal_life = graphiti_personal_life_edges(days=30, limit=15)
    # PRIMARY ranking surface: parse the nightly Dream-generated wiki.
    # This is the formal user-identity synthesis (dream.py output). When
    # available, FIGS ranks wiki threads (not raw graph edges) and asks
    # Claude to choose among those structured candidates. Soft supersession:
    # if the wiki contradicts a raw edge, the wiki wins because it's the
    # most recent synthesis.
    wiki = wiki_parser.parse_wiki()
    wiki_threads_ranked: list[dict] = []
    if wiki.available:
        scored = [(wiki_parser.score_thread(t, wiki), t) for t in wiki.threads]
        scored.sort(key=lambda x: x[0], reverse=True)
        for score, t in scored:
            wiki_threads_ranked.append({
                "slug": t.slug,
                "title": t.title,
                "state": t.state,
                "score": score,
                "tension_membership": t.tension_membership,
                "detail": t.detail,
            })

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
        "stats": stats,
        "threads": threads,
        "contradictions": contradictions,
        "recurring": recurring,
        "urgent": urgent,
        "personal": personal,
        "personal_life": personal_life,
        "fresh": fresh,
        "realtime": realtime,
        "wiki": wiki,
        "wiki_threads_ranked": wiki_threads_ranked,
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
You are MIKAI, Brian's notification decider. Your job this tick: surface 2 to 5 distinct notifications, each picking up a real thread of Brian's life at the exact decision point he last paused on. NOT 0, NOT 1, NOT 6. If you can only justify 1, pick a second-best from the needs registry — Brian curated it; every item there is worth a nudge.

CURRENT TIME: {now} (UTC), {weekday}, hour {hour} UTC

== TOP-TIER — Brian's declared life-tier themes (OUTRANKS ontology ordering) ==
{life_tier_content}

== FRAME — Brian's life-dimensions ontology (highest level) ==
Below is Brian's personal ontology: 9 dimensions of his life, each with concrete
goals and evidence concepts. Use this as the ROUTING SCHEMA when ranking
candidates. Two hard rules:

  RULE A — Spectrum coverage. Your 2-5-item slate MUST span at least 3
  distinct dimensions. Do NOT stack the whole slate under one dimension.

  RULE B — Noise filter. The concepts listed under Dimension 1 (AI Career /
  MIKAI Build) are mostly framework/tooling noise — MIKAI, Claude Code,
  Perplexity, Neo4j, Assistant, sidecar, launchd, etc. DO NOT surface these
  as notifications unless a CONCRETE decision point in Dimension 1 crystallizes
  (founder-vs-employee commitment, ship milestone, funding move). Otherwise
  they are background context Brian sees every day; a notification about them
  is signal-poor.

{dimensions_content}

== PRIMARY LENS — Full-corpus ontology wiki (LLM synthesis over entire corpus) ==
Below is Brian's PRIMARY narrative representation of himself, synthesized from
the whole corpus (~6,700 episodes, 21M chars, spanning 2013→today) organized
against the DIMENSIONS ontology. This is the RICHEST source of surfaceable
candidates you have — it contains named goals, dated pickup points, cross-time
patterns, and stalled decisions that the last-7d incremental wiki misses
entirely. TREAT THIS AS THE PRIMARY LENS for candidate selection. Pull
surfacing candidates from this wiki's per-dimension sections; each dimension's
listed goals with state/pickup are directly notification-eligible.

{ontology_wiki_content}

== HIGHEST PRIORITY — Brian-curated PRIORITY NEEDS ==
The NEEDS REGISTRY below was hand-curated by Brian. These are load-bearing life needs that may not surface in his conversations (financial admin, health admin, career decisions). FIGS should treat these as the FIRST candidates for surfacing, ranked by their score. The wiki and graph evidence below are SUPPORTING context — if a need's `next_step` aligns with recent fresh activity, surface that need.

NEEDS REGISTRY (ranked by state × urgency × tension × detail):
{needs_summary}

== PRIMARY SYNTHESIS ==
The WIKI below was synthesized last night by MIKAI's `dream.py` from the previous 7 days of Brian's activity. It is the most current and authoritative model of what Brian is actually doing, deciding, and conflicted about. Trust it over individual raw graph edges; raw edges may be stale or superseded by what the wiki now says. The needs registry above OUTRANKS the wiki because Brian curated it explicitly.

WIKI ## Who (stable self-model):
{wiki_who}

WIKI ## Now (active threads, ranked by surface_priority — state × tension_pressure × detail_quality):
{wiki_threads_summary}

WIKI ## Tensions (held contradictions — these are MIKAI's priority-0 signal):
{wiki_tensions_summary}

WIKI ## Wants (inferred goals, certainty in words):
{wiki_wants_summary}

WIKI last_dream_at: {wiki_last_dream}

== SUPPORTING SUBSTRATE (raw graph edges + live sources) ==

GRAPH STATE:
- Entities: {entity_count}
- Edges: {edge_count}
- Episodes: {episode_count}

ACTIVE THREADS (from edge search, most relevant first):
{threads_summary}

CONTRADICTIONS / TENSIONS (currently active):
{contradictions_summary}

RECURRING PATTERNS (multi-source signal):
{recurring_summary}

URGENT / TIME-SENSITIVE (deadlines, bookings, upcoming things):
{urgent_summary}

PERSONAL LIFE (relationships, family, travel, milestones):
{personal_summary}

RANKED CANDIDATES from MIKAI graph (layered windows: last_24h / last_7d / last_30d, scored by recency × importance):
NOTE: The ranking is recency-dominant today because the importance signal is a stub. Older items (last_7d, last_30d windows) can still appear here if they have a high score — they are NOT noise; they are threads MIKAI thinks may still need attention. Treat them as "you may have started this and never followed through."
{fresh_summary}

PINNED PERSONAL-LIFE CANDIDATES (keyword-targeted, last 30 days, excluding MIKAI-internal architecture noise — these are high-signal personal threads Brian started recently. Evaluate each as a candidate for the "stalled personal-life thread" pattern in rule 2):
{personal_life_summary}

LIVE EVENTS FROM SOURCES (iMessage / Calendar / Gmail, last 24-72h):
{realtime_summary}

BRIAN'S RECENT NOTIFICATIONS AND HIS RESPONSES (newest first):
{recent_decisions_summary}

RULES YOU MUST FOLLOW:

0. **AT LEAST 1 ITEM MUST COME FROM THE ONTOLOGY WIKI, NOT THE NEEDS REGISTRY.** The needs registry has only 5 curated items. The ontology wiki covers Brian's ENTIRE 13-year corpus across all 9 dimensions — surfacing only from the registry means missing everything Brian hasn't hand-curated (International Village real estate, ocean farming, Kenya coffee, Recurring Themes, city-choice, Monstera project, dry-eye/smoking, etc.). Any dimension's goals + evidence in the ontology wiki are notification-eligible. Explicitly force yourself to promote AT LEAST ONE non-registry candidate this tick.

1. **Rank the NEEDS REGISTRY items alongside ontology-wiki candidates.** Every entry in the Brian-curated needs registry is eligible AND every dimension-scoped goal in the ontology wiki is eligible. A need or wiki-goal that aligns with fresh raw activity (calendar event, message, email, graph edge) has high delivery_value. An item with no recent movement AND no contradicting evidence is a stalled-thread candidate (the canonical MIKAI use case). Give registry items a priority boost but DO NOT let it exclude wiki-only items.

2. **The 4-factor metric.** surface_priority = thread_state × tension_pressure × delivery_value × delivery_cost⁻¹
   - thread_state: acting > stalled > decided > exploring
   - tension_pressure: threads listed in ## Tensions get a boost (priority-0 signal per MIKAI's design)
   - delivery_value: would surfacing this CHANGE what Brian does today? A stalled thread where a nudge could unblock action = high. An acting thread with active momentum = low (he doesn't need a reminder; he's on it).
   - delivery_cost⁻¹: time-of-day (workday = higher bar), recent dismiss patterns (don't repeat dismissed topics)

3. **Wiki supersedes raw edges (SOFT GATE).** If a raw graph edge says "X" but the wiki ## Who or ## Now says "Y" (different detail, different state, different location/decision), trust the wiki. Example: a raw edge says "Denver proposal spots" but the wiki says "planning a proposal trip with Germaine — Atacama or Ladakh are leading candidates" — DO NOT surface Denver; that's stale. The proposal thread isn't even in ## Now (it's at the ## Who level), suggesting it's background, not currently-being-acted-on.

4. **Default to silence FOR NOISE.** Newsletters, marketing emails, parking auto-receipts, meta-references about MIKAI itself, system messages — silent (i.e., don't include them in the output array). But the FLOOR for the output array is 2: if you're tempted to silence everything, you're misreading the needs registry — re-rank.

5. **Pick up the conversation. Don't open a new one.** This is the single most important rule for body content. For every notification, you must:
   (a) identify the **decision point** Brian last paused at on this thread — the unresolved question, the half-made choice, the blocker he hit, the next concrete move he was weighing;
   (b) write the body so it RESUMES from that point, not from the topic in general.
   - BAD: "Denver proposal spots — still open?" (vague, reopens a closed thread, no pickup)
   - BAD: "Have you thought about your MSP?" (no decision point, no movement)
   - GOOD: "MSP doc hunt: BC residence proof is the blocker. Pull BC license + utility bill tonight, slot the ServiceBC visit." (states the exact unresolved beat + the smallest next move)
   - GOOD: "Atacama vs Ladakh — last beat: cost vs altitude. Atacama is 15h on a plane; Ladakh needs Oct timing. Pick one this week so we can book the venue." (resumes from the actual last decision-fork, not the topic)
   The needs registry's `next_step` and `last_movement` fields are your ground truth for the decision point. The wiki ## Now thread state (acting/stalled/decided) tells you what kind of pickup is needed. If you can't identify a concrete decision point for an item, you do NOT have enough signal to surface it — skip it.

6. **Diversify the slate.** The 2-5 items must come from at least 2 different domains (e.g., not 3 finance items in a row). Mix: needs registry items + 1 wiki thread + at most 1 live event from iMessage/Calendar/Gmail if highly relevant. Hard-cap: at most 1 notification per `wiki_thread_slug` and at most 1 per needs `slug` per tick.

7. **High-value send pattern.** A wiki ## Now thread in state "acting" with high tension_pressure AND a recent raw-event signal (calendar event tomorrow, message about it, deadline-language) = clear send candidate.

8. **Time-of-day matters.** UTC hour {hour}; Brian is typically Pacific. Late night = quieter (still send 2, never 5). Morning brief = up to 5. Workday tick = 2-3.

9. **Voice:** brief, Brian-voiced, second-person, present-tense. Example: "Crypto scammer's pushing the test transfer move. Same playbook as last time." NOT: "There is an outstanding response required for the Kenya thread."

10. **Citation:** if you cite specific raw edge UUIDs, they MUST be visible in the candidates section. You may also cite wiki thread slugs (the [slug] before the title in ## Now) or needs registry slugs — those are always valid because they came from the curated lists above.

11. **Classify then route.** For every notification, first name the `action_type` explicitly, then choose `next_step_url` based on that type. The destination IS the action — do not attach a distracting URL to a pickup that's really a decision or a physical task.

Action types (pick exactly one per notification):

- `transaction` — do it inside a specific portal (MSP portal, Scotia banking, IBKR)
- `communication` — send a message to a specific person (email draft, iMessage draft)
- `search` — the pickup is "look up more info" or "research this"
- `capture` — fill in a form / add a calendar event / log a decision (Notes, Calendar, Reminders)
- `decision` — the action is *thinking*, not doing. The right destination is a time-block on the calendar with the full context bundle embedded so cognitive state can be resurrected when the block fires.
- `physical` — offline action (pull docs from drawer, in-person conversation, make a call)
- `user_response` — Brian's own meta-action on a prior notification (snooze/mark done). Not a first-step; handled by future action buttons.

Routing by action_type:

(a) `transaction` → a specific deep-link portal URL from DIMENSIONS.md's Per-Dimension Destination Templates.
(b) `communication` → `googlegmail://co?to=<addr>&subject=<url-encoded>&body=<url-encoded>` draft (PREFERRED over mailto:). For iMessage: `sms:<phone>&body=<url-encoded>`.
(c) `search` → `https://www.perplexity.ai/search?q=<url-encoded query>` (or Google Flights, Zonaprop, etc. from DIMENSIONS.md).
(d) `capture` → Google Calendar quick-add URL. Pre-fill `text=` (event title) and `dates=` (30-min block in the next 3-5 days). Include a brief description in `details=`.
(e) `decision` → Google Calendar quick-add URL. Same as capture, BUT the `details=` parameter MUST be a full context bundle so the calendar event carries the resurrection substrate. The bundle should contain, in url-encoded form:
    - A 2-3 line wiki excerpt naming the dimension's goal and current state
    - A "Prior beats:" list of dated decisions/beats from the corpus (up to 5)
    - A "Research to load:" list of 3-5 URLs (Perplexity, LinkedIn, Notes, specific research the user has already done)
    When the block fires 3 days later, this description IS what re-lights the cognitive state. Do not set null for decision — the block IS the destination.
(f) `physical` → `next_step_url: null`. Explain in `reasoning` that this is an offline action. Optionally: if the action is calling someone, use `tel:+1...`.
(g) `user_response` → `next_step_url: null` (action-button mechanism is deferred to a later iteration).

For `capture` and `decision`, choose a reasonable block time relative to CURRENT TIME (see prompt header). Weekday work items → weekday morning. Personal decisions → weekend morning. Never invent URLs — use only the templates in DIMENSIONS.md or well-known schemes.

OUTPUT FORMAT: Return STRICTLY valid JSON, no markdown code fence, no commentary, no preamble. Just the JSON object.

Shape (notifications is an array of 2-5 items, OR 0 only if everything is genuine noise/dismissed-cooldown):

{{
  "notifications": [
    {{
      "title": "<<= 55 chars; topic + state, not a question>",
      "body": "<<= 220 chars; (a) last beat in 4-10 words, then (b) concrete pickup move in 8-20 words. Read rule 5.>",
      "priority": "passive|active|timeSensitive",
      "decision_point": "<one sentence stating the EXACT unresolved question or choice Brian last paused at. Required.>",
      "evidence_edge_uuids": ["<uuid or 8-char short form or wiki slug or needs slug>", ...],
      "wiki_thread_slug": "<slug from ## Now if applicable, else null>",
      "needs_slug": "<slug from needs registry if applicable, else null>",
      "action_type": "<one of: transaction | communication | search | capture | decision | physical | user_response — see RULE 11>",
      "next_step_url": "<URL routed by action_type per RULE 11; for `decision`, a Google Calendar quick-add URL with the full context bundle in details=; null only for physical/user_response>",
      "dimension": "<dim_1 | dim_2 | ... | dim_9 — the life-dimension slug this item belongs to (from the FRAME section above); required so the feedback loop can score tap-rate by dimension>",
      "reasoning": "<one sentence: why this item, why now, naming the 4 factors>"
    }},
    ...
  ],
  "silent_reason": null,
  "considered": [
    {{"slug": "...", "rank": 1, "source": "needs|wiki|graph", "selected": true|false, "note": "..."}},
    ...
  ]
}}

If — and ONLY if — every candidate is genuine noise/cooldown and you cannot find 2 items worth surfacing (this should be extremely rare given the curated needs registry), return:

{{"notifications": [], "silent_reason": "<one-sentence why all-silent is justified>", "considered": [ ... ]}}

REQUIRED: the "considered" field lists ALL needs registry slugs AND wiki ## Now thread slugs you ranked (selected or not), in priority order, with a 1-line note on each. This shows your work and is how FIGS audits coverage.
"""


def build_prompt(context: dict, recent_decisions: list[dict]) -> str:
    now = datetime.now(timezone.utc)
    wiki = context.get("wiki")
    return DECIDE_PROMPT.format(
        now=now.isoformat(timespec="minutes"),
        weekday=now.strftime("%A"),
        hour=now.hour,
        entity_count=context["stats"].get("entity_count", "?"),
        edge_count=context["stats"].get("edge_count", "?"),
        episode_count=context["stats"].get("episode_count", "?"),
        threads_summary=format_edges(context["threads"]),
        contradictions_summary=format_edges(context["contradictions"]),
        recurring_summary=format_edges(context["recurring"]),
        urgent_summary=format_edges(context.get("urgent", [])),
        personal_summary=format_edges(context.get("personal", [])),
        personal_life_summary=format_edges(context.get("personal_life", [])),
        fresh_summary=format_edges(context.get("fresh", [])),
        realtime_summary=format_realtime(context.get("realtime", [])),
        recent_decisions_summary=format_decisions(recent_decisions),
        wiki_who=format_wiki_who(wiki),
        wiki_threads_summary=format_wiki_threads(context.get("wiki_threads_ranked", []), wiki),
        wiki_tensions_summary=format_wiki_tensions(wiki),
        wiki_wants_summary=format_wiki_wants(wiki),
        wiki_last_dream=(wiki.last_dream_at if wiki and wiki.available else "WIKI UNAVAILABLE"),
        needs_summary=format_needs(context.get("needs_ranked", []), context.get("needs_registry")),
        dimensions_content=load_dimensions(),
        ontology_wiki_content=load_ontology_wiki(),
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


def format_wiki_who(wiki) -> str:
    if not wiki or not wiki.available:
        return "(wiki not yet generated — fall back to raw graph evidence)"
    who = wiki.who.strip()
    return who[:1200] if who else "(empty)"


def format_wiki_threads(ranked: list[dict], wiki) -> str:
    if not wiki or not wiki.available or not ranked:
        return "(wiki has no threads — fall back to raw graph evidence)"
    lines = []
    for t in ranked:
        tension_tag = f" ⚠tensions={t['tension_membership']}" if t.get("tension_membership") else ""
        lines.append(
            f"- [{t['slug']}] state={t['state']} score={t['score']:.2f}{tension_tag}: {t['title']}"
        )
        detail = (t.get("detail") or "").strip()
        # Show the body after the title prefix, trimmed.
        body = detail
        # Strip leading "**Title** — State." chunk so we only see the meaningful content
        body = re.sub(r"^\*\*[^*]+\*\*\s*[—\-–]\s*\w+\.?\s*", "", body)
        body_short = (body or "")[:280].strip()
        if body_short:
            lines.append(f"     {body_short}")
    return "\n".join(lines)


def format_wiki_tensions(wiki) -> str:
    if not wiki or not wiki.available or not wiki.tensions:
        return "(none)"
    lines = []
    for tension in wiki.tensions:
        related = f" [related: {','.join(tension.related_thread_slugs)}]" if tension.related_thread_slugs else ""
        lines.append(f"  #{tension.index}: {tension.title}{related}")
    return "\n".join(lines)


def format_wiki_wants(wiki) -> str:
    if not wiki or not wiki.available or not wiki.wants:
        return "(none)"
    lines = []
    for w in wiki.wants[:8]:
        lines.append(f"  - ({w.certainty}) {w.text[:200]}")
    return "\n".join(lines)


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


def format_edges(edges: list[dict]) -> str:
    if not edges:
        return "(none)"
    lines = []
    for e in edges[:15]:
        fact = (e.get("fact") or "").strip()
        uuid = e.get("uuid") or ""
        uuid_short = uuid[:8] if uuid else "????????"
        # Ranked candidates carry _window + _score; render them; fall back
        # to valid_at for plain edges.
        window = e.get("_window")
        score = e.get("_score")
        if window is not None and score is not None:
            tag = f"{window} s={score:.2f}"
        else:
            tag = f"valid_at={e.get('valid_at') or ''}"
        lines.append(f"- [{uuid_short}] {fact} ({tag})")
    return "\n".join(lines) if lines else "(empty after format)"


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

SLATE_MIN = 2
SLATE_MAX = 5


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
            "evidence_edge_uuids", "wiki_thread_slug", "needs_slug",
            "next_step_url", "action_type", "reasoning",
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


def _evidence_pool(context: dict) -> set:
    seen = set()
    for key in ("threads", "contradictions", "recurring",
                "urgent", "personal", "personal_life", "fresh"):
        for edge in context.get(key, []):
            uuid = edge.get("uuid")
            if uuid:
                seen.add(uuid)
                seen.add(uuid[:8])
    for t in context.get("wiki_threads_ranked", []) or []:
        if t.get("slug"):
            seen.add(t["slug"])
    for n in context.get("needs_ranked", []) or []:
        if n.get("slug"):
            seen.add(n["slug"])
    # Ontology-wiki citations. The wiki content is always in-context (via the
    # PRIMARY LENS section), so any 'wiki-dimension-*' or 'wiki-goal-*' citation
    # is provably grounded. Rather than enumerate every possible dimension slug,
    # we accept the prefix-based patterns and validate downstream via the
    # sentinel token.
    seen.add("__WIKI_ONTOLOGY__")  # sentinel — see _is_ontology_citation
    return seen


_ONTOLOGY_PREFIXES = (
    "wiki-dimension-", "wiki-goal-", "wiki-theme-",
    "dimension-", "dim-", "dim_",
    "ontology-", "ontology_",
)


def _is_ontology_citation(cite: str) -> bool:
    c = (cite or "").lower()
    return any(c.startswith(p) for p in _ONTOLOGY_PREFIXES)


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

    pool = _evidence_pool(context)
    wiki_slugs = set()
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

        # Dedup: at most one per wiki_thread_slug, at most one per needs_slug.
        ws = n.get("wiki_thread_slug")
        if ws:
            if ws in wiki_slugs:
                return False, f"notification[{i}] duplicate wiki_thread_slug '{ws}'"
            wiki_slugs.add(ws)
        ns = n.get("needs_slug")
        if ns:
            if ns in needs_slugs:
                return False, f"notification[{i}] duplicate needs_slug '{ns}'"
            needs_slugs.add(ns)

        # Citation check — accept graph UUIDs (full or 8-char), wiki-thread slugs,
        # needs slugs (from _evidence_pool), OR ontology-wiki citations
        # (wiki-dimension-*, dim_*, ontology-*), since the ontology wiki is
        # always present in-context as a prompt section.
        for c in (n.get("evidence_edge_uuids", []) or []):
            if c not in pool and c[:8] not in pool and not _is_ontology_citation(c):
                return False, f"notification[{i}] cited evidence '{c}' not in context"

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
            json.dumps(notif.get("evidence_edge_uuids", []) or []),
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
             notif_id: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO notification_log
            (tick_ts, prompt_hash, decision_json, sent, title, body, priority,
             evidence_edge_uuids, reasoning, decision_point,
             slate_index, slate_size, next_step_url, action_type, notif_id)
        VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tick_ts,
            hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
            json.dumps(notif),
            notif["title"],
            notif["body"],
            notif["priority"],
            json.dumps(notif.get("evidence_edge_uuids", []) or []),
            notif.get("reasoning", ""),
            notif.get("decision_point", ""),
            slate_index,
            slate_size,
            notif.get("next_step_url"),
            notif.get("action_type"),
            notif_id,
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
        print(f"Graph: {context['stats'].get('entity_count','?')} entities, "
              f"{context['stats'].get('episode_count','?')} episodes")
        print()
        print(f"--- Needs Registry ({len(context.get('needs_ranked', []))}) ---")
        for n in context.get("needs_ranked", []):
            print(f"  {n['score']:.2f} [{n['state']:<10}/{n['urgency']:<8}] {n['title']}")
            if n.get("next_step"):
                print(f"        next: {n['next_step'][:120]}")
        print()
        print(f"--- Wiki Threads ({len(context.get('wiki_threads_ranked', []))}) ---")
        for t in context.get("wiki_threads_ranked", []):
            print(f"  {t['score']:.2f} [{t['state']:<10}] {t['title']}")
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
            for t in context.get("wiki_threads_ranked", []):
                if len(top3) >= 3:
                    break
                top3.append({
                    "title": t["title"],
                    "next_step": (t.get("detail") or "")[:200],
                    "source": "wiki",
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
    print("Pulling context from Graphiti…")
    context = gather_context()
    if context["stats"]:
        print(f"  graph: {context['stats'].get('entity_count')} entities, "
              f"{context['stats'].get('episode_count')} episodes")
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

    if len(notifs) < SLATE_MIN:
        # Soft floor — the prompt asks for 2-5. If the LLM came back with 1,
        # we send it but log a warning so we can grade it later.
        print(f"WARN: slate undersized ({len(notifs)} < {SLATE_MIN}); proceeding",
              file=sys.stderr)

    if args.dry_run:
        for i, n in enumerate(notifs):
            print(f"DRY-RUN [{i+1}/{len(notifs)}]: title='{n['title']}', "
                  f"body='{n['body']}', priority={n['priority']}")
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
        if sent_ok:
            log_sent(conn, now_ts, prompt, n, slate_index=i,
                     slate_size=slate_size, notif_id=notif_id)
            print(f"  ✓ [{i+1}/{slate_size}] SENT: {n['title']} "
                  f"(notif_id={notif_id})")
        else:
            log_silent(conn, now_ts, prompt, n, f"dispatch_failed: {dispatch_msg}")
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
