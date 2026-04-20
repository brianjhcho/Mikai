"""
Tests for mcp_ingest.poll_source — the cloud-source polling loop.

The real poll path spawns an MCP server subprocess, handshakes with it, calls
a tool, and feeds the result into graphiti-core → Neo4j. None of that is
appropriate to exercise in a unit test. Instead, poll_source accepts its
collaborators (session factory, clock, state path, sleep) as keyword-only
parameters — we pass in-memory fakes and assert on observable effects:
episodes written, checkpoint advanced, failures contained.

This follows the same "Humble Object" pattern already in use for L3 via the
L3Backend port (ARCH-024): push I/O to the edge, test orchestration against
in-memory doubles.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

import pytest

from mcp_ingest import poll_source


# ── Test doubles ─────────────────────────────────────────────────────────────


@dataclass
class FakeTextContent:
    text: str
    type: str = "text"


@dataclass
class FakeImageContent:
    type: str = "image"


@dataclass
class FakeCallToolResult:
    content: list


class FakeSession:
    """Duck-types mcp.client.session.ClientSession's .call_tool()."""

    def __init__(self, content: list | None = None):
        self._content = content or []
        self.call_tool_args: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, args: dict):
        self.call_tool_args.append((name, dict(args)))
        return FakeCallToolResult(content=list(self._content))


def make_session_factory(
    session: FakeSession | None = None,
    *,
    raise_on_enter: Exception | None = None,
):
    """Build an async-context-manager factory compatible with poll_source."""

    @asynccontextmanager
    async def _factory(command, args, env):
        if raise_on_enter is not None:
            raise raise_on_enter
        yield session

    return _factory


class FakeGraphiti:
    """Records every add_episode call; can be rigged to fail on specific indexes."""

    def __init__(self, fail_on: set[int] | None = None):
        self.add_calls: list[dict] = []
        self._fail_on = fail_on or set()

    async def add_episode(self, **kwargs):
        idx = len(self.add_calls)
        self.add_calls.append(kwargs)
        if idx in self._fail_on:
            raise RuntimeError(f"simulated failure on call {idx}")


async def _noop_sleep(_seconds: float) -> None:
    return None


def _fixed_now(iso: str):
    dt = datetime.fromisoformat(iso)
    return lambda: dt


GMAIL_CFG = {
    "command": "npx",
    "args": ["-y", "@anthropic-ai/gmail-mcp"],
    "env": {},
    "tool": "search_emails",
    "tool_args": {"query": "newer_than:1d"},
    "group_id": "gmail",
    "source_description": "gmail",
}


# ── Tests ────────────────────────────────────────────────────────────────────


class TestPollSource:
    async def test_happy_path_ingests_every_text_item(self, tmp_path):
        session = FakeSession(content=[
            FakeTextContent(text="first email body"),
            FakeTextContent(text="second email body"),
        ])
        graphiti = FakeGraphiti()
        state: dict[str, str] = {}
        state_path = tmp_path / "state.json"

        await poll_source(
            "gmail", GMAIL_CFG, graphiti, state,
            session_factory=make_session_factory(session),
            now=_fixed_now("2026-04-17T10:00:00+00:00"),
            state_path=state_path,
            sleep=_noop_sleep,
        )

        # Both items reached graphiti verbatim.
        bodies = [c["episode_body"] for c in graphiti.add_calls]
        assert bodies == ["first email body", "second email body"]

        # Config metadata threads through to the episode.
        assert graphiti.add_calls[0]["group_id"] == "gmail"
        assert graphiti.add_calls[0]["source_description"] == "gmail"
        assert graphiti.add_calls[0]["name"].startswith("gmail-")

        # Checkpoint persisted at the given path.
        assert json.loads(state_path.read_text()) == {
            "gmail": "2026-04-17T10:00:00+00:00",
        }

        # Tool was called with the configured args.
        assert session.call_tool_args == [
            ("search_emails", {"query": "newer_than:1d"}),
        ]

    async def test_last_sync_is_interpolated_from_prior_state(self, tmp_path):
        session = FakeSession(content=[])
        graphiti = FakeGraphiti()
        state = {"drive": "2026-04-10T00:00:00+00:00"}
        state_path = tmp_path / "state.json"
        drive_cfg = {
            **GMAIL_CFG,
            "tool": "search_files",
            "tool_args": {"query": "modifiedTime > '${LAST_SYNC}'"},
            "group_id": "drive",
            "source_description": "drive",
        }

        await poll_source(
            "drive", drive_cfg, graphiti, state,
            session_factory=make_session_factory(session),
            now=_fixed_now("2026-04-17T10:00:00+00:00"),
            state_path=state_path,
            sleep=_noop_sleep,
        )

        # The ${LAST_SYNC} placeholder was filled with the prior checkpoint,
        # not the current-time fallback.
        assert session.call_tool_args == [
            ("search_files",
             {"query": "modifiedTime > '2026-04-10T00:00:00+00:00'"}),
        ]

    async def test_empty_content_still_advances_checkpoint(self, tmp_path):
        session = FakeSession(content=[])
        graphiti = FakeGraphiti()
        state: dict[str, str] = {}
        state_path = tmp_path / "state.json"

        await poll_source(
            "gmail", GMAIL_CFG, graphiti, state,
            session_factory=make_session_factory(session),
            now=_fixed_now("2026-04-17T10:00:00+00:00"),
            state_path=state_path,
            sleep=_noop_sleep,
        )

        assert graphiti.add_calls == []
        # Critical invariant: empty windows must still advance the checkpoint,
        # otherwise the daemon would re-query the same empty range forever.
        assert json.loads(state_path.read_text()) == {
            "gmail": "2026-04-17T10:00:00+00:00",
        }

    async def test_session_failure_leaves_state_untouched(self, tmp_path):
        graphiti = FakeGraphiti()
        prior = "2026-04-01T00:00:00+00:00"
        state = {"gmail": prior}
        state_path = tmp_path / "state.json"
        bad_factory = make_session_factory(
            raise_on_enter=RuntimeError("subprocess crashed"),
        )

        await poll_source(
            "gmail", GMAIL_CFG, graphiti, state,
            session_factory=bad_factory,
            now=_fixed_now("2026-04-17T10:00:00+00:00"),
            state_path=state_path,
            sleep=_noop_sleep,
        )

        # No ingestion, no checkpoint mutation, no state file written.
        assert graphiti.add_calls == []
        assert state == {"gmail": prior}
        assert not state_path.exists()

    async def test_missing_tool_name_is_a_noop(self, tmp_path):
        graphiti = FakeGraphiti()
        state: dict[str, str] = {}
        state_path = tmp_path / "state.json"
        cfg_no_tool = {**GMAIL_CFG, "tool": ""}
        # A factory that would error if invoked — proves the early return
        # happens before session setup.
        bomb = make_session_factory(
            raise_on_enter=AssertionError("factory must not run"),
        )

        await poll_source(
            "gmail", cfg_no_tool, graphiti, state,
            session_factory=bomb,
            now=_fixed_now("2026-04-17T10:00:00+00:00"),
            state_path=state_path,
            sleep=_noop_sleep,
        )

        assert graphiti.add_calls == []
        assert not state_path.exists()

    async def test_non_text_and_blank_items_are_skipped(self, tmp_path):
        session = FakeSession(content=[
            FakeImageContent(),           # non-text type → skipped
            FakeTextContent(text=""),     # empty → skipped
            FakeTextContent(text="   "),  # whitespace → skipped
            FakeTextContent(text="real content"),
        ])
        graphiti = FakeGraphiti()
        state: dict[str, str] = {}
        state_path = tmp_path / "state.json"

        await poll_source(
            "gmail", GMAIL_CFG, graphiti, state,
            session_factory=make_session_factory(session),
            now=_fixed_now("2026-04-17T10:00:00+00:00"),
            state_path=state_path,
            sleep=_noop_sleep,
        )

        assert [c["episode_body"] for c in graphiti.add_calls] == ["real content"]

    async def test_add_episode_failure_does_not_abort_remaining_items(
        self, tmp_path,
    ):
        session = FakeSession(content=[
            FakeTextContent(text="one"),
            FakeTextContent(text="two"),
            FakeTextContent(text="three"),
        ])
        graphiti = FakeGraphiti(fail_on={1})  # middle item fails
        state: dict[str, str] = {}
        state_path = tmp_path / "state.json"

        await poll_source(
            "gmail", GMAIL_CFG, graphiti, state,
            session_factory=make_session_factory(session),
            now=_fixed_now("2026-04-17T10:00:00+00:00"),
            state_path=state_path,
            sleep=_noop_sleep,
        )

        # All three attempts made — one failure does not short-circuit the loop.
        assert [c["episode_body"] for c in graphiti.add_calls] == [
            "one", "two", "three",
        ]
        # Checkpoint still advances; partial failure is expected and retryable.
        assert json.loads(state_path.read_text()) == {
            "gmail": "2026-04-17T10:00:00+00:00",
        }

    async def test_env_overrides_are_layered_on_process_env(
        self, tmp_path, monkeypatch,
    ):
        """Captured env should include both os.environ and source_cfg['env']."""
        monkeypatch.setenv("PROCESS_LEVEL_VAR", "from-process")

        captured: dict = {}

        @asynccontextmanager
        async def capturing_factory(command, args, env):
            captured["command"] = command
            captured["args"] = args
            captured["env"] = env
            yield FakeSession(content=[])

        cfg = {
            **GMAIL_CFG,
            "env": {"SOURCE_LEVEL_VAR": "from-source", "PROCESS_LEVEL_VAR": "overridden"},
        }

        await poll_source(
            "gmail", cfg, FakeGraphiti(), {},
            session_factory=capturing_factory,
            now=_fixed_now("2026-04-17T10:00:00+00:00"),
            state_path=tmp_path / "state.json",
            sleep=_noop_sleep,
        )

        assert captured["command"] == "npx"
        assert captured["env"]["SOURCE_LEVEL_VAR"] == "from-source"
        # Source-level values win over process-level for matching keys.
        assert captured["env"]["PROCESS_LEVEL_VAR"] == "overridden"
