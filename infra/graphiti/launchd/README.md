# MIKAI launchd ingestion supervisor

macOS-native persistent auto-ingestion supervisor for the MIKAI sync daemon, addressing O-040.

## Prerequisites

- `.venv` built in `infra/graphiti/` (run `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` from that directory)
- Phase A's `sync.py` exists at `infra/graphiti/sync.py`
- `~/.mikai/launchd.env` exists and contains the required secrets (e.g. `NEO4J_URI`, `OPENAI_API_KEY`, `VOYAGE_API_KEY`, `DEEPSEEK_API_KEY`)

## Install

Run these four commands, substituting your actual repo path for `REPO`:

```bash
REPO="$HOME/path/to/MIKAI"

# 1. Render the template — replace placeholders with real paths.
sed -e "s|<REPO>|$REPO|g" -e "s|<HOME>|$HOME|g" \
  "$REPO/infra/graphiti/launchd/com.mikai.ingestion.plist.template" \
  > /tmp/com.mikai.ingestion.plist

# 2. Copy rendered plist to LaunchAgents.
cp /tmp/com.mikai.ingestion.plist ~/Library/LaunchAgents/com.mikai.ingestion.plist

# 3. Load the agent.
launchctl load ~/Library/LaunchAgents/com.mikai.ingestion.plist

# 4. Verify it started.
launchctl list | grep com.mikai.ingestion
```

## Verify

```bash
# Check the agent is listed (PID column non-zero means it's running).
launchctl list | grep com.mikai.ingestion

# Tail the error log for startup output and exceptions.
tail -f ~/.mikai/logs/sync.err.log
```

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.mikai.ingestion.plist && rm ~/Library/LaunchAgents/com.mikai.ingestion.plist
```

## Why launchd, not docker-compose?

The MIKAI sync daemon reads personal data from `~/Library/...` paths (Apple Notes, Calendar, Mail) that Docker cannot reach on macOS without privileged mode — Apple's container sandbox blocks access to user-owned library directories. launchd runs in the user session, inherits full access to `~/Library`, is the Apple-native service manager, survives reboots automatically, and restarts the process on crash via `KeepAlive`. No Docker daemon overhead, no port-forwarding, no volume mounts.

## Related deferred work

A validated Gmail-specific config for `mcp_ingest.py` is deferred to the lead branch — see `docs/OPEN.md` O-041 and `infra/graphiti/mcp_sources.example.yaml` for the current (unvalidated) template.
