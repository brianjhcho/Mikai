<!-- Generated: 2026-04-11 -->

# MIKAI

## Purpose
MIKAI is a task-state awareness engine ("noonchi") — the AI that knows where you are in your thinking across apps and tells you what to do next.

## Current architectural state

MIKAI is mid-migration from a dual SQLite/Supabase backend to Graphiti + Neo4j as the sole L3 knowledge graph. Main has been cleaned to reflect this direction:

- **L3 (knowledge graph) → Graphiti + Neo4j** — `infra/graphiti/`
- **L4 (task-state awareness)** — to be rebuilt against Graphiti. Prior SQLite-backed L4 preserved on `feat/l4-testing`.
- **Ingestion** — via Python scripts in `infra/graphiti/scripts/`. The TypeScript source connectors have been retired; any new ingestion path is built directly against the Graphiti sidecar.
- **Product surface (MCP server)** — to be rebuilt. The prior SQLite-coupled MCP server is preserved on `legacy/sqlite-local` and `wip/2026-04-10-presplit`.

For the full architectural snapshot that motivated this cleanup, see `docs/CURRENT_STACK.md`. For the cleanup inventory, see `docs/CLEANUP_CANDIDATES.md`.

## Repository layout (post-cleanup)

| Path | Purpose |
|------|---------|
| `infra/graphiti/` | Graphiti L3 infrastructure (Neo4j docker-compose, FastAPI sidecar, Python import and community-detection scripts) |
| `docs/` | Architecture reference, decision log, cleanup inventory, current stack snapshot |
| `private/` | Strategy docs (gitignored, local only) |
| `package.json` | Minimal shell — repo metadata only, no Node dependencies |
| `.env.example` | Graphiti + Neo4j environment variables |

## Branches

| Branch | Purpose |
|--------|---------|
| `main` | Graphiti-only. Clean slate for Graphiti-native rebuild. |
| `feat/l4-testing` | L4 pipeline work-in-progress (reads SQLite, needs porting to Graphiti) |
| `legacy/sqlite-local` | Frozen pointer at the last state where SQLite L3 was live (commit `b8f07ee`) |
| `legacy/supabase` | Frozen pointer at v0.2.0, the pure Supabase era (commit `2a0bf8c`) |
| `wip/2026-04-10-presplit` | Safety snapshot from before the cleanup, including the 861-line MCP server rewrite |
| `chore/cleanup-2026-04-11` | This cleanup branch |

## For AI agents working on this repo

Read `docs/CURRENT_STACK.md` first for the honest state of the architecture as of 2026-04-10/11. Then read `docs/GRAPHITI_INTEGRATION.md` for the scaling patch applied to graphiti-core and for operational notes on the 6,990-entity graph.

All future product code targets the Graphiti sidecar at `http://localhost:8100`. Do not reintroduce SQLite or Supabase paths. If a local-data option is needed in the future, revive it from `legacy/sqlite-local`.
