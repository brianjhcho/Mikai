# MIKAI — Claude Code session context

## What MIKAI is

MIKAI is a task-state awareness engine (noonchi). Two conceptual layers:

- **L3 — Knowledge graph.** Bitemporal entity graph extracted from personal content. Backed by Graphiti + Neo4j + DeepSeek V3 + Voyage AI.
- **L4 — Task-state awareness.** Thread detection, state classification (exploring → decided → acting → stalled), next-step inference. **The product.** Currently unbuilt on main — needs to be designed against Graphiti's freeform graph model.

## Current state of the repo

Main is Graphiti-only. The v0.3 local-SQLite and v0.2 Supabase implementations were retired in the 2026-04-11 cleanup. Everything in `lib/`, `engine/`, `sources/`, `surfaces/`, `bin/`, `scripts/`, and `infra/supabase/` has been removed from main. The entire TypeScript codebase has been retired.

What remains on main:
- `infra/graphiti/` — Neo4j docker-compose, FastAPI sidecar, Python import/analysis scripts
- `docs/` — Architecture reference, decision log, cleanup inventory, current stack snapshot
- Root-level metadata files (`package.json` stripped to identity-only, `.env.example`, `AGENTS.md`, `CLAUDE.md`, `README.md`)

For the full state-of-the-world snapshot that drove the cleanup, read `docs/CURRENT_STACK.md`. For the per-file deletion rationale, read `docs/CLEANUP_CANDIDATES.md`.

## Architectural direction

The direction going forward is clear: **everything new is built directly against the Graphiti sidecar at `http://localhost:8100`.** No SQLite path. No Supabase path. No dual-backend abstraction layer. If a future local-data option is needed, revive it from `legacy/sqlite-local` as a separate branch; do not re-entangle it with main.

The next work items, roughly in order:
1. Redesign L4's tension/state/thread detection to work over Graphiti's freeform relationship graph (edges like `CONTRADICTS`, `COLLABORATED_WITH`, `HAS_THREADS_ABOUT`) rather than the fixed epistemic vocabulary from the SQLite era.
2. Build a new product surface (likely MCP) that calls the Graphiti sidecar's `/search` endpoint.
3. Build an automated ingestion pipeline that feeds source apps into Graphiti via the sidecar's `/episode` endpoint, replacing the manual Python script workflow.
4. Build eval tooling for Graphiti graph quality.

## Branches

| Branch | Purpose |
|---|---|
| `main` | Graphiti-only, post-cleanup |
| `feat/l4-testing` | L4 WIP (reads SQLite, needs porting) |
| `legacy/sqlite-local` | v0.3 local SQLite snapshot (commit `b8f07ee`) |
| `legacy/supabase` | v0.2 Supabase snapshot (commit `2a0bf8c`) |
| `wip/2026-04-10-presplit` | Safety snapshot with the 861-line MCP server rewrite |

## Graphiti operational notes

The 6,990-entity graph lives in Neo4j. Graphiti-core has been patched to cap candidate resolution at 50 entities and strip attributes from resolution prompts — without this patch, the LLM context overflows at scale. The patch is applied in-place to `.venv/lib/.../graphiti_core/utils/maintenance/node_operations.py` line 299. See `docs/GRAPHITI_INTEGRATION.md` for the full technical write-up, import cost estimates, and entity resolution pipeline explanation.

The sidecar uses a custom `DeepSeekClient` class that adapts DeepSeek V3 to Graphiti's JSON-schema expectations by injecting the schema into the system prompt and using `json_object` response format.

## After every build task

Provide two explanations:

1. **What was built** — technical summary suitable for a git commit. Files changed, what the code does, why.
2. **What this means** — plain-English explanation for Brian. What changed, what problem it solves, how it connects to the L3/L4 direction.

## Do not

- Reintroduce Supabase, SQLite, Voyage AI remote embeddings, or Nomic local ONNX in any path that's not inside the Graphiti sidecar or explicitly marked as a legacy revival.
- Add a dual-backend abstraction layer ("L3Backend" TypeScript interface) — Graphiti is the only L3. Any TypeScript code written from here on calls the sidecar over HTTP.
- Pull from `legacy/sqlite-local` or `legacy/supabase` into main. Those branches are archival, not source material.
- Describe MIKAI as "local-first" in new docs unless the local option has been explicitly revived as a separate project.

## Settled decisions

| Decision | What was decided |
|---|---|
| ARCH-019 | Graphiti + Neo4j is the sole L3 backend. Supersedes ARCH-001 (Supabase only) and ARCH-018 (stay on Supabase). |
| ARCH-020 | Ingestion targets Graphiti directly via the sidecar `/episode` endpoint. No intermediate storage layer. |
| ARCH-021 | No dual-backend abstraction. Code calls the sidecar HTTP API directly. If a local option is ever needed it lives on a separate branch. |
| D-039 | MCP remains the intended product surface direction (pending rebuild). |
