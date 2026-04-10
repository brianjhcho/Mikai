# MIKAI — Claude Code Session Context

## What MIKAI is

MIKAI is a task-state awareness engine (noonchi). Two layers:
- **L3:** Knowledge graph with typed edges. The user's evolving understanding — must be accurate, current, and accessible from any surface.
- **L4:** Thread detection, state classification (exploring → decided → acting → stalled), next-step inference across apps. **THE PRODUCT.**

L4 is the product. But L4 is only as good as L3. If the graph doesn't accurately understand the user, task-state awareness fails (proven: 20% state classification accuracy traced to L3 quality).

---

## Two architectural constraints (override all other decisions)

### 1. L3 graph quality is the gating function for L4

L4 (task-state awareness) is the asset. But L3 must be correct first — L4 is only as good as the graph it sits on (proven: 20% state accuracy traced to L3 quality).

**The evolution of the L3 hypothesis:**
1. Pre-LLM: Identity/360 user profiles — structured data about the user from behavioral traces
2. LLM-assisted: Use LLMs to create nodes and synthesize graph structure from unstructured content → user profile indexed on relevant nodes
3. Competitor review: Compared Mem0, Zep/Graphiti, Cognee, Letta, Hindsight for their treatment of graphs and memory systems as L3 layers
4. **Landing: Graphiti** — best starting point. Happy medium of textual depth about the user AND computational speed/efficiency

**Current focus:** Validate L3 works correctly with Graphiti. Measure graph quality. Document the reasoning branches so that once L3 passes at an acceptable rate, we can connect it to L4 use cases.

Specific L3 quality requirements:
- **Entity summaries must evolve** — not frozen at extraction time
- **Entity resolution must be accurate** — LLM disambiguation for ambiguous cases
- **Edge invalidation must reflect changed beliefs** — superseded facts marked, not served as current
- **Community detection** — cluster related entities into themes

Graph accuracy must be measured before L4 work resumes. Target: >80% precision on "is this what the user actually thinks?"

### 2. Multi-surface access is unsolved — needs research, not implementation

MCP was chosen as the sole product surface because it was the **fastest path to testing and usability** (D-039). It is NOT the final answer for multi-surface access.

**What's unsolved:**
- Multi-surface access has real ecosystem constraints that aren't addressed by simply adding HTTP/SSE transport
- Apple Shortcuts is NOT the right integration path for MIKAI — it's too constrained
- Deeper research needed: How does Apple Intelligence currently operationalize user profiles? How can MIKAI integrate at the OS level rather than through Shortcuts?
- The question of "how does the user access their graph from mobile/web" requires platform-specific research, not premature infrastructure

**What's NOT decided:**
- Cloud vs local deployment model for mobile/web
- Transport protocol for non-desktop surfaces
- Authentication model
- Whether MCP is even the right protocol for all surfaces (vs REST API, native SDK, etc.)

**Research needed before building:**
- Apple Intelligence user profile architecture — how it works, where MIKAI could integrate
- Claude mobile/web MCP support — current capabilities and roadmap
- Alternative integration patterns (widgets, notifications, OS-level hooks)

Do not build multi-surface infrastructure until the research answers these questions.

---

## Context routing (read what's relevant, not everything)

| Session type | Read first |
|---|---|
| **Writing code** | `docs/ARCHITECTURE.md`, `surfaces/mcp/server.ts`, relevant source files |
| **L3 / Graphiti work** | `docs/GRAPHITI_INTEGRATION.md`, `infra/graphiti/AGENTS.md`, `infra/graphiti/sidecar/main.py` |
| **L4 build work** | `docs/L4_RESEARCH_INTEGRATION.md`, `engine/l4/AGENTS.md`, relevant L4 source files |
| **Strategy / positioning** | `private/strategy/01_CORE_ENGINE.md`, `private/strategy/02_EXECUTION_STRATEGY.md` |
| **Competitive analysis** | `private/strategy/reference/COMPETITIVE_LANDSCAPE.md` |
| **Current status / planning** | `private/strategy/03_WORKING_STATE.md` |
| **Extraction prompt work** | `lib/ingest-pipeline.ts`, `docs/EPISTEMIC_EDGE_VOCABULARY.md` |
| **Decisions / open questions** | `docs/DECISIONS.md`, `docs/OPEN_QUESTIONS.md` |

---

## North Star

**Noonchi — "The AI that knows where you are and what to do next."**

Not a memory system. A task-state awareness engine. The product is knowing that you were researching flight options and haven't booked yet, that your article draft stopped mid-paragraph on the trust section, that you told Sarah you'd send the proposal by Friday and it's Thursday.

**V1 product (wedge):** Cross-app memory for Claude via MCP. "Claude remembers everything across your apps." The graph and tensions are differentiating features within this framing. Target: 20 beta users, 5+ who'd pay.

**V2 product (noonchi):** Thread-state tracking, reasoning-stage classification, next-step inference. The thing nobody else is building.

**V1 success metric:** 20 beta users, 5+ who say "I would pay for this."

---

## Pipeline — three stages, always run in sequence

```
# Stage 1: Ingest (no LLM, fast)
npm run sync:notes       # Apple Notes (direct osascript)
npm run sync:local       # Markdown, Claude exports, Perplexity
npm run sync:imessage    # iMessage (requires Full Disk Access)
npm run sync:gmail       # Gmail (requires GMAIL_* in .env.local)
npm run sync:all         # All sources in sequence

# Stage 2: Extract graph
npm run build-graph      # Track A (Claude) + Track B (rule engine)
npm run build-segments   # Track C (zero-LLM segmentation)

# Stage 3: Score nodes
npm run run-rule-engine  # Stall probability scoring (no LLM)
```

After every ingest, always run `build-graph`, `build-segments`, then `run-rule-engine`.

Or run the full pipeline: `npm run scheduler:run`

---

## Settled decisions — do not relitigate

| Decision | What was decided |
|---|---|
| ARCH-001 | Supabase only — no separate vector DB |
| ARCH-013 | Claude Haiku for extraction; Voyage AI voyage-3 for embeddings |
| ARCH-014 | Ingestion and extraction are decoupled — never merge them |
| ARCH-015 | Graph traversal: 5 seeds → 1-hop edge expansion → cap 15 nodes |
| ARCH-016 | Embeddings at node level, not chunk level |
| ARCH-017 | Fixed taxonomy — see `docs/EPISTEMIC_EDGE_VOCABULARY.md` |
| ARCH-018 | Stay on Supabase (PuppyGraph experiment: marginal gain at current scale) |
| D-026 | LLM reserved for 3 roles: Track A extraction, terminal desire synthesis, NLG delivery |
| D-027 | Source type determines extraction tool. Never apply LLM to behavioral traces. |
| D-038 | Three-tier memory: L1 brief, L2 segments, L3 graph |
| D-039 | MCP server is sole product surface. Next.js removed. All ingestion via `ingest-direct.ts`. |

---

## Active tensions — do not resolve unilaterally

- **D-016:** No monetization model compatible with "trust over engagement" has been defined.
- **O-012:** Passive capture and the trust cliff are in direct proportion — structural, not engineering.
- **O-015:** Single-player compounding has no organic discovery mechanism.
- **O-025:** Does the extraction prompt generalize beyond Brian's writing style?

---

## Extraction prompt quality standard

The prompt in `lib/ingest-pipeline.ts` is a reasoning-map prompt, not a taxonomy prompt. Do not simplify or revert it. A valid extraction must produce:

- At least 2 `tension` or `question` nodes out of 5–7 total
- First-person `content` fields ("I've concluded..." not "The author believes...")
- Typed edges with a `note` field explaining the specific relationship
- Revision events when a source shows belief updating

Full specification: `docs/EPISTEMIC_EDGE_VOCABULARY.md`

---

## Edge priority ordering — intentional, do not reorder

```
unresolved_tension → 0   ← internal conflict actively held
contradicts        → 1   ← structural contradiction
depends_on         → 2
partially_answers  → 3
supports           → 4
extends            → 5
```

Reordering silently breaks the retrieval contract even if the code runs correctly.

---

## Build plan (phases)

| Phase | What | Status |
|-------|------|--------|
| 0 | Architecture cleanup | DONE (2026-03-14) |
| 1 | Prove semantic engine | DONE — accuracy 4.0, non-obviousness 3.6 |
| 1.5 | PuppyGraph experiment | DONE — stay on Supabase (ARCH-018) |
| 2 | MCP source integrations | DONE — iMessage + Gmail + Track B |
| 3 | Track C + MCP Server | DONE — 8 tools, Claude Desktop connected |
| 3.5 | Trust barrier | DONE — pipeline automation, 25,749 segments |
| **→** | **V1 launch: "Cross-app memory for Claude" — public repo, 20 beta users** | **NOW** |
| 4A | Thread detection + state classification + graph enrichment | DONE (2026-03-28) — detect-threads, classify-state, graph-enrichment |
| 4B | Evaluation gate (Sumimasen) + structured inference (OmniActions) | DONE (2026-03-28) — evaluate-delivery, infer-next-step rewrite |
| 4C | Delivery event logging (PPP training signal) + progress file | DONE (2026-03-28) — delivery_events table, l4-progress.json |
| L3-2 | Entity resolution | DONE (2026-03-29) — hybrid search (vec kNN + BM25 + RRF), 1,072 cross-source edges, cross-app threads 4→16 |
| Seg | Segmentation fix | DONE (2026-03-29) — source-adaptive splitting (Gmail/Apple Note/iMessage), per-source thresholds |
| 4D | L4 eval suite (MEMTRACK-inspired) | DONE (2026-03-29) — 27 ground truth, detection 100% F1, state 22% (pre-narrowing) |
| L3-3 | Edge invalidation (Graphiti Phase 3) | DONE (2026-03-29) — 48 edges invalidated (34 contradiction + 14 supersession) |
| 4E | L4 multi-view + configurable state machine | PAUSED — blocked on L3 quality gate |
| **G1** | **Graphiti + Neo4j as L3 backend** | **DONE (2026-04-07)** — DeepSeek + Voyage, 6,990 entities, 8,056 edges |
| **G2** | **Apple Notes import (1,102 episodes)** | **DONE (2026-04-08)** — sequential `add_episode()`, full graph maturation |
| **G3** | **MCP server v2.0 (9 tools, Graphiti-consistent)** | **DONE (2026-04-02)** — hybrid search, edge invalidation, temporal queries |
| **G4** | **Embedding comparison (Voyage vs Nomic)** | **DONE (2026-04-07)** — dual embeddings on all entities |
| **→** | **Claude thread import (562 remaining, turn-by-turn with saga)** | **NEXT** — ~$4.50 on DeepSeek |
| → | Perplexity import (583 episodes, query+answer with saga) | NEXT — ~$3.50 on DeepSeek |
| → | Community detection (connect orphan entities) | NEXT — 1,233 orphans (17.6%) need clustering |
| → | Orphan cleanup (prune noise entities) | NEXT |
| → | L3Backend interface (TypeScript abstraction for MCP↔Graphiti) | Planned |
| 5 | L4 re-eval against Graphiti graph (target >50% state accuracy) | Planned — blocked on L3 completion |
| 6 | Trajectory modeling + desire classification | Planned (the noonchi moment) |
| 7 | Intention-behavior gap + proactive delivery | Planned |

**Graphiti integration details:** `docs/GRAPHITI_INTEGRATION.md` (scaling issues, patches, cost analysis, entity resolution pipeline)
**Current detailed status:** `private/strategy/03_WORKING_STATE.md`
**Strategic reference:** `private/strategy/01_CORE_ENGINE.md` (L3/L4 definition), `private/strategy/02_EXECUTION_STRATEGY.md` (V1/V2/V3 plan)

---

## After every build task

Provide two explanations:

**1) WHAT WAS BUILT** — technical summary for git commit. Files changed, what the code does, why.

**2) WHAT THIS MEANS** — plain English for Brian. What changed, what problem it solves, how it connects. No jargon.

---

## Do not overbuild

- Simplify architecture. Think MVP.
- Always explain tradeoffs of a decision in both product and architecture terms.
- Don't add features, refactor code, or make "improvements" beyond what was asked.
- Only build what's needed for the current phase.

---

## L3 Upgrade — Graphiti-inspired (Phase 1 of 3)

Bitemporal edges, BM25 fulltext search, and hybrid retrieval with RRF. Runs on top of the existing L3 knowledge graph schema.

### Bitemporal Edge Fields
New columns added to the `edges` table (idempotent migration):
- `valid_at` — when the fact became true (backfilled from source node's `created_at`)
- `invalid_at` — when the fact stopped being true (Phase 3: edge invalidation)
- `expired_at` — soft-delete marker for superseded edges
- `episodes` — JSON array of `source_id`s that established this edge
- `fact` — normalized natural-language statement of the edge relationship

### BM25 via FTS5
Three FTS5 virtual tables (contentless, external-content mode):
- `fts_nodes` — indexes `label`, `content`
- `fts_segments` — indexes `topic_label`, `processed_content`
- `fts_edges` — indexes `relationship`, `note`, `fact`

Run `npm run l3:sync-fts` after bulk data changes to rebuild indices.

### Hybrid Search with RRF
`hybridGraphSearch()` in `engine/l3/hybrid-search.ts`:
1. Vector search (sqlite-vec) + BM25 (FTS5) on nodes
2. Merge via Reciprocal Rank Fusion (k=1, matching Graphiti default)
3. Top 5 seeds → BFS 1-hop expansion → cap 15 nodes

### Commands
```
npm run l3:upgrade        # Full upgrade: migrate + sync FTS
npm run l3:upgrade -- --migrate-only   # Bitemporal migration only
npm run l3:sync-fts       # Rebuild FTS5 indices only
npm run l3:resolve        # Cross-source entity resolution
npm run l3:resolve:force  # Re-resolve all nodes
npm run l3:upgrade -- --resolve   # migrate + sync FTS + entity resolution
```

### Phase Roadmap
- **Phase 1 (DONE):** Bitemporal columns + BM25 FTS5 + hybrid search with RRF
- **Phase 2 (DONE 2026-03-29):** Entity resolution — hybrid search (vec kNN + BM25 + RRF), 1,072 cross-source edges created, cross-app threads 4→16
- **Phase 2B (DEFERRED):** Community detection (Graphiti label propagation). Deferred — graph too sparse. See O-040.
- **Phase 3 (DONE 2026-03-29):** Edge invalidation — 48 edges invalidated (34 contradiction + 14 supersession). Sets `invalid_at` on superseded facts.

### Architecture
- `engine/l3/types.ts` — BiTemporalEdge, SearchResult, HybridSearchConfig
- `engine/l3/migrate-bitemporal.ts` — Idempotent schema migration
- `engine/l3/sync-fts.ts` — FTS5 index rebuild
- `engine/l3/hybrid-search.ts` — Vector + BM25 + RRF + BFS
- `engine/l3/entity-resolution.ts` — Cross-source entity deduplication
- `engine/l3/run-l3-upgrade.ts` — CLI orchestrator (migrate + FTS + optional resolve)
- `engine/l3/run-entity-resolution.ts` — Standalone entity resolution CLI

---

## L4 — Task-State Awareness

The L4 layer sits on top of L3's universal knowledge graph. L3 stores everything. L4 provides **domain-specific views** with pluggable state machines. See `docs/ARCHITECTURE.md` for the full multi-view design.

**Current: View A (Project Tracker)** — tracks active work with goals and endpoints. State machine: exploring → evaluating → decided → acting → stalled → completed. Thread detection anchored by `project`/`decision` nodes.

**Planned: View B (Belief Tracker)**, **View C (Event Log)** — different state models for beliefs and transactions.

### Pipeline (6-stage)
```
npm run l4              # Full pipeline: resolve → invalidate → detect → classify → evaluate → infer
npm run l4:detect       # Thread detection only (zero LLM)
npm run l4:classify     # State classification only (zero LLM)
npm run l4:infer        # Re-run next-step inference (Haiku)
npm run l4:no-llm       # Detect + classify without inference
```

Stage 0: entity resolution. Stage 0.5: edge invalidation (Phase 3). Both feed temporal signals into thread detection and state classification.

### Architecture
| File | Purpose | Paper basis |
|------|---------|-------------|
| `engine/l4/types.ts` | All L4 types — Thread, GraphSignals, ActionCategory, DeliveryEvent, ClassificationSignals | OmniActions (ActionCategory), PPP (DeliveryEvent) |
| `engine/l4/schema.ts` | DB tables — threads (+ delivery columns), thread_members, thread_transitions, thread_edges, delivery_events | PPP (delivery_events table) |
| `engine/l4/store.ts` | CRUD + delivery event logging + PPP metrics | PPP (insertDeliveryEvent, recordDeliveryResponse, getPPPMetrics) |
| `engine/l4/detect-threads.ts` | kNN + Union-Find clustering + graph enrichment post-step | Hybrid decision (§Critical Architecture Decision in L4_RESEARCH_INTEGRATION.md) |
| `engine/l4/graph-enrichment.ts` | L3 edge signals between thread members → confidence boost + classification hints | Graphiti-inspired (temporal entity subgraph pattern) |
| `engine/l4/classify-state.ts` | Rule-based state machine + graph edge type signals (contradicts → evaluating, depends_on unresolved → stalled) | Inner Thoughts stage 3 (thought formation) |
| `engine/l4/evaluate-delivery.ts` | Sumimasen gate — filters threads before inference (cooldown, stall window, recency, cross-source boost, cap 5/cycle) | ProMemAssist (UIST 2025) timing model, Inner Thoughts stage 4 (evaluation) |
| `engine/l4/infer-next-step.ts` | Haiku next-step with OmniActions 7-category CoT: Search/Create/Capture/Share/Schedule/Navigate/Configure | OmniActions (CHI 2024) structured action taxonomy |
| `engine/l4/run-l4-pipeline.ts` | 4-stage orchestrator: detect → classify → evaluate → infer. Logs delivery events. Writes `l4-progress.json`. | Inner Thoughts (CHI 2025) 5-stage loop, Anthropic harness pattern (progress file) |

### State Machine
exploring → evaluating → decided → acting → stalled → completed

### MCP Server v2.0 (9 tools, local-first, Graphiti-consistent)

| Tool | What it does |
|------|-------------|
| `search` | Hybrid retrieval (vec + BM25 + RRF) over segments + graph. Single primary tool. |
| `get_brief` | L4-aware context brief: thread summary, valid tensions, stalled threads |
| `get_tensions` | Active tensions, valid edges only (invalid_at filtered), with thread context |
| `get_threads` | Thread-level view with state filter (replaces old node-level get_stalled) |
| `get_thread_detail` | Deep view: state history, members, related threads |
| `get_next_steps` | Noonchi surface: prioritized next steps across threads |
| `get_history` | Temporal query: graph state at a point in time, thought evolution |
| `add_note` | Save insight from conversation (local embeddings, immediately searchable) |
| `mark_resolved` | Resolve node or thread, propagates to containing threads |

Removed in v2.0: `search_knowledge`, `search_graph` (merged into `search`), `get_stalled` (replaced by `get_threads` with state filter), `get_status` (folded into `get_brief`). All Supabase code removed — local SQLite only.

### Key Design Decisions
- Thread detection is zero LLM — uses pre-computed segment embeddings
- Thread detection uses HYBRID approach: embedding proximity for clustering (memory-agnostic) + graph edge signals for enrichment (quality boost). See `docs/L4_RESEARCH_INTEGRATION.md` §Critical Architecture Decision.
- State classification is zero LLM — rule-based heuristics + L3 graph edge type signals (contradiction edges → evaluating, dependency chains → stalled)
- Evaluation gate (Sumimasen, from **ProMemAssist**) sits between classification and inference — not every thread gets surfaced. V1 is rule-based; V2 trains from dismiss/act feedback.
- Next-step inference is the ONE LLM call (Haiku, ~200 tokens/thread) using structured 7-category action taxonomy from **OmniActions** (CHI 2024)
- Delivery events are logged after every inference for future **PPP** (CMU 2025) multi-objective training (productivity × proactivity × personalization)
- `l4-progress.json` written after each run following **Anthropic's harness pattern** for long-running agent state persistence
- Cross-source signal is the key differentiator
- `graph-enrichment.ts` is the **Graphiti abstraction boundary** — if L3 is swapped for Graphiti/Cognee, only this file changes

### Research Foundation (paper → component mapping)
Full build spec with V1/V2+ scope per paper: `docs/L4_RESEARCH_INTEGRATION.md`

| Paper | Venue | What it provides | L4 component | Status |
|-------|-------|-----------------|--------------|--------|
| **ProMemAssist** | UIST 2025, arXiv:2507.21378 | Working memory timing model | `evaluate-delivery.ts` (Sumimasen gate) | V1 built (rule-based) |
| **OmniActions** | CHI 2024, arXiv:2405.03901 | 7-category structured action taxonomy | `infer-next-step.ts` (CoT prompt + ActionCategory) | V1 built |
| **Inner Thoughts** | CHI 2025, arXiv:2501.00383 | 5-stage proactive cognitive loop | `run-l4-pipeline.ts` (detect→classify→evaluate→infer) | V1 built |
| **PPP / UserVille** | CMU Nov 2025, arXiv:2511.02208 | Multi-objective training signal | `delivery_events` table + `store.ts` PPP metrics | V1 built (data collection) |
| **MEMTRACK** | NeurIPS 2025, arXiv:2510.01353 | Cross-platform state tracking eval | `engine/eval/eval-l4.ts` | Not yet built |
| **Anthropic Harness** | anthropic.com/engineering | Session state persistence | `l4-progress.json` output | V1 built |

### What's deferred (V2+, DO NOT BUILD NOW)
- ProMemAssist: real-time cognitive load modeling (needs activity stream)
- OmniActions: multimodal input, top-3 prediction, full 17-category taxonomy
- Inner Thoughts: continuous parallel thought generation (needs event-driven arch)
- PPP: multi-objective RL training loop (needs hundreds of delivery events per user)
- MEMTRACK: full simulation benchmark with synthetic events
