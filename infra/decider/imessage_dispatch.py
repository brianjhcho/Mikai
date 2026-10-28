"""Send Surface Engine notifications to Brian's iMessage through Hermes.

Uses the official `hermes send` CLI, which delivers through the live Hermes
gateway's Photon sidecar. The default target "photon" is Hermes's configured
home channel (Brian's own number), so no phone number or secret is read here.

Off unless MIKAI_IMESSAGE=1. A failed send returns (False, reason) for the
caller to log; it never raises, so ntfy dispatch is never blocked.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable

REPLY_HINT = "Reply: done · snooze · not relevant"
SEND_TIMEOUT_S = 30


def imessage_enabled() -> bool:
    return os.environ.get("MIKAI_IMESSAGE", "") == "1"


def hermes_bin() -> str:
    return os.environ.get("MIKAI_HERMES_BIN") or str(Path.home() / ".local" / "bin" / "hermes")


def target() -> str:
    return os.environ.get("MIKAI_IMESSAGE_TARGET") or "photon"


def format_message(title: str, body: str, notif_id: str) -> str:
    return f"{title.strip()}\n\n{body.strip()}\n\n{REPLY_HINT}\nref: {notif_id}"


def send(
    text: str,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[bool, str]:
    cmd = [hermes_bin(), "send", "--to", target(), "--quiet", "--file", "-"]
    try:
        proc = runner(cmd, input=text, capture_output=True, text=True, timeout=SEND_TIMEOUT_S)
    except FileNotFoundError:
        return False, f"hermes_not_found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return False, f"hermes_send_timeout: {SEND_TIMEOUT_S}s"
    except OSError as e:
        return False, f"hermes_send_oserror: {e}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, f"hermes_send_exit_{proc.returncode}: {detail[-1] if detail else 'no output'}"
    return True, "imessage_sent"


OUTBOX_SCHEMA = """CREATE TABLE IF NOT EXISTS imessage_outbox (
    ref TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    kind TEXT NOT NULL,
    sent_at TEXT NOT NULL
)"""


# Messages sent via `hermes send` never enter the Hermes chat session, so a bare
# "done" reply has no context there. The outbox is what lets the MCP side
# (mikai_recent_surfaced) tell Hermes what MIKAI just texted.
def record_outbox(db_path: Path, ref: str, text: str, kind: str = "surface") -> None:
    import sqlite3
    from datetime import datetime, timezone

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(OUTBOX_SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO imessage_outbox (ref, text, kind, sent_at) VALUES (?, ?, ?, ?)",
            (ref, text, kind, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


def _send_test() -> int:
    import secrets

    db = Path(os.environ.get("MIKAI_DB_PATH", str(Path.home() / ".mikai" / "notification_log.db")))
    ref = f"test-{secrets.token_hex(3)}"
    text = format_message("MIKAI test", "Reply 'done' to check that replies get logged.", ref)
    ok, status = send(text)
    print(status)
    if ok:
        record_outbox(db, ref, text, kind="test")
        print(f"recorded {ref} in imessage_outbox")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["--send-test"]:
        raise SystemExit(_send_test())
    print("usage: imessage_dispatch.py --send-test")
    raise SystemExit(2)
