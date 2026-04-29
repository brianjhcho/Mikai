"""
Tests for sync.py — the Mode 1 filesystem ingestion daemon for Apple Notes
+ Claude Code per ARCH-023.

Production code calls out to osascript (Apple Notes), reads JSONL files off
disk (Claude Code sessions), and writes episodes into Graphiti. None of that
is appropriate to exercise in a unit test. sync.py's public functions accept
their collaborators as keyword-only parameters — tests pass fakes and assert
on observable effects: episodes ingested, state advanced, dedup honored.

This follows the same Humble Object discipline used in test_mcp_ingest.py
and formalized as D-047.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

import sync


# ── Test doubles ─────────────────────────────────────────────────────────────


@dataclass
class FakeIngestCall:
    name: str
    content: str
    source_description: str
    reference_time: datetime
    group_id: str


class FakeIngestFn:
    """Records every call that a sync function makes."""

    def __init__(self, fail_on: set[int] | None = None) -> None:
        self.calls: list[FakeIngestCall] = []
        self._fail_on = fail_on or set()

    async def __call__(
        self, *, name: str, content: str, source_description: str,
        reference_time: datetime, group_id: str,
    ) -> None:
        idx = len(self.calls)
        self.calls.append(FakeIngestCall(
            name=name, content=content,
            source_description=source_description,
            reference_time=reference_time, group_id=group_id,
        ))
        if idx in self._fail_on:
            raise RuntimeError(f"simulated ingest failure at call {idx}")


def make_osascript_runner(stdout: str = "", stderr: str = "", rc: int = 0):
    def _run(_script: str) -> tuple[str, str, int]:
        return stdout, stderr, rc
    return _run


def make_legacy_fetcher(stdout: str = "", stderr: str = "", rc: int = 0):
    """Wrap the osascript runner as a NotesFetcher so tests can keep their
    canned-stdout style without paying for the SQLite path. Mirrors what
    sync.py does when --legacy-applescript is passed."""
    runner = make_osascript_runner(stdout=stdout, stderr=stderr, rc=rc)
    return lambda: sync.fetch_apple_notes(runner=runner)


async def _noop_sleep(_seconds: float) -> None:
    return None


def _fixed_now(iso: str):
    dt = datetime.fromisoformat(iso)
    return lambda: dt


def _encode_osascript_notes(notes: list[tuple[str, str]]) -> str:
    """Emit the null-delimited format that the osascript template produces."""
    chunks = [f"{title}\x00{body}" for title, body in notes]
    return "\x01".join(chunks) + "\x01"


# ── fetch_apple_notes ────────────────────────────────────────────────────────


class TestFetchAppleNotes:
    def test_rc_nonzero_returns_none(self):
        runner = make_osascript_runner(stderr="not authorized", rc=1)
        assert sync.fetch_apple_notes(runner=runner) is None

    def test_empty_stdout_returns_empty_list(self):
        runner = make_osascript_runner(stdout="")
        assert sync.fetch_apple_notes(runner=runner) == []

    def test_parses_single_note(self):
        raw = _encode_osascript_notes([("My title", "My body content")])
        runner = make_osascript_runner(stdout=raw)
        notes = sync.fetch_apple_notes(runner=runner)
        assert len(notes) == 1
        identifier, title, body = notes[0]
        assert title == "My title"
        assert body == "My body content"
        assert identifier.startswith("applescript:")

    def test_parses_multiple_notes(self):
        raw = _encode_osascript_notes([
            ("First", "body1"),
            ("Second", "body2"),
            ("Third", "body3"),
        ])
        runner = make_osascript_runner(stdout=raw)
        notes = sync.fetch_apple_notes(runner=runner)
        assert [t for _, t, _ in notes] == ["First", "Second", "Third"]
        # All identifiers must be unique — same title on different notes
        # would otherwise re-ingest forever (regression for O-039 dedup).
        assert len({i for i, _, _ in notes}) == 3

    def test_handles_empty_body(self):
        raw = "Title only\x00\x01"
        runner = make_osascript_runner(stdout=raw)
        notes = sync.fetch_apple_notes(runner=runner)
        assert len(notes) == 1
        _, title, body = notes[0]
        assert (title, body) == ("Title only", "")

    def test_duplicate_titles_get_distinct_identifiers(self):
        """Regression for the dedup bug: two notes with the same title but
        different content must still be tracked independently."""
        raw = _encode_osascript_notes([
            ("Sept 2022", "first month log"),
            ("Sept 2022", "second month log"),
        ])
        runner = make_osascript_runner(stdout=raw)
        notes = sync.fetch_apple_notes(runner=runner)
        ids = [i for i, _, _ in notes]
        assert ids[0] != ids[1]


# ── sync_apple_notes ─────────────────────────────────────────────────────────


class TestSyncAppleNotes:
    async def test_ingests_every_new_note(self, tmp_path):
        raw = _encode_osascript_notes([
            ("n1", "body one"),
            ("n2", "body two"),
        ])
        state: dict = {}
        fake = FakeIngestFn()

        count = await sync.sync_apple_notes(
            state,
            ingest_fn=fake,
            notes_fetcher=make_legacy_fetcher(stdout=raw),
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep,
            state_path=tmp_path / "state.json",
        )

        assert count == 2
        assert [c.content for c in fake.calls] == [
            "# n1\n\nbody one",
            "# n2\n\nbody two",
        ]
        assert all(c.source_description == "apple-notes" for c in fake.calls)
        assert all(c.group_id == sync.GROUP_ID_APPLE_NOTES for c in fake.calls)

    async def test_unchanged_note_is_skipped_on_second_pass(self, tmp_path):
        raw = _encode_osascript_notes([("n1", "same body")])
        state: dict = {}
        fake = FakeIngestFn()
        kwargs = dict(
            notes_fetcher=make_legacy_fetcher(stdout=raw),
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep,
            state_path=tmp_path / "state.json",
        )
        await sync.sync_apple_notes(state, ingest_fn=fake, **kwargs)
        assert len(fake.calls) == 1
        await sync.sync_apple_notes(state, ingest_fn=fake, **kwargs)
        assert len(fake.calls) == 1  # dedup held

    async def test_modified_note_is_re_ingested(self, tmp_path):
        state: dict = {}
        fake = FakeIngestFn()
        kwargs = dict(
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep,
            state_path=tmp_path / "state.json",
        )
        first_raw = _encode_osascript_notes([("n1", "original body")])
        await sync.sync_apple_notes(
            state, ingest_fn=fake,
            notes_fetcher=make_legacy_fetcher(stdout=first_raw), **kwargs,
        )
        second_raw = _encode_osascript_notes([("n1", "edited body — now longer")])
        await sync.sync_apple_notes(
            state, ingest_fn=fake,
            notes_fetcher=make_legacy_fetcher(stdout=second_raw), **kwargs,
        )
        assert len(fake.calls) == 2
        assert "original body" in fake.calls[0].content
        assert "edited body" in fake.calls[1].content

    async def test_osascript_failure_returns_zero(self, tmp_path):
        fake = FakeIngestFn()
        count = await sync.sync_apple_notes(
            {},
            ingest_fn=fake,
            notes_fetcher=make_legacy_fetcher(stderr="not authorized", rc=1),
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep,
            state_path=tmp_path / "state.json",
        )
        assert count == 0
        assert fake.calls == []

    async def test_state_is_persisted_across_passes(self, tmp_path):
        raw = _encode_osascript_notes([("n1", "body")])
        state_path = tmp_path / "state.json"

        fake1 = FakeIngestFn()
        state1: dict = {}
        await sync.sync_apple_notes(
            state1, ingest_fn=fake1,
            notes_fetcher=make_legacy_fetcher(stdout=raw),
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep, state_path=state_path,
        )
        assert len(fake1.calls) == 1

        # Second pass in a fresh process — reload state from disk.
        from sidecar.ingest import load_state
        state2 = load_state(state_path)
        fake2 = FakeIngestFn()
        await sync.sync_apple_notes(
            state2, ingest_fn=fake2,
            notes_fetcher=make_legacy_fetcher(stdout=raw),
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep, state_path=state_path,
        )
        assert fake2.calls == []  # persisted dedup held across the restart

    async def test_blank_title_and_body_skipped(self, tmp_path):
        raw = "\x00\x01" + _encode_osascript_notes([("real", "content here")])
        fake = FakeIngestFn()
        await sync.sync_apple_notes(
            {},
            ingest_fn=fake,
            notes_fetcher=make_legacy_fetcher(stdout=raw),
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep,
            state_path=tmp_path / "state.json",
        )
        assert [c.name for c in fake.calls] == ["apple-notes::real"]


# ── tail_jsonl ───────────────────────────────────────────────────────────────


class TestTailJsonl:
    def test_reads_all_lines_from_offset_zero(self, tmp_path):
        p = tmp_path / "session.jsonl"
        p.write_text('{"a":1}\n{"b":2}\n{"c":3}\n')
        records, new_offset = sync.tail_jsonl(p, 0)
        assert records == [{"a": 1}, {"b": 2}, {"c": 3}]
        assert new_offset == p.stat().st_size

    def test_reads_nothing_when_offset_at_eof(self, tmp_path):
        p = tmp_path / "session.jsonl"
        p.write_text('{"a":1}\n')
        size = p.stat().st_size
        records, new_offset = sync.tail_jsonl(p, size)
        assert records == []
        assert new_offset == size

    def test_reads_only_new_lines_when_appended(self, tmp_path):
        p = tmp_path / "session.jsonl"
        p.write_text('{"a":1}\n')
        first_offset = p.stat().st_size
        # Append more content
        with p.open("a") as f:
            f.write('{"b":2}\n')
        records, new_offset = sync.tail_jsonl(p, first_offset)
        assert records == [{"b": 2}]
        assert new_offset == p.stat().st_size

    def test_skips_malformed_lines(self, tmp_path):
        p = tmp_path / "session.jsonl"
        p.write_text('{"ok":1}\n{not json\n{"ok":2}\n')
        records, _ = sync.tail_jsonl(p, 0)
        assert records == [{"ok": 1}, {"ok": 2}]

    def test_missing_file_returns_empty_and_preserves_offset(self, tmp_path):
        records, new_offset = sync.tail_jsonl(tmp_path / "nope.jsonl", 42)
        assert records == []
        assert new_offset == 42


# ── extract_turns ─────────────────────────────────────────────────────────────


class TestExtractTurns:
    def test_flat_string_content(self):
        recs = [
            {"type": "human", "content": "hi", "timestamp": "2026-01-01T00:00:00"},
            {"type": "assistant", "content": "hello"},
        ]
        turns = sync.extract_turns(recs)
        assert [t["role"] for t in turns] == ["user", "assistant"]
        assert turns[0]["content"] == "hi"
        assert turns[1]["content"] == "hello"

    def test_nested_message_content(self):
        recs = [
            {"type": "user", "message": {"role": "user", "content": "from nested"}},
        ]
        turns = sync.extract_turns(recs)
        assert turns == [{"role": "user", "content": "from nested", "ts": None}]

    def test_content_list_with_text_blocks(self):
        recs = [
            {"type": "assistant", "content": [
                {"type": "text", "text": "part one"},
                {"type": "text", "text": "part two"},
            ]},
        ]
        turns = sync.extract_turns(recs)
        assert turns[0]["content"] == "part one\npart two"

    def test_tool_result_text_is_extracted(self):
        recs = [
            {"type": "assistant", "content": [
                {"type": "tool_result", "content": [
                    {"type": "text", "text": "tool output"},
                ]},
            ]},
        ]
        turns = sync.extract_turns(recs)
        assert turns[0]["content"] == "tool output"

    def test_empty_content_dropped(self):
        recs = [
            {"type": "user", "content": ""},
            {"type": "assistant", "content": "  \n "},
            {"type": "user", "content": "real"},
        ]
        turns = sync.extract_turns(recs)
        assert [t["content"] for t in turns] == ["real"]

    def test_non_conversation_types_skipped(self):
        recs = [
            {"type": "system", "content": "ignore me"},
            {"type": "summary", "content": "ignore me too"},
            {"type": "human", "content": "real"},
        ]
        turns = sync.extract_turns(recs)
        assert len(turns) == 1

    def test_handles_empty_input(self):
        assert sync.extract_turns([]) == []


# ── sync_claude_code ─────────────────────────────────────────────────────────


class TestSyncClaudeCode:
    async def test_ingests_new_turns_from_one_file(self, tmp_path):
        sess = tmp_path / "session.jsonl"
        sess.write_text(
            json.dumps({"type": "human", "content": "q1"}) + "\n" +
            json.dumps({"type": "assistant", "content": "a1"}) + "\n"
        )
        fake = FakeIngestFn()
        state: dict = {}
        count = await sync.sync_claude_code(
            state, ingest_fn=fake,
            lister=lambda _base: [sess],
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep,
            base_path=tmp_path,
            state_path=tmp_path / "state.json",
        )
        assert count == 2
        assert [c.content for c in fake.calls] == ["[user] q1", "[assistant] a1"]

    async def test_offset_persists_so_second_pass_is_noop(self, tmp_path):
        sess = tmp_path / "s.jsonl"
        sess.write_text(json.dumps({"type": "human", "content": "q"}) + "\n")
        fake = FakeIngestFn()
        state: dict = {}
        kwargs = dict(
            lister=lambda _b: [sess],
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep,
            base_path=tmp_path,
            state_path=tmp_path / "state.json",
        )
        await sync.sync_claude_code(state, ingest_fn=fake, **kwargs)
        assert len(fake.calls) == 1
        await sync.sync_claude_code(state, ingest_fn=fake, **kwargs)
        assert len(fake.calls) == 1

    async def test_appended_turns_picked_up_on_next_pass(self, tmp_path):
        sess = tmp_path / "s.jsonl"
        sess.write_text(json.dumps({"type": "human", "content": "first"}) + "\n")
        fake = FakeIngestFn()
        state: dict = {}
        kwargs = dict(
            lister=lambda _b: [sess],
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep,
            base_path=tmp_path,
            state_path=tmp_path / "state.json",
        )
        await sync.sync_claude_code(state, ingest_fn=fake, **kwargs)
        with sess.open("a") as f:
            f.write(json.dumps({"type": "assistant", "content": "second"}) + "\n")
        await sync.sync_claude_code(state, ingest_fn=fake, **kwargs)
        assert [c.content for c in fake.calls] == ["[user] first", "[assistant] second"]

    async def test_no_files_noop(self, tmp_path):
        fake = FakeIngestFn()
        count = await sync.sync_claude_code(
            {}, ingest_fn=fake,
            lister=lambda _b: [],
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep,
            base_path=tmp_path,
            state_path=tmp_path / "state.json",
        )
        assert count == 0
        assert fake.calls == []

    async def test_ts_from_record_used_when_valid(self, tmp_path):
        sess = tmp_path / "s.jsonl"
        sess.write_text(
            json.dumps({
                "type": "human", "content": "q",
                "timestamp": "2025-03-01T12:00:00+00:00",
            }) + "\n"
        )
        fake = FakeIngestFn()
        await sync.sync_claude_code(
            {}, ingest_fn=fake,
            lister=lambda _b: [sess],
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep,
            base_path=tmp_path,
            state_path=tmp_path / "state.json",
        )
        assert fake.calls[0].reference_time == datetime.fromisoformat(
            "2025-03-01T12:00:00+00:00"
        )


# ── run_sync_pass ─────────────────────────────────────────────────────────────


class TestRunSyncPass:
    async def test_combines_apple_and_claude_counts(self, tmp_path):
        raw = _encode_osascript_notes([("n1", "body")])
        sess = tmp_path / "s.jsonl"
        sess.write_text(json.dumps({"type": "human", "content": "q"}) + "\n")

        fake = FakeIngestFn()
        notes, turns = await sync.run_sync_pass(
            ingest_fn=fake,
            state_path=tmp_path / "state.json",
            notes_fetcher=make_legacy_fetcher(stdout=raw),
            jsonl_lister=lambda _b: [sess],
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep,
            base_claude_path=tmp_path,
        )
        assert notes == 1
        assert turns == 1
        # Episode counts must match ingest call count
        assert len(fake.calls) == 2
        source_descs = {c.source_description for c in fake.calls}
        assert source_descs == {"apple-notes", "claude-code"}

    async def test_apple_failure_does_not_prevent_claude_pass(self, tmp_path):
        sess = tmp_path / "s.jsonl"
        sess.write_text(json.dumps({"type": "human", "content": "q"}) + "\n")
        fake = FakeIngestFn()
        notes, turns = await sync.run_sync_pass(
            ingest_fn=fake,
            state_path=tmp_path / "state.json",
            notes_fetcher=make_legacy_fetcher(rc=1, stderr="denied"),
            jsonl_lister=lambda _b: [sess],
            now=_fixed_now("2026-04-20T10:00:00+00:00"),
            sleep=_noop_sleep,
            base_claude_path=tmp_path,
        )
        assert notes == 0
        assert turns == 1
