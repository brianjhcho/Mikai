# MIKAI — Claude Code session context

> **⚠ Graph deprecated but retained (as of 2026-08-11).** The Neo4j/Graphiti substrate is preserved for archival + optional query but is NOT the active writing surface. MIKAI's L3 substrate is now a Karpathy-style **file-based wiki** (`~/.mikai/wiki/`), with `sources/` (immutable per-source markdown) + `concepts/` (LLM-synthesized concept pages) + `SCHEMA.md` (governance). The `dream.py` and `sync.py` daemons that write to Neo4j are stopped (`com.mikai.ingestion` unloaded 2026-08-11). Product code targeting the graph still exists behind the `L3Backend` port but no new writes flow through it. See `~/.mikai/wiki/SCHEMA.md` for the current substrate spec.

## What MIKAI is

MIKAI is a task-state awareness engine (noonchi). Two conceptual layers:

- **L3 — Wiki substrate.** File-based Karpathy-style wiki (~/.mikai/wiki/) — `sources/` immutable per-source captures + `concepts/` LLM-synthesized concept pages. Neo4j/Graphiti retained but deprecated (see banner above).
- **L4 — Task-state awareness.** Thread detection, state classification (exploring → decided → acting → stalled), next-step inference. **The product.** Reads L3 wiki files.

L3 access historically routed through an `L3Backend` port (ARCH-024) with adapters below. Current active substrate is the wiki files directly; adapters remain for legacy code paths:

- **`GraphitiAdapter`** (deprecated) — FastAPI sidecar at `http://localhost:8100`; graphiti-core + Neo4j + DeepSeek V3 + Voyage AI. Retained for archival query, not written to.
- **`LocalAdapter`** (ARCH-025, unbuilt) — fully on-device graph deployment. Design deferred; wiki files supersede this direction.

The wiki files ARE the substrate now. Product code should read `~/.mikai/wiki/concepts/` and `~/.mikai/wiki/sources/`, not the port.

## Where to look for what — docs router

Always start with `docs/STATUS.md` for the volatile "what's actually on main right now" view. CLAUDE.md itself is the constitution — stable principles, not state.

| Working on... | Read first |
|---|---|
| Current state of main / what's live | `docs/STATUS.md` |
| Product vision / noonchi / positioning / moat | `docs/VISION.md` |
| Scope boundaries vs Hermes / OpenClaw / adjacent tools · consumer-product bet | `docs/COMPARISON.md` |
| Architecture / port-adapter / Graphiti patch / current stack | `docs/ARCHITECTURE.md` |
| L3 port/adapter design | `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` → ARCH-024, ARCH-025 |
| Ingestion (filesystem, MCP client, drop folder) | `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` → ARCH-023 |
| L4 design / edge vocabulary / epistemic schema / segmentation | `docs/FOUNDATIONS.md` |
| Open questions / structural gaps / unresolved | `docs/OPEN.md` |
| Architecture decisions (append-only) | `docs/DECISIONS.md` |
| Raw research / archived drafts (Graphiti review, cleanup inventory, L4 papers, memory thesis) | `docs/research/` |

## Architectural direction

Ingestion follows the hybrid model in ARCH-023: filesystem watchers for sources without APIs (Apple Notes, Claude Code), MCP client polling for cloud sources that expose MCP servers (Gmail, Calendar, Drive), and a drop folder as manual fallback. All modes converge on a single write path: the `L3Backend.ingestEpisode()` port method, which each adapter implements (Graphiti calls `add_episode()`; Local calls its own extraction pipeline).

L4 (thread/state detection, next-step inference) is a separate product layer above the port. D-041 is explicit: the port exposes only generic graph primitives (search, node fetch, BFS expand, edges-between, history, stats, episode write, communities). Tension detection, stall surfacing, and state classification are L4 concerns and are implemented once, against the port, so they work with either adapter.

## Branches

| Branch | Purpose |
|---|---|
| `main` | Graphiti adapter live; typed extraction (Stage 6) + OAuth (Stage 5) + ingestion daemon (Stage 2) + eval harness (Stage 4) all landed. Port extraction + LocalAdapter still in design. |
| `feat/ingestion-mcp-client` | Mode 2: MCP client polling for Gmail/Calendar/Drive (not yet merged) |
| `feat/phase-b-local-expand` | Mode 1 expansion — iMessage + local files watchers (not yet merged) |
| `feat/l4-testing` | L4 pipeline WIP (needs porting onto `L3Backend`) |
| `legacy/sqlite-local` | Frozen at v0.3 (`b8f07ee`); design input for `LocalAdapter` |
| `legacy/supabase` | Frozen at v0.2 (`2a0bf8c`); archival only |
| `wip/2026-04-10-presplit` | Safety snapshot, pre-cleanup |

## Graphiti operational notes

The graph lives in Neo4j (~2,371 episodes / 9,920+ entities as of 2026-05-20). graphiti-core is patched to cap candidate resolution at 50 entities and strip attributes from resolution prompts — without this patch, the LLM context overflows at scale. Patch is reproducible via `scripts/apply_graphiti_patch.py` (D-042). Full technical write-up: `docs/ARCHITECTURE.md` (raw research: `docs/research/graphiti-review.md`).

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
