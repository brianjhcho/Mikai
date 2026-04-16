# MIKAI — Vision

> **Consolidated from:** `INTENT_INTELLIGENCE_MANIFESTO.md`, `NOONCHI_STRATEGIC_ANALYSIS.md`, `MEMORY_ARCHITECTURE_THESIS.md` (Pass 2, 2026-04-16)
> **Authoritative for:** what MIKAI is, why the task-state layer (noonchi) is the product, how MIKAI is positioned vs. memory infrastructure competitors, and what "local-first as first-class mode" means at the product level.

---

## §1 — Intent intelligence, not memory

Every LLM conversation starts cold. You open Claude or ChatGPT and the model has no idea that you are deciding between two job offers and can't sleep, that you have been researching the same problem for six weeks without moving forward, or that you've already contradicted yourself on which outcome you actually want. Each conversation begins in amnesia.

Memory systems — Mem0, Zep, Letta, Rewind — solve a narrower problem: *what did I say?* They store what you wrote. They retrieve it when you ask. This is plumbing. Necessary, but not sufficient.

The harder problem, the one nobody is solving, is inference: *what am I trying to do? Where am I stuck? What should I do next?* A chatbot can remember that you mentioned job offers three weeks ago. It cannot infer that you're stalled between two competing visions of your future, that each offer represents a different self-model, and that the real decision isn't about compensation — it's about which version of yourself you want to become.

**Memory is what you said. Intent intelligence is what you meant.**

### The three layers of AI personalization

Current systems collapse personalization into a single dimension. But there are three distinct layers, and they compound differently.

- **L1 — Memory Interface.** The API contract between an application and a memory system: HTTP endpoints, semantic search, structured retrieval. MCP, LangChain integrations, chat context windows. **Commodity.** Every LLM vendor is building this. The problem is well-defined, the solution is straightforward, margins are thin.

- **L2 — Memory Infrastructure.** The backend that stores and indexes memory: vector embeddings, retrieval architectures, temporal modeling, graph databases. Currently diverging (Pinecone, Weaviate, Graphiti, PuppyGraph compete) but will converge to commodity over the next 12–18 months. MIKAI's L3 port (ARCH-024) treats this layer as swappable — `GraphitiAdapter` today, a second adapter tomorrow.

- **L3 — Intention-Behavior Gap Detection.** The capacity to model what someone *said* they wanted vs. what they actually did, what they believe they value vs. where they spend time, where they've stated intentions but actions have stalled, which stated beliefs contradict each other. Requires cross-referencing behavior across multiple contexts — conversations, sources, time — and building a persistent model of the gaps. **Nobody is building this.** It's the frontier.

*(MIKAI's "L3 graph" and the "L3 intention-behavior gap detection layer" above are numbered differently. The former is the knowledge-graph infrastructure layer in MIKAI's stack. The latter is the strategic positioning layer in this taxonomy. The numbering collides because MIKAI's product layer is called L4 in the stack — it sits above the L3 graph and implements the gap detection described here. See §3.)*

---

## §2 — Noonchi: the moat is task-state awareness

**MIKAI is a task-state awareness engine — the AI that knows where you are in your thinking across apps and tells you what to do next.** This is the one-sentence product.

Noonchi is Korean for "reading the room." Applied to your digital life: the system reads the room of what you're doing across Notes, Gmail, iMessage, Claude threads, Perplexity, calendar — and surfaces what you're actually working through, where it stalled, and the concrete next step.

### What noonchi actually looks like

When you open Claude with MIKAI connected, it doesn't just remember what you said. It knows *where you are*:

- "You were researching flight options to Nairobi. You found 3 options but haven't booked yet. **Next step:** Compare prices on the Kenya Airways vs Ethiopian Airlines options you saved."
- "Your article draft is at 1,200 words. You stopped mid-paragraph on the trust section. **Next step:** Finish the paragraph — your last note said you wanted to reference the Edelman report."
- "You told Sarah you'd send the proposal by Friday. It's Thursday. You haven't started. **Next step:** Draft the proposal — your research notes from last week have the key points."

This is not memory. This is *awareness*.

### The four capabilities no competitor has

| Capability | Who else is building it |
|---|---|
| Store/retrieve facts from conversations | Mem0, Letta, Supermemory, Zep, Cognee, Hindsight |
| Graph-based memory with typed edges | Supermemory, Zep, Cognee |
| Temporal fact tracking | Zep (best-in-class), Hindsight |
| Belief confidence evolution | Hindsight (Opinion Network) |
| **Cross-app task-state tracking** | **Nobody** |
| **Reasoning-stage classification** | **Nobody** |
| **Next-step inference** | **Nobody** |
| **Intention-behavior gap detection** | **Nobody** |

The top four are memory infrastructure — commodity, replicable, converging. The bottom four are MIKAI's product. Every memory vendor can add typed edges or tension detection in a migration. None of them has the multi-source data pipeline or the reasoning-stage model required for noonchi.

### The reasoning-state model

Every thread (a topic that appears across apps) has a state:

| State | Signal |
|---|---|
| **Exploring** | Gathering info, no decisions, multiple sources |
| **Evaluating** | Comparing options, listing pros/cons |
| **Decided** | Chose an option, haven't acted |
| **Acting** | Draft started, code being written, email half-composed |
| **Stalled** | Was acting, stopped, no activity for N days |
| **Completed** | Done, confirmed by behavior (e.g. booking email) |

State transitions are detected from cross-source signals — not from the user telling the system, but from the system observing across Notes, Gmail, iMessage, Claude threads, and files. Full build spec: see FOUNDATIONS.md §3 and D-041.

### Epistemic edges and tension surfacing are not moats

This is the honest, load-bearing correction to earlier positioning: **epistemic edges and tension surfacing are features, not moats.** Any competitor can add `supports`/`contradicts` edge types in a schema migration and add one query to surface tensions. Those capabilities are replicable in 1–2 weeks of engineering.

The moat is four layers of depth *above* the edges:

1. **Cross-app task-state tracking.** Requires ingestion from 4+ source types + thread detection + state classification. Nobody has the multi-source data pipeline.
2. **Reasoning-stage classification.** Novel problem. No existing benchmark. No existing solution. First-mover defines the category.
3. **Next-step inference.** Requires task-state + trajectory + context. Depends on having thread-state tracking working first.
4. **Intention-behavior gap detection.** Requires cross-referencing authored content (what you said) vs. behavioral traces (what you did). Nobody else has both data sources.

> **Unresolved (O-035):** The current extraction prompt was tuned on Brian's reflective, framework-heavy writing style. The edge vocabulary (see FOUNDATIONS.md §2) was built against the same corpus. NOONCHI_STRATEGIC_ANALYSIS argues the vocabulary may have drifted toward philosophy rather than utility, and that the extraction prompt may need to shift toward thread/task-state signals rather than epistemic relationships. EPISTEMIC_EDGE_VOCABULARY treats the vocabulary as a settled spec. These two stances disagree. The L3 edge vocabulary is still the L3 schema, but whether it is load-bearing for L4 task-state detection — or whether L4 needs a different, activity-oriented extraction pass — is an open question. Don't treat the edge vocabulary as a durable L4 moat until O-035 resolves.

### Action vs. engagement

Current tools optimize for engagement. Mem0 surfaces what you know. Rewind surfaces what you said. The system succeeds when you use it frequently.

MIKAI optimizes for action. It surfaces what you're avoiding deciding, what contradicts your stated beliefs, where intentions have stalled. The system succeeds when the user acts on a surfaced intention.

These are different training signals. Over time, they produce fundamentally different products. An engagement-trained system learns to surface things that make you browse. An action-trained system learns to surface things that make you act. The "default to silence" / *Sumimasen* principle — every notification is a trust transaction — is the opposite of engagement logic.

**"Trust over engagement"** is the positioning. The dismiss rate gate (<30% after 20 interactions) is the structural product gate that forces it.

### Launch positioning: "the AI that knows what you're stuck on"

Per D-033, this is the primary positioning. Not "second brain" (dead category signal). Not "follows you everywhere" (infrastructure language that triggers Mem.ai / Rewind pattern-matching). Not "intent prediction engine" (Series C narrative, not the seed pitch).

"The AI that knows what you're stuck on" describes a user-felt experience, not a technical capability. It is something no product in the competitive landscape (Mem0, Mem.ai, Rewind, Granola, Howie) can honestly claim today.

---

## §3 — Memory is commodity; the L3 intention-behavior gap is the moat

### Honest competitive position

| Claimed Differentiator | Why It's Not Defensible |
|---|---|
| "Infers what you want" | Mem0 + one prompt + one schema change gets 80% of the way there |
| Epistemic edge vocabulary | Any competitor can add `supports`/`contradicts` edge types in a migration |
| Tension surfacing | One new query + one UI feature |
| Source-type-aware extraction | Pipeline engineering, replicable in 1-2 weeks |
| Behavioral data accumulation | Every memory system creates switching costs |
| Three-track extraction | Architectural pattern, not proprietary |

The memory infrastructure space is commoditizing. Six+ serious competitors shipped in 12 months. The architecture is converging on vector + graph + temporal as standard.

**What is defensible: the intention-behavior gap.**

```
Track A: What Brian THINKS  →  "I've decided to build in East Africa"
Track B: What Brian DID     →  No flight booked. No visa. No contacts.
THE GAP:                    →  Intention stalling for 3 weeks. Why?
```

Mem0 stores what Brian SAID. Hindsight recalls what Brian SAID. Supermemory extracts what Brian SAID. None compare what was said to what was done. No competitor cross-references stated intentions (from notes, conversations, reflections) against actual behavior (from email, messages, calendar, transactions) to detect where intentions have stalled and why.

### Competitor deep dive (concise)

- **Letta (MemGPT).** Agent manages its own memory through tool calls. Memory blocks, FIFO eviction, recursive summarization. No epistemic typing, no tension detection, no trajectory modeling. Complementary, not competitive. MIKAI's judgment layer could theoretically sit on top of Letta's memory OS. Threat: LOW as competitor, HIGH as adjacent builder.

- **Zep / Graphiti.** Bitemporal knowledge graph. Four timestamps on every edge. 94.8% DMR, +18.5% on LongMemEval. MIKAI *uses* Graphiti as its L3 adapter (see ARCHITECTURE.md §2). Zep's edges are factual (`lives_in`, `works_at`), not epistemic, and they don't build intent inference or proactive surfacing. Threat: MEDIUM — research direction is temporal, not epistemic.

- **Hindsight (Vectorize).** Four memory networks (World/Bank/Observation/Opinion). TEMPR runs four retrieval strategies merged via RRF. CARA adds configurable disposition parameters. 91.4% LongMemEval. Models confidence in individual beliefs; MIKAI models relationships between beliefs. Threat: HIGH. Most intellectually serious competitor. Could build toward MIKAI's thesis from below.

- **Cognee.** Cognitive-science memory, dynamic relationship evolution (recency, frequency, contextual relevance — strengthens with access, decays with neglect). 12K+ GitHub stars. Infrastructure, not judgment layer. Threat: LOW as competitor, medium as foundation MIKAI could adopt.

- **Mem0 / Supermemory.** Ingest, extract, retrieve. Commoditizing quickly.

### The four-layer architecture (revised)

```
LAYER 4: TASK-STATE AWARENESS — THE PRODUCT (noonchi)
═══════════════════════════════════════════════════════════
  Thread detection: same topic across Notes + Gmail + iMessage + Claude
  State classification: exploring → evaluating → decided → acting → stalled → completed
  Next-step inference: given state + trajectory, what's the logical next action?
  Intention-behavior gap: cross-reference Track A (said) vs Track B (did)

  No competitor is building this. This layer is the product.

LAYER 3: INTENTION-BEHAVIOR GAP DETECTION (the moat within L4)
═══════════════════════════════════════════════════════════
  Optimize for ACTION (dismiss rate < 30%)
  Training signal: user acts or dismisses surfaced intentions

LAYER 2: MEMORY INFRASTRUCTURE (commodity — adopt best patterns)
═══════════════════════════════════════════════════════════
  Short-term: zero-LLM structural segmentation — built (the pre-Graphiti era)
  Evaluation: recurrence + contradiction + stall checks — Graphiti adapter does this natively
  Long-term: bitemporal graph with typed edges + confidence — via GraphitiAdapter today

  This entire layer sits behind the L3Backend port (ARCH-024). Swappable.
  GraphitiAdapter is live; LocalAdapter is a first-class alternate (ARCH-025).
  MIKAI's value is L4, not L2.

LAYER 1: MEMORY INTERFACE (commodity — MCP standard)
═══════════════════════════════════════════════════════════
  MCP tools exposed to Claude Desktop
  Model-agnostic: works with any MCP client
```

### Standing strategic questions

- **What happens when Claude's native memory gets good enough?** Claude's memory knows only what you told Claude. MIKAI knows what you told everyone — cross-source data (Apple Notes + Gmail + iMessage + Perplexity + Claude threads) Claude's native memory doesn't have.
- **What happens when Mem0 adds desire inference?** They'll optimize for engagement (more API calls = more revenue). MIKAI optimizes for action. Different training signals → different products. Philosophical defense, not technological.
- **What happens when Apple builds this into the OS?** Apple has the data, the privacy story, the distribution. Defense: Apple will optimize for the median user, not for the power user who writes 2,000+ notes and wants epistemic reasoning. MIKAI's depth on personal knowledge work is a niche Apple won't serve.
- **Is the moat just "Brian's personal tool"?** Possibly. Phase 4 (5 beta users) tests whether intention-behavior gap detection generalizes. See O-025, O-035, O-038.

---

## §4 — Privacy posture: local-first as first-class mode

MIKAI supports two runtime modes, selected at startup by `L3_BACKEND`:

- `L3_BACKEND=graphiti` (default) — `GraphitiAdapter`: FastAPI sidecar + Neo4j + DeepSeek V3 + Voyage AI. Episode content leaves the device for extraction and embedding.
- `L3_BACKEND=local` — `LocalAdapter`: fully on-device. Embedded graph store, local embeddings, local LLM. Zero external service dependency — no Docker, no Neo4j, no remote API calls.

This is not a cloud product with a "local option." It is a two-adapter architecture in which local-first is a first-class runtime mode, designed into the port boundary from the start. See ARCH-025 for the full settled decision.

### Why this is a product-level commitment, not just a technical choice

Competitors like Granola have shown that "download it, it runs entirely on your laptop" is a materially different product than "install Docker, configure Neo4j, point it at a sidecar." Some users — and some of Brian's own research workflows with sensitive content — require that nothing leaves the device. The privacy posture is a product claim, not an engineering preference.

The two-adapter architecture (ARCH-024, ARCH-025) makes this claim enforceable:

- The `LocalAdapter` path never calls DeepSeek, never calls Voyage, never opens an outbound connection. A user on `L3_BACKEND=local` gets a categorically different privacy guarantee than a user on `L3_BACKEND=graphiti`.
- The port surface is intentionally small (8 methods, all in domain terms, no Graphiti/Neo4j/SQLite nouns) to keep both adapters viable. If product code leaks an adapter-specific assumption, `LocalAdapter` breaks immediately and the leak is caught.
- Switching modes is a single env var. No code changes. No rebuild. This is what makes it a product commitment rather than a fork.

**The two-adapter architecture is a product-level commitment, not just a technical design choice.** See ARCH-025 for the scope of what "local" means, the tradeoffs accepted (model quality gap, feature gap), and the sequencing (port extraction → GraphitiAdapter stabilization → LocalAdapter implementation).
