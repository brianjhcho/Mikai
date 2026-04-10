<!-- Generated: 2026-03-27 | Updated: 2026-04-02 -->

# MIKAI

## Purpose
Task-state awareness engine ("noonchi") that knows where you are in your thinking across apps and tells you what to do next. Two layers: L3 (knowledge graph — powered by Graphiti + Neo4j) and L4 (thread detection, state classification, next-step inference).

## Architecture Layers
| Layer | Purpose | Backend | LLM Usage |
|-------|---------|---------|-----------|
| L3 — Knowledge Graph | Entity extraction, entity resolution, community detection, temporal edges | **Graphiti + Neo4j** (production) / SQLite (npm package) | Claude Haiku (extraction), Voyage AI (embeddings) |
| L4 — Task-State Awareness | Thread detection, state classification, next-step inference | SQLite (threads, transitions, delivery events) | Claude Haiku (inference only) |

## L3 Backend Transition (2026-04-02)

**Old stack:** Supabase (cloud) + SQLite (local) + custom hybrid search
**Current stack:** Graphiti + Neo4j (production) + SQLite (npm package fallback)

| Component | Old | Current |
|-----------|-----|---------|
| Graph storage | Supabase pgvector / SQLite | Neo4j (via Graphiti) |
| Entity extraction | Custom Track A prompt | Graphiti `add_episode()` (Haiku) |
| Entity resolution | Custom hybrid search + RRF | Graphiti 3-tier (semantic + deterministic + LLM) |
| Edge invalidation | Custom `invalidate-edges.ts` | Graphiti temporal model (`valid_at`/`invalid_at`) |
| Community detection | Deferred | Graphiti label propagation + LLM summaries |
| Embeddings | Voyage AI (cloud) / Nomic (local) | Voyage AI (via Graphiti embedder) |
| BM25 search | FTS5 virtual tables | Neo4j fulltext indices (via Graphiti) |
| Retrieval | Custom `hybridGraphSearch()` | Graphiti `search()` (vec + BM25 + RRF, k=1) |

## Key Files
| File | Description |
|------|-------------|
| `package.json` | @chobus/mikai — npm package manifest |
| `CLAUDE.md` | Development context, architectural constraints, build instructions |
| `.env.local` | API keys (Anthropic, Voyage) — DO NOT COMMIT |
| `tsconfig.json` | TypeScript configuration |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `engine/` | Core processing pipeline (see `engine/AGENTS.md`) |
| `engine/l3/` | L3 Graphiti-inspired search + resolution (SQLite path) (see `engine/l3/AGENTS.md`) |
| `engine/l4/` | L4 task-state awareness pipeline (see `engine/l4/AGENTS.md`) |
| `lib/` | Storage backends and embeddings (see `lib/AGENTS.md`) |
| `surfaces/` | Product surfaces — MCP server v2.0 (see `surfaces/AGENTS.md`) |
| `sources/` | Data connectors — Apple Notes, Perplexity, Claude, Gmail (see `sources/AGENTS.md`) |
| `infra/graphiti/` | Graphiti + Neo4j docker-compose, FastAPI sidecar, migration scripts |
| `scripts/` | Utility scripts for watching/cleanup |
| `docs/` | Architecture docs, decisions, open questions |
| `private/` | Strategy docs — identity, roadmap, competitive analysis |
| `bin/` | CLI entrypoint (`mikai.ts`) |

## For AI Agents

### Working In This Directory
- Use `.env.local` for API keys — never hardcode secrets
- **Two L3 backends exist:**
  - **Graphiti + Neo4j** (Brian's production): `infra/graphiti/docker-compose.yml`. Sidecar at `http://localhost:8100`
  - **SQLite** (npm package): `~/.mikai/mikai.db`. Set `MIKAI_LOCAL=1`
- The MCP server (`surfaces/mcp/server.ts`) currently uses SQLite directly. An `L3Backend` interface abstraction is planned to support both backends.
- Source sync scripts (`sources/`) write to Supabase (legacy) — direct-to-Graphiti import scripts are in `infra/graphiti/scripts/`

### Data Flow — Graphiti Path (Production)
```
Apple Notes / Perplexity / Claude → osascript/file read
  → infra/graphiti/scripts/import_from_dump.py
  → Graphiti sidecar (POST /episode)
  → Graphiti: entity extraction (Haiku) + resolution + community detection
  → Neo4j graph
  → MCP server queries via sidecar API (planned: L3Backend interface)
```

### Data Flow — SQLite Path (npm package)
```
Sources → sync scripts → ingest-direct.ts → Supabase (legacy) / SQLite
  → build-graph (Track A: Haiku, Track B: rule engine)
  → build-segments (Track C: zero-LLM)
  → L4 pipeline (detect → classify → infer)
  → MCP server v2.0 (hybrid search, L4-aware)
```

### Testing Requirements
- `npm test` runs the full eval suite
- `npm run l4` runs the L4 pipeline
- `curl http://localhost:8100/health` checks Graphiti sidecar
- `curl -X POST http://localhost:8100/search -H 'Content-Type: application/json' -d '{"query": "test"}'` tests Graphiti search

### Pipeline Commands
```bash
# Graphiti path (production)
cd infra/graphiti
docker-compose up -d                    # Start Neo4j + sidecar
python scripts/import_from_dump.py      # Import Apple Notes
curl http://localhost:8100/search ...   # Query

# SQLite path (npm package)
npm run sync:all                        # Ingest from all sources
npm run build-graph                     # Track A + B extraction
npm run build-segments                  # Track C segmentation
npm run l4                              # Full L4 pipeline
npm run mcp                             # Start MCP server
```

## Dependencies

### External
- `@anthropic-ai/sdk` — Claude API for extraction and inference
- `@modelcontextprotocol/sdk` — MCP server framework
- `better-sqlite3` + `sqlite-vec` — Local storage with vector search (SQLite path)
- `graphiti-core` — Knowledge graph framework (Graphiti path, Python)
- `neo4j` — Graph database (Graphiti path, Docker)
- Voyage AI — Embeddings (both paths)

<!-- MANUAL: -->
