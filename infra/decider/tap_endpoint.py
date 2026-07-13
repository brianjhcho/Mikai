"""
FIGS tap-redirect endpoint.

Every notification carries a Click URL of the form `${TAP_BASE}/t/{notif_id}`.
When the user taps the ntfy card, iOS opens that URL. This tiny HTTP
server:

  1. Looks up the SENT row for that notif_id in the FIGS SQLite DB.
  2. Inserts a TAPPED event.
  3. Returns a 302 to the real next_step_url (Gmail compose, Calendar
     quick-add, Sunsama, etc.).

Runs on the host as a LaunchAgent, port MIKAI_TAP_PORT (default 8200).
Cloudflared quick-tunnel exposes it publicly so the iPhone can reach it
from cellular. The real destination URL never leaves this process — ntfy
only ever sees the redirect URL, so a leaked ntfy log doesn't expose the
user's inboxes.

Stdlib only — no FastAPI dependency in the decider path.

Design notes:
- The DB write is done in-process because there's exactly one tap
  endpoint. If we ever run multiple replicas, use a queue.
- Unknown notif_ids are logged to stderr then returned 404. We don't
  insert a TAPPED row for them because it would skew the ranking signal
  (a bot could inflate any dimension by hitting random IDs).
- Health: `GET /healthz` returns 200 for cloudflared/monitoring.
"""

from __future__ import annotations

import http.server
import json
import logging
import os
import re
import socketserver
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("mikai-tap")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

DB_PATH = Path(
    os.environ.get(
        "MIKAI_DB_PATH",
        str(Path.home() / ".mikai" / "notification_log.db"),
    )
)
PORT = int(os.environ.get("MIKAI_TAP_PORT", "8210"))
HOST = os.environ.get("MIKAI_TAP_HOST", "127.0.0.1")

# notif_id = uuid4().hex[:12] — 12 lowercase hex chars.
NOTIF_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def _lookup_sent(notif_id: str) -> tuple[str | None, str | None, str | None]:
    """Return (next_step_url, dimension, action_type) for the SENT event
    of notif_id, or (None, None, None) if not found.
    """
    if not DB_PATH.exists():
        return (None, None, None)
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=rw", uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT next_step_url, dimension, action_type
            FROM notification_events
            WHERE notif_id = ? AND event_type = 'SENT'
            ORDER BY id DESC
            LIMIT 1
            """,
            (notif_id,),
        ).fetchone()
        conn.close()
        if row is None:
            return (None, None, None)
        return (row["next_step_url"], row["dimension"], row["action_type"])
    except sqlite3.Error as exc:
        logger.warning("DB lookup failed for %s: %s", notif_id, exc)
        return (None, None, None)


def _log_tapped(
    notif_id: str,
    dimension: str | None,
    action_type: str | None,
    next_step_url: str | None,
) -> None:
    """Best-effort log of the TAPPED event. Never raises."""
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=rw", uri=True, timeout=2.0)
        conn.execute(
            """
            INSERT INTO notification_events
                (notif_id, event_type, event_ts, dimension, action_type,
                 next_step_url)
            VALUES (?, 'TAPPED', ?, ?, ?, ?)
            """,
            (
                notif_id,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                dimension,
                action_type,
                next_step_url,
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as exc:
        # Do NOT block redirect on log failure — better to lose one tap
        # event than strand the user on a spinner.
        logger.warning("could not log TAPPED for %s: %s", notif_id, exc)


class TapHandler(http.server.BaseHTTPRequestHandler):
    server_version = "MikaiTap/1.0"

    def do_GET(self) -> None:  # noqa: N802 — stdlib API
        path = self.path.split("?", 1)[0]

        if path == "/healthz":
            self._reply(200, "text/plain", b"ok\n")
            return

        m = re.match(r"^/t/([^/]+)$", path)
        if not m:
            self._reply(404, "text/plain", b"not found\n")
            return

        notif_id = m.group(1)
        if not NOTIF_ID_RE.match(notif_id):
            logger.info("rejected malformed notif_id=%r", notif_id)
            self._reply(404, "text/plain", b"not found\n")
            return

        next_url, dimension, action_type = _lookup_sent(notif_id)
        if next_url is None:
            logger.info("unknown or expired notif_id=%s", notif_id)
            self._reply(404, "text/plain", b"not found\n")
            return

        _log_tapped(notif_id, dimension, action_type, next_url)
        # 302 (not 301) so browsers/iOS don't cache the redirect.
        self.send_response(302)
        self.send_header("Location", next_url)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()
        logger.info(
            "TAPPED notif_id=%s dim=%s action=%s → %s",
            notif_id, dimension, action_type,
            (next_url[:80] + "…") if next_url and len(next_url) > 80 else next_url,
        )

    def _reply(self, status: int, ctype: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Route BaseHTTPServer's noisy default logs through our logger at DEBUG,
    # so INFO logs stay clean.
    def log_message(self, fmt: str, *args) -> None:  # noqa: N802
        logger.debug("access: " + fmt, *args)


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    logger.info("MIKAI tap endpoint starting on %s:%d (DB=%s)",
                HOST, PORT, DB_PATH)
    if not DB_PATH.exists():
        logger.warning("DB does not exist yet at %s — every tap will 404 "
                       "until mikai_decide.py --init runs.", DB_PATH)
    try:
        server = ThreadedServer((HOST, PORT), TapHandler)
    except OSError as exc:
        logger.error("could not bind %s:%d: %s", HOST, PORT, exc)
        return 1
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
