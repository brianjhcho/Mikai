"""Collect the L4-surfacing view.

Reuses infra.cockpit for scored threads + attention head so we compute
scores exactly once and never disagree with the cockpit. Reads the raw
state files directly for deliveries, transitions, and Attention Engine
tick history.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from infra.cockpit import collect_departments, compute_attention
from infra.mikai_brain import DELIVERY_LOG, PROGRESS_LOG


# Log-line transition marker: "- 2026-08-05 [decided→stalled] ..." OR
# "- 2026-08-05 [stalled→acting] ...". We deliberately skip single-state
# markers like "[acting]" — those are activity notes, not transitions.
_TRANSITION_RE = re.compile(
    r"^-\s+(?P<date>\d{4}-\d{2}-\d{2})\s+\[(?P<from>[a-z]+)→(?P<to>[a-z]+)\](?:\s+(?P<note>.*))?$"
)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _fmt_ts(ts: str) -> str:
    """ISO8601 → 'MM-DD HH:MM'. Falls back to raw string on parse failure."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%m-%d %H:%M")
    except (ValueError, AttributeError):
        return ts


# ── attention head + ranked scores ───────────────────────────────────────


def collect_attention(departments: list[dict]) -> dict:
    """Return {'head': dict|None, 'scored': [...], 'quiet': [slug,...]}.

    head:   the attention-head dict (or None if all quiet)
    scored: every non-completed thread with score > 0, top-first, with
            slug + score + reason + next_step (for the ranked table)
    quiet:  slugs with score == 0 and state != completed — the
            contrapositive list ("what MIKAI is choosing to be silent
            about")
    """
    att = compute_attention(departments)
    head = att["attention_head"]
    if head.get("quiet"):
        head = None

    # Build a slug → thread-dict index so we can attach next_step to
    # each scored row without recomputing it.
    by_slug: dict[str, dict] = {}
    for d in departments:
        for t in d["threads"]:
            by_slug[t["slug"]] = t

    scored_rows: list[dict] = []
    for row in att["scored"]:
        if row["score"] <= 0:
            continue
        t = by_slug.get(row["slug"], {})
        scored_rows.append({
            "score": row["score"],
            "slug": row["slug"],
            "state": t.get("state", ""),
            "reason": row["reason"],
            "next_step": t.get("next_step", "") or "—",
        })

    quiet_slugs: list[dict] = []
    for row in att["scored"]:
        if row["score"] > 0:
            continue
        t = by_slug.get(row["slug"], {})
        # score==0 in `att['scored']` already excludes completed threads
        quiet_slugs.append({
            "slug": row["slug"],
            "state": t.get("state", ""),
            "last_activity": t.get("last_activity", ""),
        })

    return {"head": head, "scored": scored_rows, "quiet": quiet_slugs}


# ── deliveries (Sumimasen ledger) ────────────────────────────────────────


def collect_deliveries(limit: int = 10) -> list[dict]:
    """Last `limit` rows from delivery_events.jsonl, newest first."""
    rows = _read_jsonl(DELIVERY_LOG)
    tail = rows[-limit:]
    tail.reverse()
    return [{
        "ts": _fmt_ts(r.get("ts", "")),
        "thread": r.get("thread", ""),
        "kind": r.get("kind", ""),
        "response": r.get("response", ""),
        "note": (r.get("note") or "").strip(),
    } for r in tail]


# ── transitions (from thread log lines) ─────────────────────────────────


def collect_transitions(departments: list[dict], limit: int = 10) -> list[dict]:
    """Last `limit` state transitions across all thread logs.

    Sorted by (date DESC, slug). Only lines with an explicit
    `[from→to]` marker are transitions — single-state markers are
    activity notes and are skipped.
    """
    events: list[dict] = []
    for d in departments:
        for t in d["threads"]:
            for line in t.get("log_full") or []:
                m = _TRANSITION_RE.match(line.strip())
                if not m:
                    continue
                events.append({
                    "date": m.group("date"),
                    "slug": t["slug"],
                    "from": m.group("from"),
                    "to": m.group("to"),
                    "note": (m.group("note") or "").strip(),
                })
    events.sort(key=lambda e: (e["date"], e["slug"]), reverse=True)
    return events[:limit]


# ── Attention Engine ticks (mode contains "decide") ──────────────────────


def collect_engine_ticks(limit: int = 3) -> list[dict]:
    """Last `limit` progress.jsonl rows whose mode contains 'decide'.

    Attention Engine ticks are the surface engine's decision points —
    when the decider was invoked, what it saw, whether it dispatched.
    The primary tick recorder today is `standup`, but if a `decide`
    mode ever lands (per infra/decider/mikai_decide.py) it wins.
    """
    rows = _read_jsonl(PROGRESS_LOG)
    decide = [r for r in rows if "decide" in (r.get("mode") or "").lower()]
    tail = decide[-limit:]
    tail.reverse()
    return [{
        "ts": _fmt_ts(r.get("ts", "")),
        "mode": r.get("mode", ""),
        "surfaced": r.get("surfaced", 0),
        "acted": r.get("acted", 0),
        "dismissed": r.get("dismissed", 0),
        "did": (r.get("did") or "").strip(),
    } for r in tail]


def collect_standup_ticks(limit: int = 3) -> list[dict]:
    """Fallback tick trace when no 'decide' mode is logged.

    Standup is the surface engine's heartbeat in the current codebase —
    it scans threads, surfaces findings, writes delivery events. Same
    shape as `collect_engine_ticks` for render-side reuse.
    """
    rows = _read_jsonl(PROGRESS_LOG)
    standups = [r for r in rows if (r.get("mode") or "") == "standup"]
    tail = standups[-limit:]
    tail.reverse()
    return [{
        "ts": _fmt_ts(r.get("ts", "")),
        "mode": r.get("mode", ""),
        "surfaced": r.get("surfaced", 0),
        "acted": r.get("acted", 0),
        "dismissed": r.get("dismissed", 0),
        "did": (r.get("did") or "").strip(),
    } for r in tail]


# ── top-level assembly ───────────────────────────────────────────────────


def collect_view() -> dict:
    """Assemble the full surfacing view."""
    departments = collect_departments()
    attention = collect_attention(departments)
    ticks = collect_engine_ticks(limit=3)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_at_human": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "attention": attention,
        "deliveries": collect_deliveries(limit=10),
        "transitions": collect_transitions(departments, limit=10),
        "engine_ticks": ticks,
        # Only fall back to standup when no explicit decider ticks exist,
        # so the panel never disappears entirely on today's codebase.
        "standup_ticks": [] if ticks else collect_standup_ticks(limit=3),
    }
