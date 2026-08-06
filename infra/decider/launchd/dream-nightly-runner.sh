#!/usr/bin/env bash
# Nightly narrative runner — LaunchAgent (03:00 local daily).
#
# Mon-Sat: incremental delta — 1 LLM call over sections newer than the
# last run, appended to ~/.mikai/wiki/wiki-narrative.md as a dated
# '## Δ' entry (30-day retention). Skips silently when fewer than 5 new
# sections exist.
#
# Sunday: fresh full-window rebuild (last 30 days, ~5 calls) — replaces
# the accumulated deltas and resets the incremental watermark, so the
# weekly narrative stays coherent and the file stays bounded.
#
# Bills against Max sub via claude -p. No API top-ups.
set -euo pipefail

ENV_FILE="$HOME/.mikai/launchd.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
fi

# claude -p uses first-party subscription OAuth; ANTHROPIC_API_KEY set from
# launchd.env (for Graphiti's DeepSeek/Voyage path) would push this call to
# API billing and fail. Unset for this process only.
unset ANTHROPIC_API_KEY

mkdir -p "$HOME/.mikai/logs"

REPO="$HOME/Desktop/MIKAI"
cd "$REPO"

if [[ "$(date +%u)" == "7" ]]; then
  # Sunday 03:00 — full-window rebuild (before dream-weekly at 06:00 and
  # consolidate at 08:00, so both read a fresh narrative).
  exec /usr/bin/env python3 -m infra.graphiti.dream_bootstrap narrative \
    --max-calls 8 --ledger-mode dream-nightly
else
  exec /usr/bin/env python3 -m infra.graphiti.dream_bootstrap narrative \
    --incremental --max-calls 2 --ledger-mode dream-nightly
fi
