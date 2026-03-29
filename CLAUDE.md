# MIKAI — Claude Code Session Context

## What MIKAI is

MIKAI is a task-state awareness engine (noonchi). Two layers:
- **L3 (built, commodity):** Knowledge graph with typed edges. Memory infrastructure. Adoptable from OSS if needed.
- **L4 (unbuilt, differentiator):** Thread detection, state classification (exploring → decided → acting → stalled), next-step inference across apps. **THE PRODUCT.**

Memory is commodity. Task-state awareness is the product.

---

## Context routing (read what's relevant, not everything)

| Session type | Read first |
|---|---|
| **Writing code** | `docs/ARCHITECTURE.md`, `surfaces/mcp/server.ts`, relevant source files |
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
| 4D | L4 eval suite (MEMTRACK-inspired) | Next — manually label 20-30 threads, measure accuracy |
| 5 | Trajectory modeling + desire classification | Planned (the noonchi moment) |
| 6 | Intention-behavior gap + proactive delivery (multi-surface) | Planned |
| 7 | Multi-user + memory passport + evaluate replacing memory layer with OSS | Planned |

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
- **Phase 2 (DONE):** Entity resolution — deduplicate nodes across sources
- **Phase 3:** Edge invalidation — mark contradicted/superseded facts as expired

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

The L4 layer sits on top of L3's knowledge graph. It is the actual product — what differentiates MIKAI.

### Pipeline (4-stage, Inner Thoughts cognitive loop)
```
npm run l4              # Full pipeline: detect → classify → evaluate → infer
npm run l4:detect       # Thread detection only (zero LLM)
npm run l4:classify     # State classification only (zero LLM)
npm run l4:infer        # Re-run next-step inference (Haiku)
npm run l4:no-llm       # Detect + classify without inference
```

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

### MCP Tools (L4)
- `get_threads` — List active threads with states
- `get_thread_detail` — Deep view of one thread
- `get_next_steps` — The noonchi surface: what to do next

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
