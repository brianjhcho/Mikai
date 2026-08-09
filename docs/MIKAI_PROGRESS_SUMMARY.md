# MIKAI — Progress Summary

**Generated:** 2026-06-10
**Scope:** What MIKAI is, the major work completed (with emphasis on the 2026-06-09→10 ingestion-recovery session), the current live state, and where the next thread of work (L4) picks up.

---

## What MIKAI is

MIKAI is a **task-state awareness engine** ("noonchi"). Two conceptual layers:

- **L3 — Knowledge graph.** A bitemporal entity graph extracted from personal content (Apple Notes, Claude threads, Gmail, WhatsApp). Backed by **Graphiti + Neo4j + DeepSeek V3 + Voyage AI**, exposed through a FastAPI sidecar at `http://localhost:8100`.
- **L4 — Task-state awareness.** Thread detection, state classification (exploring → decided → acting → stalled), and next-step inference. **This is the product, and it is still unbuilt** — it needs to be designed against Graphiti's freeform graph.

Architecture rule: everything new is built **directly against the Graphiti sidecar**. No SQLite path, no Supabase path, no dual-backend abstraction.

---

## Headline of the latest session (2026-06-09 → 06-10)

**A latency question uncovered that ingestion had been 100% broken for ~3 weeks — we root-caused it, fixed it, backfilled the gap, and made ingestion fully automated for the first time.**

### How it unfolded

1. **Latency check.** Noted the MIKAI connector felt slow. Pulled the sidecar's `duration_ms` telemetry: `get_source` is actually fast (~15–340 ms), `search` ~0.7–2 s (cold up to ~5 s), `get_history` up to ~4 s. No hard timeout exists, so the latency is harmless. Along the way, found a real bug: **`get_history` throws on `as_of` dates without a timezone** (naive vs. aware datetime comparison). Logged it as a known issue.

2. **L4 kickoff (paused).** Began designing L4 over the real graph. Discovered the graph's edges are **~99% generic native extraction** (`USES`, `INCLUDES`, `CONTAINS`…), not the aspirational epistemic edges (`CONTRADICTS`, `HAS_THREADS_ABOUT`) — those were only **15 of 15,108 edges**. Graphiti already provides **Communities** (50 emergent topic clusters) and **Sagas** (import-time conversation groupings). The open design fork: use Communities + temporal signal as the thread substrate, vs. computing task-threads fresh.

3. **Ingestion-coverage check → outage found.** Before building L4, verified the graph was current. It was frozen at **May 21**. Investigation revealed it wasn't merely stale — **every episode was failing to ingest.**

### Root cause

`requirements.txt` pinned `graphiti-core>=0.5` (**unpinned**). A `pip install` floated it to **0.28.2**, which:
- **reserves `summary`** as a protected `EntityNode` field, and
- **persists custom node/edge attributes as nested Neo4j `Map`s**, which Neo4j rejects (`Property values can only be of primitive types`).

The entire **Stage 6 typed-extraction layer** (custom entity types + epistemic edges, both using `summary`/`confidence`/`explanation` attributes) was incompatible with 0.28.2, so every `add_episode` threw and **nothing was written** after the dependency floated.

### The fix (decision D-052)

- **Switched ingestion to graphiti-core's _native_ extraction** through the cloned `GraphitiAdapter` (L3). The single chokepoint `extraction/router.py::extraction_params_for()` now returns `{}` (no custom types) unless `MIKAI_TYPED_EXTRACTION=1`. Native nodes/edges carry only primitive fields → no Map bug.
- **Pinned `graphiti-core==0.28.2`** to stop the silent float.
- Stage 6 modules left **intact and revivable** (gated behind the flag; reviving needs a graphiti-core version that persists custom attributes correctly).

Rationale: native sidesteps the bug, matches the freeform-graph L4 direction, the graph was ~99% native already, and it's **~4× cheaper**.

### Results

| Metric | Before | After |
|---|---|---|
| Newest content | May 21 | **Current** (through June) |
| Episodes | ~2,379 | **~3,370** |
| Entities | ~11,137 | **~12,640** |
| Backlog ingested | — | **954 Claude turns** (+ Apple Notes) |
| Cost of catch-up | — | **$1.30** (~$0.0014/turn) |
| Failure rate | 100% | ~2.3% (transient DeepSeek blips) |

### Ingestion is now automated (closes roadmap item #3 / O-040)

The launchd ingestion daemon was **never actually installed** before (TCC-blocked because the repo lives under `~/Desktop/`). It is now **live**:
- `com.mikai.ingestion`, installed via the **D-051 TCC-safe pattern**: runner at `~/Library/Application Support/mikai/launchd/sync-runner.sh` (outside `~/Desktop/`), secrets in `~/.mikai/launchd.env`, logs at `~/.mikai/logs/sync.{out,err}.log`, folded into the App-Support `install.sh`.
- Runs `sync.py` in **watchdog mode** — auto-ingests new Claude threads + Apple Notes the moment files change. Confirmed multi-hour stable uptime with real-time per-turn ingestion.
- **Full Disk Access** granted on the Homebrew python so Apple Notes (sandboxed SQLite) reads work.
- Pause anytime: `launchctl bootout gui/$(id -u)/com.mikai.ingestion`.

---

## Current live state (on `main`)

- **L3 graph:** ~3,370 episodes / ~12,640 entities in Neo4j 5.26 (docker-compose). Graphiti sidecar + custom `DeepSeekClient` + Voyage `voyage-3` embeddings. graphiti-core pinned `==0.28.2` with the cap-50 candidate-resolution patch (D-042).
- **L3 port (Stage 7, D-050):** `L3Backend` ABC + `GraphitiAdapter`; product code is port-only.
- **Extraction:** **native by default** (D-052). Typed extraction (Stage 6) disabled behind `MIKAI_TYPED_EXTRACTION=1`.
- **Ingestion:** `sync.py` filesystem daemon now **running under launchd** (auto, real-time). Manual catch-up still available via `sync.py --once`.
- **MCP surface (Stage 5, D-048):** Python MCP server at `/mcp` (FastMCP, streamable HTTP) + stdio for Desktop; OAuth for Claude.ai web/mobile. Tools: `search`, `get_source`, `get_history`, `add_note`, `get_stats`.
- **Deployment (Pattern B, D-051):** laptop-as-home-server; Docker stack + health probe managed by LaunchAgents.

---

## Where L4 picks up (the next item)

L4 (the actual product) is still unbuilt. The session established the design substrate against the real graph:

- **Old design premises are dead.** The retired SQLite-era L4 assumed it would build its own threads (embedding kNN + Union-Find) and read epistemic edge *types* for state. Neither holds: Graphiti already clusters (Communities), and the epistemic edges effectively don't exist (15/15,108).
- **State signal must come from where it lives:** **temporal activity** (recency/burst/silence over timestamped episodes) + **bitemporal churn** (726 invalidated edges = belief revision), not edge types.
- **Open fork (undecided):** what is a "thread"? — (A) Graphiti **Communities** as topic backbone + temporal signal for state [recommended], (B) compute **task-threads fresh** from episodic co-occurrence, or (C) **Sagas** (likely a dead end — they're import artifacts).

The graph is now current and self-maintaining, so L4 can be designed against complete data.

---

## Commits from this session

- `a19a81c` — fix(ingestion): default to native graphiti extraction; pin graphiti-core
- `fdbbfd5` — docs: reconcile main to current state (D-052, STATUS, OPEN, operator guide, compose)
- `3c70e4d` (branch `mcp-layer`) — docs(mcp): note `get_history` naive/aware datetime bug

---

## Open follow-ups

- **`get_history` timezone bug** — one-line fix known (normalize naive `as_of` to UTC), deferred.
- **Repo-side launchd template** (`infra/graphiti/launchd/`) still describes the old `~/Desktop/` path — should be reconciled to the deployed App-Support reality.
- **`mcp-layer` worktree** is stale (58 commits behind `main`, all work already merged) — safe to remove.
- **L4 design** — pick the thread substrate and start building.
- **Reviving typed extraction** — only if L4 needs typed attributes, and only after adopting a graphiti-core version that persists custom attributes as flat properties.
