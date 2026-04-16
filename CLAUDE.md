# MIKAI — Claude Code session context

## What MIKAI is

MIKAI is a task-state awareness engine (noonchi). Two conceptual layers:

- **L3 — Knowledge graph.** Bitemporal entity graph extracted from personal content.
- **L4 — Task-state awareness.** Thread detection, state classification (exploring → decided → acting → stalled), next-step inference. **The product.**

L3 is accessed through an `L3Backend` port (ARCH-024). Two adapters coexist on main:

- **`GraphitiAdapter`** (default) — FastAPI sidecar at `http://localhost:8100`; graphiti-core + Neo4j + DeepSeek V3 + Voyage AI.
- **`LocalAdapter`** (first-class alternate, ARCH-025) — fully on-device deployment (Granola-style): embedded graph store, local embeddings, local LLM. Design input: `legacy/sqlite-local`.

Product code depends only on the port. `L3_BACKEND=graphiti|local` selects the adapter at startup.

## Where to look for what — docs router

Always start with `docs/STATUS.md` for the volatile "what's actually on main right now" view. CLAUDE.md itself is the constitution — stable principles, not state.

| Working on... | Read first |
|---|---|
| Current state of main / what's live | `docs/STATUS.md` |
| L3 graph / entity resolution / Graphiti patch | `docs/GRAPHITI_INTEGRATION.md`, `docs/GRAPHITI_BEST_PRACTICES_REVIEW.md` |
| L3 port/adapter design | `docs/DECISIONS.md` → ARCH-024, ARCH-025 |
| Ingestion (filesystem, MCP client, drop folder) | `docs/DECISIONS.md` → ARCH-023 |
| L4 thread/state detection | `docs/L4_RESEARCH_INTEGRATION.md`, `docs/SEGMENTATION_FRAMEWORK.md` |
| Edge vocabulary / epistemic schema | `docs/EPISTEMIC_EDGE_VOCABULARY.md`, `docs/EPISTEMIC_DESIGN.md` |
| Product positioning / noonchi / moat | `docs/NOONCHI_STRATEGIC_ANALYSIS.md`, `docs/INTENT_INTELLIGENCE_MANIFESTO.md`, `docs/MEMORY_ARCHITECTURE_THESIS.md` |
| Architecture decisions (append-only) | `docs/DECISIONS.md` |
| Structural gaps in current build | `docs/ARCHITECTURE_GAPS.md` |
| Open / unresolved questions | `docs/OPEN_QUESTIONS.md` |

## Architectural direction

Ingestion follows the hybrid model in ARCH-023: filesystem watchers for sources without APIs (Apple Notes, Claude Code), MCP client polling for cloud sources that expose MCP servers (Gmail, Calendar, Drive), and a drop folder as manual fallback. All modes converge on a single write path: the `L3Backend.ingestEpisode()` port method, which each adapter implements (Graphiti calls `add_episode()`; Local calls its own extraction pipeline).

L4 (thread/state detection, next-step inference) is a separate product layer above the port. D-041 is explicit: the port exposes only generic graph primitives (search, node fetch, BFS expand, edges-between, history, stats, episode write, communities). Tension detection, stall surfacing, and state classification are L4 concerns and are implemented once, against the port, so they work with either adapter.

## Branches

| Branch | Purpose |
|---|---|
| `main` | Port + GraphitiAdapter live; LocalAdapter in design |
| `feat/ingestion-automation` | Mode 1+3: filesystem watchers + drop folder |
| `feat/ingestion-mcp-client` | Mode 2: MCP client polling for cloud sources |
| `feat/l4-testing` | L4 pipeline WIP (needs porting onto `L3Backend`) |
| `legacy/sqlite-local` | Frozen at v0.3 (`b8f07ee`); design input for `LocalAdapter` |
| `legacy/supabase` | Frozen at v0.2 (`2a0bf8c`); archival only |
| `wip/2026-04-10-presplit` | Safety snapshot, pre-cleanup |

## Graphiti operational notes

The 6,990-entity graph lives in Neo4j. graphiti-core is patched to cap candidate resolution at 50 entities and strip attributes from resolution prompts — without this patch, the LLM context overflows at scale. Patch is reproducible via `scripts/apply_graphiti_patch.py` (D-042). Full technical write-up: `docs/GRAPHITI_INTEGRATION.md`.

The sidecar uses a custom `DeepSeekClient` that adapts DeepSeek V3 to Graphiti's JSON-schema expectations by injecting the schema into the system prompt and using `json_object` response format.

## After every build task

Provide two explanations:

1. **What was built** — technical summary suitable for a git commit. Files changed, what the code does, why.
2. **What this means** — plain-English explanation for Brian. What changed, what problem it solves, how it connects to the L3/L4 direction.

## Do not

- Skip the `L3Backend` port for new product code. MCP handlers, the L4 engine, the ingestion daemon — all depend on the port, never directly on Neo4j, Cypher, SQLite, or sidecar HTTP.
- Leak adapter-specific types into port signatures. If a method can't be described without saying "Graphiti," "Neo4j," or "SQLite," it belongs in an adapter, not in the port.
- Pull from `legacy/sqlite-local` or `legacy/supabase` into main as source material. They are archival references. `LocalAdapter` is a fresh build informed by (not copied from) `legacy/sqlite-local`.
- Describe MIKAI as "local-first" as if it's the only mode. It's one of two first-class modes, selected by `L3_BACKEND`.

## Settled decisions

See `docs/DECISIONS.md` for the full log. Currently load-bearing:

| Decision | What was decided |
|---|---|
| ARCH-019 | Graphiti + Neo4j is the default L3 backend. |
| ARCH-020 | Ingestion targets L3 via `add_episode()`. No intermediate storage. |
| ARCH-023 | Hybrid ingestion: filesystem watchers + MCP client + drop folder. |
| ARCH-024 | `L3Backend` port introduced. Supersedes ARCH-021. |
| ARCH-025 | Local-first preserved as first-class adapter (not legacy revival). |
| D-040 | Python MCP server, co-located with Graphiti sidecar. |
| D-041 | L4 is product layer; port exposes only graph primitives. |
| D-042 | graphiti-core managed as patched dependency, not a fork. |
