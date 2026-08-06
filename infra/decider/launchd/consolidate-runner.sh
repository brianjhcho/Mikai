#!/usr/bin/env bash
# Weekly BRAIN.md consolidation runner — LaunchAgent (Sunday 08:00 local).
#
# Reads: threads/*, progress.jsonl (last 7 days), decisions/LOG.md tail.
# Writes: ~/.mikai/brain/inbox/proposed-priorities-<date>.md (target=inbox).
# The proposal is folded into BRAIN.md by the next `triage` run — Brian
# stays in the loop weekly. To flip to autonomous overwrite once trust is
# calibrated: change --target=inbox to --target=brain-md below.
#
# One claude -p call per invocation. Bills against Max sub. No API top-ups.
set -euo pipefail

ENV_FILE="$HOME/.mikai/launchd.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

# claude -p uses first-party subscription OAuth; ANTHROPIC_API_KEY set from
# launchd.env (for Graphiti's DeepSeek/Voyage path) would push this call to
# API billing and fail. Unset for this process only.
unset ANTHROPIC_API_KEY

mkdir -p "$HOME/.mikai/logs"

REPO="$HOME/Desktop/MIKAI"
cd "$REPO"

exec /usr/bin/env python3 -m infra.mikai_brain.consolidate --target=inbox
