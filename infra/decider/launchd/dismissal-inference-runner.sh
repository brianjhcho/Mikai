#!/usr/bin/env bash
# Hourly dismissal inference — marks SENT-with-no-TAPPED-in-24h as
# DISMISSED_INFERRED. Idempotent.

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
cd "$REPO/infra/decider"

exec /usr/bin/env python3 dismissal_inference.py
