<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-27 | Updated: 2026-03-28 -->

# l4

## Purpose
L4 Task-State Awareness — the differentiating product layer. Detects threads (topics tracked across apps), classifies their reasoning state, evaluates delivery timing, and infers actionable next steps. This is what makes MIKAI a product, not just infrastructure.

## Key Files
| File | Description | Paper basis |
|------|-------------|-------------|
| `types.ts` | All L4 types — Thread, ThreadState, GraphSignals, ActionCategory, DeliveryEvent, ClassificationSignals | OmniActions (ActionCategory), PPP (DeliveryEvent) |
| `schema.ts` | L4 database tables — threads (+ delivery columns), thread_members, thread_transitions, thread_edges, delivery_events | PPP (delivery_events) |
| `store.ts` | CRUD operations for all L4 entities + delivery event logging + PPP metrics | PPP (training signal collection) |
| `detect-threads.ts` | Thread detection via kNN + Union-Find clustering + graph enrichment post-step | Hybrid decision (embedding proximity + graph connectivity) |
| `graph-enrichment.ts` | Post-clustering L3 edge signal extraction — confidence boost + classification hints. **Graphiti abstraction boundary**: if L3 is swapped, only this file changes. | Graphiti-inspired (entity subgraph pattern) |
| `classify-state.ts` | Rule-based state classification (zero LLM) + graph edge type signals (contradicts→evaluating, depends_on→stalled) | Inner Thoughts stage 3 (thought formation) |
| `evaluate-delivery.ts` | Sumimasen gate — filters threads before inference. Rules: 48h cooldown, 7-30d stall window, recency, cross-source boost, cap 5/cycle. | ProMemAssist (UIST 2025) timing model |
| `infer-next-step.ts` | Claude Haiku next-step with OmniActions 7-category CoT (Search/Create/Capture/Share/Schedule/Navigate/Configure) | OmniActions (CHI 2024) action taxonomy |
| `run-l4-pipeline.ts` | 4-stage orchestrator: detect → classify → evaluate → infer. Logs delivery events. Writes `l4-progress.json`. | Inner Thoughts (CHI 2025) cognitive loop + Anthropic harness pattern |

## Pipeline (4-stage cognitive loop — Inner Thoughts CHI 2025)
```
Stage 1: TRIGGER + DETECTION  →  detect-threads.ts + graph-enrichment.ts
Stage 2: THOUGHT FORMATION    →  classify-state.ts (with graph edge signals)
Stage 3: EVALUATION           →  evaluate-delivery.ts (Sumimasen gate)
Stage 4: PARTICIPATION        →  infer-next-step.ts (only gated threads)
         + LOGGING            →  delivery_events table (PPP training signal)
```

## State Machine
```
exploring → evaluating → decided → acting → stalled → completed
                                              ↑          |
                                              └──────────┘ (re-activate)
```

## For AI Agents

### Working In This Directory
- Thread detection is ZERO LLM — uses pre-computed embeddings from L3
- Graph enrichment queries L3 edges between thread members — additive, degrades gracefully if graph is sparse
- State classification is ZERO LLM — rule-based heuristics + graph edge type signals
- Evaluation gate (Sumimasen) is ZERO LLM — rule-based V1, future V2 trains from delivery feedback
- Next-step inference is the ONE place L4 uses Claude (Haiku, ~200 tokens per thread, structured CoT)
- Delivery events log every surfaced next-step for PPP training signal collection
- `l4-progress.json` is written after each pipeline run (Anthropic harness pattern)
- All functions take `db: Database.Database` as first argument (same pattern as `lib/store-sqlite.ts`)
- Import from `./store.js` for CRUD, `./types.js` for types
- Cross-source signal is the key differentiator: same topic in Notes + Gmail = strong thread

### Swappable Components (paper → file)
Each component can be independently upgraded or replaced:
- **Timing model**: `evaluate-delivery.ts` — swap rule-based for trained model when delivery_events accumulate (ProMemAssist)
- **Action taxonomy**: `infer-next-step.ts` SYSTEM_PROMPT — expand from 7 to 17 categories (OmniActions)
- **Memory layer**: `graph-enrichment.ts` — swap L3 SQLite queries for Graphiti/Cognee API calls
- **Training loop**: `store.ts` PPP metrics — feed into multi-objective RL when data is sufficient (PPP/UserVille)

### Testing Requirements
- Run `npm run l4 -- --detect-only` to test detection in isolation
- Run `npm run l4 -- --skip-infer` to test detect + classify + gate without LLM cost
- Check `l4-progress.json` for pipeline run stats
- Check thread quality: do detected threads match real user topics?

### Common Patterns
- Functions are async even when not strictly needed (future-proofing for batched LLM calls)
- The Union-Find in detect-threads.ts is the core clustering algorithm
- Classification signals are extracted from content patterns (regex) + temporal patterns (activity gaps) + graph edge types
- `addColumnSafe()` in schema.ts handles idempotent migrations for existing databases

## Dependencies

### Internal
- `lib/store-sqlite.ts` — database init, L3 queries
- `engine/graph/` — segments and nodes that L4 clusters into threads
- `engine/l3/` — L3 edges consumed by graph-enrichment.ts
- `engine/inference/` — stall scoring patterns reused in L4 classification

### External
- `@anthropic-ai/sdk` — Claude Haiku for next-step inference only
- `better-sqlite3` — database operations
