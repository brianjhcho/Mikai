# MIKAI — Foundations

> **Consolidated from:** `EPISTEMIC_DESIGN.md`, `EPISTEMIC_EDGE_VOCABULARY.md`, `L4_RESEARCH_INTEGRATION.md`, `SEGMENTATION_FRAMEWORK.md` (Pass 2, 2026-04-16)
> **Authoritative for:** the epistemic content-type framework, the node/edge vocabulary specification, the L4 build spec (five-paper research integration), and the source-adaptive segmentation framework.

This doc holds MIKAI's philosophical and design foundations. It should be read before modifying the extraction prompt, before adding new node or edge types, before designing the evaluation framework, or before changing segmentation.

---

## §1 — Three content types and neuroscience grounding

MIKAI's build decisions have two types of grounding. Some are pragmatic: which database, what API shape, how to chunk text. Others are epistemic: what is a "person" in data terms, what makes a graph node meaningful, how should the system treat a one-line fragment vs. a processed reflection. This section holds the second type.

### The epistemic problem — three content types

Not all content in a personal corpus is epistemically equivalent. The extraction layer must treat them differently or it collapses meaningful signal into noise.

**Type 1 — The Fragment.** *Example: "Can we get food costs down so we can subsidize labor and rent costs."* A single associative spark — a connection fired between two concepts without development. A neuron firing, not a thought. Not a belief, not a project, not a conclusion. Store it; weight it low; look for recurrence across time. Wrong treatment: extracting it as a project node. One mention does not constitute an intent.

**Type 2 — The Structured Ideation.** *Example: "Vehicle and robot causeways should be separate from pedestrian... creating villages and areas of culture rather than individual restaurants..."* Developed enough to indicate genuine engagement — multiple connected ideas, a proposed system, aesthetic preferences embedded in functional reasoning. A working hypothesis, active not settled. Extract as a concept cluster with internal relationships; weight as "active hypothesis"; flag for recurrence checking. Wrong treatment: treating it with the same weight as a processed reflection. Structure indicates engagement, not resolution.

**Type 3 — The Processed Reflection.** *Example: "I've failed as a leader. I see the emotional patterns Patrick and you have developed... I'm not making you and Patrick better, I'm making you more dysfunctional humans..."* Qualitatively different. Contains named evidence, a causal theory, a proposed corrective action, emotional processing of contradiction. The person has already done the synthesis work — the system is reading a concluded thought, not inferring one. A belief update. The highest-signal content in any personal corpus. Extract as a decision or tension node with high confidence weight. Wrong treatment: weighting it equally with fragments. A 400-word processed reflection with specific evidence and named people outweighs a hundred article saves on the same topic.

### Three neuroscience principles

These aren't metaphors — they have concrete implementation implications.

**1. Memory consolidation is reconstruction, not storage.** Every time you recall something, you reconstruct it from fragments and update it in the process. Memories recalled frequently become more accurate and integrated. Memories never recalled degrade and distort. Implication for MIKAI: the graph should not be a static snapshot. It should be a living reconstruction that updates every time a query touches a node. Concepts queried frequently get edges strengthened; concepts never recalled decay. What this rules out: a "write once, read many" architecture.

**2. Episodic vs. semantic memory are distinct systems.** Neuroscience distinguishes episodic memory (specific events — *"what I wrote on December 3rd, in this emotional state, about these named people"*) from semantic memory (generalized knowledge — *"I believe X about leadership"*). A personal notes corpus contains both. They need different treatment: episodic carries timestamps and context, trajectory and change over time; semantic carries confidence scores that update, stable identity structure. What extraction must do: distinguish time-bound reflection ("this happened with Patrick in December") from generalized belief extracted from it ("I tend to damage the people I lead"). Both belong in the graph — as different node types with different update logic. What this rules out: a flat graph where a dated journal entry and a recurring principle are stored identically.

**3. The self-model is constructed, not discovered.** The brain does not have a stable "self" that generates behavior. It constructs a self-model in real time from available evidence — memories, bodily states, social feedback, ongoing experience — and that model is constantly being revised. Implication: MIKAI is not trying to *discover* who Brian is. It's building a model that approximates *how Brian constructs himself*. The December leadership reflection is valuable not because it reveals stable truth — it's valuable because it shows the self-model being actively revised: *"I thought I was a good leader → new evidence contradicts this → updating model."* A system that tracks these revision events — when the self-model changed and what caused it — is doing something qualitatively different from a system that aggregates static beliefs. What this rules out: treating all graph nodes as equally stable facts.

### How to transform a corpus into a person-graph

- **Classify epistemic type before extracting.** Fragment, structured ideation, or processed reflection. Each gets a different extraction prompt and a different confidence weight.
- **Distinguish episodic from semantic content.** Episodic: timestamps + context fields. Semantic: confidence scores that compound across the corpus.
- **Track self-model revision events.** When content shows belief update ("I used to think X, now I think Y because Z"), extract as a revision event. Highest-value nodes in the graph.
- **Weight by recurrence, not just content.** A concept across five notes over six months is more central than a concept in one rich note. A fragment that recurs becomes a pattern; a pattern that recurs becomes a belief.
- **Let recall queries update the graph.** Searches that find satisfying results strengthen edges. Searches that fail reveal gaps.

### The epistemic advantage — why this matters strategically

Facebook treats all behavioral signals as equivalent inputs to a single preference model. The model doesn't distinguish what you chose deliberately from what you clicked by accident, or a belief you hold deeply from content that triggered a reflex. This produces a model of **reactivity**, not **reasoning**.

MIKAI's corpus contains three signal types Facebook structurally cannot access:

| Signal Type | Source | What It Tells You |
|-------------|--------|-------------------|
| **Reactive** | Clicks, dwell time, saves | What triggers your attention |
| **Reflective** | Written notes, processed reflections | What you have concluded after internal reasoning |
| **Generative** | Things you create, not consume | What you are actively building toward |

A deeply processed reflection about leadership failure is orders of magnitude more informative than a hundred article saves on the same topic. The moat is not passive capture per se — it is the ability to distinguish reactive signal from reflective and generative signal, and build a graph that weights them accordingly.

### The ethical constraint

What is being built — if fully realized — is closer to a computational model of identity than a knowledge management tool. The consent architecture must be first-class, not an afterthought. The user should be able to look at any node in their graph and understand exactly how it got there, what source it came from, what confidence it carries, and how to remove it. Transparency at the node level is what distinguishes MIKAI from surveillance.

---

## §2 — Node and edge vocabulary

This section is the full vocabulary specification. It is open for adoption by other memory systems. Preserve Section headers verbatim — this doc will be grep'd.

### Motivation

Flat fact storage — key-value, vector-only — cannot represent the structure of reasoning. Consider:

- "User prefers Python." (a fact)
- "User is deciding between Python and Rust — wrote positively about Rust's memory safety last week but chose Python for a prototype yesterday, suggesting the decision is unresolved." (a reasoning structure)

A vector-only system retrieves both but cannot distinguish a settled belief from an active contradiction. The epistemic edge vocabulary adds typed relationships that capture not just what someone believes, but *how they believe it* — whether they are conflicted, whether they are investigating, whether one belief is becoming invalidated by new evidence. The highest-value signal in personal knowledge work is often not where thinking is settled but where it is unresolved.

### Node Types

| Type | Definition | When to Use | When NOT to Use | Examples |
|------|-----------|------------|-----------------|----------|
| **concept** | A belief, idea, or mental model the person holds | Working hypothesis, recurring principle, general idea | Temporary fragments or fleeting thoughts with one mention only | "Passive capture is the moat, not a convenience feature" / "Self-model is constructed in real-time from available evidence, not discovered" |
| **question** | An open question the person is actively investigating | Source explicitly shows probing, testing, or resolving | Rhetorical questions or questions already answered elsewhere | "Does the extraction prompt generalize beyond my writing style?" / "What is the minimum corpus threshold for meaningful inference?" |
| **decision** | A resolved choice with reasoning attached | Source shows concluding after deliberation with reasoning chain | Assumptions, hypotheses, or choices that later evidence contradicts | "Use Supabase only — no separate vector DB" / "MCP is the sole product surface in Phase 1" |
| **tension** | An active contradiction held without resolution | Two incompatible beliefs or goals the person is actively managing together | Resolved contradictions (those become two separate nodes linked by `contradicts`) | "Engine-first vs distribution-first — when does the surface decision become blocking?" / "Trust over engagement is the right optimization target, but monetization strategy is undefined" |
| **project** | An ongoing initiative or goal | Actively building toward, with evidence of repeated action or refinement | Ideas mentioned once or aspirational goals with no demonstrated commitment | "Build MIKAI's MCP server for Claude Desktop" / "Develop the three-layer memory architecture" |

> **Voice-mismatch footnote (O-035):** This taxonomy was validated on Brian's reflective, framework-heavy corpus. NOONCHI_STRATEGIC_ANALYSIS raises the concern that the vocabulary may have been tuned to this voice — that tensions and decisions are abundant in reflective writing but rare in task-oriented sources (iMessage, Gmail, calendar), and that an L4 task-state layer may need a different, activity-oriented extraction pass. The taxonomy stands; the risk is that it may not be load-bearing for L4. See VISION.md §2 for the same flag, OPEN.md for the resolution path.

### Node Type Misclassifications — Common Pitfalls

**concept vs question.** "I wonder if passive capture is the moat" appearing in a section that goes on to explain why it isn't — this is not a question; the person has concluded. Extract as a concept. A true question is "Does my extraction prompt generalize beyond my writing?" where the person hasn't yet worked through the answer.

**decision vs concept.** "I've decided X" feels like a decision, but if the decision is theoretical (not yet acted on) and the reasoning is incomplete, it may be a concept. A true decision has reasoning trace and appears at the end of deliberation. "I'll use Supabase only" after weighing Graphiti, Neo4j, and Postgres is a decision. "Supabase seems good" in early exploration is a concept.

**tension vs two nodes linked by contradicts.** A tension node means the person is actively holding both beliefs, managing the conflict. If instead the source shows "I used to think distribution first, but now I believe engine-first is right," this is two nodes (old belief, new belief) linked by `contradicts` with a `valid_from`/`expired_at` timestamp.

**project vs decision.** "I've decided to build MIKAI's MCP server" is a decision. "I'm building MIKAI's MCP server — integrated with Claude Desktop, 8 tools, handling Track C synthesis" is a project. Projects have ongoing refinement and evidence of repeated action. Decisions are moments of commitment. A decision can spawn a project.

### Edge Types

All edges carry a required `note` field (free-form plain language) that explains the specific relationship. The note is what makes edges legible to both humans and AI during synthesis.

| Edge Type | Priority | Definition | Crucial Distinction | Directionality | Example |
|-----------|----------|-----------|---------------------|-----------------|---------|
| **unresolved_tension** | 0 (highest) | Internal conflict the person is actively holding — both beliefs simultaneously active, no clear resolution path | vs **contradicts**: unresolved_tension is internal holding (two nodes both active); contradicts is structural conflict (one may supersede the other). Tensions are psychology; contradicts is logic. | Bidirectional — if A and B are in tension, the relationship is symmetric | User believes "engine work is critical" AND "distribution is critical" simultaneously. Note: "User recognizes both are essential but unclear which constraint is blocking." |
| **contradicts** | 1 | Structural contradiction — one may supersede, or they represent different time periods | vs **unresolved_tension**: contradicts is structural (logically incompatible); unresolved_tension is psychological (both held active). | Directional — from old/challenged to new/challenging. Can carry valid_from / expired_at | Old: "Python best for prototypes" (expired_at=date), contradicts new: "Rust for memory safety" (valid_from=date). Note: "New evidence from safety-critical prototype triggered belief update." |
| **depends_on** | 2 | Node A cannot be resolved without Node B | vs **partially_answers**: depends_on means B is a prerequisite; partially_answers means B addresses part of A but doesn't resolve it | Directional — from dependent (A) to prerequisite (B). One-way causal chain | Decision "Use Supabase only" depends_on resolved question "Will Neo4j scale to 100k nodes?" |
| **partially_answers** | 3 | Node A addresses part of Node B but doesn't fully resolve it | vs **depends_on**: partially_answers is partial resolution; depends_on is a blocker | Directional — from answering (A) to questioned (B) | Concept "Temporal edges with valid_from/expired_at capture belief revision" partially_answers question "How do we track when beliefs change?" |
| **supports** | 4 | Node A provides evidence or reasoning for Node B | vs **extends**: supports is evidential (A justifies B); extends is developmental (A builds on B). | Directional — from evidence (A) to supported (B) | Concept "Recurrence signal is stronger than single-mention signal" supports decision "Weight multi-source evidence higher than single-source." |
| **extends** | 5 (lowest) | Node A builds on Node B without contradiction | vs **supports**: extends is structural building (A develops B further); supports is evidential (A justifies B). | Directional — from extending (A) to extended (B) | Concept "Epistemic edge typing" extends concept "Graph-based knowledge representation." |

### Edge Priority Ordering Rationale

The priority ordering is not arbitrary. Retrieval expands from vector-seeded nodes via one-hop edges in priority order. Edges are returned in this sequence:

1. **unresolved_tension (0)** — highest because unresolved thinking is the signal. If you want to know what someone is actually thinking about, ask about their tensions.
2. **contradicts (1)** — contradiction indicates change. When someone updates a belief, the old and new nodes are both informative — the edge between them tells you the trajectory.
3. **depends_on (2)** — dependencies show the structure of reasoning.
4. **partially_answers (3)** — partial answers are less valuable than full answers but more selective than support edges.
5. **supports (4)** — valuable but abundant. Too much support-edge retrieval produces unfocused results.
6. **extends (5)** — weakest relationship, lowest priority.

This ordering implements a hypothesis: **in synthesis, the most valuable signal is where thinking is unresolved, not where it is settled.** An AI fed a subgraph biased toward tensions, contradictions, and dependencies will ask better questions than one fed a subgraph dominated by supportive evidence.

### Extraction Quality Standard

A good extraction from a personal reflection should produce:

- **At least 2 tension or question nodes out of 5–7 total.** If every node is a concept or decision, extraction has drifted to summarization.
- **Content fields in first-person.** "I've concluded that passive capture alone isn't enough" — not "The author believes..."
- **Every edge has a note field explaining the relationship.** "contradicts" with no note is useless.
- **Revision events are captured.** When a source shows belief updating, extract as two nodes (old, new) linked by `contradicts` with a note and temporal metadata.

**Anti-pattern:** dense passages of reasoning extracted as a single concept node. A 400-word reflection on leadership failure should produce at least 3 nodes (old self-model, new self-model, supporting evidence concept) linked by edges showing the revision sequence.

### Implementation Notes

**Schema.** Nodes carry `id`, `label`, `content`, `node_type`, `embedding` (1024-dim from Voyage), `confidence`, `source_id`, `created_at`, `updated_at`. Edges carry `from_node_id`, `to_node_id`, `relationship`, `note` (required for `unresolved_tension` and `contradicts`), `weight`, `valid_from`, `expired_at`, `created_at`.

**Retrieval.** Embed query → top-5 vector-similar nodes → one-hop expansion in priority order → cap 15 nodes total → serialize with note fields for explanation.

**Tier 1 Contradiction Detection (zero LLM).** Embed new segment → find similar graph nodes (cosine > 0.75) → check for negation signals in text ("not", "wrong", "actually", "changed my mind", "I used to think") → if detected, flag for Tier 2 conflict resolution (one LLM call to determine if revision or held tension).

**Tier 1 Recurrence Detection (zero LLM).** Embed new segment → query segments for similar content (cosine > 0.85) from DIFFERENT sources → if found from 3+ sources across 2+ weeks, flag as recurring pattern → trigger Tier 2 promotion (one LLM call to generate node label and classify type).

**Model-agnostic design.** The vocabulary is model-agnostic: Claude, ChatGPT, Cursor, any LLM with graph traversal capability. The spec defines the *structure* of reasoning relationships, not how a specific model consumes them.

---

## §3 — L4 build spec

L4 is MIKAI's product layer: thread detection, state classification, next-step inference, intention-behavior gap detection. It sits above the `L3Backend` port (D-041). This section is the research-to-build bridge.

### The five papers and what they solve

Each paper solves one component of the L4 pipeline. None builds the complete system. MIKAI's job is to assemble them.

```
MIKAI L4 Pipeline:
  detect-threads → classify-state → [EVALUATION GATE] → infer-next-step → [DELIVERY]
  ──────────────   ───────────────   ────────────────   ────────────────   ──────────
                                     (ProMemAssist)                        (Inner Thoughts)
                                     (PPP training)                        (PPP training)
```

**Paper 1 — ProMemAssist (UIST 2025, arXiv:2507.21378).** Solves *when to deliver* (the Sumimasen timing gate). Models working memory as a bounded buffer (~4±1 items) with three degradation mechanisms: displacement (new information pushes out old), interference (modality overlap × semantic distance), recency decay (exponential). Timing: `utility(message) = value(message) - cost(displacement) - cost(interference)`. Deliver only when utility > threshold; threshold adapts on dismiss/act feedback. V1 implementation: rule-based proxy using cross-app activity patterns as cognitive load indicator (rapid app switching → don't interrupt; long idle period after active research → potential stall, good time; morning delivery window; max 3 items/cycle).

**Paper 2 — OmniActions (CHI 2024, arXiv:2405.03901).** Solves *what to recommend* (structured action prediction). Defines 7 general action categories — **Search, Create, Capture, Share, Schedule, Navigate, Configure** — derived from a 382-entry diary study with 39 participants. Chain-of-thought prompt: (1) general action category, (2) specific action, (3) concrete next step with details. Next-step inference uses this CoT structure. Action-category alignment with thread state: exploring → Search/Navigate; evaluating → Search/Create; decided → Create/Share; acting → Create/Share/Schedule; stalled → any action that unblocks.

**Paper 3 — Inner Thoughts (CHI 2025, arXiv:2501.00383).** Solves *the cognitive loop* for proactive delivery. Five-stage continuous reasoning loop grounded in SOAR/ACT-R: **Trigger → Retrieval → Thought Formation → Evaluation → Participation.** Mapped to MIKAI: trigger = cross-app activity detected; retrieval = L2 segments + L3 subgraph + thread context via the port; thought formation = re-run state classification for the affected thread; evaluation = Sumimasen gate (the critical stage — proactive systems that surface every inference are annoying; one that evaluates before speaking is useful); participation = surface via MCP or notification. V1 pipeline: `detect → classify → evaluate → infer (only for gated threads)`.

**Paper 4 — PPP (CMU, November 2025, arXiv:2511.02208).** Solves *how to train the delivery system*. Three joint optimization objectives: **Productivity** (act_count / surface_count), **Proactivity** (proactive_surface_count / total), **Personalization** (1 - dismiss_count / surface_count). UserVille: 20 persona types with varying preferences (communication style, interruption tolerance, autonomy, detail level). Key finding: optimizing productivity alone hurts proactivity and personalization — must optimize jointly. V1 implementation: collect the signal via a `delivery_events` table with `user_response ∈ {acted, dismissed, ignored, deferred}`. Defer the RL training loop until hundreds of delivery events per user exist.

**Paper 5 — MEMTRACK (Patronus AI, NeurIPS 2025, arXiv:2510.01353).** Solves *how to evaluate L4*. Simulates a software org with interleaved events across Slack, Linear, Git. Cross-platform dependencies, temporal ordering, deliberate contradictions. Three metrics: correctness (0–100%), efficiency (tool calls/lookups), redundancy (duplicate storage). Key result: GPT-5 scores 60% correctness; adding Mem0 or Zep does NOT significantly improve. Memory infrastructure alone doesn't solve cross-platform state tracking — the L4 layer is required. V1 implementation: manually label 20–30 threads from Brian's data as ground truth; measure detection accuracy (precision/recall), state classification accuracy, next-step relevance (1–5 rating).

### Anthropic's harness pattern

For state persistence across L4 pipeline runs. Three artifacts: (1) `l4-progress.json` — append-only log of what was accomplished; (2) thread state — structured tracking (`exploring`, `evaluating`, `decided`, `acting`, `stalled`, `completed`); (3) git-style commit log — `thread_transitions` table as temporal checkpoints. Pipeline run = startup ritual: read current state, verify, advance. State changes are logged as transitions with reasons (audit trail).

### The critical architecture decision — embedding proximity vs. graph connectivity

Should threads be defined by embedding proximity (segments with similar embeddings cluster), graph connectivity (nodes connected by L3 edges cluster), or hybrid? **Hybrid, with embedding as primary.** Embedding is memory-layer-agnostic (preserves the `L3Backend` port abstraction — swap the adapter, threads still work) and cross-source by default. Graph connectivity refines thread quality as a secondary signal: if L3 edges exist between thread members, boost confidence and annotate the thread with edge types. Thread state classification uses these edge types (contradicts/unresolved_tension within thread → evaluating; depends_on chain unresolved → stalled; supports chain leading to decision → decided). Graph enrichment is additive — if L3 is swapped, detection degrades gracefully rather than breaking.

### Hypothesis — state classification may be rule-based (zero LLM)

If state transitions (exploring → evaluating → decided → acting → stalled → completed) are detectable from temporal activity patterns + simple heuristics, the cost stays near zero. Only next-step inference would need LLM synthesis. Detection rules:

- Multiple sources, no decisions → exploring
- Comparison language, pros/cons → evaluating
- Decision language + no behavioral follow-through → decided
- Active edits/drafts/bookings in progress → acting
- Activity drop-off after acting → stalled
- Behavioral confirmation (booking email, merge commit) → completed

This is O-036. Target: if rule-based accuracy > 80%, keep LLM to a single call per thread for next-step inference only.

### Build priority

- Thread detection (kNN + Union-Find clustering) with graph-enrichment post-step — done on the L4 prior build (SQLite era). Needs porting to `L3Backend`.
- State classification (rule-based + graph edge signals) — same.
- Evaluation gate (Sumimasen: 48h cooldown, 7–30d stall window, recency filter, cross-source boost, cap 5/cycle) — same.
- Structured next-step inference (OmniActions 7-category CoT, Haiku) — same.
- Evaluation suite (MEMTRACK methodology, 20–30 labeled threads) — next.

Deferred to V2+: working-memory cognitive load model, multi-objective RL training, persona type classification, continuous parallel thought generation, full MEMTRACK simulation, adaptive Sumimasen threshold.

### Research sources

- ProMemAssist: arXiv:2507.21378 (UIST 2025)
- OmniActions: arXiv:2405.03901 (CHI 2024)
- Inner Thoughts: arXiv:2501.00383 (CHI 2025)
- PPP / UserVille: arXiv:2511.02208 (CMU, November 2025)
- MEMTRACK: arXiv:2510.01353 (Patronus AI, NeurIPS 2025)
- Anthropic harness: anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Anatomy of Agentic Memory: arXiv:2602.19320 (February 2026 survey)

---

## §4 — Source-adaptive segmentation

L4 requires cross-app thread detection. In the SQLite-era implementation, L4 detected 1,640 threads but 99.3% were single-source because gmail (50 segments), apple-notes (123), and imessage (~6) were drastically under-segmented compared to perplexity (14,946) and claude-thread (4,705). Three compounding failures:

1. **Source exclusion.** Gmail and iMessage were excluded from the default segment allowlist.
2. **Global word threshold.** A 500-word minimum killed 75% of gmail (264/461 sources are <500 words) and 100% of Apple Notes (largest note: 122 words).
3. **No source-adaptive splitters.** No `splitGmail()` or `splitIMessage()` — they fell through to `splitGeneric()`, which was designed for long documents.

### How comparable systems solve this

- **Pattern 1 — canonical schema per source type (Celonis / OCEL 2.0).** Normalize heterogeneous sources into a canonical unit. No minimum content threshold — value is in the link to other events, not content volume. Each source gets its own adapter that produces units of comparable *information density*, not comparable *length*.
- **Pattern 2 — metadata enrichment before embedding (Anthropic Contextual Retrieval, Sept 2024).** Prepending a 50–100 token context summary before embedding reduces retrieval failure by **49%**; combined with BM25, **67%**. Short texts cluster in a different embedding region than long texts about the same topic (Jina AI size bias) — metadata enrichment brings short texts up to ~100+ tokens, substantially reducing this bias.
- **Pattern 3 — aggregate upward, never discard.** Glean aggregates Slack messages into conversation windows (5–10 messages = 1 chunk). Dust flags orphan pages but retains them. Linear attaches short issue comments to parent issues. No surveyed system drops content because it's short — the unit of retrieval adapts.
- **Pattern 4 — three cross-source linking mechanisms.** Hub-and-spoke (Linear: Issue aggregates PR + Slack thread + design doc), identity graph resolution (Glean: same person across systems via email/username alias), structural normalization (Activity Streams 2.0: Actor → Verb → Object → Target).
- **Pattern 5 — multi-scale indexing (AI21, 2025–2026).** Index at 128, 256, 512 token granularities simultaneously; each retrieved chunk votes for its parent doc; RRF aggregates. 1–37% recall improvement over single-scale.

### The framework — source-adaptive segment strategy

Every segment, regardless of source, produces a canonical record with:

- `source_id`, `source_type`
- `topic_label` (human-readable)
- `enriched_content` (metadata prefix + processed content — this is what gets embedded)
- `processed_content` (raw content for display)
- `participants` (people involved; anonymized for imessage)
- `action_verbs` (already extracted in sync scripts)
- `temporal_anchor` (ISO timestamp)
- `information_type` ∈ {research, reflection, transaction, conversation, action}

The `enriched_content` field is what gets embedded. Metadata enrichment happens at segmentation time, not retrieval time.

### Per-source adapter configuration

| Source | Min Words | Splitter | Enrichment Prefix | Information Type |
|--------|----------|---------|-------------------|-----------------|
| perplexity | 30 | `splitPerplexityThread` | `[Research] Query: {topic} \| Source: Perplexity \| Date: {date}` | research |
| claude-thread | 15 | `splitClaudeThread` | `[Conversation] Topic: {topic} \| Source: Claude \| Date: {date}` | research |
| manual | 20 | `splitMarkdown` | `[Document] Title: {label} \| Date: {date}` | reflection |
| **gmail** | **15** | **`splitGmail` (NEW)** | `[Email] Subject: {subject} \| From: {from} \| To: {to} \| Date: {date}` | transaction |
| **apple-notes** | **10** | **`splitAppleNote` (NEW)** | `[Note] Title: {label} \| Date: {date}` | reflection |
| **imessage** | **20** | **`splitIMessage` (NEW)** | `[Message] Participants: {contacts} \| Date: {date}` | conversation |

**Splitter designs.** `splitGmail`: one email = one segment (emails are atomic; don't split them — enrich them). `splitAppleNote`: one note = one segment (reflective fragments, short by nature). `splitIMessage`: conversation windows (messages within 2 hours = one segment; gap > 2h = new segment; minimum 2 messages; participants anonymized in metadata).

**Why 10–30 words, not 500.** Apple Notes average 50–120 words; the 500-word threshold eliminates 100%. A gmail "Your Kenya Airways flight is confirmed. Reference KQ-7382." is 14 words but contains the behavioral signal that links to the Perplexity "Kenya trip research" thread — the metadata prefix carries the embedding signal.

### Impact on thread detection

```
Before:  14,946 perplexity : 50 gmail = 299:1 (gmail invisible)
          Cross-app threads: 4 / 1,640 = 0.2%

After:   14,946 perplexity : ~350 gmail = 43:1 (gmail visible)
          Cross-app opportunity: Remitly transfer email + Kenya research in Perplexity + Apple Note about trip planning
```

The metadata enrichment is key: "Kenya" in a gmail subject + "Kenya Airways" in Perplexity + "Kenya trip" in an Apple Note should cluster when all three have metadata-enriched embeddings carrying the topic signal.

**Adjustments to thread detection.** Consider raising the cross-source bonus from 0.08 to 0.12–0.15 (metadata-enriched segments from different sources should match more easily). Add metadata-based linking as secondary signal (shared participant name or <24h temporal proximity lowers the similarity threshold further). Use information type: a `transaction` segment (gmail confirmation) linking to a `research` segment (Perplexity search) is a strong cross-app signal.
