#!/usr/bin/env bash
# MIKAI demo preflight — go/no-go check of the full surface chain.
#
# Runs in under 3 seconds. Exits 0 if every dependency the demo needs is up;
# non-zero (and prints a BLOCKED verdict) if anything's red. Run before
# walking on stage or before opening Claude on iPhone in front of an
# audience.
#
# What it checks, in order of how-bad-if-it-fails:
#   1. Tailscale daemon          — needed for iPhone path
#   2. Tailscale Funnel config   — public URL routing to localhost:8100
#   3. Docker daemon             — needed for sidecar + Neo4j
#   4. Neo4j container healthy   — the graph itself
#   5. Sidecar container running — MCP server + FastAPI
#   6. Sidecar /health (direct)  — desktop Claude path
#   7. Funnel /health (public)   — iPhone Claude path
#   8. OAuth discovery (public)  — Claude.ai connector entry point (D-048)
#   9. /mcp auth gate (--full)   — confirms the OAuth token gate is active
#
# Usage:
#   scripts/preflight.sh           # run all checks
#   scripts/preflight.sh --full    # also probe the /mcp auth gate (slower)

set -u

FUNNEL_URL="https://brians-macbook-air.tail8e4198.ts.net"
SIDECAR_URL="http://localhost:8100"
TS_BIN="/Applications/Tailscale.app/Contents/MacOS/Tailscale"

FULL=0
for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
  esac
done

# ── output helpers ───────────────────────────────────────────────────────────

if [[ -t 1 ]]; then
  GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  GREEN=""; RED=""; DIM=""; RESET=""
fi

FAIL_COUNT=0
FAIL_REASONS=()

pass() { printf "  ${GREEN}✓${RESET} %-32s ${DIM}%s${RESET}\n" "$1" "$2"; }
fail() {
  printf "  ${RED}✗${RESET} %-32s ${DIM}%s${RESET}\n" "$1" "$2"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAIL_REASONS+=("$1: $2")
}

# ── checks ───────────────────────────────────────────────────────────────────

echo "MIKAI preflight — $(date '+%Y-%m-%d %H:%M:%S')"
echo

# 1. Tailscale daemon
if [[ -x "$TS_BIN" ]] && "$TS_BIN" status >/dev/null 2>&1; then
  ip=$("$TS_BIN" status 2>/dev/null | awk 'NR==1 {print $1}')
  pass "tailscale daemon" "$ip"
else
  fail "tailscale daemon" "not running — open -a Tailscale"
fi

# 2. Funnel config
if [[ -x "$TS_BIN" ]] && "$TS_BIN" funnel status 2>/dev/null | grep -q "proxy http://127.0.0.1:8100"; then
  pass "tailscale funnel" "proxying /  → :8100"
else
  fail "tailscale funnel" "no route to localhost:8100 — re-add serve rule"
fi

# 3. Docker daemon
if docker info >/dev/null 2>&1; then
  pass "docker daemon" "responsive"
else
  fail "docker daemon" "not running — open -a Docker"
fi

# 4. Neo4j container
neo4j_status=$(docker inspect --format='{{.State.Health.Status}}' mikai-neo4j 2>/dev/null || echo "missing")
if [[ "$neo4j_status" == "healthy" ]]; then
  pass "mikai-neo4j" "healthy"
else
  fail "mikai-neo4j" "$neo4j_status"
fi

# 5. Sidecar container
sidecar_state=$(docker inspect --format='{{.State.Status}}' mikai-graphiti 2>/dev/null || echo "missing")
if [[ "$sidecar_state" == "running" ]]; then
  pass "mikai-graphiti" "running"
else
  fail "mikai-graphiti" "$sidecar_state — docker compose up -d"
fi

# 6. Sidecar /health (direct, desktop path)
if direct=$(curl -sS -m 3 "$SIDECAR_URL/health" 2>/dev/null) && echo "$direct" | grep -q '"status":"ok"'; then
  pass "sidecar /health (direct)" "desktop Claude path"
else
  fail "sidecar /health (direct)" "no response — check docker logs mikai-graphiti"
fi

# 7. Funnel /health (public, iPhone path)
if public=$(curl -sS -m 5 "$FUNNEL_URL/health" 2>/dev/null) && echo "$public" | grep -q '"status":"ok"'; then
  pass "funnel /health (public)" "iPhone Claude path"
else
  fail "funnel /health (public)" "${public:-no response} — check funnel + sidecar"
fi

# 8. OAuth discovery (public) — the entry point Claude.ai's connector probes
if oauth_meta=$(curl -sS -m 5 "$FUNNEL_URL/.well-known/oauth-authorization-server" 2>/dev/null) \
   && echo "$oauth_meta" | grep -q '"issuer"'; then
  pass "oauth discovery (public)" "Claude.ai connector can register"
else
  fail "oauth discovery (public)" "no AS metadata — connector add will fail"
fi

# 9. /mcp auth gate (optional, --full)
# With OAuth on (D-048), an unauthenticated /mcp POST must return 401. That
# 401 is the success condition: it proves the token gate is active.
if [[ $FULL -eq 1 ]]; then
  code=$(curl -sS -o /dev/null -w '%{http_code}' -m 8 \
       -H "Accept: application/json, text/event-stream" \
       -H "Content-Type: application/json" \
       -X POST "$FUNNEL_URL/mcp" \
       -d '{"jsonrpc":"2.0","id":1,"method":"ping"}' 2>/dev/null)
  if [[ "$code" == "401" ]]; then
    pass "mcp auth gate (public)" "/mcp requires an OAuth token — gate active"
  else
    fail "mcp auth gate (public)" "expected 401, got ${code:-no response}"
  fi
fi

# ── verdict ──────────────────────────────────────────────────────────────────

echo
if [[ $FAIL_COUNT -eq 0 ]]; then
  echo "${GREEN}GO${RESET}: all systems green. Demo on."
  exit 0
else
  echo "${RED}BLOCKED${RESET}: $FAIL_COUNT check(s) failed."
  for r in "${FAIL_REASONS[@]}"; do echo "  - $r"; done
  exit 1
fi
