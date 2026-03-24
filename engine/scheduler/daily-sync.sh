#!/usr/bin/env bash
# engine/scheduler/daily-sync.sh
#
# Sync pipeline: apple-notes → local-files → iMessage → Gmail → build-graph → run-rule-engine → build-segments
# Chains all stages sequentially. If any stage fails, logs the error and continues (non-blocking).
#
# Usage:
#   bash engine/scheduler/daily-sync.sh
#   npm run scheduler:run
#
# Logs to: engine/scheduler/logs/daily-sync-YYYY-MM-DD.log

set -euo pipefail

# ── Config ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/daily-sync-$(date +%Y-%m-%d).log"
LOCK_FILE="/tmp/mikai-sync.lock"

mkdir -p "$LOG_DIR"

# ── Logging ───────────────────────────────────────────────────────────────────

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ── Lockfile ──────────────────────────────────────────────────────────────────

if [ -f "$LOCK_FILE" ]; then
  LOCKED_PID="$(cat "$LOCK_FILE" 2>/dev/null || true)"
  if [ -n "$LOCKED_PID" ] && kill -0 "$LOCKED_PID" 2>/dev/null; then
    log "Another sync is already running (PID $LOCKED_PID). Exiting."
    exit 0
  else
    log "Stale lockfile found (PID $LOCKED_PID not running). Removing."
    rm -f "$LOCK_FILE"
  fi
fi

echo $$ > "$LOCK_FILE"

cleanup() {
  rm -f "$LOCK_FILE"
}
trap cleanup EXIT

# ── Main ──────────────────────────────────────────────────────────────────────

log "=== MIKAI sync started ==="
log "Project root: $PROJECT_ROOT"

cd "$PROJECT_ROOT"

# Stage 1: Apple Notes sync (direct via osascript — no HTML export required)
# Fallback: npm run sync (HTML export path, requires export/ folder to exist)
log "--- Stage 1: Apple Notes sync ---"
if npm run sync:notes >> "$LOG_FILE" 2>&1; then
  log "Apple Notes sync: OK"
else
  log "Apple Notes sync: FAILED (exit $?) — continuing"
fi

# Stage 2: Local files sync (only if Next.js dev server is running)
log "--- Stage 2: Local files sync ---"
if curl -s --max-time 3 http://localhost:3000 > /dev/null 2>&1; then
  if npm run sync:local >> "$LOG_FILE" 2>&1; then
    log "Local files sync: OK"
  else
    log "Local files sync: FAILED (exit $?) — continuing"
  fi
else
  log "Local files sync: SKIPPED (Next.js dev server not running on localhost:3000)"
fi

# Stage 3: iMessage sync
log "--- Stage 3: iMessage sync ---"
if npm run sync:imessage >> "$LOG_FILE" 2>&1; then
  log "iMessage sync: OK"
else
  log "iMessage sync: FAILED (exit $?) — continuing"
fi

# Stage 4: Gmail sync
log "--- Stage 4: Gmail sync ---"
if npm run sync:gmail >> "$LOG_FILE" 2>&1; then
  log "Gmail sync: OK"
else
  log "Gmail sync: FAILED (exit $?) — continuing"
fi

# Stage 5: Claude Code session sync (one-shot scan, no watcher)
log "--- Stage 5: Claude Code session sync ---"
if node scripts/watch-claude-code.js --scan >> "$LOG_FILE" 2>&1; then
  log "Claude Code sync: OK"
else
  log "Claude Code sync: FAILED (exit $?) — continuing"
fi

# Stage 6: build-graph
log "--- Stage 6: build-graph ---"
if npm run build-graph >> "$LOG_FILE" 2>&1; then
  log "build-graph: OK"
else
  log "build-graph: FAILED (exit $?) — continuing"
fi

# Stage 7: run-rule-engine (score all nodes)
log "--- Stage 7: run-rule-engine ---"
if npm run run-rule-engine >> "$LOG_FILE" 2>&1; then
  log "run-rule-engine: OK"
else
  log "run-rule-engine: FAILED (exit $?) — continuing"
fi

# Stage 8: build-segments
log "--- Stage 8: build-segments ---"
if npm run build-segments -- --sources apple-notes,perplexity,manual,claude-thread >> "$LOG_FILE" 2>&1; then
  log "build-segments: OK"
else
  log "build-segments: FAILED (exit $?) — continuing"
fi

log "=== MIKAI sync complete ==="
