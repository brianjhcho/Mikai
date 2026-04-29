"""
MIKAI filesystem ingestion daemon — Mode 1 per ARCH-023.

Watches two local sources and ingests new content into Graphiti:
  1. Apple Notes — osascript-based enumeration, content-hash diff per O-039
  2. Claude Code — JSONL session file tail by byte offset

Drop folder (Mode 3) and local files / iMessage (Mode 1 expansion) live on
feat/phase-b-local-expand. Cloud MCP sources (Mode 2) live in mcp_ingest.py.

Imports shared helpers from sidecar.client (Graphiti wiring) and
sidecar.ingest (load_state / save_state) — no duplicated wiring per D-047.

Usage:
    python sync.py --once         # single pass, exit when done
    python sync.py --dry-run      # log what would be ingested (no writes)
    python sync.py --once --dry-run
    python sync.py                # daemon mode (watchdog + debounce)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType

from sidecar.client import init_graphiti as _init_graphiti_client
from sidecar.ingest import (
    load_state as _load_state_at,
    save_state as _save_state_at,
)

import notes_sqlite
import permissions
from sidecar.rate_limit import bucket_for

logger = logging.getLogger("mikai-sync")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


# ── Paths ─────────────────────────────────────────────────────────────────────

MIKAI_DIR = Path.home() / ".mikai"
STATE_PATH = MIKAI_DIR / "sync_state.json"

NOTES_CONTAINER_PATH = (
    Path.home() / "Library" / "Group Containers" / "group.com.apple.notes"
)
CLAUDE_PROJECTS_PATH = Path.home() / ".claude" / "projects"

GROUP_ID_APPLE_NOTES = "apple-notes"
GROUP_ID_CLAUDE_CODE = "claude-code"

EPISODE_DELAY_SECONDS = 2.0
DEBOUNCE_SECONDS = 5.0


# ── Injectable collaborators (same pattern as mcp_ingest.poll_source) ────────


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


OsascriptRunner = Callable[[str], tuple[str, str, int]]


def _default_osascript_runner(script: str) -> tuple[str, str, int]:
    """Production osascript runner. Times out at 30s."""
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=600,
        )
        return proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return "", "osascript timeout", 1


JsonlLister = Callable[[Path], list[Path]]


def _default_jsonl_lister(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return sorted(base.rglob("*.jsonl"))


IngestFn = Callable[..., Awaitable[None]]


def _make_default_ingest_fn(graphiti: Graphiti) -> IngestFn:
    """Bind a real Graphiti instance to an IngestFn-compatible callable.

    Each call burns one DeepSeek (LLM extraction) and several Voyage
    (embedding) credits. The rate limiter buckets gate both — first
    import of a new source can produce thousands of calls in a burst,
    which previously hit DeepSeek's 429 in minutes (O-041).
    """
    async def _ingest(
        *, name: str, content: str, source_description: str,
        reference_time: datetime, group_id: str,
    ) -> None:
        preview = content[:80].replace("\n", " ")
        logger.info(f"[{source_description}] ingesting: {preview!r}")
        await bucket_for("deepseek").acquire()
        await bucket_for("voyage").acquire()
        try:
            result = await graphiti.add_episode(
                name=name,
                episode_body=content,
                source=EpisodeType.text,
                source_description=source_description,
                reference_time=reference_time,
                group_id=group_id,
            )
            nodes = len(result.nodes) if result and result.nodes else 0
            edges = len(result.edges) if result and result.edges else 0
            logger.info(
                f"[{source_description}] ingested — "
                f"{nodes} entities, {edges} edges"
            )
        except Exception as e:
            logger.error(f"[{source_description}] add_episode failed: {e}")
    return _ingest


async def _dry_run_ingest(
    *, name: str, content: str, source_description: str,
    reference_time: datetime, group_id: str,
) -> None:
    preview = content[:80].replace("\n", " ")
    logger.info(
        f"[DRY-RUN][{source_description}][{group_id}] would ingest "
        f"{name!r}: {preview!r}"
    )


async def _seed_only_ingest(
    *, name: str, content: str, source_description: str,
    reference_time: datetime, group_id: str,
) -> None:
    """Used with --seed-only: walks the dedup path, writes state, but never
    calls Graphiti. After a --seed-only pass, --once becomes a no-op against
    already-present content; only subsequent changes trigger real ingestion.

    Rationale: the initial corpus (Apple Notes, Claude Code threads) was
    bulk-imported before the daemon existed. A fresh --once run with an empty
    state file would re-ingest ~1,100 Apple Notes at ~$0.005-0.01 each per
    ARCH-025 AND create duplicate episodes in Graphiti. Seeding avoids both.
    """
    logger.debug(f"[SEED-ONLY][{source_description}] state-recorded: {name!r}")


# ── Apple Notes ───────────────────────────────────────────────────────────────

APPLE_SCRIPT = """\
set delimField to (ASCII character 0)
set delimRecord to (ASCII character 1)
set output to ""
set skipped to 0
tell application "Notes"
    set theNotes to every note
    repeat with i from 1 to count of theNotes
        try
            set n to item i of theNotes
            set t to name of n
            set b to body of n
            set output to output & t & delimField & b & delimRecord
        on error
            set skipped to skipped + 1
        end try
    end repeat
end tell
log "mikai-sync: notes skipped (unreadable) = " & skipped
return output
"""

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITIES = {
    "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
    "&quot;": '"', "&apos;": "'", "&#39;": "'", "&rsquo;": "'",
    "&lsquo;": "'", "&ldquo;": '"', "&rdquo;": '"',
}


def _strip_html(html: str) -> str:
    """Apple Notes returns rich-text bodies as HTML — strip tags + decode the
    handful of entities that show up in practice. Anything more elaborate
    (table layout, inline images) loses its formatting but keeps the text,
    which is what graph extraction needs."""
    text = _HTML_TAG_RE.sub("", html)
    for entity, replacement in _HTML_ENTITIES.items():
        text = text.replace(entity, replacement)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def fetch_apple_notes(
    *, runner: OsascriptRunner = _default_osascript_runner,
) -> list[tuple[str, str, str]] | None:
    """Legacy AppleScript path — kept behind --legacy-applescript as a
    fallback for users who can't grant Full Disk Access (e.g. corporate
    Mac with MDM-locked TCC).

    On a 1,000-note corpus this takes ~10 minutes per pass because each
    `body of n` is a separate Apple Event round-trip. Prefer the SQLite
    path (`fetch_apple_notes_via_sqlite`) which does the same work in
    ~20 seconds.

    Returns None on subprocess failure, else list of (identifier, title,
    body) triples. AppleScript has no stable note id, so identifier is
    "applescript:<content-hash>" — collision-resistant for distinct notes,
    but renames or edits change identity (small dedup-state leak).
    """
    stdout, stderr, rc = runner(APPLE_SCRIPT)
    if rc != 0:
        logger.warning(f"Apple Notes osascript failed (rc={rc}): {stderr.strip()}")
        return None
    raw = stdout.strip()
    if not raw:
        return []
    notes: list[tuple[str, str, str]] = []
    for chunk in raw.split("\x01"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("\x00", 1)
        title = parts[0].strip() if parts else ""
        body = _strip_html(parts[1]) if len(parts) > 1 else ""
        identifier = f"applescript:{_note_hash(title, body)}"
        notes.append((identifier, title, body))
    return notes


# Type for any fetcher: list of (identifier, title, body) triples or None.
NotesFetcher = Callable[[], list[tuple[str, str, str]] | None]


def fetch_apple_notes_via_sqlite(
    *,
    note_store: Path = notes_sqlite.DEFAULT_NOTE_STORE,
    interactive_prompt: bool = True,
) -> list[tuple[str, str, str]] | None:
    """Default Apple Notes path — direct SQLite + protobuf read.

    ~20 seconds for 1,000 notes vs ~10 min via AppleScript. Requires Full
    Disk Access; if FDA is missing, prompts the user (via System Settings
    deep link), logs guidance, and returns None so the caller skips Apple
    Notes for this pass. Subsequent passes re-check.

    Returns None on permission failure or read error, else list of
    (title, body) pairs in the same shape as fetch_apple_notes().
    """
    has_access, reason = permissions.check_full_disk_access(canary=note_store)
    if not has_access:
        logger.warning(f"Apple Notes (sqlite): FDA not granted — {reason}")
        if interactive_prompt:
            permissions.prompt_for_full_disk_access(reason=reason)
        return None
    try:
        with notes_sqlite.copy_note_store(note_store) as snapshot:
            return [
                (n.identifier or f"sqlite-pk:{n.z_pk}", n.title, n.body)
                for n in notes_sqlite.iter_notes(snapshot)
            ]
    except (OSError, Exception) as e:
        logger.warning(f"Apple Notes SQLite read failed: {e}")
        return None


def _note_hash(title: str, body: str) -> str:
    return hashlib.sha256(f"{title}\x00{body}".encode("utf-8")).hexdigest()


def _note_key(identifier: str) -> str:
    """Stable lookup key for a note. The fetcher provides the identifier:
    SQLite supplies ZIDENTIFIER (UUID), AppleScript supplies a content-hash
    fallback. Either way, we just hash whatever the fetcher gives us so
    the key length stays uniform in state.json."""
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()


async def sync_apple_notes(
    state: dict,
    *,
    ingest_fn: IngestFn,
    runner: OsascriptRunner = _default_osascript_runner,
    notes_fetcher: NotesFetcher | None = None,
    now: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    state_path: Path = STATE_PATH,
    episode_delay: float = EPISODE_DELAY_SECONDS,
) -> int:
    """Sync Apple Notes whose content hash changed since last pass.

    `notes_fetcher` defaults to the SQLite path. Pass a different callable
    (e.g. lambda: fetch_apple_notes(runner=runner)) to use the AppleScript
    fallback. The callable returns list[(title, body)] or None on failure.
    """
    fetcher = notes_fetcher or fetch_apple_notes_via_sqlite
    notes = fetcher()
    if notes is None:
        return 0

    note_state = state.setdefault("apple_notes", {"hashes": {}})
    stored: dict[str, str] = note_state.setdefault("hashes", {})
    count = 0

    for identifier, title, body in notes:
        if not title and not body:
            continue
        key = _note_key(identifier)
        h = _note_hash(title, body)
        if stored.get(key) == h:
            continue  # unchanged since last pass — dedup per O-039
        content = f"# {title}\n\n{body}" if title else body
        if not content.strip():
            continue
        await ingest_fn(
            name=f"apple-notes::{title[:60]}",
            content=content,
            source_description="apple-notes",
            reference_time=now(),
            group_id=GROUP_ID_APPLE_NOTES,
        )
        stored[key] = h
        count += 1
        if count > 1 and episode_delay > 0:
            await sleep(episode_delay)

    _save_state_at(state, state_path)
    if count:
        logger.info(f"Apple Notes: {count} note(s) ingested")
    return count


# ── Claude Code JSONL ─────────────────────────────────────────────────────────


def tail_jsonl(path: Path, offset: int) -> tuple[list[dict], int]:
    """Read new JSON lines from `path` starting at `offset`.

    Returns (records, new_offset). Malformed lines are skipped. Missing files
    return ([], offset) so a deleted session file doesn't corrupt state.
    """
    try:
        size = path.stat().st_size
        if size <= offset:
            return [], offset
        records: list[dict] = []
        with path.open("rb") as f:
            f.seek(offset)
            for raw_line in f:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            new_offset = f.tell()
        return records, new_offset
    except FileNotFoundError:
        return [], offset
    except Exception as e:
        logger.warning(f"Could not read {path}: {e}")
        return [], offset


def extract_turns(records: list[dict]) -> list[dict]:
    """Pull user/assistant turns out of JSONL records.

    Handles two wire shapes seen in Claude Code sessions:
      - Flat:   {"type": "human"|"assistant", "content": ..., "timestamp": ...}
      - Nested: {"type": "...", "message": {"role": "...", "content": ...}}

    Content may be a string, a list of content blocks (text / tool_result),
    or missing — each shape is normalised to a single string.
    """
    turns: list[dict] = []
    for rec in records:
        msg_type = rec.get("type", "")
        if msg_type not in ("human", "user", "assistant"):
            continue
        role = "user" if msg_type in ("human", "user") else "assistant"

        # Content can live in rec.content OR rec.message.content.
        content: Any = rec.get("content")
        if content is None:
            msg = rec.get("message")
            if isinstance(msg, dict):
                content = msg.get("content")
        if content is None:
            continue

        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    t = block.get("type")
                    if t == "text":
                        parts.append(block.get("text", ""))
                    elif t == "tool_result":
                        for item in block.get("content", []) or []:
                            if isinstance(item, dict) and item.get("type") == "text":
                                parts.append(item.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            content = "\n".join(p for p in parts if p)
        if not isinstance(content, str):
            content = str(content)
        content = content.strip()
        if content:
            turns.append({
                "role": role,
                "content": content,
                "ts": rec.get("timestamp"),
            })
    return turns


async def sync_claude_code(
    state: dict,
    *,
    ingest_fn: IngestFn,
    lister: JsonlLister = _default_jsonl_lister,
    now: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    base_path: Path = CLAUDE_PROJECTS_PATH,
    state_path: Path = STATE_PATH,
    episode_delay: float = EPISODE_DELAY_SECONDS,
) -> int:
    """Tail all Claude Code JSONL files; ingest any new turns since last pass."""
    code_state = state.setdefault("claude_code", {"offsets": {}})
    offsets: dict[str, int] = code_state.setdefault("offsets", {})
    count = 0

    for path in lister(base_path):
        key = str(path)
        offset = offsets.get(key, 0)
        records, new_offset = tail_jsonl(path, offset)
        offsets[key] = new_offset
        if not records:
            continue
        turns = extract_turns(records)
        for turn in turns:
            role = turn["role"]
            content = turn["content"]
            ts_raw = turn.get("ts")
            try:
                ref_time = datetime.fromisoformat(ts_raw) if ts_raw else now()
            except (ValueError, TypeError):
                ref_time = now()
            await ingest_fn(
                name=f"claude-code::{path.name}::{role}",
                content=f"[{role}] {content}",
                source_description="claude-code",
                reference_time=ref_time,
                group_id=GROUP_ID_CLAUDE_CODE,
            )
            count += 1
            if episode_delay > 0:
                await sleep(episode_delay)

    _save_state_at(state, state_path)
    if count:
        logger.info(f"Claude Code: {count} turn(s) ingested")
    return count


# ── Full sync pass ────────────────────────────────────────────────────────────


async def run_sync_pass(
    *, ingest_fn: IngestFn,
    state_path: Path = STATE_PATH,
    osascript_runner: OsascriptRunner = _default_osascript_runner,
    notes_fetcher: NotesFetcher | None = None,
    jsonl_lister: JsonlLister = _default_jsonl_lister,
    now: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    base_claude_path: Path = CLAUDE_PROJECTS_PATH,
    episode_delay: float = EPISODE_DELAY_SECONDS,
) -> tuple[int, int]:
    """One full pass across Apple Notes + Claude Code. Returns (notes, turns).

    `episode_delay` defaults to EPISODE_DELAY_SECONDS to protect Neo4j during
    real ingestion. Pass 0 for --seed-only / --dry-run runs where there is no
    backend to protect — otherwise seeding the corpus burns hours of sleep.

    `notes_fetcher` overrides the default SQLite path — set to a lambda that
    calls fetch_apple_notes(runner=...) for the AppleScript fallback.
    """
    state = _load_state_at(state_path)
    apple = await sync_apple_notes(
        state, ingest_fn=ingest_fn, runner=osascript_runner,
        notes_fetcher=notes_fetcher,
        now=now, sleep=sleep, state_path=state_path,
        episode_delay=episode_delay,
    )
    code = await sync_claude_code(
        state, ingest_fn=ingest_fn, lister=jsonl_lister,
        now=now, sleep=sleep, base_path=base_claude_path,
        state_path=state_path,
        episode_delay=episode_delay,
    )
    return apple, code


# ── Daemon (watchdog + debounce) ──────────────────────────────────────────────


async def daemon_loop(
    *, ingest_fn: IngestFn,
    state_path: Path = STATE_PATH,
) -> None:
    """Run forever. Re-syncs on filesystem events with 5s debounce. Also kicks
    off one pass at startup to catch anything written while we were down."""
    from watchdog.events import FileSystemEventHandler  # type: ignore
    from watchdog.observers import Observer              # type: ignore

    loop = asyncio.get_running_loop()
    event = asyncio.Event()

    class _Handler(FileSystemEventHandler):
        def on_any_event(self, _ev: Any) -> None:
            loop.call_soon_threadsafe(event.set)

    observer = Observer()
    handler = _Handler()
    for path in (NOTES_CONTAINER_PATH, CLAUDE_PROJECTS_PATH):
        if path.exists():
            observer.schedule(handler, str(path), recursive=True)
            logger.info(f"Watching {path}")
        else:
            logger.warning(f"Watch path missing (skipping): {path}")

    observer.start()
    try:
        # One pass immediately so we catch anything queued during downtime.
        await run_sync_pass(ingest_fn=ingest_fn, state_path=state_path)

        while True:
            await event.wait()
            # Debounce: keep draining new events for DEBOUNCE_SECONDS.
            while True:
                event.clear()
                try:
                    await asyncio.wait_for(event.wait(), timeout=DEBOUNCE_SECONDS)
                except asyncio.TimeoutError:
                    break
            logger.info("Filesystem events settled; running sync pass.")
            await run_sync_pass(ingest_fn=ingest_fn, state_path=state_path)
    finally:
        observer.stop()
        observer.join()


# ── CLI entry ─────────────────────────────────────────────────────────────────


async def _main_async(args: argparse.Namespace) -> None:
    if args.seed_only:
        ingest_fn: IngestFn = _seed_only_ingest
        logger.info(
            "SEED-ONLY mode — walking dedup path, recording state hashes, "
            "but NOT calling Graphiti. Subsequent --once runs will only "
            "ingest items that changed after this seed pass."
        )
    elif args.dry_run:
        ingest_fn = _dry_run_ingest
        logger.info("DRY-RUN mode — no episodes will be written to Graphiti.")
    else:
        logger.info("Initializing Graphiti...")
        graphiti = await _init_graphiti_client()
        ingest_fn = _make_default_ingest_fn(graphiti)

    notes_fetcher: NotesFetcher | None = None
    if args.legacy_applescript:
        logger.info("Apple Notes path: AppleScript (--legacy-applescript)")
        notes_fetcher = lambda: fetch_apple_notes()
    else:
        logger.info("Apple Notes path: SQLite + protobuf (default)")
        # Pre-flight FDA check so the user sees the prompt at startup rather
        # than during the first sync. The check is cheap; the prompt is a
        # no-op if access is already granted.
        has_access, reason = permissions.check_full_disk_access()
        if not has_access:
            logger.warning(f"Full Disk Access not granted: {reason}")
            permissions.prompt_for_full_disk_access(reason=reason)

    if args.once or args.seed_only:
        episode_delay = 0.0 if (args.seed_only or args.dry_run) else EPISODE_DELAY_SECONDS
        notes, turns = await run_sync_pass(
            ingest_fn=ingest_fn,
            episode_delay=episode_delay,
            notes_fetcher=notes_fetcher,
        )
        label = "--seed-only" if args.seed_only else "--once"
        logger.info(
            f"{label} pass complete. apple-notes={notes} claude-code-turns={turns}"
        )
        return

    await daemon_loop(ingest_fn=ingest_fn)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MIKAI Mode 1 ingestion daemon — Apple Notes + Claude Code."
    )
    parser.add_argument("--once", action="store_true",
                        help="Run one pass and exit.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log what would be ingested without writing to Graphiti.")
    parser.add_argument("--seed-only", action="store_true",
                        help="Walk the dedup path and record state hashes "
                             "without calling Graphiti. Use once before the first "
                             "real --once run to avoid re-ingesting already-imported "
                             "content.")
    parser.add_argument("--legacy-applescript", action="store_true",
                        help="Use the AppleScript path for Apple Notes "
                             "instead of the SQLite + protobuf default. "
                             "~10 min per pass on 1000 notes vs ~20s for "
                             "SQLite — only useful if Full Disk Access "
                             "cannot be granted (e.g. MDM-locked Mac).")
    args = parser.parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
