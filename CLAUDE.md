# MIKAI — Claude Code Session Context

## What MIKAI is

MIKAI is an intent extraction and cognitive profiling engine that ingests streams of personal digital behavior and produces a structured personal knowledge graph — nodes (concepts, decisions, tensions, questions) connected by typed edges (supports, contradicts, unresolved_tension, etc.). It is not a product; it is the engine that powers products. Which surface to build first is a strategic decision that follows from engine quality, not the other way around.

---

## Read these files before writing any code

| Priority | File | Why |
|---|---|---|
| 1 | `02_ARCHITECTURE_STACK.md` | Canonical architecture, all settled technical decisions, pipeline design, retrieval layer, taxonomy |
| 2 | `04_DECISION_LOG.md` | All product decisions (D-001–D-017) and technical decisions (ARCH-001–ARCH-017) |
| 3 | `03_PRD_CURRENT.md` | Build status table — what's live, what's pending, what's out of scope |
| 4 | `05_OPEN_QUESTIONS.md` | Active tensions — do not paper over these with confident answers |
| 5 | `surfaces/mcp/server.ts` | **THE product** — MCP server with 8 tools, graph retrieval, edge priority ordering (do not reorder) |
| 6 | `lib/ingest-pipeline.ts` | Extraction prompt + `extractGraph()` — reasoning-map prompt, not taxonomy prompt |
| 7 | `engine/graph/build-graph.js` | Graph extraction script and all its flags |
| 8 | `engine/ingestion/ingest-direct.ts` | Standalone ingestion — writes directly to Supabase, no web server |

---

## North Star

MIKAI is an inference model that detects stalled desires from the digital ecosystem and surfaces them through WhatsApp (V1) → Siri (final destination). It works like a persistent assistant messaging you, managing your life proactively. The inference model — not the capture mechanism — is the competitive moat.

**V1 use case:** Detect stalled immediate desires (the table to buy, the appointment to book, the trip to plan) from sources via MCP. Surface them through WhatsApp before the user remembers to act. Validate that the model predicts behavior (surfaced it before user would have done it anyway) and drives behavior change (user acts because of the prompt).

**Final form:** OS-level assistant layer integrated with Siri. Infers immediate, instrumental, and terminal desires from the full digital ecosystem. Knows what you want before you articulate it.

---

## Current phase

**Phase 1: Prove the semantic engine.** The goal is to confirm that the extraction and profiling engine produces output that is accurate and valuable from manual input — before building MCP integrations, the structural extraction track, or the WhatsApp delivery layer.

Phase 1 is complete when: the intent graph contains enough signal that a query like "what tensions am I holding about MIKAI?" returns a grounded, non-hallucinated answer that Brian recognizes as accurate and non-obvious.

**Phase 1 is not complete yet.** The remaining blocker is the evaluation protocol (O-020): there is no methodology for measuring whether extraction is good. All Phase 2+ work is hard-blocked on this.

---

## Pipeline — three stages, always run in sequence

```
# Stage 1: Ingest (no LLM, fast)
npm run sync             # Apple Notes
npm run sync:local       # Markdown, Claude exports, Perplexity
npm run sync:imessage    # iMessage (requires Full Disk Access)
npm run sync:gmail       # Gmail (requires GMAIL_* in .env.local)
npm run sync:all         # All four sources in sequence

# Stage 2: Extract graph (Claude + Voyage AI for Track A; rule engine for Track B)
npm run build-graph
# Track A (authored content): Claude extractGraph() → Voyage embeddings
# Track B (behavioral traces: imessage, gmail): action-verb scan → stall_probability = 0.6

# Useful build-graph flags
--rebuild                # Delete all nodes and re-extract everything
--source-id <uuid>       # One source only (bypasses chunk_count filter)
--dry-run                # Show what would run, no API calls
--preview                # Run Claude extraction, print JSON, no DB writes

# Stage 3: Score nodes (rule engine, no LLM, fast)
npm run run-rule-engine
# Applies scoreNode() to all nodes, writes stall_probability back to DB
# Run after every build-graph pass
```

After every ingest, always run `build-graph` then `run-rule-engine`. These are not one command.

---

## Settled decisions — do not relitigate

| Decision | What was decided |
|---|---|
| ARCH-001 | Supabase only — no separate vector DB (Pinecone, Chroma, Weaviate) |
| ARCH-002/013 | Claude Sonnet 4.6 for extraction + synthesis; Voyage AI `voyage-3` (1024-dim) for embeddings |
| ARCH-004 | **SUPERSEDED by D-039** — Next.js removed. MCP server (`surfaces/mcp/server.ts`) is the sole product surface. All ingestion via `ingest-direct.ts`. |
| ARCH-005 | No authentication in Phase 1 |
| ARCH-006 | TypeScript throughout — no plain JavaScript |
| ARCH-014 | Ingestion (batch API) and graph extraction (build-graph script) are decoupled — never merge them |
| ARCH-015 | Graph traversal retrieval: 5 vector seeds → one-hop edge expansion → cap 15 nodes |
| ARCH-016 | Embeddings at node level (extracted reasoning units), not chunk level |
| ARCH-017 | Node types: `concept \| project \| question \| decision \| tension`. Edge types: `supports \| contradicts \| extends \| depends_on \| unresolved_tension \| partially_answers`. Every edge has a `note TEXT` field. |
| D-001 | MIKAI is the engine. Surface selection follows engine validation. |
| D-007 | Mode B (Grounded Synthesis) is the default chat mode |
| D-008 | Surface progression: Local UI → WhatsApp → Vercel → Siri |
| D-009 | Mode C (Gap Detection) is deferred to Phase 2 |
| D-015 | Context injection into existing LLM sessions is the strongest near-term wedge |
| D-026 | LLM reserved for 3 roles only: Track A extraction, terminal desire synthesis, NLG for delivery. Everything else is ML infrastructure (feature computation → rule engine → classifier) |
| D-027 | Source type determines extraction tool: authored content → LLM Track A; behavioral traces → rule engine Track B. Never apply LLM reasoning-map prompt to behavioral traces |
| D-028 | Graphiti + FalkorDB spike before Phase 2 MCP integrations begin. Decision to migrate or stay on Supabase made with evidence at Phase 1→2 boundary |

---

## Active tensions — do not resolve unilaterally

- **O-018 + hard constraint:** Surface work is blocked on engine validation. WhatsApp and any agent-facing surface cannot begin until O-020 (evaluation protocol) is resolved. An agent fed a weak graph produces confidently wrong outputs.
- **D-016:** No monetization model compatible with "trust over engagement" has been defined. This is a blocking strategic question, not a Phase 3 problem.
- **O-012:** Passive capture and the trust cliff are in direct proportion — this is structural, not an engineering problem.
- **O-015:** Single-player compounding has no organic discovery mechanism. The distribution problem is unsolved.
- **O-019:** Documented Supabase schema does not match the live schema. Reconcile before the next schema migration.

---

## After every build task

Provide two explanations when any code or infrastructure change is complete:

**1) WHAT WAS BUILT** — a technical summary suitable for the git commit message. What files changed, what the code does, why it was structured this way.

**2) WHAT THIS MEANS** — a plain English explanation assuming no coding background. What changed from Brian's perspective, what problem it solves, and how it connects to MIKAI's architecture. No jargon. If a non-technical person couldn't understand it, rewrite it.

---

## Extraction prompt quality standard

The extraction prompt in `lib/ingest-pipeline.ts` is a reasoning-map prompt, not a taxonomy prompt. Do not simplify or revert it. A valid extraction must produce:

- At least 2 `tension` or `question` nodes out of 5–7 total (if every node is a `concept` or `decision`, extraction has drifted to summarization)
- First-person `content` fields ("I've concluded..." not "The author believes...")
- Typed edges with a `note` field explaining the specific relationship
- Revision events when a source shows belief updating

---

## Edge priority ordering — intentional, do not reorder

```
unresolved_tension → 0   ← internal conflict Brian is actively holding
contradicts        → 1   ← structural contradiction between nodes
depends_on         → 2
partially_answers  → 3
supports           → 4
extends            → 5
```

The chat system prompt instructs Claude to surface tensions rather than paper over them. This ordering ensures the subgraph fed to Claude is biased toward unresolved thinking. Reordering silently breaks the retrieval contract even if the code runs correctly.

---

## Build plan (phases)

| Phase | What | Gate |
|-------|------|------|
| 0 | Architecture cleanup: remove iPad Brief (D-023), delete brief endpoints, update docs | ✓ DONE (2026-03-14) |
| 1 | Prove semantic engine: resolve O-020, validate extraction quality on existing corpus | ✓ DONE (2026-03-14) — avg accuracy 4.0, avg non-obviousness 3.6, PASS |
| 1.5 | PuppyGraph experiment: add PuppyGraph on top of existing Supabase Postgres (zero migration), test whether typed edge traversal produces meaningfully different recall vs. vector search alone | ✓ DONE (2026-03-15) — avg tension delta +1.2 across 5 queries (gate was ≥2). STAY on Supabase. See ARCH-018. |
| 2 | MCP source integrations: iMessage + Gmail connectors live; Track B rule engine routing in build-graph.js; daily sync scheduler | ✓ DONE (2026-03-15) — 1283 Track B nodes with stall_probability > 0.5 from Gmail behavioral traces. iMessage pending Full Disk Access. |
| 3 | Track C + MCP Server + Source Capture | ✓ DONE (2026-03-19) — 969 segments, MCP server live with 4 tools, Claude Desktop connected, Perplexity export built |
| 3.5 | Trust Barrier: Automatic capture + pipeline automation | ✓ MOSTLY DONE (2026-03-22) — P1-P6 complete, P7 deferred. 8 MCP tools. 25,749 segments. Brief routing PASS. |
| 4 | Evaluation Bridge + Infrastructure: Tier 1 checks (recurrence, contradiction, stall resolution) + BM25 retrieval + temporal edges + proactive surfacing via Cowork | Tier 1 detects recurring patterns without false positives. BM25 improves recall by 10%+. |
| 5 | Desire Classification + Trajectory: desire_level on nodes (immediate/instrumental/terminal), trajectory modeling (acceleration/decay), dismiss/act feedback loop | Instrumental desires classified with evidence edges. Dismiss rate <30% on surfaced items. |
| 6 | Terminal Desire Inference + Multi-Surface Delivery: Claude synthesis across trajectories, WhatsApp for immediate desires, Cowork/email for instrumental, Claude Desktop for terminal | Terminal desires inferred from instrumental trajectory. Multi-surface routing functional. |
| 7 | Multi-User + Memory Passport: user_id on all tables, JSONL export, beta validation with 5 users | Extraction generalizes beyond Brian (O-025). 5 users querying via MCP. |

**Deferred:** Siri integration · LoRA personalization · browser passive capture (P7) · cross-encoder reranking · spreading activation beyond 1-hop

**Strategic reference:** See `09_MEMORY_ARCHITECTURE_THESIS.md` for the three-layer model (interface → infrastructure → intention-behavior gap detection) and tiered evaluation pipeline (Tier 0-3).

## What's next (in priority order)

1. **PHASE 3 COMPLETE (2026-03-19):** Track C condensed synthesis (969 segments across 2,171 sources), MCP server with 4 tools connected to Claude Desktop, Perplexity bulk export tool built, extraction logging and model routing implemented.

2. **PHASE 3.5: TRUST BARRIER (next)** — The system must work when Brian forgets about it. Eight priorities:
   - **P1: Decouple ingest from Next.js dev server** — ✅ DONE (D-039). Next.js removed entirely. All syncs use `ingest-direct.ts` (standalone Supabase writes). No web server dependency.
   - **P2: Add build-segments + all syncs to daily-sync.sh** — segments powering MCP go stale without this. (30 min)
   - **P3: Increase sync frequency to every 30 min** — 16-hour latency breaks trust. Change launchd from daily to interval. (1 hour)
   - **P4: Claude Code session watcher** — monitor ~/.claude/ for new sessions, auto-ingest. (1-2 days)
   - **P5: Apple Notes via osascript** — direct read without HTML export step. (2-3 days)
   - **P6: get_status MCP tool** — "Last sync: 12 min ago. 2,171 sources. No failures." Trust requires verifiability. (half day)
   - **P7: Chrome extension for Claude.ai + Perplexity capture** — closes browser LLM gap. (1-2 weeks)
   - **P8: Full pipeline orchestrator** — one command runs all syncs + graph + segments with error reporting. (half day)

3. **Trust test:** Write a note at 3pm. Have a Claude conversation at 4pm. At 9pm ask "what was I thinking about today?" If the answer includes both, Phase 3.5 is complete.

4. **MIKAI Brief (L1 context injection):** `get_brief` MCP tool returns a ~400 token knowledge base snapshot (tensions, stalled items, projects, stats) injected at conversation start. Makes Claude aware of the graph without calling depth tools. Test protocol: `engine/eval/eval-brief-routing.md`.

5. **Architecture gap closure (08_ARCHITECTURE_GAPS.md):** 7 gaps identified. P0: write tools (mark_resolved, add_note) + documentation audit. P1: BM25 retrieval, conflict resolution, temporal edges, epistemic edge scoring, user_id columns. See D-036 for features adopted from Mem0/Hindsight/Zep/Letta.
