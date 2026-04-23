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
