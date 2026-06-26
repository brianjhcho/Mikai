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
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import request as urlreq

# Make sibling `adapters/` importable regardless of CWD
sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters import imessage, calendar as cal_adapter, gmail  # noqa: E402

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

CLAUDE_TIMEOUT_S = 180

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
"""


def db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
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


def graphiti_recent_edges(hours: int = 24, limit: int = 25) -> list[dict]:
    """Return the most-recently-created edges in the graph.

    This is the 'what's new' lens. Semantic search can't answer it because
    embeddings don't encode time. We query Neo4j directly by `created_at`.
    Returns dicts shaped to match what format_edges() expects.
    """
    cypher = """
        MATCH ()-[r:RELATES_TO]->()
        WHERE r.created_at > datetime() - duration({hours: $hours})
        RETURN r.uuid AS uuid,
               r.fact AS fact,
               toString(r.created_at) AS created_at,
               toString(r.valid_at) AS valid_at
        ORDER BY r.created_at DESC
        LIMIT $limit
    """
    rows = neo4j_query(cypher, {"hours": hours, "limit": limit})
    return [
        {
            "uuid": r.get("uuid") or "",
            "fact": r.get("fact") or "",
            "valid_at": r.get("valid_at") or r.get("created_at") or "",
        }
        for r in rows
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
    # Time-based lens — what's newly ingested. Semantic queries can't answer
    # this because embeddings don't encode recency. This is the single most
    # important lens for "right now" decisions.
    fresh = graphiti_recent_edges(hours=24, limit=25)

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
        "fresh": fresh,
        "realtime": realtime,
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
You are MIKAI, Brian's notification decider. Your single job: decide whether to send Brian a notification right now, and if so what to say.

CURRENT TIME: {now} (UTC), {weekday}, hour {hour} UTC

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

FRESHLY INGESTED IN LAST 24h (what just landed in the graph — use this as your primary "right now" signal):
{fresh_summary}

LIVE EVENTS FROM SOURCES (iMessage / Calendar / Gmail, last 24-72h):
{realtime_summary}

BRIAN'S RECENT NOTIFICATIONS AND HIS RESPONSES (newest first):
{recent_decisions_summary}

RULES YOU MUST FOLLOW:
1. Default to silence. The bar for "send" is high — silence is almost always the right answer.
2. Only send if there is a specific, concrete thread genuinely worth interrupting Brian about right now. Vague "you should think about X" notifications are forbidden.
3. Patterns Brian dismissed recently: do NOT repeat those patterns.
4. Patterns Brian acted on recently: similar candidates are stronger.
5. Time-of-day matters. UTC hour {hour}; convert to Brian's local time if known (he's typically Pacific or East Africa). Late night = quieter. Morning = brief active. Workday = passive unless urgent.
6. If you cite specific evidence, the edge UUIDs you cite MUST be visible in the threads/contradictions/recurring section above. Don't invent UUIDs. Use the [8-char] short form if that's all you have.
7. Voice: brief, Brian-voiced, second-person. Example: "Martin's been waiting on the Kenya cultivar question. 12 days." NOT: "There is an outstanding response required for the Kenya thread."

OUTPUT FORMAT: Return STRICTLY valid JSON, no markdown code fence, no commentary, no preamble. Just the JSON object.

If silent:
{{"send": false, "reasoning": "<one-sentence why silent>"}}

If sending:
{{"send": true, "title": "<<= 55 chars>", "body": "<<= 160 chars>", "priority": "passive|active|timeSensitive", "evidence_edge_uuids": ["<uuid or 8-char short form>", ...], "reasoning": "<one-sentence why now>"}}
"""


def build_prompt(context: dict, recent_decisions: list[dict]) -> str:
    now = datetime.now(timezone.utc)
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
        fresh_summary=format_edges(context.get("fresh", [])),
        realtime_summary=format_realtime(context.get("realtime", [])),
        recent_decisions_summary=format_decisions(recent_decisions),
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


def format_edges(edges: list[dict]) -> str:
    if not edges:
        return "(none)"
    lines = []
    for e in edges[:15]:
        fact = (e.get("fact") or "").strip()
        uuid = e.get("uuid") or ""
        uuid_short = uuid[:8] if uuid else "????????"
        valid_at = e.get("valid_at") or ""
        lines.append(f"- [{uuid_short}] {fact} (valid_at={valid_at})")
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

def invoke_claude(prompt: str) -> str | None:
    """Invoke Claude via the `claude` CLI in headless mode (Max-legitimate)."""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT_S,
        )
        if result.returncode != 0:
            print(f"ERROR: `claude` CLI returned {result.returncode}", file=sys.stderr)
            if result.stderr:
                print(f"  stderr: {result.stderr.strip()[:500]}", file=sys.stderr)
            return None
        return result.stdout.strip()
    except FileNotFoundError:
        print("ERROR: `claude` CLI not found. Install Claude Code first.", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print(f"ERROR: `claude` CLI timed out after {CLAUDE_TIMEOUT_S}s", file=sys.stderr)
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


def validate_decision(decision: dict | None, context: dict) -> tuple[bool, str]:
    if not isinstance(decision, dict):
        return False, "decision is not a dict"
    if not isinstance(decision.get("send"), bool):
        return False, "'send' must be a boolean"
    if not decision["send"]:
        return True, "silent ok"

    for field in ("title", "body", "priority"):
        if not decision.get(field):
            return False, f"missing required field: {field}"

    if decision["priority"] not in VALID_PRIORITIES:
        return False, f"invalid priority: {decision['priority']}"

    if len(decision["title"]) > 80:
        return False, f"title too long ({len(decision['title'])} chars > 80)"
    if len(decision["body"]) > 300:
        return False, f"body too long ({len(decision['body'])} chars > 300)"

    # Evidence: every cited UUID must be in the context we provided.
    cited = decision.get("evidence_edge_uuids", []) or []
    if cited:
        seen = set()
        for edges_list in (context["threads"], context["contradictions"], context["recurring"]):
            for edge in edges_list:
                uuid = edge.get("uuid")
                if uuid:
                    seen.add(uuid)
                    seen.add(uuid[:8])
        for c in cited:
            if c not in seen and c[:8] not in seen:
                return False, f"cited evidence UUID '{c}' not present in context"

    return True, "ok"


# ── ntfy dispatch ──────────────────────────────────────────────────────

# ntfy priority levels: 1 (min) to 5 (max); default 3
NTFY_PRIORITY_MAP = {
    "passive": "2",
    "active": "3",
    "timeSensitive": "4",
    "critical": "5",
}


def dispatch_via_ntfy(title: str, body: str, priority: str = "active") -> tuple[bool, str]:
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

    req = urlreq.Request(
        url,
        data=body.encode("utf-8"),
        headers={
            "Title": title_for_header,
            "Priority": ntfy_priority,
            "Tags": "mikai",
        },
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


def log_sent(conn: sqlite3.Connection, tick_ts: str, prompt: str, decision: dict) -> None:
    conn.execute(
        """
        INSERT INTO notification_log
            (tick_ts, prompt_hash, decision_json, sent, title, body, priority,
             evidence_edge_uuids, reasoning)
        VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
        """,
        (
            tick_ts,
            hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
            json.dumps(decision),
            decision["title"],
            decision["body"],
            decision["priority"],
            json.dumps(decision.get("evidence_edge_uuids", []) or []),
            decision.get("reasoning", ""),
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

    print(f"DECISION:\n{json.dumps(decision, indent=2)}")

    # Validate
    ok, msg = validate_decision(decision, context)
    if not ok:
        print(f"VALIDATION FAILED: {msg}", file=sys.stderr)
        if not args.dry_run:
            log_silent(conn, now_ts, prompt, decision, f"validation_failed: {msg}")
        return 1

    if not decision["send"]:
        if not args.dry_run:
            log_silent(conn, now_ts, prompt, decision, "llm_chose_silent")
        print(f"SILENT: {decision.get('reasoning', '(no reasoning)')}")
        return 0

    # Dispatch
    if args.dry_run:
        print(f"DRY-RUN: would send title='{decision['title']}', "
              f"body='{decision['body']}', priority={decision['priority']}")
        return 0

    print(f"Dispatching via ntfy ('{NTFY_TOPIC}')…")
    sent_ok, dispatch_msg = dispatch_via_ntfy(
        decision["title"], decision["body"], decision["priority"]
    )

    if sent_ok:
        log_sent(conn, now_ts, prompt, decision)
        print(f"✓ SENT: {decision['title']}")
        return 0
    else:
        log_silent(conn, now_ts, prompt, decision, f"dispatch_failed: {dispatch_msg}")
        print(f"✗ DISPATCH FAILED: {dispatch_msg}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
