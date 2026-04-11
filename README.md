# MIKAI

*The AI that knows where you are in your thinking across apps and tells you what to do next.*

## Status: Rebuild in progress

As of April 2026, MIKAI's main branch has been cleaned down to its Graphiti + Neo4j L3 infrastructure. The prior TypeScript-based ingestion pipeline, MCP server, and SQLite backend have been retired and preserved on legacy branches for future recovery. The next phase of work is rebuilding the product surface against Graphiti directly.

Read `docs/CURRENT_STACK.md` for the honest snapshot of the current architecture and `docs/CLEANUP_CANDIDATES.md` for the inventory that drove this cleanup.

## What MIKAI is becoming

A task-state awareness engine with two conceptual layers:

- **L3 — Knowledge graph.** Ingests personal digital content (notes, conversations, messages) and builds a bitemporal entity graph with freeform LLM-extracted relationships. Backed by Graphiti + Neo4j.
- **L4 — Task-state awareness.** Sits on top of L3. Detects threads of activity, classifies their reasoning state (exploring → decided → acting → stalled), and infers next steps. Currently being redesigned against Graphiti's freeform graph model.

The v0.3 (local SQLite) and v0.2 (Supabase) implementations of both layers have been retired from main. They remain accessible via `legacy/sqlite-local` and `legacy/supabase` branches if a local-data option is needed in the future.

## Architecture — the Graphiti L3 stack

| Component | Technology |
|---|---|
| Graph database | Neo4j 5.26 (Docker) |
| Knowledge graph engine | `graphiti-core` (Python, open source, by Zep) |
| LLM (entity extraction + edge resolution) | DeepSeek V3 via OpenAI-compatible API |
| Embeddings | Voyage AI voyage-3 (1024-dim) + Nomic v1.5 (768-dim, dual embedding) |
| Sidecar API | FastAPI (Python, Docker) |

Current graph state: approximately 6,990 entities, 8,056 edges, 1,158 episodes. See `docs/GRAPHITI_INTEGRATION.md` for full technical details including the scaling patch applied to `graphiti-core`.

## Running the Graphiti stack

```
cd infra/graphiti
docker-compose up -d
```

This launches Neo4j and the FastAPI sidecar. The sidecar exposes `/health`, `/search`, `/episode`, `/episode/bulk`, and `/communities` at `http://localhost:8100`.

To import content, use the Python scripts in `infra/graphiti/scripts/`:

```
python scripts/import_sequential.py
python scripts/import_apple_notes.py
python scripts/bulk_import.py
python scripts/run_community_detection.py
```

## What's not yet built on main

- Product surface (MCP server) targeting Graphiti
- Automated ingestion from source apps (Apple Notes, Gmail, iMessage, local files)
- L4 task-state pipeline reading from Graphiti's freeform graph
- Eval tooling for Graphiti graph quality

These will be built fresh against the Graphiti sidecar.
