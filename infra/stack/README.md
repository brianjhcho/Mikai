# MIKAI stack orchestration

Pattern B (per D-051) package for the MIKAI local backend lifecycle:
Docker Desktop → Neo4j → Graphiti sidecar → downstream LaunchAgents (FIGS,
dream, ingestion, claude-threads).

This package makes the stack **self-healing** and adds a **`mikai` CLI**
for on-command control. Previously, the health-probe was a passive alerter
— it noticed sidecar-down and sent Telegram, but the user had to manually
run `docker compose up -d` to bring things back. This package makes the
probe heal, and gives you one-line control.

## Files

| File | Purpose |
|---|---|
| `start-stack.sh` | Opens Docker Desktop, waits for daemon, runs `docker compose up -d` for Neo4j + Graphiti. Idempotent. |
| `health-probe.sh` | Every 5 min: curl sidecar `/health`. If down: run start-stack, wait 90s, re-check. Alert only after 3 consecutive failed recoveries (~15min real down). |
| `com.mikai.docker-compose.plist` | LaunchAgent — runs `start-stack.sh` at user login. |
| `com.mikai.health-probe.plist` | LaunchAgent — runs `health-probe.sh` every 5 min. |
| `mikai` | User-facing CLI: `up`, `down`, `status`, `restart`, `logs`. |
| `install.sh` | Installer — copies scripts + plists to deploy location, rebinds LaunchAgents. Prints instructions for CLI install. |

## Install

```bash
bash infra/stack/install.sh
```

Then install the CLI (needs write to a bin dir; install.sh prints the exact command for your prefix — Homebrew's `/opt/homebrew/bin` or `/usr/local/bin`).

## Layer coverage

Two lines of defense:

1. **Docker Compose `restart: unless-stopped`** on the `neo4j` and `graphiti`
   services (see `infra/graphiti/docker-compose.yml`). Handles container-level
   crashes for free — Docker daemon restarts them without any external agent.
2. **`health-probe.sh` as healer** — handles the case where Docker Desktop
   itself is down (compose can't help if there's no daemon). Runs
   `start-stack.sh`, which opens Docker Desktop and brings compose back up.

Between these two, the only failure mode that survives is Docker Desktop
being down for >15min AND the health-probe itself failing to heal. That's
when Telegram alerts fire.

## Cadence reasoning

- **5-min health-probe interval**: matches the previous cadence. Fast enough
  to catch failures before downstream LaunchAgents (FIGS, dream) tick; slow
  enough to avoid CPU/battery drain.
- **3-fail threshold before Telegram**: prevents alerts during transient
  wake-from-sleep, Docker Desktop restarts, or laptop resume events. Only
  alerts when recovery has genuinely failed 3× in a row (= ~15 min of
  persistent down).
- **90s wait after start-stack.sh**: Docker Desktop cold-start can take
  30-60s; sidecar container start adds another 10-20s. 90s covers the
  slow case.

## `mikai` CLI

```
mikai up              # start Docker Desktop + sidecar (idempotent)
mikai down            # stop sidecar containers (Docker Desktop stays)
mikai status          # colored table of every layer's state
mikai restart         # down + up
mikai logs [service]  # tail logs
                      # services: sidecar (default) | neo4j | figs |
                      #           dream | ingestion | claude-threads |
                      #           health-probe
mikai help
```

Status output covers: Docker Desktop process, Docker daemon, Neo4j
container + HTTP, Graphiti container + `/health`, plus which MIKAI
LaunchAgents are currently loaded (docker-compose, health-probe,
claude-threads, dream, ingestion, figs-decide, figs-brief).

## Pause / debug

```bash
# Pause the healer temporarily (for maintenance)
launchctl bootout "gui/$(id -u)/com.mikai.health-probe"

# Force a health-probe cycle now
launchctl kickstart -k "gui/$(id -u)/com.mikai.health-probe"

# Tail the healer log
tail -f "$HOME/Library/Application Support/mikai/launchd/logs/health-probe.log"

# Manually invoke recovery
bash "$HOME/Library/Application Support/mikai/launchd/start-stack.sh"
```

## Env vars

Optional `~/Library/Application Support/mikai/launchd/.env`:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Sourced by `health-probe.sh` only. If not set, Telegram alerts are silently skipped.
