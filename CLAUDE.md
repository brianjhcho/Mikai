# MIKAI — Claude Code Session Context

## What MIKAI is

MIKAI is a local-first intent intelligence engine. It ingests personal digital content, builds a structured knowledge graph with typed reasoning relationships, and exposes it to Claude Desktop via MCP. The product is the MCP server. The moat is the intention-behavior gap detection — cross-referencing what you said vs what you did.

---

## Read these files before writing any code

| Priority | File | Why |
|---|---|---|
| 1 | `docs/ARCHITECTURE.md` | Canonical architecture — pipeline, data model, retrieval, inference |
| 2 | `docs/DECISIONS.md` | All product decisions (D-001–D-039) and technical decisions (ARCH-001–ARCH-018) |
| 3 | `docs/OPEN_QUESTIONS.md` | Active tensions — do not paper over these with confident answers |
| 4 | `docs/EPISTEMIC_EDGE_VOCABULARY.md` | Node types, edge types, priority ordering, extraction quality standard |
| 5 | `surfaces/mcp/server.ts` | **THE product** — 8 MCP tools, graph retrieval, edge priority (do not reorder) |
| 6 | `lib/ingest-pipeline.ts` | Extraction prompt + `extractGraph()` — reasoning-map prompt, not taxonomy |
| 7 | `engine/graph/build-graph.js` | Graph extraction script and all its flags |

---

## North Star

**Path 2: Category Creation** — "The AI that knows what you're stuck on."

Create the "intent intelligence" category. Publish the framework. Build the open-source reference implementation. Attract reflective power users who recognize the gap between "what AI remembers" and "what AI infers."

**V1 product:** Local-first MCP server. Connect sources, build intent graph, every Claude conversation has your full cognitive context.

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
| **→** | **Path 2 launch: public repo, manifesto, 20 beta users** | **NOW** |
| 4 | Evaluation bridge: Tier 1 checks + BM25 + temporal edges | Next |
| 5 | Desire classification + trajectory modeling | Planned |
| 6 | Terminal desire inference + multi-surface delivery | Planned |
| 7 | Multi-user + memory passport | Planned |

**Strategic reference:** `docs/MEMORY_ARCHITECTURE_THESIS.md` for the three-layer model and tiered evaluation pipeline.

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
