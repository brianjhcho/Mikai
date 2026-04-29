"""
Tests for sync_local_expand — drop folder, local files, and iMessage watchers.

Follows the same "Humble Object" pattern as test_mcp_ingest.py:
  - All external I/O (filesystem moves, DB queries, network) is exercised
    against in-memory / tmp_path fakes.
  - ``add_episode_fn`` is a simple list-appending coroutine — never real Graphiti.
  - iMessage tests create an in-memory SQLite DB with the minimal chat.db schema.

ARCH-023 Mode coverage:
  Mode 3 (drop folder)  → TestDropFolder
  Mode 1 (local files)  → TestLocalFiles
  iMessage opt-in       → TestIMessage
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sync_local_expand import (
    _DropFolderHandler,
    _LocalFilesHandler,
    _load_json,
    _save_json,
    run_imessage_watcher,
    APPLE_EPOCH_OFFSET,
)


# ── Shared test double ────────────────────────────────────────────────────────


class FakeAddEpisode:
    """List-appending coroutine — never touches real Graphiti."""

    def __init__(self, fail: bool = False):
        self.calls: list[dict] = []
        self._fail = fail

    async def __call__(self, *, name: str, content: str, source_description: str) -> None:
        self.calls.append(
            {"name": name, "content": content, "source_description": source_description}
        )
        if self._fail:
            raise RuntimeError("simulated add_episode failure")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── Drop-folder tests ─────────────────────────────────────────────────────────


class TestDropFolder:
    async def test_happy_path_md_file_is_ingested_and_moved(self, tmp_path):
        drop_folder = tmp_path / "imports"
        drop_folder.mkdir()
        processed_dir = drop_folder / "processed"
        state_path = tmp_path / "drop_state.json"
        add_ep = FakeAddEpisode()

        # Place a markdown file.
        md_file = drop_folder / "notes.md"
        md_file.write_text("# My notes\n\nSome content here.", encoding="utf-8")

        handler = _DropFolderHandler(
            add_ep,
            drop_folder=drop_folder,
            processed_dir=processed_dir,
            state_path=state_path,
            loop=asyncio.get_event_loop(),
        )
        await handler._ingest(md_file)

        assert len(add_ep.calls) == 1
        assert add_ep.calls[0]["name"] == "notes.md"
        assert add_ep.calls[0]["source_description"] == "drop-folder"
        assert "My notes" in add_ep.calls[0]["content"]

        # File moved to processed/.
        assert not md_file.exists()
        processed_files = list(processed_dir.iterdir())
        assert len(processed_files) == 1
        assert processed_files[0].name.endswith("-notes.md")

        # State persisted.
        state = json.loads(state_path.read_text())
        assert len(state) == 1
        sha = list(state.keys())[0]
        assert state[sha]["filename"] == "notes.md"

    async def test_duplicate_hash_is_skipped(self, tmp_path):
        drop_folder = tmp_path / "imports"
        drop_folder.mkdir()
        processed_dir = drop_folder / "processed"
        state_path = tmp_path / "drop_state.json"
        add_ep = FakeAddEpisode()

        content = b"Hello world"
        sha = _sha256_bytes(content)
        # Pre-seed the state with this hash.
        _save_json({sha: {"filename": "prev.txt", "ingested_at": "2026-01-01T00:00:00+00:00"}}, state_path)

        txt_file = drop_folder / "hello.txt"
        txt_file.write_bytes(content)

        handler = _DropFolderHandler(
            add_ep,
            drop_folder=drop_folder,
            processed_dir=processed_dir,
            state_path=state_path,
            loop=asyncio.get_event_loop(),
        )
        await handler._ingest(txt_file)

        # No ingestion because hash already known.
        assert add_ep.calls == []
        # File not moved.
        assert txt_file.exists()

    async def test_sensitive_filename_is_skipped(self, tmp_path):
        drop_folder = tmp_path / "imports"
        drop_folder.mkdir()
        state_path = tmp_path / "drop_state.json"
        add_ep = FakeAddEpisode()

        # "secret" is in SKIP_PATTERNS from sidecar.ingest.is_sensitive_name
        secret_file = drop_folder / "my_secret_notes.txt"
        secret_file.write_text("sk-supersecret", encoding="utf-8")

        handler = _DropFolderHandler(
            add_ep,
            drop_folder=drop_folder,
            processed_dir=drop_folder / "processed",
            state_path=state_path,
            loop=asyncio.get_event_loop(),
        )
        await handler._ingest(secret_file)

        assert add_ep.calls == []
        assert secret_file.exists()  # file not moved

    async def test_unsupported_extension_is_skipped(self, tmp_path):
        drop_folder = tmp_path / "imports"
        drop_folder.mkdir()
        state_path = tmp_path / "drop_state.json"
        add_ep = FakeAddEpisode()

        bin_file = drop_folder / "data.xyz"
        bin_file.write_bytes(b"\x00\x01\x02\x03")

        handler = _DropFolderHandler(
            add_ep,
            drop_folder=drop_folder,
            processed_dir=drop_folder / "processed",
            state_path=state_path,
            loop=asyncio.get_event_loop(),
        )
        await handler._ingest(bin_file)

        assert add_ep.calls == []

    async def test_add_episode_failure_does_not_move_file_or_update_state(self, tmp_path):
        drop_folder = tmp_path / "imports"
        drop_folder.mkdir()
        processed_dir = drop_folder / "processed"
        state_path = tmp_path / "drop_state.json"
        add_ep = FakeAddEpisode(fail=True)

        txt_file = drop_folder / "important.txt"
        txt_file.write_text("critical content", encoding="utf-8")

        handler = _DropFolderHandler(
            add_ep,
            drop_folder=drop_folder,
            processed_dir=processed_dir,
            state_path=state_path,
            loop=asyncio.get_event_loop(),
        )
        await handler._ingest(txt_file)

        # File should still be present (not moved on failure).
        assert txt_file.exists()
        # State should not be updated.
        assert not state_path.exists()

    async def test_dedup_state_persists_across_separate_handler_instances(self, tmp_path):
        drop_folder = tmp_path / "imports"
        drop_folder.mkdir()
        processed_dir = drop_folder / "processed"
        state_path = tmp_path / "drop_state.json"
        add_ep1 = FakeAddEpisode()

        content = "persist across runs"
        txt_file = drop_folder / "doc.txt"
        txt_file.write_text(content, encoding="utf-8")

        handler1 = _DropFolderHandler(
            add_ep1,
            drop_folder=drop_folder,
            processed_dir=processed_dir,
            state_path=state_path,
            loop=asyncio.get_event_loop(),
        )
        await handler1._ingest(txt_file)
        assert len(add_ep1.calls) == 1

        # Re-create the file with same content (same hash) in drop folder.
        txt_file2 = drop_folder / "doc.txt"
        txt_file2.write_text(content, encoding="utf-8")

        add_ep2 = FakeAddEpisode()
        handler2 = _DropFolderHandler(
            add_ep2,
            drop_folder=drop_folder,
            processed_dir=processed_dir,
            state_path=state_path,
            loop=asyncio.get_event_loop(),
        )
        await handler2._ingest(txt_file2)

        # Second handler should see existing state and skip.
        assert add_ep2.calls == []

    async def test_processed_subdir_files_are_ignored(self, tmp_path):
        drop_folder = tmp_path / "imports"
        drop_folder.mkdir()
        processed_dir = drop_folder / "processed"
        processed_dir.mkdir()
        state_path = tmp_path / "drop_state.json"
        add_ep = FakeAddEpisode()

        # File already in processed/ — should be ignored.
        proc_file = processed_dir / "abc123-old.txt"
        proc_file.write_text("already done", encoding="utf-8")

        handler = _DropFolderHandler(
            add_ep,
            drop_folder=drop_folder,
            processed_dir=processed_dir,
            state_path=state_path,
            loop=asyncio.get_event_loop(),
        )
        await handler._ingest(proc_file)

        assert add_ep.calls == []


# ── Local files tests ─────────────────────────────────────────────────────────


class TestLocalFiles:
    async def test_happy_path_md_file_ingested(self, tmp_path):
        watch_dir = tmp_path / "research"
        watch_dir.mkdir()
        state_path = tmp_path / "local_files_state.json"
        add_ep = FakeAddEpisode()

        md_file = watch_dir / "paper.md"
        md_file.write_text("# Research\n\nImportant findings.", encoding="utf-8")

        handler = _LocalFilesHandler(
            add_ep,
            max_file_size_bytes=10 * 1024 * 1024,
            state_path=state_path,
            loop=asyncio.get_event_loop(),
        )
        await handler._ingest(md_file)

        assert len(add_ep.calls) == 1
        assert add_ep.calls[0]["name"] == "paper.md"
        assert add_ep.calls[0]["source_description"] == "local-files"
        assert "Research" in add_ep.calls[0]["content"]

    async def test_oversized_file_is_skipped(self, tmp_path):
        watch_dir = tmp_path / "downloads"
        watch_dir.mkdir()
        state_path = tmp_path / "local_files_state.json"
        add_ep = FakeAddEpisode()

        big_file = watch_dir / "huge.txt"
        # 1 byte over the 100-byte limit for this test.
        big_file.write_bytes(b"x" * 101)

        handler = _LocalFilesHandler(
            add_ep,
            max_file_size_bytes=100,
            state_path=state_path,
            loop=asyncio.get_event_loop(),
        )
        await handler._ingest(big_file)

        assert add_ep.calls == []

    async def test_sensitive_filename_is_skipped(self, tmp_path):
        watch_dir = tmp_path / "docs"
        watch_dir.mkdir()
        state_path = tmp_path / "local_files_state.json"
        add_ep = FakeAddEpisode()

        secret_file = watch_dir / "password_vault.txt"
        secret_file.write_text("p@ssw0rd", encoding="utf-8")

        handler = _LocalFilesHandler(
            add_ep,
            max_file_size_bytes=10 * 1024 * 1024,
            state_path=state_path,
            loop=asyncio.get_event_loop(),
        )
        await handler._ingest(secret_file)

        assert add_ep.calls == []

    async def test_dedup_state_prevents_re_ingestion(self, tmp_path):
        watch_dir = tmp_path / "research"
        watch_dir.mkdir()
        state_path = tmp_path / "local_files_state.json"
        add_ep = FakeAddEpisode()

        md_file = watch_dir / "notes.md"
        content = "# Stable notes"
        md_file.write_text(content, encoding="utf-8")

        handler = _LocalFilesHandler(
            add_ep,
            max_file_size_bytes=10 * 1024 * 1024,
            state_path=state_path,
            loop=asyncio.get_event_loop(),
        )

        await handler._ingest(md_file)
        assert len(add_ep.calls) == 1

        # Second call — same file, same content — should be deduped.
        await handler._ingest(md_file)
        assert len(add_ep.calls) == 1  # still only 1

    async def test_changed_content_triggers_new_ingestion(self, tmp_path):
        watch_dir = tmp_path / "research"
        watch_dir.mkdir()
        state_path = tmp_path / "local_files_state.json"
        add_ep = FakeAddEpisode()

        md_file = watch_dir / "evolving.md"
        md_file.write_text("version 1", encoding="utf-8")

        handler = _LocalFilesHandler(
            add_ep,
            max_file_size_bytes=10 * 1024 * 1024,
            state_path=state_path,
            loop=asyncio.get_event_loop(),
        )
        await handler._ingest(md_file)
        assert len(add_ep.calls) == 1

        # Overwrite with new content — hash changes, new dedup key.
        md_file.write_text("version 2 — updated content", encoding="utf-8")
        await handler._ingest(md_file)
        assert len(add_ep.calls) == 2


# ── iMessage helpers ──────────────────────────────────────────────────────────


def _now_apple_ns() -> int:
    """Current time as Apple epoch nanoseconds."""
    unix_now = datetime.now(tz=timezone.utc).timestamp()
    return int((unix_now - APPLE_EPOCH_OFFSET) * 1_000_000_000)


def _make_chat_db(path: Path) -> sqlite3.Connection:
    """
    Create a minimal chat.db schema at *path* and return the open connection.

    Tables: message, handle, chat_message_join (schema matches macOS 12+ layout).
    """
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS handle (
            rowid  INTEGER PRIMARY KEY,
            id     TEXT
        );
        CREATE TABLE IF NOT EXISTS message (
            rowid       INTEGER PRIMARY KEY,
            handle_id   INTEGER,
            date        INTEGER,
            text        TEXT,
            is_from_me  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS chat_message_join (
            chat_id     INTEGER,
            message_id  INTEGER
        );
    """)
    conn.commit()
    return conn


def _insert_handle(conn: sqlite3.Connection, id_str: str) -> int:
    cur = conn.execute("INSERT INTO handle (id) VALUES (?)", (id_str,))
    conn.commit()
    return cur.lastrowid


def _insert_message(
    conn: sqlite3.Connection,
    *,
    handle_rowid: int,
    date_ns: int,
    text: str,
    is_from_me: int = 0,
) -> int:
    cur = conn.execute(
        "INSERT INTO message (handle_id, date, text, is_from_me) VALUES (?, ?, ?, ?)",
        (handle_rowid, date_ns, text, is_from_me),
    )
    conn.commit()
    return cur.lastrowid


# ── iMessage tests ────────────────────────────────────────────────────────────


class TestIMessage:
    async def test_opt_in_gate_returns_zero_when_disabled(self, tmp_path):
        add_ep = FakeAddEpisode()
        db_path = tmp_path / "chat.db"
        _make_chat_db(db_path)

        result = await run_imessage_watcher(
            add_ep,
            enable=False,
            db_path=db_path,
            state_path=tmp_path / "imessage_state.json",
        )

        assert result == 0
        assert add_ep.calls == []

    async def test_opt_in_gate_does_not_query_db_when_disabled(self, tmp_path):
        add_ep = FakeAddEpisode()
        # Provide no DB at all — if the gate is correctly honoured, no error.
        missing_db = tmp_path / "nonexistent_chat.db"

        result = await run_imessage_watcher(
            add_ep,
            enable=False,
            db_path=missing_db,
            state_path=tmp_path / "imessage_state.json",
        )

        assert result == 0

    async def test_happy_path_ingests_conversation(self, tmp_path):
        db_path = tmp_path / "chat.db"
        conn = _make_chat_db(db_path)

        handle_rowid = _insert_handle(conn, "+15551234567")
        now_ns = _now_apple_ns()
        _insert_message(conn, handle_rowid=handle_rowid, date_ns=now_ns - 1_000_000_000, text="Hey!", is_from_me=0)
        _insert_message(conn, handle_rowid=handle_rowid, date_ns=now_ns, text="What's up?", is_from_me=1)
        conn.close()

        add_ep = FakeAddEpisode()
        result = await run_imessage_watcher(
            add_ep,
            enable=True,
            checkpoint_hours=24,
            db_path=db_path,
            state_path=tmp_path / "imessage_state.json",
        )

        assert result == 1
        assert len(add_ep.calls) == 1
        ep = add_ep.calls[0]
        assert ep["source_description"] == "imessage"
        assert "+15551234567" in ep["content"]
        assert "Hey!" in ep["content"]
        assert "What's up?" in ep["content"]

    async def test_duplicate_conversation_is_skipped(self, tmp_path):
        db_path = tmp_path / "chat.db"
        conn = _make_chat_db(db_path)

        handle_rowid = _insert_handle(conn, "+15550000001")
        now_ns = _now_apple_ns()
        rowid = _insert_message(conn, handle_rowid=handle_rowid, date_ns=now_ns, text="Hello", is_from_me=0)
        conn.close()

        state_path = tmp_path / "imessage_state.json"
        # Pre-seed with the dedup key for this conversation.
        dedup_key = f"{handle_rowid}::{rowid}"
        _save_json({dedup_key: {"handle": "+15550000001", "ingested_at": "2026-01-01T00:00:00+00:00"}}, state_path)

        add_ep = FakeAddEpisode()
        result = await run_imessage_watcher(
            add_ep,
            enable=True,
            checkpoint_hours=24,
            db_path=db_path,
            state_path=state_path,
        )

        assert result == 0
        assert add_ep.calls == []

    async def test_sensitive_handle_is_skipped(self, tmp_path):
        db_path = tmp_path / "chat.db"
        conn = _make_chat_db(db_path)

        handle_rowid = _insert_handle(conn, "password_reset@example.com")
        now_ns = _now_apple_ns()
        _insert_message(conn, handle_rowid=handle_rowid, date_ns=now_ns, text="Reset link", is_from_me=0)
        conn.close()

        add_ep = FakeAddEpisode()
        result = await run_imessage_watcher(
            add_ep,
            enable=True,
            checkpoint_hours=24,
            db_path=db_path,
            state_path=tmp_path / "imessage_state.json",
        )

        assert result == 0
        assert add_ep.calls == []

    async def test_messages_outside_checkpoint_window_not_ingested(self, tmp_path):
        db_path = tmp_path / "chat.db"
        conn = _make_chat_db(db_path)

        handle_rowid = _insert_handle(conn, "+15559990000")
        # Place message 48 hours in the past; checkpoint_hours=1 → should be excluded.
        old_unix = datetime.now(tz=timezone.utc).timestamp() - 48 * 3600
        old_apple_ns = int((old_unix - APPLE_EPOCH_OFFSET) * 1_000_000_000)
        _insert_message(conn, handle_rowid=handle_rowid, date_ns=old_apple_ns, text="Old message", is_from_me=0)
        conn.close()

        add_ep = FakeAddEpisode()
        result = await run_imessage_watcher(
            add_ep,
            enable=True,
            checkpoint_hours=1,
            db_path=db_path,
            state_path=tmp_path / "imessage_state.json",
        )

        assert result == 0

    async def test_dedup_state_persists_across_calls(self, tmp_path):
        db_path = tmp_path / "chat.db"
        conn = _make_chat_db(db_path)

        handle_rowid = _insert_handle(conn, "+15551112222")
        now_ns = _now_apple_ns()
        _insert_message(conn, handle_rowid=handle_rowid, date_ns=now_ns, text="Persistent dedup", is_from_me=0)
        conn.close()

        state_path = tmp_path / "imessage_state.json"
        add_ep1 = FakeAddEpisode()
        result1 = await run_imessage_watcher(
            add_ep1,
            enable=True,
            checkpoint_hours=24,
            db_path=db_path,
            state_path=state_path,
        )
        assert result1 == 1

        # Second call — same state file — should skip.
        add_ep2 = FakeAddEpisode()
        result2 = await run_imessage_watcher(
            add_ep2,
            enable=True,
            checkpoint_hours=24,
            db_path=db_path,
            state_path=state_path,
        )
        assert result2 == 0
        assert add_ep2.calls == []

    async def test_missing_db_returns_zero(self, tmp_path):
        add_ep = FakeAddEpisode()
        result = await run_imessage_watcher(
            add_ep,
            enable=True,
            db_path=tmp_path / "no_such_chat.db",
            state_path=tmp_path / "imessage_state.json",
        )
        assert result == 0
        assert add_ep.calls == []
