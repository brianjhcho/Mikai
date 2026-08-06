#!/usr/bin/env bash
# Install (or re-install) the cron-fleet heartbeat LaunchAgent:
#   com.mikai.health-check — 08:15 daily
# Idempotent: unloads any existing job before loading the new one.
set -euo pipefail

DEST_DIR="$HOME/Library/Application Support/mikai/launchd"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$DEST_DIR"

LABEL="com.mikai.health-check"
RUNNER="health-check-runner.sh"
PLIST="$DEST_DIR/${LABEL}.plist"

launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true

cp "$SRC_DIR/$RUNNER"        "$DEST_DIR/$RUNNER"
cp "$SRC_DIR/${LABEL}.plist" "$PLIST"
chmod +x "$DEST_DIR/$RUNNER"

launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "installed: $LABEL"
echo "  plist:  $PLIST"
echo "  runner: $DEST_DIR/$RUNNER"
echo
echo "verify:  launchctl list | grep com.mikai.health-check"
echo "trigger: launchctl kickstart -k gui/\$(id -u)/$LABEL"
echo "logs:    ~/.mikai/logs/health-check.{out,err}.log"
echo "unload:  launchctl bootout gui/\$(id -u) '$PLIST'"
