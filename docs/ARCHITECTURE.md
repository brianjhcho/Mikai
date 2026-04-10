# MIKAI Architecture & Technical Stack

*Last updated: 2026-03-24 (D-039: Next.js removed, MCP server is sole surface)*

---

## System Overview

MIKAI is a local-first intent intelligence engine. It ingests personal digital content, extracts a structured knowledge graph with typed reasoning relationships, and exposes it to Claude Desktop via MCP.

```
Sources (Apple Notes, files, Gmail, iMessage)
    │
    ▼
Ingestion (zero LLM — chunking + storage)
    │
    ▼
Extraction
├── Track A: Claude Haiku → reasoning map (authored content)
├── Track B: Rule engine → action patterns (behavioral traces)
└── Track C: Smart split → searchable segments (all content)
    │
    ▼
Supabase (Postgres + pgvector)
├── sources    — raw content
├── nodes      — extracted reasoning units with embeddings
├── edges      — typed reasoning relationships
└── segments   — condensed passages for fast search
    │
    ▼
MCP Server (8 tools → Claude Desktop)
```

---

## Implementation Stack

| Component | Technology | Role |
|-----------|------------|------|
| LLM (extraction) | Claude Haiku (`claude-haiku-4-5-20251001`) | Track A reasoning-map extraction |
| LLM (synthesis) | Claude Sonnet 4.6 | Terminal desire synthesis (future) |
| Embeddings | Voyage AI `voyage-3` (1024-dim) | Node + segment embeddings |
| Database | Supabase (Postgres + pgvector) | All storage, vector search, graph traversal |
| MCP Server | `@modelcontextprotocol/sdk` (stdio) | Product surface — 8 tools for Claude Desktop |
| Scheduler | macOS launchd | Automated 30-min sync pipeline |
| Runtime | Node.js + tsx | All scripts and server |

---

## Data Model (Supabase / Postgres)

```sql
CREATE TABLE sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type TEXT NOT NULL,           -- 'llm_thread' | 'note' | 'voice' | 'web_clip' | 'document'
  label TEXT,
  raw_content TEXT NOT NULL,
  metadata JSONB DEFAULT '{}',
  source TEXT,                  -- 'apple-notes' | 'claude-thread' | 'perplexity' | 'manual' | 'imessage' | 'gmail'
  chunk_count INT DEFAULT 0,
  node_count INT DEFAULT 0,
  edge_count INT DEFAULT 0,
  content_hash TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID REFERENCES sources(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  label TEXT NOT NULL,
  node_type TEXT NOT NULL,      -- 'concept' | 'project' | 'question' | 'decision' | 'tension'
  embedding VECTOR(1024),
  track TEXT,                   -- 'A' (LLM-extracted) | 'B' (behavioral trace)
  occurrence_count INT DEFAULT 1,
  query_hit_count INT DEFAULT 0,
  confidence_weight FLOAT DEFAULT 1.0,
  has_action_verb BOOLEAN DEFAULT false,
  stall_probability FLOAT,
  resolved_at TIMESTAMPTZ,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE edges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_node UUID REFERENCES nodes(id) ON DELETE CASCADE,
  to_node UUID REFERENCES nodes(id) ON DELETE CASCADE,
  relationship TEXT NOT NULL,   -- see docs/EPISTEMIC_EDGE_VOCABULARY.md
  note TEXT,
  weight FLOAT DEFAULT 1.0,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE segments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID REFERENCES sources(id) ON DELETE CASCADE,
  topic_label TEXT NOT NULL,
  processed_content TEXT NOT NULL,
  processed_embedding VECTOR(1024),
  created_at TIMESTAMPTZ DEFAULT now()
);
```

**Taxonomy:** See `docs/EPISTEMIC_EDGE_VOCABULARY.md` for the full specification of node types, edge types, priority ordering, and extraction quality standard.

---

## Three-Track Extraction Pipeline

### Track A: Authored Content → Claude Reasoning Map

**Script:** `npm run build-graph` → `engine/graph/build-graph.js`
**Sources:** Apple Notes, LLM threads, personal reflections, Perplexity threads
**Process:** Claude Haiku extracts 5-7 nodes + typed edges per source → Voyage AI embeds each node → write to `nodes` + `edges`
**Cost:** ~$0.01 per source

The extraction prompt produces a *reasoning map*, not a summary. A valid extraction must include tension/question nodes — if every node is a concept, extraction has drifted to summarization. See `lib/ingest-pipeline.ts` → `extractGraph()`.

### Track B: Behavioral Traces → Rule Engine

**Script:** Same `build-graph.js` (routes automatically by source type)
**Sources:** iMessage, Gmail
**Process:** Action-verb scan on raw text → creates `concept` nodes with `has_action_verb: true`, `stall_probability: 0.6`, `track: 'B'` → no LLM calls, no embeddings
**Cost:** $0

Source type determines extraction tool (D-027). Never apply the LLM reasoning-map prompt to behavioral traces.

### Track C: All Content → Searchable Segments

**Script:** `npm run build-segments` → `engine/graph/build-segments.js`
**Sources:** All authored content (apple-notes, perplexity, manual, claude-thread)
**Process:** `smart-split.js` splits by source type (zero LLM) → Voyage AI embeds → write to `segments`
**Cost:** ~$0.001 per source (embedding only)

---

## Ingestion Layer

**Script:** Source connectors call `engine/ingestion/ingest-direct.ts`
**Process:** Accept raw content → clean via `preprocess.ts` → chunk → store in `sources` with `chunk_count`
**No LLM calls.** Ingestion and extraction are decoupled (ARCH-014). After ingest, run `build-graph` then `build-segments` separately.

### Source Connectors

| Connector | Script | Method |
|-----------|--------|--------|
| Apple Notes | `sources/apple-notes/sync-direct.js` | osascript (direct read) |
| Local files | `sources/local-files/sync.js` | File scan + `ingest-direct.ts` |
| iMessage | `sources/imessage/sync.js` | SQLite read of `chat.db` + `ingest-direct.ts` |
| Gmail | `sources/gmail/sync.js` | Google API + `ingest-direct.ts` |
| Claude exports | `scripts/watch-claude-exports.js` | File watcher → `sync:local` |
| Claude Code | `scripts/watch-claude-code.js` | Session scanner → `ingest-direct.ts` |

### Preprocessing (`engine/ingestion/preprocess.ts`)

| Source type | What it strips |
|---|---|
| `apple-notes` | HTML tags, entities, backslash breaks |
| `markdown` | Frontmatter, image syntax, bare URLs, header markers |
| `claude-export` | JSON → user/assistant text turns only |
| `imessage` | Timestamps, phone numbers → `[contact]` |
| `gmail` | Quoted replies, headers, HTML |
| `browser` | Nav, footer, scripts, cookie banners |

---

## MCP Server v2.0 (The Product)

**File:** `surfaces/mcp/server.ts`
**Transport:** stdio (runs as `npx tsx surfaces/mcp/server.ts`)
**Backend:** Local SQLite only (sqlite-vec + FTS5). No cloud dependencies.

### Tools (9)

| Tool | Tier | What it does |
|------|------|-------------|
| `get_brief` | L1 | L4-aware context brief: thread summary by state, valid tensions, stalled threads |
| `search` | L2+L3 | Hybrid retrieval (vec + BM25 + RRF) over segments AND knowledge graph in one call |
| `get_tensions` | L3 | Active tensions, valid edges only (invalid_at filtered), with thread context |
| `get_threads` | L4 | Thread-level view with state filter (replaces node-level get_stalled) |
| `get_thread_detail` | L4 | Deep view: state history, members, related threads |
| `get_next_steps` | L4 | Noonchi surface: prioritized next steps across threads |
| `get_history` | L3 | Temporal query: graph state at a point in time, evolution tracking |
| `add_note` | Write | Create source + segments from conversation (local embeddings) |
| `mark_resolved` | Write | Resolve node or thread, propagates to containing threads |

### Graphiti Consistency

The MCP tools are fully consistent with the L3 Graphiti-inspired infrastructure:

- **Hybrid search**: All retrieval uses vec + BM25 + RRF (not pure vector)
- **Edge invalidation**: BFS expansion filters `invalid_at IS NULL`. Only current facts shown.
- **Fact field**: Edges display natural-language `fact` descriptions when available (59% of edges)
- **Episode provenance**: Edges show which source documents established the relationship
- **Temporal queries**: `get_history` supports point-in-time graph state via `valid_at`/`invalid_at` ranges

### Retrieval Pipeline (inside MCP server)

1. Embed query via Nomic nomic-embed-text-v1.5 (768-dim, local ONNX)
2. **Segments**: hybrid search (vec + BM25 + RRF) → top-K passages with source provenance
3. **Graph**: hybrid node search → 5 seeds → BFS 1-hop expansion (filters invalidated + expired) → cap 15 nodes
4. Edges serialized with `fact` field and episode provenance
5. Tensions and contradictions surfaced first (edge priority ordering)

---

## L3 Entity Resolution

**Script:** `npm run l3:resolve` → `engine/l3/entity-resolution.ts`

Entity resolution runs after the main L3 upgrade (bitemporal + BM25 + hybrid search) to create cross-source edges between nodes that refer to the same real-world entity across different apps.

**How it works:**
1. For each node, retrieve nearest neighbors via hybrid search (vec kNN + BM25 + RRF)
2. Candidates above a similarity threshold that share no existing edge are resolution targets
3. A `resolves_to` edge is created between the duplicate nodes, linking the cross-source occurrences
4. Result: cross-app threads that were previously invisible become detectable — e.g., a Gmail thread and an Apple Note about the same project are now graph-connected

**Cross-source edges:** Entity resolution created 1,072 cross-source edges on the current corpus, increasing detectable cross-app threads from 4 → 16.

**Relationship to L4 thread detection:** The hybrid thread detection approach in `engine/l4/detect-threads.ts` uses both embedding proximity (kNN clustering via Union-Find) and graph connectivity (post-clustering enrichment from L3 edges). Entity resolution feeds directly into the graph enrichment step — `resolves_to` edges between nodes from different sources become the signals that allow L4 to group cross-app activity into coherent threads. Without entity resolution, cross-source threads can only be detected by embedding proximity, which misses structurally distinct but topically related content.

---

## L4 — Task-State Awareness (Multi-View Architecture)

L4 sits on top of L3's universal knowledge graph. L3 stores everything (beliefs, projects, transactions, events). L4 provides **domain-specific views** over that graph, each with its own state machine, thread detection strategy, and delivery rules.

### Design Principle

L3 is universal. L4 is pluggable. Different use cases load different L4 configs. The output format (NextStepResult) is the same regardless of domain — thread + state + action + next step. Any output surface (email, SMS, push notification, MCP) consumes the same signal shape.

### L4 Views

| View | What it tracks | State machine | Thread detection |
|------|---------------|---------------|-----------------|
| **View A: Project Tracker** | Active work with goals and endpoints | exploring → evaluating → decided → acting → stalled → completed | Anchored by `project`/`decision` nodes + multi-turn research segments |
| **View B: Belief Tracker** | Evolving beliefs, values, intuitions | forming → reinforced → challenged → evolved → dormant | Anchored by `concept`/`tension` nodes (FUTURE) |
| **View C: Event Log** | Transactions, receipts, communications | No state machine — timestamped record | Entity-anchored (one log per contact/service) (FUTURE) |

**View A is the current implementation.** Views B and C are planned.

### Domain Configurations

The state machine, classification rules, and thread detection filters are defined in `engine/l4/domain-config.ts`. Two validated use cases:

**Personal (default):** Projects, research, shopping journeys, career decisions. Sources: apple-notes, manual, perplexity, claude-thread. State machine: exploring → evaluating → decided → acting → stalled → completed.

**Physio Office (planned):** Patient journeys from inquiry to treatment completion. Sources: email, SMS, booking system. State machine: inquiry → booked → attended → treatment_plan → active_treatment → follow_up → completed. Delivery has SLAs (respond within 48h, remind 24h before appointment).

Both produce the same `NextStepResult` output format. The output layer doesn't need to change between domains.

### How Temporal Signals Feed Classification (Phase 3)

Edge `valid_at` / `invalid_at` from L3 provide temporal ground truth:
- **Edge age**: days since newest valid edge. Old edges + no activity = stalled.
- **Invalidation**: superseded beliefs/decisions signal the thread has evolved.
- **Temporal override**: content patterns ("I'm building X") are only trusted if the thread has recent activity (< 7 days). Older content defaults to exploring/stalled.

### Pipeline

```
Stage 0:   Entity resolution (L3 cross-source edges)
Stage 0.5: Edge invalidation (L3 Phase 3 — mark superseded facts)
Stage 1:   Thread detection (kNN + Union-Find + graph-edge merging)
Stage 2:   State classification (temporal-first, content-secondary)
Stage 3:   Evaluation gate (Sumimasen — should we surface this?)
Stage 4:   Next-step inference (Haiku CoT → OmniActions)
```

---

## Inference Layer

### Stall Detection Rule Engine

**File:** `engine/inference/rule-engine.ts`
**Runner:** `npm run run-rule-engine`

High-confidence rule (all four met → 0.8):
- `occurrence_count >= 2`
- `days_since_first_seen > 14`
- `has_action_verb = true`
- `resolved_at IS NULL`

Otherwise: weighted combination of action_verb (0.3) + recurrence (0.3) + staleness (0.2) + hit_boost (0.1) × confidence_weight.

LLM is reserved for 3 roles only (D-026): Track A extraction, terminal desire synthesis, NLG for delivery. Everything else is ML infrastructure.

---

## Scheduler

**File:** `engine/scheduler/daily-sync.sh`
**Schedule:** macOS launchd (configurable interval)

Pipeline stages (sequential):
1. Apple Notes sync (osascript)
2. Local files sync
3. iMessage sync
4. Gmail sync
5. Claude Code session scan
6. `build-graph` (Track A + B extraction)
7. `run-rule-engine` (stall scoring)
8. `build-segments` (Track C segmentation)

Lockfile at `/tmp/mikai-sync.lock`. Logs to `engine/scheduler/logs/`.

---

## Epistemic Content Type Framework

Not all content is equal signal. Source quality by epistemic type:

| Type | Signal Value | Graph Treatment |
|---|---|---|
| Processed reflection | Highest | High-confidence nodes, preserve reasoning chain |
| Active working note | High | Concept clusters, flag for recurrence |
| Research absorption | Medium | Extract into user's frame |
| Fragment / capture | Low | Store, weight low, watch for recurrence |
| Reference material | Lowest | Skip or low-weight nodes |

See `docs/EPISTEMIC_DESIGN.md` for the full philosophical foundations.

---

## Key Architecture Decisions

| Decision | What was decided |
|---|---|
| ARCH-001 | Supabase only — no separate vector DB |
| ARCH-013 | Claude Haiku for extraction; Voyage AI voyage-3 for embeddings |
| ARCH-014 | Ingestion and extraction are decoupled — never merge them |
| ARCH-015 | Graph traversal: 5 seeds → 1-hop → cap 15 nodes |
| ARCH-016 | Embeddings at node level, not chunk level |
| ARCH-017 | Fixed taxonomy — see `docs/EPISTEMIC_EDGE_VOCABULARY.md` |
| ARCH-018 | Stay on Supabase through Phase 2 (PuppyGraph experiment: marginal gain) |
| D-026 | LLM reserved for 3 roles only |
| D-027 | Source type determines extraction tool |
| D-038 | Three-tier memory (L1/L2/L3) |
| D-039 | MCP server is sole product surface (Next.js removed) |

Full decision log: `docs/DECISIONS.md`

---

*This document describes the architecture as built (L1-L3: memory interface, memory infrastructure, graph/retrieval). For the strategic direction — task-state awareness as the product layer (L4) above memory — see `docs/NOONCHI_STRATEGIC_ANALYSIS.md`. For competitive positioning and the evaluation bridge design, see `docs/MEMORY_ARCHITECTURE_THESIS.md`. For the epistemic foundations, see `docs/EPISTEMIC_DESIGN.md`. For gaps and risks, see `docs/ARCHITECTURE_GAPS.md`.*
