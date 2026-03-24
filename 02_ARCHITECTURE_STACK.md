# MIKAI Architecture & Technical Stack

## System Layers

### Layer 0: Foundation
- User consent & privacy controls (per-device, per-domain toggles)
- Encrypted data storage (events, URLs, timestamps, dwell time)
- Clear retention and deletion policies
- Per-domain blacklisting (banking, health, legal automatically excluded by default)

### Layer 1: Data Collection
- **Browser extension** capturing tabs, URLs, titles, dwell time, referrer
- Cross-platform aggregation addressing "too many platforms problem"
- Content snippets via DOM extraction for semantic analysis
- Respect blacklisted domains
- **Phase 1 alternative:** Manual input (paste/upload) before passive capture is built

### Layer 2: Intent Agent (Noonchi Core)
- **Event normalization:** sessionization, domain categorization, query parsing
- **Short-term intent:** session-level classification (informational, commercial, navigational)
- **Long-term intent:** cluster sessions into projects/goals using embeddings
- **Personal graph construction:** nodes (concepts, projects, resources), edges (typed relationships)
- Continuous updates as new behavior observed

### Layer 3: Recommendation Engine (Sumimasen Core)
- **Candidate generation:** continue projects, consolidate research, next-step nudges
- **Ranking:** recency, frequency, dwell time, revisit patterns
- **Filtering:** max prompts/day, quiet hours, session depth thresholds
- **Delivery:** browser sidebar, daily digest, end-of-session triggers
- Respectful framing as optional suggestions
- Trust accounting: track accepts/ignores to calibrate frequency

### Layer 4: Orchestration
- Agent registration and coordination
- Workflow routing to appropriate specialized agents
- Integration gateway for third-party ecosystem
- Feedback loop: track accepts/ignores to improve ranking

---

## Implementation Stack

| Component | Technology | Role |
|-----------|------------|------|
| LLM backbone | Claude Sonnet 4.6 | Stream extraction, profile generation, graph synthesis |
| Orchestration | n8n cloud | Visual pipeline, webhook triggers, SaaS integrations |
| Browser extension | Chrome Manifest V3 | Passive tab and URL capture |
| Vector DB | Supabase pgvector | Embedding store for personal intent graph |
| Hosting | Vercel | Next.js web app deployment |
| Personalization (Phase 2) | HuggingFace PEFT / LoRA | Parameter-efficient fine-tuning on user data |

### Why Claude + n8n (not OpenAI AgentKit)
- Claude's computer use capability + n8n's visual workflow builder = fastest low-code path
- Less glue code than OpenAI's developer-centric agent stack
- n8n provides SaaS API connectors with minimal programming
- OpenAI is more code-heavy for orchestration (no low-code canvas like n8n)

---

## Synthesis Modes

The chat interface supports three modes of response generation. In v1 the user selects the mode manually. In Phase 2, mode selection will be inferred automatically based on query type and graph structure — see O-011.

### Mode A: Pure Retrieval
Claude answers using only what exists in the user's knowledge graph. No outside knowledge added. Claude acts as a summarizer of the user's own thinking.
**Best for:** "What have I thought about X?"

### Mode B: Grounded Synthesis *(v1 default)*
Claude uses the knowledge graph as context but extends with its own knowledge. Grounds answers in the user's thinking while adding relevant outside connections.
**Best for:** "What do I think about X, and what am I missing?"

### Mode C: Gap Detection *(Phase 2)*
A separate reasoning layer analyzes the graph structure and identifies what the user is circling but hasn't resolved, what's missing, and what contradicts. Claude responds to the gaps rather than the literal question. Requires a reasoning layer above the retrieval layer — not just retrieval itself.
**Best for:** Proactive synthesis — surfacing blind spots the user hasn't yet articulated.

---

## Surface Progression

Planned deployment sequence for the chat interface:

1. **Local UI** — validate the chat interface and synthesis modes against the knowledge graph
2. **WhatsApp** — highest daily use; connects to existing WhatsApp AI agent via n8n webhook pattern
3. **Web app on Vercel** — public deployment of `surfaces/web` Next.js app
4. **Siri via Apple Shortcuts webhook** — ambient layer for voice-triggered queries

---

## Stream Extraction Engine (Feature 1 — Phase 1 Core)

### What It Does
Ingests any message thread, browsing session, or document stream. Outputs:

1. **Intent & Goal Map** — what the user is actually trying to accomplish
   - Short-term intent: what they're working on right now
   - Long-term intent: what larger goal this serves
   - Gaps: what they're circling but not yet articulating

2. **Personality & Economic Profile** — how they process and decide
   - Animal spirits: dominant disposition as economic actor
   - Information metabolism: preferred depth, format, cadence
   - Cognitive type indicators from language patterns

3. **Feed & Workspace Configuration** — dynamic environment tuning
   - Social media filter alignment
   - Reading list curation and re-ranking
   - Notification filter by relevance to current intent

### Input Sources (phased)
- **Phase 1 (manual):** Pasted text, uploaded documents, chat exports
- **Phase 2 (passive):** Browser history, iMessage, Notion, email
- **Phase 3 (ambient):** Calendar, Slack, cross-platform OS integration

---

## Performance Requirements

| Requirement | Target |
|-------------|--------|
| Stream extraction (≤5,000 words) | < 10 seconds |
| Browser extension page load overhead | < 50ms |

---

## The Context Trap Problem
Linear token costs vs non-linear attention degradation in LLMs — as context windows grow, effective attention on relevant details degrades. Raw context scaling is insufficient for true long-term personalization. This is why MIKAI uses structured graphs and synthesis rather than dumping raw history into context.

## Personalization Architecture (Phase 2+)
Not training a foundation model ($10–15B). Instead: personalization stack over existing models.

1. **Data layer:** Log URLs, summaries, annotations, project tags
2. **Embedding + retrieval:** Store as vectors, retrieve similar past items at query time
3. **Profile + preference:** Track patterns (acceptance rates, receptive times, preferred formats)
4. **Tiny adapter (optional):** Fine-tune small model on user style/priorities using LoRA

Cost: hundreds to thousands of dollars, not billions. User owns the adapter, not the base model.

---

## Build-Time Technical Specification
*Canonical reference for Claude Code sessions. When building, treat this section as ground truth.*

### Repository Structure

```
/mikai
  /engine
    /ingestion    → Content parsing, chunking, embedding pipeline
    /graph        → Supabase graph read/write operations (import scripts)
    /synthesis    → Claude API calls: extraction, summarization, graph synthesis
    /retrieval    → Semantic search, graph traversal, context assembly
  /sources
    /apple-notes  → Raw Apple Notes exports and knowledge graph HTML
  /surfaces
    /web          → Next.js app: frontend (chat UI, node explorer) + API routes
    /api          → Placeholder for future standalone API service
  /infra
    /supabase     → Schema migrations, pgvector functions, edge functions
    /n8n          → Workflow export files
  ARCHITECTURE.md
  PHASE1_SCOPE.md
  DECISIONS.md
```

**One module per concern. No cross-importing between ingestion and retrieval.**

---

### Data Model (Supabase / Postgres)

```sql
-- Raw content before processing
CREATE TABLE sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type TEXT NOT NULL,           -- 'llm_thread' | 'note' | 'voice' | 'web_clip' | 'document'
  label TEXT,                   -- human-readable title
  raw_content TEXT NOT NULL,
  metadata JSONB DEFAULT '{}',
  source TEXT,                  -- 'apple-notes' | 'claude-thread' | 'perplexity' | 'manual' | etc.
  chunk_count INT DEFAULT 0,
  node_count INT DEFAULT 0,
  edge_count INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Processed knowledge units (atomic ideas)
CREATE TABLE nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID REFERENCES sources(id) ON DELETE CASCADE,
  content TEXT NOT NULL,        -- the concept/idea in plain text
  label TEXT NOT NULL,          -- short node label
  node_type TEXT NOT NULL,      -- 'concept' | 'project' | 'question' | 'decision' | 'tension'
  embedding VECTOR(1024),       -- pgvector embedding (Voyage AI voyage-3 = 1024 dims)
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Relationships between nodes
CREATE TABLE edges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_node UUID REFERENCES nodes(id) ON DELETE CASCADE,
  to_node UUID REFERENCES nodes(id) ON DELETE CASCADE,
  relationship TEXT NOT NULL,   -- 'supports' | 'contradicts' | 'extends' | 'depends_on' | 'unresolved_tension' | 'partially_answers'
  note TEXT,                    -- one-phrase explanation of why this relationship exists
  weight FLOAT DEFAULT 1.0,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Briefs (deprecated — do not write new briefs; table retained for data continuity)
CREATE TABLE briefs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT,
  content TEXT NOT NULL,
  source_node_ids UUID[],
  brief_type TEXT NOT NULL,     -- 'project' | 'daily' | 'domain' | 'manual'
  created_at TIMESTAMPTZ DEFAULT now()
);

```

**Vector index:**
```sql
CREATE INDEX ON nodes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**Fixed taxonomies (do not change without updating DECISIONS.md and ARCH-017):**
- Node types: `concept`, `project`, `question`, `decision`, `tension`
- Edge types: `supports`, `contradicts`, `extends`, `depends_on`, `unresolved_tension`, `partially_answers`

---

### API Surface (Next.js routes under `/api/`)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/ingest` | POST | Accept raw content, trigger ingestion pipeline |
| `/api/search` | POST | Semantic search over nodes |
| `/api/nodes` | GET | List nodes (paginated, filterable by type) |
| `/api/graph` | GET | Return node + edge data for visualization |

---

### Module Boundaries (Strict)

- `/ingestion` only writes to `sources` and triggers graph writes. It never reads.
- `/graph` owns all reads and writes to `nodes` and `edges`. Nothing else touches these tables directly.
- `/synthesis` only calls Claude API. It receives content as input and returns text. No database access.
- `/retrieval` reads from graph, calls synthesis, returns assembled context. It never writes.
- `/web` calls API routes only. No direct Supabase access from the frontend.

---

### Environment Variables

```bash
ANTHROPIC_API_KEY=        # Claude API
VOYAGE_API_KEY=           # Voyage AI embeddings (voyage-3 model)
SUPABASE_URL=             # Supabase project URL
SUPABASE_SERVICE_KEY=     # Supabase service role key
DATABASE_URL=             # Direct Postgres connection string (session mode pooler)
N8N_WEBHOOK_URL=          # For triggering n8n workflows
```

---

---

## Ingestion + Graph Pipeline (Two-Engine Architecture)

*Implemented 2026-03-13. See ARCH-014.*

The pipeline is split into two independent stages. Never conflate them.

### Stage 1: Ingestion (fast, no LLM)
**Script/route:** `npm run sync` / `npm run sync:local` → `POST /api/ingest/batch`
**What it does:** Accepts raw content, cleans it (`engine/ingestion/preprocess.ts`), chunks it, stores `sources` record with `raw_content` and `chunk_count`. No Claude calls. `maxDuration: 60s`.
**Output:** Source record in Supabase with `chunk_count > 0`.

### Stage 2: Graph Extraction (slow, LLM + embedding)
**Script:** `npm run build-graph` → `engine/graph/build-graph.js`
**What it does:** Reads all sources with `chunk_count > 0` and `node_count = 0`. Calls Claude with the reasoning-map extraction prompt. Embeds each extracted node with Voyage AI. Writes to `nodes` and `edges` tables.
**Output:** Nodes + typed edges in Supabase with embeddings.

**Flags:**
- `--rebuild` — delete existing nodes (cascades to edges) and re-extract all sources
- `--source-id <uuid>` — process one source; bypasses `chunk_count > 0` filter
- `--dry-run` — print what would be processed, no API calls
- `--preview` — run Claude extraction and print raw JSON without writing to DB

**After any ingest, always run:** `npm run build-graph`

---

## Graph Retrieval Layer

*Implemented 2026-03-13. See ARCH-015, ARCH-016.*

**File:** `lib/graph-retrieval.ts`

### Retrieval flow (both `/api/chat` and `/api/search`)
1. Embed query with Voyage AI → vector similarity search → 5 seed nodes
2. Query all edges where `from_node IN (seeds) OR to_node IN (seeds)`
3. Rank connected non-seed nodes by best-priority edge type
4. Fetch top N connected nodes to fill remaining slots (cap: 15 total nodes)
5. Filter edges to only those within the final node set
6. Serialize as structured context string

### Edge priority ordering
```
unresolved_tension  → 0 (highest — surfaces active unresolved thinking first)
contradicts         → 1
depends_on          → 2
partially_answers   → 3
supports            → 4
extends             → 5 (lowest)
```

### Subgraph serialization structure (`serializeSubgraph`)
1. **Nodes retrieved by semantic similarity** — the seed nodes
2. **Active tensions and contradictions** — high-priority edges + both connected nodes
3. **Connected nodes (one hop)** — each with its edge relationships listed inline
4. **Other relationships** — supports, extends, depends_on

### API endpoints
| Endpoint | Method | Returns |
|---|---|---|
| `/api/chat` | POST `{ query }` | `{ answer, sources, subgraph_size }` |
| `/api/search` | GET `?q=<query>&limit=<5>` | `{ subgraph, seed_count, total_nodes, total_edges }` |

---

## Extraction Prompt Quality Standard

*Established 2026-03-13. Prompt lives in `lib/ingest-pipeline.ts` → `extractGraph()`.*

The extraction prompt is a reasoning-map prompt, not a taxonomy prompt. Do not simplify or revert it. The following outputs are required and must be preserved across any prompt iteration:

**Required node outputs:**
- `tension` and `question` nodes must appear — not just `concept` nodes. A source that produces only concepts and decisions has failed extraction.
- `content` fields must be written in first person from Brian's perspective (e.g., "I've concluded that..." not "The author believes..."). This is what makes the graph personal rather than generic.
- Revision events — when a source shows belief updating ("I used to think X, now I think Y") — must be captured, either as a `decision` node superseding a prior concept or as a `tension` node between old and new belief.

**Required edge outputs:**
- Every edge must have a `note` field explaining the specific relationship in plain language. A note-less edge is underspecified.
- `unresolved_tension` edges must be used when the source explicitly holds two things in conflict without resolving them. Do not substitute `contradicts` (which implies external contradiction, not internal holding).

**Validation heuristic:** A good extraction from a personal reflection note should have at least 2 `tension` or `question` nodes out of 5–7 total. If every node is a `concept` or `decision`, the prompt has drifted toward summarization rather than reasoning-map extraction.

---

## Epistemic Content Type Framework

*Documented in `MIKAI_Epistemic_Design.md`. Informs extraction and future classify-before-extract optimization.*

Not all content is equal signal. The framework distinguishes source quality by epistemic type:

| Type | Description | Extraction value | Examples |
|---|---|---|---|
| Processed reflection | Author has synthesized an experience into a belief or updated position | Highest | Monthly journal entries, decision retrospectives, thesis documents |
| Active working note | Thinking in progress — tensions and questions explicitly held | High | Open questions docs, working state docs, session notes mid-project |
| Research absorption | Author processing external material into their own frame | Medium | Thread exports, annotated reading notes, Perplexity threads |
| Fragment / capture | Raw capture with no synthesis — list items, quick notes, URLs | Low | Bookmark dumps, short Apple Notes, single-line captures |
| Reference material | Factual content the author hasn't personally processed | Lowest | Copied articles, unedited exports |

**Build implication:** A future optimization (not yet built) is to classify content type before extraction and either skip fragments entirely or produce low-weight nodes with reduced graph priority. Do not build this without first validating extraction quality on processed reflections (O-020). Reference: `MIKAI_Epistemic_Design.md`.

---

## Graph Retrieval — Edge Priority Rationale

*See also: inline comment in `lib/graph-retrieval.ts` above `EDGE_PRIORITY`.*

The edge priority ordering (`unresolved_tension(0) > contradicts(1) > ...`) is intentional and load-bearing. Do not reorder without discussion.

The chat system prompt explicitly instructs Claude to surface unresolved tensions and contradictions rather than paper over them. The edge priority ordering ensures the subgraph fed to Claude is biased toward the most contested and unresolved parts of Brian's thinking. Reordering to deprioritize tensions would silently undermine the core retrieval contract even if the code continued to function correctly.

The ordering is also asymmetric by design: `unresolved_tension` ranks above `contradicts` because an unresolved tension is something Brian is actively holding in conflict (internal), while a contradiction is between two nodes that conflict (structural). Internal holding is more valuable signal for synthesis than structural contradiction.

---

## Preprocessing Module

*Implemented 2026-03-13. File: `engine/ingestion/preprocess.ts`*

`cleanContent(rawContent: string, sourceType: string): string`

| Source type | Handler | Use |
|---|---|---|
| `apple-notes` | `cleanAppleNotes` | Apple Notes HTML export |
| `whatsapp` | `cleanWhatsApp` | WhatsApp chat export (strips timestamps/sender prefixes) |
| `browser` | `cleanBrowser` | Browser-saved HTML (strips nav, footer, scripts, boilerplate) |
| `markdown` | `cleanMarkdown` | .md files — strips frontmatter, images, bare URLs, header markers |
| `claude-export` | `cleanClaudeExport` | Claude JSON exports — extracts user/assistant text turns only |
| `plain` | `cleanPlain` | Default — normalizes whitespace only |

---

## Source Connectors

| Connector | Script | Input dirs |
|---|---|---|
| Apple Notes | `npm run sync` → `sources/apple-notes/sync.js` | `sources/apple-notes/export/` |
| Local files | `npm run sync:local` → `sources/local-files/sync.js` | `sources/local-files/export/{markdown,claude-exports,perplexity}/` |

**Local-files handler dispatch:**
- `markdown/*.md` or `*.txt` → `cleanMarkdown`, source: `manual`, type: `document`
- `claude-exports/*.json` → `cleanClaudeExport`, source: `claude-thread`, type: `llm_thread`
- `perplexity/*.html` → `cleanBrowser`, source: `perplexity`, type: `document`
- `perplexity/*.md` → `cleanMarkdown`, source: `perplexity`, type: `document`

---

## Canonical Node/Edge Taxonomy

*Updated 2026-03-13. See ARCH-017. Supersedes ARCH-007 and ARCH-008.*

**Node types:** `concept` | `project` | `question` | `decision` | `tension`

**Edge types:** `supports` | `contradicts` | `extends` | `depends_on` | `unresolved_tension` | `partially_answers`

**Edge note field:** Every edge has an optional `note TEXT` column explaining the specific relationship in plain language. Required for `unresolved_tension` and `contradicts` edges. Supabase migration: `infra/supabase/add_edge_note.sql`.

**Do not change the taxonomy without updating ARCH-017 in `04_DECISION_LOG.md`.**

---

## Inference Layer Stack

*Decided 2026-03-14. See D-026, D-027, D-028.*

The inference layer is not a monolithic LLM pipeline. It is a stack of tools, each assigned to the problem it is best suited for. LLM calls happen at three points only.

### Tool assignment by layer

| Layer | Tool | When |
|-------|------|------|
| Identity resolution — unify Brian across Notes, Chrome, WhatsApp, Claude threads | Probabilistic record linkage (entity matching, fuzzy label + temporal proximity) | Phase 2 |
| Feature computation — `occurrence_count`, temporal gaps, action verbs, edge density, source quality score | SQL aggregations on graph schema (materialized on each `build-graph` run) | Phase 2 |
| Immediate desire scoring | Rule engine → gradient-boosted classifier (trained from `predictions` table once 50+ labels exist) | Phase 2 |
| Instrumental desire detection | Unsupervised embedding clustering + temporal recurrence detection | Phase 2 |
| **Track A extraction — authored content** | **LLM (reasoning-map prompt, already built)** | Phase 1 ✓ |
| **Track B extraction — behavioral traces** | **Rule engine / structural pattern detection (never LLM)** | Phase 2 |
| **Terminal desire synthesis** | **LLM (interpretive pass across full graph trajectory)** | Phase 3 |
| **Natural language generation — WhatsApp delivery** | **LLM (one call per delivery cycle, not per node evaluated)** | Phase 3 |

### Source type determines extraction tool (D-027)

Never apply the LLM reasoning-map prompt to behavioral traces. The distinction:

- **Authored content** (Apple Notes, LLM threads, personal reflections, Perplexity threads) → Track A. The person has synthesized their thinking into language. The LLM extracts the reasoning structure.
- **Behavioral traces** (email, iMessage, WhatsApp message history, browser behavior) → Track B. These are raw action data — threads with no reply, questions with no follow-through, topics visited repeatedly. Structural pattern matching, not semantic extraction.

### Rule engine → classifier progression (Phase 2 → Phase 3)

Phase 2 starts with a hand-tuned rule engine for stalled immediate desire scoring:

```
IF occurrence_count >= 2
  AND days_since_first_seen > 14
  AND has_action_verb = true
  AND resolved_at IS NULL
THEN stall_probability = 0.8
```

Every rule engine evaluation writes a prediction record to the `predictions` table. After 50+ dismiss/confirm signals from the validation UI, a gradient-boosted classifier (XGBoost) is trained on the feature vectors. The rule engine is replaced by the classifier at that point. The classifier runs sub-millisecond — no API call required.

---

## Desire Layer Architecture (Phase 2+)

*Specified 2026-03-14. See deep-interview spec: `.omc/specs/deep-interview-desire-taxonomy.md`.*

The current node taxonomy is an **epistemological taxonomy** — it describes what you know, believe, question, and decide. Phase 2 requires a **motivational taxonomy** — a second axis describing what you want and at what level.

### Desire Levels (future node attribute)

These are not replacement node types. They are an additional dimension to be added to the `nodes` table as `desire_level TEXT`.

| Level | Value | Properties |
|-------|-------|------------|
| Immediate | `immediate` | Short horizon, high specificity, resolves or decays. If it persists across months, reclassify as instrumental. |
| Instrumental | `instrumental` | Persistent, accumulates evidence, pursued through friction. Has recognizable shape: a question circled, a gap researched, a tension held. |
| Terminal | `terminal` | Almost never appears directly in corpus. Inferred from consistent direction of instrumental desires over time. Represents what the person is consistently oriented toward. |

**Key constraint:** Terminal desires cannot be extracted from any single piece of content. They require trajectory analysis across the full graph over time. The inference layer (Phase 2+) is a separate architectural component — not a retrieval query.

**Key insight on friction:** Behavioral engagement data (clicks, dwell, saves) is inversely correlated with terminal desire in important cases. High-friction, low-engagement behavior is often the strongest instrumental desire signal. The extraction prompt already reaches for this via `unresolved_tension` nodes and the tension-first edge priority ordering. These are correct bets for the desire inference model.

### Reclassification Mechanism (Phase 2)

When an immediate desire node reappears across sources separated in time without resolving, the system automatically reclassifies it as instrumental. This requires temporal metadata on nodes (see Schema Additions below). The recurrence detection is automatic — no user confirmation needed for reclassification.

### Terminal Desire Inference (Phase 3)

A separate inference pass over the full graph trajectory — not a retrieval query but an interpretive synthesis. Takes the accumulated pattern of instrumental desires over time and infers what terminal desires they serve. Output: a `terminal_desire` node cluster plus a constructed-self summary.

This component does not exist yet and should not be built during Phase 1 or Phase 2 initial capture.

---

## Schema Additions for Desire Layer

*Not yet implemented. Migration required before Phase 2 begins. Additions are non-breaking — all new columns are nullable, all new tables are additive.*

### Additions to `nodes` table

```sql
-- Feature store columns (pre-computed at build-graph time, not LLM-derived)
-- These power the rule engine and classifier without requiring graph queries at inference time
ALTER TABLE nodes ADD COLUMN occurrence_count    INTEGER DEFAULT 1;
ALTER TABLE nodes ADD COLUMN query_hit_count     INTEGER DEFAULT 0;   -- incremented on retrieval
ALTER TABLE nodes ADD COLUMN confidence_weight   FLOAT   DEFAULT 1.0; -- source quality × extraction confidence
ALTER TABLE nodes ADD COLUMN has_action_verb     BOOLEAN DEFAULT false; -- 'buy', 'book', 'schedule', 'call', 'send'
ALTER TABLE nodes ADD COLUMN stall_probability   FLOAT;               -- output of rule engine / classifier

-- Temporal metadata for recurrence detection and lifecycle management
ALTER TABLE nodes ADD COLUMN first_seen_at       TIMESTAMPTZ;
ALTER TABLE nodes ADD COLUMN last_seen_at        TIMESTAMPTZ;

-- Desire level taxonomy (nullable: not set during Phase 1)
ALTER TABLE nodes ADD COLUMN desire_level        TEXT;
-- allowed values: 'immediate' | 'instrumental' | 'terminal'

-- Resolution tracking for immediate desires
ALTER TABLE nodes ADD COLUMN resolved_at    TIMESTAMPTZ;
-- null = active or unresolved; set = desire has resolved or decayed
```

### New table: `node_clusters`

Cross-source node identity. Required for trajectory analysis — the same desire appearing across multiple sources creates independent nodes today. Clustering is the prerequisite for recurrence detection.

```sql
CREATE TABLE node_clusters (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_label   TEXT NOT NULL,           -- representative label for the cluster
  member_node_ids   UUID[],                  -- all nodes in this semantic cluster
  cluster_type      TEXT,                    -- matches node_type of members
  desire_level      TEXT,                    -- inferred desire level for the cluster
  first_seen_at     TIMESTAMPTZ,
  last_seen_at      TIMESTAMPTZ,
  occurrence_count  INTEGER DEFAULT 1,
  created_at        TIMESTAMPTZ DEFAULT now()
);
```

### New table: `predictions`

Required for the validation feedback loop. Every desire inference surfaced to the user is a prediction. User response (confirm/dismiss/ignore) is the ground truth signal for model evaluation.

```sql
CREATE TABLE predictions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  predicted_desire  TEXT NOT NULL,           -- the surfaced desire statement
  desire_level      TEXT NOT NULL,           -- 'immediate' | 'instrumental' | 'terminal'
  evidence_node_ids UUID[],                  -- nodes that drove the prediction
  confidence_score  FLOAT,                   -- 0.0–1.0
  prediction_type   TEXT NOT NULL,           -- 'desire' | 'action' | 'behavioral'
  proposed_action   TEXT,                    -- optional: "Schedule 2hrs for X"
  user_response     TEXT,                    -- 'confirm' | 'dismiss' | 'ignore'
  responded_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ DEFAULT now()
);
```

**Signal asymmetry:** `dismiss` is a stronger model signal than `confirm`. When the user dismisses, the model misread the desire hierarchy. Track dismiss rate per desire_level as the primary quality metric.

---

## Validation Mechanism (Phase 1.5)

*Addresses O-020. The central scientific question: can the model predict human behavior and desires?*

### Desire Card (recommended for Phase 1 validation)

A daily in-app surface presenting 1–3 predictions generated from the graph. User taps to confirm or dismisses to reject. No OS integration required. Generates binary training signal from existing corpus.

**Implementation:** Query nodes with high recurrence or unresolved tension edges → generate natural-language desire statement → write to `predictions` table → surface in UI → capture response.

**Validation metric:** Dismiss rate per desire level. Target: dismiss rate < 30% for instrumental desires after 20 prediction rounds. If dismiss rate is > 50%, extraction prompt needs revision before surface work begins.

### Lock Screen Notification (Phase 2 target)

Action proposals surfaced at OS notification level. Press to activate (adds to calendar, initiates purchase, etc.), swipe to cancel. This is the V2 Sumimasen interface. Requires OS integration — do not build during Phase 1.

---

### Claude Code Session Rules

1. Read `ARCHITECTURE.md`, `02_ARCHITECTURE_STACK.md`, and `03_PRD_CURRENT.md` before writing any code.
2. Read `00_STRATEGIC_LESSONS.md` to understand build constraints before scoping any feature.
3. Work within the module you were assigned. Do not touch other modules.
4. If a decision conflicts with this spec, stop and flag it — do not resolve it yourself.
5. Write TypeScript. No plain JavaScript.
6. Every function must have a JSDoc comment explaining its input and output.
7. No external dependencies without checking `04_DECISION_LOG.md` first.
