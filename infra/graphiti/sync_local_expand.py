"""
MIKAI Local Expansion Watchers — Phase B (ARCH-023 Modes 1 & 3 extensions).

Exposes three watchers that feed personal content into the Graphiti L3 knowledge
graph via an injected ``add_episode_fn`` callback.  The callback signature
matches the ``poll_source`` pattern from ``mcp_ingest.py``:

    async def add_episode_fn(*, name: str, content: str, source_description: str) -> None

Watchers:
  - ``run_drop_folder_watcher``  — watches ``~/.mikai/imports/`` for new/modified
    files and ingests them (ARCH-023 Mode 3 drop-folder).
  - ``run_local_files_watcher``  — polls paths declared in
    ``~/.mikai/local_files.yaml`` (ARCH-023 Mode 1 filesystem).
  - ``run_imessage_watcher``     — reads ``~/Library/Messages/chat.db`` (opt-in).

PERMISSIONS NOTE — iMessage:
  ``~/Library/Messages/chat.db`` is protected by macOS Full Disk Access (FDA).
  The process running this module must be granted FDA in
  System Settings → Privacy & Security → Full Disk Access.
  Without FDA, sqlite3.connect() will succeed but every query will return zero
  rows silently, or raise OperationalError on newer macOS versions.

Design invariants:
  - No graphiti-core, Neo4j, or network imports here.  All writes go through
    the injected ``add_episode_fn`` so the module can be exercised without a
    running Graphiti instance.
  - Dedup is content-hash (sha256 of raw bytes) keyed by file path, stored in
    plain JSON state files compatible with ``sidecar.ingest.load_state`` /
    ``save_state``.
  - ``is_sensitive_name()`` is applied to filenames / handles before any I/O or
    ingestion occurs.

Dependencies: watchdog, pypdf, beautifulsoup4, pyyaml (all in requirements.txt).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Awaitable

# Bring the sidecar package onto sys.path regardless of invocation method.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sidecar.ingest import is_sensitive_name

logger = logging.getLogger("mikai-local-expand")

# ── Type alias ───────────────────────────────────────────────────────────────

AddEpisodeFn = Callable[..., Awaitable[None]]

# ── Paths ────────────────────────────────────────────────────────────────────

MIKAI_DIR = Path.home() / ".mikai"

DROP_FOLDER = MIKAI_DIR / "imports"
DROP_STATE_PATH = MIKAI_DIR / "drop_state.json"
DROP_PROCESSED_DIR = DROP_FOLDER / "processed"


# ── State helpers ─────────────────────────────────────────────────────────────


def _load_json(path: Path) -> dict:
    """Load arbitrary JSON dict from *path*; return {} on missing or corrupt."""
    if not path.exists():
        return {}
    try:
        with path.open() as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read state from %s: %s", path, exc)
        return {}


def _save_json(data: dict, path: Path) -> None:
    """Write *data* as JSON to *path*, creating parent dirs as needed."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:
            json.dump(data, fh, indent=2)
    except OSError as exc:
        logger.warning("Could not write state to %s: %s", path, exc)


# ── Content extractors ────────────────────────────────────────────────────────


def _extract_text_from_file(path: Path) -> str | None:
    """
    Extract plain text from *path* based on its extension.

    Returns None and logs a warning for unsupported extensions.
    """
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt"):
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", path, exc)
            return None
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore[import]
            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages)
        except Exception as exc:
            logger.warning("Cannot extract PDF %s: %s", path, exc)
            return None
    if suffix in (".html", ".htm"):
        try:
            from bs4 import BeautifulSoup  # type: ignore[import]
            raw = path.read_bytes()
            soup = BeautifulSoup(raw, "html.parser")
            return soup.get_text(separator="\n")
        except Exception as exc:
            logger.warning("Cannot extract HTML %s: %s", path, exc)
            return None
    logger.warning("Unsupported file extension %r — skipping %s", suffix, path.name)
    return None


def _sha256_file(path: Path) -> str | None:
    """Return hex sha256 of *path*'s raw bytes, or None on error."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        logger.warning("Cannot hash %s: %s", path, exc)
        return None


# ── Watcher 1 — drop folder ───────────────────────────────────────────────────

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent


class _DropFolderHandler(FileSystemEventHandler):
    """Watchdog handler for the ``~/.mikai/imports/`` drop folder."""

    def __init__(
        self,
        add_episode_fn: AddEpisodeFn,
        *,
        drop_folder: Path = DROP_FOLDER,
        processed_dir: Path = DROP_PROCESSED_DIR,
        state_path: Path = DROP_STATE_PATH,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        super().__init__()
        self._add_episode_fn = add_episode_fn
        self._drop_folder = drop_folder
        self._processed_dir = processed_dir
        self._state_path = state_path
        self._loop = loop

    # watchdog calls on_created / on_modified from a background thread.
    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def _handle(self, file_path: Path) -> None:
        """Dispatch ingestion to the event loop (thread-safe)."""
        loop = self._loop or asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(
            self._ingest(file_path), loop
        )

    async def _ingest(self, file_path: Path) -> None:
        """Core ingestion logic — runs in the asyncio event loop."""
        # Ignore anything inside the processed/ subdirectory to avoid loops.
        try:
            file_path.relative_to(self._processed_dir)
            return  # path is inside processed/ — skip
        except ValueError:
            pass

        if not file_path.exists() or not file_path.is_file():
            return

        filename = file_path.name

        # Sensitivity check on filename.
        if is_sensitive_name(filename):
            logger.info("Skipping sensitive filename: %s", filename)
            return

        # Content-hash dedup.
        sha256 = _sha256_file(file_path)
        if sha256 is None:
            return

        state = _load_json(self._state_path)
        if sha256 in state:
            logger.debug("Already ingested (hash %s): %s", sha256[:8], filename)
            return

        # Extract text.
        text = _extract_text_from_file(file_path)
        if text is None:
            return  # unsupported or unreadable
        if not text.strip():
            logger.debug("Empty content after extraction: %s", filename)
            return

        # Ingest.
        try:
            await self._add_episode_fn(
                name=filename,
                content=text,
                source_description="drop-folder",
            )
        except Exception as exc:
            logger.error("add_episode_fn failed for %s: %s", filename, exc)
            return

        # Update dedup state.
        state[sha256] = {
            "filename": filename,
            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        _save_json(state, self._state_path)

        # Move to processed/.
        self._processed_dir.mkdir(parents=True, exist_ok=True)
        dest = self._processed_dir / f"{sha256}-{filename}"
        try:
            shutil.move(str(file_path), str(dest))
            logger.info("Ingested and moved to processed/: %s", filename)
        except OSError as exc:
            logger.warning("Could not move %s to processed/: %s", filename, exc)


def run_drop_folder_watcher(
    add_episode_fn: AddEpisodeFn,
    *,
    drop_folder: Path = DROP_FOLDER,
    processed_dir: Path = DROP_PROCESSED_DIR,
    state_path: Path = DROP_STATE_PATH,
    loop: asyncio.AbstractEventLoop | None = None,
) -> Observer:
    """
    Start a watchdog Observer on the drop folder.

    Returns the running Observer so the caller can ``observer.stop()`` /
    ``observer.join()`` when shutting down.

    The ``loop``, ``drop_folder``, ``processed_dir``, and ``state_path``
    parameters are injectable for tests.
    """
    drop_folder.mkdir(parents=True, exist_ok=True)
    handler = _DropFolderHandler(
        add_episode_fn,
        drop_folder=drop_folder,
        processed_dir=processed_dir,
        state_path=state_path,
        loop=loop or asyncio.get_event_loop(),
    )
    observer = Observer()
    observer.schedule(handler, str(drop_folder), recursive=False)
    observer.start()
    logger.info("Drop-folder watcher started on %s", drop_folder)
    return observer


# ── Watcher 2 — local files ───────────────────────────────────────────────────

import yaml  # pyyaml>=6.0
from watchdog.observers.polling import PollingObserver

LOCAL_FILES_CONFIG_PATH = MIKAI_DIR / "local_files.yaml"
LOCAL_FILES_STATE_PATH = MIKAI_DIR / "local_files_state.json"

_DEFAULT_LOCAL_FILES_CONFIG = {
    "watches": [
        {"path": "~/Documents/research", "glob": "**/*.md"},
        {"path": "~/Downloads", "glob": "*.pdf"},
    ],
    "max_file_size_mb": 10,
}


def _load_local_files_config(config_path: Path = LOCAL_FILES_CONFIG_PATH) -> dict:
    """Load ``~/.mikai/local_files.yaml``; return defaults if missing."""
    if not config_path.exists():
        logger.info(
            "Local files config not found at %s — using defaults.", config_path
        )
        return _DEFAULT_LOCAL_FILES_CONFIG
    try:
        with config_path.open() as fh:
            cfg = yaml.safe_load(fh)
            if not cfg or not isinstance(cfg, dict):
                return _DEFAULT_LOCAL_FILES_CONFIG
            return cfg
    except Exception as exc:
        logger.warning("Cannot load local files config %s: %s", config_path, exc)
        return _DEFAULT_LOCAL_FILES_CONFIG


class _LocalFilesHandler(FileSystemEventHandler):
    """
    Watchdog handler for locally-watched file trees.

    Uses content-hash + absolute-path keying so the same file content at
    different paths produces separate episodes.
    """

    def __init__(
        self,
        add_episode_fn: AddEpisodeFn,
        *,
        max_file_size_bytes: int,
        state_path: Path = LOCAL_FILES_STATE_PATH,
        glob_pattern: str = "**/*",
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        super().__init__()
        self._add_episode_fn = add_episode_fn
        self._max_bytes = max_file_size_bytes
        self._state_path = state_path
        self._glob = glob_pattern
        self._loop = loop

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def _handle(self, file_path: Path) -> None:
        loop = self._loop or asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(self._ingest(file_path), loop)

    async def _ingest(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            return

        # Size check.
        try:
            size = file_path.stat().st_size
        except OSError:
            return
        if size > self._max_bytes:
            logger.info(
                "Skipping oversized file (%d bytes > %d): %s",
                size, self._max_bytes, file_path.name,
            )
            return

        if is_sensitive_name(file_path.name):
            logger.info("Skipping sensitive filename: %s", file_path.name)
            return

        sha256 = _sha256_file(file_path)
        if sha256 is None:
            return

        abs_path_str = str(file_path.resolve())
        dedup_key = f"{abs_path_str}::{sha256}"

        state = _load_json(self._state_path)
        if dedup_key in state:
            logger.debug(
                "Already ingested (key %s…): %s", dedup_key[:24], file_path.name
            )
            return

        text = _extract_text_from_file(file_path)
        if text is None or not text.strip():
            return

        try:
            await self._add_episode_fn(
                name=file_path.name,
                content=text,
                source_description="local-files",
            )
        except Exception as exc:
            logger.error("add_episode_fn failed for %s: %s", file_path.name, exc)
            return

        state[dedup_key] = {
            "filename": abs_path_str,
            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        _save_json(state, self._state_path)
        logger.info("Ingested local file: %s", abs_path_str)


def run_local_files_watcher(
    add_episode_fn: AddEpisodeFn,
    *,
    config_path: Path = LOCAL_FILES_CONFIG_PATH,
    state_path: Path = LOCAL_FILES_STATE_PATH,
    poll_interval: int = 300,
    loop: asyncio.AbstractEventLoop | None = None,
) -> PollingObserver:
    """
    Start a PollingObserver for all paths declared in the local-files config.

    Returns the running PollingObserver.  Injectable parameters support tests.
    """
    cfg = _load_local_files_config(config_path)
    watches = cfg.get("watches") or _DEFAULT_LOCAL_FILES_CONFIG["watches"]
    max_mb = float(cfg.get("max_file_size_mb", 10))
    max_bytes = int(max_mb * 1024 * 1024)

    observer = PollingObserver(timeout=poll_interval)

    for watch_spec in watches:
        raw_path = watch_spec.get("path", "~/Documents/research")
        glob = watch_spec.get("glob", "**/*")
        watch_path = Path(raw_path).expanduser().resolve()
        watch_path.mkdir(parents=True, exist_ok=True)

        handler = _LocalFilesHandler(
            add_episode_fn,
            max_file_size_bytes=max_bytes,
            state_path=state_path,
            glob_pattern=glob,
            loop=loop or asyncio.get_event_loop(),
        )
        observer.schedule(handler, str(watch_path), recursive=True)
        logger.info(
            "Local-files watcher scheduled: %s (glob=%s)", watch_path, glob
        )

    observer.start()
    logger.info(
        "Local-files PollingObserver started (%d path(s))", len(watches)
    )
    return observer


# ── Watcher 3 — iMessage ─────────────────────────────────────────────────────

import sqlite3

IMESSAGE_DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"
IMESSAGE_STATE_PATH = MIKAI_DIR / "imessage_state.json"

# Apple's reference epoch starts 2001-01-01 00:00:00 UTC.
APPLE_EPOCH_OFFSET = 978307200  # seconds between Unix epoch and Apple epoch


def _apple_timestamp_to_dt(apple_ts: int | float) -> datetime:
    """Convert Apple epoch nanoseconds to UTC datetime."""
    # chat.db stores timestamps as nanoseconds since Apple epoch on modern macOS.
    # Older rows may use seconds.  Heuristic: values > 1e10 are nanoseconds.
    ts = apple_ts
    if ts and ts > 1e10:
        ts = ts / 1_000_000_000  # nanoseconds → seconds
    unix_ts = ts + APPLE_EPOCH_OFFSET
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc)


def _format_imessage_thread(handle: str, messages: list) -> str:
    """Format a conversation thread as a single episode body string."""
    lines = [f"iMessage conversation with {handle}"]
    for msg in messages:
        dt = _apple_timestamp_to_dt(msg["date"])
        timestamp = dt.strftime("%Y-%m-%d %H:%M")
        sender = "me" if msg["is_from_me"] else handle
        text = (msg["text"] or "").strip()
        if text:
            lines.append(f"[{timestamp}] <{sender}>: {text}")
    return "\n".join(lines)


async def run_imessage_watcher(
    add_episode_fn: AddEpisodeFn,
    *,
    enable: bool = False,
    checkpoint_hours: int = 24,
    db_path: Path = IMESSAGE_DB_PATH,
    state_path: Path = IMESSAGE_STATE_PATH,
) -> int:
    """
    Read recent iMessage threads and ingest new conversations as episodes.

    Parameters
    ----------
    add_episode_fn:
        Injectable callback — same signature as the other watchers.
    enable:
        Opt-in gate.  Must be explicitly set to True; defaults to False so the
        watcher does nothing unless the user consciously enables it.
    checkpoint_hours:
        How many hours back from now to look for messages.
    db_path:
        Path to chat.db (injectable for tests with an in-memory fixture).
    state_path:
        Path to the dedup state JSON file (injectable for tests).

    Returns
    -------
    int
        Number of episodes ingested in this run.

    PERMISSIONS NOTE:
        macOS Full Disk Access is required for the running process.  See module
        docstring for details.
    """
    if not enable:
        logger.info(
            "iMessage ingestion disabled (set enable=True to opt in)"
        )
        return 0

    if not db_path.exists():
        logger.warning("iMessage database not found at %s", db_path)
        return 0

    # Apple epoch cutoff for the query window.
    now_unix = datetime.now(tz=timezone.utc).timestamp()
    cutoff_unix = now_unix - checkpoint_hours * 3600
    # Convert Unix → Apple epoch seconds; then to nanoseconds for comparison.
    cutoff_apple_ns = int((cutoff_unix - APPLE_EPOCH_OFFSET) * 1_000_000_000)

    state = _load_json(state_path)
    ingested = 0

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
    except sqlite3.OperationalError as exc:
        logger.error("Cannot open iMessage DB at %s: %s", db_path, exc)
        return 0

    try:
        # Query messages within the checkpoint window, joined to their handle.
        query = """
            SELECT
                m.rowid        AS rowid,
                m.handle_id    AS handle_id,
                m.date         AS date,
                m.text         AS text,
                m.is_from_me   AS is_from_me,
                h.id           AS handle
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.rowid
            WHERE m.date >= ?
            ORDER BY m.handle_id, m.date ASC
        """
        rows = conn.execute(query, (cutoff_apple_ns,)).fetchall()
    except sqlite3.OperationalError as exc:
        logger.error("iMessage DB query failed: %s", exc)
        conn.close()
        return 0

    # Group messages by handle_id.
    conversations: dict = {}
    handle_map: dict = {}
    for row in rows:
        hid = row["handle_id"]
        conversations.setdefault(hid, []).append(dict(row))
        handle_map[hid] = row["handle"] or str(hid)

    for handle_id, messages in conversations.items():
        handle = handle_map[handle_id]

        if is_sensitive_name(handle):
            logger.info("Skipping sensitive iMessage handle: %s", handle)
            continue

        newest_rowid = max(m["rowid"] for m in messages)
        dedup_key = f"{handle_id}::{newest_rowid}"

        if dedup_key in state:
            logger.debug(
                "Already ingested conversation %s (newest rowid %d)",
                handle, newest_rowid,
            )
            continue

        episode_body = _format_imessage_thread(handle, messages)

        try:
            await add_episode_fn(
                name=f"imessage-{handle}",
                content=episode_body,
                source_description="imessage",
            )
        except Exception as exc:
            logger.error(
                "add_episode_fn failed for iMessage handle %s: %s", handle, exc
            )
            continue

        state[dedup_key] = {
            "handle": handle,
            "newest_rowid": newest_rowid,
            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        _save_json(state, state_path)
        ingested += 1
        logger.info(
            "Ingested iMessage conversation: %s (%d messages)", handle, len(messages)
        )

    conn.close()
    logger.info("iMessage run complete. ingested=%d", ingested)
    return ingested
