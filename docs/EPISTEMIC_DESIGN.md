# MIKAI: Epistemic & Cognitive Design Foundations
**Document type:** Philosophical design reference — NOT a build document
**Last updated:** March 2026
**Relationship to build docs:** Informs extraction prompt design, graph schema decisions, and evaluation criteria. Does not prescribe implementation.

---

## Why This Document Exists

MIKAI's build decisions have two types of grounding. Some are pragmatic: which database, what API shape, how to chunk text. Others are epistemic: what is a "person" in data terms, what makes a graph node meaningful, how should the system treat a one-line fragment vs. a processed reflection.

This document holds the second type. It should be read before designing the extraction prompt, before defining node and edge types, and before evaluating whether the graph is producing real intelligence or sophisticated filing.

---

## The Epistemic Problem: Three Types of Content

Not all content in a personal corpus is epistemically equivalent. The extraction layer must treat them differently or it collapses meaningful signal into noise.

### Type 1 — The Fragment
*Example: "Can we get food costs down so we can subsidize labor and rent costs"*

A single associative spark — a connection fired between two concepts without development. Epistemically this tells you almost nothing about commitment or belief. It tells you something about the conceptual space the person moves through.

**What it is:** A neuron firing, not a thought.
**What it is not:** A belief, a project, a conclusion.
**Right treatment:** Store it. Weight it low. Look for whether related concepts appear repeatedly across the corpus. Recurrence across time is what elevates a fragment into a pattern.
**Wrong treatment:** Extracting it as a project node. One mention does not constitute an intent.

---

### Type 2 — The Structured Ideation
*Example: "Vehicle and robot causeways should be separate from pedestrian... creating villages and areas of culture rather than individual restaurants..."*

Developed enough to indicate genuine engagement — multiple connected ideas, a proposed system, aesthetic preferences embedded in functional reasoning. The person has tested this against reality enough to articulate it with internal structure.

**What it is:** A working hypothesis. Active, not settled.
**What it is not:** A conclusion or a commitment.
**Right treatment:** Extract as a concept cluster with internal relationships. Weight as "active hypothesis." Flag for recurrence checking.
**Wrong treatment:** Treating it with the same weight as a processed reflection. Structure indicates engagement, not resolution.

---

### Type 3 — The Processed Reflection
*Example: "I've failed as a leader. I see the emotional patterns Patrick and you have developed... I'm not making you and Patrick better, I'm making you more dysfunctional humans..."*

Qualitatively different from the other two. Contains named evidence, a causal theory, a proposed corrective action, and emotional processing of contradiction. The person has revised their self-model based on accumulated evidence. This is the output of an internal reasoning process that already happened.

**What it is:** A belief update. The highest-signal content in any personal corpus.
**What it is not:** A passing thought or hypothesis.
**Right treatment:** Extract as a decision or tension node with high confidence weight. The person has already done the synthesis work — the system is reading a concluded thought, not inferring one.
**Wrong treatment:** Weighting it equally with fragments. A 400-word processed reflection with specific evidence and named people outweighs a hundred article saves on the same topic.

---

## The Neuroscience Grounding

Three principles from cognitive neuroscience that should directly shape the architecture. These are not metaphors — they have concrete implementation implications.

### 1. Memory Consolidation Is Not Storage — It's Reconstruction

The neuroscientific model of memory is not a filing cabinet. Every time you recall something, you reconstruct it from fragments and update it in the process. Memories recalled frequently become more accurate and integrated. Memories never recalled degrade and distort.

**Implication for MIKAI:** The graph should not be a static snapshot of what was captured. It should be a living reconstruction that updates every time a query touches a node.

- A concept queried frequently should have its edges strengthened.
- A concept never recalled should have its weight decay over time.
- The graph stays relevant by simulating biological memory — not by being a perfect archive.

**What this rules out:** A "write once, read many" graph architecture. The graph must be updatable not just by new ingestion but by retrieval patterns.

---

### 2. Episodic vs. Semantic Memory Are Distinct Systems

Neuroscience distinguishes between:
- **Episodic memory:** Specific events — *"what I wrote on December 3rd, in this emotional state, about these named people"*
- **Semantic memory:** Generalized knowledge — *"I believe X about leadership"*

A personal notes corpus contains both. They need different treatment.

| Type | Characteristics | Graph Treatment |
|------|----------------|----------------|
| Episodic | Time-bound, contextual, named people, specific events | Carry timestamps and context. Show trajectory and change over time. |
| Semantic | General beliefs, working models, recurring principles | Carry confidence scores that update. Show stable identity structure. |

**What the extraction prompt must do:** Distinguish between a time-bound reflection ("this happened with Patrick in December") and a generalized belief extracted from it ("I tend to damage the people I lead"). The first is episodic. The second is semantic. Both belong in the graph — but as different node types with different update logic.

**What this rules out:** A flat graph where a dated journal entry and a recurring principle are stored identically.

---

### 3. The Self-Model Is Constructed, Not Discovered

This is the most important and most underappreciated principle. The brain does not have a stable "self" that generates behavior. It constructs a self-model in real time from available evidence — memories, bodily states, social feedback, ongoing experience — and that model is constantly being revised.

**Implication for MIKAI:** The system is not trying to *discover* who Brian is. It is building a model that approximates *how Brian constructs himself*. The December leadership reflection is valuable not because it reveals some stable truth — it is valuable because it shows the self-model being actively revised:

> *"I thought I was a good leader → new evidence contradicts this → updating model."*

A system that tracks these revision events — when the self-model changed and what caused it — is doing something qualitatively different from a system that aggregates static beliefs.

**What this rules out:** Treating all graph nodes as equally stable facts about the person. Some nodes represent current beliefs. Some represent beliefs that have already been revised. The graph needs to distinguish them.

---

## How You Transform a Corpus Into a Person-Graph

Given the three epistemic types and three neuroscience principles, here is what the inference layer must actually do — beyond what standard extraction provides.

### Step 1 — Classify Epistemic Type Before Extracting
Before running extraction, classify each piece of content: fragment, structured ideation, or processed reflection. Each type gets a different extraction prompt and a different confidence weight on the nodes it produces.

A fragment generates low-weight nodes and no project-level extraction.
A processed reflection generates high-weight nodes with the reasoning chain preserved.

### Step 2 — Distinguish Episodic from Semantic Content
Flag whether content is time-bound and contextual (episodic) or general and belief-like (semantic). Episodic nodes carry timestamps and context fields. Semantic nodes carry confidence scores that compound across the corpus.

### Step 3 — Track Self-Model Revision Events
When content shows a person updating their beliefs — "I used to think X, now I think Y because Z" — extract that as a special node type: a **revision event**. These are the highest-value nodes in the graph because they show the direction and rate of change in the person's thinking. Level 2 inference runs on revision events, not static beliefs.

### Step 4 — Weight by Recurrence, Not Just Content
A concept that appears across five notes over six months is more central to the person's identity than a concept that appears in one rich note. The graph must compound signal across the corpus. A fragment that recurs becomes a pattern. A pattern that recurs becomes a belief.

### Step 5 — Let Recall Queries Update the Graph
When the person searches for something and clicks a result, that is a signal. When they search and find nothing satisfying, that is a gap signal — the graph is missing something they are trying to reconstruct. The recall layer feeds the inference layer by revealing what the person is actively trying to access.

---

## The Facebook Comparison: Where It Holds and Where It Breaks

Facebook's data engine works by treating all behavioral signals as equivalent inputs to a preference model. Every like, every dwell time, every share feeds a single optimization target: engagement. The model does not distinguish between what you chose deliberately and what you clicked by accident. It does not distinguish between a belief you hold deeply and a piece of content that triggered a reflex.

This produces a model of **reactivity**, not **reasoning**. Facebook knows what makes you click. It has no idea what you are trying to figure out.

MIKAI's epistemic advantage — if built correctly — comes from distinguishing three signal types:

| Signal Type | Source | What It Tells You |
|-------------|--------|-------------------|
| **Reactive** | Clicks, dwell time, saves | What triggers your attention |
| **Reflective** | Written notes, processed reflections | What you have concluded after internal reasoning |
| **Generative** | Things you create, not consume | What you are actively building toward |

Facebook only has access to reactive signals. MIKAI's corpus contains all three. The graph should weight them in that order. A deeply processed reflection about leadership failure is orders of magnitude more informative about who Brian is than a hundred article saves about leadership.

**The strategic implication:** The moat is not passive capture per se. It is the ability to distinguish reactive signal from reflective and generative signal — and build a graph that weights them accordingly. That distinction is what Facebook structurally cannot make, because making it would require serving the user's reasoning rather than the advertiser's engagement target.

---

## The Core Ethical Constraint

What is being built — if fully realized — is closer to a computational model of identity than a knowledge management tool.

This means the consent architecture must be first-class, not an afterthought. The value proposition is that the user owns the model of themselves. The moment that claim feels hollow, the product collapses.

**The practical form of this:** The user should be able to look at any node in their graph and understand exactly how it got there, what source it came from, what confidence it carries, and how to remove it. Transparency at the node level is not a feature — it is what distinguishes MIKAI from surveillance.

This is the thing Facebook never built and structurally never could — because their interests and the user's interests diverge. MIKAI's thesis is that they are the same.

---

## Open Design Questions (Not Build Questions)

These are unresolved epistemic problems, not implementation gaps. They belong here, not in DECISIONS.md.

**Q-E001: What is the minimum corpus threshold for meaningful inference?**
At what point does the graph become rich enough to produce Level 2 inference? Mem's data suggests the transition happens somewhere between 100-500 notes. MIKAI's typed edges may lower this threshold, but it needs empirical validation.

**Q-E002: How should the graph handle beliefs the person no longer holds?**
A revision event updates the self-model. But the old belief should not be deleted — it is part of the trajectory. What is the right schema for "superseded belief" vs. "current belief"?

**Q-E003: What is the right unit of the graph?**
Currently: nodes are concepts, projects, questions, decisions, tensions. But the neuroscience suggests the most meaningful unit might be the revision event itself — the moment of belief update — not the static belief it produced. This has schema implications.

**Q-E004: How do you evaluate whether the graph is accurate?**
There is no ground truth for a person-graph. Self-evaluation ("does this feel right?") is the only available signal. This is both a validation problem and a product design problem — the UI must make the graph legible enough for the person to evaluate and correct it.

**Q-E005: Where do recurrence-weighting and recall-decay live in the stack?**
Sections 1, 4, and 5 of this document prescribe a graph that strengthens edges on retrieval, decays uncalled concepts, and weights recurrence across the corpus. Graphiti-core (the underlying library) implements *none* of this — it has three timestamps and binary supersession (see Addendum below). The open question: does this behavior get implemented as a layer above Graphiti (a periodic job that writes scores into `EntityEdge.attributes`), as part of L4's thread-state computation, or as a fork of graphiti-core itself? Each path has different blast radius.

---

## Addendum (2026-04-20): What Graphiti-Core Actually Does About Decay

This addendum was added after the MIKAI eval (`docs/evals/run-20260418-103324.md`) surfaced a gap between what this document prescribes and what the underlying library implements. It is recorded here, not in DECISIONS.md, because the gap is epistemic before it is architectural — what to *do* about it depends on which of this document's principles are load-bearing.

### What surfaced

In eval question B1 ("how has my thinking about coffee supply chains evolved between January and April 2026?"), MIKAI returned an arc reconstructed from source-episode reference times — but not from edge bitemporality. Most coffee edges shared `valid_since=2026-03-19T12:52`, the timestamp of a single ingestion batch. Edge timestamps reflected when *the system learned the fact*, not when *Brian wrote it*. This led to the question: doesn't MIKAI track how thoughts evolve?

### What graphiti-core actually has

Investigation of `/usr/local/lib/python3.12/site-packages/graphiti_core/edges.py:263-285` (EntityEdge model) and `utils/maintenance/edge_operations.py:425-460` (`resolve_edge_contradictions`) returned the full mechanism:

**Three temporal fields per edge, no scoring fields:**

| Field | Meaning |
|---|---|
| `expired_at` | System-clock time when edge was invalidated |
| `valid_at` | When the fact became true (asserted, optional) |
| `invalid_at` | When the fact stopped being true (asserted, optional) |

There is **no** `confidence`, `weight`, `score`, `priority`, `recency`, `recurrence_count`, or `last_recalled_at`. The only real-valued field on an edge is `fact_embedding` — used for retrieval similarity, not belief strength.

**Supersession is binary, datetime-driven:**

For each candidate edge, `resolve_edge_contradictions` does pure timestamp comparisons. If a new edge has a later `valid_at` and the windows overlap, the older edge gets `invalid_at = resolved_edge.valid_at` and `expired_at = utc_now()`. Otherwise it's left alone. There is also an LLM-driven step (`resolve_extracted_edge` prompts an LLM with invalidation candidates) — still produces a binary in-or-out decision.

**No decay for uncontradicted edges.** An edge written six months ago that nothing later contradicts stays marked "current" forever. The library has no mechanism that says "this hasn't been touched in N months, downgrade it" or "this concept has been queried 50 times, strengthen its connections."

### Where this conflicts with the prescriptions above

| This document says | Graphiti-core does |
|---|---|
| "A concept queried frequently should have its edges strengthened" (§1) | Nothing. Retrieval is read-only. |
| "A concept never recalled should have its weight decay over time" (§1) | Nothing. Old uncontradicted edges stay "current" indefinitely. |
| "Weight by recurrence, not just content" (§Step 4) | Nothing. Edges have no count, no occurrence weight. |
| "Let recall queries update the graph" (§Step 5) | Nothing. Search is non-mutating. |
| "Beliefs that have already been revised need to be distinguished" (§3, Q-E002) | Partially: `invalid_at`/`expired_at` mark superseded facts, but only the contradiction case is detected — gradual abandonment is invisible. |

In short: graphiti-core models *what was said* and *when contradictions were detected*. It does not model *how strongly the user still holds it* or *how recently they engaged with it*. The neuroscience-grounded model in §1–§3 of this document is, today, vapor at the storage layer.

### Implementation paths (not a decision, just the option space)

Three plausible places this could live, with different blast radius:

1. **Layer above graphiti-core, writing into `EntityEdge.attributes`.** A periodic job (or a sidecar endpoint hook) computes a `recall_score`, `recurrence_count`, `last_seen_at`, and writes them as custom attributes on the edge. Graphiti's storage tolerates arbitrary attributes; nothing in core changes. Lowest blast radius. Highest likelihood that the scores drift out of sync with reality.
2. **Compute it in L4 from `EntityEdge.episodes[]` + `EpisodicNode.valid_at`.** Don't materialize decay scores at all — derive them at query time from the episodes the edge cites and their authorship reference times. No write-side complexity. Slow at scale; needs caching.
3. **Fork graphiti-core to add belief-strength as a first-class field.** Highest blast radius (we're already running a patched copy per the candidate-resolution cap, but adding a scoring field touches the schema and every retrieval query). Most architecturally honest. Cuts off easy upstream merges.

The right answer depends on whether this document's principles (§1, §4, §5) are load-bearing for the product or aspirational. If load-bearing, option 3. If we're shipping L4 first and want to defer the decision, option 2 — derive at query time, materialize later if it becomes a hot path.

### What this implies for the eval rubric

The MIKAI eval's "Confidence calibration" axis is currently scoring whether the *answer* is well-calibrated. It is not scoring whether the *graph* carries calibrated belief weights — because today, no edge in the graph does. Once recurrence-weighting or recall-decay is implemented anywhere in the stack, the rubric should grow an axis for whether MIKAI's answer surfaces *strength of belief* alongside the fact itself ("you've returned to this 7 times across 4 months" vs. "you mentioned this once").

---

*This document should be read before modifying the extraction prompt, before adding new node or edge types, and before designing the evaluation framework. It is a design constraint document, not a specification.*
