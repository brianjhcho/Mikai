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

import html
import http.server
import json
import logging
import os
import re
import socketserver
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import request as urlreq

# caldav_client is stdlib-only, so importing it at module load is safe even
# if iCloud creds aren't configured. The client constructor is the layer
# that requires MIKAI_ICLOUD_{USER,APP_PASSWORD}.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from caldav_client import ICloudCalDAV, CalDAVError, Event  # noqa: E402

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
# proposal_id has the same shape (uuid4().hex[:12] in calendar_planner.py).
PROPOSAL_ID_RE = NOTIF_ID_RE

# A proposal not resolved within this window auto-EXPIREs on next lookup.
PROPOSAL_EXPIRY_HOURS = float(os.environ.get("MIKAI_PROPOSAL_EXPIRY_H", "4"))

NTFY_BASE_URL = os.environ.get("MIKAI_NTFY_BASE", "https://ntfy.sh")
NTFY_TOPIC = os.environ.get("MIKAI_NTFY_TOPIC", "")


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


# ── Calendar-proposal approval loop (D-055) ────────────────────────────


def _open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=rw", uri=True, timeout=2.0)
    conn.row_factory = sqlite3.Row
    return conn


def _lookup_proposal(proposal_id: str) -> sqlite3.Row | None:
    if not DB_PATH.exists():
        return None
    try:
        conn = _open_db()
        row = conn.execute(
            "SELECT * FROM calendar_proposals WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        conn.close()
        return row
    except sqlite3.Error as exc:
        logger.warning("proposal lookup failed for %s: %s", proposal_id, exc)
        return None


def _parse_ts_utc(v: str) -> datetime | None:
    """Parse either an ISO-8601 aware timestamp (what the planner writes)
    or a SQLite `datetime('now')` naive string (`'YYYY-MM-DD HH:MM:SS'`).
    Naive values are assumed UTC — which matches SQLite's default.
    """
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace(" ", "T"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _mark_expired_if_stale(row: sqlite3.Row) -> str:
    """If row is PROPOSED and older than PROPOSAL_EXPIRY_HOURS, mark it
    EXPIRED and return the new status; else return the original status.
    """
    if row["status"] != "PROPOSED":
        return row["status"]
    proposed_at = _parse_ts_utc(row["proposed_at"])
    if proposed_at is None:
        return row["status"]
    if datetime.now(timezone.utc) - proposed_at <= timedelta(hours=PROPOSAL_EXPIRY_HOURS):
        return row["status"]
    try:
        conn = _open_db()
        conn.execute(
            "UPDATE calendar_proposals SET status='EXPIRED', resolved_at=? "
            "WHERE proposal_id=? AND status='PROPOSED'",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),
             row["proposal_id"]),
        )
        conn.commit()
        conn.close()
        logger.info("expired proposal %s (proposed_at=%s > %sh)",
                    row["proposal_id"], row["proposed_at"], PROPOSAL_EXPIRY_HOURS)
        return "EXPIRED"
    except sqlite3.Error as exc:
        logger.warning("expiry update failed for %s: %s", row["proposal_id"], exc)
        return row["status"]


def _finalize_proposal(
    proposal_id: str,
    new_status: str,
    apply_error: str | None = None,
    new_etag: str | None = None,
) -> None:
    """Atomically flip PROPOSED → new_status. If the row is already in a
    non-PROPOSED state, the UPDATE hits 0 rows and we return without side
    effects — idempotent by construction.
    """
    try:
        conn = _open_db()
        conn.execute(
            """
            UPDATE calendar_proposals
            SET status = ?,
                resolved_at = ?,
                apply_error = COALESCE(?, apply_error),
                event_etag = COALESCE(?, event_etag)
            WHERE proposal_id = ? AND status = 'PROPOSED'
            """,
            (
                new_status,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                apply_error, new_etag, proposal_id,
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as exc:
        logger.warning("finalize failed for %s: %s", proposal_id, exc)


def _apply_to_icloud(row: sqlite3.Row) -> tuple[bool, str, str]:
    """Refetch the event by UID (etag may have drifted), PATCH SUMMARY +
    DESCRIPTION, return (ok, message, new_etag).
    """
    user = os.environ.get("MIKAI_ICLOUD_USER", "")
    pw = os.environ.get("MIKAI_ICLOUD_APP_PASSWORD", "")
    if not user or not pw:
        return (False, "iCloud creds missing on the tap-endpoint host", "")
    try:
        client = ICloudCalDAV(user, pw)
        # Refetch by scanning today's events on all calendars until the UID matches
        # — safer than PUTting with the stored stale etag.
        events = client.todays_events(sole_attendee_only=False)
        target = next((e for e in events if e.uid == row["event_uid"]), None)
        if target is None:
            # Not on today's list — maybe the user moved the block. Try a
            # direct GET against the stored href as a last resort.
            return (False, f"event UID {row['event_uid']} no longer in today's range", "")
        new_etag = client.patch_event(
            target,
            new_title=row["proposed_title"],
            new_description=row["proposed_description"],
        )
        return (True, "applied", new_etag or "")
    except CalDAVError as exc:
        return (False, f"CalDAV error: {exc}", "")


def _send_confirmation_ntfy(title: str, body: str) -> None:
    if not NTFY_TOPIC:
        return
    try:
        req = urlreq.Request(
            f"{NTFY_BASE_URL}/{NTFY_TOPIC}",
            data=body.encode("utf-8"),
            method="POST",
            headers={"Title": title, "Priority": "3", "Tags": "mikai,calendar"},
        )
        with urlreq.urlopen(req, timeout=8):
            pass
    except Exception as exc:
        logger.warning("confirmation ntfy failed: %s", exc)


# ── Approval / rejection HTML confirmation pages ───────────────────────


_PAGE_CSS = (
    "font-family:-apple-system,BlinkMacSystemFont,sans-serif;"
    "max-width:520px;margin:48px auto;padding:0 24px;"
    "line-height:1.55;color:#111"
)


def _confirmation_page(headline: str, sub: str, current: str, proposed: str,
                       accent: str) -> bytes:
    return (
        f"<!doctype html><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(headline)}</title>"
        f"<div style='{_PAGE_CSS}'>"
        f"<h2 style='color:{accent};margin-bottom:6px'>{html.escape(headline)}</h2>"
        f"<p style='color:#666;margin-top:0'>{html.escape(sub)}</p>"
        f"<hr style='border:none;border-top:1px solid #eee;margin:24px 0'>"
        f"<div style='color:#888;font-size:13px'>Was</div>"
        f"<div>{html.escape(current)}</div>"
        f"<div style='color:#888;font-size:13px;margin-top:14px'>Now</div>"
        f"<div style='font-weight:600'>{html.escape(proposed)}</div>"
        f"</div>"
    ).encode()


class TapHandler(http.server.BaseHTTPRequestHandler):
    server_version = "MikaiTap/1.0"

    def do_GET(self) -> None:  # noqa: N802 — stdlib API
        path = self.path.split("?", 1)[0]

        if path == "/healthz":
            self._reply(200, "text/plain", b"ok\n")
            return

        m = re.match(r"^/t/([^/]+)$", path)
        if m:
            self._handle_tap(m.group(1))
            return

        m = re.match(r"^/approve/([^/]+)$", path)
        if m:
            self._handle_proposal(m.group(1), approve=True)
            return

        m = re.match(r"^/reject/([^/]+)$", path)
        if m:
            self._handle_proposal(m.group(1), approve=False)
            return

        self._reply(404, "text/plain", b"not found\n")

    # ── Route handlers ────────────────────────────────────────────────

    def _handle_tap(self, notif_id: str) -> None:
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

    def _handle_proposal(self, proposal_id: str, approve: bool) -> None:
        if not PROPOSAL_ID_RE.match(proposal_id):
            logger.info("rejected malformed proposal_id=%r", proposal_id)
            self._reply(404, "text/plain", b"not found\n")
            return

        row = _lookup_proposal(proposal_id)
        if row is None:
            logger.info("unknown proposal_id=%s", proposal_id)
            self._reply(404, "text/plain", b"not found\n")
            return

        status = _mark_expired_if_stale(row)

        # Idempotent second-tap: if already resolved, show the final state.
        if status != "PROPOSED":
            label = {
                "APPLIED": ("✓ Already applied", "#0a7d3a"),
                "REJECTED": ("✗ Already rejected", "#a11a1a"),
                "EXPIRED": ("⌛ Proposal expired", "#8a6f00"),
            }.get(status, (f"Status: {status}", "#333"))
            self._reply(
                200, "text/html; charset=utf-8",
                _confirmation_page(
                    label[0],
                    "This proposal was resolved earlier — no change made now.",
                    row["current_title"] or "",
                    row["proposed_title"] or "",
                    label[1],
                ),
            )
            return

        if not approve:
            _finalize_proposal(proposal_id, "REJECTED")
            logger.info("REJECTED proposal_id=%s", proposal_id)
            self._reply(
                200, "text/html; charset=utf-8",
                _confirmation_page(
                    "✗ Rejected",
                    "Calendar block left untouched. MIKAI will try again tomorrow.",
                    row["current_title"] or "",
                    row["proposed_title"] or "",
                    "#a11a1a",
                ),
            )
            return

        # Approve path — call iCloud CalDAV.
        ok, msg, new_etag = _apply_to_icloud(row)
        if not ok:
            _finalize_proposal(proposal_id, "PROPOSED",
                               apply_error=msg[:400])  # stay PROPOSED so retry works
            # Actually the UPDATE has WHERE status='PROPOSED', so no
            # transition happens — apply_error still isn't recorded that way.
            # Do it directly:
            try:
                conn = _open_db()
                conn.execute(
                    "UPDATE calendar_proposals SET apply_error = ? "
                    "WHERE proposal_id = ?",
                    (msg[:400], proposal_id),
                )
                conn.commit()
                conn.close()
            except sqlite3.Error:
                pass
            logger.warning("APPLY FAILED proposal_id=%s: %s", proposal_id, msg)
            self._reply(
                500, "text/html; charset=utf-8",
                _confirmation_page(
                    "⚠ Could not apply",
                    f"iCloud rejected the change: {msg}",
                    row["current_title"] or "",
                    row["proposed_title"] or "",
                    "#a11a1a",
                ),
            )
            return

        _finalize_proposal(proposal_id, "APPLIED", new_etag=new_etag or None)
        logger.info("APPLIED proposal_id=%s → %r", proposal_id, row["proposed_title"])
        _send_confirmation_ntfy(
            "✓ MIKAI updated your block",
            f"Rewrote {row['current_title']!r} → {row['proposed_title']!r}",
        )
        self._reply(
            200, "text/html; charset=utf-8",
            _confirmation_page(
                "✓ Applied",
                "Your iCloud calendar was updated. iPhone should refresh in a few seconds.",
                row["current_title"] or "",
                row["proposed_title"] or "",
                "#0a7d3a",
            ),
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
