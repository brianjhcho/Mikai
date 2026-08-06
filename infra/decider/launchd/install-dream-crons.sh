#!/usr/bin/env bash
# Install (or re-install) the dream LaunchAgents:
#   com.mikai.dream-weekly  — ontology rebuild, Sunday 06:00 local
#   com.mikai.dream-monthly — wiki compaction, 1st of month 05:00 local
# Idempotent: unloads any existing job before loading the new one.
set -euo pipefail

DEST_DIR="$HOME/Library/Application Support/mikai/launchd"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$DEST_DIR"

install_job() {
  local label="$1" runner="$2"
  local plist="$DEST_DIR/${label}.plist"

  # Unload if already installed. Ignore errors — first-install case.
  launchctl bootout "gui/$(id -u)" "$plist" 2>/dev/null || true

  # Copy runner + plist into the deployed location. Pattern B doctrine:
  # ~/Library/Application Support/mikai/launchd/ is the source of truth
  # for launchd; repo copies are canonical + versioned but launchd runs
  # these copies. Re-run install after any repo-side edit.
  cp "$SRC_DIR/$runner"        "$DEST_DIR/$runner"
  cp "$SRC_DIR/${label}.plist" "$plist"
  chmod +x "$DEST_DIR/$runner"

  # Load. bootstrap is preferred over `load` on macOS 12+.
  launchctl bootstrap "gui/$(id -u)" "$plist"

  echo "installed: $label"
  echo "  plist:  $plist"
  echo "  runner: $DEST_DIR/$runner"
}

install_job "com.mikai.dream-weekly"  "dream-weekly-runner.sh"
install_job "com.mikai.dream-monthly" "dream-monthly-runner.sh"

echo
echo "verify:  launchctl list | grep com.mikai.dream"
echo "trigger: launchctl kickstart -k gui/\$(id -u)/com.mikai.dream-weekly"
echo "         launchctl kickstart -k gui/\$(id -u)/com.mikai.dream-monthly"
echo "logs:    ~/.mikai/logs/dream-{weekly,monthly}.{out,err}.log"
echo "unload:  launchctl bootout gui/\$(id -u) '$DEST_DIR/com.mikai.dream-weekly.plist'"
echo "         launchctl bootout gui/\$(id -u) '$DEST_DIR/com.mikai.dream-monthly.plist'"
