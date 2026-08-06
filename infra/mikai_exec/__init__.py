"""MIKAI executor layer — act on a surfaced thread, end-to-end.

When the cockpit or Surface Engine (figs) surfaces a thread, this module
closes the loop: it proposes ONE concrete action for the thread, shows it
to Brian in a native approval dialog, and only then executes it through a
deliberately scoped channel:

  - MCP-backed types (email / calendar / drive / note) run through
    `claude -p --allowedTools <specific server>` — Claude with exactly one
    MCP server whitelisted, nothing else. This intentionally bypasses the
    blanket `--tools ""` lockdown in infra.mikai_llm: that lockdown is for
    pure-text synthesis calls; execution calls are scoped-not-none.
  - `message` has no MCP today — MIKAI composes the text and copies it to
    the clipboard (pbcopy) for Brian to paste anywhere.
  - `shell` / `code` run Claude with only Bash/Read(/Edit) allowed.
  - `browse` is skipped entirely until a Playwright MCP is installed.

Doctrine: approval before any mutation (the dialog is non-negotiable),
and an action that leaves no trace never happened (ledger.run + thread
log line on every executed action; delivery event on every dismissal).
"""

from .core import ACTION_POLICIES, execute

__all__ = ["ACTION_POLICIES", "execute"]
