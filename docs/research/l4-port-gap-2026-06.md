# L4 Port Gap Audit — 2026-06

> **Captured:** 2026-06-23 from a deep research thread on what it takes to port the existing L4 prototype onto the live `L3Backend` port (ARCH-024 / D-050).
> **Status:** L4 prototype exists on `feat/l4-testing` (last commit `ff8a883`). L4 is NOT on main. The pipeline was built against the SQLite-era L3 and needs structural porting, not just a code move.
> **Use this when:** Planning the L4 port; deciding language / persistence / algorithm choices; estimating effort.

---

## Current state

| Thing | State |
|---|---|
| L3 port on main | Live. 11 async methods at `infra/graphiti/sidecar/l3/port.py`. Domain types only. |
| L4 pipeline | Exists on `feat/l4-testing`. TypeScript + `better-sqlite3`. 11 files in `engine/l4/`, plus `engine/eval/eval-l4.ts`. |
| L4 on main | None. |
| FOUNDATIONS §3 build priority match | Pipeline shape (detect → classify → evaluate → infer) **already built** on the branch. The gap is integration, not greenfield. |

---

## What survives the port unchanged (logic only)

Pure logic with no L3 coupling — drop-in across language port:

- `infer-next-step.ts` SYSTEM_PROMPT (OmniActions 7-category CoT, Haiku)
- `evaluate-delivery.ts` rules (48h cooldown, 7–30d stall window, cap 5/cycle, cross-source boost)
- `classify-state.ts` regex pattern tables (COMPARISON / DECISION / ACTION / RESOLUTION)
- `domain-config.ts` (state machine spec, anchor node types)
- `delivery_events` schema + PPP metrics
- Union-Find clustering algorithm
- Anthropic harness state file (`l4-progress.json`)

---

## What is structurally broken by the port

Five categories, ranked by severity:

### 1. Wrong language

L3 port is Python; L4 is TypeScript. Two paths:

- **(a)** Rewrite L4 in Python, co-located with the sidecar (`infra/graphiti/sidecar/l4/`). Direct port-method calls, single runtime, simpler ops.
- **(b)** Add an HTTP/MCP L3 client in TypeScript. Preserves existing TS but adds RTT + serialization.

`STATUS.md` line 81 implies (a): "needs a real rewrite onto the new `L3Backend` port."

### 2. SQLite-era tables that don't exist in the Graphiti world

- `segments` table → no equivalent. Graphiti stores raw `Episode` content; entities extracted as `Node`s. The `splitGmail` / `splitAppleNote` / `splitIMessage` segmentation framework (FOUNDATIONS §4) **was never ported to the Graphiti pipeline.**
- `vec_segments`, `vec_nodes` (sqlite-vec ANN indexes) → no equivalent. Vector search is `port.search()` / `port.search_nodes()`. You don't get raw embedding-space kNN — you get hybrid ranked results.
- `nodes.has_action_verb`, `nodes.node_type` → port returns `Node(uuid, name, labels, summary)`. `node_type` becomes `labels[0]`; `has_action_verb` has no replacement.

### 3. Direct SQL → port primitive map

| `engine/l4/*` SQL | Port equivalent |
|---|---|
| `SELECT * FROM segments JOIN sources …` | No single call — reformulate around `Episode` / `Node`. |
| `SELECT … FROM vec_segments WHERE embedding MATCH …` | `port.search(SearchQuery(text, k))` — returns ranked edges, not distances. |
| `SELECT … FROM vec_nodes WHERE embedding MATCH …` | `port.search_nodes(SearchQuery(text, k))`. |
| `SELECT relationship, COUNT(*) FROM edges WHERE from_node IN (…) AND to_node IN (…)` | `port.edges_between(node_uuids)` — returns full `Edge` objects; aggregate client-side. |
| `SELECT MAX(valid_at), SUM(CASE WHEN invalid_at IS NOT NULL …) FROM edges` | `port.edges_between(node_uuids, as_of=..., include_invalidated=True)`; aggregate client-side. |
| Stage 0 `resolveEntities` call | **Delete entirely.** Native to `GraphitiAdapter` (4-tier resolution at ingest). |
| Stage 0.5 `invalidateEdges` call | **Delete entirely.** Native to Graphiti (bitemporal `invalid_at`). |

### 4. Persistence layer for L4 state

`threads`, `thread_members`, `thread_transitions`, `thread_edges`, `delivery_events` are L4 metadata, not L3 knowledge. They don't belong in Neo4j.

Right answer: **separate small SQLite or Postgres file owned by the L4 layer** (e.g. `~/.mikai/l4.db`). Keeps the L3 port pure; gives L4 cheap relational queries for bookkeeping.

### 5. Thread detection algorithm needs rethinking

The branch's `detect-threads.ts` does Union-Find over raw embedding distances (k=15 per item, threshold 0.72, cross-source/cross-layer bonuses). The Graphiti port doesn't expose raw vectors — `search()` returns ranked Edge results.

Two options:

- **(a)** Keep the algorithm; run it against a **parallel embedding store** owned by L4 (write each Episode's text into SQLite + sqlite-vec at ingest, alongside the Graphiti write).
- **(b)** Re-cast detection as **repeated `port.search_nodes()` queries** seeded by recently-active nodes.

---

## Four design decisions blocking porting

These should be settled before code starts:

1. **Language** — Python in sidecar (recommended) vs. TypeScript over HTTP.
2. **L4 state persistence** — separate SQLite (recommended) vs. Neo4j.
3. **Thread detection algorithm** — parallel sqlite-vec store (preserves Union-Find) vs. port-native `search_nodes()` expansion.
4. **Segmentation strategy in the Graphiti world** — one-episode-per-source-unit (current default) vs. resurrect FOUNDATIONS §4 segmentation framework.

---

## Effort estimate (three buckets)

| Bucket | Effort | Notes |
|---|---|---|
| Mechanical port — regex tables, rule-based classifier, intervention-timing gate, OmniActions CoT prompt, `delivery_events` schema, `progress.json` | 1–2 days | Pure copy-paste once language is picked. |
| Adapter shim layer — port-method wrappers for `edges_between`, `search`, `search_nodes`, plus client-side aggregation that used to be SQL `GROUP BY` / `MAX` / `SUM` | 2–3 days | Tedious but obvious. |
| Design decisions before code | Real thinking | This is the gating work. Without these, the porting flounders. |

---

## What FOUNDATIONS §3 says vs. what's true on the branch

- ✅ "Thread detection (kNN + Union-Find) with graph-enrichment post-step — done on the L4 prior build. Needs porting to `L3Backend`." Accurate.
- ✅ "State classification (rule-based + graph edge signals) — same." Accurate.
- ✅ "Evaluation gate (intervention timing) — same." Accurate (modulo terminology rename).
- ✅ "Structured next-step inference (OmniActions 7-category CoT, Haiku) — same." Accurate.
- ⚠️ "Evaluation suite (MEMTRACK methodology, 20–30 labeled threads) — next." `engine/eval/eval-l4.ts` + `l4-ground-truth.json` + `l4-threads-to-label.json` **already exist on the branch.** Not "next" — they're sitting there waiting to be ported too.
- ❌ O-036 hypothesis ("rule-based >80% accuracy"): **not yet measured.** The branch never ran the eval suite against ground-truth labels.

---

## Cross-references

- `engine/l4/*` on branch `feat/l4-testing` — the source material
- `infra/graphiti/sidecar/l3/port.py` on main — the port surface
- `docs/FOUNDATIONS.md §3` — L4 build spec
- `docs/STATUS.md` — current state of main
- `docs/research/strategic-research-2026-06.md` — broader strategic context
