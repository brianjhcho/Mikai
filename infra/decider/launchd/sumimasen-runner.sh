#!/usr/bin/env bash
# Sumimasen watcher runner — LaunchAgent (every 5 min).
# Scans Calendar.sqlitedb for MIKAI-created blocks firing in the next 15 min
# and sends a rich preparatory ntfy notification with the context bundle.
#
# Detection signature: event description starts with "Dim <N>" (the
# dimension anchor MIKAI's decision/capture URLs always emit).
#
# Dedup persists in ~/.mikai/sumimasen.db keyed on (title, start_time)
# so re-ticks of the same window don't re-fire.

set -euo pipefail

ENV_FILE="$HOME/.mikai/launchd.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

# Sumimasen does not call `claude -p` — pure Python + SQLite + ntfy HTTP,
# so ANTHROPIC_API_KEY does not need to be unset here.

mkdir -p "$HOME/.mikai/logs"

# Until Sumimasen lands on main, canonical code lives in pear-seashore.
# Update REPO to "$HOME/Desktop/MIKAI" after the merge.
REPO="$HOME/.superset/worktrees/MIKAI/pear-seashore"
cd "$REPO/infra/decider"

exec /usr/bin/env python3 sumimasen_watcher.py
