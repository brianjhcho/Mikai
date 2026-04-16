"""
Tests for checkpoint state and tool-arg interpolation in sidecar/ingest.py.

These are the functions that gate "what did we already sync?" across restarts
of the MCP ingestion daemon. A silent bug (e.g. save never reaches disk, load
returns stale data on parse error) would cause the daemon to re-fetch the
same window forever or skip items it should have ingested.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sidecar.ingest import interpolate_tool_args, load_state, save_state


# ── load_state ───────────────────────────────────────────────────────────────


class TestLoadState:
    def test_returns_empty_when_file_missing(self, tmp_path):
        assert load_state(tmp_path / "never_written.json") == {}

    def test_reads_valid_json(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text(json.dumps({"gmail": "2026-03-01T00:00:00Z"}))
        assert load_state(p) == {"gmail": "2026-03-01T00:00:00Z"}

    def test_returns_empty_on_invalid_json(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text("{ not valid json")
        # We want the daemon to keep running, not crash — returning {} means
        # "no prior sync", which on next save will overwrite the bad file.
        assert load_state(p) == {}

    def test_returns_empty_if_file_is_a_list_not_dict(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text(json.dumps(["not", "a", "dict"]))
        assert load_state(p) == {}

    def test_accepts_str_path(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text(json.dumps({"key": "value"}))
        assert load_state(str(p)) == {"key": "value"}


# ── save_state ───────────────────────────────────────────────────────────────


class TestSaveState:
    def test_round_trip_preserves_data(self, tmp_path):
        state = {"gmail": "2026-03-01T00:00:00Z", "drive": "2026-03-02T00:00:00Z"}
        path = tmp_path / "state.json"
        save_state(state, path)
        assert load_state(path) == state

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "nested" / "deeper" / "state.json"
        save_state({"x": "y"}, path)
        assert path.exists()
        assert json.loads(path.read_text()) == {"x": "y"}

    def test_overwrites_existing_file(self, tmp_path):
        path = tmp_path / "state.json"
        save_state({"v": "1"}, path)
        save_state({"v": "2"}, path)
        assert load_state(path) == {"v": "2"}

    def test_writes_pretty_printed_json(self, tmp_path):
        path = tmp_path / "state.json"
        save_state({"a": "b"}, path)
        # indent=2 means there's at least one newline between entries.
        assert "\n" in path.read_text()

    def test_does_not_raise_on_unwritable_path(self, tmp_path):
        # A path where the parent is a file, not a directory, is unwritable.
        blocker = tmp_path / "blocker"
        blocker.write_text("I am a file")
        bad_path = blocker / "state.json"
        # Should log a warning but not raise — callers retry on next poll.
        save_state({"x": "y"}, bad_path)
        # And the state file should not exist.
        assert not bad_path.exists()


# ── interpolate_tool_args ─────────────────────────────────────────────────────


class TestInterpolateToolArgs:
    def test_replaces_last_sync_placeholder(self):
        out = interpolate_tool_args(
            {"query": "modifiedTime > '${LAST_SYNC}'"},
            "2026-03-01T00:00:00Z",
        )
        assert out == {"query": "modifiedTime > '2026-03-01T00:00:00Z'"}

    def test_leaves_non_string_values_untouched(self):
        out = interpolate_tool_args(
            {"limit": 50, "include_drafts": True, "labels": ["a", "b"]},
            "2026-01-01T00:00:00Z",
        )
        assert out == {"limit": 50, "include_drafts": True, "labels": ["a", "b"]}

    def test_leaves_strings_without_placeholder_alone(self):
        out = interpolate_tool_args(
            {"query": "static filter"},
            "2026-01-01T00:00:00Z",
        )
        assert out == {"query": "static filter"}

    def test_last_sync_none_fills_with_current_time(self):
        before = datetime.now(tz=timezone.utc)
        out = interpolate_tool_args({"q": "after ${LAST_SYNC}"}, None)
        after = datetime.now(tz=timezone.utc)

        assert out["q"].startswith("after ")
        iso = out["q"][len("after "):]
        parsed = datetime.fromisoformat(iso)
        # The substituted time should fall between our two wall-clock samples.
        assert before <= parsed <= after

    def test_multiple_placeholders_in_same_string(self):
        out = interpolate_tool_args(
            {"range": "from ${LAST_SYNC} until ${LAST_SYNC}"},
            "2026-03-01T00:00:00Z",
        )
        assert out["range"].count("2026-03-01T00:00:00Z") == 2

    def test_empty_dict_returns_empty_dict(self):
        assert interpolate_tool_args({}, "2026-01-01") == {}
