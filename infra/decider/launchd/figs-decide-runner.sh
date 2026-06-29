#!/usr/bin/env bash
# FIGS notification decider runner — LaunchAgent (3x daily).
# Invokes mikai_decide.py from the pear-seashore worktree (where FIGS V1 lives
# until it merges to main). Secrets sourced from ~/.mikai/launchd.env.
#
# Schedule: 07:00, 12:00, 18:00 local (see com.mikai.figs-decide.plist).
# Cooldown of 2h in mikai_decide.py prevents back-to-back sends; --force is
# never set from this runner.
set -euo pipefail

ENV_FILE="$HOME/.mikai/launchd.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

# CRITICAL: FIGS invokes `claude -p` which uses Max-plan first-party OAuth.
# launchd.env carries ANTHROPIC_API_KEY for Graphiti's DeepSeek/Voyage path —
# but having ANTHROPIC_API_KEY set causes `claude` to refuse OAuth and fall
# back to API billing, which fails for `-p` interactive mode. Unset it for
# this process only; the other runners (sync, claude-threads, dream) keep it.
unset ANTHROPIC_API_KEY

mkdir -p "$HOME/.mikai/logs"

# Until FIGS merges to main, the canonical code lives in the pear-seashore
# worktree. Update REPO to "$HOME/Desktop/MIKAI" after the merge.
REPO="$HOME/.superset/worktrees/MIKAI/pear-seashore"
cd "$REPO/infra/decider"

exec /usr/bin/env python3 mikai_decide.py
