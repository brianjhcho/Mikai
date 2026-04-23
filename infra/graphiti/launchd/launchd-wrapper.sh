#!/usr/bin/env bash
set -euo pipefail

# Source user env if present. The file should contain KEY=VALUE lines only.
ENV_FILE="$HOME/.mikai/launchd.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

mkdir -p "$HOME/.mikai/logs"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Phase A creates sync.py; this path references it by future location.
exec "$REPO/infra/graphiti/.venv/bin/python" "$REPO/infra/graphiti/sync.py"
