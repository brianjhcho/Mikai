# MIKAI — Current Stack & Infrastructure Reference

*Last synthesized: 2026-04-10*
*Repo state: `main` at commit `4efa463` (Adopt Graphiti + Neo4j as L3 backend, drop dead Supabase code)*
*Source: five parallel analysis agents (commits trajectory, stack inventory, topology, data flow, stale code) with cross-verification against the live code.*

## Executive summary

MIKAI is in a **transitional architectural state** as of 2026-04-10. Three backend eras coexist in the codebase — Supabase (abandoned), local SQLite (current for the live product path), and Graphiti + Neo4j (committed as the new L3 backend infrastructure but not yet queried by the product surface). The live product path (MCP server → Claude Desktop) still runs against Supabase or SQLite, not Graphiti. Graphiti holds a 6,990-entity knowledge graph populated by manual Python import scripts, but receives no live ingestion traffic. The commit that adopted Graphiti (`4efa463`) staged the infrastructure but did not wire it into the product path — that's the refactor work still pending.

This document describes what's **actually running** today, not what any single commit message claims. Several descriptions in CLAUDE.md, docs/ARCHITECTURE.md, and previous memory files are out of sync with reality. Where they conflict with code, the code wins.

## Architectural timeline

| Era | Dates | Backend | Status |
|---|---|---|---|
| **v0.1 – v0.2 (pre-SQLite)** | through 2026-03-25 | Supabase Postgres + pgvector, Voyage AI embeddings, Claude Haiku extraction | Abandoned but code references remain in 21+ files |
| **v0.3 (local SQLite)** | 2026-03-26 to 2026-04-06 | better-sqlite3 + sqlite-vec + FTS5, Nomic local embeddings, Claude Haiku extraction; Supabase kept as optional fallback via `MIKAI_LOCAL` flag | Live today in MCP server on main. Being phased out. |
| **v0.4 (Graphiti + Neo4j)** | 2026-04-07 onward, committed 2026-04-10 (`4efa463`) | Neo4j 5.26 + graphiti-core + DeepSeek V3 (LLM) + Voyage AI (embeddings, 1024-dim) + Nomic (embeddings, 768-dim), FastAPI sidecar | Infrastructure present, 6,990 entities loaded, not yet queried by MCP server |

The current live state on `main` is a hybrid: Graphiti infra committed, but the query path still reads SQLite (or Supabase if `MIKAI_LOCAL` is unset). There is a **fracture** between the v0.3 live path and the v0.4 Graphiti path — they do not meet anywhere in the code.

## System topology (as-built, not as-described)

```
┌─────────────────────────────────────────────────────────────────────┐
│                      LIVE PRODUCT PATH (v0.3)                        │
│                                                                      │
│  Claude Desktop                                                      │
│       │ stdio MCP                                                    │
│       ▼                                                              │
│  surfaces/mcp/server.ts (1221 lines, on main)                        │
│    • Imports @supabase/supabase-js (line 29)                         │
│    • Imports store-sqlite, embeddings-local, engine/l3, engine/l4    │
│    • Requires SUPABASE_URL + SUPABASE_SERVICE_KEY unless MIKAI_LOCAL │
│    • With MIKAI_LOCAL=true: reads ~/.mikai/mikai.db                  │
│    • Without: reads Supabase Postgres                                │
│       │                                                              │
│       ▼                                                              │
│  Two possible backends (selected at runtime by MIKAI_LOCAL):         │
│                                                                      │
│  ┌───────────────────┐         ┌──────────────────────┐              │
│  │ Local SQLite      │         │ Supabase (cloud)     │              │
│  │ ~/.mikai/mikai.db │         │ Postgres + pgvector  │              │
│  │                   │         │                      │              │
│  │ tables:           │         │ tables:              │              │
│  │ • sources         │         │ • sources            │              │
│  │ • nodes           │         │ • nodes              │              │
│  │ • edges           │         │ • edges              │              │
│  │ • segments        │         │ • segments           │              │
│  │ • threads (L4)    │         │                      │              │
│  │ • thread_members  │         │ (no L4 tables)       │              │
│  │ • delivery_events │         │                      │              │
│  │ • fts_nodes/segs  │         │                      │              │
│  └───────────────────┘         └──────────────────────┘              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                  GRAPHITI PATH (v0.4, NOT LIVE)                      │
│                                                                      │
│  Manual invocation only:                                             │
│                                                                      │
│  python infra/graphiti/scripts/import_*.py                           │
│       │                                                              │
│       │ reads from: SQLite dump files, Supabase sources table,       │
│       │             osascript Apple Notes, Claude threads,           │
│       │             Perplexity threads                               │
│       ▼                                                              │
│  HTTP POST localhost:8100                                            │
│       │                                                              │
│       ▼                                                              │
│  FastAPI sidecar (infra/graphiti/sidecar/main.py)                    │
│    • graphiti-core with DeepSeek V3 LLM client (custom)              │
│    • Voyage AI voyage-3 embedder                                     │
│    • Nomic dual embeddings (post-hoc, added via script)              │
│    • Endpoints: /health /search /episode /episode/bulk /communities  │
│       │                                                              │
│       ▼                                                              │
│  Neo4j 5.26 container (bolt://localhost:7687)                        │
│    • 6,990 entities                                                  │
│    • 8,056 edges                                                     │
│    • 1,158 episodes (1,102 Apple Notes + 87 Claude threads partial)  │
│    • 1,233 orphan entities (17.6%)                                   │
│    • Patched graphiti_core/utils/maintenance/node_operations.py      │
│      to cap candidates at 50 and strip attributes (scaling fix)      │
│                                                                      │
│  No code path connects this to surfaces/mcp/server.ts.               │
│  The MCP server does not call port 8100. The sidecar does not read   │
│  from SQLite or Supabase except when explicitly invoked by import    │
│  scripts.                                                            │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                  INGESTION PIPELINE (v0.1/v0.2 era)                  │
│                                                                      │
│  Source connectors (TypeScript/JavaScript):                          │
│  • sources/apple-notes/sync.js (osascript)                           │
│  • sources/apple-notes/sync-direct.js (osascript, preferred)         │
│  • sources/gmail/sync.js (Google API)                                │
│  • sources/imessage/sync.js (chat.db)                                │
│  • sources/local-files/sync.js (file scanner)                        │
│       │                                                              │
│       ▼ all call                                                     │
│  engine/ingestion/ingest-direct.ts                                   │
│    • Requires SUPABASE_URL + SUPABASE_SERVICE_KEY (throws if missing)│
│    • Writes raw content to Supabase sources table                    │
│    • No SQLite path                                                  │
│    • No Graphiti path                                                │
│       │                                                              │
│       ▼                                                              │
│  Supabase `sources` table                                            │
│       │                                                              │
│       ▼                                                              │
│  engine/graph/build-graph.js                                         │
│    • Reads Supabase sources WHERE node_count = 0                     │
│    • Track A: Claude Haiku extraction → nodes + edges                │
│    • Track B: Rule-engine word/verb scan → behavioral nodes          │
│    • Voyage AI embeddings on extracted nodes                         │
│    • Writes to Supabase nodes + edges                                │
│       │                                                              │
│       ▼                                                              │
│  engine/graph/build-segments.js                                      │
│    • Track C: zero-LLM segmentation                                  │
│    • Voyage AI embeddings on segments                                │
│    • Writes to Supabase segments                                     │
│       │                                                              │
│       ▼                                                              │
│  engine/inference/rule-engine.ts   ← BROKEN                          │
│    • Computes stall_probability                                      │
│    • Imports from deleted lib/supabase.ts → crashes at import time   │
│                                                                      │
│  engine/scheduler/daily-sync.sh                                      │
│    • Orchestrates: sync:* → build-graph → run-rule-engine →          │
│      build-segments                                                  │
│    • Runs against Supabase                                           │
│    • Not installed in launchd on Brian's machine (optional)          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Runtime services

| Service | Role | Status | Location / evidence |
|---|---|---|---|
| Node.js MCP server | Product surface (stdio) — 8 tools for Claude Desktop | **ACTIVE** | `surfaces/mcp/server.ts`, 1221 lines, started via `npm run mcp` |
| Claude Desktop | MCP client | **ACTIVE** | `surfaces/mcp/claude-desktop-config.json` |
| Local SQLite (mikai.db) | L3 graph + L4 state backend when `MIKAI_LOCAL=true` | **ACTIVE** | `~/.mikai/mikai.db`, path from `~/.mikai/config.json`; `lib/store-sqlite.ts` |
| Supabase Postgres + pgvector | Legacy L3 + segment storage, fallback when `MIKAI_LOCAL` unset | **TRANSITIONAL** (still wired in main MCP server, required by ingestion pipeline) | `.env.local`, `surfaces/mcp/server.ts:29,65-79`, `engine/ingestion/ingest-direct.ts:145-149` |
| Neo4j 5.26 (Docker) | Graphiti graph database | **INFRASTRUCTURE PRESENT, NOT LIVE** (has 6,990 entities but not queried by product) | `infra/graphiti/docker-compose.yml` |
| Graphiti FastAPI sidecar | HTTP wrapper around graphiti-core | **INFRASTRUCTURE PRESENT, NOT LIVE** | `infra/graphiti/sidecar/main.py`, port 8100 |
| launchd scheduler | Optional daily sync cron | **AVAILABLE, NOT INSTALLED** | `engine/scheduler/com.mikai.daily-sync.plist`; `npm run scheduler:install` to activate |

## Data stores

| Store | Schema / Tables | Status | Notes |
|---|---|---|---|
| **Local SQLite** `~/.mikai/mikai.db` | `sources`, `nodes`, `edges`, `segments`, `threads`, `thread_members`, `thread_transitions`, `thread_edges`, `delivery_events`, `fts_nodes`, `fts_segments`, `fts_edges` (FTS5 external-content) | **ACTIVE (L3+L4 backend for MCP when `MIKAI_LOCAL=true`)** | Defined in `lib/store-sqlite.ts`. L4 schema initialized by `initL4Schema()` in `engine/l4/schema.ts`. Vectors via `sqlite-vec`. |
| **Neo4j** | Graphiti-managed: entity nodes with labels, episodic nodes, `RELATES_TO` edges with `fact`/`valid_at`/`invalid_at`/`episodes`, community nodes | **INFRA PRESENT, NOT LIVE** (has data, no product reads) | 6,990 entities; patch applied at `.venv/.../node_operations.py` line 299 to cap candidates and strip attributes |
| **Supabase Postgres** | `sources`, `nodes`, `edges`, `segments` (all with `embedding VECTOR(1024)`) | **TRANSITIONAL** (ingestion pipeline still writes here; MCP server reads here when `MIKAI_LOCAL` unset) | Schema described in `docs/ARCHITECTURE.md` (now out of sync with reality) |
| **File-based state** | `l4-progress.json` (root), `sources/*/.synced.json`, `.synced-direct.json`, `scripts/.claude-code-synced.json` | **ACTIVE** | Harness-pattern state files for pipeline resumption and sync deduplication |

## LLMs and embedding services

| Service | Provider | Role | Status | Evidence |
|---|---|---|---|---|
| Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | Anthropic | Track A node extraction (reasoning map), L4 next-step inference (OmniActions 7-category CoT) | **ACTIVE** | `engine/l4/infer-next-step.ts`, `lib/ingest-pipeline.ts` |
| Claude Sonnet 4.6 | Anthropic | Terminal desire synthesis (future) | **NOT WIRED** | Referenced in CLAUDE.md / docs only |
| DeepSeek V3 | DeepSeek OpenAI-compatible API | Graphiti sidecar entity extraction + edge resolution | **ACTIVE inside Graphiti path** (dormant from MCP perspective) | `infra/graphiti/sidecar/main.py` `DeepSeekClient` class with `json_object` mode |
| Voyage AI voyage-3 (1024-dim) | Voyage AI | Remote embeddings for Supabase era + Graphiti entity embeddings | **DUAL STATUS** — legacy for Supabase path, active for Graphiti path | `lib/embeddings.ts`, `infra/graphiti/sidecar/main.py`, `VoyageAIEmbedder` |
| Nomic nomic-embed-text-v1.5 (768-dim) | Local ONNX via `@huggingface/transformers` | Local embeddings for SQLite L3 hybrid search + Graphiti dual-embedding post-pass | **ACTIVE** | `lib/embeddings-local.ts`, `infra/graphiti/scripts/add_nomic_embeddings.py` |

## Dependencies

**Node.js (`package.json`)**

ACTIVE in live product path:
- `@modelcontextprotocol/sdk` (MCP server stdio transport)
- `@anthropic-ai/sdk` (Haiku calls)
- `better-sqlite3` (SQLite backend)
- `sqlite-vec` (vector search inside SQLite)
- `@huggingface/transformers` (local Nomic embeddings)
- `zod` (MCP tool input validation)
- `tsx` (TypeScript runtime)
- `@supabase/supabase-js` — **HARD DEPENDENCY in main MCP server**, imported unconditionally at `surfaces/mcp/server.ts:29`

Optional / used only in specific connectors:
- `googleapis` (Gmail sync, optional per package.json)
- `playwright` (Perplexity export, optional)
- `voyageai` (installed but not imported; `lib/embeddings.ts` calls Voyage via raw `fetch`)

Dev-only:
- `pg` (testing)
- TypeScript, eslint, `@types/*`

**Python (`infra/graphiti/requirements.txt`)**

All are sidecar-scoped, not part of the Node.js runtime:
- `graphiti-core[anthropic,voyageai]>=0.5`
- `fastapi>=0.115`
- `uvicorn>=0.34`
- `pydantic>=2.0`

## Environment variables

Required for live product path (as of main):
- `ANTHROPIC_API_KEY` — Haiku inference for L4
- Either `MIKAI_LOCAL=true` AND `~/.mikai/config.json` with `dbPath`, **OR** `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`

Required for ingestion pipeline (whether or not you use SQLite for MCP):
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — `engine/ingestion/ingest-direct.ts` throws if absent
- `VOYAGE_API_KEY` — embeddings for Supabase-path build-graph / build-segments
- Connector-specific: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`

Required for Graphiti path (only when running import scripts or the sidecar):
- `DEEPSEEK_API_KEY` (sidecar LLM)
- `VOYAGE_API_KEY` (sidecar embeddings)
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`

Unused / legacy in `.env.local` but still referenced by code:
- None specifically dead — everything in the env file still has at least one code path that reads it, though many of those code paths are themselves legacy (see `docs/CLEANUP_CANDIDATES.md`).

## Directory topology

Top-level directories with current status. `ACTIVE` = in the live product path. `INFRA PRESENT` = code is current but not yet wired to live path. `TRANSITIONAL` = still referenced but being phased out. `LEGACY` = dead or vestigial. `EMPTY` = no files of substance.

| Path | Contents | Status | Imported by |
|---|---|---|---|
| `apps/web/` | (empty) | EMPTY | — |
| `bin/` | `mikai.ts` — CLI for init / serve / sync / build / status | ACTIVE | npm bin entry `@chobus/mikai` |
| `docs/` | Architecture specs, decision logs, research integration notes, epistemic vocabulary, Graphiti integration, this doc | Reference (not imported) | — |
| `engine/eval/` | L4 eval suite, segment/stall/node evals, test-suite, brief-routing, PuppyGraph experiment artifacts, L4 ground truth | ACTIVE for L4 eval, LEGACY for PuppyGraph pieces | `engine/eval/eval-l4.ts` reads L4 output; most other files are standalone |
| `engine/graph/` | `build-graph.js` (Supabase-coupled Track A+B), `build-segments.js` (Supabase Track C), `build-segments-local.ts` (SQLite variant), `smart-split.js` | TRANSITIONAL | Scheduler (`daily-sync.sh`), npm scripts |
| `engine/ingestion/` | `ingest-direct.ts` (Supabase-only), `ingest-cli.ts`, `preprocess.ts` (content cleaning) | TRANSITIONAL (preprocess active, ingest-direct Supabase-bound) | All `sources/*/sync.js` import `cleanContent` from preprocess.ts |
| `engine/inference/` | `rule-engine.ts` (**BROKEN**: imports deleted `lib/supabase.ts`), `run-rule-engine.js` | TRANSITIONAL but broken | Scheduler stage 7 (would crash if invoked) |
| `engine/l3/` | `bitemporal`, `entity-resolution`, `hybrid-search`, `invalidate-edges`, `migrate-bitemporal`, `run-l3-upgrade`, `sync-fts`, `types` | TRANSITIONAL (SQLite-era L3, will be deleted when Graphiti integration is complete) | `surfaces/mcp/server.ts` imports `hybridGraphSearch`, `searchSegmentsHybrid`; L4 `graph-enrichment.ts` queries the same SQLite `edges` table |
| `engine/l4/` | Pipeline: types, schema, store, detect-threads, classify-state, graph-enrichment, evaluate-delivery, infer-next-step, backfill-sources, run-l4-pipeline | ACTIVE (reads SQLite L3, not Graphiti) | `surfaces/mcp/server.ts`, `engine/eval/eval-l4.ts` |
| `engine/scheduler/` | `daily-sync.sh`, `com.mikai.daily-sync.plist`, `README.md` | AVAILABLE (plist not loaded into launchd by default) | npm script `scheduler:run` |
| `infra/graphiti/` | `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `sidecar/main.py` (FastAPI + graphiti-core + DeepSeek + Voyage), `scripts/*.py` (15 Python import/analysis/comparison scripts) | INFRA PRESENT (new L3 backend, not yet queried by product) | Standalone Python processes. **Not imported by any TypeScript code.** |
| `infra/supabase/` | Legacy SQL migrations and schema files | LEGACY | Referenced only by Supabase-era scripts |
| `lib/` | `store-sqlite.ts`, `embeddings-local.ts`, `embeddings.ts` (Voyage), `ingest-pipeline.ts` (extraction prompt), `AGENTS.md` | MIXED: store-sqlite + embeddings-local active; embeddings.ts + ingest-pipeline.ts transitional | `store-sqlite.ts` is the highest-fan-in file (8 importers); `embeddings.ts` is imported only by `engine/graph/build-*` Supabase-era scripts |
| `private/` | Strategy docs (`01_CORE_ENGINE.md`, `02_EXECUTION_STRATEGY.md`, `03_WORKING_STATE.md`, `reference/COMPETITIVE_LANDSCAPE.md`), archive, identity placeholder | Local-only (`.gitignore`-d) | Not imported |
| `scripts/` | `cleanup-noisy-nodes.js`, `cleanup-sources.js`, `embed-local.ts`, `perplexity-playwright.ts`, `test-embeddings-local.ts`, `test-generalization.js`, `watch-claude-code.js`, `watch-claude-exports.js` | MIXED (`watch-claude-code.js` in scheduler; others are one-off tools or tests) | `engine/scheduler/daily-sync.sh` calls `watch-claude-code.js` |
| `sources/apple-notes/` | `sync.js` (HTML export), `sync-direct.js` (osascript, preferred) | ACTIVE | Scheduler stage 1 |
| `sources/gmail/` | `sync.js` | ACTIVE | Scheduler stage 4 |
| `sources/imessage/` | `sync.js` | ACTIVE | Scheduler stage 3 |
| `sources/local-files/` | `sync.js` (import folder + Claude exports) | ACTIVE | Scheduler stage 2 |
| `surfaces/mcp/` | `server.ts` (1221 lines, Supabase-coupled), `claude-desktop-config.json`, `SETUP.md`, `AGENTS.md` | ACTIVE | Bin entry, npm `mcp` script |
| `surfaces/web/` | (empty) | EMPTY | — |

## Data flow pipelines

### Pipeline A — live product (Supabase → SQLite bridge → MCP)

What runs today when Brian uses Claude Desktop:

1. Source connectors write to **Supabase** via `engine/ingestion/ingest-direct.ts`. Not to SQLite directly. If `SUPABASE_URL` isn't set, ingestion fails hard.
2. `engine/graph/build-graph.js` reads Supabase sources, runs Claude Haiku extraction + rule engine, writes Supabase `nodes` and `edges`.
3. `engine/graph/build-segments.js` segments and embeds via Voyage AI, writes Supabase `segments`.
4. `engine/inference/rule-engine.ts` should compute stall scores — **broken**, fails at import due to deleted `lib/supabase.ts`.
5. For MCP reads: either the MCP server reads directly from Supabase (when `MIKAI_LOCAL` is unset) or it reads from a **separate local SQLite database** at `~/.mikai/mikai.db` that has been populated... by what? There is no live script on main that replicates Supabase → SQLite. The local SQLite is populated by older manual migration runs (see `legacy/sqlite-local` branch at `b8f07ee`) or by scripts no longer called.

Consequence: if Brian hasn't run a Supabase→SQLite sync recently, his local `~/.mikai/mikai.db` is **stale** relative to Supabase. And Supabase itself is only fresh if he's running ingestion scripts manually (scheduler isn't loaded in launchd).

### Pipeline B — Graphiti (dormant from the product's perspective)

What exists but is not wired:

1. A Neo4j 5.26 container and a FastAPI sidecar run if Brian manually does `docker-compose up` inside `infra/graphiti/`.
2. Manual Python scripts in `infra/graphiti/scripts/` read from sources (Apple Notes via osascript, Claude threads from SQLite dumps, Perplexity threads) and POST episodes to the sidecar `/episode` endpoint.
3. The sidecar calls DeepSeek V3 for extraction and Voyage AI for embeddings.
4. Neo4j stores entities, relationships, and communities.

Nothing in `surfaces/mcp/`, `engine/l3/`, `engine/l4/`, `engine/graph/`, `engine/ingestion/`, or `engine/inference/` ever calls the sidecar. The 6,990-entity graph is read-only from the product's perspective — it exists, it's not consulted.

### Scheduler reality check

`engine/scheduler/daily-sync.sh` defines an 8-stage pipeline: sync:notes → sync:local → sync:imessage → sync:gmail → watch-claude-code → build-graph → run-rule-engine → build-segments. It's invoked via `npm run scheduler:run` or via launchd (if installed).

- **launchd plist is not currently loaded.** Brian would need to `launchctl load` it manually. So the scheduler is not firing daily.
- **If it did fire**, it would run the entire Supabase pipeline, and step 7 (`run-rule-engine`) would crash because `rule-engine.ts` imports from the deleted `lib/supabase.ts`.
- **L4 pipeline is NOT in the scheduler.** `npm run l4` is a separate manual command; state classification isn't computed on a schedule.

## What the MCP server actually exposes

Confirmed from `surfaces/mcp/server.ts` on main (the 1221-line version, not the 861-line rewrite in wip):

The tool list on main is older than the "9 tools v2.0" described in CLAUDE.md. The server on main still has `search_knowledge` and `search_graph` as separate tools (they were merged into one `search` in the wip rewrite). It still has `get_stalled` (replaced by `get_threads` in the rewrite). It still has `get_status` (folded into `get_brief` in the rewrite).

The 9-tools-v2.0 MCP server description in CLAUDE.md refers to a state that exists only on `wip/2026-04-10-presplit`, not on main.

## Active architectural issues

These are state-of-the-world findings, not recommendations. Recommendations live in `docs/CLEANUP_CANDIDATES.md`.

1. **`engine/inference/rule-engine.ts` has a runtime break** introduced by commit `4efa463`. Line 14 imports from `'../../lib/supabase.js'` — the file that commit deleted. Dormant because the scheduler isn't loaded and nothing else calls it, but it's broken on disk. Either the import must be removed, the file restored (on a legacy branch), or `rule-engine.ts` itself must be deleted.

2. **The live MCP server on main still has hard Supabase coupling.** `surfaces/mcp/server.ts` unconditionally imports `@supabase/supabase-js` and creates a client. The `MIKAI_LOCAL` flag is checked later, but the import always runs. Removing `@supabase/supabase-js` from `package.json` would cause the MCP server to fail at boot.

3. **The ingestion pipeline writes only to Supabase.** `engine/ingestion/ingest-direct.ts` throws if `SUPABASE_URL` is unset. Sources do not write to SQLite directly, and they do not write to Graphiti at all. This means every description of "MIKAI as a local-first system" that describes new data landing in SQLite or Graphiti is aspirational, not actual.

4. **The local SQLite at `~/.mikai/mikai.db` has no live population path.** When the MCP server is configured with `MIKAI_LOCAL=true`, it reads from a database that's only populated by manual script runs. If Brian hasn't run a sync recently, the MCP server serves stale data.

5. **Graphiti has 6,990 entities but zero live write traffic.** The only way data enters Graphiti is via manual Python scripts in `infra/graphiti/scripts/`. There is no automated path, no scheduler hook, no webhook, no MIKAI code that calls the sidecar. The graph is a static snapshot of what Brian imported on the days he ran the scripts.

6. **Three directions of scheduler truth.** `engine/scheduler/daily-sync.sh` runs the Supabase path. `npm run l4` runs the SQLite-L4 path manually. `python infra/graphiti/scripts/import_*.py` populates Graphiti manually. None of the three are integrated with each other.

7. **The MCP server rewrite exists but is uncommitted.** An 861-line cleaner rewrite of `surfaces/mcp/server.ts` (merging tools into `search`, removing all Supabase references, renaming tools to v2.0 shapes) exists only on `wip/2026-04-10-presplit`. It has not been merged to main. Every description in CLAUDE.md that talks about the v2.0 tool set is describing the wip version, not main.

8. **`docs/ARCHITECTURE.md` on main still describes Supabase + pgvector as the primary store.** The doc has not been updated for the SQLite era, let alone the Graphiti era. Any reader of that doc will build a wrong mental model.

9. **Settled decisions ARCH-001 and ARCH-018 in CLAUDE.md still assert "Supabase only."** The CLAUDE.md decision table has not been updated to mark them as superseded. A new decision (ARCH-019 — Graphiti adopted) has not been added.

10. **`infra/supabase/` still contains live SQL migrations referenced by build-graph.js.** Dropping Supabase as a backend means reckoning with that directory too. It's not just dead SQL files — scripts point at them.

## Current branches at a glance

| Branch | Purpose | Latest commit |
|---|---|---|
| `main` | Graphiti infra + Supabase deletions. Still has v0.3 SQLite L3, v0.3 MCP server with Supabase coupling. | `4efa463` |
| `feat/l4-testing` | L4 WIP: multi-domain config, classification tweaks, eval suite | `ff8a883` |
| `legacy/sqlite-local` | Pointer to pre-Graphiti main state | `b8f07ee` |
| `legacy/supabase` | Pointer to pre-SQLite era (v0.2.0) | `2a0bf8c` |
| `wip/2026-04-10-presplit` | Safety snapshot. Contains: MCP server rewrite (861 lines), L3 transitional tweaks, doc rewrites, uncommitted AGENTS.md / CLAUDE.md / docs/ARCHITECTURE.md changes, new L3 `invalidate-edges.ts` | `44b2739` |

## Critical disclaimer

This reference doc describes MIKAI as-built, not as-documented. If you are reading `CLAUDE.md`, `docs/ARCHITECTURE.md`, or `docs/MEMORY_ARCHITECTURE_THESIS.md`, be aware that several load-bearing claims in those files reflect earlier architectural eras. Specifically:

- `docs/ARCHITECTURE.md` describes Supabase + pgvector as the primary store with Track A/B/C extraction writing to `sources/nodes/edges/segments` in Postgres. That's the v0.2 reality. The v0.3 (SQLite) transition is not fully reflected. The v0.4 (Graphiti) transition is not reflected at all.
- `CLAUDE.md` describes an MCP server v2.0 with 9 tools (`search`, `get_brief`, `get_tensions`, `get_threads`, `get_thread_detail`, `get_next_steps`, `get_history`, `add_note`, `mark_resolved`). That server exists only on `wip/2026-04-10-presplit`. The `main` MCP server is older, has different tool names, and has hard Supabase coupling.
- `CLAUDE.md` lists ARCH-001 (Supabase only) and ARCH-018 (stay on Supabase) in "Settled decisions — do not relitigate." Those decisions have been superseded by the Graphiti adoption in commit `4efa463`, but the text has not been updated.
- Memory files reference Graphiti as "live with 6,990 entities." The graph exists with that many entities, but it is not queried by any live product path. "Live" means "populated," not "integrated."

A doc refresh is needed, but it should happen *after* cleanup — the post-cleanup architecture will be different from both the current reality and the aspirational description, and writing the doc now would mean rewriting it twice.
