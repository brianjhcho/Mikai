"""
raw_corpus.py — graphless corpus reader.

Produces the SAME `list[dict]` shape that `full_corpus_dream.fetch_all_episodes()`
returns from Neo4j — `{uuid, name, content, group_id, valid_at}` — but reads
directly from the raw sources instead. This makes the graph OPTIONAL for wiki
generation: a fresh user can build the ontology wiki of their digital traces
without standing up Docker/Neo4j/Graphiti.

It reuses the exact reader functions the ingestion daemons use, so the produced
content is byte-identical to what those sources put into the graph — which is
what makes the wiki-first head-to-head a clean isolation of "graph-stored text
vs raw-source text" (MEMORY_ARCHITECTURE PART K).

Each source reader is independently guarded: a missing/unavailable source
(no Claude desktop app, Apple Notes TCC not granted, etc.) is skipped with a
warning rather than aborting the whole run — the graceful-skip behaviour the
onboarding flow needs.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

import httpx

import claude_threads as ct
import sync


def _log(msg: str) -> None:
    print(f"[raw_corpus] {msg}", file=sys.stderr)


# ── claude-thread (Claude.ai web/desktop via the internal API) ────────────────

def _read_claude_thread() -> list[dict]:
    """Mirror claude_threads.run_once ingestion: one episode per message,
    content=`[sender] text`, so the text matches the graph's claude-thread
    episodes exactly."""
    session_key = ct.read_session_key()
    episodes: list[dict] = []
    with httpx.Client(timeout=60.0, headers=ct._base_headers(session_key)) as client:
        org_id = ct.resolve_org_id(client)
        conversations = ct.list_conversations(client, org_id)
        _log(f"claude-thread: {len(conversations)} conversations")
        for conv in conversations:
            uuid = conv.get("uuid")
            if not uuid:
                continue
            name = (conv.get("name") or "(untitled)").strip()
            try:
                messages = ct.fetch_messages(client, org_id, uuid)
            except httpx.HTTPError as e:
                _log(f"  fetch failed for {uuid[:8]}: {e}")
                continue
            for idx, msg in enumerate(messages):
                text = ct._message_text(msg)
                if not text:
                    continue
                sender = msg.get("sender", "unknown")
                episodes.append({
                    "uuid": f"raw-ct-{uuid}-{idx:03d}",
                    "name": f"claude-thread::{name[:60]}::{sender}",
                    "content": f"[{sender}] {text}",
                    "group_id": "claude-thread",
                    "valid_at": msg.get("created_at") or conv.get("updated_at") or "",
                })
    return episodes


# ── apple-notes (SQLite reader) ───────────────────────────────────────────────

def _read_apple_notes() -> list[dict]:
    notes = sync.fetch_apple_notes_via_sqlite(interactive_prompt=False)
    if not notes:
        return []
    episodes: list[dict] = []
    for identifier, title, body in notes:
        body = (body or "").strip()
        if not body:
            continue
        episodes.append({
            "uuid": f"raw-note-{identifier}",
            "name": (title or "")[:80],
            "content": body,
            "group_id": "apple-notes",
            "valid_at": "",  # Apple Notes SQLite path carries no reliable per-note ts here
        })
    _log(f"apple-notes: {len(episodes)} notes")
    return episodes


# ── claude-code (JSONL session tails, read in full) ───────────────────────────

def _read_claude_code() -> list[dict]:
    episodes: list[dict] = []
    for path in sync._default_jsonl_lister(sync.CLAUDE_PROJECTS_PATH):
        records, _ = sync.tail_jsonl(path, 0)  # offset 0 = full read
        if not records:
            continue
        for turn in sync.extract_turns(records):
            content = (turn.get("content") or "").strip()
            if not content:
                continue
            role = turn.get("role", "unknown")
            episodes.append({
                "uuid": f"raw-cc-{path.name}-{len(episodes)}",
                "name": f"claude-code::{path.name}::{role}",
                "content": f"[{role}] {content}",
                "group_id": "claude-code",
                "valid_at": turn.get("ts") or "",
            })
    _log(f"claude-code: {len(episodes)} turns")
    return episodes


_READERS = {
    "claude-thread": _read_claude_thread,
    "apple-notes": _read_apple_notes,
    "claude-code": _read_claude_code,
}

RAW_CAPABLE_GROUPS = tuple(_READERS.keys())


def fetch_raw_episodes(groups: list[str] | None = None) -> list[dict]:
    """Read the requested source groups directly (no Neo4j). Unknown groups are
    ignored; a reader that raises is skipped with a warning (graceful degrade).
    Returns episodes sorted by valid_at ASC to match the Neo4j path's ordering."""
    wanted = list(groups) if groups else list(RAW_CAPABLE_GROUPS)
    episodes: list[dict] = []
    for g in wanted:
        reader = _READERS.get(g)
        if reader is None:
            _log(f"skip unknown/graphless-unsupported source: {g}")
            continue
        try:
            episodes.extend(reader())
        except Exception as e:  # noqa: BLE001 — one bad source must not abort the run
            _log(f"SKIP {g}: unavailable ({type(e).__name__}: {str(e)[:120]})")
    episodes.sort(key=lambda e: e.get("valid_at") or "")
    _log(f"total raw episodes: {len(episodes)} from {wanted}")
    return episodes
