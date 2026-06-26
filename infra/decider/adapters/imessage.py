"""
iMessage adapter — reads ~/Library/Messages/chat.db (SQLite, no auth).

Requires:
  - Full Disk Access for the running Python interpreter
    (System Settings → Privacy & Security → Full Disk Access → +)

On newer macOS, message text is often stored in `attributedBody` (a
NSKeyedArchiver plist blob) rather than `text`. We pull `text` when
available; messages with only `attributedBody` are tagged
`[content_in_attributedBody]` so the decider knows a message exists.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"

# Apple Cocoa epoch: 2001-01-01 UTC = 978307200 unix seconds
COCOA_EPOCH_OFFSET = 978307200


def recent_events(hours: int = 24, limit: int = 100) -> list[dict]:
    """Return iMessage events from the last `hours` hours."""
    if not CHAT_DB.exists():
        return [{"source": "imessage", "error": f"chat.db not found at {CHAT_DB}"}]

    cutoff_ns = int((datetime.now().timestamp() - hours * 3600 - COCOA_EPOCH_OFFSET) * 1e9)

    try:
        conn = sqlite3.connect(f"file:{CHAT_DB}?mode=ro&immutable=1", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.OperationalError as e:
        return [{"source": "imessage",
                 "error": f"cannot open chat.db: {e}. Grant Full Disk Access to your Python interpreter."}]

    query = """
        SELECT
            datetime(message.date/1000000000 + 978307200, 'unixepoch', 'localtime') AS ts,
            message.is_from_me,
            message.text,
            message.attributedBody IS NOT NULL AS has_attributed_body,
            handle.id AS contact,
            chat.display_name AS chat_name,
            chat.chat_identifier AS chat_id,
            message.is_read
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        LEFT JOIN chat_message_join ON chat_message_join.message_id = message.ROWID
        LEFT JOIN chat ON chat.ROWID = chat_message_join.chat_id
        WHERE message.date > ?
        ORDER BY message.date DESC
        LIMIT ?
    """

    try:
        rows = conn.execute(query, (cutoff_ns, limit)).fetchall()
    except sqlite3.OperationalError as e:
        return [{"source": "imessage", "error": f"query failed: {e}"}]

    events = []
    for r in rows:
        content = r["text"]
        if not content and r["has_attributed_body"]:
            content = "[content_in_attributedBody]"
        if not content:
            continue

        chat_label = r["chat_name"] or r["chat_id"] or (r["contact"] or "unknown")
        sender = "me" if r["is_from_me"] else (r["contact"] or "unknown")

        events.append({
            "source": "imessage",
            "timestamp": r["ts"],
            "sender": sender,
            "content": content[:500],
            "chat": chat_label,
            "is_action_required": (not r["is_from_me"] and not r["is_read"]),
        })

    conn.close()
    return events


if __name__ == "__main__":
    import json
    import sys
    events = recent_events(hours=24)
    print(json.dumps(events[:10], indent=2))
    print(f"\nTotal events in last 24h: {len(events)}", file=sys.stderr)
