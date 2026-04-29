"""macOS Full Disk Access (FDA) detection and onboarding prompt.

Reading Apple Notes' NoteStore.sqlite directly is the only way to ingest
1000+ notes in usable time (sub-30s vs 10+ min via AppleScript). The
database lives in a sandboxed group container gated by TCC; only the user
can grant access in System Settings.

This module: detects FDA, shows a native dialog explaining what's needed
and why, opens the right Settings pane on click, falls back to log
instructions when no GUI is available (launchd / SSH / CI).

Usage:
    has_access, reason = check_full_disk_access()
    if not has_access:
        prompt_for_full_disk_access(reason=reason)
        # caller decides: skip Apple Notes, or exit and wait for restart
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Callable

logger = logging.getLogger("mikai-sync.permissions")

NOTES_CONTAINER = (
    Path.home() / "Library" / "Group Containers" / "group.com.apple.notes"
)
NOTES_DB = NOTES_CONTAINER / "NoteStore.sqlite"

SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
)

# Injectable for tests — defaults call into the live OS.
SubprocessRunner = Callable[..., "subprocess.CompletedProcess[str]"]


def _default_runner(*args, **kwargs) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(*args, **kwargs)


def check_full_disk_access(
    *,
    canary: Path = NOTES_DB,
    system: Callable[[], str] = platform.system,
) -> tuple[bool, str | None]:
    """Probe FDA by opening a sandboxed file. Returns (has_access, reason).

    Reason is None on success, else a short description for logging/UI.
    Non-Darwin platforms trivially return True — FDA is a macOS concept.
    """
    if system() != "Darwin":
        return True, None
    if not canary.parent.exists():
        return False, (
            f"Notes container not visible at {canary.parent}. "
            f"Either Apple Notes was never opened on this Mac, or Full Disk "
            f"Access has not been granted to this process."
        )
    if not canary.exists():
        return False, f"NoteStore.sqlite missing at {canary}"
    try:
        with open(canary, "rb") as f:
            f.read(16)
        return True, None
    except PermissionError as e:
        return False, f"Permission denied reading {canary}: {e}"
    except OSError as e:
        return False, f"Could not read {canary}: {e}"


def is_gui_session(
    *,
    runner: SubprocessRunner = _default_runner,
    env: dict[str, str] | None = None,
) -> bool:
    """Heuristic: are we in a context where a dialog can be shown?

    SSH sessions and launchd Background managers cannot show dialogs.
    Aqua manager (the user's GUI session) can. Falls back to True when
    detection itself fails — better to attempt a dialog and have it no-op
    than silently skip onboarding for a user at the keyboard.
    """
    env = env if env is not None else os.environ
    if "SSH_CONNECTION" in env or "SSH_CLIENT" in env:
        return False
    try:
        result = runner(
            ["launchctl", "managername"],
            capture_output=True, text=True, timeout=2,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return True
    return result.stdout.strip() == "Aqua"


def prompt_for_full_disk_access(
    *,
    reason: str | None = None,
    interactive: bool = True,
    binary: str | None = None,
    runner: SubprocessRunner = _default_runner,
    gui_check: Callable[[], bool] = is_gui_session,
) -> bool:
    """Show the user what's needed and how to grant it.

    Returns True iff a GUI dialog was shown AND the user opted to open
    System Settings. False otherwise — including non-Darwin, no GUI,
    user-dismissed, and dialog-failed cases. Always logs the full
    instruction text so non-GUI callers (launchd, CI) have something to
    surface in their logs.
    """
    if platform.system() != "Darwin":
        return False

    # Resolve symlinks: macOS TCC tracks binaries by their real path, not by
    # symlink alias. A `.venv/bin/python` symlink points at the homebrew /
    # framework binary — granting FDA to the symlink is unreliable across
    # macOS versions. Always show and reveal the resolved target.
    binary = str(Path(binary or sys.executable).resolve())
    text = (
        "MIKAI needs Full Disk Access to read your Apple Notes.\n\n"
        "Why: reading 1,000+ notes via AppleScript takes 10+ minutes per "
        "pass. Reading the database directly takes ~20 seconds — but that "
        "database is sandboxed by macOS, and only you can grant access.\n\n"
        f"Reason: {reason or 'access check failed'}\n\n"
        "When you click Open Settings:\n"
        "  • Two windows open — System Settings (Full Disk Access pane) "
        "and a Finder window with the right file already highlighted.\n"
        "  • Drag that highlighted file from Finder into the Full Disk "
        "Access list. The toggle should switch on automatically.\n"
        "  • If drag-and-drop fails, click + in the FDA list and paste "
        "the path (already copied to your clipboard).\n"
        "  • Quit and re-run MIKAI so the new permission takes effect.\n\n"
        f"File to add: {binary}\n\n"
        "Until access is granted, Apple Notes ingestion is skipped. "
        "Other sources (Claude Code) continue normally."
    )
    logger.warning("Full Disk Access not granted:\n%s", text)

    if not interactive or not gui_check():
        return False

    return _show_dialog_and_open_settings(text, binary=binary, runner=runner)


def _show_dialog_and_open_settings(
    text: str, *, binary: str = "", runner: SubprocessRunner,
) -> bool:
    """Render the dialog, then on a confirm click do three helpers:
      - copy the binary path to the clipboard (paste-ready in FDA + dialog)
      - reveal the binary in Finder with it preselected (drag-target)
      - open the System Settings → Full Disk Access pane
    Each helper is best-effort — failures are logged and don't abort.
    """
    # ensure_ascii=False so unicode chars (em dash, arrow) pass through as
    # literal bytes — AppleScript's parser rejects \uXXXX escapes.
    quoted = json.dumps(text, ensure_ascii=False)
    script = (
        f"display dialog {quoted} "
        f'buttons {{"Skip", "Open Settings"}} '
        f'default button "Open Settings" '
        f'with title "MIKAI: Full Disk Access needed" '
        f"with icon caution"
    )
    try:
        result = runner(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=300,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning(f"FDA prompt dialog could not display: {e}")
        return False

    if result.returncode != 0 or "Open Settings" not in result.stdout:
        return False

    if binary:
        _copy_to_clipboard(binary, runner=runner)
        _reveal_in_finder(binary, runner=runner)

    try:
        runner(["open", SETTINGS_URL], timeout=10)
        return True
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning(f"Could not open System Settings pane: {e}")
        return False


def _copy_to_clipboard(text: str, *, runner: SubprocessRunner) -> None:
    """Stuff `text` onto the macOS clipboard via pbcopy — gives the user a
    paste-ready path even if drag-and-drop from Finder fails."""
    try:
        runner(
            ["pbcopy"],
            input=text, text=True, capture_output=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug(f"pbcopy of FDA path failed: {e}")


def _reveal_in_finder(path: str, *, runner: SubprocessRunner) -> None:
    """`open -R` reveals the file in Finder with it preselected — much
    easier than navigating to a hidden venv directory by hand."""
    try:
        runner(["open", "-R", path], timeout=5)
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug(f"Could not reveal {path} in Finder: {e}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    has_access, reason = check_full_disk_access()
    if has_access:
        logger.info("Full Disk Access: GRANTED")
        sys.exit(0)
    logger.warning("Full Disk Access: NOT GRANTED — reason: %s", reason)
    prompt_for_full_disk_access(reason=reason)
    sys.exit(1)
