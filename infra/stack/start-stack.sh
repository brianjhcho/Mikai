#!/bin/bash
# MIKAI stack starter.
# Opens Docker Desktop, waits for daemon, brings up sidecar (Neo4j + Graphiti).
# Idempotent — safe to re-run; no-ops if the stack is already up.

set -u
REPO="${MIKAI_REPO:-/Users/briancho/Desktop/MIKAI}"
DOCKER="${DOCKER_BIN:-/usr/local/bin/docker}"
ENV_FILE="$REPO/.env.local"

# Open Docker Desktop if the daemon isn't already responsive. Silent on
# failure — the wait loop below handles the "not yet responsive" case.
if ! "$DOCKER" info >/dev/null 2>&1; then
    open -a Docker 2>/dev/null || true
fi

for i in {1..60}; do
    if "$DOCKER" info >/dev/null 2>&1; then
        break
    fi
    sleep 5
done

if ! "$DOCKER" info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon did not become responsive within 5min" >&2
    exit 1
fi

set -e
cd "$REPO/infra/graphiti"

if [ -f "$ENV_FILE" ]; then
    exec "$DOCKER" compose --env-file "$ENV_FILE" up -d
else
    exec "$DOCKER" compose up -d
fi
