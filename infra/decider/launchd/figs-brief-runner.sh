#!/usr/bin/env bash
# FIGS Calendar daily-brief runner — LaunchAgent (once at 06:30 local).
# Writes a single-day MIKAI brief into macOS Calendar.app via osascript.
# Body = top 3 candidates from FIGS' slate (needs registry first, then wiki).
#
# Idempotent: dispatch_calendar.py deletes any existing MIKAI-brief event on
# the target date before creating the new one, so reruns don't duplicate.
set -euo pipefail

ENV_FILE="$HOME/.mikai/launchd.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

# Brief generation itself doesn't call Claude (it composes from the slate
# alone), but mikai_decide.py imports common code that may probe Claude
# health. Same caveat as figs-decide-runner.sh — unset to be safe.
unset ANTHROPIC_API_KEY

mkdir -p "$HOME/.mikai/logs"

REPO="$HOME/Desktop/MIKAI"
cd "$REPO/infra/decider"

exec /usr/bin/env python3 mikai_decide.py --write-brief
