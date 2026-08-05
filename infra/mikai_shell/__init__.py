"""MIKAI Shell — reactive product surface.

The on-demand agent triggered by hotkey (v1.5) or CLI (v1). Consumes MIKAI's
substrate (life-tier + wiki + graph) to reason about the user's request,
proposes actions via native macOS dialogs, executes on user approval with
rollback support.

Distinct from the proactive layer (FIGS decider, Sumimasen, calendar
planner) which decides *when* to interrupt the user. The shell fires only
when the user initiates.

Consumer-product commitments (per docs/COMPARISON.md):
- No CLI to memorize (hotkey + text input; CLI is for now)
- No API keys visible to the user
- Errors do not leak infrastructure detail
- Trust story: approve per action, silence is default
- Native macOS UI via `osascript` — zero new dependencies
"""

__version__ = "0.1.0"
