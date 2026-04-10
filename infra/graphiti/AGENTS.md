<!-- Parent: ../../AGENTS.md -->
<!-- Generated: 2026-04-02 | Updated: 2026-04-02 -->

# Graphiti Infrastructure

## Purpose
Production L3 backend for MIKAI. Runs Graphiti (Python) + Neo4j as Docker containers with a FastAPI sidecar that the TypeScript MCP server queries via HTTP.

## Architecture
```
Apple Notes (osascript) → import_from_dump.py → Graphiti sidecar (POST /episode)
                                                      ↓
                                              Graphiti core (Python)
                                              ├── Entity extraction (Haiku)
                                              ├── Entity resolution (3-tier: semantic + deterministic + LLM)
                                              ├── Edge invalidation (temporal: valid_at/invalid_at)
                                              └── Community detection (label propagation + LLM)
                                                      ↓
                                                Neo4j graph database
                                                      ↓
                                              Graphiti sidecar (GET /search, /health)
                                                      ↓
                                              MCP server (TypeScript) → Claude Desktop
```

## Key Files
| File | Description |
|------|-------------|
| `docker-compose.yml` | Neo4j 5.26 + Graphiti sidecar containers |
| `Dockerfile` | Python 3.12 + graphiti-core[anthropic,voyageai] + FastAPI |
| `requirements.txt` | Python dependencies |
| `sidecar/main.py` | FastAPI app: 6 endpoints wrapping graphiti-core |
| `scripts/import_from_dump.py` | Import Apple Notes dump into Graphiti with retry logic |
| `scripts/import_apple_notes.py` | Direct osascript → Graphiti import (alternative) |
| `scripts/read_notes.applescript` | Read Apple Notes to /tmp/mikai_notes_raw.txt |
| `scripts/migrate_sqlite_to_graphiti.py` | Import from SQLite sources table (legacy) |

## Sidecar Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness check |
| `/search` | POST | Hybrid search (vec + BM25 + RRF) — returns facts as edges |
| `/episode` | POST | Add episode — triggers extraction, resolution, communities |
| `/communities` | POST | Get community summaries |

## Configuration
| Env Var | Required | Description |
|---------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | For Haiku entity extraction |
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
- **Rate limits:** Haiku has 50K input tokens/min limit. Use `--delay 8` and the script has retry logic with backoff.
- The sidecar uses `AnthropicClient` for LLM, `VoyageAIEmbedder` for embeddings, `PassthroughReranker` for cross-encoding (no OpenAI dependency)

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
