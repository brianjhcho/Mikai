#!/usr/bin/env bash
# Install (or re-install) the weekly consolidate LaunchAgent.
# Idempotent: unloads existing job before loading the new one.
set -euo pipefail

DEST_DIR="$HOME/Library/Application Support/mikai/launchd"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.mikai.consolidate"
PLIST="$DEST_DIR/${LABEL}.plist"
RUNNER="$DEST_DIR/consolidate-runner.sh"

mkdir -p "$DEST_DIR"

# Unload if already installed. Ignore errors — first-install case.
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true

# Copy runner + plist into the deployed location. Pattern B doctrine:
# ~/Library/Application Support/mikai/launchd/ is the source of truth
# for launchd; repo copies are canonical + versioned but launchd runs
# these copies. Re-run install after any repo-side edit.
cp "$SRC_DIR/consolidate-runner.sh" "$RUNNER"
cp "$SRC_DIR/${LABEL}.plist"        "$PLIST"
chmod +x "$RUNNER"

# Load. bootstrap is preferred over `load` on macOS 12+.
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "installed: $LABEL"
echo "  plist:  $PLIST"
echo "  runner: $RUNNER"
echo
echo "verify:  launchctl list | grep $LABEL"
echo "trigger: launchctl kickstart -k gui/\$(id -u)/$LABEL"
echo "logs:    ~/.mikai/logs/consolidate.{out,err}.log"
echo "unload:  launchctl bootout gui/\$(id -u) '$PLIST'"
