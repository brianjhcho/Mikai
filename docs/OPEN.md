# MIKAI — Open Questions & Gaps

> **Consolidated from:** `ARCHITECTURE_GAPS.md` (7 gaps, P0/P1), `OPEN_QUESTIONS.md` (38 entries) (Pass 2, 2026-04-16)
> **Authoritative for:** unresolved questions and known structural gaps, merged and triaged by priority.

## How to use this doc

New work gets triaged into this list before starting. Each entry carries 2–4 sentences and preserves original IDs (`Gap N`, `O-NNN`) side-by-side when entries merge. When a question is resolved, move it to the **Resolved** section at the bottom with a one-line close note. Do not add new entries here through this doc — new open questions enter through work sessions and are appended at the end of the appropriate priority block.

Priority ordering: what blocks L4 ship > what blocks extraction validation > privacy/distribution > philosophical.

---

## Blocking — prevents shipping L4 / product

### [Gap 1] No write path from MCP tools (historical — now addressed by D-037)
MCP tools historically were read-only. Claude could not record new information from conversation, mark a tension resolved, or correct an inaccurate extraction. D-037 added `mark_resolved(node_id)` and `add_note(content)`. Verify both are live on the Python MCP server after the ARCH-024 port extraction; if not, re-implement against the port.

### [Gap 2] Documentation claims vs reality
`MIKAI_Architecture_Memory_Comparison.md` marked BM25 keyword retrieval, the five-operation Update Resolver, four-timestamp edges, and async summarization as complete. None were implemented. Downstream planning that assumed these existed operated on false premises. Pass 1 of the docs refactor closed the STATUS.md gap; verify all other docs were corrected.

### [O-018] Engine-first vs. distribution-first — when does the surface decision become blocking?
Proving the engine in isolation is the right Phase 1 call. An engine with no surface has no distribution. The trigger for when the surface decision becomes urgent is undefined. **Hard constraint (2026-03-13):** surface work is blocked on engine validation — an agent fed a weak graph produces confidently wrong outputs. Evaluation (O-020) is a hard dependency, not a nice-to-have gate.

### [O-020] No evaluation methodology for extraction quality
The graph contains thousands of nodes. There is no way to measure whether the extraction is good. No ground truth. Informal standard: "does it feel right." Blocks Phase 1 completion and all downstream surface work. Design a minimal evaluation protocol (rate 10 nodes for accuracy + non-obviousness, compare retrieved subgraphs to manually-selected, track groundedness over 20 queries).

### [O-025] Does the extraction prompt generalize beyond Brian's writing style?
Phase 1 validation was on Brian's corpus. Brian writes reflectively, framework-heavy, explicit about tensions. If extraction produces mostly `concept` nodes from a user who writes quick action items, the graph is useless. Blocks beta launch. Week 3 beta specifically tests this.

### [O-035] Should the extraction prompt be rewritten for thread/task detection?
Current prompt produces reasoning maps (tensions, beliefs, edges) from the EPISTEMIC_EDGE_VOCABULARY. Noonchi requires activity maps (threads, states, progression). Two positions disagree: NOONCHI_STRATEGIC_ANALYSIS says the vocabulary may have drifted toward philosophy rather than utility and may need rewrite for task-state detection; EPISTEMIC_EDGE_VOCABULARY treats the vocabulary as settled spec. Test both approaches on 20 sources and compare which produces more actionable output for "where are you with X?" queries. May coexist (L3 reasoning + L4 thread-state). Related: O-025, VISION.md §2, FOUNDATIONS.md §2.

### [O-036] Can thread-state classification be done with zero LLM?
If reasoning-state transitions are detectable from temporal activity patterns + simple heuristics, cost stays near zero — only next-step inference needs LLM synthesis. Prototype state classification rules against Brian's data. Measure accuracy against manually labeled thread states. If rule-based > 80%, LLM stays single-call per thread. Critical for L4 cost structure. Related: D-026, FOUNDATIONS.md §3.

---

## High — affects extraction quality, privacy, generalization

### [Gap 6 / O-023] Epistemic edges barely read; node lifecycle management deferred
Edge types (`supports`, `contradicts`, `unresolved_tension`, `partially_answers`, `depends_on`, `extends`) are stored but only used for sort ordering. They do not influence retrieval scoring (a `contradicts` edge should boost relevance more than `supports`), do not trigger automatic tension detection when a query touches an unresolved edge, do not track belief revision chains, and are not used by segment search at all. The claimed competitive moat is an asset that is barely read. Also: nodes accumulate indefinitely; stale immediate-desire nodes (resolved purchases, past appointments) degrade retrieval over time. Needs a lifecycle policy (active → resolved → decayed → compacted) derived from behavioral data accumulated in Phases 2–3.

### [Gap 3] Pure vector retrieval — no keyword or temporal fusion
`search_knowledge` and `search_graph` use only Voyage AI embedding similarity. No BM25/full-text search, no temporal filtering, no cross-encoder reranking. Estimated retrieval quality: 50–60% on LongMemEval (vs Hindsight's 91.4%). Concrete failure: "rent costs" fails if segments use "lease" instead of "rent." Fix: add `to_tsvector` full-text search as parallel retrieval path; merge via RRF. Note: in the Graphiti era this is partially addressed by Graphiti's native hybrid (vector + BM25), but retrieval on the L3 read path still needs verification.

### [Gap 4] No conflict resolution on node insertion
Graph-building writes nodes without checking for duplicates or contradictions. No dedup logic, no embedding-similarity check before insert. Risk: 30-minute sync frequency re-processes unchanged sources, creating duplicate nodes. Fix: before insertion, check embedding similarity against existing nodes from same source; similarity > 0.92 → skip. In the Graphiti era, Graphiti does this natively via its 4-tier entity resolution — but verify in the MCP / ingestion paths.

### [Gap 5] No temporal validity on edges or nodes (Supabase-era)
Schema has only `created_at`. Cannot answer "what did I believe about X in January?" Cannot expire superseded beliefs. Cannot track belief revision. Graphiti's bitemporal edges (valid_at, invalid_at) address this natively; remaining work is to ensure the port surfaces history correctly to product code via `history(id)`.

### [O-024] Track B noise — action-verb regex matching boilerplate text
`ACTION_VERBS` regex in `build-graph.js` is too broad. Matches "Std msg rates **apply**", "**sign up**", "**download**", "To edit your saved search, **cancel**". Pollutes top of `getTopStalledNodes()`. Pre-filter in Track B line scan: strip boilerplate patterns (Std msg rates, unsubscribe, click here), filter URL-heavy lines, require minimum content length after stripping. Not blocking Phase 3 but degrades delivery quality before WhatsApp surfacing. Related: D-027.

### [O-002] Passive collection vs. privacy compliance
How far can cross-platform behavioral monitoring go before hitting EU/California/enterprise compliance walls? What is the minimum viable data surface for noonchi to work? MIKAI's core value depends on passive observation — if the legal ceiling is too low, the product thesis changes. Per-surface profiles differ (child data regulated tightest, e-commerce moderate, knowledge worker moderate).

### [O-012] Passive capture and the trust cliff are in direct proportion
The more ambient and invisible MIKAI becomes, the richer the graph. The more ambient it is, the more it looks like surveillance. This tension cannot be engineered away — it is structural. Consent architecture must be a first-class product feature (not deferred legal fine print), concurrent with Phase 1. Design question: what does consent feel like when it's part of UX rather than a modal you click through? Related: O-002, O-004.

### [O-004] Proactive assistance vs. surveillance perception
Where exactly is the line between helpful nudge and creepy inference? Varies dramatically by surface — knowledge worker tolerance differs from parent tolerance differs from shopper tolerance. One wrong interaction can permanently damage trust. Per-surface calibration needed.

### [O-021] Structural extraction pattern design for behavioral traces
Track B V1 signal is action-verb presence in raw text with a 0.6 stall baseline. Open sub-question: what constitutes resolution? `resolved_at` column exists but no mechanism yet sets it. Before building production structural extraction, define the pattern library: email threads with no reply after N days + commitment language; messages with no follow-through; LLM conversations across 3+ sessions without resolution. Define false-positive mitigation (user dismissed = suppress for 30 days). Related: D-021, D-024, D-027.

### [O-022] Timing model for WhatsApp / proactive delivery
When does MIKAI decide to surface a stalled item? Too frequent = annoying, erodes trust. Too infrequent = misses time-sensitive items. Must account for urgency (appointment tomorrow vs. trip in 3 months), staleness, cognitive load (max items per session), receptivity (time of day/week). V1: fixed schedule (morning, max 3 items); urgency override for implicit deadlines; iterate on dismiss/act. Related: D-019, D-021, D-024, ProMemAssist / Sumimasen gate in FOUNDATIONS §3.

### [O-032] Track C (segments) has no evaluation methodology
969 segments exist but no `eval-segments.ts` tests their quality. Track A (graph nodes) has `eval-nodes.ts` with accuracy/non-obviousness scoring; Track C has no equivalent. Quality is assumed good from manual testing but not systematically measured. Build an eval scoring 20 random segments for accuracy, coherence, information density.

---

## Medium — architectural, performance, integration

### [Gap 7] Single-tenant schema (in Supabase era, predates Graphiti)
No `user_id` column on sources, nodes, edges, segments. All RPCs searched the full database. Graphiti's per-episode isolation partially addresses this but multi-tenancy needs explicit design at the port level. Prevent the most expensive possible future migration.

### [O-005] Single-player vs. multiplayer graphs
Individual graphs are the starting point. HICCUP needs household graphs; e-commerce needs cross-user patterns; child tracking is inherently multi-party. Engine data model should not hardcode single-user. Multiplayer graph mechanics deferred. If graph architecture assumes single-user and needs to go multiplayer later, migration is expensive.

### [O-008] Engine evaluation methodology (general)
Intent maps and profiles are subjective — no ground truth dataset. Candidates: self-evaluation by the person analyzed ("does this feel right?"), A/B extraction quality with different prompts, downstream surface metrics. Without a way to measure, we can't iterate systematically. Related: O-020, O-025, O-032.

### [O-029] Silent sync failures — ingest depends on Next.js dev server (historical)
Pre-Graphiti: all sync scripts POSTed to `localhost:3000/api/ingest/batch`; if the Next.js dev server wasn't running, syncs failed silently. Addressed by D-039 (Next.js removed) and ARCH-020/ARCH-023 (ingestion direct to Graphiti via `add_episode()`). Verify no residual localhost dependencies in the current ingestion daemon.

### [O-030 / O-031] Segment staleness and default build-segments excludes claude-thread (historical)
`daily-sync.sh` did not run Apple Notes sync, local files sync, or build-segments; claude-thread was excluded from default sources. Both superseded by ARCH-020/ARCH-023 (unified ingestion on `L3Backend.ingestEpisode()`). Verify against current ingestion daemon after it lands from `feat/ingestion-automation`.

### [O-033] Attention-weighted retrieval scoring
Can transformer-attention principles improve retrieval? Weight segment relevance by epistemic edge type to query-relevant nodes (contradicts > supports), recency, query-hit frequency, source type (authored > behavioral). Implement as a scoring layer over existing vector search. Test against pure-cosine on a 10-query eval suite. Related: Gap 6.

### [O-034] Can MIKAI function as a universal memory layer across LLMs?
"Memory passport": one memory system feeding Claude, ChatGPT, Cursor, any future LLM. MCP is the protocol for Claude Desktop/Cursor. Define the integration surface for non-MCP consumers (REST API, webhooks, SDK). Test with ChatGPT custom instructions import. Related: D-031, D-038.

### [O-007] Deterministic automation vs. general intent inference
For agent-powered surfaces: when should behavior be explicitly configured vs. inferred? Current hypothesis: tiered model where explicit configuration trains future inference. Active design question relevant once a surface is chosen.

### [O-011] Mode routing — how does the engine infer synthesis mode automatically? (Phase 2)
V1 users select synthesis mode manually. Phase 2 should infer. Signals: query type (what-I've-thought → Mode A; open-ended → Mode B; what-am-I-missing → Mode C), graph density (sparse → B; dense with contradictions → C), confidence threshold, explicit gap signals in query language. No design work done. Phase 2 dependency.

### [O-019] Supabase schema drift — documented vs. actual (historical, partially closed)
Schema in docs/ARCHITECTURE.md did not match what was deployed. Pass 1 and Pass 2 of the docs refactor resolved the Supabase-schema doc drift (Supabase has been retired on main; see ARCH-019, ARCH-020). Verify no residual schema-drift references in newer docs.

### [O-028] When does the reactive→proactive transition happen?
MIKAI launches reactive (user asks, graph answers via MCP). Vision is proactive (surfaces stalled items via WhatsApp/notification). Define proactive readiness criteria: (a) graph density threshold, (b) stall detection precision measured against confirm/dismiss, (c) delivery timing model validated. Do not build proactive delivery until all three are met.


---

## Low — philosophical, long-horizon

### [O-003] When to open the platform API
Too early = no moat. Too late = others build competing orchestration layers. Deferred until at least one surface proves PMF. Engine architecture should not preclude it. Long-term vision: engine-as-platform.

### [O-006] Hyperscaler bundling risk
What prevents OpenAI/Anthropic from commoditizing intent extraction and profiling? Current answer: philosophy (noonchi as first-class concept), surface-agnostic architecture, depth of cognitive profiling. Revisit quarterly against hyperscaler product announcements. If Claude ships "deep personalization" as built-in, differentiation narrows.

### [O-009] Nairobi market application
How do MIKAI concepts apply specifically to East African knowledge workers? Does emerging market context change engine design, surface selection, or just GTM? Brian is based in Nairobi — local context could be constraint or unique advantage. M-PESA infrastructure, fragmented data ecosystems, mobile-first behavior may favor certain surfaces.

### [O-010] Profile portability and ownership
If the user owns their intent graph and cognitive profile, what does portability actually look like technically? Export? Plug into another system? Revoke access? "You own the profile" is a core philosophy claim — needs technical implementation, not just marketing.

### [O-013] Cold-start problem is real
Mem users: "with five notes the AI does little, with five hundred it becomes magical." Graph only becomes valuable past a corpus threshold. Passive capture answers this but takes time. D-013 addresses via corpus bootstrapping at onboarding; specific threshold and mechanism undefined.

### [O-014] The bootstrapping problem has not been fully solved
Context injection requires a populated graph. Empty graph injects nothing useful. What is the minimum behavior that populates the graph enough to make recall demonstrably better than nothing? Partially resolved by recall-first reframe (even manual Apple Notes import is enough to demonstrate value). Needs explicit tracking.

### [O-015] Single-player compounding has no organic discovery mechanism
MIKAI's value compounds for the individual over time, not across users. No social pressure to adopt, no network effect. Every new user is a cold acquisition — the structural reason the Mem category has not produced a venture-scale consumer business. Collaboration features are the typical answer (→ enterprise pivot). Undefined resolution path.

### [O-016] Behavior change as side effect vs. behavior change as requirement
The internet offered capability that didn't exist before; behavior change was a side effect of obvious value exchange. MIKAI's "follows you everywhere" vision may require paradigm adoption before value delivery — the harder side. Context injection (D-015) is on the right side (removes existing pain with no new behavior). The broader passive-capture vision may be on the wrong side. Map each feature against this test.

### [O-017] Ambitious vision vs. fundable wedge
"Follows you everywhere" is the reason to build MIKAI; it is not the seed pitch. Tension is structuring the build so the wedge genuinely compounds into the vision rather than becoming a permanently small product. Context injection (D-015) is current best wedge. Validate that context injection generates the intent graph as a byproduct, so the wedge literally builds the engine that enables the vision.

### [O-026] What is the minimum corpus size for useful tensions?
Mem.ai suggests 10–20 notes for connections. MIKAI's typed edges may require more density for tension detection to produce value. Track the relationship between corpus size and tension-surfacing accuracy across beta users. Related: O-013, O-014, D-013.

### [O-027] Is MCP adoption broad enough to sustain a business?
MCP is supported by Claude Desktop, Cursor, and a growing set of tools — still developer-oriented. If the target is "founders who write a lot," it needs to work without a terminal. Monitor MCP ecosystem growth. Track whether beta users (who are comfortable with MCP config) represent actual target market or only a developer subset.

### [O-037] When should the memory layer be replaced with open source? (Partially closed)
V1 ships with current stack. Graphiti (MIT), Cognee (12K+ GitHub stars), Letta — all open source. MIKAI's value is L4, not L2. Largely closed by ARCH-019 (adopted Graphiti as the L3 backend). Remaining version of the question: if a future alternative (Cognee with dynamic-relationship evolution, or a next-gen OS KG) becomes clearly superior, when does MIKAI switch the default adapter behind the port?

### [O-038] Does the V1 "cross-app memory" framing attract noonchi users or memory users?
If beta users come for memory and stay for memory, the noonchi thesis needs re-examination. If they come for memory and say "I wish it could tell me what to do next," the thesis is validated. Answered by beta user behavior (20-user target). Onboarding question: "What would make this 10x more useful?" Track whether answers cluster around memory/recall or toward task-awareness/next-steps.

---

## Resolved

- **[O-001]** Which surface first? — **Resolved 2026-03-14** via D-019. V1: WhatsApp bot. Final destination: Siri integration.
- **[O-039]** Daemon-restart dedup — **Resolved 2026-04-29** on `feat/stage-2-ingestion-prod`. Per-source content-hash checkpoint shipped: `sync.py` keys Apple Notes by ZIDENTIFIER (UUID) and Claude Code by JSONL byte offset; `mcp_ingest.py` keys cloud sources by ISO poll-time. State persists to `~/.mikai/sync_state.json` after every pass.
- **[O-040]** Daemon lifecycle / supervisor — **Resolved 2026-04-29** via launchd. `infra/graphiti/launchd/` ships a plist template + wrapper script + install README; `KeepAlive` + 30s `ThrottleInterval` handle crash recovery, `RunAtLoad` handles boot. macOS-native — no Docker dependency for the user-data ingestion path.
- **[O-041]** Burst-import API rate limits — **Resolved 2026-04-29** on `feat/stage-2-ingestion-prod`. Async token bucket (`sidecar/rate_limit.py`) wired ahead of every direct `graphiti.add_episode` call in `sync.py` and `mcp_ingest.py`. Defaults: 60 rpm each for DeepSeek and Voyage; per-bucket overrides via `MIKAI_RATELIMIT_<NAME>_RPM` env vars.

---

## Pressing reminders for every build decision

- **"Follows you everywhere" is a destination, not a wedge.** Always know which surface you're proving first.
- **The intent graph is the asset. The surface is a product decision.** Never collapse the engine into a single application prematurely.
- **Sumimasen applies to the product pitch, not just the notification layer.** Don't interrupt the user's existing workflow until confidence is high that the value exchange is worth it.
- **Every new feature: does it serve the engine, or does it serve a surface?** These require different justifications.
- **The monetization model must be compatible with "trust over engagement."** If the growth metric requires compromising the philosophy, the philosophy will lose. Decide this early.
- **Measure day-30 behavior, not day-1 activation.** The ambitious vision compounds slowly. The metric that matters is whether MIKAI has changed what the user does, not whether they installed it.
