# MIKAI Decision Log

Format for each entry:
- **Date:** YYYY-MM-DD
- **Decision:** What was decided
- **Why:** Core reasoning
- **Rejected:** What alternatives were considered and why they lost
- **Revisit if:** Conditions that would reopen this decision

---

## D-001: MIKAI Is an Engine, Not a Product
**Date:** 2026-03
**Decision:** MIKAI is the intent extraction + cognitive profiling engine. Output surfaces (knowledge worker tool, HICCUP, e-commerce layer, child tracker, etc.) are separate product decisions that consume engine output.
**Why:** The core value is the extraction and profiling capability. Committing to a single surface prematurely constrains the opportunity space and forces UX decisions before the engine is proven. Multiple viable surfaces exist — the engine should serve all of them.
**Rejected:** iPad Brief as the primary product (too specific — collapses the engine into one output format). Building a full product surface before proving extraction quality.
**Revisit if:** Engine quality is proven but no surface achieves product-market fit within 6 months — may need to commit to one surface to focus.

---

## D-002: Engine Outputs = Intent Map + Profile (Two Primary Artifacts)
**Date:** 2026-03
**Decision:** The engine produces two structured outputs: an Intent & Goal Map (what the person is trying to do) and a Personality & Economic Profile (how they think and decide). Everything else is downstream.
**Why:** These are the two things no current system extracts well from passive behavior. They are surface-agnostic — any product can consume them. They are also independently valuable (you could sell just the profile, or just the intent map).
**Rejected:** Adding workspace configuration or feed curation as core engine outputs (these are surface-specific transformations of the two primary outputs).
**Revisit if:** A third output type emerges that is genuinely engine-level (not surface-specific).

---

## D-003: Prove Extraction Engine Before Passive Capture
**Date:** 2026-02
**Decision:** Build stream extraction → structured output pipeline first. Chrome extension and passive capture come after.
**Why:** If the extraction output isn't valuable, passive capture doesn't matter. Core engine must produce intent maps and profiles worth consuming.
**Rejected:** Building extension first (puts distribution before engine quality signal).
**Revisit if:** Manual input friction prevents getting enough test data for extraction quality iteration.

---

## D-004: Claude + n8n Over OpenAI AgentKit
**Date:** 2026-01
**Decision:** Use Claude as LLM backbone, n8n for orchestration.
**Why:** Claude's computer use + n8n's visual builder = fastest low-code path. Less glue code than OpenAI's developer-centric stack.
**Rejected:** OpenAI AgentKit (more code-heavy, less plug-and-play for desktop orchestration).
**Revisit if:** Claude's API pricing changes dramatically or n8n hits scaling limits.

---

## D-005: Supabase pgvector for Intent Graph Storage
**Date:** 2026-01
**Decision:** Use Supabase with pgvector extension for embedding storage and semantic search.
**Why:** Combines relational data with vector similarity search in one managed service. Low operational overhead for solo founder.
**Rejected:** Pinecone (separate service, additional cost), Neo4j (powerful graph queries but heavier to manage, overkill for Phase 1).
**Revisit if:** Graph traversal queries become the bottleneck and pgvector's lack of native graph operations limits Noonchi's multi-hop synthesis.

---

## D-006: Sumimasen Is Delivery Middleware, Not Core Engine
**Date:** 2026-03
**Decision:** Sumimasen (intelligent delivery/notification) sits between the engine and surfaces as middleware. It is not part of the core extraction engine.
**Why:** Sumimasen only matters for surfaces that push information to users. Pull-based surfaces don't need it. Keeping it separate preserves engine simplicity and lets different surfaces implement delivery differently.
**Rejected:** Embedding Sumimasen into the engine itself (would couple timing/delivery logic to extraction logic unnecessarily).
**Revisit if:** Every viable surface turns out to need push delivery, making Sumimasen effectively universal.

---

---

## D-007: Mode B as the v1 default synthesis mode
**Date:** 2026-03-10
**Decision:** The chat interface defaults to Mode B (Grounded Synthesis). Mode A and C are available but not default.
**Why:** Mode A (pure retrieval) is too restrictive for a knowledge graph at Phase 1 scale — 12 nodes is not enough to answer most questions from Brian's own thinking alone. Mode C (gap detection) requires a reasoning layer that doesn't exist yet. Mode B delivers immediate value while grounding responses in Brian's actual thinking.
**Rejected:** Mode A as default (insufficient graph density in Phase 1), Mode C as default (not yet built).
**Revisit if:** Graph grows large enough that Mode A produces satisfying answers on its own, or Mode C reasoning layer is built.

---

## D-008: WhatsApp as the second surface after local UI
**Date:** 2026-03-10
**Decision:** Deployment sequence: Local UI → WhatsApp → Vercel web app → Siri/Apple Shortcuts.
**Why:** WhatsApp is Brian's highest daily-use communication surface. The existing WhatsApp AI agent + n8n webhook pattern means the integration path is already partially built — lowest friction path to a surface Brian will actually use daily. Vercel web app comes third because it requires deployment infrastructure. Siri is last — most ambient but most constrained by Apple's Shortcuts API.
**Rejected:** Vercel first (adds deployment complexity before the interface is validated), Siri first (too constrained to validate the synthesis modes properly).
**Revisit if:** WhatsApp API access becomes restricted, or n8n webhook pattern proves unreliable.

---

## D-009: Mode C deferred to Phase 2
**Date:** 2026-03-10
**Decision:** Gap detection (Mode C) is a Phase 2 feature. It will not be built in Phase 1.
**Why:** Mode C requires a reasoning layer above the retrieval layer — analyzing graph structure for contradictions, unresolved tensions, and circling patterns. This is architecturally distinct from retrieval + synthesis and requires the graph to be dense enough to have meaningful structural patterns to analyze. Phase 1 graph (12 nodes) is insufficient for this.
**Rejected:** Building Mode C now (premature — graph too sparse, reasoning layer not designed).
**Revisit if:** Graph exceeds ~100 nodes with typed edges, and retrieval quality is validated.

*Add new decisions below. Number sequentially. Include date, reasoning, rejected alternatives, and revisit conditions.*

---

## D-010: Recall-first, inference-second build sequence
**Date:** 2026-03
**Source:** Thread — Recall-First Architecture & Passive Capture as Moat
**Decision:** Build sequence is: recall validation (Phase 1) → passive capture proving graph richness (Phase 2) → intent inference (Phase 3).
**Why:** Recall is the immediate pain users feel every day. Intent inference compounds only once the graph is dense enough to have structural patterns worth analyzing. Inverting the sequence risks building a sophisticated system with no immediate value proposition.
**Rejected:** Inference-first architecture (requires graph density that Phase 1 cannot produce).
**Revisit if:** Phase 1 recall validation fails and inference-first emerges as the more tractable path.

---

## D-011: Passive capture is the moat, not a convenience feature
**Date:** 2026-03
**Source:** Thread — Recall-First Architecture & Passive Capture as Moat
**Decision:** Passive (ambient) capture is MIKAI's core defensibility mechanism. Intentionally-fed tools are commoditizable. Ambient-fed graphs are not.
**Why:** Mem.ai's trajectory proves that intentional-capture recall can be commoditized by any tool adding AI search over manually-fed content. The only defensible position is a graph populated from the full digital footprint — including things the user never consciously decided to save.
**Rejected:** Framing passive capture as Phase 2 infrastructure or a convenience feature (understates its strategic centrality).
**Revisit if:** A manually-fed graph proves demonstrably sufficient and passive capture engineering cost exceeds defensibility benefit.

---

## D-012: Phase 1 and Phase 2 validations are sequential, not parallel
**Date:** 2026-03
**Source:** Thread — Recall-First Architecture & Passive Capture as Moat
**Decision:** Two distinct validations must run in sequence. Validation 1 (Phase 1): does the retrieval and structuring logic work? Testable with Apple Notes corpus. Validation 2 (Phase 2): does passive capture populate the graph with higher signal than intentional clipping? Requires the capture layer to be built and run over time. Do not conflate them.
**Why:** Conflating the validations risks building Phase 2 infrastructure before Phase 1 retrieval quality is proven, or measuring Phase 2 success by Phase 1 criteria. A positive Phase 1 result proves the engine. The product is only proven when passive capture at ambient scale feeds the engine and recall still works.
**Rejected:** Running both validations simultaneously (resource constraint; Phase 2 methodology requires Phase 1 to succeed first).
**Revisit if:** Phase 1 validation is blocked by insufficient manual corpus.

---

## D-013: Corpus bootstrapping at onboarding is required
**Date:** 2026-03
**Source:** Thread — Recall-First Architecture & Passive Capture as Moat
**Decision:** New users must bootstrap the graph at onboarding — via Apple Notes import, browser history, or equivalent — to deliver day-1 value. The cold-start problem is real.
**Why:** Mem's own user data confirms: "with five notes the AI does little, with five hundred it becomes magical." Passive capture alone takes weeks to accumulate. Without an onboarding import, MIKAI has no value during the critical first-impression window.
**Rejected:** Relying on passive capture alone to populate the graph from day 1 (too slow); setting no expectations and accepting cold-start churn as normal.
**Revisit if:** A minimum viable onboarding corpus threshold is identified that can be reached through a mechanism other than bulk import.

---

## D-014: "Second brain" and "follows you everywhere" rejected as primary positioning language
**Date:** 2026-03
**Source:** Thread — Product Positioning & Strategic Constraints
**Decision:** Neither "second brain" nor "platform agnostic second brain that follows you everywhere" should be used as primary positioning language.
**Why:** "Second brain" is a dead category signal — Notion, Roam, Obsidian, Logseq all sold this framing, none became category-defining. "Follows you everywhere" is infrastructure language that triggers immediate VC pattern-matching to Mem.ai and Rewind. Positioning must describe the behavior change MIKAI produces, not the metaphor it resembles.
**Rejected:** Keeping these as secondary language while leading with them in the pitch (same problem, slower correction).
**Revisit if:** Positioning research demonstrates these phrases test well with the actual target user.

---

## D-015: Context injection into existing LLM conversations is the strongest near-term wedge
**Date:** 2026-03
**Source:** Thread — Product Positioning & Strategic Constraints
**Decision:** Context injection — removing the cold-start friction of every new LLM conversation — is the strongest near-term expression of the engine's value and the most fundable single claim.
**Why:** Immediate pain removal, zero new behavior required from the user, measurable outcome, generates the intent graph as a byproduct. Current best candidate answer to "what is MIKAI's email?"
**Rejected:** Leading with passive capture as the pitch (harder to validate quickly); leading with intent inference (requires graph density not yet proven).
**Revisit if:** Phase 1 extraction quality validation suggests a different wedge performs better in practice. Question should remain open and be revisited after Phase 1.

---

## D-016: Monetization model compatible with "trust over engagement" is an unresolved blocking question
**Date:** 2026-03
**Source:** Thread — Product Positioning & Strategic Constraints
**Decision:** Flagged as a blocking strategic question. A monetization model that does not require compromising the "trust over engagement" philosophy has not been defined. Must be resolved before Phase 3.
**Why:** Trust over engagement is the right ethical stance and is in direct conflict with the engagement metrics that drive consumer SaaS growth. If unresolved, the growth model will eventually override the philosophy.
**Rejected:** Treating monetization as a Phase 3 problem with no present constraint (build decisions made now shape what monetization is possible later).
**Revisit if:** Any monetization model is proposed — evaluate it explicitly against this constraint.

---

## D-017: Behavior change argument is Series C narrative, not seed narrative
**Date:** 2026-03
**Source:** Thread — Product Positioning & Strategic Constraints
**Decision:** The "people will change their behavior" argument belongs in the Series C deck, not the seed pitch or near-term product framing.
**Why:** Every founder who successfully argued "behavior will change" had a specific wedge that worked today, with existing behavior, as the foundation for the bigger vision. MIKAI's near-term framing must be the immediate pain it removes, not the paradigm shift it enables.
**Rejected:** Leading with behavior change in the seed pitch (requires paradigm adoption before value delivery).
**Revisit if:** Context injection wedge achieves meaningful adoption and the behavior change argument becomes demonstrable rather than theoretical.

---

## D-018: Desire Taxonomy Adopted as North Star Model
**Date:** 2026-03-14
**Source:** Deep interview session — architectural design review with Claude (see `.omc/specs/deep-interview-desire-taxonomy.md`)
**Decision:** MIKAI's inference model is oriented around three desire levels — immediate, instrumental, and terminal — each with distinct temporal properties and extraction mechanisms. Terminal desire inference from instrumental desire trajectory is the North Star product capability. The inference model (not the capture mechanism) is the competitive moat.
**Why:** Facebook and advertisers have demonstrated that desire inference from fragmentary behavioral data is possible at scale — but they optimize for immediate desires (engagement). MIKAI's thesis is that aligning inference with terminal desires creates more long-term value. Friction is a signal, not noise: high-effort engagement indicates instrumental desire more reliably than high-engagement behavior. The corpus MIKAI ingests (personal notes, reflections, tensions) contains friction signals that behavioral data misses.
**Rejected:** Positioning the moat as passive capture scale (commoditized by OS players). Positioning the graph as a "second brain" or knowledge archive (catalog of what you know, not what you want). Building V2/V3 desire inference during Phase 1 (premature before engine quality is proven).
**Revisit if:** O-020 evaluation results show that extraction quality is too low to support desire-level classification, or if terminal desire inference proves statistically intractable on personal corpus sizes.

---

## D-019: WhatsApp as V1 Delivery Surface — Siri as Final Destination
**Date:** 2026-03-14
**Source:** Architecture design session
**Decision:** V1 delivery surface is WhatsApp via WhatsApp Business API + n8n. Final destination is Siri integration (Apple Shortcuts webhook near-term → SiriKit medium-term → Apple Intelligence long-term). iMessage is explicitly rejected as a proactive delivery surface for V1.
**Why:** iMessage has no reliable API for sending proactive messages programmatically. WhatsApp Business API is mature, has n8n connector, and was already in the roadmap (D-008). The assistant experience — "feels like an assistant is always messaging you, managing your life" — is achievable through WhatsApp without OS integration. Siri is the endgame because MIKAI's final form is an OS-level assistant layer.
**Rejected:** iMessage for V1 proactive push (API limitation — can read via MCP locally but cannot send proactively at scale). Building a new dedicated app surface before validating the model.
**Revisit if:** Apple opens iMessage Business API, or WhatsApp API costs become prohibitive at scale.

---

## D-020: MCP as Integration Layer — No Custom Connectors
**Date:** 2026-03-14
**Source:** Architecture design session
**Decision:** New data sources are connected via MCP servers, not custom sync scripts. The current apple-notes/sync.js and local-files/sync.js connectors are Phase 1 exceptions. From Phase 2 onward, all source integrations use MCP.
**Why:** Custom connectors per source (Gmail connector, iMessage connector, calendar connector) is a maintenance spiral. MCP makes new sources configuration, not code. The ingestion pipeline becomes a generic MCP client rather than a collection of bespoke scripts.
**Rejected:** Writing custom connectors for each new source (8+ sources required = 8+ maintenance burdens). Building proprietary integrations before validating which sources have signal.
**Revisit if:** A required source has no MCP server and the signal it contains is high enough to justify custom work.

---

## D-021: Two-Track Extraction Architecture
**Date:** 2026-03-14
**Source:** Architecture design session
**Decision:** The extraction pipeline has two tracks. Track A (Semantic): Claude reasoning-map prompt for authored content — notes, reflections, LLM exports. Track B (Structural): rule/pattern-based extraction for behavioral traces — email threads, messages, calendar gaps, transactions. Both tracks write to the same graph. A periodic Claude synthesis pass draws edges connecting nodes across tracks.
**Why:** Running every data source through the Claude reasoning-map prompt is inefficient and wrong for behavioral traces. An email thread with "let's find a time" doesn't need LLM interpretation — the signal is structural. Claude earns its cost at the synthesis layer (connecting behavioral signals to authored content), not at the individual trace extraction layer. Running Claude over every browser visit or message would be prohibitively expensive and produce low-quality nodes.
**Rejected:** Everything through Claude (expensive, overkill for behavioral traces). Separate graphs per track (retrieval across tracks becomes impossible). Keeping tracks strictly separate without synthesis edges (loses the most valuable signal: behavioral trace + authored context together).
**Revisit if:** A structural extraction pattern proves too brittle and produces too many false positives, requiring LLM validation.

---

## D-022: Schema Stays Minimal Until Phase Needs It
**Date:** 2026-03-14
**Source:** Architecture design session
**Decision:** Do not add desire_level, extraction_method, confidence_score, first_seen_at, last_seen_at, occurrence_count, predictions table, or node_clusters table until the phase that needs them begins. Schema additions are documented in docs/ARCHITECTURE.md as planned but not yet migrated.
**Why:** Premature schema additions create nullable columns with no data and no extraction logic to populate them. They add cognitive overhead without value. Phase 1 does not require desire-level classification. Add columns when the extraction logic that populates them is being built.
**Rejected:** Adding all future schema columns now for "forward compatibility" (adds complexity without function until the extraction layer is ready).
**Revisit if:** A Phase 2 build task is blocked because the schema addition wasn't made earlier.

---

## D-023: iPad Brief Removed Entirely
**Date:** 2026-03-14
**Source:** Architecture design session
**Decision:** The iPad Brief is removed as a product concept. app/api/brief/generate and app/api/brief/[id] endpoints are deleted. All references to the iPad Brief, scrollable brief, 5-15 minute read, and daily brief are removed from all project files.
**Why:** The iPad Brief was defined as the primary output artifact before the desire inference model was the north star. The delivery surface is now WhatsApp (proactive push) and eventually Siri. A scrollable synthesis document is not compatible with an ambient assistant model. Brief synthesis as a background capability may return, but not as a product-facing surface.
**Rejected:** Keeping brief generation as a background capability while removing the product surface (the code itself implies the wrong product direction — delete cleanly).

---

## D-024: Primary V1 Use Case — Stalled Immediate Desires
**Date:** 2026-03-14
**Source:** Architecture design session
**Decision:** V1 is not terminal desire inference. V1 is detection and surfacing of stalled immediate desires — things that entered the digital ecosystem with clear intent but never resolved due to cognitive load. The table to buy, the appointment to book, the trip to plan, the budget about to be exceeded. Two validation criteria: (1) MIKAI surfaces something the user was going to do anyway before they did it (prediction), (2) MIKAI surfaces it and the user acts because of the prompt (behavior change).
**Why:** Terminal desire inference requires months of trajectory data and a validated extraction model. Stalled immediate desire detection is tractable from a small corpus, produces immediate behavioral validation signal, and solves a real pain point (cognitive load of tracking small decisions across many apps). It is also the wedge that justifies WhatsApp delivery.
**Rejected:** Terminal desire inference as V1 (requires data volume and model validation not yet possible). Passive capture-first before engine validation (D-003 still holds).

---

## D-026: Inference Layer Built from ML Infrastructure — LLM Reserved for Three Roles
**Date:** 2026-03-14
**Source:** Architecture design session — enterprise CDP + recommendation engine analysis
**Decision:** The inference layer is built from proven ML infrastructure, not LLM calls. LLM is reserved for exactly three roles: (a) Track A extraction of authored content — already built, (b) terminal desire synthesis — interpretive pass across full graph trajectory, (c) natural language generation for WhatsApp delivery — one call per delivery cycle. Everything between is feature computation (SQL aggregations on the graph schema), scoring (rule engine first, gradient-boosted classifier once 50+ dismiss/confirm labels exist from the predictions table), and ranking.
**Why:** Immediate desire detection is a classification problem with learnable features — `occurrence_count`, temporal gaps, action verbs, source type score, edge density. Running Claude on every node evaluation to ask "is this a stalled desire?" is both expensive and wrong-tool. The model can't learn from dismiss/confirm signals if it's doing inference via generation rather than structured classification. Enterprise CDPs and recommendation engines use gradient-boosted trees (XGBoost/LightGBM) for the same reason — sub-millisecond inference, interpretable outputs, trainable from behavioral labels.
**Rejected:** LLMs as primary inference engine (conflates language generation with desire classification — separable problems). Full classical ML for everything (terminal desire inference genuinely requires LLM reasoning — no learnable features, no labels, output is structured reasoning not a probability score).
**Revisit if:** A specific inference task proves intractable with ML approaches and demonstrably requires LLM reasoning beyond the three designated roles.

---

## D-027: Source Type Determines Extraction Tool
**Date:** 2026-03-14
**Source:** Architecture design session
**Decision:** Authored content (Apple Notes, LLM threads, personal reflections, Perplexity threads) → LLM Track A reasoning-map extraction. Behavioral traces (email, iMessage, WhatsApp message history, browser behavior) → rule engine / structural pattern detection Track B. The LLM reasoning-map prompt must never be applied to behavioral traces.
**Why:** The reasoning-map prompt is designed for content where a person has already synthesized their thinking into language — the eval results confirm this: tension nodes from personal reflections scored 5/5, team operations notes from external sources scored 2/3. Behavioral traces are raw action data — thread with no reply after N days, question with no follow-through, topic visited repeatedly. These are structural pattern-matching problems. Applying the LLM reasoning-map to them produces hallucinated intent from a list of emails rather than detecting real staleness patterns.
**Rejected:** Unified LLM extraction for all source types (wrong tool for behavioral data, expensive, pattern-matching problems are better solved with rule engines that can be trained from dismiss/confirm signals).

---

## D-028: PuppyGraph Phase 1.5 Experiment Gates Infrastructure Migration
**Date:** 2026-03-14
**Source:** Architecture design session — enterprise graph database analysis
**Decision:** Phase 1 recall proofs are artificially clean because the corpus is small and deliberately structured (Apple Notes export). Before migrating infrastructure, validate that typed edge traversal produces meaningfully different recall results compared to vector search alone — at real corpus size. The Phase 1.5 experiment: add PuppyGraph on top of existing Supabase Postgres (zero migration, zero data movement), run equivalent queries using graph traversal and pure vector similarity, compare recall quality. Decision to migrate to FalkorDB (self-hosted) or stay on Supabase is made from this evidence, not from theory.
**Migration decision tree:**
- PuppyGraph shows typed edge traversal produces meaningfully better recall → migrate to FalkorDB self-hosted before Phase 2 MCP integrations begin
- Improvement is marginal at current corpus size → stay on Supabase until passive capture pushes the graph to the density where the difference becomes visible
**Why:** Supabase cannot execute the full product vision at scale (multi-hop traversal, temporal validity windows, trajectory-based terminal desire inference). But Phase 1 does not stress Supabase — the limitation hits at thousands of densely-connected behavioral trace nodes, not hundreds of manually-ingested notes. Building a migration before the limitation is empirically visible is adding infrastructure cost without evidence. PuppyGraph answers the question cheaply.
**Rejected:** Migrating before validating (adds complexity without evidence that the limitation is real at current scale). Deferring the question entirely to Phase 3 (builds Phase 2 on wrong infrastructure under production pressure — migration cost compounds with every Phase 2 feature).
**Revisit if:** PuppyGraph experiment is inconclusive at current corpus size — may need to ingest more sources first to make the comparison meaningful.

---

## D-025: Node Lifecycle Management Deferred
**Date:** 2026-03-14
**Source:** Architecture design session
**Decision:** Node lifecycle management — when to engage a node (surface it), compact it (merge with related nodes), or discard it (resolved desire, stale signal) — is documented as a future requirement but not built in Phase 1 or Phase 2.
**Why:** The policy for lifecycle management depends on empirical data about which nodes produce value when surfaced. Building it before the WhatsApp delivery loop generates behavioral signal would be policy without evidence. The schema should note the requirement but not implement it prematurely.
**Rejected:** Building lifecycle management before validating which nodes are worth surfacing (premature optimization of a system whose signal quality is unproven).
**Revisit if:** Graph grows large enough that stale nodes degrade retrieval quality before Phase 4.

---

## Technical Architecture Decisions
*These decisions govern how MIKAI is built. Product decisions above govern what is built. Both must be read together. When a technical decision conflicts with a product decision, flag it — do not resolve it yourself.*

---

### [ARCH-014] Decouple ingestion from graph extraction
**Date:** 2026-03-13
**Status:** SETTLED

**Decision:** The ingestion pipeline (`/api/ingest/batch`) does chunking and raw content storage only — no LLM calls. Graph extraction (Claude reasoning-map prompt + Voyage embeddings) runs in a separate standalone script (`engine/graph/build-graph.js`).

**Why:** LLM calls in the ingestion path were causing timeouts and silent failures. Decoupling means: (a) ingestion never fails due to LLM issues, (b) graph building is independently re-runnable without re-ingesting, (c) extraction prompts can be iterated and `--rebuild` run across the full corpus without touching ingestion logic.

**Practical consequence:** After any batch ingest, run `npm run build-graph` separately to extract graphs. `build-graph.js` picks up all sources with `chunk_count > 0` and `node_count = 0`.

**Rejected:** Keeping extraction in the batch route (too slow, timeouts, coupled failure modes).

---

### [ARCH-015] Graph traversal retrieval with typed edge priority ordering
**Date:** 2026-03-13
**Status:** SETTLED

**Decision:** Retrieval expands beyond vector search seed nodes via one-hop edge traversal. Connected nodes are ranked by the highest-priority edge type connecting them to any seed node. Total context is capped at 15 nodes. Priority order: `unresolved_tension(0) > contradicts(1) > depends_on(2) > partially_answers(3) > supports(4) > extends(5)`.

**Why:** Pure vector search returns nodes that are semantically similar but misses the most valuable signal — active tensions and contradictions. By prioritizing those edge types in traversal, Claude's context is biased toward unresolved thinking rather than supporting evidence.

**Implementation:** `lib/graph-retrieval.ts` — `buildSubgraph()` and `serializeSubgraph()`. Used by both `/api/chat` and `/api/search`.

**Rejected:** Pure vector search retrieval (misses graph structure); full multi-hop traversal (too broad, dilutes context quality).

---

### [ARCH-016] Embeddings at node level, not chunk level; Voyage AI voyage-3
**Date:** 2026-03-13
**Status:** SETTLED

**Decision:** Embeddings are generated per node (extracted concept/decision/tension), not per raw chunk. Model: Voyage AI `voyage-3`, 1024 dimensions.

**Why:** Embedding chunks produces retrieval over raw content. Embedding nodes produces retrieval over structured reasoning units. A node like "trust vs. engagement tension" is more semantically precise than the paragraph it was extracted from. This makes similarity search meaningfully better.

**Rejected:** Chunk-level embeddings (less precise for structured knowledge retrieval).

---

### [ARCH-017] Extraction node/edge taxonomy expanded; max_tokens 4096
**Date:** 2026-03-13
**Status:** SETTLED

**Decision:** The extraction prompt uses an expanded taxonomy:
- **Node types:** `concept`, `project`, `resource`, `question`, `decision`, `tension`
- **Edge types:** `supports`, `contradicts`, `extends`, `questions`, `depends_on`, `unresolved_tension`, `partially_answers`
- **Edge note field:** Every edge carries a free-text `note` explaining the specific relationship
- **max_tokens:** 4096 (was 1024 — truncation caused silent failures on documents >600 words)

**Why:** The `tension` node type captures active contradictions the person is holding as a first-class entity. `unresolved_tension` and `partially_answers` edges capture the structure of open thinking that `supports/contradicts` alone cannot. The `note` field makes edge relationships legible to Claude during synthesis.

**Schema requirement:** `edges` table requires `note TEXT` column. Migration: `infra/supabase/add_edge_note.sql`.

**Supersedes:** ARCH-007 (node taxonomy) and ARCH-008 (edge taxonomy).

---

### [ARCH-001] Supabase as the single database — no separate vector DB
**Date:** 2026
**Status:** SETTLED

**Decision:** Use Supabase pgvector for both relational data and vector embeddings. Do not add Pinecone, Weaviate, Chroma, or any dedicated vector database.

**Why:** At personal scale (one user, thousands of nodes not millions), pgvector performance is more than sufficient. The architectural simplicity of a single database far outweighs the marginal performance gain of a dedicated vector DB. Every additional service is a failure point and a cost center. Aligns with D-005.

**Rejected:** Pinecone (overkill, adds infra complexity, costs money at rest), Chroma (local-only, breaks cloud-first model), Weaviate (heavy, self-hosted complexity not justified).

---

### [ARCH-002] Claude as primary LLM — SUPERSEDED by ARCH-013 for embeddings
**Date:** 2026
**Status:** PARTIALLY SUPERSEDED

**Decision:** Use Claude Sonnet (claude-sonnet-4-6) for all synthesis, extraction, and reasoning tasks. Embeddings use Voyage AI — see ARCH-013.

---

### [ARCH-003] n8n for orchestration, not LangChain or custom backend
**Date:** 2026
**Status:** SETTLED

**Decision:** Use n8n cloud as the orchestration layer. Do not build a custom orchestration backend. Do not use LangChain, LangGraph, or similar frameworks.

**Why:** Brian has no software development background. n8n's visual-first interface means orchestration logic can be authored and debugged without code. Aligns with D-004.

**Rejected:** LangChain (code-heavy, abstracts things we need to control), LangGraph (designed for multi-agent production systems), Custom FastAPI backend (requires significant engineering investment).

---

### [ARCH-004] Next.js for frontend, not standalone React or Vue
**Date:** 2026
**Status:** SETTLED

**Decision:** Use Next.js (App Router) deployed on Vercel for all frontend surfaces including the web app and API routes.

**Why:** API routes in Next.js eliminate the need for a separate backend service in Phase 1. Vercel deployment is one command. App Router supports server components which reduce client-side complexity.

**Rejected:** Standalone React/Vite (requires separate API hosting), Vue/Nuxt (no advantage, less ecosystem alignment).

---

### [ARCH-005] No authentication in Phase 1
**Date:** 2026
**Status:** SETTLED

**Decision:** Phase 1 has no user authentication. Single-user personal application. API routes not publicly exposed in a way that requires auth.

**Why:** Auth adds significant development overhead. For a personal tool running on a private Vercel deployment, it is unnecessary friction. Phase 3 adds auth when multi-user requirements emerge.

**Rejected:** Supabase Auth from day one (premature), Clerk / Auth0 (same objection).

---

### [ARCH-006] TypeScript throughout, no plain JavaScript
**Date:** 2026
**Status:** SETTLED

**Decision:** All code is TypeScript.

**Why:** Type safety catches a large class of bugs, especially across the data pipeline where shape mismatches (embedding dimensions, JSONB structure) cause silent failures.

---

### [ARCH-007] Node type taxonomy (settled for Phase 1)
**Date:** 2026
**Status:** SETTLED

**Decision:** Phase 1 uses these fixed node types: `concept`, `project`, `resource`, `question`, `decision`.

**Why:** An open taxonomy creates inconsistency in retrieval. A fixed taxonomy makes filtering and graph traversal predictable.

**Rejected:** Free-form tags (too inconsistent), LLM-generated types (unpredictable, breaks graph queries).

---

### [ARCH-008] Edge relationship taxonomy (settled for Phase 1)
**Date:** 2026
**Status:** SETTLED

**Decision:** Phase 1 uses these fixed edge types: `supports`, `contradicts`, `extends`, `questions`, `depends_on`.

**Why:** These five types cover the primary ways ideas relate to each other in knowledge work. Aligns with typed edge model in 03_PRD_CURRENT.md.

---

### [ARCH-013] Switch embeddings from OpenAI to Voyage AI
**Date:** 2026-03-10
**Status:** SETTLED — supersedes ARCH-002 (embedding component)

**Decision:** Use Voyage AI `voyage-3` model for all vector embeddings. Embedding dimension: 1024. Replaces OpenAI text-embedding-3-small.

**Why:** Voyage AI's retrieval-optimized models outperform OpenAI embeddings on knowledge graph and semantic search tasks. voyage-3 is purpose-built for retrieval quality. Brian chose this explicitly.

**Rejected:** OpenAI text-embedding-3-small (good general-purpose model but voyage-3 retrieves more relevant results for this use case).

---

### [ARCH-018] Stay on Supabase through Phase 2 — FalkorDB migration deferred
**Date:** 2026-03-15
**Status:** SETTLED — closes D-028 (PuppyGraph experiment gate)

**Decision:** Do not migrate to FalkorDB before Phase 2. Continue using Supabase Postgres for graph storage and traversal.

**Evidence:** Phase 1.5 graph traversal comparison (engine/eval/results/puppygraph-comparison-2026-03-15.json):

| Query | 1-hop nodes | 2-hop nodes | 1-hop tensions | 2-hop tensions |
|---|---|---|---|---|
| What tensions am I holding about MIKAI? | 13 | 16 | 4 | 5 |
| What decisions am I second-guessing? | 15 | 22 | 4 | 6 |
| Where does my thinking contradict itself? | 14 | 19 | 4 | 5 |
| What depends on something I haven't resolved? | 15 | 25 | 4 | 6 |
| What am I avoiding deciding? | 14 | 18 | 3 | 3 |
| **Average** | **14.2** | **20.0** | **3.8** | **5.0** |

Avg tension edge delta: **+1.2** (gate was ≥2). Multi-hop traversal adds nodes but not enough high-priority tension/contradiction edges to justify migration at 842-node corpus size.

**Why:** The value of a dedicated graph DB (FalkorDB/Neo4j) is multi-hop traversal at scale and temporal validity windows. At current corpus size, 1-hop SQL-based traversal already captures the most relevant tension edges. The marginal gain from 2-hop does not justify the migration cost, schema rewrite, and operational overhead before Phase 2 is proven.

**Revisit if:** Corpus exceeds ~5,000 nodes (Supabase recursive CTE degradation threshold) OR multi-hop traversal is needed for structural pattern detection in Phase 2 behavioral traces OR Graphiti + FalkorDB spike (D-028) shows qualitatively better temporal entity modeling.

---

## D-029: Direct SQLite Access for iMessage — No MCP Server
**Date:** 2026-03-15
**Decision:** iMessage connector reads `~/Library/Messages/chat.db` directly via `better-sqlite3`. No MCP server, no intermediary.
**Why:** D-020 established MCP as the integration layer, but MCP server development adds weeks of overhead for a personal use case. Direct SQLite access is zero-latency, requires no API keys, and works offline. The `chat.db` schema is stable and well-documented. For a single-user engine, the MCP abstraction provides no value.
**Rejected:** Building an MCP server wrapper for Messages (would add a separate process, OAuth surface, and maintenance overhead for no user-visible benefit at this scale). Apple's MessageKit API (requires macOS app, not a script).
**Revisit if:** Multi-user support is required, or Apple changes `chat.db` schema in a future macOS version.

---

## D-030: Daily Sync via macOS launchd — No Persistent Process
**Date:** 2026-03-15
**Decision:** MIKAI's daily sync pipeline (iMessage → Gmail → build-graph) runs as a macOS launchd job at 06:00. No persistent daemon, no cron, no background server.
**Why:** launchd is the native macOS task scheduler — more reliable than cron on macOS (survives sleep/wake cycles), zero infrastructure overhead, and integrates with system lifecycle. A persistent daemon would consume memory continuously for a job that needs to run once per day. launchd handles retry and logging natively.
**Rejected:** cron (less reliable on macOS due to sleep/wake), a persistent Node.js daemon (unnecessary resource use), GitHub Actions (requires internet and secrets exposure).
**Revisit if:** Sync frequency increases to sub-hourly, or the pipeline moves to a server environment where cron or systemd is more appropriate.

---

## ARCH-019: Phase 2 Schema Additions — `track`, `resolved_at` Columns
**Date:** 2026-03-15
**Decision:** Added two columns to the `nodes` table: `track TEXT` (values: `'A'` for LLM-extracted nodes, `'B'` for behavioral trace nodes) and `resolved_at TIMESTAMPTZ` (set when a stalled desire is resolved, used by rule engine high-confidence rule).
**Why:** `track` enables build-graph.js to route processing correctly and lets queries filter by extraction method. `resolved_at` is required by the `scoreNode()` high-confidence stall rule (`resolved_at === null` is one of four conditions for 0.8 score). Both were deferred per D-022 (schema stays minimal) and added now that Phase 2 builds the logic to populate them.
**Rejected:** Storing track as a node metadata JSON field (not queryable efficiently), deriving resolved status from edge types (would require a join on every scoring pass).
**Revisit if:** A third track type (e.g., Track C for structured document extraction) is needed.

---

## D-031: Phase 3 Reprioritized — MCP Server Before WhatsApp
**Date:** 2026-03
**Source:** Competitive Strategy & Positioning Analysis
**Decision:** Phase 3 (WhatsApp delivery) deprioritized. MCP server exposing the knowledge graph to Claude Desktop and Cursor is the new Phase 3 launch target.
**Why:** WhatsApp delivery requires solving proactive intelligence (what to surface, when, how often) — the hardest unsolved problem. MCP context injection is reactive (user asks, graph answers) — the easiest solved problem. WhatsApp has a dismiss rate gate that could fail. MCP plugs into existing surfaces with zero new UX. Phase 1 eval (accuracy 4.0, non-obviousness 3.6) already validates the reactive path.
**Rejected:** WhatsApp first (requires proactive intelligence not yet built), custom UI (unnecessary when MCP connects to existing tools).
**Revisit if:** MCP adoption proves too niche to sustain a business, or proactive delivery becomes tractable before MCP launches.

---

## D-032: HICCUP Shelved — Different Product, Different Market
**Date:** 2026-03
**Source:** Competitive Strategy & Positioning Analysis
**Decision:** HICCUP (household coordination AI) is shelved entirely. It is a different product targeting a different market (household multi-person coordination) with different distribution requirements.
**Why:** HICCUP's core value (multi-person household state management) is orthogonal to MIKAI's core value (single-user intent graph). Building both dilutes focus. The household coordination market (vs. Howie) requires a completely different go-to-market and trust architecture.
**Rejected:** Running HICCUP as a parallel product (resource dilution), integrating HICCUP into MIKAI (different users, different needs).
**Revisit if:** MIKAI's engine proves valuable enough to power household coordination as a surface, or if the consumer AI market shifts toward multi-person contexts.

---

## D-033: Launch Positioning — "The AI That Knows What You're Stuck On"
**Date:** 2026-03
**Source:** Competitive Strategy & Positioning Analysis
**Decision:** Primary positioning: "The AI that knows what you're stuck on." Not "second brain," not "follows you everywhere," not "intent prediction engine."
**Why:** No product in the competitive landscape (Howie, Granola, Mem0, Mem.ai) surfaces unresolved tensions or contradictions. Mem.ai surfaces related notes but cannot tell you two notes contradict each other. MIKAI's typed edges (contradicts, unresolved_tension, partially_answers) are the structural basis for this claim. The positioning describes a user-felt experience, not a technical capability.
**Rejected:** "Second brain" (dead category signal — D-014), "follows you everywhere" (infrastructure language), "intent prediction engine" (Series C narrative — D-017).
**Revisit if:** Beta user feedback suggests a different framing resonates more strongly.

---

## D-034: 30-Day Beta Target — 5 Users via MCP
**Date:** 2026-03
**Source:** Competitive Strategy & Positioning Analysis
**Decision:** 30-day launch target: 5 beta users querying their personal graphs via MCP in Claude Desktop. Week 1: MCP server. Week 2: onboarding pipeline for non-Brian users. Week 3: private beta recruitment. Week 4: iterate and ship public beta.
**Why:** The MCP server is largely a protocol wrapper around existing /api/chat infrastructure. 5 users is enough to test extraction quality on non-Brian content (the highest-risk unknown) while small enough to support personally.
**Rejected:** Larger beta (support overhead), solo use only (doesn't test generalization).
**Revisit if:** MCP server takes longer than 1 week, or extraction quality on non-Brian content is too poor to ship.

---

## D-035: Beta Success Metric — Daily Queries + Accuracy Rating
**Date:** 2026-03
**Source:** Competitive Strategy & Positioning Analysis
**Decision:** Beta success criteria: >3 daily queries per user AND >3.5 accuracy rating on tension surfacing queries.
**Why:** Daily query count measures habitual value. Accuracy on tension surfacing specifically (not general recall) tests MIKAI's unique differentiator — the thing no competitor does.
**Rejected:** NPS alone (too abstract), retention only (doesn't measure the unique value prop).
**Revisit if:** Tension surfacing proves too hard to evaluate with a 5-point scale, or users primarily use MIKAI for general recall rather than tension detection.

---

## D-036: Features to Adopt from Memory Infrastructure Competitors
**Date:** 2026-03-22
**Source:** Architecture gap assessment vs Mem0, Zep/Graphiti, Hindsight, Letta
**Decision:** Adopt specific architectural patterns from competitors while preserving MIKAI's unique differentiators (epistemic edges, tension surfacing, stall detection).

**From Hindsight (91.4% LongMemEval):**
- Adopt: BM25 keyword search as parallel retrieval path (Supabase `to_tsvector`)
- Adopt: Reciprocal Rank Fusion (RRF) for merging vector + keyword results
- Defer: Cross-encoder reranking, spreading activation (P2)

**From Zep/Graphiti:**
- Adopt: Temporal validity on edges (`valid_from`, `expired_at` columns)
- Adopt: Edge invalidation pattern (supersede, don't delete)
- Defer: Full bitemporal model with 4 timestamps (P2)

**From Mem0:**
- Adopt: Write operations from conversation (add_note, mark_resolved)
- Adopt: Embedding similarity dedup on node insertion (>0.92 = skip)
- Skip: Full LLM-based Update Resolver (MIKAI's zero-LLM approach is more cost-efficient)

**From Letta (MemGPT):**
- Adopt: Tiered memory concept (L1 brief = core memory, L2 segments = recall, L3 graph = archival)
- Skip: Agent self-editing memory (too expensive, non-deterministic per D-026)

**Why:** MIKAI's competitive advantages are in intelligence (epistemic edges, tension detection, stall inference). The infrastructure (retrieval, write path, temporal) is behind commodity competitors. Adopting infrastructure patterns levels the playing field while preserving the intelligence moat.
**Revisit if:** Any adopted pattern conflicts with MIKAI's zero-LLM cost architecture.

---

## D-037: MCP Write Tools — mark_resolved and add_note
**Date:** 2026-03-22
**Source:** P0-1 from docs/ARCHITECTURE_GAPS.md
**Decision:** Add two write tools to the MCP server: `mark_resolved(node_id)` sets `resolved_at = now()` on a node, and `add_note(content, label?)` creates a new source + segments directly from conversation. Both are deterministic writes — no LLM needed.
**Why:** Without write tools, Claude cannot record user corrections during conversation. This breaks the trust loop: Claude surfaces a stalled item → user says "I did that" → next session Claude surfaces it again. The write tools close this loop.
**Rejected:** Full LLM-based Update Resolver (expensive, non-deterministic). Letta-style agent self-editing (requires full runtime adoption).
**Revisit if:** Write operations create data quality issues that require LLM validation before writes.

---

## D-038: Tiered Memory Architecture (L1/L2/L3)
**Date:** 2026-03-22
**Source:** Letta MemGPT architecture + MIKAI get_brief design
**Decision:** Formalize the three-tier memory model:
- L1 (always in context, ~400 tokens): `get_brief` — tensions, stalled items, projects, stats
- L2 (on-demand vector search): `search_knowledge` — 15,954 segments
- L3 (on-demand graph traversal): `search_graph` — 2,246 nodes with epistemic edges
Each tier serves a different query depth. L1 prevents unnecessary L2/L3 calls. L2 handles most queries. L3 surfaces structural reasoning relationships.
**Why:** CPU cache analogy — fast L1 handles 80% of context needs, L2/L3 handle depth. Reduces per-conversation cost and latency.
**Revisit if:** L1 brief proves insufficient and Claude consistently needs to call L2 for basic questions.

---

## D-039: Next.js Web Layer Removed — MCP Server Is the Sole Product Surface
**Date:** 2026-03-24
**Source:** Path 2 (Category Creation) alignment — `MIKAI_Three_Paths_Strategic_Map.md`
**Decision:** Removed the entire Next.js web application layer (`app/` directory, Next.js/React/Tailwind dependencies, API routes). The MCP server (`surfaces/mcp/server.ts`) is now the sole product surface. All ingestion uses `engine/ingestion/ingest-direct.ts` (standalone Supabase writes). No web server is required for any operation.

**What was removed:**
- `app/` directory (chat endpoint, synthesis endpoint, ingest endpoint, graph API, search API, web UI pages)
- `lib/graph-retrieval.ts`, `lib/segment-retrieval.ts` (logic already duplicated in MCP server)
- `lib/extraction-logger.ts` (unused by engine)
- Next.js, React, React-DOM, Tailwind, PostCSS from dependencies (removed 246 packages)
- `next.config.ts`, `next-env.d.ts`, `postcss.config.mjs`
- 4 experimental Perplexity scraper variants (kept `perplexity-playwright.ts` — the final automated version)
- Google OAuth client secret file (moved to `.gitignore`)

**Why:** Path 2 delivers the product entirely through MCP (Claude Desktop, Cursor). The web UI was a Phase 1 validation tool — useful for proving the engine, but not the product. Removing it eliminates: the Next.js runtime dependency, the localhost:3000 requirement for syncs, duplicated retrieval logic (lib/ vs MCP server), and ~246 npm packages. The codebase drops from ~50 code files to ~36 focused files.

**Tradeoff:** Loses the web chat demo and graph visualization UI. These were developer tools, not user-facing product. If a web surface is needed later, it can be rebuilt as a standalone app that queries via MCP or direct Supabase calls.

**Revisit if:** A web-based demo becomes necessary for beta onboarding or investor demos.

---

## ARCH-019: Graphiti + Neo4j as Sole L3 Backend
**Date:** 2026-04-10
**Source:** Architectural pivot after Graphiti import of 6,990 entities from 1,102 Apple Notes
**Decision:** Graphiti (graphiti-core) + Neo4j 5.26 is the sole L3 knowledge graph backend. Supabase Postgres + pgvector and local SQLite + sqlite-vec are retired from main. All L3 reads and writes go through the Graphiti FastAPI sidecar or graphiti-core in-process.
**Why:** Graphiti provides entity resolution (4-tier: exact → fuzzy → BM25 → LLM), bitemporal edges (valid_at/invalid_at), community detection, and episode-based ingestion — capabilities that took months to partially implement in the SQLite/Supabase eras and still produced only 18.5% state classification accuracy. Graphiti gives these as primitives. The 6,990-entity graph imported via Graphiti is richer and more structurally connected than the SQLite graph ever was.
**Supersedes:** D-005 (Supabase pgvector for storage), ARCH-001 (Supabase only), ARCH-018 (stay on Supabase).
**Rejected:** Keeping SQLite as a parallel local-data option on main (creates dual-backend maintenance burden; the local option is preserved on legacy/sqlite-local branch for future revival if needed). Keeping Supabase as a fallback (no code on main should reference SUPABASE_URL).
**Revisit if:** Graphiti is abandoned by Zep, or a local-first requirement makes Neo4j Docker untenable for distribution. In that case, revive from legacy/sqlite-local.

---

## ARCH-020: Ingestion Targets Graphiti Directly
**Date:** 2026-04-11
**Source:** Cleanup analysis (docs/CURRENT_STACK.md) revealed the ingestion pipeline was Supabase-only
**Decision:** All new data enters the knowledge graph via Graphiti's `add_episode()` API, either through the sidecar's `/episode` HTTP endpoint or graphiti-core in-process. No intermediate storage layer (no SQLite sources table, no Supabase sources table). The TypeScript source connectors (sources/apple-notes/sync.js, sources/gmail/sync.js, etc.) are retired. Ingestion into Graphiti currently happens via manual Python scripts in infra/graphiti/scripts/; automated ingestion will be built on the feat/ingestion-automation branch.
**Why:** The old ingestion path wrote to Supabase exclusively (ingest-direct.ts threw if SUPABASE_URL was unset), then a separate extraction pass wrote nodes/edges, then a separate segmentation pass wrote segments. Three stages, two backends, no atomicity. Graphiti's add_episode() does extraction, entity resolution, and edge creation in one atomic call. One write replaces three.
**Supersedes:** D-020 (MCP as integration layer for source connectors), D-029 (direct SQLite for iMessage).
**Rejected:** Porting the TypeScript source connectors to call Graphiti's sidecar (the connectors are JavaScript/TypeScript, the sidecar is Python — cross-language complexity for no benefit when Python scripts do the same job).
**Revisit if:** An automated ingestion daemon is needed that watches for new Apple Notes/Gmail/iMessage in real-time. That's the feat/ingestion-automation branch, not a relitigation of the backend choice.

---

## ARCH-021: No Dual-Backend Abstraction Layer
**Date:** 2026-04-11
**Source:** L3Backend interface discussion during the refactor planning
**Decision:** There is no TypeScript "L3Backend" interface or abstraction layer. Product code calls the Graphiti sidecar's HTTP API directly (or graphiti-core in-process for the Python MCP server). If a local-data option is ever needed, it lives on a separate branch — not behind an abstraction on main.
**Why:** The L3Backend abstraction was proposed as a way to support both SQLite and Graphiti from the same MCP server. But dual-backend abstractions are maintenance liabilities: they force the lowest common denominator, they double the test surface, and they prevent using backend-specific features (like Graphiti's community detection or Neo4j's Cypher traversals). MIKAI's competitive advantage comes from deep integration with Graphiti, not from backend portability.
**Rejected:** Writing lib/l3-backend.ts + lib/l3-backend-graphiti.ts as an interface/implementation pair (proposed and then abandoned during the refactor planning session). Keeping SQLite as a fallback behind the interface (same maintenance burden as dual-backend).
**Revisit if:** A second backend becomes genuinely necessary (e.g., a mobile-local deployment where Neo4j can't run). Even then, prefer a separate branch or separate product over an abstraction layer.

---

## D-040: Python MCP Server Replaces TypeScript
**Date:** 2026-04-11
**Source:** Socratic analysis of the old MCP tool set vs Graphiti capabilities
**Decision:** The MCP server for Claude Desktop is rebuilt in Python, co-located with the Graphiti sidecar at infra/graphiti/sidecar/mcp_server.py. TypeScript is no longer used anywhere in the MIKAI codebase on main. The MCP server initializes graphiti-core in-process (no HTTP hop to the sidecar for L3 calls).
**Why:** With all L3 logic in Python (graphiti-core, the sidecar endpoints, the import scripts), a TypeScript MCP server would be a thin HTTP forwarder adding latency and a second language runtime for no benefit. Python MCP (via the mcp>=1.0 SDK) supports stdio transport for Claude Desktop. One language, one process, direct graph access.
**Supersedes:** D-039 partially (MCP is still the sole product surface, but the implementation language changed from TypeScript to Python).
**Rejected:** Keeping TypeScript for the MCP server (adds cross-language boundary, HTTP hop, npm dependency chain — all for a thin forwarding layer).
**Revisit if:** The Python MCP SDK proves too limited for a feature Claude Desktop needs, or if a TypeScript-based MCP surface is required for a different client (e.g., Cursor, VS Code extension).

---

## D-041: L4 Is Product Layer, L3 Sidecar Is Pure Graph Primitives
**Date:** 2026-04-11
**Source:** Socratic analysis of old MCP tools — which are L3 (graph queries) vs L4 (derived state)
**Decision:** The Graphiti sidecar exposes only generic graph primitives: search, node fetch, BFS expand, edges-between, history, stats, episode write, communities. It does NOT implement tension detection, thread detection, state classification, stalled-project surfacing, next-step inference, or context briefs. Those are L4 concerns that belong in a separate L4 engine, to be designed and built on a dedicated branch (feat/l4-engine) after the product semantics are settled.
**Why:** The old MCP server blurred L3 and L4 because both lived in the same file reading the same SQLite tables. Graphiti forces the separation visible: the five "noonchi" tools (get_tensions, get_threads, get_thread_detail, get_next_steps, get_brief) asked questions the graph can't answer natively — they require a state model, a temporal decay concept, and LLM reasoning layered ON TOP of graph data. Mixing these into the sidecar would couple the L4 design to the L3 API, making both harder to evolve independently.
**Rejected:** Building tension/thread detection as sidecar endpoints (leaks L4 semantics into L3). Building all tools before shipping any (delays the V1 wedge — "Graphiti-backed memory for Claude" ships with 4 L3 tools while L4 is designed separately).
**Revisit if:** A specific L4 operation turns out to be a pure graph query after all (e.g., "tensions" can be defined as "communities with high internal contradiction-edge density" without any state machine). In that case, promote it to a sidecar endpoint.

---

## D-042: Graphiti Dependency Management — Patch Script, Not Fork
**Date:** 2026-04-11
**Source:** Best practices review of graphiti-core (docs/GRAPHITI_BEST_PRACTICES_REVIEW.md)
**Decision:** Maintain graphiti-core as a pip dependency with a reproducible patch script (scripts/apply_graphiti_patch.py) rather than forking. The patch fixes the context-window overflow in node_operations.py (candidate cap at 50, attribute stripping). Submit an upstream PR for a configurable max_resolution_candidates parameter. Fork only if the trigger conditions are met.
**Why:** Forking creates an ongoing merge burden — every graphiti-core release must be manually merged into the fork. With one patched file and a reproducible script, the maintenance cost is near zero. The patch is well-documented (docs/GRAPHITI_INTEGRATION.md) and the upstream PR is drafted (docs/UPSTREAM_PR_DRAFT.md).
**Fork trigger conditions:**
- Need to change Graphiti's Neo4j schema (node labels, edge properties)
- Need to modify the entity resolution algorithm beyond the candidate cap
- Have patched 3+ files in graphiti-core
- Upstream PR rejected or unresponsive for 30+ days
- A graphiti-core upgrade breaks the patch AND contains needed features
**Revisit if:** Any fork trigger condition is met.

---

## ARCH-023: Hybrid Ingestion Architecture (Pattern 2 + Pattern 3)
**Date:** 2026-04-13
**Source:** Analysis of 12 commercial products with automated personal data ingestion (Glean, Dust.tt, Limitless, Granola, Readwise, Microsoft Copilot, Apple Intelligence, Google Gemini, Recall.ai, Reflect, Capacities, Khoj)
**Decision:** MIKAI's ingestion daemon uses a hybrid of two patterns, converging on a single write path (`graphiti.add_episode()`):

**Mode 1 — Filesystem watchers (Pattern 3: OS-level capture).** For local sources that have no API and never will. The Python `watchdog` library wraps macOS FSEvents to detect filesystem changes in real time. Sources: Apple Notes (`~/Library/Group Containers/group.com.apple.notes/`), Claude Code sessions (`~/.claude/projects/`), local files. This is where the highest-signal personal data lives — private notes, AI conversations, research threads.

**Mode 2 — MCP client polling (Pattern 2: API/event-driven, standardized).** For cloud sources that expose MCP servers. MIKAI connects as an MCP client, calls the source's list/search tools on a schedule (e.g., every 30 minutes), and feeds results into Graphiti. Sources: Gmail (MCP server exists), Google Calendar (MCP server exists), Google Drive (MCP server exists). Zero custom API code per source — one MCP client works with any MCP server. MIKAI becomes both an MCP server (exposing tools to Claude Desktop) and an MCP client (consuming tools from cloud sources).

**Mode 3 — Drop folder (manual fallback).** For sources with no MCP server and no accessible filesystem location. User drops JSON or markdown exports into `~/.mikai/imports/`. The file watcher picks them up and ingests them. Sources: Perplexity threads, Claude.ai web conversation exports, any ad-hoc content.

**Why hybrid:** The most personal sources (Apple Notes, iMessage, Claude Code) will never have MCP servers — Apple has no incentive to expose user data to third-party AI systems, and Claude Code writes JSONL to disk directly. Pattern 3 is the only way to access them. Cloud sources (Gmail, Calendar, Drive) already have MCP servers, so Pattern 2 avoids building custom API connectors. The drop folder catches everything else.

**Build phases:**
- Phase 1 (`feat/ingestion-automation`): Mode 1 (Apple Notes + Claude Code filesystem watchers) + Mode 3 (drop folder). Ships a working daemon.
- Phase 2 (`feat/ingestion-mcp-client`): Mode 2 (MCP client for Gmail, Calendar, Drive). The daemon becomes an MCP client alongside filesystem watchers.

**Supersedes:** The old TypeScript source connectors (`sources/apple-notes/sync.js`, `sources/gmail/sync.js`, etc.) and the old `engine/scheduler/daily-sync.sh` pipeline, both of which wrote to Supabase. All retired in the 2026-04-11 cleanup.

**Rejected:**
- Pure Pattern 2 / API-only (cannot access Apple Notes, iMessage, Claude Code — the highest-signal sources have no APIs)
- Pure Pattern 3 / OS-level only (cannot access cloud-only services like Gmail, Google Drive without local sync clients)
- Message queue architecture like Temporal (overkill for single-user scale — checkpoint files per source provide the same resume-on-failure guarantee)
- Building custom API connectors per cloud source (MCP standardizes this; custom connectors are maintenance burden that MCP eliminates)

**Revisit if:** MCP adds a push/subscription mechanism (webhooks, event streams) that replaces polling for Mode 2. Or if Apple opens an App Intents API for Notes content that makes Mode 1 unnecessary for that source.
