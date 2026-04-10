# L4 Research Integration: Build Spec for Claude Code

**Created:** 2026-03-28
**Purpose:** Translate five research papers + Anthropic's harness pattern into actionable architecture decisions for L4. This document tells Claude Code exactly what to build now, what to defer, and why.
**Authority:** This document is the research-to-build bridge. For L4 concept definitions, see `private/strategy/01_CORE_ENGINE.md`. For current L4 code, see `engine/l4/`.

---

## The Five Papers and What They Solve

Each paper solves one component of the L4 pipeline. None of them build the complete system. MIKAI's job is to assemble them.

```
MIKAI L4 Pipeline:
  detect-threads.ts → classify-state.ts → [EVALUATION GATE] → infer-next-step.ts → [DELIVERY]
  ──────────────────   ─────────────────   ────────────────   ──────────────────   ──────────
  Already built         Already built       NOT BUILT          Already built         NOT BUILT
                                            (ProMemAssist)                          (Inner Thoughts)
                                            (PPP training)                          (PPP training)
```

### Paper 1: ProMemAssist (UIST 2025)
**What it solves:** When to deliver (the Sumimasen timing gate)
**Source:** arXiv:2507.21378

**Architecture (what Claude Code needs to know):**
The system models a user's working memory as a bounded buffer with three degradation mechanisms:

1. **Displacement** — new information pushes out old items when buffer is full. Buffer capacity is modeled as ~4±1 items (Cowan's working memory limit). When a new percept arrives and the buffer is full, the oldest item is evicted.

2. **Interference** — items competing for the same modality (visual-visual, verbal-verbal) degrade each other. The cost function:
   ```
   interference_cost = modality_overlap(new_item, active_items) × semantic_distance(new_item, active_items)
   ```
   High modality overlap + low semantic distance = high interference (the new thing disrupts what you're focused on).

3. **Recency decay** — items not reinforced decay over time. Exponential decay:
   ```
   strength(t) = initial_strength × e^(-λt)
   ```
   Where λ is the decay rate and t is time since last reinforcement.

**Timing prediction formula:**
```
utility(message) = value(message) - cost(displacement) - cost(interference)
```
Deliver only when utility > threshold. The threshold adapts based on dismiss/act feedback.

**What to build NOW (V1):**
- A `SumimasenGate` module in `engine/l4/` that decides whether to surface a next-step
- V1 implementation: rule-based proxy using cross-app activity patterns as cognitive load indicator
  - Rapid app switching (>3 source types active in last hour) = high load → don't interrupt
  - Extended time in single source (>30 min no cross-app activity) = deep focus → don't interrupt
  - Long idle period after active research (>2 hours no activity after burst) = potential stall → good time
  - Time of day heuristic: morning delivery window, max 3 items per cycle
- Add `delivery_score` field to threads table (0-1, computed by the gate)
- Add `dismissed_count` and `acted_count` fields for future training signal

**What to defer (V2+):**
- Actual working memory modeling (requires real-time sensory input MIKAI doesn't have)
- Continuous interference cost computation (needs activity stream, not batch processing)
- Adaptive threshold training from dismiss/act signals (needs users first)

**Schema addition for V1:**
```sql
ALTER TABLE threads ADD COLUMN delivery_score REAL DEFAULT 0.0;
ALTER TABLE threads ADD COLUMN dismissed_count INTEGER DEFAULT 0;
ALTER TABLE threads ADD COLUMN acted_count INTEGER DEFAULT 0;
ALTER TABLE threads ADD COLUMN last_surfaced_at TEXT;
```

---

### Paper 2: OmniActions (CHI 2024)
**What it solves:** What to recommend (structured action prediction)
**Source:** arXiv:2405.03901

**Architecture (what Claude Code needs to know):**
OmniActions defines a structured action space derived from a 382-entry diary study with 39 participants:

**7 General Action Categories:**
1. Search — look up more information
2. Create — make new content (draft, document, message)
3. Capture — save, bookmark, screenshot
4. Share — send to someone, post
5. Schedule — set reminder, add to calendar, book
6. Navigate — open app, go to URL, switch context
7. Configure — change setting, update preference

**17 Specific Categories (subset most relevant to knowledge work):**
- Search: web search, document search, contact search
- Create: draft message, write document, create task
- Share: send email, share link, forward message
- Schedule: set reminder, book meeting, add deadline
- Navigate: open reference, switch to app
- Configure: update list, modify plan

**Chain-of-thought prompt structure:**
```
Given this thread context:
- Thread: {label}
- State: {state}
- Recent activity: {activity_summary}
- Cross-app signals: {source_types and their content}

Step 1: What general action category is most appropriate? (Search/Create/Share/Schedule/Navigate/Configure)
Step 2: What specific action within that category?
Step 3: What is the concrete next step with specific details from the thread?
```

**What to build NOW (V1):**
- Replace the current free-form next-step inference prompt in `infer-next-step.ts` with the structured CoT approach above
- Add `action_category` field (general) and `action_type` field (specific) to the inference result
- This makes next-step outputs parseable and classifiable, not just free text
- Keep using Haiku — the CoT structure actually improves accuracy without needing a larger model

**Concrete changes to `infer-next-step.ts`:**

Update the SYSTEM_PROMPT to include the action taxonomy:
```typescript
const SYSTEM_PROMPT = `You are a task-state awareness engine. Given a user's thread, infer the next step using structured reasoning.

Action categories:
- Search: look up more information about the topic
- Create: draft a message, document, or task
- Share: send something to someone
- Schedule: set a reminder, book something, add a deadline
- Navigate: open a reference or switch to an app
- Configure: update a list, modify a plan

Rules:
- First identify the general action category, then the specific action, then the concrete step.
- Be specific: "Draft a follow-up email to Sarah about the proposal deadline" not "Think about the proposal"
- Match the thread's state:
  - exploring: Search or Navigate actions
  - evaluating: Search or Create (comparison document) actions
  - decided: Create or Share actions (execute the decision)
  - acting: Create, Share, or Schedule actions (continue the work)
  - stalled: any action that unblocks — often Search, Share, or Schedule
- Format: [CATEGORY] Specific action description
- Keep to 1-2 sentences max.`;
```

Update `NextStepResult` type:
```typescript
export interface NextStepResult {
  thread_id: string;
  next_step: string;
  action_category: 'search' | 'create' | 'capture' | 'share' | 'schedule' | 'navigate' | 'configure';
  reasoning: string;
  confidence: number;
  generated_at: string;
}
```

**What to defer (V2+):**
- Multimodal input (camera, audio) — OmniActions uses this but MIKAI doesn't need it
- The full 17-category specific taxonomy (start with 7 general categories, expand as data comes in)
- Top-3 prediction (start with top-1, evaluate accuracy before adding alternatives)

---

### Paper 3: Inner Thoughts (CHI 2025)
**What it solves:** The cognitive loop for proactive delivery
**Source:** arXiv:2501.00383

**Architecture (what Claude Code needs to know):**
Inner Thoughts defines a five-stage continuous reasoning loop grounded in SOAR/ACT-R cognitive architectures:

```
┌─────────┐     ┌───────────┐     ┌─────────────────┐     ┌────────────┐     ┌───────────────┐
│ TRIGGER  │ ──→ │ RETRIEVAL │ ──→ │ THOUGHT          │ ──→ │ EVALUATION │ ──→ │ PARTICIPATION │
│          │     │           │     │ FORMATION        │     │            │     │               │
│ Activity │     │ L2/L3     │     │ State            │     │ Sumimasen  │     │ Deliver via   │
│ detected │     │ query     │     │ classification   │     │ gate       │     │ MCP / notify  │
└─────────┘     └───────────┘     └─────────────────┘     └────────────┘     └───────────────┘
```

**Stage details mapped to MIKAI:**

1. **Trigger** — a cross-app activity event arrives (new email about existing topic, note updated, message received, file modified). In MIKAI: this is the scheduler detecting new ingested content that falls within an existing thread's embedding space.

2. **Retrieval** — pull relevant context. In MIKAI: `search_knowledge` (L2 segments) + `search_graph` (L3 nodes) + `getThreadMembers` (L4 thread context). The key insight: retrieval uses BOTH working memory (recent thread activity) and long-term memory (full knowledge graph).

3. **Thought Formation** — synthesize a new "thought" from trigger + retrieved context. In MIKAI: re-run `classifyThreadStates` for the affected thread. Has the state changed? Did the new activity push `exploring → evaluating` or `decided → acting`?

4. **Evaluation** — assess intrinsic motivation to express this thought. In MIKAI: the Sumimasen gate (ProMemAssist's timing model). Key question: is this state change worth surfacing right now?

5. **Participation** — if motivation exceeds threshold, deliver. In MIKAI: surface via MCP `get_next_steps` tool, or push via notification/email digest.

**The critical insight: the evaluation stage is as important as the inference stage.** A proactive system that surfaces every inference is annoying. One that evaluates before speaking is useful.

**What to build NOW (V1):**
- Formalize the five-stage loop as the L4 pipeline orchestrator
- Current `run-l4-pipeline.ts` already does stages 1-3 (detect → classify → infer)
- Add stage 4: evaluation gate between classify and infer (the SumimasenGate)
- Stage 5 is already the MCP delivery layer

**Concrete change to `run-l4-pipeline.ts`:**
```typescript
// Current pipeline: detect → classify → infer
// New pipeline:     detect → classify → evaluate → infer (only for threads that pass gate)

export async function runL4Pipeline(db: Database.Database, options: PipelineOptions) {
  // Stage 1: Trigger + Detection
  const detectResult = await detectThreads(db);

  // Stage 2-3: Classification (includes retrieval internally)
  const classifyResult = await classifyThreadStates(db);

  // Stage 4: Evaluation gate (NEW)
  const deliverableThreads = await evaluateForDelivery(db);
  // Only threads that pass the gate get inference (saves Haiku calls)

  // Stage 5: Inference (only for gated threads)
  const inferResult = await inferNextSteps(db, deliverableThreads);
}
```

**What to defer (V2+):**
- Continuous parallel thought generation (requires event-driven architecture, not batch)
- Working memory vs long-term memory separation (for now, treat all context equally)
- Intrinsic motivation modeling (start with rule-based evaluation, train later)

---

### Paper 4: PPP (CMU, November 2025)
**What it solves:** How to train the delivery system
**Source:** arXiv:2511.02208

**Architecture (what Claude Code needs to know):**
PPP defines three joint optimization objectives:

1. **Productivity** — does the system help the user complete their task?
   - MIKAI metric: did the user act on the surfaced next-step? (act_count / surface_count)

2. **Proactivity** — does the system anticipate needs without being asked?
   - MIKAI metric: was the next-step surfaced before the user asked for it? (proactive_surface_count / total_surface_count)

3. **Personalization** — does the system respect individual preferences?
   - MIKAI metric: dismiss rate per user (target: <30% after 20 interactions)

**UserVille: 20 persona types** with varying preferences:
- Communication style (brief vs detailed)
- Interruption tolerance (high vs low)
- Autonomy preference (wants suggestions vs wants the system to act)
- Detail level (high-level direction vs step-by-step)

**Training signal:**
```
reward = α × productivity_score + β × proactivity_score + γ × personalization_score
```
Where α, β, γ are tuned per persona type. Key finding: optimizing productivity alone hurts proactivity and personalization. Must optimize jointly.

**What to build NOW (V1):**
- Add user preference tracking infrastructure (not the RL training, just the data collection)
- Schema: `user_preferences` table with dismiss/act/ignore signals per delivery
- Track three metrics per user from day 1:
  - `productivity_score`: act_count / surface_count (did they do what was suggested?)
  - `proactivity_score`: proactive_surface_count / total (was it unsolicited and useful?)
  - `personalization_score`: 1 - (dismiss_count / surface_count) (did they reject it?)

**Schema addition for V1:**
```sql
CREATE TABLE IF NOT EXISTS delivery_events (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  thread_id TEXT NOT NULL REFERENCES threads(id),
  next_step TEXT NOT NULL,
  action_category TEXT,
  delivery_score REAL,
  user_response TEXT CHECK(user_response IN ('acted', 'dismissed', 'ignored', 'deferred')),
  response_at TEXT,
  delivered_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_delivery_thread ON delivery_events(thread_id);
CREATE INDEX IF NOT EXISTS idx_delivery_response ON delivery_events(user_response);
```

**What to defer (V2+):**
- Multi-objective RL training (needs hundreds of delivery events per user)
- Persona type classification (needs multiple users with different preferences)
- UserVille-style simulation environment for offline training
- Adaptive α/β/γ tuning per user

---

### Paper 5: MEMTRACK (Patronus AI, NeurIPS 2025)
**What it solves:** How to evaluate L4
**Source:** arXiv:2510.01353

**Architecture (what Claude Code needs to know):**
MEMTRACK simulates a software org with interleaved events across Slack, Linear, and Git. Each scenario has:

- **Cross-platform dependencies** — information from Slack is needed to answer a question about a Linear ticket
- **Temporal ordering** — events must be processed in chronological order
- **Deliberate contradictions** — status updates on Slack that contradict Linear ticket states
- **State questions** — "What is the current status of project X?" requires tracking across platforms

**Three evaluation metrics:**
1. **Correctness** (0-100%) — is the tracked state accurate?
2. **Efficiency** (lower = better) — how many tool calls / memory lookups needed?
3. **Redundancy** (lower = better) — is duplicate information stored?

**Key result:** GPT-5 scores 60% correctness. Adding Mem0 or Zep does NOT significantly improve this. Memory infrastructure alone doesn't solve cross-platform state tracking.

**What to build NOW (V1):**
- Create an eval suite for L4 modeled on MEMTRACK's methodology
- Use Brian's own data: manually label 20-30 threads with ground-truth states
- Measure three things:
  1. Thread detection accuracy: do detected threads match real topics? (precision/recall)
  2. State classification accuracy: does the classified state match reality?
  3. Next-step relevance: rate 1-5, is the suggestion actually useful?
- Add to `engine/eval/eval-l4.ts`

**Eval structure:**
```typescript
interface L4EvalCase {
  // Ground truth (manually labeled)
  thread_label: string;
  expected_source_types: string[];      // which apps should be grouped
  expected_state: ThreadState;          // what state is this thread really in
  expected_next_step_category: string;  // what kind of action is appropriate

  // System output (from L4 pipeline)
  detected_thread_id: string | null;    // did L4 find this thread?
  classified_state: ThreadState | null; // what state did L4 assign?
  inferred_next_step: string | null;    // what did L4 suggest?

  // Scores
  detection_correct: boolean;
  state_correct: boolean;
  next_step_relevance: number;          // 1-5 human rating
}
```

**What to defer (V2+):**
- Full MEMTRACK-style simulation with synthetic events
- Automated scoring (requires ground truth generation)
- Publishing benchmark results (wait until L4 is stable)

---

### Anthropic's Harness Pattern
**What it solves:** State persistence across sessions
**Source:** anthropic.com/engineering/effective-harnesses-for-long-running-agents

**Architecture (what Claude Code needs to know):**
Anthropic's harness for long-running agents uses three state artifacts:

1. **`claude-progress.txt`** — append-only log of what was accomplished
2. **Feature list (JSON)** — structured tracking with `passes: true/false` per item
3. **Git history** — incremental commits as temporal checkpoints

**Session startup ritual:**
1. Read progress file → understand recent work
2. Read feature list → find highest-priority incomplete item
3. Run tests → verify current state isn't broken
4. Work on next item
5. Commit + update progress + update feature list

**MIKAI L4 analogy:** The harness is L4 for agents. MIKAI is L4 for humans. Same pattern, different subject.

| Harness Artifact | L4 Equivalent |
|---|---|
| `claude-progress.txt` | `thread_transitions` table (what happened) |
| Feature list JSON (`passes: false/true`) | `threads.state` field (current state per thread) |
| Git commits | Cross-app activity events (temporal checkpoints) |
| Session startup ritual | L4 pipeline run (reconstruct context, classify state, infer next) |

**What to build NOW (V1):**
- The L4 pipeline already follows this pattern. Validate that:
  - Thread state is persisted and reconstructable from `thread_transitions`
  - Each pipeline run starts by reading current state, not recomputing from scratch
  - State changes are logged as transitions with reasons (audit trail)
- Add a `l4-progress.json` file that the pipeline writes after each run:
  ```json
  {
    "last_run_at": "2026-03-28T10:00:00Z",
    "threads_total": 45,
    "threads_by_state": { "exploring": 12, "evaluating": 8, "decided": 5, "acting": 10, "stalled": 7, "completed": 3 },
    "next_steps_generated": 15,
    "delivery_events": 3
  }
  ```

---

## Critical Architecture Decision: Graph Structure vs Embedding Proximity for Thread Detection

### The question
Should threads be defined by:
- **(A) Embedding proximity** — segments with similar embeddings get grouped (current approach in `detect-threads.ts`)
- **(B) Graph connectivity** — nodes connected by L3 edges get grouped
- **(C) Hybrid** — use both signals with different weights

### The analysis

**Option A: Embedding proximity (current implementation)**

Strengths:
- Memory-layer agnostic. If you swap L3 for Graphiti/Cognee (V3), thread detection still works. Any system that produces embeddings can feed L4.
- Cross-source by default. An Apple Note about "Kenya trip" and a Gmail about "Nairobi flights" have similar embeddings even though they share no graph edges.
- Zero LLM, fast. kNN on pre-computed vectors is milliseconds.

Weaknesses:
- Embedding similarity is semantic, not structural. Two segments about "Kenya" get grouped even if one is about coffee farming and the other about travel. Without graph edges, you can't distinguish topical similarity from reasoning relationship.
- No edge-type awareness. A segment that `contradicts` another and one that `supports` it look equally "similar" in embedding space. The relationship type is lost.
- Over-clustering risk. Broad topics (e.g., "AI") will absorb unrelated threads because embeddings are too close.

**Option B: Graph connectivity**

Strengths:
- Structurally precise. If two nodes are connected by a `depends_on` or `contradicts` edge, they're genuinely related in the user's reasoning. No false grouping.
- Edge types carry meaning. A thread built from `unresolved_tension` edges is qualitatively different from one built from `supports` edges — the first is stalled, the second is confirmed.
- Natural state signals. Graph structure directly encodes reasoning state: a cluster of `contradiction` edges = evaluating; `depends_on` chain with no resolution = stalled.

Weaknesses:
- **Coupled to L3.** If you swap the knowledge graph, thread detection breaks. This violates the V3 strategy (memory layer is replaceable).
- **Coverage gap.** Graph only has edges where the extraction prompt produced them. Behavioral traces (Track B) and segments (Track C) often have no graph edges at all. A Gmail about "send the proposal to Sarah" has no L3 edges — it would be invisible to graph-based thread detection.
- **Sparse for new users.** Graph density depends on extraction quality. Empty graph = no threads detected, even if the segments are rich.

**Option C: Hybrid (RECOMMENDED)**

Use embedding proximity as the primary clustering mechanism (preserving memory-layer agnosticism), but use graph connectivity as a secondary signal that refines thread quality.

```
Step 1: Cluster by embedding similarity (current kNN + Union-Find)
         → produces candidate threads

Step 2: For each candidate thread, check if L3 edges exist between member nodes
         → if edges exist, boost confidence and annotate thread with edge types
         → if no edges exist, thread is valid but lower-confidence

Step 3: Use edge types to inform state classification
         → contradicts/unresolved_tension edges within thread → evaluating signal
         → depends_on chains with missing resolution → stalled signal
         → supports chains leading to decision node → decided signal
```

### Implementation for V1

Modify `detect-threads.ts` to add a post-clustering graph enrichment step:

```typescript
// After Union-Find clustering produces candidate threads:
function enrichWithGraphSignals(db: Database.Database, thread: Thread, memberNodeIds: string[]): GraphSignals {
  if (memberNodeIds.length < 2) return { hasEdges: false, edgeTypes: [], graphConfidenceBoost: 0 };

  const placeholders = memberNodeIds.map(() => '?').join(',');
  const edges = db.prepare(`
    SELECT edge_type, COUNT(*) as count FROM edges
    WHERE from_node IN (${placeholders}) AND to_node IN (${placeholders})
    GROUP BY edge_type
  `).all(...memberNodeIds, ...memberNodeIds) as { edge_type: string; count: number }[];

  const edgeTypes = edges.map(e => e.edge_type);
  const graphConfidenceBoost = edges.length > 0 ? 0.15 : 0;

  return { hasEdges: edges.length > 0, edgeTypes, graphConfidenceBoost };
}
```

Modify `classify-state.ts` to use graph signals:

```typescript
// Add to ClassificationSignals:
export interface ClassificationSignals {
  // ... existing fields ...
  graph_edge_types: string[];           // L3 edge types within thread
  has_contradiction_edges: boolean;     // contradicts/unresolved_tension
  has_dependency_chain: boolean;        // depends_on without resolution
  has_support_chain: boolean;           // supports leading to decision
}
```

### The verdict

**Embedding proximity is the foundation. Graph connectivity is the enrichment layer.**

This preserves memory-layer agnosticism (V3 strategy) while using graph structure when available to improve thread quality and state classification. The graph enrichment is additive — if L3 is swapped out, thread detection degrades gracefully (lower confidence, fewer state signals) rather than breaking entirely.

---

## Build Priority (for Claude Code)

### Phase 4A: Thread Detection Enhancement — DONE (2026-03-28)
1. ✅ kNN + Union-Find clustering (already built)
2. ✅ Graph enrichment post-step (hybrid approach) — `graph-enrichment.ts`
3. ✅ `graph_confidence_boost` applied to thread confidence
4. ✅ `edge_types_within` stored as JSON on thread record

### Phase 4B: State Classification Enhancement — DONE (2026-03-28)
1. ✅ Rule-based classification (already built)
2. ✅ Graph edge signals: contradicts/unresolved_tension → evaluating, depends_on unresolved → stalled
3. ✅ Delivery columns added: `delivery_score`, `dismissed_count`, `acted_count`, `last_surfaced_at`, `edge_types_within`, `action_category`

### Phase 4C: Evaluation Gate — DONE (2026-03-28)
1. ✅ Created `engine/l4/evaluate-delivery.ts` (Sumimasen gate)
2. ✅ Rule-based V1: 48h cooldown, 7-30d stall window, recency filter, cross-source boost, cap 5/cycle
3. ✅ Wired into pipeline between classify and infer stages

### Phase 5A: Structured Next-Step Inference — DONE (2026-03-28)
1. ✅ Updated `infer-next-step.ts` with OmniActions 7-category CoT prompt
2. ✅ Added `action_category` to `NextStepResult` type + parsing from `[CATEGORY]` prefix
3. ✅ Created `delivery_events` table + CRUD + PPP metrics in store.ts
4. ✅ Pipeline logs delivery events after inference

### Phase L3-2: Entity Resolution — DONE (2026-03-29)
1. ✅ Entity resolution via hybrid search (vec kNN + BM25 + RRF) to find cross-source node matches
2. ✅ `resolves_to` edges created between nodes referring to the same entity across different source apps
3. ✅ 1,072 cross-source edges created; cross-app detectable threads increased from 4 → 16
4. ✅ Feeds directly into L4 graph enrichment step — entity edges boost thread confidence + enable cross-source clustering

### Phase 5B: Evaluation Suite — NEXT
1. **NEW:** Create `engine/eval/eval-l4.ts` modeled on MEMTRACK methodology
2. Manually label 20-30 threads from Brian's data as ground truth
3. Measure detection accuracy, state accuracy, next-step relevance

### Deferred to V2+ (DO NOT BUILD NOW)
- Working memory cognitive load model (ProMemAssist — needs real-time input)
- Multi-objective RL training loop (PPP — needs hundreds of delivery events)
- Persona type classification (PPP UserVille — needs multiple users)
- Continuous parallel thought generation (Inner Thoughts — needs event-driven architecture)
- Full MEMTRACK simulation benchmark (needs synthetic event generation)
- Adaptive Sumimasen threshold from dismiss/act signals (needs delivery event data first)

---

## New Schema Summary (all additions for V1)

```sql
-- Thread delivery tracking
ALTER TABLE threads ADD COLUMN delivery_score REAL DEFAULT 0.0;
ALTER TABLE threads ADD COLUMN dismissed_count INTEGER DEFAULT 0;
ALTER TABLE threads ADD COLUMN acted_count INTEGER DEFAULT 0;
ALTER TABLE threads ADD COLUMN last_surfaced_at TEXT;
ALTER TABLE threads ADD COLUMN edge_types_within TEXT DEFAULT '[]';
ALTER TABLE threads ADD COLUMN action_category TEXT;

-- Delivery event log (PPP training signal collection)
CREATE TABLE IF NOT EXISTS delivery_events (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  thread_id TEXT NOT NULL REFERENCES threads(id),
  next_step TEXT NOT NULL,
  action_category TEXT,
  delivery_score REAL,
  user_response TEXT CHECK(user_response IN ('acted', 'dismissed', 'ignored', 'deferred')),
  response_at TEXT,
  delivered_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_delivery_thread ON delivery_events(thread_id);
CREATE INDEX IF NOT EXISTS idx_delivery_response ON delivery_events(user_response);
```

---

## Files Created (2026-03-28 / 2026-03-29)

| File | Purpose | Status |
|---|---|---|
| `engine/l4/evaluate-delivery.ts` | Sumimasen gate — decides which threads are worth surfacing (ProMemAssist) | ✅ Built |
| `engine/l4/graph-enrichment.ts` | Post-clustering graph signal extraction (Graphiti abstraction boundary) | ✅ Built |
| `engine/l3/entity-resolution.ts` | Graphiti entity resolution — cross-source edge creation via hybrid search | ✅ Built |
| `engine/l3/run-entity-resolution.ts` | CLI runner for standalone entity resolution | ✅ Built |
| `docs/SEGMENTATION_FRAMEWORK.md` | Research-backed segmentation framework (source-adaptive thresholds + metadata enrichment) | ✅ Built |
| `engine/eval/eval-l4.ts` | L4 evaluation suite modeled on MEMTRACK | Not yet |

## Files Modified (2026-03-28 / 2026-03-29)

| File | Change | Status |
|---|---|---|
| `engine/l4/types.ts` | Added `ActionCategory`, `GraphSignals`, `DeliveryEvent`, extended `Thread` + `ClassificationSignals` | ✅ Done |
| `engine/l4/schema.ts` | Added `delivery_events` table + 6 delivery columns on `threads` via safe migration | ✅ Done |
| `engine/l4/store.ts` | Added `insertDeliveryEvent`, `recordDeliveryResponse`, `getDeliveryEvents`, `getPPPMetrics` | ✅ Done |
| `engine/l4/detect-threads.ts` | Hybrid detection (nodes + segments) with graph-edge merging post-clustering | ✅ Done |
| `engine/l4/classify-state.ts` | Added graph edge signals (contradiction → evaluating, dependency → stalled) | ✅ Done |
| `engine/l4/infer-next-step.ts` | Replaced prompt with OmniActions 7-category CoT, parses `[CATEGORY]` prefix, accepts gated thread IDs | ✅ Done |
| `engine/l4/run-l4-pipeline.ts` | Added Stage 0 entity resolution; rewired to detect → classify → evaluate gate → infer. Logs delivery events. Writes `l4-progress.json`. | ✅ Done |
| `engine/l4/graph-enrichment.ts` | Bug fix: `edge_type` → `relationship` column name | ✅ Done |
| `engine/graph/smart-split.js` | Added `splitGmail`, `splitAppleNote`, `splitIMessage` source-specific splitters | ✅ Done |
| `engine/graph/build-segments.js` | All source types supported; per-source thresholds for segment length | ✅ Done |

---

## Research Sources

- **ProMemAssist:** [arXiv:2507.21378](https://arxiv.org/abs/2507.21378) — UIST 2025
- **OmniActions:** [arXiv:2405.03901](https://arxiv.org/abs/2405.03901) — CHI 2024
- **Inner Thoughts:** [arXiv:2501.00383](https://arxiv.org/abs/2501.00383) — CHI 2025
- **PPP / UserVille:** [arXiv:2511.02208](https://arxiv.org/abs/2511.02208) — CMU, November 2025
- **MEMTRACK:** [arXiv:2510.01353](https://arxiv.org/abs/2510.01353) — Patronus AI, NeurIPS 2025
- **Anthropic Harness:** [anthropic.com/engineering/effective-harnesses-for-long-running-agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- **Anatomy of Agentic Memory:** [arXiv:2602.19320](https://arxiv.org/abs/2602.19320) — February 2026 survey

---

*This document supersedes informal notes about L4 research integration. For L4 concept definitions, see `private/strategy/01_CORE_ENGINE.md`. For current L4 code, see `engine/l4/AGENTS.md`.*
