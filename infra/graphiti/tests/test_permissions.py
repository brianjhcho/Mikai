"""Behavioral tests for the FDA permission helper.

All tests use the same fakes-over-mocks pattern as test_sync.py — inject
collaborators, observe outputs. No live osascript or System Settings calls.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import permissions  # noqa: E402


def _completed(stdout: str = "", returncode: int = 0) -> SimpleNamespace:
    """Mimic enough of subprocess.CompletedProcess for the helper to read."""
    return SimpleNamespace(stdout=stdout, returncode=returncode, stderr="")


# ── check_full_disk_access ──────────────────────────────────────────────────


def test_check_returns_true_on_non_darwin():
    has, reason = permissions.check_full_disk_access(system=lambda: "Linux")
    assert has is True
    assert reason is None


def test_check_returns_false_when_container_invisible(tmp_path: Path):
    canary = tmp_path / "missing-dir" / "NoteStore.sqlite"
    has, reason = permissions.check_full_disk_access(
        canary=canary, system=lambda: "Darwin",
    )
    assert has is False
    assert "container not visible" in (reason or "")


def test_check_returns_false_when_db_missing(tmp_path: Path):
    canary = tmp_path / "NoteStore.sqlite"
    canary.parent.mkdir(parents=True, exist_ok=True)
    has, reason = permissions.check_full_disk_access(
        canary=canary, system=lambda: "Darwin",
    )
    assert has is False
    assert "missing" in (reason or "")


def test_check_returns_true_when_readable(tmp_path: Path):
    canary = tmp_path / "NoteStore.sqlite"
    canary.write_bytes(b"SQLite format 3\x00")
    has, reason = permissions.check_full_disk_access(
        canary=canary, system=lambda: "Darwin",
    )
    assert has is True
    assert reason is None


# ── is_gui_session ──────────────────────────────────────────────────────────


def test_gui_session_false_under_ssh():
    assert permissions.is_gui_session(env={"SSH_CONNECTION": "x"}) is False
    assert permissions.is_gui_session(env={"SSH_CLIENT": "x"}) is False


def test_gui_session_true_under_aqua():
    runs = []
    def runner(*args, **kwargs):
        runs.append(args)
        return _completed(stdout="Aqua\n")
    assert permissions.is_gui_session(env={}, runner=runner) is True


def test_gui_session_false_under_background_manager():
    def runner(*args, **kwargs):
        return _completed(stdout="Background\n")
    assert permissions.is_gui_session(env={}, runner=runner) is False


def test_gui_session_falls_back_to_true_when_launchctl_missing():
    def runner(*args, **kwargs):
        raise FileNotFoundError("launchctl not on PATH")
    assert permissions.is_gui_session(env={}, runner=runner) is True


# ── prompt_for_full_disk_access ─────────────────────────────────────────────


def test_prompt_no_op_on_non_darwin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(permissions.platform, "system", lambda: "Linux")
    assert permissions.prompt_for_full_disk_access(reason="x") is False


def test_prompt_returns_false_when_non_interactive(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(permissions.platform, "system", lambda: "Darwin")
    assert (
        permissions.prompt_for_full_disk_access(reason="x", interactive=False)
        is False
    )


def test_prompt_returns_false_when_no_gui(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(permissions.platform, "system", lambda: "Darwin")
    assert (
        permissions.prompt_for_full_disk_access(
            reason="x", gui_check=lambda: False,
        )
        is False
    )


def test_prompt_opens_settings_when_user_clicks_open(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(permissions.platform, "system", lambda: "Darwin")
    runs: list[list[str]] = []

    def runner(args, **kwargs):
        runs.append(args)
        if args[0] == "osascript":
            return _completed(stdout="button returned:Open Settings\n")
        if args[0] in ("open", "pbcopy"):
            return _completed()
        raise AssertionError(f"unexpected runner call: {args}")

    result = permissions.prompt_for_full_disk_access(
        reason="x", gui_check=lambda: True, runner=runner, binary="/fake",
    )
    assert result is True
    # All four expected calls fired in order: dialog, clipboard, reveal, settings
    commands = [r[0] for r in runs]
    assert commands == ["osascript", "pbcopy", "open", "open"]
    assert runs[2] == ["open", "-R", "/fake"]
    assert runs[3] == ["open", permissions.SETTINGS_URL]


def test_prompt_skips_open_when_user_dismisses(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(permissions.platform, "system", lambda: "Darwin")
    runs: list[list[str]] = []

    def runner(args, **kwargs):
        runs.append(args)
        # simulate Esc / Skip — non-zero rc, no "Open Settings" in stdout
        return _completed(stdout="button returned:Skip\n", returncode=0)

    result = permissions.prompt_for_full_disk_access(
        reason="x", gui_check=lambda: True, runner=runner, binary="/fake",
    )
    assert result is False
    # one call (osascript), no second call to `open`
    assert len(runs) == 1


def test_prompt_handles_dialog_failure(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(permissions.platform, "system", lambda: "Darwin")

    def runner(args, **kwargs):
        raise OSError("osascript missing")

    result = permissions.prompt_for_full_disk_access(
        reason="x", gui_check=lambda: True, runner=runner,
    )
    assert result is False
