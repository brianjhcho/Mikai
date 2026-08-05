#!/usr/bin/env bash
# MIKAI calendar planner (D-055) — LaunchAgent runner.
# Once per fire: fetch today's editable iCloud blocks, gather candidate
# pool (git + OPEN.md + inflight.md + needs registry), ask DeepSeek to
# pick 2-3 items, insert PROPOSED row, dispatch ntfy with Approve/Reject.
#
# The actual PATCH to iCloud only happens when the user taps Approve —
# handled by the tap-endpoint's /approve/{proposal_id} route.

set -euo pipefail

ENV_FILE="$HOME/.mikai/launchd.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

# Uses DeepSeek + ntfy over the network — needs the DeepSeek key from
# ~/.mikai/launchd.env, plus MIKAI_NTFY_TOPIC and iCloud creds.
mkdir -p "$HOME/.mikai/logs"

REPO="$HOME/Desktop/MIKAI"
cd "$REPO/infra/decider"

exec /usr/bin/env python3 calendar_planner.py
