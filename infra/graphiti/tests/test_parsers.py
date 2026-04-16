"""
Tests for the pure-Python parsers in sidecar/ingest.py.

These functions read osascript output, JSON-wrapped Perplexity threads, and
Claude thread dumps. Bugs here silently corrupt episodes before they even
reach Graphiti, which is exactly the kind of failure that wouldn't surface
until much later.
"""

import json

import pytest

from sidecar.ingest import (
    NOTE_SEPARATOR,
    FIELD_SEPARATOR,
    SKIP_PATTERNS,
    is_sensitive_name,
    parse_claude_turns,
    parse_notes_dump,
    parse_osascript_notes_output,
    parse_perplexity_query_and_answer,
)


# ── is_sensitive_name ────────────────────────────────────────────────────────


class TestIsSensitiveName:
    def test_all_skip_patterns_are_detected(self):
        # Lock in the contract: every configured pattern actually filters.
        for pattern in SKIP_PATTERNS:
            assert is_sensitive_name(f"my {pattern} note")

    def test_is_case_insensitive(self):
        assert is_sensitive_name("My API Key Dump")
        assert is_sensitive_name("PASSWORDS")

    def test_returns_false_for_ordinary_names(self):
        assert not is_sensitive_name("grocery list")
        assert not is_sensitive_name("")
        assert not is_sensitive_name("ideas for 2026")


# ── parse_notes_dump ──────────────────────────────────────────────────────────


DUMP_TEMPLATE = (
    "===NOTE_START===\n"
    "NAME:{name}\n"
    "DATE:{date}\n"
    "{body}\n"
    "===NOTE_END===\n"
)


def _make_dump(*notes: dict) -> str:
    return "".join(
        DUMP_TEMPLATE.format(name=n["name"], date=n["date"], body=n["body"])
        for n in notes
    )


class TestParseNotesDump:
    def test_parses_single_note_from_text_blob(self):
        dump = _make_dump({
            "name": "Reading list",
            "date": "2026-03-01T00:00:00Z",
            "body": "Books I want to read this quarter, with notes:\n- A\n- B\n- C",
        })
        notes = parse_notes_dump(dump)
        assert len(notes) == 1
        assert notes[0]["name"] == "Reading list"
        assert notes[0]["date"] == "2026-03-01T00:00:00Z"
        assert "Books I want to read" in notes[0]["body"]

    def test_parses_multiple_notes_in_order(self):
        dump = _make_dump(
            {"name": "First note", "date": "2026-01-01T00:00:00Z",
             "body": "First body content here — long enough to survive the filter."},
            {"name": "Second note", "date": "2026-02-01T00:00:00Z",
             "body": "Second body content here — long enough to survive the filter."},
        )
        notes = parse_notes_dump(dump)
        assert [n["name"] for n in notes] == ["First note", "Second note"]

    def test_drops_notes_shorter_than_min_body_chars(self):
        dump = _make_dump(
            {"name": "Too short", "date": "2026-01-01", "body": "tiny"},
            {"name": "Fine",      "date": "2026-01-01",
             "body": "x" * 60},
        )
        notes = parse_notes_dump(dump)
        assert [n["name"] for n in notes] == ["Fine"]

    def test_drops_sensitive_notes_by_name(self):
        dump = _make_dump(
            {"name": "API KEYS secret store", "date": "2026-01-01",
             "body": "DO NOT LEAK THIS — " + "x" * 80},
            {"name": "weekly planning",        "date": "2026-01-01",
             "body": "meeting notes — " + "x" * 80},
        )
        notes = parse_notes_dump(dump)
        assert len(notes) == 1
        assert notes[0]["name"] == "weekly planning"

    def test_preserves_body_newlines(self):
        dump = _make_dump({
            "name": "Multi-line",
            "date": "2026-01-01",
            "body": "line one\nline two\nline three\n" + "x" * 40,
        })
        notes = parse_notes_dump(dump)
        assert "line one\nline two\nline three" in notes[0]["body"]

    def test_truncates_when_max_body_chars_set(self):
        body = "x" * 10_000
        dump = _make_dump({"name": "Huge", "date": "2026-01-01", "body": body})
        notes = parse_notes_dump(dump, max_body_chars=500)
        assert len(notes[0]["body"]) == 500

    def test_skips_partial_note_without_end_marker(self):
        dump = (
            "===NOTE_START===\n"
            "NAME:Dangling note\n"
            "DATE:2026-01-01\n"
            "This note was cut off mid-write.\n"
        )
        # No NOTE_END — parser should simply not emit anything.
        assert parse_notes_dump(dump) == []

    def test_handles_empty_input(self):
        assert parse_notes_dump("") == []

    def test_reads_from_file_path(self, tmp_path):
        body = "persisted content " + "x" * 60
        dump = _make_dump({"name": "From file", "date": "2026-01-01", "body": body})
        p = tmp_path / "dump.txt"
        p.write_text(dump)
        notes = parse_notes_dump(p)
        assert len(notes) == 1
        assert notes[0]["name"] == "From file"


# ── parse_osascript_notes_output ──────────────────────────────────────────────


def _osascript_blob(*notes: tuple[str, str, str]) -> str:
    """Build the single-line delimited format that osascript emits."""
    out = ""
    for name, body, date in notes:
        out += NOTE_SEPARATOR + name + FIELD_SEPARATOR + body + FIELD_SEPARATOR + date
    return out


class TestParseOsascriptNotesOutput:
    def test_extracts_all_fields(self):
        blob = _osascript_blob(
            ("Morning routine", "wake, coffee, read — " + "x" * 50, "2026-03-01T00:00:00Z"),
        )
        notes = parse_osascript_notes_output(blob)
        assert len(notes) == 1
        n = notes[0]
        assert n["name"] == "Morning routine"
        assert "wake, coffee, read" in n["body"]
        assert n["date"] == "2026-03-01T00:00:00Z"

    def test_skips_short_bodies(self):
        blob = _osascript_blob(
            ("Short", "tiny", "2026-01-01T00:00:00Z"),
            ("Long",  "x" * 80, "2026-01-01T00:00:00Z"),
        )
        names = [n["name"] for n in parse_osascript_notes_output(blob)]
        assert names == ["Long"]

    def test_skips_sensitive_names(self):
        blob = _osascript_blob(
            ("My PASSWORDS", "secret " + "x" * 80, "2026-01-01"),
            ("Ordinary",     "text " + "x" * 80,   "2026-01-01"),
        )
        names = [n["name"] for n in parse_osascript_notes_output(blob)]
        assert names == ["Ordinary"]

    def test_skips_entries_with_too_few_fields(self):
        # Missing date field — fewer than 3 FIELD_SEPARATORs.
        broken = NOTE_SEPARATOR + "Name" + FIELD_SEPARATOR + "body " + "x" * 80
        assert parse_osascript_notes_output(broken) == []

    def test_empty_input_returns_empty_list(self):
        assert parse_osascript_notes_output("") == []


# ── parse_claude_turns ────────────────────────────────────────────────────────


class TestParseClaudeTurns:
    def test_splits_alternating_turns(self):
        raw = (
            "[User]: hi there\n"
            "[Assistant]: hello\n"
            "[User]: how are you\n"
            "[Assistant]: fine thanks\n"
        )
        turns = parse_claude_turns(raw)
        assert [t["role"] for t in turns] == ["user", "assistant", "user", "assistant"]
        assert turns[0]["content"] == "hi there"
        assert turns[3]["content"] == "fine thanks"

    def test_multi_line_turn_content_is_joined(self):
        raw = (
            "[User]: first prompt\n"
            "with a second line\n"
            "and a third\n"
            "[Assistant]: one-line reply\n"
        )
        turns = parse_claude_turns(raw)
        assert turns[0]["role"] == "user"
        assert "first prompt" in turns[0]["content"]
        assert "with a second line" in turns[0]["content"]
        assert "and a third" in turns[0]["content"]

    def test_handles_empty_input(self):
        assert parse_claude_turns("") == []

    def test_preamble_before_first_marker_is_discarded(self):
        raw = "some header text\n[User]: the actual start\n[Assistant]: reply\n"
        turns = parse_claude_turns(raw)
        assert len(turns) == 2
        assert turns[0]["role"] == "user"
        assert turns[0]["content"] == "the actual start"

    def test_last_turn_without_trailing_newline_still_captured(self):
        raw = "[User]: q\n[Assistant]: final answer with no newline"
        turns = parse_claude_turns(raw)
        assert turns[-1]["role"] == "assistant"
        assert turns[-1]["content"] == "final answer with no newline"


# ── parse_perplexity_query_and_answer ─────────────────────────────────────────


def _perplexity_json(query: str, answer: str | dict) -> str:
    """Build a realistic two-step INITIAL_QUERY + FINAL array."""
    answer_payload = (
        json.dumps(answer) if isinstance(answer, dict) else answer
    )
    return json.dumps([
        {"step_type": "INITIAL_QUERY", "content": {"query": query}},
        {"step_type": "FINAL", "content": {"answer": answer_payload}},
    ])


class TestParsePerplexityQueryAndAnswer:
    def test_extracts_query_and_plain_answer(self):
        raw = _perplexity_json("what is graphiti?", "a knowledge-graph framework")
        q, a = parse_perplexity_query_and_answer(raw)
        assert q == "what is graphiti?"
        assert a == "a knowledge-graph framework"

    def test_unwraps_double_encoded_answer(self):
        # FINAL.answer is itself a JSON string with an 'answer' field.
        raw = _perplexity_json(
            "why?",
            {"answer": "the real payload", "citations": ["a", "b"]},
        )
        q, a = parse_perplexity_query_and_answer(raw)
        assert q == "why?"
        assert a == "the real payload"

    def test_strips_assistant_prefix(self):
        raw = "[Assistant]: " + _perplexity_json("prefixed q", "prefixed a")
        q, a = parse_perplexity_query_and_answer(raw)
        assert q == "prefixed q"
        assert a == "prefixed a"

    def test_handles_concatenated_arrays_by_taking_first(self):
        first = _perplexity_json("first q", "first a")
        second = _perplexity_json("second q", "second a")
        q, a = parse_perplexity_query_and_answer(first + second)
        # Only the first array is consumed; second is ignored.
        assert q == "first q"
        assert a == "first a"

    def test_malformed_json_returns_none(self):
        q, a = parse_perplexity_query_and_answer("this is not JSON at all")
        assert q is None and a is None

    def test_truncated_json_returns_none(self):
        q, a = parse_perplexity_query_and_answer('[{"step_type": "INITIAL_QUERY"')
        assert q is None and a is None

    def test_single_object_is_accepted_as_one_step(self):
        raw = json.dumps({"step_type": "INITIAL_QUERY", "content": {"query": "solo"}})
        q, a = parse_perplexity_query_and_answer(raw)
        assert q == "solo"
        # No FINAL step, no answer.
        assert a is None

    def test_query_missing_returns_none_for_query(self):
        raw = json.dumps([
            {"step_type": "FINAL", "content": {"answer": "lone answer"}},
        ])
        q, a = parse_perplexity_query_and_answer(raw)
        assert q is None
        assert a == "lone answer"
