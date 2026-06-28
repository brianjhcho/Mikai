"""
MIKAI Claude.ai thread ingestion — closes the claude-thread gap.

The filesystem daemon (sync.py) ingests Apple Notes + Claude Code JSONL, but
Claude.ai web/desktop conversations live in Anthropic's cloud, not on disk, so
the `claude-thread` source had ZERO episodes. This script fills that gap by
pulling conversations from the claude.ai internal web API and ingesting each
message as an episode (group_id="claude-thread"), exactly mirroring how
sync.py ingests Claude Code turns.

Auth: the script decrypts the live `sessionKey` cookie the Claude **desktop
app** stores in ~/Library/Application Support/Claude/Cookies, using the
"Claude Safe Storage" AES key from the macOS Keychain. Because the desktop app
refreshes that cookie as you use it, this is self-renewing — no monthly manual
token paste (which is the silent-failure trap we're avoiding). If decryption is
unavailable (no Keychain access under some launchd setups), set CLAUDE_SESSION_KEY
in ~/.mikai/launchd.env as a fallback.

State: ~/.mikai/claude_threads_state.json maps conversation uuid -> ISO
timestamp of the most recent message already ingested. Only newer messages are
ingested on subsequent runs, so re-running is cheap and idempotent.

Usage:
    python claude_threads.py --once                 # one pass (watermark-based)
    python claude_threads.py --once --since-days 7  # only convs touched in 7d
    python claude_threads.py --once --dry-run       # log, don't ingest
    python claude_threads.py --once --all           # ignore window (full backfill)

The daily launchd job runs `--once --since-days 7`: cheap, and the watermark
keeps it idempotent. Run `--once --all` once by hand to backfill history.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sidecar.l3 import Episode, make_backend
from sidecar.ingest import load_state as _load_state_at, save_state as _save_state_at

logger = logging.getLogger("mikai-claude-threads")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# ── Paths / constants ─────────────────────────────────────────────────────────

MIKAI_DIR = Path.home() / ".mikai"
STATE_PATH = MIKAI_DIR / "claude_threads_state.json"

COOKIES_DB = Path.home() / "Library" / "Application Support" / "Claude" / "Cookies"
KEYCHAIN_SERVICE = "Claude Safe Storage"

GROUP_ID = "claude-thread"
SOURCE_DESCRIPTION = "claude-thread"
API_BASE = "https://claude.ai/api"

EPISODE_DELAY_SECONDS = 2.0  # protect Neo4j during ingest, same as sync.py
HTTP_TIMEOUT = 60.0

# Browser-like headers; the per-conversation endpoint 403s without Referer /
# Origin / anthropic-client-platform (Cloudflare gating).
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _base_headers(session_key: str) -> dict[str, str]:
    return {
        "Cookie": f"sessionKey={session_key}",
        "User-Agent": _UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://claude.ai",
        "Referer": "https://claude.ai/recents",
        "anthropic-client-platform": "web_claude_ai",
    }


# ── Session key (Keychain decrypt, env fallback) ──────────────────────────────


def _keychain_password() -> str:
    out = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", KEYCHAIN_SERVICE],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError(
            f"Keychain read of {KEYCHAIN_SERVICE!r} failed (rc={out.returncode}): "
            f"{out.stderr.strip()}"
        )
    return out.stdout.strip()


def _decrypt_chromium_cookie(encrypted: bytes, keychain_pw: str) -> str:
    """Decrypt a macOS Chromium/Electron v10 cookie value.

    PBKDF2-HMAC-SHA1(pw, salt='saltysalt', iter=1003, len=16) -> AES-128-CBC
    with a 16-space IV. Newer Chromium prepends a 32-byte SHA256 domain hash to
    the plaintext; we slice it off if the value doesn't look like an sk-ant key.
    """
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = hashlib.pbkdf2_hmac("sha1", keychain_pw.encode(), b"saltysalt", 1003, dklen=16)
    decryptor = Cipher(
        algorithms.AES(key), modes.CBC(b" " * 16), backend=default_backend()
    ).decryptor()
    body = encrypted[3:]  # strip "v10" version prefix
    plaintext = decryptor.update(body) + decryptor.finalize()
    plaintext = plaintext[: -plaintext[-1]]  # strip PKCS7 padding
    text = plaintext.decode("utf-8", "replace")
    if not text.startswith("sk-ant"):
        text = plaintext[32:].decode("utf-8", "replace")
    return text


def _safe_storage_password() -> str:
    """The 'Claude Safe Storage' AES password.

    Prefer CLAUDE_SAFE_STORAGE_PW from the environment — this is how the launchd
    job avoids a Keychain access prompt, which hangs under a LaunchAgent (the
    authorization dialog can't be shown non-interactively). That password is
    set once when the desktop app is installed and never rotates, so caching it
    in ~/.mikai/launchd.env is safe and durable. Fall back to a live Keychain
    read for interactive/manual runs.
    """
    cached = os.environ.get("CLAUDE_SAFE_STORAGE_PW", "").strip()
    if cached:
        return cached
    return _keychain_password()


def read_session_key() -> str:
    """Resolve the live sessionKey. Order: explicit CLAUDE_SESSION_KEY override,
    else decrypt the desktop cookie using the Safe Storage password (cached env
    var or Keychain)."""
    env_key = os.environ.get("CLAUDE_SESSION_KEY", "").strip()
    if env_key:
        logger.info("Using CLAUDE_SESSION_KEY from environment.")
        return env_key
    if not COOKIES_DB.exists():
        raise RuntimeError(
            f"Claude desktop cookie store not found at {COOKIES_DB}. "
            "Open the Claude desktop app and sign in, or set CLAUDE_SESSION_KEY."
        )
    keychain_pw = _safe_storage_password()
    # Copy the DB so we don't fight the app's write lock.
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        shutil.copy(COOKIES_DB, tmp_path)
        con = sqlite3.connect(tmp_path)
        row = con.execute(
            "SELECT encrypted_value FROM cookies "
            "WHERE name='sessionKey' AND host_key='.claude.ai'"
        ).fetchone()
        con.close()
    finally:
        tmp_path.unlink(missing_ok=True)
    if not row:
        raise RuntimeError("sessionKey cookie not found — sign in to Claude desktop.")
    key = _decrypt_chromium_cookie(row[0], keychain_pw)
    if not key.startswith("sk-ant"):
        raise RuntimeError("Decrypted sessionKey does not look valid (no sk-ant prefix).")
    return key


# ── claude.ai API ─────────────────────────────────────────────────────────────


def resolve_org_id(client: httpx.Client) -> str:
    """Env override (CLAUDE_ORG_ID) else first org from /api/organizations."""
    env_org = os.environ.get("CLAUDE_ORG_ID", "").strip()
    if env_org:
        return env_org
    r = client.get(f"{API_BASE}/organizations")
    r.raise_for_status()
    orgs = r.json()
    if not orgs:
        raise RuntimeError("No organizations returned for this account.")
    # Prefer an org that can chat; otherwise take the first.
    for org in orgs:
        caps = org.get("capabilities") or []
        if "chat" in caps:
            return org["uuid"]
    return orgs[0]["uuid"]


def list_conversations(client: httpx.Client, org_id: str) -> list[dict]:
    """All conversations (uuid, name, updated_at), newest-first, paginated."""
    out: list[dict] = []
    offset = 0
    page = 100
    while True:
        r = client.get(
            f"{API_BASE}/organizations/{org_id}/chat_conversations",
            params={"limit": page, "offset": offset},
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        offset += len(batch)
        if len(batch) < page:
            break
    return out


def fetch_messages(client: httpx.Client, org_id: str, conv_uuid: str) -> list[dict]:
    """Fetch a conversation's chat_messages (sender, text, created_at)."""
    r = client.get(
        f"{API_BASE}/organizations/{org_id}/chat_conversations/{conv_uuid}",
        params={"tree": "True", "rendering_mode": "raw"},
    )
    r.raise_for_status()
    return r.json().get("chat_messages", []) or []


# ── Time helpers ──────────────────────────────────────────────────────────────


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _message_text(msg: dict) -> str:
    """Prefer the flat `text` field; fall back to assembling content blocks."""
    text = (msg.get("text") or "").strip()
    if text:
        return text
    parts: list[str] = []
    for block in msg.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append((block.get("text") or "").strip())
    return "\n".join(p for p in parts if p)


# ── Main pass ─────────────────────────────────────────────────────────────────


async def run_once(*, dry_run: bool, since_days: int | None, max_convs: int | None) -> None:
    session_key = read_session_key()
    logger.info("Session key acquired (%d chars).", len(session_key))

    state = _load_state_at(STATE_PATH)  # {conv_uuid: last_ingested_msg_iso}
    cutoff = (
        datetime.now(tz=timezone.utc) - timedelta(days=since_days)
        if since_days is not None
        else None
    )

    backend = None if dry_run else await make_backend()

    with httpx.Client(
        timeout=HTTP_TIMEOUT, headers=_base_headers(session_key)
    ) as client:
        org_id = resolve_org_id(client)
        logger.info("Organization: %s", org_id)
        conversations = list_conversations(client, org_id)
        logger.info("Listed %d conversations.", len(conversations))

        # Newest-first from the API; process oldest-first so reference_time
        # ordering in the graph is chronological.
        conversations.reverse()

        considered = 0
        ingested_msgs = 0
        touched_convs = 0

        for conv in conversations:
            uuid = conv.get("uuid")
            if not uuid:
                continue
            conv_updated = _parse_ts(conv.get("updated_at"))
            if cutoff is not None and conv_updated < cutoff:
                continue
            watermark_raw = state.get(uuid)
            watermark = _parse_ts(watermark_raw) if watermark_raw else None
            # Skip if nothing new since last ingest (updated_at not advanced).
            if watermark is not None and conv_updated <= watermark:
                continue

            considered += 1
            if max_convs is not None and considered > max_convs:
                logger.info("Hit --max-convs=%d; stopping this pass.", max_convs)
                break

            name = (conv.get("name") or "(untitled)").strip()
            try:
                messages = fetch_messages(client, org_id, uuid)
            except httpx.HTTPError as e:
                logger.error("fetch failed for %s (%s): %s", uuid[:8], name[:40], e)
                continue

            # Ingest only messages newer than the per-conversation watermark.
            new_for_conv = 0
            max_seen = watermark
            for idx, msg in enumerate(messages):
                created = _parse_ts(msg.get("created_at"))
                if watermark is not None and created <= watermark:
                    continue
                text = _message_text(msg)
                if not text:
                    continue
                sender = msg.get("sender", "unknown")
                episode_name = f"claude-thread::{name[:60]}::{idx:03d}::{sender}"
                content = f"[{sender}] {text}"
                if dry_run:
                    preview = text[:80].replace("\n", " ")
                    logger.info(
                        "[DRY-RUN] would ingest %s (%s): %r",
                        uuid[:8], sender, preview,
                    )
                else:
                    try:
                        result = await backend.ingest_episode(Episode(
                            content=content,
                            source_description=SOURCE_DESCRIPTION,
                            reference_time=created,
                            group_id=GROUP_ID,
                            name=episode_name,
                        ))
                        logger.info(
                            "[%s] ingested %s/%s — %d entities, %d edges",
                            name[:40], sender, created.date(),
                            result.entities_extracted, result.edges_extracted,
                        )
                    except Exception as e:  # noqa: BLE001 — one bad turn ≠ abort
                        logger.error("ingest failed (%s, msg %d): %s", uuid[:8], idx, e)
                        continue
                    if EPISODE_DELAY_SECONDS > 0:
                        await asyncio.sleep(EPISODE_DELAY_SECONDS)
                new_for_conv += 1
                ingested_msgs += 1
                if max_seen is None or created > max_seen:
                    max_seen = created

            if new_for_conv:
                touched_convs += 1
                logger.info(
                    "%s %d new message(s) from %r",
                    "[DRY-RUN]" if dry_run else "ingested", new_for_conv, name[:50],
                )
                # Advance watermark to the conversation's updated_at (covers the
                # case where the newest message has no parseable timestamp).
                if not dry_run:
                    newest = max(max_seen or conv_updated, conv_updated)
                    state[uuid] = newest.isoformat()
                    _save_state_at(state, STATE_PATH)

    logger.info(
        "%s pass complete. conversations touched=%d, messages ingested=%d",
        "DRY-RUN" if dry_run else "Claude-thread", touched_convs, ingested_msgs,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Claude.ai threads into Graphiti.")
    parser.add_argument("--once", action="store_true",
                        help="Single pass then exit (default behavior).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log what would be ingested; no graph writes, no state change.")
    parser.add_argument("--since-days", type=int, default=None,
                        help="Only consider conversations updated within N days.")
    parser.add_argument("--all", action="store_true",
                        help="Ignore --since-days; consider full history (backfill).")
    parser.add_argument("--max-convs", type=int, default=None,
                        help="Safety cap on conversations processed this pass.")
    args = parser.parse_args()

    since_days = None if args.all else args.since_days
    MIKAI_DIR.mkdir(parents=True, exist_ok=True)
    asyncio.run(run_once(
        dry_run=args.dry_run, since_days=since_days, max_convs=args.max_convs,
    ))


if __name__ == "__main__":
    main()
