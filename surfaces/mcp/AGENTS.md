<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-27 | Updated: 2026-04-02 -->

# MCP Server v2.0

## Purpose
MCP server — the primary product surface. Exposes MIKAI's knowledge graph and task-state awareness to Claude Desktop (and future surfaces) via stdio. Local-first: SQLite + sqlite-vec + FTS5. Graphiti-consistent: hybrid search, edge invalidation, temporal queries, episode provenance.

## Key Files
| File | Description |
|------|-------------|
| `server.ts` | MCP server v2.0 — 9 tools, local SQLite backend, hybrid search, L4-aware |

## MCP Tools (9)
| Tool | Layer | Purpose |
|------|-------|---------|
| `search` | L2+L3 | **Unified** hybrid search (vec + BM25 + RRF) over segments AND graph. Filters invalidated edges. Shows fact field + episode provenance. |
| `get_brief` | L1 | L4-aware context brief: thread summary by state, valid tensions, stalled threads |
| `get_tensions` | L3 | Active tensions — valid edges only (invalid_at filtered), ranked by connectivity + recency, shows thread context |
| `get_threads` | L4 | Thread-level view with state filter. Replaces old node-level `get_stalled` |
| `get_thread_detail` | L4 | Deep view: state history, members, related threads |
| `get_next_steps` | L4 | Noonchi surface — prioritized next steps across threads |
| `get_history` | L3 | Temporal query: graph state at a point in time, thought evolution tracking |
| `add_note` | Write | Save insight from conversation (local embeddings, immediately searchable) |
| `mark_resolved` | Write | Resolve node or thread, propagates to containing threads |

## Removed in v2.0
- `search_knowledge` + `search_graph` → merged into `search`
- `get_stalled` → replaced by `get_threads` with state filter
- `get_status` → folded into `get_brief`
- All Supabase code removed — local SQLite only

## Graphiti Consistency
- Hybrid search (vec + BM25 + RRF, k=1)
- BFS filters `invalid_at IS NULL AND expired_at IS NULL`
- Edge `fact` field displayed when available (59% of edges)
- Episode provenance shown on high-priority edges
- Temporal queries via `valid_at`/`invalid_at` ranges in `get_history`

## For AI Agents

### Working In This Directory
- Server is local SQLite only — no Supabase, no dual-backend branching
- Opens `~/.mikai/mikai.db` via config or default path
- Uses `engine/l3/hybrid-search.ts` for retrieval and `engine/l4/store.ts` for thread queries
- **Planned:** `L3Backend` interface abstraction to also query Graphiti sidecar at `http://localhost:8100`
- Start with `npm run mcp` or `npx tsx surfaces/mcp/server.ts`

### Testing
```bash
# Startup test
npx tsx --eval "import './surfaces/mcp/server.ts'; setTimeout(() => process.exit(0), 5000);"

# Should print: MIKAI MCP: connected (v2.0 — local-first, hybrid search, L4-aware)
```

## Dependencies

### Internal
- `lib/store-sqlite.ts` — database, CRUD operations
- `lib/embeddings-local.ts` — Nomic ONNX embeddings (768-dim)
- `engine/l3/hybrid-search.ts` — hybrid retrieval pipeline
- `engine/l4/store.ts` — thread queries
- `engine/l4/schema.ts` — L4 table initialization
- `engine/l4/infer-next-step.ts` — on-demand Haiku inference

### External
- `@modelcontextprotocol/sdk` — MCP protocol
- `zod` — Input validation
- `better-sqlite3` + `sqlite-vec` — Storage

<!-- MANUAL: -->
