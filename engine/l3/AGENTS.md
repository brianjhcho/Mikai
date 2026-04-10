<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-27 | Updated: 2026-04-02 -->

# L3 — SQLite Path (npm package fallback)

## Purpose
Graphiti-inspired L3 implementation on SQLite — bitemporal edges, BM25 fulltext, hybrid search with RRF, entity resolution, edge invalidation. This is the **SQLite fallback path** for the npm package. Brian's production instance uses Graphiti + Neo4j directly (`infra/graphiti/`).

## Role in the Architecture
```
Production (Brian):  Sources → Graphiti + Neo4j (infra/graphiti/)
npm package (users): Sources → This code (engine/l3/) + SQLite
```

Both paths implement the same Graphiti patterns. This code is a TypeScript reimplementation of Graphiti's core features for local-first deployment without Neo4j.

## Key Files
| File | Description |
|------|-------------|
| `types.ts` | BiTemporalEdge, SearchResult, HybridSearchConfig types |
| `hybrid-search.ts` | Hybrid retrieval: vec (sqlite-vec) + BM25 (FTS5) + RRF (k=1) + BFS expansion. Filters `invalid_at` and `expired_at` in BFS. |
| `entity-resolution.ts` | Cross-source entity deduplication via hybrid search + RRF scoring. Creates edges between matching entities across apps. 1,072 edges on current corpus. |
| `invalidate-edges.ts` | Edge invalidation: contradiction + supersession patterns. Sets `invalid_at` without deleting. 48 edges invalidated. |
| `migrate-bitemporal.ts` | Idempotent migration: adds valid_at/invalid_at/expired_at/episodes/fact to edges, creates FTS5 tables |
| `sync-fts.ts` | Rebuilds FTS5 indices (fts_nodes, fts_segments, fts_edges) |
| `run-l3-upgrade.ts` | CLI orchestrator: migrate → FTS sync → entity resolution → invalidation |
| `run-entity-resolution.ts` | Standalone entity resolution CLI |

## Graphiti Feature Mapping
| Graphiti Feature | This Implementation | Gap |
|---|---|---|
| RRF (k=1) | `rrf()` in hybrid-search.ts | Exact match |
| Bitemporal edges | valid_at, invalid_at, expired_at, fact, episodes columns | Correct schema |
| Hybrid search | vec + BM25 + RRF + BFS | Correct pattern |
| Entity resolution | 2-tier (semantic + deterministic) | Missing LLM tier 3 |
| Edge invalidation | Contradiction + supersession heuristics | Missing LLM contradiction detection |
| Community detection | Not implemented | Deferred — Graphiti production path has this |
| Entity summaries | Static (set at extraction) | Missing — Graphiti evolves summaries per episode |
| Edge-centric search | Returns nodes, edges secondary | Graphiti returns edges as primary unit |

## For AI Agents

### Working In This Directory
- This code is the **SQLite fallback**, not the primary L3 path
- All functions take `db: Database.Database` as first argument
- Migrations are idempotent — safe to run multiple times
- BFS expansion filters `expired_at IS NULL AND invalid_at IS NULL` (fixed 2026-04-02)
- RRF k=1 matches Graphiti's default
- FTS5 tables use `content=''` (contentless) — run `syncFtsIndices` after bulk data changes

### Commands
```bash
npm run l3:upgrade              # Full: migrate + FTS
npm run l3:upgrade -- --resolve # + entity resolution
npm run l3:resolve              # Entity resolution only
npm run l3:sync-fts             # Rebuild FTS indices
```

## Dependencies

### Internal
- `lib/store-sqlite.ts` — openDatabase, EdgeRow, NodeRow types
- `engine/l4/` — L4 thread detection uses hybrid search as input

### External
- `better-sqlite3` — SQLite operations
- `sqlite-vec` — Vector similarity search

<!-- MANUAL: This directory will be maintained for the npm package path even after Graphiti becomes the primary L3 backend. Do not remove. -->
