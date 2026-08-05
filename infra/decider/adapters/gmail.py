"""
Gmail adapter — reads recent emails via IMAP with an app-specific password.

Requires (one-time setup):
  1. Enable 2-Step Verification on your Google account
     (https://myaccount.google.com/security)
  2. Create an App password for "Mail":
     https://myaccount.google.com/apppasswords
  3. Add to your .env.local:
       MIKAI_GMAIL_USER="you@gmail.com"
       MIKAI_GMAIL_APP_PASSWORD="<16-char app password, no spaces>"

Pulls recent inbox + unread items. Uses Python stdlib only (imaplib).
"""
from __future__ import annotations

import email
import imaplib
import os
from datetime import datetime, timedelta
from email.header import decode_header


IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


def _decode_str(s: str | None) -> str:
    if not s:
        return ""
    parts = decode_header(s)
    out = []
    for text, encoding in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(encoding or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def recent_emails(hours: int = 24, limit: int = 50) -> list[dict]:
    user = os.environ.get("MIKAI_GMAIL_USER", "")
    pw = os.environ.get("MIKAI_GMAIL_APP_PASSWORD", "")
    if not user or not pw:
        return [{
            "source": "gmail",
            "error": ("MIKAI_GMAIL_USER and MIKAI_GMAIL_APP_PASSWORD env vars not set. "
                      "See adapters/gmail.py docstring for setup.")
        }]

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(user, pw)
    except imaplib.IMAP4.error as e:
        return [{"source": "gmail", "error": f"login failed: {e}"}]
    except Exception as e:
        return [{"source": "gmail", "error": f"connection failed: {e}"}]

    try:
        status, _ = mail.select("INBOX", readonly=True)
        if status != "OK":
            return [{"source": "gmail", "error": "could not select INBOX"}]

        since = (datetime.now() - timedelta(hours=hours)).strftime("%d-%b-%Y")
        status, data = mail.search(None, f'(SINCE "{since}")')
        if status != "OK" or not data or not data[0]:
            return []

        msg_ids = data[0].split()[-limit:]

        events: list[dict] = []
        for msg_id in reversed(msg_ids):  # newest first
            status, msg_data = mail.fetch(
                msg_id,
                "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE TO)])"
            )
            if status != "OK" or not msg_data:
                continue

            flags_bytes = b""
            header_bytes = b""
            for chunk in msg_data:
                if isinstance(chunk, tuple) and len(chunk) >= 2:
                    flags_bytes = chunk[0] or b""
                    header_bytes = chunk[1] or b""
                    break

            is_unread = b"\\Seen" not in flags_bytes
            msg = email.message_from_bytes(header_bytes)

            events.append({
                "source": "gmail",
                "timestamp": _decode_str(msg.get("Date")),
                "sender": _decode_str(msg.get("From")),
                "to": _decode_str(msg.get("To"))[:200],
                "subject": _decode_str(msg.get("Subject"))[:200],
                "is_unread": is_unread,
                "is_action_required": is_unread,
            })

        return events
    finally:
        try:
            mail.close()
        except Exception:
            pass
        try:
            mail.logout()
        except Exception:
            pass


if __name__ == "__main__":
    import json
    import sys
    events = recent_emails(hours=24)
    print(json.dumps(events[:10], indent=2))
    print(f"\nTotal recent emails (last 24h): {len(events)}", file=sys.stderr)
