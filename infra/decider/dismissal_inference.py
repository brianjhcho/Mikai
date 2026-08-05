"""
Dismissal inference — the negative-signal half of the feedback loop.

Any SENT event that has no matching TAPPED after 24h is treated as a
DISMISSED_INFERRED. This gives the ranking layer the shown-but-skipped
signal that Discover treats as ground truth for "user isn't interested."

Idempotent: only inserts DISMISSED_INFERRED if the notif_id has no
existing TAPPED or DISMISSED_INFERRED. Re-runs are safe.

Run via LaunchAgent every hour (com.mikai.dismissal-inference).
Also usable ad-hoc: `python3 dismissal_inference.py --dry-run`.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(
    os.environ.get(
        "MIKAI_DB_PATH",
        str(Path.home() / ".mikai" / "notification_log.db"),
    )
)

DISMISS_AFTER_HOURS = float(os.environ.get("MIKAI_DISMISS_AFTER_HOURS", "24"))


def find_pending_dismissals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return SENT rows older than DISMISS_AFTER_HOURS that have no
    corresponding TAPPED or DISMISSED_INFERRED yet.
    """
    return conn.execute(
        """
        SELECT e1.notif_id, e1.dimension, e1.action_type, e1.next_step_url
        FROM notification_events e1
        WHERE e1.event_type = 'SENT'
          AND datetime(e1.event_ts) < datetime('now', ?)
          AND NOT EXISTS (
              SELECT 1
              FROM notification_events e2
              WHERE e2.notif_id = e1.notif_id
                AND e2.event_type IN ('TAPPED', 'DISMISSED_INFERRED')
          )
        """,
        (f"-{DISMISS_AFTER_HOURS} hours",),
    ).fetchall()


def mark_dismissed(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for r in rows:
        conn.execute(
            """
            INSERT INTO notification_events
                (notif_id, event_type, event_ts, dimension, action_type,
                 next_step_url)
            VALUES (?, 'DISMISSED_INFERRED', ?, ?, ?, ?)
            """,
            (r["notif_id"], now, r["dimension"], r["action_type"],
             r["next_step_url"]),
        )
        n += 1
    conn.commit()
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Show candidates but don't insert.")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"NOTE: DB missing at {DB_PATH}; nothing to do.", file=sys.stderr)
        return 0

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = find_pending_dismissals(conn)
        if not rows:
            print(f"OK: no pending dismissals (threshold={DISMISS_AFTER_HOURS}h)")
            return 0
        if args.dry_run:
            print(f"DRY-RUN: {len(rows)} candidate(s) would be marked DISMISSED_INFERRED:")
            for r in rows:
                print(f"  {r['notif_id']}  dim={r['dimension']}  "
                      f"action={r['action_type']}")
            return 0
        n = mark_dismissed(conn, rows)
        print(f"OK: marked {n} DISMISSED_INFERRED (threshold={DISMISS_AFTER_HOURS}h)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
