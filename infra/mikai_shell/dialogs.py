"""Native macOS dialog wrappers via `osascript`.

Zero-dep UI layer for the MIKAI Shell. All dialogs modal, all use macOS
built-in styling. Reused across every shell scenario (organize, find,
draft, etc.).

Each function returns a plain string / bool / list result — no framework
state, no threading, no window management. If a dialog is cancelled, the
function returns None (input) or False (confirm).
"""

from __future__ import annotations

import subprocess


def _osascript(script: str, timeout: float = 3600.0) -> tuple[int, str, str]:
    """Run an AppleScript snippet, return (returncode, stdout, stderr).
    Timeout is deliberately long — modal dialogs wait for the user."""
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _escape(s: str) -> str:
    """Escape a string for embedding inside an AppleScript double-quoted literal."""
    # AppleScript uses \" for literal quote inside "..." strings and \\ for backslash.
    return s.replace("\\", "\\\\").replace('"', '\\"')


def prompt_text(
    message: str = "MIKAI",
    default: str = "",
    ok_label: str = "Run",
    cancel_label: str = "Cancel",
) -> str | None:
    """Show a text-input dialog. Returns the typed string, or None on cancel."""
    script = (
        f'set d to display dialog "{_escape(message)}" '
        f'default answer "{_escape(default)}" '
        f'buttons {{"{_escape(cancel_label)}", "{_escape(ok_label)}"}} '
        f'default button 2 cancel button 1 with title "MIKAI"'
    )
    rc, out, err = _osascript(script)
    if rc != 0:
        # osascript exits nonzero on cancel and on real errors alike; disambiguate.
        if "User canceled" in err or "gave up" in err:
            return None
        # Treat every other failure as cancel too — the dialog is optional.
        return None
    # osascript output format: "button returned:Run, text returned:hello world"
    for part in out.split(", "):
        if part.startswith("text returned:"):
            return part[len("text returned:"):]
    return None


def confirm(
    message: str,
    approve_label: str = "Approve",
    reject_label: str = "Cancel",
) -> bool:
    """Show a two-button confirm. Returns True on approve, False on cancel."""
    script = (
        f'display dialog "{_escape(message)}" '
        f'buttons {{"{_escape(reject_label)}", "{_escape(approve_label)}"}} '
        f'default button 2 cancel button 1 with title "MIKAI"'
    )
    rc, _, _ = _osascript(script)
    return rc == 0


def confirm_three(
    message: str,
    approve_label: str = "Approve all",
    review_label: str = "Review one-by-one",
    reject_label: str = "Cancel",
) -> str:
    """Show a three-button confirm. Returns the chosen label, or 'Cancel'."""
    script = (
        f'set r to display dialog "{_escape(message)}" '
        f'buttons {{"{_escape(reject_label)}", "{_escape(review_label)}", "{_escape(approve_label)}"}} '
        f'default button 3 cancel button 1 with title "MIKAI"'
    )
    rc, out, err = _osascript(script)
    if rc != 0:
        return reject_label
    for part in out.split(", "):
        if part.startswith("button returned:"):
            return part[len("button returned:"):]
    return reject_label


def notify(title: str, body: str) -> None:
    """Fire-and-forget macOS Notification Center banner."""
    script = (
        f'display notification "{_escape(body)}" '
        f'with title "{_escape(title)}"'
    )
    try:
        _osascript(script, timeout=5.0)
    except subprocess.TimeoutExpired:
        pass


def message(text: str, title: str = "MIKAI") -> None:
    """Show an informational alert (single OK button)."""
    script = (
        f'display alert "{_escape(title)}" '
        f'message "{_escape(text)}" '
        f'buttons {{"OK"}} default button 1'
    )
    try:
        _osascript(script)
    except subprocess.TimeoutExpired:
        pass


if __name__ == "__main__":
    # Quick smoke test — run this file directly.
    resp = prompt_text("What do you want MIKAI to do?", "organize my desktop")
    print(f"typed: {resp!r}")
    if resp:
        ok = confirm(f"Ready to interpret: {resp!r}")
        print(f"confirmed: {ok}")
