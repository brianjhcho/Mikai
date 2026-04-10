

# MIKAI Open Questions & Active Tensions

These are NOT resolved. When a thread touches one, surface it — don't paper over it with a confident answer.

---
## Pressing Reminders for Every Build Decision

- **"Follows you everywhere" is a destination, not a wedge.** Always know which surface you're proving first.
- **The intent graph is the asset. The surface is a product decision.** Never collapse the engine into a single application prematurely.
- **Sumimasen applies to the product pitch, not just the notification layer.** Don't interrupt the user's existing workflow until confidence is high that the value exchange is worth it.
- **Every new feature: does it serve the engine, or does it serve a surface?** These require different justifications.
- **The monetization model must be compatible with "trust over engagement."** If the growth metric requires compromising the philosophy, the philosophy will lose. Decide this early.
- **Measure day-30 behavior, not day-1 activation.** The ambitious vision compounds slowly. The metric that matters is whether MIKAI has changed what the user does, not whether they installed it.


## O-001: Which Surface First?
**Status: RESOLVED — 2026-03-14**
V1 surface: WhatsApp bot. Final destination: Siri integration / replacing Siri as OS-level assistant. See D-019.

---

## O-002: Passive Collection vs. Privacy Compliance
How far can cross-platform behavioral monitoring go before hitting EU/California/enterprise compliance walls? What is the minimum viable data surface for Noonchi to work?
**Status:** Unresolved. Need legal research + technical privacy audit.
**Why it matters:** MIKAI's core value depends on passive observation. If the legal ceiling is too low, the product thesis changes.
**Note:** Different surfaces have different privacy profiles. Child data is the most regulated. E-commerce has established norms. Knowledge worker is moderate.

---

## O-003: When to Open the Platform API
Too early = no moat. Too late = others build competing orchestration layers. What metric triggers the opening?
**Status:** Deferred until at least one surface proves PMF. But the engine architecture should not preclude it.
**Why it matters:** The long-term vision is engine-as-platform. Timing this transition is existential.

---

## O-004: Proactive Assistance vs. Surveillance Perception
Where exactly is the line between helpful nudge and creepy inference?
**Status:** Active tension. Varies dramatically by surface — knowledge worker tolerance differs from parent tolerance differs from shopper tolerance.
**Why it matters:** One wrong interaction can permanently damage trust. Per-surface calibration needed.

---

## O-005: Single-Player vs. Multiplayer Graphs
Individual graphs are the starting point. But HICCUP needs household graphs, e-commerce needs cross-user patterns, and child tracking is inherently multi-party (parent + child).
**Status:** Engine data model should not hardcode single-user. But multiplayer graph mechanics are deferred.
**Why it matters:** If graph architecture assumes single-user and needs to go multiplayer later, migration is expensive.

---

## O-006: Hyperscaler Bundling Risk
What prevents OpenAI/Anthropic from commoditizing the intent extraction and profiling layer?
**Current answer:** Philosophy (Noonchi as first-class concept), surface-agnostic architecture (they ship integrated products), and depth of cognitive profiling (they optimize for general helpfulness, not user modeling).
**Status:** Strategic risk. Revisit quarterly against hyperscaler product announcements.
**Why it matters:** If Claude ships "deep personalization" as a built-in feature, MIKAI's differentiation narrows.

---

## O-007: Deterministic Automation vs. General Intent Inference
For agent-powered surfaces: when should behavior be explicitly configured vs. inferred?
**Current hypothesis:** Tiered model where explicit configuration trains future inference.
**Status:** Active design question relevant once a surface is chosen.

---

## O-008: Engine Evaluation Methodology
How do we know the engine is producing good output? Intent maps and profiles are subjective — there's no ground truth dataset.
**Status:** Critical unsolved problem for Phase 1.
**Possible approaches:** Self-evaluation by the person analyzed ("does this feel right?"), A/B extraction quality with different prompts, downstream surface metrics (if the surface works, the engine works).
**Why it matters:** Without a way to measure extraction quality, we can't iterate the engine systematically.

---

## O-009: Nairobi Market Application
How do the MIKAI concepts apply specifically to East African knowledge workers and infrastructure? Does the emerging market context change the engine design, the surface selection, or just the go-to-market?
**Status:** Underdeveloped. Worth its own research thread.
**Why it matters:** Brian is based in Nairobi. Local context could be either a constraint or a unique advantage. M-PESA infrastructure, fragmented data ecosystems, and mobile-first behavior may favor certain surfaces over others.

---

## O-010: Profile Portability and Ownership
If the user owns their intent graph and cognitive profile, what does portability actually look like technically? Can they export it? Plug it into another system? Revoke access from a surface?
**Status:** Architecturally important but deferred for Phase 1.
**Why it matters:** "You own the profile" is a core philosophy claim. It needs a technical implementation, not just a marketing line.

---

## O-011: Mode Routing — How Does the Engine Infer A, B, or C Automatically?
In v1 the user selects the synthesis mode manually. Phase 2 should infer it automatically. But what signals determine which mode a query should use?
**Candidates:**
- Query type: questions about "what I've thought" → Mode A, open-ended questions → Mode B, "what am I missing" → Mode C
- Graph density at the queried nodes: sparse → Mode B (needs outside knowledge), dense with contradictions → Mode C
- Confidence threshold: if retrieval similarity scores are high → Mode A, low → Mode B
- Explicit gap signals in the query language ("what am I missing", "what contradicts") → Mode C
**Status:** Open. No design work done. Phase 2 dependency.
**Why it matters:** Automatic mode routing is what makes MIKAI feel like Noonchi — anticipating what kind of answer the user needs before they specify it.

---

*Add new open questions below. Number sequentially. When resolved, move to docs/DECISIONS.md with the resolution.*

---

## O-024: Track B noise — action-verb regex matching boilerplate text
The `ACTION_VERBS` regex in `build-graph.js` is too broad for behavioral trace content. It matches boilerplate/legalese in iMessage and Gmail sources: "Std msg rates **apply**", "**sign up** (https://www...)", "**download** it now for your records", "To edit your saved search, **cancel** future...". These produce low-quality nodes that pollute the top of `getTopStalledNodes()` output.
**Status:** Deferred. Not blocking Phase 3 but will degrade delivery quality if unaddressed before WhatsApp surfacing.
**Resolution path:** Add a pre-filter in the Track B line scan: (a) strip lines matching known boilerplate patterns (Std msg rates, unsubscribe, click here, etc.), (b) filter lines that are predominantly URLs, (c) require a minimum content length after stripping URLs and punctuation. Do not touch the ACTION_VERBS set itself — the problem is the input lines, not the verbs.
**Related:** D-027, O-021

---

## O-012 [T-001]: Passive capture and the trust cliff are in direct proportion
The more ambient and invisible MIKAI becomes, the richer the graph. The more ambient it is, the more it looks like surveillance to a first-time user. This tension cannot be engineered away — it is structural. OpenClaw is already hitting this: security researchers flagged prompt injection and data exfiltration risks from third-party skills within months of launch.
**Status:** Active. Consent architecture must be designed as a first-class product feature, not deferred legal fine print. Must be concurrent with Phase 1, not Phase 2.
**Resolution path:** What does consent feel like when it's part of the UX rather than a modal you click through? Design question, not a legal question.
**Related:** O-002, O-004, D-011

---

## O-013 [T-002]: Cold-start problem is real and Mem's own data confirms it
Mem users report: "with five notes the AI does little, with five hundred it becomes magical." The graph only becomes valuable past a corpus threshold. Passive capture is the answer — but passive capture takes time to accumulate. There is a window between "installed" and "valuable" where MIKAI needs to either survive on manual input or find a way to bootstrap richly enough to deliver immediate value.
**Status:** Partially addressed by D-013 (corpus bootstrapping at onboarding), but the specific threshold and mechanism are undefined.
**Resolution path:** Identify the minimum corpus size that produces demonstrably better recall than keyword search. Design onboarding to hit that threshold on day 1.
**Related:** D-013

---

## O-014 [T-003]: The bootstrapping problem has not been fully solved
Context injection into LLM conversations was identified as the wedge. But context injection requires the graph to already be populated. An empty graph injects nothing useful. Which means the wedge still has a prior: what is the minimum behavior that populates the graph enough to make recall demonstrably better than nothing?
**Status:** Partially resolved by the recall-first reframe — even a graph populated from manual import (Apple Notes) is enough to demonstrate value before passive capture is built. Needs explicit tracking.
**Resolution path:** Define the minimum viable graph size for context injection to produce a noticeably better LLM response. Test empirically during Phase 1.
**Related:** D-013, D-015, O-013

---

## O-015 [T-004]: Single-player compounding has no organic discovery mechanism
MIKAI's value compounds for the individual over time, not across users. There is no social pressure to adopt, no network effect, no "last person without email" dynamic. Every new user is a cold acquisition. This is the structural reason the Mem category has not produced a venture-scale consumer business.
**Status:** Active. Collaboration features are the typical answer (→ enterprise pivot). MIKAI's engine-first architecture defers the surface decision — which is also the decision that could introduce multiplayer or sharing. The longer it's deferred, the longer the distribution problem remains unsolved.
**Resolution path:** Undefined. May require a surface decision that introduces a sharing or collaborative mechanism without compromising single-player depth.
**Related:** O-005, D-001, O-016

---

## O-016: Behavior change as side effect vs. behavior change as requirement
The internet didn't ask for behavior change — it offered capability that didn't exist before. Email eliminated the 3-day wait. Search replaced driving to a library. The behavior change was a side effect of an obvious value exchange. MIKAI's "follows you everywhere" vision may require paradigm adoption before value delivery — the harder side of that line.
**Status:** Active tension. Context injection (D-015) is on the right side of this line — it removes existing pain with no new behavior. The broader passive capture vision may be on the wrong side. Which parts of MIKAI require behavior change as a prerequisite, and which don't?
**Resolution path:** Map each proposed feature against this test: is the value exchange obvious with existing behavior, or does it require the user to first believe in a new paradigm?
**Related:** D-017, D-015

---

## O-017: Ambitious vision vs. fundable wedge
The "follows you everywhere" north star is the reason to build MIKAI. It is not the seed pitch. The tension is structuring the build so the wedge genuinely compounds into the vision rather than becoming a permanently small product.
**Status:** Active. Current best wedge candidate is context injection (D-015). The question is whether context injection is architecturally continuous with the full vision or a detour.
**Resolution path:** Validate that context injection generates the intent graph as a byproduct (not just as a user benefit), so the wedge literally builds the engine that enables the vision.
**Related:** D-015, D-001, O-003

---

## O-018: Engine-first vs. distribution-first — when does the surface decision become blocking?
Proving the engine in isolation is the right Phase 1 call. But an engine with no surface has no distribution. At some point the surface decision stops being deferrable and becomes the thing blocking further engine validation. The trigger for that decision is undefined.
**Status:** Active. No design work done on defining the trigger condition.
**Resolution path:** Define explicitly: what Phase 1 engine quality threshold makes the surface decision urgent? What signal — extraction accuracy, recall quality score, user behavior metric — makes "we need a real surface now" the correct call?
**Related:** O-001, D-001, D-003, O-015

**Hard constraint added 2026-03-13:** Surface work is explicitly blocked on engine validation. The WhatsApp surface (D-008) and any other agent-facing surface cannot begin until the extraction quality evaluation protocol (O-020) confirms the graph is good enough to inject into agent context. An agent fed a weak graph produces confidently wrong outputs — the failure mode is worse than no agent at all. Evaluation is not a nice-to-have gate before surfaces; it is a hard dependency.

---

## O-019: Supabase schema drift — documented vs. actual
The schema in `docs/ARCHITECTURE.md` does not match what is actually deployed. The live `sources` table has at minimum: `label TEXT`, `chunk_count INT`, `raw_content TEXT`, `source TEXT` columns not in the documented DDL. The `edges` table now has a `note TEXT` column added via migration (`infra/supabase/add_edge_note.sql`). The `nodes` table has a `label TEXT` column (used as the primary identifier during extraction) and `node_type TEXT` (not `type`).
**Status:** Active. Documentation is the source of truth for new sessions — if it's wrong, build decisions will be wrong.
**Resolution path:** Run a `\d sources`, `\d nodes`, `\d edges` schema dump from Supabase and reconcile with the documented DDL. Update `docs/ARCHITECTURE.md` to match live state before the next major build session.
**Related:** ARCH-001, ARCH-007, ARCH-017

---

## O-020: No evaluation methodology for extraction quality
The graph now contains hundreds of nodes extracted from Brian's notes. But there is no way to measure whether the extraction is good. No ground truth. No scoring rubric. The informal standard so far is "does it feel right" — which is fine for iteration but not for knowing when Phase 1 is complete.
**Status:** Active. Blocking Phase 1 completion declaration.
**Resolution path:** Design a minimal evaluation protocol. Candidates: (a) Brian reads 10 extracted nodes and rates accuracy + non-obviousness on a simple scale, (b) for a given query, compare the subgraph retrieved to what Brian would have manually selected, (c) track whether chat answers feel grounded or hallucinated over 20 real queries.
**Related:** O-008, D-003

---

## O-021: Structural extraction pattern design for behavioral traces
Two-track extraction is decided (D-021) but the structural extraction patterns for Track B are not yet defined. What specific signals in email, iMessage, and WhatsApp indicate a stalled immediate desire? What constitutes an "unanswered commitment" vs. a resolved one vs. a consciously deferred one?
**Status:** Partially resolved (2026-03-15). Track B V1 signal: action verb presence in raw behavioral text (iMessage outgoing messages + Gmail action-verb-filtered inbox). Stall baseline = 0.6 for fresh behavioral nodes; rule engine refines via occurrence_count + days_since_first_seen. Open sub-question: what constitutes resolution? `resolved_at` column exists but no mechanism yet sets it. Lifecycle states (active → resolved → decayed) remain undefined — see O-022 (node lifecycle).
**Resolution path:** Before building structural extraction, define the pattern library: (a) email — thread with no reply after N days where last message contains commitment language ("let's find a time", "can you review", "I'll send you"), (b) messages — question or meeting request with no follow-through after N days, (c) LLM conversations — same topic across 3+ sessions without resolution node. Define false positive mitigation (user dismissed signal = suppress for 30 days).
**Related:** D-021, D-024

---

## O-022: Timing model for WhatsApp delivery
When does MIKAI decide to surface a stalled item? Too frequent = annoying, erodes trust. Too infrequent = misses time-sensitive items. The timing model must account for urgency (appointment tomorrow vs. trip in 3 months), staleness (how long since last signal), cognitive load (max items per session), and receptivity (time of day/week).
**Status:** Active. Blocking Phase 3.
**Resolution path:** Start with fixed schedule (morning delivery, max 3 items) as V1. Urgency override for items with implicit deadlines detected from corpus. Iterate based on dismiss/act signals.
**Related:** D-019, D-021, D-024

---

## O-023: Node lifecycle management (deferred)
Nodes accumulate indefinitely. Stale immediate desire nodes (resolved purchases, past appointments) degrade retrieval quality over time. Needs a policy for when to engage a node (surface it), compact it (merge with related nodes), or discard it (desire resolved or decayed).
**Status:** Deferred to Phase 4+. Document the requirement, do not build.
**Resolution path:** Define lifecycle states — active, resolved, decayed, compacted. Add resolved_at and lifecycle_state columns when Phase 4 begins. Policy derived from behavioral signal data accumulated in Phases 2-3.
**Related:** D-025

---

## O-025: Does the extraction prompt generalize beyond Brian's writing style?
Phase 1 validation was on Brian's corpus. Brian writes in a specific way (reflective, framework-heavy, explicit about tensions). If the extraction prompt produces mostly `concept` nodes from a user who writes quick action items, the graph is useless.
**Status:** Active. Blocking beta launch.
**Resolution path:** Week 3 beta specifically tests this. The extraction prompt may need per-user calibration or a set of style-adaptive variants.
**Related:** D-034, O-020

---

## O-026: What is the minimum corpus size for useful tensions?
Mem.ai suggests 10-20 notes for connections to emerge. MIKAI's typed edges may require more density for tension detection to produce value. What is the threshold where "the AI that knows what you're stuck on" starts working?
**Status:** Active. Empirical testing needed during beta.
**Resolution path:** Track the relationship between corpus size and tension surfacing accuracy across beta users. Define the minimum viable graph size for the context injection wedge.
**Related:** O-013, O-014, D-013

---

## O-027: Is MCP adoption broad enough to sustain a business?
MCP is supported by Claude Desktop, Cursor, and a growing set of tools. But it is still a developer-oriented protocol. If the target user is "founders who write a lot," they need it to work without touching a terminal.
**Status:** Active. Strategic question for distribution.
**Resolution path:** Monitor MCP ecosystem growth. Track whether beta users (who are comfortable with MCP config) represent the actual target market or only a developer subset.
**Related:** D-031, O-015

---

## O-028: When does the reactive→proactive transition happen?
MIKAI launches as reactive (user asks, graph answers via MCP). The vision is proactive (MIKAI surfaces stalled items via WhatsApp/notification). What signal triggers moving from reactive to proactive? What evidence from the reactive phase is needed to de-risk the proactive phase?
**Status:** Active. Phase 3→4 transition question.
**Resolution path:** Define the proactive readiness criteria: (a) graph density threshold, (b) stall detection precision measured against user confirm/dismiss, (c) delivery timing model validated. Do not build proactive delivery until all three are met.
**Related:** D-031, D-024, O-022

---

## O-029: Silent sync failures — ingest depends on Next.js dev server
All sync scripts (apple-notes, local-files, gmail) POST to `localhost:3000/api/ingest/batch`. If the Next.js dev server is not running, syncs fail silently — launchd reports success because the script exits normally. Brian has no visibility into whether ingestion actually succeeded.
**Status:** Active. Highest-priority trust barrier issue.
**Resolution path:** Decouple the chunking logic from the API route into a standalone script that writes directly to Supabase. Update all sync scripts to use the standalone path.
**Related:** Phase 3.5 P1

---

## O-030: Segment staleness — build-segments missing from daily sync
The daily-sync.sh pipeline runs iMessage sync, Gmail sync, build-graph, and run-rule-engine. It does NOT run Apple Notes sync, local files sync, or build-segments. The MCP `search_knowledge` tool queries segments — without regular rebuilds, segment answers go stale.
**Status:** Active. Quick fix.
**Resolution path:** Add `npm run sync`, `npm run sync:local`, and `npm run build-segments` to daily-sync.sh.
**Related:** Phase 3.5 P2

---

## O-031: Default build-segments excludes claude-thread
`build-segments.js` defaults to `--sources apple-notes,perplexity,manual`. Claude threads are excluded unless explicitly passed via `--sources claude-thread`. The watch-claude-exports script passes this flag, but a standalone `npm run build-segments` does not process Claude threads.
**Status:** Active. Should change default to include claude-thread.
**Resolution path:** Change SOURCES_RAW default in build-segments.js to include claude-thread.
**Related:** O-030

---

## O-032: Track C (segments) has no evaluation methodology
969 segments exist but no eval-segments.ts tests their quality. Track A (graph nodes) has eval-nodes.ts with accuracy/non-obviousness scoring. Track C has no equivalent. Segment quality is assumed good based on manual testing of /api/chat/synthesize but not systematically measured.
**Status:** Active. Not blocking but creates quality risk as corpus grows.
**Resolution path:** Build eval-segments.ts modeled on eval-nodes.ts. Score 20 random segments for accuracy, coherence, and information density.
**Related:** O-020, O-025

---

## O-033: Attention-weighted retrieval scoring
Can attention mechanism principles (from transformer architecture) improve MIKAI's retrieval? Instead of pure cosine similarity, weight segment relevance by:
- Epistemic edge type to query-relevant nodes (contradicts > supports)
- Recency (recent sources weighted higher)
- Query hit frequency (frequently retrieved segments are more relevant)
- Source type (authored content weighted higher than behavioral traces)
**Status:** Research question. Inspired by visual attention variants literature.
**Resolution path:** Implement as a scoring layer on top of existing vector search. Test against current pure-cosine approach on the 10-query eval suite.
**Related:** Gap 6 (epistemic edges under-leveraged), ARCH-020 (hybrid retrieval)

---

## O-034: Can MIKAI function as a universal memory layer across LLMs?
The "memory passport" concept: one memory system feeding Claude, ChatGPT, Cursor, and any future LLM. MCP is the protocol for Claude Desktop/Cursor. What about non-MCP tools?
**Status:** Strategic question. Partially addressed by MCP server + API endpoints.
**Resolution path:** Define the integration surface for non-MCP consumers (REST API, webhooks, SDK). Test with ChatGPT custom instructions import.
**Related:** D-031 (MCP as Phase 3), D-038 (tiered memory)

---

## O-035: Should the extraction prompt be rewritten for thread/task detection?
The current extraction prompt produces reasoning maps (tensions, beliefs, edges). Noonchi requires activity maps (threads, states, progression). These may coexist (L3 = reasoning structure, L4 = task state) or the prompt may need to shift toward detecting task-state signals rather than epistemic relationships.
**Status:** Active. Raised by the noonchi strategic reframe (2026-03-26).
**Resolution path:** Test both approaches on 20 sources: (a) current reasoning-map prompt, (b) a new thread/task-state prompt. Compare which produces more actionable output for "where are you with X?" queries. They may coexist — L3 graph for deep reasoning, L4 thread-state for next-step inference.
**Related:** O-025, NOONCHI_STRATEGIC_ANALYSIS.md

---

## O-036: Can thread-state classification be done with zero LLM?
If reasoning-state transitions (exploring → evaluating → decided → acting → stalled) are detectable from temporal activity patterns + simple heuristics (like the current stall detection rule engine), the cost stays near zero. Only next-step inference would need LLM synthesis.
**Status:** Active. Critical for cost structure of the noonchi layer.
**Resolution path:** Prototype state classification rules against Brian's existing data. Measure accuracy against manually labeled thread states. If rule-based accuracy > 80%, LLM is only needed for next-step inference.
**Related:** D-026 (LLM reserved for 3 roles), NOONCHI_STRATEGIC_ANALYSIS.md

---

## O-037: When should the memory layer be replaced with open-source?
V1 ships with the current SQLite/Supabase stack. Graphiti (temporal KG, MIT license), Cognee (cognitive memory, 12K+ GitHub stars), and Letta (agent memory OS) are all open-source and well-funded. MIKAI's value is L4 (task-state awareness), not L2 (memory infrastructure).
**Status:** Active. Strategic build-vs-adopt question.
**Resolution path:** Trigger for evaluation: when temporal reasoning or memory benchmarks become a competitive requirement that the current stack can't meet, or when a competitor's open-source memory layer is clearly superior and integration cost is < 2 weeks.
**Related:** NOONCHI_STRATEGIC_ANALYSIS.md, MEMORY_ARCHITECTURE_THESIS.md

---

## O-039: Thesis test findings — embedding proximity alone is insufficient for cross-app detection

Three findings from the entity resolution + segmentation work (2026-03-29):

1. **Cross-app detection requires entity resolution (graph edges), not just embedding proximity.** Before entity resolution, only 4 cross-app threads were detectable via kNN clustering. After creating 1,072 `resolves_to` edges via hybrid search, 16 cross-app threads surfaced. The embedding signal alone was insufficient — topically similar but app-separated nodes didn't cluster because embedding distance reflects content similarity, not identity.

2. **Node↔segment embedding similarity is limited by size bias (Jina AI research).** Node embeddings (short, extracted labels) and segment embeddings (multi-sentence passages) occupy different regions of the embedding space. Cosine similarity comparisons across these two representation sizes systematically underweight cross-representation matches. Hybrid thread detection (nodes + segments via Union-Find with graph-edge merging) partially addresses this, but the underlying size bias remains.

3. **Source-adaptive segmentation with metadata enrichment needed for comparable segment quality.** Gmail, Apple Notes, and iMessage have structurally different content (quoted-reply threads, HTML formatting, short conversational turns). A single `smart-split` pass without source awareness produces segments of wildly different quality. Fix: source-specific splitters (`splitGmail`, `splitAppleNote`, `splitIMessage`) with per-source length thresholds and metadata preservation (sender, timestamp, thread context). See `docs/SEGMENTATION_FRAMEWORK.md`.

**Status:** Active. Findings directly inform L4 eval design (O-040/Phase 4D) — eval must measure cross-source detection quality, not just intra-source thread accuracy.

---

## O-040: Community detection belongs in L3 but is premature — multi-hop transitivity is the real gap

Architectural analysis (2026-03-29) of Graphiti-style community detection (label propagation) in L3 vs L4:

**Key findings:**
1. **Entity resolution already solves segmentation invariance.** A 1200-idea mega-note and 120 small notes converge to the same graph structure because ER links equivalent concepts across extraction boundaries. Community detection consumes this convergence — it does not create it. The bottleneck is extraction quality, not graph structure.
2. **The actual gap is multi-hop transitivity.** L4's graph-edge merging (`detect-threads.ts:348-399`) only processes direct cross-source edges. If A→B and B→C exist but not A→C, current code misses the A-C relationship. Fix: process all entity-resolution edges through Union-Find transitively (~20 lines in L4), not a new L3 abstraction.
3. **Communities only cover ~8% of threadable items.** Nodes: ~2,246. Segments: ~25,749. Community detection operates on nodes only. Segments (11:1 ratio) still need kNN for thread assignment. `NODE_SOURCE_TYPES` further restricts to apple-notes + manual.
4. **Graph is too sparse for label propagation to add value.** 1,072 cross-source edges across ~2,246 nodes. At this density, label propagation produces communities identical to connected components. Label propagation becomes valuable when the largest connected component exceeds ~40% of all nodes and needs sub-partitioning.
5. **Community drift risk.** Label propagation is non-deterministic (tie-breaking depends on iteration order). Running twice on the same graph can produce different communities, causing thread groupings to visibly shift between syncs.

**Decision:** Defer L3 community detection. Fix multi-hop transitivity in L4 now. Revisit communities when cross-source edges > 5,000 and wire them into `hybridGraphSearch` for retrieval (not just L4 seeding).
**Status:** Active — multi-hop fix in L4 is next action.
**Related:** O-039, Phase 2B in L3 roadmap

---

## O-038: Does the V1 "cross-app memory" framing attract noonchi users or memory users?
If beta users come for memory and stay for memory, the noonchi thesis needs re-examination. If they come for memory and say "I wish it could tell me what to do next," the thesis is validated.
**Status:** Active. Will be answered by beta user behavior (20-user target).
**Resolution path:** In beta onboarding, ask: "What would make this 10x more useful?" Track whether answers cluster around better memory/recall or toward task-awareness/next-steps.
**Related:** O-015, O-017, NOONCHI_STRATEGIC_ANALYSIS.md
