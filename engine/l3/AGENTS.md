<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-27 | Updated: 2026-03-27 -->

# l3

## Purpose
L3 Graphiti-inspired upgrades — bitemporal edges, BM25 fulltext, hybrid search with RRF. Phase 1 of 3: adds temporal validity tracking to edges, FTS5 full-text indices, and a hybrid retrieval pipeline (vector + BM25 + RRF + BFS expansion) modeled on Graphiti's architecture.

## Key Files
| File | Description |
|------|-------------|
| `types.ts` | L3 upgrade types — BiTemporalEdge, SearchResult, HybridSearchConfig, defaults |
| `migrate-bitemporal.ts` | Idempotent migration: adds valid_at/invalid_at/expired_at/episodes to edges, creates fts_nodes/fts_segments/fts_edges FTS5 virtual tables |
| `sync-fts.ts` | Rebuilds FTS5 indices from source tables (nodes, segments, edges) |
| `hybrid-search.ts` | Hybrid search: vector (sqlite-vec) + BM25 (FTS5) + RRF fusion + BFS graph expansion |
| `run-l3-upgrade.ts` | CLI orchestrator: migrate → sync FTS, with --migrate-only and --sync-fts-only flags |

## Phase Roadmap
| Phase | What | Status |
|-------|------|--------|
| **1 (current)** | Bitemporal edges + BM25 FTS5 + hybrid search with RRF | **Done** |
| 2 | Entity resolution — deduplicate nodes across sources | Planned |
| 3 | Edge invalidation — mark contradicted/superseded facts as expired | Planned |

## For AI Agents

### Working In This Directory
- All migration functions are **idempotent** — safe to run multiple times
- `migrateToBitemporal` uses `PRAGMA table_info` to check column existence before ALTER TABLE
- FTS5 tables use `content=''` (contentless) — `syncFtsIndices` must be run to populate them
- `hybridGraphSearch` is the primary retrieval entrypoint: takes query string + embedding vector, returns nodes + edges
- BFS expansion uses `expired_at IS NULL` filter by default — set `filterExpired: false` to include expired edges
- RRF k=1 matches Graphiti's default; adjust in `rrf()` call if needed

### Testing Requirements
- Run `npm run l3:upgrade -- --migrate-only` to test migration in isolation
- Run `npm run l3:sync-fts` to rebuild FTS indices after bulk data changes
- Run `npm run l3:upgrade` for a full migration + FTS sync

### Common Patterns
- Functions take `db: Database.Database` as first argument (same pattern as `lib/store-sqlite.ts`)
- Import types from `./types.js`, search functions from `./hybrid-search.js`
- FTS5 `rank` is negative — lower (more negative) = better match; ORDER BY rank ASC

## Dependencies

### Internal
- `lib/store-sqlite.ts` — openDatabase, initDatabase, EdgeRow, NodeRow, SegmentRow types
- `engine/l4/` — L4 thread detection uses hybrid search results as input

### External
- `better-sqlite3` — synchronous SQLite operations
- `sqlite-vec` — vector similarity search (loaded via initDatabase)
