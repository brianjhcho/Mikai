#!/usr/bin/env bash
# Surface Engine decider runner — LaunchAgent (3x daily).
# (Formerly FIGS; job label kept for launchctl continuity.)
#
# Invokes mikai_decide.py. Secrets sourced from ~/.mikai/launchd.env.
#
# Schedule: 07:00, 12:00, 18:00 local (see com.mikai.figs-decide.plist).
# Cooldown of 2h in mikai_decide.py prevents back-to-back sends; --force is
# never set from this runner.
#
# TOGGLE: Surface Engine is OFF by default. Every tick that fires will exit
# with "Surface Engine disabled" unless MIKAI_SURFACE_ENABLED=1 is exported
# in ~/.mikai/launchd.env. This is intentional — MIKAI stays silent until
# Brian turns Surface on.
#   ON:  echo 'export MIKAI_SURFACE_ENABLED=1' >> ~/.mikai/launchd.env
#   OFF: remove that line (or set to 0).
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

# Surface Engine V1 is on main as of 2026-08-05 (feat/pure-file-brain merge).
# If Brian wants to test a branch locally, point REPO at the worktree.
REPO="$HOME/Desktop/MIKAI"
cd "$REPO/infra/decider"

exec /usr/bin/env python3 mikai_decide.py
