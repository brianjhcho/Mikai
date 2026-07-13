#!/usr/bin/env bash
# FIGS tap-redirect endpoint runner — LaunchAgent (always-on).
# Serves GET /t/{notif_id} → 302 to the real next_step_url,
# logging TAPPED events into ~/.mikai/notification_log.db.
#
# Phase 1: binds LAN address (works when iPhone is on home wifi).
# Phase 2: swap MIKAI_TAP_HOST/PORT to a Tailscale binding for off-wifi.

set -euo pipefail

ENV_FILE="$HOME/.mikai/launchd.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

mkdir -p "$HOME/.mikai/logs"

# Phase 1: bind all interfaces so LAN + localhost both work.
# The endpoint validates notif_ids strictly (12-char hex), so an attacker
# on your LAN can only guess-hit 302s; the real threat model is a stolen
# ntfy log, not LAN sniffing.
export MIKAI_TAP_HOST="${MIKAI_TAP_HOST:-0.0.0.0}"
# Port 8200 collides with an unrelated brain.py uvicorn service on this
# machine — using 8210 to keep the tap endpoint isolated.
export MIKAI_TAP_PORT="${MIKAI_TAP_PORT:-8210}"
export MIKAI_DB_PATH="${MIKAI_DB_PATH:-$HOME/.mikai/notification_log.db}"

REPO="$HOME/.superset/worktrees/MIKAI/pear-seashore"
cd "$REPO/infra/decider"

exec /usr/bin/env python3 tap_endpoint.py
