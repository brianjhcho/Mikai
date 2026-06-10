# MCP Operator Guide

> **Updated 2026-06-04.** Tunnel is Tailscale Funnel (not Cloudflare). Mobile + web auth is OAuth 2.1 with PKCE + DCR (not bearer). The whole stack runs under LaunchAgents that live outside `~/Desktop/` to avoid macOS TCC blocking script execution. Pattern B (laptop-as-home-server) is the active deployment target; cloud-hosted Neo4j (O-042) is closed.

## What `/mcp` is

MIKAI's MCP endpoint at `/mcp` exposes the Graphiti L3 backend to three Claude surfaces — Claude Desktop, the Claude.ai web app, and the Claude iOS connector — via Streamable HTTP. The endpoint is mounted inside the same FastAPI sidecar that serves `/health`, `/episode`, and `/search`. Same process, same Neo4j connection, single public URL.

Five L3 tools exposed (per D-040, D-045):

- **`search(query, num_results=10)`** — Hybrid (vector + BM25 + RRF) edge search.
- **`get_history(query, as_of?, num_results=10)`** — Bitemporal point-in-time edge filter. `as_of` must be a **timezone-aware** ISO datetime (e.g. `2026-03-15T00:00:00+00:00`); naive datetimes raise.
- **`add_note(content, source_description=...)`** — Write a new episode; Graphiti extracts entities + edges via the Stage 6 typed pipeline (D-049).
- **`get_stats()`** — Entity / edge / episode / community / orphan counts.
- **`get_source(query, num_results=5)`** — Returns raw source-episode prose (D-045). Complements `search`: edge claims vs. the prose they came from.

No L4 tools (tensions, threads, state classification) — those land later on the L4 branch (D-041).

---

## Public surface

The public URL is **`https://brians-macbook-air.tail8e4198.ts.net`**, served via Tailscale Funnel proxying `127.0.0.1:8100`.

```bash
tailscale serve status      # see current ingress
tailscale funnel status     # confirm Funnel is on
```

Why Tailscale Funnel and not Cloudflare Tunnel (which earlier versions of this guide described): no domain to manage, no DNS step, the `*.ts.net` hostname is free with any Tailscale account, and the daemon is already required for any other tailnet device access. Cloudflare Tunnel works equivalently — it's just an extra moving part we don't need.

---

## Auth — OAuth 2.1 (mobile/web) + bearer (Desktop)

The sidecar runs both auth paths simultaneously, gated by env vars:

| Surface | Auth mode | Why |
|---|---|---|
| Claude Desktop via `mcp-remote` | Bearer (`MIKAI_MCP_TOKEN`, optional on loopback) | `mcp-remote` shim supports bearer; no OAuth flow needed |
| Claude.ai web Custom Connector | OAuth 2.1 | Claude.ai's connector form has no bearer field — only OAuth |
| Claude iOS Custom Connector | OAuth 2.1 | Same — connector UI is OAuth-only |

OAuth 2.1 layer lives at `sidecar/oauth.py` (D-048):

- **Dynamic Client Registration** at `/oauth/register` — Claude auto-registers a `client_id` on first connect; no manual setup.
- **Authorization code + PKCE (S256)** — `/oauth/authorize` issues codes after a password-gated consent page.
- **JWT access tokens (1h) + refresh tokens (30d)** — `/oauth/token` exchanges codes; refresh tokens persist across sidecar restarts.
- **State at `/var/lib/mikai/oauth_state.json`** inside the container, mapped to the `oauth_data` named Docker volume. Survives `docker compose down`; **wiped only by `docker compose down -v`**. The JWT signing secret lives in that file — destroy it and every existing token becomes invalid, forcing every connector to re-authorize.

Activated by `MIKAI_OAUTH_ENABLED=1`. Operator password for the consent page is `MIKAI_OAUTH_PASSWORD`. Both in `infra/graphiti/.env`.

Discovery endpoints (Claude's connector form probes these automatically):

- `GET /.well-known/oauth-authorization-server` — server metadata (issuer, endpoints, supported flows)
- `GET /.well-known/oauth-protected-resource` — points at `/mcp` as the protected resource

---

## Setup

### Claude Desktop (bearer / `mcp-remote`)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mikai": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8100/mcp"]
    }
  }
}
```

Restart Claude Desktop. On loopback the bearer token is optional; for the public URL, add `--header "Authorization: Bearer ${MIKAI_MCP_TOKEN}"` to `args`.

### Claude.ai web (OAuth)

Settings → Tools & Integrations → Add Custom Connector. Fill in:

| Field | Value |
|---|---|
| Name | MIKAI |
| URL | `https://brians-macbook-air.tail8e4198.ts.net/mcp` |
| Auth | OAuth (Claude auto-discovers endpoints from the metadata above) |

Click **Connect** → consent page opens → enter `MIKAI_OAUTH_PASSWORD`. Connector appears in the Tools pane.

### Claude iOS (OAuth)

Settings → Tools & Integrations → Add Custom Connector. Same fields as web; same OAuth flow.

If you ever see Claude attempting a manual OAuth dance via bash ("paste the code back to me"), MIKAI is not registered as a Custom Connector in that surface — re-add it.

---

## Running the stack — Pattern B (laptop-as-home-server)

The stack is `docker compose` in `/Users/briancho/Desktop/MIKAI/infra/graphiti/`. Pattern B means it auto-starts at login and a probe alerts when it goes down. See D-051 for the architectural rationale.

### LaunchAgents

Two LaunchAgents installed at `~/Library/LaunchAgents/`:

| Agent | Trigger | What it does |
|---|---|---|
| `com.mikai.docker-compose` | RunAtLoad (login) | `open -a Docker`, polls `docker info` until ready, then `docker compose up -d` against `Desktop/MIKAI/infra/graphiti/`. Idempotent. |
| `com.mikai.health-probe` | Every 300s + WakeUp | `curl localhost:8100/health` (10s timeout). On failure: logs locally and pushes a Telegram alert if creds present. |

Scripts and plist sources live at **`~/Library/Application Support/mikai/launchd/`** — deliberately outside `~/Desktop/`, because **macOS TCC blocks launchd-spawned bash from `exec`ing scripts under Desktop/Documents/Downloads** (silent `Operation not permitted`, exit code 126). The scripts can still reference Desktop paths (`docker compose` itself reads the compose file fine — Docker Desktop has its own TCC grants); the restriction is on launchd-spawned shell, not the docker daemon.

To install or refresh:

```bash
bash "$HOME/Library/Application Support/mikai/launchd/install.sh"
```

Uses `launchctl bootstrap gui/$UID` (modern API on Sonoma+), not deprecated `load`. Idempotent — bootouts the existing label before bootstrapping the new plist.

### Manual one-time setup

1. **Prevent sleep on AC:** `sudo pmset -c sleep 0 disksleep 0`. Without this, lid-closed = stack-down regardless of LaunchAgents.
2. **Docker Desktop autostart:** Docker Desktop → Settings → General → "Start Docker Desktop when you sign in". The start-stack script handles the cold case, but pre-launching cuts ~10s.
3. **Telegram alerts (optional):** create `~/Library/Application Support/mikai/launchd/.env` with:
   ```
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_CHAT_ID=...
   ```

---

## Verification

End-to-end sweep:

```bash
# Local sidecar
curl -s localhost:8100/health
# → {"status":"ok","backend":"graphiti-deepseek","neo4j":true}

# Local OAuth discovery
curl -s localhost:8100/.well-known/oauth-authorization-server | head -c 200

# Public via Funnel
curl -s -o /dev/null -w "%{http_code} in %{time_total}s\n" \
  https://brians-macbook-air.tail8e4198.ts.net/health

# LaunchAgent state
launchctl print "gui/$(id -u)/com.mikai.docker-compose" | grep -E "last exit|state|runs"
launchctl print "gui/$(id -u)/com.mikai.health-probe"    | grep -E "last exit|state|runs"
```

Healthy: HTTP 200 on both, agents `last exit code = 0`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Public URL returns 502 | Sidecar down, Funnel proxying to nothing | `docker ps`; if missing, `cd Desktop/MIKAI/infra/graphiti && docker compose up -d` |
| `docker info` hangs | Docker Desktop not running | `open -a Docker`; wait ~10s. Enable Docker Desktop autostart for next time. |
| LaunchAgent `last exit code = 126` + stderr "Operation not permitted" | TCC blocking script execution | Confirm scripts are at `~/Library/Application Support/mikai/launchd/`, not under `~/Desktop/`. Re-run `install.sh`. |
| Mobile/web shows OAuth dance via bash ("paste the code") | MIKAI not registered as a Custom Connector on that surface | Re-add via Tools & Integrations using the OAuth flow above |
| Connector reaches server but `/mcp` returns 401 after OAuth | `oauth_data` volume wiped (`docker compose down -v`) → signing secret rotated → existing refresh tokens invalid | Re-authorize from the Custom Connector — Claude redoes DCR + consent |
| `get_history` errors "can't compare offset-naive and offset-aware datetimes" | Naive ISO datetime passed | Use timezone-aware: `2026-03-15T00:00:00+00:00` |
| `mcp-remote` silent hang on Desktop | Port 8100 unreachable | `curl localhost:8100/health`; if it fails, sidecar is down. `docker logs mikai-graphiti`. |
| Funnel public URL stops after reboot | Rare; Tailscale serve config dropped | `tailscale funnel --bg --https=443 http://127.0.0.1:8100` |

---

## Next steps

The L3 surface is operationally settled. The remaining frontiers:

1. **L4 product layer** (D-041) — task-state awareness, thread detection, next-step inference. The actual product, still unbuilt. Rewrite of `feat/l4-testing` onto the new `L3Backend` port (D-050) is the unblocked path.
2. **Auto-ingestion coverage** — the 2026-04-18 eval (`docs/evals/run-20260418-103324.md`) showed Claude.ai's native chat memory retained higher-fidelity detail than MIKAI's graph because Claude captures everything by default. Closing this is the Hermes-style continuous-capture problem. Pattern B is the operational substrate any auto-ingestion daemon would run on.
3. **Stage 6 quality verification** — 200+200 hand-labeling via `eval/label.py`.
4. **Migrate the ingestion daemon's LaunchAgent** out of `infra/graphiti/launchd/` (still TCC-blocked) to the same `~/Library/Application Support/mikai/launchd/` location. Same workaround applies.

See `docs/DECISIONS.md` D-040, D-041, D-043, D-045, D-048, D-051 for the architectural rationale.
