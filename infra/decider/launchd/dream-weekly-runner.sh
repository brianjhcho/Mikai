#!/usr/bin/env bash
# Weekly ontology rebuild runner — LaunchAgent (Sunday 06:00 local).
#
# Whole-corpus map-reduce over ~/.mikai/wiki/wiki.md -> wiki-ontology.md.
# ~31 interactive LLM calls at current corpus size (~15 min wall-clock);
# --max-calls 40 leaves room to grow. Fires two hours before consolidate
# (Sunday 08:00) so consolidation consumes a fresh ontology.
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

# 1) Ontology rebuild — feeds hydrator + latent-threads.
/usr/bin/env python3 -m infra.graphiti.dream_bootstrap ontology \
  --max-calls 40 --ledger-mode dream-weekly

# 2) User-model rebuild — 1 interactive call; reads the fresh
#    ontology + wiki narrative + brain/entities + threads + ledger
#    to compile ~/.mikai/brain/USER_MODEL.md. Downstream hydrator and
#    latent-threads consult it as their ranker (not raw counts).
#    See docs/USER_MODEL_RESEARCH.md.
exec /usr/bin/env python3 -m infra.graphiti.dream_bootstrap user-model \
  --max-calls 5 --ledger-mode dream-weekly-user-model
