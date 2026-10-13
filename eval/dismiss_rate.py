#!/usr/bin/env python3
"""Dismiss rate for MIKAI's Surface Engine notifications.

Read-only over ~/.mikai/notification_log.db (override with --db). Stdlib only.

dismiss rate = negatives / (positives + negatives)
  positive: ACTED, TAPPED
  negative: DISMISSED, NOT_RELEVANT, DISMISSED_INFERRED
  neutral:  SNOOZED (excluded from the rate)
  no-signal: sent, but no feedback event recorded

The brief's gate: dismiss rate < 30% once >= 20 sent items carry a signal.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter

DEFAULT_DB = os.path.expanduser("~/.mikai/notification_log.db")

POSITIVE = {"ACTED", "TAPPED"}
NEGATIVE = {"DISMISSED", "NOT_RELEVANT", "DISMISSED_INFERRED"}
NEUTRAL = {"SNOOZED"}
EXPLICIT = {"ACTED", "DISMISSED", "NOT_RELEVANT", "SNOOZED"}
SIGNAL_EVENTS = POSITIVE | NEGATIVE | NEUTRAL

# Explicit labels beat inferred ones; a tap beats an inferred dismissal.
PRECEDENCE = {"ACTED": 5, "NOT_RELEVANT": 5, "DISMISSED": 5, "SNOOZED": 5,
              "TAPPED": 3, "DISMISSED_INFERRED": 1}

# notification_log.user_response, if ever populated, maps onto the same labels.
RESPONSE_ALIASES = {
    "acted": "ACTED", "done": "ACTED", "tapped": "TAPPED",
    "dismissed": "DISMISSED", "dismiss": "DISMISSED",
    "not_relevant": "NOT_RELEVANT", "not relevant": "NOT_RELEVANT",
    "snoozed": "SNOOZED", "snooze": "SNOOZED",
}

GATE_MIN_SIGNAL = 20
GATE_MAX_RATE = 0.30

SILENT_BY_CHOICE_PREFIXES = ("llm_chose_silent", "cooldown")


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _in_window(ts: str | None, since: str | None, until: str | None) -> bool:
    if ts is None:
        return since is None and until is None
    if since and ts < since:
        return False
    if until and ts >= until:
        return False
    return True


def _silent_reason_bucket(reason: str | None) -> str:
    if not reason:
        return "unknown"
    if reason.startswith(SILENT_BY_CHOICE_PREFIXES):
        return "silent_by_choice"
    return "failed"


def compute(db_path: str, since: str | None = None, until: str | None = None) -> dict:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        tables = _tables(conn)
        log_cols = _columns(conn, "notification_log") if "notification_log" in tables else set()

        decisions = 0
        silent_buckets: Counter[str] = Counter()
        silent_reasons: Counter[str] = Counter()
        # key -> {"notif_id", "title", "tick_ts", "events": [(type, ts)]}
        items: dict[str, dict] = {}

        if log_cols:
            want = ["id", "tick_ts", "sent", "title"]
            for opt in ("notif_id", "not_sent_reason", "user_response", "response_at"):
                if opt in log_cols:
                    want.append(opt)
            for row in conn.execute(f"SELECT {', '.join(want)} FROM notification_log ORDER BY id"):
                rec = dict(zip(want, row))
                if not _in_window(rec["tick_ts"], since, until):
                    continue
                decisions += 1
                if not rec["sent"]:
                    reason = rec.get("not_sent_reason")
                    silent_buckets[_silent_reason_bucket(reason)] += 1
                    silent_reasons[(reason or "unknown").split(":")[0]] += 1
                    continue
                key = rec.get("notif_id") or f"log:{rec['id']}"
                item = items.setdefault(key, {"notif_id": rec.get("notif_id"),
                                              "title": rec["title"], "tick_ts": rec["tick_ts"],
                                              "events": []})
                label = RESPONSE_ALIASES.get((rec.get("user_response") or "").strip().lower())
                if label:
                    item["events"].append((label, rec.get("response_at") or rec["tick_ts"]))

        if "notification_events" in tables:
            rows = conn.execute(
                "SELECT notif_id, event_type, event_ts FROM notification_events ORDER BY event_ts, id")
            sent_event_ids = set()
            for notif_id, event_type, event_ts in rows:
                etype = (event_type or "").upper()
                if etype == "SENT":
                    sent_event_ids.add(notif_id)
                    if notif_id not in items and _in_window(event_ts, since, until):
                        items[notif_id] = {"notif_id": notif_id, "title": None,
                                           "tick_ts": event_ts, "events": []}
                    continue
                if notif_id in items and etype in SIGNAL_EVENTS:
                    items[notif_id]["events"].append((etype, event_ts))
    finally:
        conn.close()

    outcomes: Counter[str] = Counter()
    explicit_counts: Counter[str] = Counter()
    inferred_counts: Counter[str] = Counter()
    per_item = []
    for key, item in items.items():
        events = item["events"]
        if events:
            # highest precedence wins; ties broken by latest timestamp
            label, ts = max(events, key=lambda e: (PRECEDENCE.get(e[0], 0), e[1] or ""))
        else:
            label, ts = None, None
        if label in POSITIVE:
            outcome = "positive"
        elif label in NEGATIVE:
            outcome = "negative"
        elif label in NEUTRAL:
            outcome = "neutral"
        else:
            outcome = "no_signal"
        outcomes[outcome] += 1
        if label:
            (explicit_counts if label in EXPLICIT else inferred_counts)[label] += 1
        per_item.append({"key": key, "title": item["title"], "tick_ts": item["tick_ts"],
                         "label": label, "outcome": outcome})

    pos, neg = outcomes["positive"], outcomes["negative"]
    rated = pos + neg
    rate = (neg / rated) if rated else None

    explicit_pos = sum(explicit_counts[l] for l in POSITIVE & EXPLICIT)
    explicit_neg = sum(explicit_counts[l] for l in NEGATIVE & EXPLICIT)
    explicit_rated = explicit_pos + explicit_neg
    explicit_rate = (explicit_neg / explicit_rated) if explicit_rated else None

    gate_met = rated >= GATE_MIN_SIGNAL
    gate_pass = gate_met and rate is not None and rate < GATE_MAX_RATE

    sent = len(items)
    return {
        "db": db_path,
        "window": {"since": since, "until": until},
        "decisions": decisions,
        "sent": sent,
        "silent": sum(silent_buckets.values()),
        "silent_breakdown": dict(silent_buckets),
        "silent_reasons": dict(silent_reasons),
        "outcomes": {k: outcomes[k] for k in ("positive", "negative", "neutral", "no_signal")},
        "signal_coverage": (sent - outcomes["no_signal"]) / sent if sent else None,
        "dismiss_rate": rate,
        "rated_items": rated,
        "explicit": {"labels": dict(explicit_counts), "rated": explicit_rated,
                     "dismiss_rate": explicit_rate},
        "inferred": {"labels": dict(inferred_counts)},
        "gate": {"min_rated": GATE_MIN_SIGNAL, "max_rate": GATE_MAX_RATE,
                 "sample_sufficient": gate_met, "passes": gate_pass},
        "items": per_item,
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def render(r: dict) -> str:
    w = r["window"]
    window = "all time" if not (w["since"] or w["until"]) else f"{w['since'] or '…'} → {w['until'] or 'now'}"
    o = r["outcomes"]
    lines = [
        f"Surface Engine dismiss rate ({window})",
        f"  decisions: {r['decisions']}  sent: {r['sent']}  silent: {r['silent']} {r['silent_breakdown']}",
        f"  outcomes:  positive {o['positive']} · negative {o['negative']} · neutral {o['neutral']} · no signal {o['no_signal']}",
        f"  signal coverage: {_pct(r['signal_coverage'])} of sent items have any feedback",
        f"  dismiss rate: {_pct(r['dismiss_rate'])} (n={r['rated_items']})",
        f"    explicit labels: {r['explicit']['labels'] or 'none'} → {_pct(r['explicit']['dismiss_rate'])} (n={r['explicit']['rated']})",
        f"    inferred labels: {r['inferred']['labels'] or 'none'}",
    ]
    g = r["gate"]
    if not g["sample_sufficient"]:
        verdict = f"NOT EVALUABLE — need >= {g['min_rated']} rated items, have {r['rated_items']}"
    else:
        verdict = "PASS" if g["passes"] else "FAIL"
    lines.append(f"  gate (<{int(g['max_rate'] * 100)}% after >= {g['min_rated']}): {verdict}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--since", help="ISO timestamp, inclusive (e.g. 2026-08-01)")
    p.add_argument("--until", help="ISO timestamp, exclusive")
    p.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = p.parse_args(argv)
    if not os.path.exists(args.db):
        print(f"no database at {args.db}", file=sys.stderr)
        return 1
    result = compute(args.db, args.since, args.until)
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
