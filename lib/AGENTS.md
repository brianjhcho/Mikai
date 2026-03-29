<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-27 | Updated: 2026-03-27 -->

# lib

## Purpose
Storage backends and embedding utilities. The abstraction layer between engine logic and data persistence.

## Key Files
| File | Description |
|------|-------------|
| `store-sqlite.ts` | Local SQLite backend — the ONLY storage for `npx @mikai/mcp` path. Manages sources, nodes, edges, segments with sqlite-vec for vector search |
| `store-supabase.ts` | Cloud Supabase backend — Postgres + pgvector. Used by `npm run` scripts |
| `embeddings.ts` | Voyage AI embeddings (1024-dim, cloud path) |
| `embeddings-local.ts` | Nomic local embeddings (768-dim, via @huggingface/transformers) |
| `ingest-pipeline.ts` | Extraction prompt for reasoning-map generation |

## For AI Agents

### Working In This Directory
- Two parallel storage paths: SQLite (local) and Supabase (cloud). DO NOT mix
- `store-sqlite.ts` is the canonical reference for schema — L4 tables extend it
- Vector dimensions differ: Voyage = 1024-dim, Nomic = 768-dim. The `vec_*` tables use 768 for local
- All store functions take `db: Database.Database` as first arg

### Testing Requirements
- Changes to store-sqlite.ts affect the MCP server and L4 pipeline
- Test with `npm run mcp` to verify MCP still starts
