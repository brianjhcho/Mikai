#!/usr/bin/env bash
# Cron-fleet heartbeat runner — LaunchAgent (08:15 daily).
#
# Reads ~/.mikai/brain/state/progress.jsonl, asserts every scheduled job
# has left a ledger trace within its expected window, alerts via ntfy on
# gaps. Fires 15 min after the consolidate window (Sunday 08:00) so a
# Sunday consolidate has already logged if it ran.
#
# Zero LLM calls. Needs MIKAI_NTFY_TOPIC from launchd.env for dispatch.
set -euo pipefail

ENV_FILE="$HOME/.mikai/launchd.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

mkdir -p "$HOME/.mikai/logs"

REPO="$HOME/Desktop/MIKAI"
cd "$REPO"

exec /usr/bin/env python3 -m infra.mikai_brain.health
