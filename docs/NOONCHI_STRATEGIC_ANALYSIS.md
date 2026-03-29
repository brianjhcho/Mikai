# Noonchi Strategic Analysis: Task-State Awareness Is the Product

**Date:** March 26, 2026
**Status:** Active — supersedes competitive differentiation claims in prior docs

---

## The One Sentence

**MIKAI is not a memory system. MIKAI is a task-state awareness engine that knows where you are in your thinking across apps and tells you what to do next.**

Memory is the foundation. Task-state awareness is the product. If the memory layer can be adopted from an open-source competitor (Letta, Graphiti, Cognee), do it. The thing that matters — the thing nobody else is building — is the layer that tracks reasoning progression and infers next steps.

---

## Why This Distinction Matters

Every competitor in the AI memory space is building some variant of: ingest content, extract structure, retrieve on demand. The architectures are converging on vector + graph + temporal as standard. Six serious competitors shipped in 12 months. The memory infrastructure layer is commoditizing.

**What no competitor is building:**

| Capability | Who's building it |
|---|---|
| Store/retrieve facts from conversations | Mem0, Letta, Supermemory, Zep, Cognee, Hindsight |
| Graph-based memory with typed edges | Supermemory, Zep, Cognee |
| Temporal fact tracking | Zep (best-in-class), Hindsight |
| Belief confidence evolution | Hindsight (Opinion Network) |
| **Task-state tracking across apps** | **Nobody** |
| **Reasoning-stage classification** | **Nobody** |
| **Next-step inference** | **Nobody** |
| **Intention-behavior gap detection** | **Nobody** |

The bottom four rows are MIKAI's product. Everything above is infrastructure that can be bought, adopted, or built on top of open-source implementations.

---

## What Task-State Awareness Actually Looks Like

### The user experience (noonchi)

When you open Claude with MIKAI connected, it doesn't just remember what you said. It knows *where you are*:

- "You were researching flight options to Nairobi. You found 3 options but haven't booked yet. **Next step:** Compare prices on the Kenya Airways vs Ethiopian Airlines options you saved."
- "Your article draft is at 1,200 words. You stopped mid-paragraph on the trust section. **Next step:** Finish the paragraph — your last note said you wanted to reference the Edelman report."
- "You asked Claude about Kubernetes networking yesterday but never applied the answer to the config file you were editing. **Next step:** Open `deployment.yaml` and apply the DNS policy change."
- "You told Sarah you'd send the proposal by Friday. It's Thursday. You haven't started. **Next step:** Draft the proposal — your research notes from last week have the key points."

This is not memory. This is *awareness*. The Korean concept of noonchi — reading the room of your own digital life.

### The data model

| Current MIKAI (memory) | Noonchi MIKAI (task-state awareness) |
|---|---|
| Nodes = concepts, beliefs, tensions | Nodes = threads (a topic tracked across apps) |
| Edges = supports, contradicts, depends_on | Edges = led_to, blocked_by, resumed_from, resolved_by |
| Static snapshot per extraction | State machine: exploring -> evaluating -> decided -> acting -> stalled -> completed |
| Answers: "what do you think about X?" | Answers: "where are you with X? here's what's next." |

### The reasoning-state model

Every thread (a topic that appears across your apps) has a state:

| State | Signal | Example |
|---|---|---|
| **Exploring** | Gathering info, no decisions, multiple sources | Researching coffee farms in Kenya across Perplexity + Apple Notes |
| **Evaluating** | Comparing options, listing pros/cons | Three flight options saved, price comparison started |
| **Decided** | Chose an option, haven't acted | "I'm going with Ethiopian Airlines" in notes, no booking |
| **Acting** | In progress, actively working | Draft started, code being written, email half-composed |
| **Stalled** | Was acting, stopped, no activity for N days | Told Sarah you'd send the proposal, silence for a week |
| **Completed** | Done, confirmed by behavior | Flight booked (confirmation email in Gmail) |

The transition between states is detected from cross-source signals — not from the user telling the system, but from the system observing across Notes, Gmail, iMessage, Claude conversations, and files.

---

## How the Terminology Became a Trap

When the product docs were built out, "tensions," "beliefs," and "reasoning maps" became the core vocabulary. This happened because the extraction prompt was tested against Brian's writing — reflective, framework-heavy, full of explicit tensions. The vocabulary fit this content perfectly.

But the vocabulary drifted the product away from the hypothesis:

1. **Drifted toward philosophy rather than utility.** Surfacing "unresolved tensions" sounds profound but doesn't help a user pick up where they left off.
2. **Created superficial differentiation.** "Epistemic edge vocabulary — any competitor can add supports/contradicts edge types in a migration." (from MEMORY_ARCHITECTURE_THESIS.md's own honest assessment)
3. **Optimized for one writing style.** O-025 (does the extraction prompt generalize?) remains unresolved because the vocabulary assumes reflective writing.

The original hypothesis was noonchi — context awareness across your digital life. Task-state awareness. Not epistemology.

---

## The Build-or-Buy Decision for Memory

### Memory infrastructure: adopt, don't build

MIKAI's current memory layer (SQLite + sqlite-vec + Haiku extraction + Nomic embeddings) works. But it's solving a problem that well-funded teams with PhD researchers are pouring millions into.

| Competitor | Memory innovation | Open source? | Could MIKAI adopt? |
|---|---|---|---|
| **Graphiti (Zep)** | Bitemporal knowledge graph, temporal invalidation | MIT license | Yes — best-in-class temporal reasoning |
| **Cognee** | Cognitive-science memory with dynamic relationship evolution | Open source, 12K+ GitHub stars | Yes — relationship strength/decay |
| **Letta** | Agent self-managed memory (OS model) | Open source | Partially — different paradigm |
| **Hindsight** | Four epistemically-distinct memory networks, TEMPR retrieval | Research paper, not open source | No — but learnings can be applied |

**Recommendation:** Keep the current memory layer for V1 (it works, it's shipped). For V2, evaluate adopting Graphiti's temporal model or Cognee's dynamic relationships as the memory foundation. Spend engineering time on what nobody else is building: the task-state awareness layer on top.

### Task-state awareness: build, this is the product

No open-source project, no funded startup, no research paper is building cross-app task-state tracking with reasoning-stage classification and next-step inference. This is greenfield. This is the moat.

**What needs to be built:**

1. **Thread detection** — cluster related nodes/segments across different source types into threads. A "thread" is the same topic appearing in Notes + Claude + Gmail + iMessage. Implementation: high-similarity embedding clusters with cross-source linking.

2. **State classification** — for each thread, determine its reasoning state (exploring/evaluating/decided/acting/stalled/completed). Implementation: temporal activity patterns + content analysis. Most classification can be rule-based (zero LLM):
   - Multiple sources, no decisions -> exploring
   - Comparison language, pros/cons -> evaluating
   - Decision language + no behavioral follow-through -> decided
   - Active edits, drafts, bookings in progress -> acting
   - Activity drop-off after acting -> stalled
   - Behavioral confirmation (booking email, merge commit) -> completed

3. **Next-step inference** — given state + trajectory + context, what's the logical next action? This is the one place where LLM synthesis adds unique value. One Claude call per thread, not per source.

4. **Intention-behavior gap** — cross-reference Track A (what you said in notes/conversations) vs Track B (what you did in email/messages/calendar). This is the existing thesis, now grounded in the thread-state model.

---

## Revised Competitive Position

### What is NOT the moat (drop these claims)

| Old claim | Why it's not defensible |
|---|---|
| "Epistemic edge vocabulary" | Any competitor adds supports/contradicts in a migration |
| "Tension surfacing" | One new query + one UI feature for Mem0 or Hindsight |
| "Three-track extraction pipeline" | Pipeline engineering, replicable in 1-2 weeks |
| "Reasoning maps from personal content" | Synonym for knowledge extraction — Cognee, Mem0, Hindsight all do variants |
| "Local-first architecture" | Good engineering choice, not a moat |

### What IS the moat (invest everything here)

| Capability | Why it's defensible | Timeline |
|---|---|---|
| **Cross-app task-state tracking** | Requires ingestion from 4+ source types + thread detection + state classification. Nobody has the multi-source data pipeline to even attempt this. | Phase 4 |
| **Reasoning-stage classification** | Novel problem — no existing benchmark, no existing solution. First-mover defines the category. | Phase 4-5 |
| **Next-step inference** | Requires task-state + trajectory + context. Depends on having thread-state tracking working first. | Phase 5 |
| **Intention-behavior gap** | Requires cross-referencing authored content (Track A) vs behavioral traces (Track B). Nobody else has both data sources. | Phase 5-6 |
| **Action-optimized delivery** | Training signal is "user acted" not "user engaged." Different optimization target produces different product over time. | Phase 6 |

---

## Competitor Deep Dive: What Each Actually Built

### Letta (MemGPT) — LLM-as-Operating-System
- **Team:** Charles Packer + Sarah Wooders, PhDs from UC Berkeley Sky Computing Lab (Ion Stoica's group). $10M seed from Felicis.
- **Innovation:** The agent manages its own memory through tool calls. Self-editing memory blocks with FIFO eviction + recursive summarization. Not RAG — agent-managed cognition.
- **What they DON'T do:** No epistemic typing (memory blocks are text blobs), no tension detection, no trajectory modeling, no trust-calibrated delivery.
- **Relationship to MIKAI:** Complementary, not competitive. Letta solved "how does an agent manage memory efficiently?" MIKAI is solving "what should an agent do with what it knows?" MIKAI's judgment layer could theoretically sit on top of Letta's memory OS.
- **Threat:** LOW as direct competitor, HIGH as adjacent builder who could add judgment features.

### Zep/Graphiti — Bitemporal Knowledge Graphs
- **Team:** Daniel Chalef, Preston Rasmussen. Published peer-reviewed paper (January 2025).
- **Innovation:** Four timestamps on every edge (t_created, t_expired, t_valid_from, t_valid_to). Tracks when the system learned a fact vs when the fact was actually true. Enables retroactive correction and belief revision at infrastructure level.
- **Benchmarks:** 94.8% DMR, +18.5% accuracy on LongMemEval, 90% lower latency.
- **What they DON'T do:** No epistemic edge types (edges are factual: lives_in, works_at — not reasoning: contradicts, partially_answers). No intent inference. No proactive surfacing.
- **Relationship to MIKAI:** Zep tracks fact evolution ("when did this change?"). MIKAI tracks belief coherence ("how does this relate to that in terms of reasoning?"). MIKAI adopted Zep's temporal schema but hasn't built the query engine.
- **Threat:** MEDIUM. Could add epistemic edges, but research direction is temporal, not epistemic.

### Hindsight (Vectorize) — Four Memory Networks + TEMPR/CARA
- **Team:** Chris Latimer, with Virginia Tech and Washington Post collaboration. 7 co-authors on the paper.
- **Innovation:** Four parallel networks (World/Bank/Observation/Opinion) modeling different kinds of knowledge. TEMPR runs four retrieval strategies simultaneously (semantic, BM25, graph, temporal) merged via Reciprocal Rank Fusion. CARA adds configurable disposition parameters (skepticism, literalism, empathy).
- **Benchmarks:** 91.4% LongMemEval. Multi-session: 21.1% -> 79.7%. Temporal: 31.6% -> 79.7%.
- **What they DON'T do:** Opinion Network has confidence scores, not epistemic edge types. CARA calibrates the agent's reasoning, not the user's cognitive trajectory. No stall detection, no trajectory modeling.
- **Relationship to MIKAI:** Most intellectually serious competitor. Hindsight models confidence in individual beliefs. MIKAI models relationships between beliefs. If Hindsight extends CARA to user-level modeling, they close the gap.
- **Threat:** HIGH. Most likely to build toward MIKAI's thesis from below. Fast research velocity.

### Cognee — Cognitive Science-Informed Memory
- **Team:** Vasilije Markovic (cognitive science + clinical psychology background). Backed by Pebblebed (Pamela Vagata, OpenAI co-founder) and Keith Adams (Facebook AI Research founder). $7.5M seed. 12K+ GitHub stars.
- **Innovation:** Grounded in Atkinson-Shiffrin memory model. Dynamic relationship evolution based on recency, frequency, contextual relevance — relationships strengthen with access and decay with neglect, like neural pathways.
- **What they DON'T do:** No epistemic edge types (associative relationships, not reasoning relationships). No tension detection. Infrastructure, not judgment layer.
- **Threat:** LOW as direct competitor (infrastructure play). Medium as foundation MIKAI could adopt.

---

## Revised Roadmap

### V1 (now): Ship as cross-app memory for Claude
- Public pitch: "Claude remembers everything across your apps"
- The graph and tensions are a differentiating feature within this framing
- Target: 20 beta users, 5+ who'd pay for memory alone
- Run LongMemEval to establish benchmark credibility
- **This is the wedge, not the product**

### V2: Build the task-state awareness layer

| Phase | Old framing | Noonchi reframe | Priority |
|---|---|---|---|
| 4A | Recurrence/contradiction checks | **Thread detection + cross-source linking** | Critical path |
| 4B | BM25 + temporal edges | **State classification + temporal progression** | Critical path |
| 5A | Desire classification (immediate/instrumental/terminal) | **Thread-state model (exploring -> decided -> acting -> stalled)** | Critical path |
| 5B | Trajectory modeling | **Same — applied to threads** | Critical path |
| 5C | Terminal desire inference | **Next-step inference ("here's what to do next")** | The noonchi moment |
| 6 | Multi-surface delivery | **Push next-step recommendations across surfaces** | Scale |

### V3: Replace the memory layer with best-in-class open source
- Evaluate adopting Graphiti (temporal), Cognee (cognitive), or whatever wins the memory infrastructure race
- MIKAI's value is the layer above — thread-state awareness doesn't depend on a specific memory implementation
- The intent graph is the asset; the memory store is a commodity

---

## The Evaluation Problem

No benchmark exists for task-state awareness. LongMemEval tests conversational memory recall. Creating the evaluation methodology for noonchi may be MIKAI's most important intellectual contribution.

**Proposed noonchi evaluation dimensions:**

| Dimension | What it measures | How to test |
|---|---|---|
| Thread detection accuracy | Does the system correctly identify that the same topic appears across 3+ apps? | Manually label 50 threads in Brian's data, measure precision/recall |
| State classification accuracy | Does the system correctly identify exploring vs decided vs stalled? | Label 50 threads with ground-truth states, measure agreement |
| Next-step relevance | When the system suggests a next step, does the user find it useful? | Present 20 next-step suggestions, rate helpfulness 1-5 |
| Intention-behavior gap detection | Does the system correctly identify "said but didn't do"? | Label 20 known gaps in Brian's data, measure detection rate |
| Dismiss rate | Does the user act on surfaced items or dismiss them? | Target: <30% dismiss rate after 20 interactions |

**This evaluation framework is the intellectual property.** The memory benchmarks (LongMemEval, LoCoMo, DMR) measure the wrong thing for MIKAI. Building the right benchmark — and publishing it — positions MIKAI as the category creator.

---

## Open Questions

1. **Should the extraction prompt be rewritten around thread/task detection rather than tension/belief detection?** The current prompt produces reasoning maps. Noonchi needs activity maps. These may coexist (L3 = reasoning structure, L4 = task state) or the prompt may need to shift.

2. **Can thread-state classification be done with zero LLM?** If state transitions are detectable from temporal activity patterns + simple heuristics (like the current stall detection rule engine), the cost stays near zero. Only next-step inference needs LLM synthesis.

3. **When does the memory layer get replaced?** V1 ships with the current SQLite/Supabase stack. At what point does adopting Graphiti or Cognee become worth the migration cost? Trigger: when temporal reasoning or memory benchmarks become a competitive requirement.

4. **Does the V1 "cross-app memory" framing attract users who want noonchi, or users who want memory?** If beta users come for memory and stay for memory, the noonchi thesis needs re-examination. If they come for memory and say "I wish it could tell me what to do next," the thesis is validated.

---

*This document supersedes competitive differentiation claims in MEMORY_ARCHITECTURE_THESIS.md and positioning statements in CLAUDE.md where they conflict. The honest assessment: the memory layer is commodity. Task-state awareness is the product. Build accordingly.*
