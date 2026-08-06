#!/bin/bash
# Install / update the MIKAI stack orchestration package.
#
# What this does:
#   1. Creates ~/.mikai/state/ (used by health-probe.sh for the fail counter)
#   2. Copies scripts + plists to ~/Library/Application Support/mikai/launchd/
#   3. Rebinds the two LaunchAgents (docker-compose + health-probe)
#   4. Prints instructions for installing the `mikai` CLI (needs write access
#      to a bin dir; done manually by the user, not automated here to avoid
#      surprise sudo prompts)
#
# Idempotent: safe to re-run. It bootouts + bootstraps each agent, so an
# already-registered agent gets refreshed rather than double-registered.

set -euo pipefail

REPO_STACK="$(cd "$(dirname "$0")" && pwd)"
LAUNCHD_DIR="$HOME/Library/Application Support/mikai/launchd"
STATE_DIR="$HOME/.mikai/state"

echo "→ Installing MIKAI stack orchestration"
echo "  source: $REPO_STACK"
echo "  target: $LAUNCHD_DIR"

mkdir -p "$LAUNCHD_DIR" "$STATE_DIR" "$LAUNCHD_DIR/logs"

cp "$REPO_STACK/start-stack.sh"                    "$LAUNCHD_DIR/start-stack.sh"
cp "$REPO_STACK/health-probe.sh"                   "$LAUNCHD_DIR/health-probe.sh"
cp "$REPO_STACK/com.mikai.docker-compose.plist"    "$LAUNCHD_DIR/com.mikai.docker-compose.plist"
cp "$REPO_STACK/com.mikai.health-probe.plist"      "$LAUNCHD_DIR/com.mikai.health-probe.plist"
chmod +x "$LAUNCHD_DIR/start-stack.sh" "$LAUNCHD_DIR/health-probe.sh"

echo "→ Rebinding LaunchAgents"
for label in com.mikai.docker-compose com.mikai.health-probe; do
    launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$LAUNCHD_DIR/$label.plist"
    echo "  $(launchctl list | grep -q "$label" && echo "✓" || echo "✗") $label"
done

# Smoke: is the sidecar currently healthy?
if curl -fsS --max-time 3 http://localhost:8100/health >/dev/null 2>&1; then
    echo "→ Sidecar health check: ✓ (currently up)"
else
    echo "→ Sidecar health check: ✗ (not up right now — health-probe will heal within 5min)"
fi

cat <<EOF

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Install of LaunchAgents complete. Next steps:

1. Install the mikai CLI to your PATH:

     # Homebrew (recommended):
     sudo cp "$REPO_STACK/mikai" /opt/homebrew/bin/mikai
     sudo chmod +x /opt/homebrew/bin/mikai

     # OR (if no Homebrew):
     sudo cp "$REPO_STACK/mikai" /usr/local/bin/mikai
     sudo chmod +x /usr/local/bin/mikai

2. Verify:
     mikai status

3. If you want Telegram alerts on 3+ consecutive recovery failures,
   add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to:
     $LAUNCHD_DIR/.env
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF
