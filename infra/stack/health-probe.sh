#!/bin/bash
# MIKAI stack healer.
# Every 5 minutes (per com.mikai.health-probe.plist):
#   1. Curl the sidecar health endpoint.
#   2. If healthy: reset the fail counter and exit 0.
#   3. If unhealthy: run start-stack.sh, wait 30s, re-check.
#   4. If still unhealthy: increment a fail counter in ~/.mikai/state.
#      After 3 consecutive failed recoveries (~15 min of persistent
#      down), fire the Telegram alert and reset the counter.
#
# The 3-fail threshold prevents Telegram spam during transient
# wake-from-sleep, Docker Desktop restarts, or laptop resume events —
# only alerts when recovery genuinely isn't working.

set -u
ENDPOINT="http://localhost:8100/health"
TIMEOUT=10
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$HOME/.mikai/state"
FAIL_FILE="$STATE_DIR/health-probe.count"
LOG_FILE="$DIR/logs/health-probe.log"
START_STACK="$DIR/start-stack.sh"
FAIL_THRESHOLD=3

mkdir -p "$STATE_DIR" "$DIR/logs"

ENV_FILE="$DIR/.env"
[ -f "$ENV_FILE" ] && source "$ENV_FILE"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"
}

healthy() {
    curl -fsS --max-time "$TIMEOUT" "$ENDPOINT" >/dev/null 2>&1
}

read_count() {
    if [ -f "$FAIL_FILE" ]; then
        cat "$FAIL_FILE" 2>/dev/null || echo 0
    else
        echo 0
    fi
}

send_telegram() {
    [ -z "${TELEGRAM_BOT_TOKEN:-}" ] && return 0
    [ -z "${TELEGRAM_CHAT_ID:-}" ] && return 0
    curl -fsS --max-time 10 \
        -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        -d "text=$1" >/dev/null 2>&1 || true
}

# Fast path — sidecar is healthy.
if healthy; then
    if [ -f "$FAIL_FILE" ]; then
        rm -f "$FAIL_FILE"
        log "recovered — cleared fail counter"
    fi
    exit 0
fi

# Sidecar down. Attempt recovery.
log "sidecar down — attempting recovery via start-stack.sh"

if [ -x "$START_STACK" ]; then
    bash "$START_STACK" >> "$LOG_FILE" 2>&1 &
    RECOVERY_PID=$!
    # Give recovery up to 90s (Docker Desktop can take a while).
    for _ in {1..18}; do
        sleep 5
        if healthy; then
            wait "$RECOVERY_PID" 2>/dev/null || true
            log "recovered on this tick after start-stack.sh"
            rm -f "$FAIL_FILE"
            exit 0
        fi
    done
    kill "$RECOVERY_PID" 2>/dev/null || true
else
    log "ERROR: $START_STACK missing or not executable"
fi

# Still down after recovery attempt. Increment the fail counter.
COUNT=$(read_count)
COUNT=$((COUNT + 1))
echo "$COUNT" > "$FAIL_FILE"
log "recovery failed (attempt ${COUNT}/${FAIL_THRESHOLD})"

if [ "$COUNT" -ge "$FAIL_THRESHOLD" ]; then
    STAMP=$(date '+%Y-%m-%d %H:%M:%S')
    MSG="MIKAI sidecar down at $STAMP — ${COUNT} consecutive recovery attempts failed. Endpoint: $ENDPOINT"
    log "ALERT: $MSG"
    send_telegram "$MSG"
    rm -f "$FAIL_FILE"
fi

exit 1
