# MCP Operator Guide

## What /mcp is

MIKAI's MCP endpoint at `/mcp` exposes your Graphiti knowledge graph to Claude Desktop, mobile (iOS/Android), and the Claude.ai browser web app via Streamable HTTP. The endpoint is mounted inside the Graphiti sidecar FastAPI server — same process, same Neo4j connection, single public URL.

The MCP server implements four L3 (graph primitives) tools:

- **`search(query, num_results=10)`** — Hybrid search (semantic + BM25 + reciprocal rank fusion) across the graph. Returns edges (relationships) and adjacent nodes ranked by relevance. Start here for queries like "what am I contradicting?" or "what depends on X?"
- **`get_history(query, as_of?, num_results=10)`** — Bitemporal point-in-time search. Returns current facts and superseded (invalidated) facts separately, so you can see how beliefs have evolved. Pass an ISO datetime in `as_of` (e.g. `2026-03-15T00:00:00`) to see the graph as it looked on that date.
- **`add_note(content, source_description="claude-conversation")`** — Write a new insight into the knowledge graph as a Graphiti episode. Graphiti extracts entities and relationships automatically from the content.
- **`get_stats()`** — Graph quality snapshot: total entities, relationships, episodes, communities, and orphan count (entities with no relationships).

Reference the decision log (docs/DECISIONS.md D-040, D-041, D-043) for the architectural rationale. The sidecar exposes REST endpoints for ingestion and admin; `/mcp` is the only surface exposed to Claude clients.

---

## Claude Desktop setup

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

Then restart Claude Desktop. You should see "mikai" in the Tools pane.

**Why the `mcp-remote` indirection?** Claude Desktop's config syntax only accepts stdio servers. The `mcp-remote` package is a community shim that bridges the gap: it translates Claude's stdio MCP requests into HTTP calls to your local Streamable HTTP endpoint, then streams responses back as stdio. This lets Desktop reach the same `/mcp` endpoint that mobile and browser use, without MIKAI having to implement two separate transport layers (stdio + HTTP). The shim is well-maintained and adds negligible latency on localhost.

---

## Claude mobile (iOS/Android) setup

Open Claude on your phone or tablet. Tap **Settings > Tools & Integrations > Add Custom Connector**.

Fill in:

| Field | Value |
|-------|-------|
| **Name** | MIKAI |
| **Description** | Knowledge graph memory |
| **URL** | `https://<your-tunnel-domain>/mcp` (see Cloudflare Tunnel section below) |
| **Authentication** | Bearer Token |
| **Token** | (your MIKAI_MCP_TOKEN value from step 6) |

Tap **Save**. The connector will appear in the Tools pane once it's live. Test by asking Claude to search for something in your knowledge graph.

---

## Claude.ai browser setup

In the Claude.ai web app, click your **profile > Settings > Tools & Integrations > Add Custom Connector**.

Same fields as mobile:

| Field | Value |
|-------|-------|
| **Name** | MIKAI |
| **Description** | Knowledge graph memory |
| **URL** | `https://<your-tunnel-domain>/mcp` |
| **Authentication** | Bearer Token |
| **Token** | (your MIKAI_MCP_TOKEN value) |

Save and refresh the page. The connector will be available in the Tools menu.

---

## Cloudflare Tunnel quickstart

To expose your local `/mcp` endpoint to mobile and browser, use Cloudflare Tunnel (no open ports, no firewall config, free tier covers personal use).

**1. Install cloudflared:**

```bash
brew install cloudflare/cloudflare/cloudflared
```

**2. Authenticate:**

```bash
cloudflared tunnel login
```

Your browser opens; approve the domain authorization.

**3. Create a tunnel:**

```bash
cloudflared tunnel create mikai
```

Prints your tunnel UUID and credentials location.

**4. Create `infra/graphiti/config.yml`:**

```yaml
tunnel: <your-tunnel-uuid>
credentials-file: ~/.cloudflared/<tunnel-uuid>.json

ingress:
  - hostname: mikai.<your-cloudflare-domain>
    service: http://localhost:8100
  - service: http_status:404
```

Replace `<your-tunnel-uuid>` with the output from step 3. Replace `<your-cloudflare-domain>` with your Cloudflare-managed domain (e.g., `example.com` if you added that to Cloudflare DNS).

**5. Create DNS record:**

In your Cloudflare dashboard, add a CNAME: `mikai` → `<tunnel-uuid>.cfargotunnel.com`.

**6. Run the tunnel:**

```bash
cd infra/graphiti
cloudflared tunnel run mikai
```

Tunnel is now live. Test: `curl https://mikai.<your-domain>/health` should return `{"status":"ok"}`.

**Important:** This exposes the entire sidecar (`/search`, `/episode`, `/stats`, etc.) to the internet. Currently no endpoint-level ACL exists. Future work: add a middleware that whitelists only `/mcp` for public requests and requires authentication for admin endpoints. For now, rely on bearer-token authentication (step 6) as your security boundary.

---

## Bearer-token auth setup

Set the token in the sidecar environment. Edit `infra/graphiti/docker-compose.yml`:

```yaml
services:
  mikai-graphiti:
    environment:
      MIKAI_MCP_TOKEN: "your-secret-token-here"
      # ... other vars
```

Or set it at runtime:

```bash
export MIKAI_MCP_TOKEN="your-secret-token-here"
docker-compose up -d
```

**If unset:** `/mcp` is unauthenticated (safe for `localhost:8100` when Desktop hits it via `mcp-remote`; **NOT safe** for a public tunnel).

**For mobile/browser connectors:** Paste the token value in the Custom Connector's "Token" field. The client will automatically send it as:

```
Authorization: Bearer your-secret-token-here
```

The sidecar validates the token before handling any MCP request.

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| **401 Unauthorized** | Token mismatch or missing | Check `MIKAI_MCP_TOKEN` env var matches the token in your Claude client config. Restart sidecar after changing env. |
| **404 on /mcp** | Sidecar not running or mount failed | `curl http://localhost:8100/health` — should return `{"status":"ok"}`. If 404, check `docker logs mikai-graphiti` for startup errors. |
| **500 Internal Error** | Graphiti or Neo4j crash | Check `docker logs mikai-graphiti` and `docker logs mikai-neo4j` for stack traces. Common: Neo4j OOM (increase Docker memory) or Graphiti patch not applied. |
| **mcp-remote silent hang** | Port 8100 unreachable | Verify sidecar is running: `docker ps \| grep mikai-graphiti`. If not running, check `docker-compose up -d` output. If running but unreachable, check Docker network: `docker network ls` and `docker inspect <network> \| grep -A 10 mikai-graphiti`. |
| **Custom Connector setup fails on mobile** | Tunnel URL must be HTTPS | Check that your tunnel URL starts with `https://` (not `http://`). Cloudflare Tunnel always uses HTTPS. |
| **Sidecar starts but /mcp returns 404** | FastMCP mount may have failed | Check `docker logs mikai-graphiti` for lines like "Mounting FastMCP" or "ASGI app setup". If missing, the mcp_tools.py or main.py changes may not be in the image. Rebuild: `docker-compose down && docker-compose up -d --build`. |

---

## Next steps

Once all three surfaces are working, you have validated the transport and auth layer. The L4 (product semantics) layer — tension detection, thread detection, state classification — is designed separately on the `feat/l4-engine` branch. For now, L3 primitives (`search`, `add_note`, etc.) are the shipped interface.

Read docs/DECISIONS.md D-034, D-041, and D-043 for the rationale behind surface coverage, L3/L4 separation, and the Streamable HTTP transport choice.
