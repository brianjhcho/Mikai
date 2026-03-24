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

---

*This document should be read before modifying the extraction prompt, before adding new node or edge types, and before designing the evaluation framework. It is a design constraint document, not a specification.*
