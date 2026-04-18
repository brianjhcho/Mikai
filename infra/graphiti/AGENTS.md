<!-- Parent: ../../AGENTS.md -->
<!-- Generated: 2026-04-02 | Updated: 2026-04-17 -->

# Graphiti Infrastructure

## Purpose
Production L3 backend for MIKAI. Runs Graphiti (Python) + Neo4j as Docker containers with a FastAPI sidecar that exposes both REST endpoints and an MCP Streamable HTTP endpoint at `/mcp` for Claude Desktop, mobile, and browser (D-043).

## Architecture
```
Apple Notes (osascript) → import_from_dump.py → Graphiti sidecar (POST /episode)
                                                      ↓
                                              Graphiti core (Python)
                                              ├── Entity extraction (DeepSeek V3)
                                              ├── Entity resolution (3-tier: semantic + deterministic + LLM)
                                              ├── Edge invalidation (temporal: valid_at/invalid_at)
                                              └── Community detection (label propagation + LLM)
                                                      ↓
                                                Neo4j graph database
                                                      ↓
                                     Graphiti sidecar (single process)
                                     ├── REST: /search, /episode, /nodes/*, /history, /stats
                                     └── MCP:  /mcp (Streamable HTTP — FastMCP)
                                                      ↓
                                  ┌───────────────────┼────────────────────┐
                                  ↓                   ↓                    ↓
                         Claude Desktop       Claude mobile        Claude.ai browser
                        (via mcp-remote)      (Custom Connector)   (Custom Connector)
```

## Key Files
| File | Description |
|------|-------------|
| `docker-compose.yml` | Neo4j 5.26 + Graphiti sidecar containers |
| `Dockerfile` | Python 3.12 + graphiti-core[anthropic,voyageai] + FastAPI |
| `requirements.txt` | Python dependencies |
| `sidecar/main.py` | FastAPI app: REST endpoints + `/mcp` mount wrapping graphiti-core |
| `sidecar/mcp_tools.py` | FastMCP tool handlers (L3): search, get_history, add_note, get_stats |
| `scripts/import_from_dump.py` | Import Apple Notes dump into Graphiti with retry logic |
| `scripts/import_apple_notes.py` | Direct osascript → Graphiti import (alternative) |
| `scripts/read_notes.applescript` | Read Apple Notes to /tmp/mikai_notes_raw.txt |
| `scripts/migrate_sqlite_to_graphiti.py` | Import from SQLite sources table (legacy) |

## Sidecar Endpoints

**REST (for scripts and the ingestion pipeline):**
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness check |
| `/search` | POST | Hybrid search (vec + BM25 + RRF) — returns facts as edges |
| `/episode` | POST | Add episode — triggers extraction, resolution, communities |
| `/episode/bulk` | POST | Bulk import via `add_episode_bulk` |
| `/communities` | POST | Get community summaries |
| `/stats` | GET | Graph quality snapshot |
| `/nodes/search` | POST | Node-level hybrid search |
| `/nodes/{uuid}` | GET | Fetch entity node by UUID |
| `/nodes/{uuid}/expand` | POST | BFS 1-hop expansion |
| `/edges/between` | POST | Edges between a given set of nodes |
| `/history` | POST | Bitemporal point-in-time search |

**MCP (for Claude Desktop / mobile / browser):**
| Endpoint | Purpose |
|----------|---------|
| `/mcp` | FastMCP Streamable HTTP. Tools: search, get_history, add_note, get_stats |

## Claude client configuration

**Claude Desktop** (via the `mcp-remote` stdio shim since Desktop config only speaks stdio):
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

**Claude mobile / Claude.ai browser** (Custom Connector, Streamable HTTP):
- URL: `https://<your-tunnel>/mcp` (Cloudflare Tunnel or similar for public reach)
- Auth: bearer token (solo-user phase per D-034); OAuth when a second user arrives

## Configuration
| Env Var | Required | Description |
|---------|----------|-------------|
| `DEEPSEEK_API_KEY` | Yes | For DeepSeek V3 entity extraction |
| `VOYAGE_API_KEY` | Yes | For Voyage AI embeddings |
| `NEO4J_URI` | Auto | `bolt://neo4j:7687` (set by docker-compose) |
| `NEO4J_USER` | Auto | `neo4j` |
| `NEO4J_PASSWORD` | Auto | `mikai-local-dev` |

## For AI Agents

### Working In This Directory
- **Start stack:** `docker-compose up -d` (requires Docker Desktop running)
- **Check health:** `curl http://localhost:8100/health`
- **Neo4j browser:** `http://localhost:7474` (neo4j / mikai-local-dev)
- **Import notes:** First run `read_notes.applescript` to dump to /tmp, then `import_from_dump.py`
- **Rate limits:** DeepSeek V3 is the current LLM (no rate-limit issues at this scale). Voyage AI embeddings have their own per-minute budget — the import script has retry/backoff.
- The sidecar uses `DeepSeekClient` (custom adapter over `OpenAIGenericClient`) for LLM, `VoyageAIEmbedder` for embeddings, `PassthroughReranker` for cross-encoding (no OpenAI dependency).

### Import Workflow
```bash
# 1. Read Apple Notes to dump file
osascript scripts/read_notes.applescript 2>/tmp/mikai_notes_raw.txt

# 2. Import (activate venv first)
source .venv/bin/activate
python scripts/import_from_dump.py --delay 8

# 3. Monitor
docker exec mikai-neo4j cypher-shell -u neo4j -p mikai-local-dev \
  "MATCH (n) RETURN labels(n)[0] AS type, COUNT(n) AS count ORDER BY count DESC;"
```

## Dependencies

### Internal
- `../../.env.local` — API keys passed via docker-compose environment

### External
- `graphiti-core[anthropic,voyageai]` — Knowledge graph framework
- `neo4j:5.26-community` — Graph database
- `fastapi` + `uvicorn` — HTTP sidecar

<!-- MANUAL: -->
