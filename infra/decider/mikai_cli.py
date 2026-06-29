"""
mikai_cli.py — CLI for capturing user response to FIGS notifications.

V1 instrumentation: ntfy.sh's iOS app doesn't report click/dismiss
back to FIGS, so Brian uses this CLI to close the feedback loop.

Commands:
  mikai-cli mark-acted [LOG_ID]        # ACTED on most-recent dispatch (or specified)
  mikai-cli mark-dismissed [LOG_ID]    # DISMISSED
  mikai-cli snooze [LOG_ID] DAYS       # SNOOZED for N days
  mikai-cli status                     # show last 20 dispatches
  mikai-cli metrics                    # productivity, proactivity, personalization, calibration

See docs/FIGS_LOSS_FUNCTION.md §8 for the response-capture protocol.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get(
    "MIKAI_DB_PATH",
    str(Path.home() / ".mikai" / "notification_log.db"),
))


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(f"ERROR: notification log not found at {DB_PATH}", file=sys.stderr)
        print("Run `python3 infra/decider/mikai_decide.py --init` first.", file=sys.stderr)
        sys.exit(2)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Ensure V1 loss-function columns exist. Idempotent."""
    cur = conn.execute("PRAGMA table_info(notification_log)")
    cols = {row["name"] for row in cur.fetchall()}
    additions = [
        ("time_to_response_seconds", "INTEGER"),
        ("candidate_source",          "TEXT"),
        ("candidate_slug",            "TEXT"),
        ("figs_confidence",           "REAL"),
        ("acted_within_24h",          "INTEGER"),
    ]
    for col, ddl in additions:
        if col not in cols:
            conn.execute(f"ALTER TABLE notification_log ADD COLUMN {col} {ddl}")
    conn.commit()


def _most_recent_sent_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT id FROM notification_log WHERE sent=1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["id"] if row else None


def _resolve_log_id(conn: sqlite3.Connection, raw: str | None) -> int | None:
    if raw is None or raw == "":
        return _most_recent_sent_id(conn)
    try:
        return int(raw)
    except ValueError:
        print(f"ERROR: '{raw}' is not a valid log id.", file=sys.stderr)
        return None


def _mark_response(conn: sqlite3.Connection, log_id: int, response: str) -> bool:
    """Record a response. Computes time_to_response_seconds from tick_ts.

    Returns True if a row was updated.
    """
    row = conn.execute(
        "SELECT tick_ts, sent FROM notification_log WHERE id=?", (log_id,)
    ).fetchone()
    if not row:
        print(f"ERROR: no log entry with id={log_id}", file=sys.stderr)
        return False
    if not row["sent"]:
        print(f"ERROR: log entry {log_id} was not dispatched (sent=0); cannot mark response", file=sys.stderr)
        return False

    now = datetime.now(timezone.utc)
    delta_seconds: int | None = None
    try:
        tick = datetime.fromisoformat(row["tick_ts"])
        if tick.tzinfo is None:
            tick = tick.replace(tzinfo=timezone.utc)
        delta_seconds = int((now - tick).total_seconds())
    except (ValueError, TypeError):
        delta_seconds = None

    acted_within_24h = 1 if (response == "ACTED" and delta_seconds is not None and delta_seconds <= 86400) else 0

    conn.execute(
        """
        UPDATE notification_log
        SET user_response = ?,
            response_at   = ?,
            time_to_response_seconds = ?,
            acted_within_24h = COALESCE(acted_within_24h, ?)
        WHERE id = ?
        """,
        (response, now.isoformat(timespec="seconds"), delta_seconds, acted_within_24h, log_id),
    )
    conn.commit()
    return True


# ── Commands ────────────────────────────────────────────────────────────


def cmd_mark_acted(conn: sqlite3.Connection, log_id_raw: str | None) -> int:
    lid = _resolve_log_id(conn, log_id_raw)
    if lid is None:
        return 1
    if not _mark_response(conn, lid, "ACTED"):
        return 1
    print(f"✓ marked {lid} ACTED")
    return 0


def cmd_mark_dismissed(conn: sqlite3.Connection, log_id_raw: str | None) -> int:
    lid = _resolve_log_id(conn, log_id_raw)
    if lid is None:
        return 1
    if not _mark_response(conn, lid, "DISMISSED"):
        return 1
    print(f"✓ marked {lid} DISMISSED")
    return 0


def cmd_snooze(conn: sqlite3.Connection, log_id_raw: str | None, days: int) -> int:
    lid = _resolve_log_id(conn, log_id_raw)
    if lid is None:
        return 1
    if days <= 0:
        print("ERROR: days must be positive", file=sys.stderr)
        return 1
    if not _mark_response(conn, lid, "SNOOZED"):
        return 1
    # Also remember the snooze duration in the reasoning field (low-effort, no schema bump)
    conn.execute(
        "UPDATE notification_log SET not_sent_reason = COALESCE(not_sent_reason,'') || ' snooze_until=' || ? WHERE id=?",
        ((datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds"), lid),
    )
    conn.commit()
    print(f"✓ marked {lid} SNOOZED for {days} days")
    return 0


def cmd_status(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        """
        SELECT id, tick_ts, sent, title, user_response, response_at,
               time_to_response_seconds, candidate_slug
        FROM notification_log
        ORDER BY id DESC LIMIT 20
        """
    ).fetchall()
    if not rows:
        print("(empty log)")
        return 0
    print(f"{'ID':>4} {'TS':<20} {'SENT':<5} {'RESP':<10} {'TTR':>8}  TITLE / SLUG")
    print("-" * 88)
    for r in rows:
        sent = "yes" if r["sent"] else "—"
        resp = r["user_response"] or "—"
        ttr = (str(r["time_to_response_seconds"]) + "s") if r["time_to_response_seconds"] else "—"
        title = (r["title"] or "—")[:40]
        slug = r["candidate_slug"] or ""
        ts = (r["tick_ts"] or "?")[:19]
        print(f"{r['id']:>4} {ts:<20} {sent:<5} {resp:<10} {ttr:>8}  {title}{(' ['+slug+']') if slug else ''}")
    return 0


def cmd_metrics(conn: sqlite3.Connection) -> int:
    """Compute productivity, proactivity, personalization, calibration."""
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    rows = conn.execute(
        """
        SELECT user_response, sent, time_to_response_seconds, figs_confidence
        FROM notification_log
        WHERE tick_ts > ?
        """,
        (seven_days_ago,),
    ).fetchall()
    total = len(rows)
    sent = [r for r in rows if r["sent"]]
    n_sent = len(sent)
    n_acted = sum(1 for r in sent if r["user_response"] == "ACTED")
    n_dismissed = sum(1 for r in sent if r["user_response"] == "DISMISSED")
    n_snoozed = sum(1 for r in sent if r["user_response"] == "SNOOZED")
    n_ignored = sum(1 for r in sent if not r["user_response"])

    print(f"=== FIGS metrics (last 7 days) ===")
    print(f"  total ticks:         {total}")
    print(f"  notifications sent:  {n_sent}")
    print(f"    acted:    {n_acted}")
    print(f"    dismissed:{n_dismissed}")
    print(f"    snoozed:  {n_snoozed}")
    print(f"    ignored:  {n_ignored}")
    print()
    if n_sent == 0:
        print("  (no sent dispatches yet — metrics unmeasured)")
        return 0
    productivity = n_acted / n_sent
    dismiss_rate = n_dismissed / n_sent
    ignore_rate = n_ignored / n_sent

    ttrs = [r["time_to_response_seconds"] for r in sent
            if r["user_response"] == "ACTED" and r["time_to_response_seconds"]]
    median_ttr = "—"
    if ttrs:
        ttrs_sorted = sorted(ttrs)
        median_ttr = f"{ttrs_sorted[len(ttrs_sorted)//2]/3600:.1f}h"

    personalization = max(0.0, 1 - dismiss_rate / 0.30)

    L = 1.0 * dismiss_rate + 0.5 * ignore_rate - 2.0 * productivity
    if ttrs:
        L -= 0.1 * (1.0 / (sum(ttrs) / len(ttrs) / 3600.0))

    print(f"  PPP metrics (FIGS_LOSS_FUNCTION.md §4):")
    print(f"    productivity:    {productivity:.2f}  (act/sent)")
    print(f"    proactivity:     N/A     (no reactive surface in V1)")
    print(f"    personalization: {personalization:.2f}  (1 - dismiss_rate/0.30, PPP threshold)")
    print(f"    calibration:     N/A     (need figs_confidence per dispatch — V1.5)")
    print(f"  Loss (lower better): {L:+.2f}")
    print(f"  Median time-to-act:  {median_ttr}")
    return 0


# ── Entry point ─────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(prog="mikai", description="FIGS response-capture CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("mark-acted", help="Mark the most recent dispatch (or a specified id) as ACTED")
    a.add_argument("log_id", nargs="?", default=None)

    d = sub.add_parser("mark-dismissed", help="Mark as DISMISSED")
    d.add_argument("log_id", nargs="?", default=None)

    s = sub.add_parser("snooze", help="Mark as SNOOZED for N days")
    s.add_argument("log_id", nargs="?", default=None)
    s.add_argument("days", type=int, default=7, nargs="?", help="Default 7")

    sub.add_parser("status", help="Show last 20 dispatches")
    sub.add_parser("metrics", help="Show productivity/personalization/loss metrics")

    args = parser.parse_args()
    conn = _connect()
    _ensure_schema(conn)

    if args.cmd == "mark-acted":
        return cmd_mark_acted(conn, args.log_id)
    if args.cmd == "mark-dismissed":
        return cmd_mark_dismissed(conn, args.log_id)
    if args.cmd == "snooze":
        return cmd_snooze(conn, args.log_id, args.days)
    if args.cmd == "status":
        return cmd_status(conn)
    if args.cmd == "metrics":
        return cmd_metrics(conn)
    return 2


if __name__ == "__main__":
    sys.exit(main())
