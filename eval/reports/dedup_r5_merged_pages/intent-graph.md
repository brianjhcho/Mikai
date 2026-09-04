---
type: concept
title: Intent Graph
tags: [mikai, product-architecture, personal-ai, knowledge-graph, proactive-intelligence, behavioral-data, context-layer, moat, epistemic-edges, intent-modeling, behavioral-signal, data-moat, personalization, ai-strategy]
sources: ["2026-03-06-the-hard-truth-about-2nd-brain-rewind-ai-s-consumer-adapt-6a67e7.md", "2026-03-07-building-moats-beyond-model-improvement-a581c8.md", "2026-03-20-llm-best-use-case-competitive-positioning-0419ac.md", "2026-03-07-ai-tools-becoming-obsolete-to-newer-models-3c5a55.md"]
related: [passive-capture-layer, context-injection, proactive-intelligence-layer, behavior-change-cliff, wedge-first-sequencing, suno, stream-extraction-engine, context-layer-vs-capability-layer, model-context-protocol, agent-native-api-design, horizontal-vs-vertical-ai-integration, acquisition-vs-independence-mikai, home-executive-assistant, graduated-autonomy, mikai, epistemic-edge-vocabulary, substrate-beneath-surfaces, project-state-graph-vs-cognitive-state-graph, context-injection-retrieval, intent-layer-for-ambient-computing, graphiti-zep, kuzu-memory, copilot-vs-autopilot, orchestration-over-frontier-models, can-mikai-become-an-autopilot, hiccup, two-tier-knowledge-architecture]
---

## Overview
The intent graph (also called the personal intent graph) is a typed, user-owned epistemic graph that encodes a person's goals, preferences, decision patterns, half-finished ideas, and contextual relationships — a persistent, personalized model of what a user is currently working on, thinking about, and trying to accomplish. It is populated from passive behavioral signal across the user's full digital life (browsing, writing, conversations, calendar, file activity) rather than explicit declarations, is updated continuously, accretes across sessions rather than resetting, and travels with the user across surfaces. It is MIKAI's core artifact — the central asset of its thesis and the load-bearing piece of its defensibility argument.

## Notes

**Structure**
- **Nodes**: concepts, goals, half-formed ideas, open questions; entities such as projects, people, recurring tasks, and preferences extracted from behavioral streams.
- **Edges**: typed epistemic relationships — `supports`, `contradicts`, `partially_answers`, `unresolved_tension` (see [[epistemic-edge-vocabulary]]) — as well as relations like "project X has deadline Y," "person A handles logistics domain B," "preference P applies in context C."
- **Population pipeline**: the [[stream-extraction-engine]] ingests raw streams (conversation exports, browsing sessions, iMessage data) and produces structured graph output; the method is passive behavioral signal, not explicit statement.
- **Temporal model**: rate and direction of graph change — cognitive trajectory, not just current state.
- The graph encodes cognitive patterns and recurring attention areas, decision sequences and outcomes, project history and evolving priorities, behavioral signals (browsing, reading, annotation), and timing patterns captured by the [[suno]] layer (when to surface, when to stay silent).

**What makes it distinct**
- Not a contact database, file index, chat history, memory feature, or standard memory store. It is a structured representation of current cognitive focus — open projects, active questions, recent decisions, pending ambiguities — and a model of *how a specific person thinks*.
- It is inferential, not declarative: the system derives intent from behavioral signal rather than being told.
- Contrast with a [[passive-capture-layer]]: passive capture stores what happened; the intent graph encodes what the user is *trying to do*, inferred from what happened — a compression of signal into actionable semantic structure.
- **Versus RAG/memory tools**: standard RAG retrieves documents matching a query; memory stores facts. The intent graph is a structured semantic object an agent can traverse to understand *what this person would want* in a given context, encoding relationships between goals, preferences, and decision patterns queryable at task time. It maps the person (where thinking is stuck, terminal desires, ideas in tension), whereas [[claude-mpm]]/[[kuzu-memory]] map project artifacts and declared preferences, [[graphiti-zep]] maps time-stamped factual-relational edges from explicit declarations, and [[mem0]] stores declarative fact recall. None combine epistemic edges with passive behavioral input.

**Why it is the real moat**
- **It travels.** A graph that accurately represents cognitive state can be injected into any surface — browser sidebar, Slack digest, LLM conversation, calendar block — without a new interface for each.
- **It compounds.** *Density*: the longer a user interacts with ingested surfaces, the richer the graph and the better every AI interaction, deepening switching costs. *Judgement surface*: acceptance rates, readiness signals, and behavioral rhythms create a proprietary moat models alone cannot replicate — the intelligence vs. judgement split from [[context-layer-vs-capability-layer]].
- **It cannot be easily replicated.** Surface features are copyable; a rich personal intent model built from months of passive signal is not. The moat is in the data and inference quality, not the UI — a data moat, not a capability moat. Base-model improvements compress one-shot synthesis tools (see [[ai-tool-commoditization]]); the synthesis artifact (paste-in brief) commoditizes, the graph that knows *this person* across three years of sessions does not. No hyperscaler builds an opinionated, trust-first personal graph at MIKAI's philosophy level — platforms build horizontal memory primitives.
- It is the non-substitutable slot in the agent ecosystem: capability agents (browser automation, API calls) are substitutable by model providers; the intent graph requires longitudinal behavioral data from a specific user and is irreplaceable once populated.
- **Single-player constraint**: value compounds within one user over time, not across users; there are no network effects pulling in external social pressure. (The canonical source's cross-platform flywheel argument — each agent integration feeding the graph — is cut off mid-sentence in the input.)

**Strategic role**
- The graph is the [[intent-layer-for-ambient-computing]] — the missing piece separating genuine ambient computing (agents that infer what you need before you ask) from current dynamic discovery (agents that find tools when you describe what you need). See [[zero-configuration-ambient-agent-infrastructure]].
- The highest-leverage engineering surface is not the graph itself but the retrieval decision — what to inject from the graph into context. See [[context-injection-retrieval]] and [[context-injection]].
- **Autopilot thesis**: under [[copilot-vs-autopilot]], MIKAI as a synthesis tool is a copilot (vulnerable); MIKAI as an executor of next steps *because it knows the user's intent deeply* is an autopilot seed. The intent graph is the precondition for crossing that line — what makes autonomous action trustworthy rather than presumptuous.
- An architectural open question was flagged in the retired page but its text is truncated in the input and is not recorded here.