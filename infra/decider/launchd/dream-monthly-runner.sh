#!/usr/bin/env bash
# Monthly wiki compaction runner — LaunchAgent (1st of month, 05:00 local).
#
# Zero LLM calls — deterministic text processing. Dedups retry/glitch
# duplicate sections in ~/.mikai/wiki/wiki.md (oldest copy survives),
# backs up wiki.md/index/episode-log as *.pre-compact-<ts>, rebuilds the
# derived files, and writes ~/.mikai/wiki/compact-report-<date>.md.
set -euo pipefail

ENV_FILE="$HOME/.mikai/launchd.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

# No LLM calls here, but keep the invariant anyway: subscription OAuth
# breaks if ANTHROPIC_API_KEY is set in the environment.
unset ANTHROPIC_API_KEY

mkdir -p "$HOME/.mikai/logs"

REPO="$HOME/Desktop/MIKAI"
cd "$REPO"

exec /usr/bin/env python3 -m infra.graphiti.dream_bootstrap compact \
  --ledger-mode dream-monthly
