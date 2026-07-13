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

## D-034: Solo-First MCP Validation — Brian on Desktop, Mobile, and Browser
**Date:** 2026-04-17 (revised from 2026-03)
**Source:** Revised during the mcp-layer branch kickoff
**Decision:** Validate the MCP layer with Brian as the only user before recruiting any beta cohort. The L3 graph must be reachable from all three Claude surfaces Brian uses day-to-day: Claude Desktop (stdio MCP), Claude mobile (remote MCP), and the Claude.ai browser web app (remote MCP). No non-Brian onboarding pipeline, no private beta recruitment, no public beta on this branch.
**Why:** Generalization risk is downstream of surface coverage. If the graph is only queryable from Desktop, the product fails the "always available" criterion that makes a memory layer useful in the first place — Brian's actual usage is split across desktop, phone, and browser. Solo validation across all three surfaces exercises the transport modes (stdio vs remote MCP), auth, and latency envelopes before any other user is subjected to them. Extraction-quality-on-non-Brian-content is a later-stage question; it's not worth de-risking until the surfaces themselves are proven on a single corpus.
**Rejected:** 5-user beta before surface coverage is complete (previous D-034 stance — premature, optimizes for generalization before basic availability). Desktop-only solo use (doesn't cover Brian's real usage pattern). Building mobile/browser surfaces after a beta launch (would force a breaking change on early users).
**Revisit if:** All three surfaces are working reliably for Brian and the next blocker becomes "is this useful for anyone else," at which point reopen beta recruitment as a separate decision.

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
**Why:** Forking creates an ongoing merge burden — every graphiti-core release must be manually merged into the fork. With one patched file and a reproducible script, the maintenance cost is near zero. The patch is well-documented (docs/ARCHITECTURE.md; raw research in docs/research/graphiti-review.md) and an upstream PR draft exists on the `feat/ingestion-automation` branch.
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

---

## ARCH-024: L3Backend Port Introduced (Ports & Adapters)
**Date:** 2026-04-16
**Source:** Design review of the local-vs-sidecar tension that had been implicit since ARCH-019 but never formally decided
**Decision:** Introduce an `L3Backend` port (a.k.a. interface) that product code — the MCP server, the L4 engine, the ingestion daemon — depends on exclusively. Two adapters implement the port:

- `GraphitiAdapter` — the current production backend. Calls graphiti-core in-process (from the Python MCP server) or the FastAPI sidecar at `http://localhost:8100` (from other clients). Neo4j + DeepSeek V3 + Voyage AI.
- `LocalAdapter` — a first-class alternate (see ARCH-025). Fully on-device: embedded graph store, local embeddings, local LLM. Not yet built; design input is `legacy/sqlite-local`.

A composition root (one file, typically `main.py` / `server.ts` depending on the surface) reads `L3_BACKEND=graphiti|local` from the environment and instantiates the chosen adapter. Product code never sees which adapter is running.

**Port surface (domain verbs only, no infrastructure nouns):**
- `ingestEpisode(content: Episode) -> IngestResult`
- `search(query: SearchQuery) -> SearchResult[]`
- `getNode(id: NodeId) -> Node`
- `expand(seed: NodeId[], hops: int, limit: int) -> Subgraph`
- `edgesBetween(a: NodeId, b: NodeId) -> Edge[]`
- `history(id: NodeId) -> HistoryEntry[]`
- `stats() -> GraphStats`
- `communities() -> Community[]`

These mirror the primitives ARCH-023 and D-041 already settled at the sidecar level. They speak in domain terms ("episode," "node," "subgraph"), not in Graphiti, Neo4j, or SQLite terms.

**Why now:** Three forces converged. (1) The docs-folder audit in the 2026-04-16 refactor surfaced that no formal decision had been recorded rejecting local-first — ARCH-019 adopted Graphiti by momentum, not by an explicit close on the alternative. (2) A "flip a switch" requirement for privacy-sensitive deployments (see ARCH-025) requires both backends to coexist at runtime, which is the definition of Ports & Adapters. (3) Building L4 directly against Graphiti's raw API would re-couple the product to an adapter and make the future local-first mode impossible to ship without rewriting L4.

The port extraction is structural debt paid now rather than later. Every product feature built before the port landed would have to be re-wired after — cheaper to do it first.

**Supersedes:** ARCH-021 (no dual-backend abstraction layer). ARCH-021 was correct for its context — it blocked SQLite re-entanglement during the Graphiti migration. That risk no longer applies: `LocalAdapter` is a clean, first-class build, not a legacy revival. The concern ARCH-021 raised (maintenance liability of a dual-backend interface) is mitigated by keeping the port surface small and strictly in domain terms.

**Rejected:**
- Keeping the status quo where product code calls graphiti-core / sidecar directly. Works today but makes ARCH-025 (local-first adapter) impossible without a major rewrite.
- Exposing Graphiti-specific types in the port (e.g., `runCypher(query: str)`, `getSidecarHealth()`). Defeats the abstraction. If a feature requires adapter-specific access, it belongs in the adapter, and the port needs a more abstract verb.
- A generic database abstraction (`L3Store` with CRUD primitives). The port models a knowledge-graph domain, not a key-value store; it must speak in graph verbs, not storage verbs.

**Phased rollout:**
1. Extract port + migrate the current Python MCP server to depend on it (still only `GraphitiAdapter` exists).
2. Verify the port is clean by instantiating `GraphitiAdapter` twice under different names — catches cases where product code leaked adapter-specific assumptions.
3. Build `LocalAdapter` per ARCH-025 as a new file implementing the existing port. The merge is additive, not invasive.

**Revisit if:** Port surface grows past ~15 methods — likely a sign of leak from adapter-specific needs into product code. Or if a second adapter is never built within a reasonable window (~6 months) — in which case the abstraction is unused and could be collapsed back into direct calls.

---

## ARCH-025: Local-First Preserved as First-Class Adapter
**Date:** 2026-04-16
**Source:** Explicit close on the local-first-vs-sidecar tension that had been unresolved since ARCH-019
**Decision:** A fully on-device "Granola-style" deployment of MIKAI is preserved as a first-class adapter behind the `L3Backend` port (ARCH-024). This is not a legacy revival, not a future migration, not a fork. It is a supported runtime mode, selectable via `L3_BACKEND=local`, with no product-code changes required to switch.

**What "local" means here:**
- Embedded graph store (likely SQLite + `sqlite-vec`, informed by `legacy/sqlite-local`)
- Local embeddings (Nomic via ONNX or equivalent on-device model)
- Local LLM for extraction (on-device model; specific choice deferred until adapter implementation)
- Filesystem watchers remain the ingestion primitive — unchanged from ARCH-023
- Zero external service dependency: no Docker, no Neo4j, no remote API calls

**Why preserve this as first-class rather than shelve it:**
- **Privacy posture.** The Graphiti adapter sends episode content to DeepSeek V3 and Voyage AI on every ingest. Some users (and Brian's own research workflows with sensitive content) may require that nothing leaves the device.
- **Distribution model.** "Download MIKAI, it runs entirely on your laptop" is a materially different product than "install Docker, run Neo4j, configure a sidecar." Some personas reject the latter.
- **Latency.** Sub-millisecond local reads vs ~500ms HTTP + Neo4j round-trip. Matters for L4's proactive surfacing.
- **Cost posture.** The cloud-adapter path is ~$0.005–$0.01 per episode in API spend at current rates. Local is zero marginal cost after model download. At ingestion rates >100 episodes/day this compounds.
- **Architectural symmetry.** Having two adapters forces the port surface to stay honest — any leak of Graphiti-specific assumption breaks the local path and gets caught immediately.

**What this decision is *not*:**
- Not a commitment to ship `LocalAdapter` on any particular date. The sequencing is: (a) ARCH-024 port extraction, (b) `GraphitiAdapter` stabilization behind the port, (c) `LocalAdapter` implementation as bandwidth allows.
- Not a reversal of ARCH-019. Graphiti remains the default adapter. `L3_BACKEND=graphiti` is the unset-default path.
- Not a merge from `legacy/sqlite-local`. That branch is a design reference; `LocalAdapter` is a clean implementation against the ARCH-024 port.

**Tradeoffs accepted:**
- **Model quality gap.** DeepSeek V3 is stronger at entity resolution than current on-device LLMs. `LocalAdapter` will produce lower-quality extraction until on-device models close the gap. This is acceptable; users selecting the local mode are trading quality for privacy/control.
- **Feature gap.** Graphiti-specific features (community detection, bitemporal edges with native support) may ship on `GraphitiAdapter` first and on `LocalAdapter` later or never. The port surface should not stall waiting for `LocalAdapter` to catch up.

**Relation to `legacy/sqlite-local`:** The `legacy/sqlite-local` branch is reclassified from "archival only" to "design input." Code from it may be studied, extracted, and adapted into `LocalAdapter`, but the branch itself is never merged into main.

**Supersedes:** None directly. Clarifies ARCH-019 (which was read as "Graphiti only" but was more accurately "Graphiti is the current backend"). Reframes `legacy/sqlite-local` from "archival only" to "design input."

**Rejected:**
- Shelving local-first entirely. Loses the privacy posture and the architectural discipline the two-adapter model enforces.
- Building `LocalAdapter` on a long-lived branch. Defers integration pain and makes the "flip a switch" story impossible. `LocalAdapter` lands on main as a file, not as a branch merge.
- Positioning the local mode as "legacy." It is a forward-looking, first-class mode — just one that ships later than the default.

**Revisit if:** On-device LLMs close the quality gap such that `LocalAdapter` becomes strictly equal-or-better than `GraphitiAdapter` — at that point the default might flip, and `GraphitiAdapter` becomes the alternate. Or if zero users ever select `L3_BACKEND=local` and the adapter has been live for ~6 months — in which case the privacy/distribution hypothesis was wrong and the adapter can be removed to simplify the port.

---

## D-043: MCP Transport — Mounted Inside the Sidecar, Streamable HTTP Only
**Date:** 2026-04-17
**Source:** mcp-layer branch — surface-coverage refactor driven by the revised D-034
**Decision:** The MCP server for Claude Desktop, mobile, and browser is mounted at `/mcp` inside the existing Graphiti sidecar FastAPI app using FastMCP's `streamable_http_app()`. One process, one Graphiti singleton, one public URL. Transport is Streamable HTTP only — no stdio code path in MIKAI. Claude Desktop reaches it via the `npx mcp-remote http://localhost:8100/mcp` shim, which handles the stdio↔HTTP bridge without any MIKAI-side stdio implementation.
**Why:** The revised D-034 requires all three Claude surfaces (Desktop + mobile + browser) reach the same L3 graph. Mobile and browser require remote MCP over Streamable HTTP; Desktop can reach remote MCP via the community-maintained `mcp-remote` shim. Standing up stdio *and* HTTP code paths inside MIKAI would double the transport surface, duplicate the Graphiti init, and drift over time — all to avoid a one-line `mcp-remote` invocation on the client side. Mounting inside the sidecar (rather than a separate daemon) collapses the Graphiti singleton, the patched graphiti-core, and the public URL into one process, which simplifies Cloudflare Tunnel exposure and removes the 520-line duplicated `mcp_server.py`.
**What changed on this branch:**
- Added `sidecar/mcp_tools.py` exporting `build_mcp(get_graphiti)` → FastMCP with the 4 L3 tools.
- `sidecar/main.py` constructs the FastMCP instance, nests `mcp.session_manager.run()` inside the Graphiti lifespan, and mounts the ASGI app at `/mcp`.
- Deleted `sidecar/mcp_server.py` (the stdio-only standalone server) and its duplicated `DeepSeekClient` / `PassthroughReranker` / `init_graphiti` code.
- Updated `infra/graphiti/AGENTS.md` with the new architecture diagram, the `/mcp` endpoint row, and the Claude Desktop `mcp-remote` config snippet.
**Rejected:**
- Dual-transport single codebase with a `--transport {stdio,http}` CLI flag (Pattern A). Two deployment processes, two Graphiti inits, double the surface for no gain when `mcp-remote` already bridges Desktop.
- Full migration from raw `mcp.server.Server` to FastMCP across the whole stack (Pattern B). We did migrate the 4 tools to FastMCP because ASGI mount requires it, but this is a local change, not a project-wide SDK swap.
- Two literal scripts sharing Neo4j (Pattern C). Guaranteed to drift; every new tool would be written twice.
- Standalone long-running HTTP MCP daemon separate from the sidecar. Would duplicate Graphiti init and require a second Cloudflare Tunnel entry.
**Supersedes:** D-040's implementation detail that MCP runs as a standalone stdio process. The MCP-is-Python, MCP-uses-graphiti-in-process, MCP-is-the-sole-product-surface parts of D-040 all stand; only the *transport* and *process boundary* have changed.
**Revisit if:**
- A Claude client drops Streamable HTTP support (would force re-adding stdio).
- `mcp-remote` becomes unmaintained or unreliable (alternate Desktop path would be needed).
- The sidecar grows tools that cannot safely share a process with the REST ingestion endpoints (then split into two processes behind the same tunnel, not two codebases).
- A second user joins (triggers OAuth work per D-034; separate decision).

---

## D-044: Claude-Client MCP Compatibility Findings
**Date:** 2026-04-18
**Source:** mcp-layer branch — live integration debugging against Claude Desktop, Claude.ai web, and Claude mobile during the MCP output layer rollout
**Decision:** MIKAI's `/mcp` endpoint must accommodate three client-side protocol quirks discovered while wiring Pattern D to Claude.ai's hosted Custom Connector. Fixes landed in `infra/graphiti/sidecar/main.py` and `infra/graphiti/sidecar/mcp_tools.py`; record here so the pattern isn't re-discovered.

**Findings:**

1. **`/mcp` (no trailing slash) cannot 307-redirect.** Starlette's default `Mount` class redirects `/mcp` → `/mcp/` with HTTP 307 for trailing-slash consistency. Claude.ai's hosted MCP client does not follow that redirect on POST — the JSON-RPC body is lost and the handshake fails. Fix: an ASGI middleware (`MCPTrailingSlashMiddleware`) that rewrites `scope["path"]` from `/mcp` to `/mcp/` before routing. No redirect issued.

2. **`TransportSecuritySettings` rejects unfamiliar Host headers.** The MCP Python SDK's `StreamableHTTPSessionManager` ships with DNS rebinding protection on by default, which rejects any `Host` header not in its allow-list. When Claude.ai connects via a tunnel (Tailscale Funnel, Cloudflare Tunnel, etc.), the inbound `Host` is the tunnel's public hostname — not knowable at build time. Result: every request 421 Misdirected Request. Fix: `TransportSecuritySettings(enable_dns_rebinding_protection=False)` on the FastMCP instance. Authentication becomes the real security boundary.

3. **Claude.ai's first probe uses `Accept: application/json` without `text/event-stream`.** Streamable HTTP requires both. The probe returns 406 Not Acceptable, Claude.ai falls back to probing OAuth discovery endpoints (`.well-known/oauth-authorization-server`, `.well-known/oauth-protected-resource`, `/register`), all 404 on a bearer-only server, then retries with the proper Accept header and succeeds. The 406 is non-blocking but produces spurious "Couldn't reach the MCP server" UI errors on the Claude.ai connector page even when the connector works in-chat. Not fixed in code — Claude.ai's retry recovers. Recorded so the cosmetic error isn't mistaken for a real failure.

4. **Claude.ai's Custom Connector form does not expose a bearer-token field.** Only Name, URL, OAuth Client ID, OAuth Client Secret. Static bearer tokens are fine for Claude Desktop (via `mcp-remote`) but not reachable from Claude.ai web or Claude mobile. The supported auth path for those surfaces is **OAuth 2.0 + Dynamic Client Registration** — the server must expose `/.well-known/oauth-authorization-server` and `/register` endpoints, and Claude.ai will auto-register as a client. Until OAuth is implemented on the sidecar, `auth_required: false` is the operational compromise for mobile/browser access.

**Why:** All four findings are client-side behaviors of Claude's hosted MCP infrastructure, not things MIKAI gets to vote on. A correctly-implemented MCP server must tolerate them. Documenting them here prevents re-debugging.

**Rejected:** Emitting HTTP 308 instead of 307 (clients still don't follow). Adding an allow-list of tunnel hostnames to TransportSecuritySettings (fragile — hostname changes per deployment). Implementing a pre-flight `Accept` header rewrite (too invasive; Claude.ai's retry already recovers).

**Revisit if:**
- Claude.ai begins exposing a bearer-token field on the Custom Connector form (would let us re-enable bearer auth without OAuth).
- The MCP Streamable HTTP spec adds a canonical "allow any Host" setting that doesn't require disabling DNS rebinding protection entirely.
- Claude.ai stops probing OAuth endpoints on unauthenticated servers (would remove the cosmetic 406 → 404 → retry sequence).

---

## D-045: `search` Returns Edges, Not Prose — `get_source` Tool Gap
**Date:** 2026-04-18
**Source:** Live comparison between Claude.ai's built-in memory and MIKAI's `search` tool, same query (Sucafina/Martin). Claude's memory gave a multi-paragraph narrative from the original conversation; MIKAI returned compressed bullet-point facts.
**Decision:** MIKAI ships with an L3 tool gap: `search` returns edges — LLM-summarized one-line facts like "Sucafina is headquartered in Geneva" — never the source episode prose that grounds those edges. For "what have I written about X" queries (the most intuitive user request), this makes MIKAI retrieve thinner content than Claude's own session memory, inverting the manifesto's core promise. Add a new L3 tool `get_source(query, num_results)` that returns the raw episode content alongside edges, so Claude can choose edges vs. prose based on the question.

**Why:** The manifesto claimed "memory is what you said, intent intelligence is what you meant." The current MIKAI returns only *what you meant* (the extracted claim) and discards *what you said* (the prose that earned the claim). Both are useful — for "give me facts" → edges; for "give me context" → prose. The existing tool shape forces every query through the compression layer, losing the richness users expect from a memory product.

**What shipped:** `get_source(query, num_results=5)` added to `infra/graphiti/sidecar/mcp_tools.py`. Uses Neo4j's existing `episode_content` fulltext index (created by Graphiti's `build_indices_and_constraints()`) to rank Episodic nodes by relevance to the query, then returns the raw `content` string for each — formatted as markdown with source label and reference time. Falls back from phrase-match → quoted-phrase → OR-split when the first query form produces zero results. Live-validated: `get_source("Sucafina")` returns Brian's original conversation turns verbatim, matching the content Claude.ai's built-in memory had been surfacing.

**Rejected:**
- Modifying `search` to dump episode content alongside edges by default (makes every response token-expensive; Claude should choose based on intent).
- Returning raw Graphiti internal fields (leaks implementation detail to MCP clients).

**Revisit if:** The new tool lands in `feat/l4-engine` or a dedicated branch (scope: fetch top-K episodes for a query, format as markdown with source labels and timestamps). After the tool ships, re-run the eval suite — questions A1, C1, C2 in `scripts/eval_mikai.py` should show improved MIKAI responses relative to a Claude-with-memory baseline.

---

## D-046: Solo-User Eval Harness — Semi-Manual Until API Credits Available
**Date:** 2026-04-18
**Source:** Attempt to build a fully automated A/B eval (MIKAI arm via Anthropic API with MCP connector; baseline arm via Claude.ai manual copy-paste).
**Decision:** The eval harness (`scripts/eval_mikai.py`) is semi-manual: automates the MIKAI arm via the Anthropic Messages API with `mcp_servers` parameter, but requires the user to manually paste the Claude.ai-with-memory baseline responses. Fully automated reproduction of Claude.ai's built-in memory is not possible without either browser automation (Playwright driving a logged-in Claude.ai session) or API credits to substitute for a synthetic memory layer.
**Why:** Claude.ai's consumer memory feature is not exposed via the Anthropic developer API. Automating the baseline arm requires either scraping Claude.ai (fragile, ToS gray area) or approximating the memory with a retrieval layer over exported conversations (valid but not the same benchmark). For a solo-user eval, 30 seconds of copy-paste per question is cheaper than building either alternative.
**Rejected:**
- Full Playwright harness (1-2 hours to build, fragile against Claude.ai UI changes).
- Synthetic memory via Claude.ai conversation export + embedding retrieval (changes the baseline from "Claude with real memory" to "Claude with my retrieval hack" — undermines the comparison).
- Fully manual eval (no automation at all). Rejected because the MIKAI arm benefits from being automatable, even if the baseline isn't.
**Open constraint:** Max subscription does NOT include Anthropic API credits — the two wallets are separate. Current `~/.mikai/config.json` Anthropic key is exhausted. Path forward: either (a) top up ~$5 of API credit and run `scripts/eval_mikai.py` directly, or (b) register MIKAI as a Claude Code MCP server (`claude mcp add`) and spawn agents that use the user's Max quota instead. Option (b) requires a Claude Code session restart to pick up the new MCP registration.
**Revisit if:** Anthropic adds API credits to Max tier, or exposes Claude.ai's consumer memory via the API. Either would simplify the harness substantially.

---

## D-047: Three-Module Split for the Graphiti Sidecar Package
**Date:** 2026-04-20
**Source:** Retroactive formalization of commit `4f65b80` (2026-04-16), surfaced during the `feat/ingestion-mcp-client` ↔ `main` merge reconciliation on 2026-04-20. The refactor had been executed pragmatically but never captured as a decision, which allowed main's parallel `mcp-layer` work to drift back toward the pre-refactor single-file structure.
**Decision:** The `infra/graphiti/sidecar/` package is split into single-responsibility modules along domain boundaries:

- `sidecar/client.py` — All Graphiti/DeepSeek/Voyage wiring. `DeepSeekClient`, `PassthroughReranker`, `init_graphiti()`, `build_graphiti()`, `run_cypher()`, ISO-format helpers. Consumers: `sidecar/main.py`, `sidecar/mcp_server.py`, `sidecar/mcp_tools.py`, `mcp_ingest.py`, and every `scripts/import_*.py`.
- `sidecar/ingest.py` — Pure-Python parsers and state helpers. `parse_notes_dump`, `parse_osascript_notes_output`, `parse_claude_turns`, `parse_perplexity_query_and_answer`, `load_state`, `save_state`, `interpolate_tool_args`, `is_sensitive_name`. Zero external dependencies by design, which is what makes the 64+8 tests run in under two seconds.
- `sidecar/main.py` — FastAPI REST surface and the `/mcp` HTTP mount. No duplicated Graphiti wiring.
- `sidecar/mcp_server.py` — MCP stdio transport (Claude Desktop). Imports tool-related helpers from `sidecar/client.py`.
- `sidecar/mcp_tools.py` — MCP streamable-HTTP transport via FastMCP (Claude.ai, mobile, browser). Imports the same helpers.

Consumers depend on `sidecar.client` and `sidecar.ingest` by name. They do not re-implement Graphiti wiring or parsers locally.

**Why:**
1. **Duplication elimination.** Before `4f65b80`, `DeepSeekClient`, `init_graphiti()`, and the parsers existed verbatim in `sidecar/main.py`, the prior `mcp_server.py` (née `mcp_tools.py`), and each `scripts/import_*.py`. Every DeepSeek JSON-schema fix had to land in 3+ places; misses produced "works here but not there" bugs. The split collapses that to one copy per concern.
2. **Testability.** Pre-split parsers were embedded next to FastAPI handlers and required spinning the whole sidecar to exercise. Extracting them into `sidecar/ingest.py` — a module with zero external dependencies — is what makes the current `pytest` suite (72 tests, ~1.7s) possible. This is the Humble Object pattern: push I/O to the edge, test orchestration against pure modules.
3. **Port discipline (ARCH-024).** The `L3Backend` port requires that product code depend on a named interface, not on Graphiti. Having Graphiti wiring in one module (`sidecar/client.py`) makes the adapter boundary one-module-wide — future `LocalAdapter` implementation changes exactly one file's imports.

**Rejected:**
- Flat single-module sidecar (pre-`4f65b80` shape). Undoes the refactor; reinstates the duplication that motivated it; breaks the test suite's <2s performance; widens the `L3Backend` port boundary to N files.
- Merging `mcp_server.py` and `mcp_tools.py` into one "MCP module" that handles both stdio and HTTP via a single class. Possible but premature — the two transport APIs (`mcp.server.Server` vs `mcp.server.fastmcp.FastMCP`) have meaningfully different shapes, and unifying them prematurely would force a lowest-common-denominator wrapper. See follow-up below.

**Open follow-up (tool-logic duplication between transports):** `sidecar/mcp_server.py` (stdio) and `sidecar/mcp_tools.py` (HTTP FastMCP) both implement the same five MCP tools (`search`, `get_history`, `add_note`, `get_stats`, `get_source`) via transport-specific APIs. The tool *logic* is duplicated across the two files even after this split. A further refactor should extract the five tool implementations into `sidecar/tool_handlers.py` and have both transport surfaces wrap the shared handlers. Deferred until both transports are proven in production — if Claude Desktop fully adopts streamable HTTP, `mcp_server.py` may be retired entirely, in which case the duplication resolves itself.

**Revisit if:**
- The `sidecar.client` module grows past ~300 lines — likely a sign it's accumulating concerns that deserve their own module.
- A third MCP transport arrives before the tool-logic duplication is resolved — at three transports the shared-handler refactor becomes urgent rather than deferred.
- The test suite ratio (currently 1 test per 4 lines of `ingest.py` + `client.py`) drops materially, which would signal the split is no longer buying testability.

---

## D-048: Bundled OAuth 2.1 Authorization Server for the Claude.ai / Mobile Connector

**Date:** 2026-05-19
**Source:** Live connector debugging — adding MIKAI as a Claude.ai web Custom Connector fails with "Couldn't reach the MCP server" (`ofid_*`). Server-side verification confirmed the `/mcp` endpoint is fully MCP-spec-compliant (`initialize`, `tools/list`, `tools/call`, SSE GET, protocol `2025-06-18` all pass). The failure is isolated to OAuth discovery. Supersedes the interim compromise recorded in D-044 finding 4.

**Decision:** The Graphiti sidecar implements a minimal, single-user OAuth 2.1 Authorization Server — PKCE (S256) + Dynamic Client Registration — co-located with the MCP endpoint, and validates bearer access tokens on `/mcp`. New module `infra/graphiti/sidecar/oauth.py`, wired into `sidecar/main.py`. Activated by `MIKAI_OAUTH_ENABLED=1` and gated by a single operator password (`MIKAI_OAUTH_PASSWORD`). When disabled, the sidecar keeps its prior behavior (open, or static `MIKAI_MCP_TOKEN` bearer); no OAuth routes or token checks are active.

**Why:**
1. **The D-044 compromise has expired.** D-044 finding 4 named OAuth 2.0 + DCR as the only auth path Claude.ai web and mobile support, and recorded `auth_required: false` as an explicit interim compromise. That compromise worked only because Claude.ai then treated OAuth-discovery 404s as non-blocking (D-044 finding 3: "retries … and succeeds"). As of 2026-05, Claude.ai's connector treats failed OAuth discovery as a hard failure. An unauthenticated server is no longer reachable from web or mobile.
2. **It is also the first real access control.** The sidecar is currently exposed on a public Tailscale Funnel URL with no authentication — Brian's entire personal knowledge graph is queryable by anyone who has the URL. OAuth closes that, *provided* the `/authorize` consent step has a genuine credential gate. The operator password is therefore load-bearing, not decorative.
3. **Bundled, not external.** A self-contained AS keeps the deployment dependency-free, proportionate to a single-user product. PKCE makes the public-client flow safe without a client secret.

**Rejected:**
- **External authorization server** (Auth0/WorkOS/Stytch). Less code, but adds a managed-service account and dependency for a one-user system; off-pattern for MIKAI's self-contained ethos.
- **Static bearer token only.** Works for Claude Desktop (`mcp-remote`) and Claude Code, but Claude.ai's connector form exposes no bearer field (D-044 finding 4) — cannot reach web or mobile.
- **Auto-approving `/authorize` consent.** Satisfies the connector protocol but provides zero security: anyone could run DCR + the code flow and mint a token against a public URL.
- **Implementing via the `mcp` SDK's `mcp.server.auth` scaffolding.** The OAuth metadata documents must be served at the site root, not under the `/mcp` ASGI mount; hand-rolled FastAPI routes keep the sidecar framework-consistent and the emitted documents fully controlled.

**Revisit if:**
- Claude.ai adds a bearer-token field to the Custom Connector form — would allow static-token auth again and retire the AS.
- MIKAI gains a second user — the single shared password must then become per-user credentials, at which point an external IdP becomes the proportionate choice.
- The `LocalAdapter` (ARCH-025) ships — a fully on-device deployment has no public surface and may not need the AS at all.

---

## D-049: Source-Conditional Pydantic Extraction (No Second Pass)
**Date:** 2026-05-21
**Source:** Stage 6 brief — L3 typed extraction quality improvement (3.10 → ≥4.3)
**Decision:** Typing happens at extraction time via Graphiti's native `add_episode(entity_types=, edge_types=, edge_type_map=)` parameters. No second LLM pass (no Mem0-style ADD/UPDATE/DELETE/NOOP gate). No projection layer. No OWL ontology validator. Source-conditional Pydantic schemas define entity types per ingestion source (Claude threads, Apple Notes, Gmail, WhatsApp daily summaries). Every epistemic edge carries a `confidence: float` field reflecting the extraction model's certainty about the relationship.

**Why:** Graphiti's entity resolution + bitemporal invalidation (valid_from, expired_at) already provide dedup and contradiction handling semantically. Replicating Mem0's ADD/UPDATE/DELETE/NOOP gate adds LLM cost and latency without manufacturer-supported benefit. Pydantic validation is sufficient to enforce schema integrity — no need for a separate OWL ontology layer. Typing at extraction time means L4 can query `edges where type=UNRESOLVED_TENSION and confidence>0.6` directly, with no post-hoc projection step.

**Rejected:**
- **Mem0-style ADD/UPDATE/DELETE/NOOP second LLM pass:** Each class (ADD, UPDATE, DELETE) requires a separate LLM invocation. We achieve the same structural outcome (marked-resolved nodes, entity merging) from Graphiti's resolution + our confidence scoring on edges. The second pass is duplicative overhead.
- **Cognee OWL ontology validation layer:** OWL adds complexity for no gain over Pydantic. If a node doesn't conform to source-conditional schema, Pydantic validation fails at extraction time — manufacturers-supported, simpler, no separate validation loop.
- **Separate post-extraction projection/re-classification layer:** Constraining edges at extraction time via `edge_type_map` (declaring which edge types may connect which entity types) makes projection unnecessary. L4 gets typed signals directly.
- **Switching to GPT-4o/Sonnet for extraction LLM:** Deferred — measure first with schema + confidence scores + negative examples. If accuracy still doesn't cross 4.0, revisit LLM choice.
- **Introducing a second vector store or embedding service:** Graphiti's existing retrieval (Voyage embeddings) is the search layer; no additional embeddings infrastructure.

**Implementation scope (Stream H + supporting streams A–G):**
1. Source-conditional Pydantic schemas: `claude_thread.py`, `apple_note.py`, `gmail_message.py`, `whatsapp_day.py` (5–15 entity types each).
2. Shared epistemic edge types: `extraction/epistemic_edges.py` — CONTRADICTS, SUPPORTS, DEPENDS_ON, PARTIALLY_ANSWERS, UNRESOLVED_TENSION, EXTENDS (all carrying confidence).
3. Shared `edge_type_map` declaring valid connections (e.g., Question → PARTIALLY_ANSWERS → Decision).
4. Negative few-shot examples in extraction prompt (sourced from noise cluster: "Hearty simple creative", "folly", "The MacNabs").
5. Query-time recency-decay scoring overlay (time-decays edge scores so fresh facts outrank stale ones).
6. Eval suite: 200 labeled entities + 200 labeled edges, `eval/run_l3_eval.py` runner.

**Success metrics:**
- Entity precision ≥0.85, recall ≥0.75 (from labeled_entities.jsonl).
- Edge precision ≥0.80, recall ≥0.65 (from labeled_edges.jsonl).
- Noise rate <0.10 (extracted entities failing Pydantic validation or filtered post-hoc as garbage).
- Kenya-coffee benchmark: Claude thread → Apple Note → Gmail → WhatsApp daily summary all land typed entities and edges in Graphiti, connected through shared Person/Place/Project nodes.

**Revisit if:**
- Extraction accuracy fails to cross 4.0 after Pydantic schema + edge_type_map + prompt negatives are in place (triggers re-evaluation of LLM choice or schema design).
- L4 needs typed signals the current edge vocabulary doesn't capture (add new edge types).
- Bitemporal invalidation proves insufficient for handling contradictions (layer in explicit conflict resolution).

---

## D-050: L3Backend Port Extraction (ARCH-024 implemented)

**Date:** 2026-05-21
**Source:** Stage 7 work on `feat/stage-7-l3-port` — the implementation of the L3 port that ARCH-024 (2026-04-16) called for but didn't ship.

**Decision:** Product code — sync.py, mcp_ingest.py, mcp_tools.py (HTTP MCP), mcp_server.py (stdio MCP), main.py (REST endpoints) — depends exclusively on `sidecar.l3.L3Backend`, an ABC with 11 async primitives (`ingest_episode`, `ingest_episode_bulk`, `search`, `search_nodes`, `get_node`, `expand`, `edges_between`, `history`, `get_source`, `stats`, `communities`, `close`) and 10 plain-dataclass domain types. The port lives at `sidecar/l3/port.py`. `GraphitiAdapter` (sidecar/l3/graphiti_adapter.py) is the only current implementation; it wraps graphiti-core + Neo4j + the Stage 6 typed-extraction router. A composition root, `sidecar/l3/__init__.py::make_backend()`, reads `MIKAI_L3_BACKEND` (default `"graphiti"`; `"local"` raises NotImplementedError until ARCH-025 lands).

**Why:**
1. **ARCH-024 had to be cashed out before L4 or LocalAdapter can start.** Until product code stops calling graphiti-core directly, neither the LocalAdapter (ARCH-025) nor the L4 engine (D-041) has a stable interface to depend on. Stage 6's typed extraction sat directly on top of `graphiti.add_episode()` — a port pattern documented but never enforced.
2. **The adapter encapsulates Graphiti-specific machinery completely.** Rate limiting (DeepSeek + Voyage token buckets) and Stage 6 source-conditional extraction routing live inside `GraphitiAdapter.ingest_episode()`, not in callers. A future `LocalAdapter` makes its own choices about rate limits (none if the LLM is on-device) and extraction shape (no Pydantic kwargs to graphiti-core) without changing any product code.
3. **Dataclasses, not Pydantic, for port domain types.** Pydantic is the right tool for I/O validation at HTTP boundaries — kept in REST endpoint models (`SearchResult`, `NodeResult`). In-process port handoffs don't need validation; dataclasses are lighter, faster to construct, and don't drag a Pydantic model registry through every call site.
4. **The port's verb set is read-heavy and primitive-only.** Per D-041, no tension/thread/state-classification semantics leak in. The 11 verbs are the smallest set the current product code actually exercises.

**Rejected:**
- **Pydantic models for port types.** Costs more per-call construction and locks the port into the Pydantic dependency chain.
- **Synchronous port methods.** Every current backend's I/O is async; forcing sync would require a thread-pool wrapper inside the adapter.
- **`L3_BACKEND` env var name (per ARCH-024 prose).** Standardized on `MIKAI_L3_BACKEND` to match the `MIKAI_*` namespace.
- **Top-level `mikai/l3/` package outside `infra/graphiti/`.** A substantially larger refactor (every script and test import would change paths); deferred until LocalAdapter actually arrives.
- **Exposing `graphiti_core.EpisodeType` through the port.** `Episode.source_description` is the single source-routing field; adapters map it internally.
- **Pulling extraction-schema routing (Stage 6 D-049) up into the port.** Would require the port to carry Pydantic class refs, leaking adapter conventions. Routing stays inside `GraphitiAdapter.ingest_episode()`.

**Implementation rollout (four commits on `feat/stage-7-l3-port`):**
1. `22be46b` — port + GraphitiAdapter + factory + 14 port tests.
2. `9c67529` — sync.py + mcp_ingest.py + their tests.
3. `505acba` — mcp_tools.py + mcp_server.py + test_mcp_tools.py rewrite.
4. `4dca42e` — main.py REST endpoints; raw-Cypher helper deleted.

After this stage, `grep -r graphiti_core infra/graphiti/sidecar/` outside `l3/graphiti_adapter.py` returns zero hits. The port boundary is enforced by absence.

**Revisit if:**
- `LocalAdapter` arrives and exposes a primitive the port doesn't currently surface. Add it with a default-`NotImplementedError` for backends that don't support it.
- L4 engine work shows the port's 11 verbs are insufficient — likely candidates: temporal range queries, multi-hop traversals beyond single `expand()`, or write-side compensation. L4-driven, not speculative.
- A second non-Graphiti adapter is built (e.g. an in-memory test double promoted to first-class). At that point consider moving the port to a top-level `mikai/l3/` package outside `infra/graphiti/`.

---

## D-051: Pattern B operational target — laptop-as-home-server via LaunchAgents at `~/Library/Application Support/mikai/launchd/`

**Date:** 2026-06-04
**Source:** Pattern B bring-up session; resolves O-042 (free-tier cloud-hosted Neo4j).

**Decision:** MIKAI runs Pattern B (always-on home server) on the daily-driver MacBook. The docker-compose stack (Neo4j + sidecar at `Desktop/MIKAI/infra/graphiti/`) is auto-managed by two macOS LaunchAgents:

- `com.mikai.docker-compose` — RunAtLoad. Opens Docker Desktop if needed, waits for the daemon, runs `docker compose up -d`.
- `com.mikai.health-probe` — `StartInterval=300` plus `WakeUp=true`. Curls `localhost:8100/health`; on failure, logs locally and pushes a Telegram alert if creds are present.

Agents and scripts live at `~/Library/Application Support/mikai/launchd/` — **deliberately outside any TCC-protected directory** — and reference the deployed stack at `~/Desktop/MIKAI/infra/graphiti/`. `launchctl bootstrap gui/$UID` is the install API. Sleep prevention (`sudo pmset -c sleep 0 disksleep 0`) and Docker Desktop auto-start are documented manual one-time steps; install scripts do not run `sudo`.

**Why:**

1. **TCC blocks launchd-spawned bash from `exec`ing scripts under `~/Desktop/`, `~/Documents/`, `~/Downloads/`.** Discovered the hard way during the install on 2026-06-04: the docker-compose plist's `last exit code = 126` with stderr "Operation not permitted". The compose file itself can stay under `~/Desktop/` because *Docker Desktop* has its own TCC grants — the restriction is launchd-spawned shell, not the docker daemon. Scripts move to `~/Library/Application Support/mikai/launchd/`; compose paths stay.
2. **Pattern B with this laptop as the host is a transitional choice, not the end state.** Costs nothing, ships now. The same docker-compose runs on a future Raspberry Pi or NUC home server without architectural change — only the LaunchAgent paths shift. Migration is mechanical when laptop sleep becomes the binding constraint.
3. **`launchctl bootstrap`, not `launchctl load`.** On macOS Sonoma+, `load`/`unload` are deprecated for user agents; `bootstrap gui/$UID` is the supported path. Install also `bootout`s the prior label first → idempotent across edits.
4. **`WakeUp=true` on the health probe.** Pure interval-based probing misses the post-sleep window by up to 5 minutes; WakeUp fires the probe immediately on every wake transition. Combined with Telegram, Brian learns the stack is down within seconds of wake.
5. **Compose v2 auto-loads `.env` from the project directory regardless of the launchd shell environment.** Empirically confirmed — the stack came up with all OAuth env vars set even though `docker compose up -d` was invoked from a stripped-down launchd context. No `EnvironmentVariables` key in the plist needed, no `env_file:` stanza in compose needed.

**Rejected:**

- **`launchctl load`/`unload` (legacy API).** Still works on Sonoma but logs deprecation warnings; future-breaking.
- **`sudo` inside `install.sh`.** Blocks non-interactive installs and conflates power-management policy (which the user should consciously opt into) with agent registration. Split out as a documented manual step.
- **Scripts under the repo at `infra/launchd/`.** The repo lives under `~/Desktop/`, which is TCC-protected. The Stage 2 ingestion-daemon plist template at `infra/graphiti/launchd/` still sits there but is not the canonical install path on this machine — same fix applies when that LaunchAgent is activated.
- **`EnvironmentVariables` in the plist or `env_file:` in compose.** Compose v2's auto-discovery of `.env` in the project directory does the job; either alternative adds complexity for no behavioural change.
- **Free-tier cloud-hosted Neo4j (closes O-042).** Aura Free's ~200k-node cap leaves little headroom at MIKAI's growth rate, paid tier is ~$65/mo, and migration moves the JWT signing key + graph onto someone else's infra for no functional gain while the laptop is awake. Reopens only if laptop sleep becomes the actual binding constraint.

**Implementation:**

- `~/Library/Application Support/mikai/launchd/start-stack.sh` — `open -a Docker`, poll `docker info` for up to 5 min, then `cd Desktop/MIKAI/infra/graphiti && docker compose up -d`. `set -e` scoped after the poll so loop failures don't abort.
- `~/Library/Application Support/mikai/launchd/health-probe.sh` — `curl localhost:8100/health` with 10s timeout; on failure, append to `logs/health-probe.log` + push Telegram if `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` present in colocated `.env`.
- `~/Library/Application Support/mikai/launchd/com.mikai.{docker-compose,health-probe}.plist` — the two LaunchAgents.
- `~/Library/Application Support/mikai/launchd/install.sh` — bootout + bootstrap loop, copies plists to `~/Library/LaunchAgents/`. Idempotent.

**Revisit if:**

- Auto-ingestion needs 24/7 uptime (laptop sleep becomes binding) — migrate to a dedicated home server (Pi 5, NUC). Same docker-compose, different host. Or reopen O-042.
- Multi-device read availability when laptop is in the bag becomes a daily requirement.
- The Stage 2 ingestion daemon LaunchAgent (still TCC-blocked at `infra/graphiti/launchd/`) needs to be activated — apply the same TCC fix (move scripts to `~/Library/Application Support/mikai/launchd/`).
- Apple changes the TCC model such that `~/Library/Application Support/` becomes restricted (unlikely).

---

## D-052: Native graphiti extraction is the ingestion default; Stage 6 typed extraction disabled behind a flag

**Date:** 2026-06-09
**Source:** Ingestion-outage investigation (graph frozen at May 21). Qualifies D-049 (source-conditional typed extraction) and relates to the D-050 L3 port.

**Decision:** Ingestion uses graphiti-core's **native** extraction by default. The single chokepoint `sidecar/extraction/router.py::extraction_params_for()` returns `{}` (no custom `entity_types`/`edge_types`/`edge_type_map`/`custom_extraction_instructions`) unless `MIKAI_TYPED_EXTRACTION=1`. graphiti-core is pinned `==0.28.2`. The Stage 6 typed-extraction modules (`sidecar/extraction/*.py`) are left intact and revivable.

**Why:**

1. **graphiti-core 0.28.2 cannot persist custom type attributes to Neo4j.** It writes custom node/edge attributes as nested Neo4j `Map` values, which Neo4j rejects (`Property values can only be of primitive types`). It also newly reserves `summary` as a protected `EntityNode` field, which the Stage 6 models used pervasively. Both fire on every episode → 0 writes.
2. **An unpinned dependency caused a silent multi-week outage.** `requirements.txt` had `graphiti-core>=0.5`; a `pip install` floated it to 0.28.2 and froze ingestion at May 21 with no alert. Pinning prevents recurrence; the launchd ingestion daemon (still uninstalled) would have surfaced it sooner.
3. **The typed layer was barely realized anyway.** In the live graph the epistemic edges were 15 of 15,108 edges (~0.1%); the graph is ~99% native extraction already. Native carries only primitive fields (name/summary/fact), sidesteps the persistence bug, and matches the freeform-graph L4 direction (ARCH-019/021).
4. **Native is ~4× cheaper.** The 954-turn catch-up cost $1.30 (~$0.0014/turn) vs a $5–9 estimate for typed.

**Rejected:**

- **Downgrade graphiti-core to a pre-0.28 version that persists attributes correctly.** Uncertain which version + the Stage 7 L3 port is written against 0.28.2's API surface; re-applying the in-place `node_operations.py` cap-50 patch adds fragility. Forward-compatible native is cleaner.
- **Patch 0.28.2's node/edge `save()` to flatten/JSON-serialize attributes.** In-place patch clobbered on reinstall (like the cap-50 patch), and must be applied to both the local venv and the docker image.
- **Strip only the attribute fields, keep custom types.** Still leaves typed labels but the bug recurs on edge attributes; no net gain over going fully native.

---

## D-053: FIGS — LLM-only notification interface (not rules engine + bandit)

**Date:** 2026-06-26 (naming clarified 2026-06-27)
**Source:** FIGS V0 build session (`infra/decider/`); supersedes the hybrid rules-engine-plus-bandit direction proposed in the predictive-layer-spec exploratory thread.

**Naming convention (companion decision, 2026-06-27):** **MIKAI** is the backend (L3 graph + L4 reasoning). **FIGS** is the notification interface that consumes MIKAI. Every notification/push/interrupt surface is FIGS; every storage/extraction/reasoning surface is MIKAI. Code currently lives at `infra/decider/` for historical reasons; FIGS is the canonical doc name.

**Decision:** FIGS V0 is a single Python script (`infra/decider/mikai_decide.py`) that on each tick:
1. Pulls candidate signals from MIKAI (L3 graph) via Cypher recency lens (last 24h `RELATES_TO` edges) + 5 semantic-search lenses (active threads, contradictions, recurring patterns, urgent/time-sensitive, personal life)
2. Pulls live cross-source events via FIGS's own per-source adapters (`adapters/imessage.py` via SQLite, `adapters/calendar.py` via Calendar.sqlitedb direct read, `adapters/gmail.py` via IMAP + app password)
3. Invokes MIKAI's L4 reasoning by asking Claude (via headless `claude -p`, first-party OAuth — no API credits burned) "send a notification right now? if yes, what and at what interruption level?"
4. Validates evidence citations against the prompt context (no hallucinated UUIDs), enforces a cooldown window (default 2h), and dispatches via ntfy.sh on send
5. Logs every decision (sent + silent) to local SQLite at `~/.mikai/notification_log.db` for the dismiss/act feedback loop

The brain is MIKAI's L4 reasoning (the LLM). There is no rules engine, no priority queue, no LightGBM ranker, no contextual bandit, no notification-graph engineering inside FIGS itself. Default is silence; the bar for "send" is structurally high (evidence-citation requirement + cooldown + explicit "default silent" instruction in the prompt).

**Why:**

1. **Mirrors Anthropic Dreaming's shape exactly.** Dreaming (research preview, 2026-05-06) is "scheduled async LLM curator over past content." MIKAI's decider is "scheduled async LLM curator over candidate signals." Same architecture pattern in the lane Anthropic is itself heading — confirms the shape is right.
2. **The LLM is good enough to be the whole brain at single-user scale.** Candidate ranking, tiebreaker, copywriting, cold-start scoring, and explanation are all jobs the LLM does in one prompt round-trip. A rules engine sitting in front of the LLM duplicates work the LLM already does well, and adds engineering surface that doesn't pay back at 1-user scale.
3. **Cold-start works on day 1.** A contextual bandit needs hundreds of dismiss/act examples before its policy beats random. The LLM starts with strong priors and learns in-context from the most recent N decisions injected into each prompt. No pre-training, no labeled data, no warm-up period.
4. **~700 lines total.** Including all three adapters + Neo4j HTTP helper + cooldown + validation + ntfy dispatch + SQLite log. Same scope a rules engine would need just for its priority queue + dedup + token bucket.
5. **Time-based retrieval via direct Cypher closes the recency gap that semantic-only `/search` cannot.** Embeddings don't encode "what's new in the graph since yesterday"; a `MATCH ()-[r:RELATES_TO]->() WHERE r.created_at > datetime() - duration({hours: $h}) ORDER BY r.created_at DESC` does. This was the bug behind early dry-runs that surfaced 2024-era booking-tool edges instead of fresh content.

**Rejected:**

- **Hybrid rules engine + LightGBM ranker + Vowpal Wabbit contextual bandit** (the predictive-layer-spec proposal). Right architecture at FAANG scale. Wrong architecture at single-user scale: ~10× more code, multiple new ML dependencies, weeks of cold-start before signal accumulates, and the LLM is already doing every job those components would do. Logged as a future-revisit if the LLM-only approach plateaus on dismiss rate.
- **Hermes Agent fork as the runtime.** Burns extra-credit pool (third-party OAuth identity); doesn't use Max plan's base allowance. Headless `claude -p` from the user's own Claude Code install runs Max-legitimate.
- **MCP scheduled task / Routines for V0.** Routines would be the right home eventually; for V0 we run from a terminal cron equivalent. Adding the Routines integration is a separate phase once the decision quality is calibrated.
- **Apple's UNUserNotificationCenter native API (Swift app + APNs).** Would unlock action buttons on iOS lock screen, but requires a full Apple Developer setup + Swift skill. ntfy.sh provides cross-device delivery (Mac + iPhone) with standard swipe-to-dismiss interaction for V0. Upgrade path documented (terminal-notifier on Mac → Swift app on iOS) but not built.

**Implementation:**

- `infra/decider/mikai_decide.py` — main script, ~553 lines. CLI flags: `--init` (initialize SQLite), `--test-ntfy` (static dispatch test), `--dry-run` (build prompt + show Claude's decision; no dispatch, no log), `--force` (ignore cooldown), `--show-prompt`.
- `infra/decider/adapters/imessage.py` — reads `~/Library/Messages/chat.db` read-only via SQLite; requires Full Disk Access on the Python interpreter (one-time grant).
- `infra/decider/adapters/calendar.py` — reads `~/Library/Calendars/Calendar.sqlitedb` directly (works because Python already has FDA from the iMessage grant); falls back to icalbuddy then osascript. iCloud Calendars must be toggled on in System Settings → Apple ID → iCloud → Apps Using iCloud.
- `infra/decider/adapters/gmail.py` — IMAP with Google app password (`MIKAI_GMAIL_USER`, `MIKAI_GMAIL_APP_PASSWORD` in `.env.local`). Pulls unread + 24h windowed inbox.
- `infra/decider/README.md` — setup ritual, env var reference, upgrade-path table.

**Revisit if:**

- Dismiss rate fails to drop below 30% after 2–4 weeks of operation (suggests LLM judgment alone isn't enough; add a LightGBM scorer as one feature input to the prompt — predictive-layer spec).
- Notification volume becomes too sparse (suggests candidate retrieval is missing signal; add specific source adapters before changing the brain).
- Claude latency at 4h cadence becomes binding (suggests preprocessing candidates outside the LLM call; consider a lightweight scorer to shortlist the top-K from the candidate pool).
- A new Anthropic Routines + MCP integration changes the runtime model (e.g., persistent push from Routines instead of cron).

**Related to:**
- ARCH-024 (L3 port) — decider sits above the port, reads via `GraphitiAdapter` (HTTP `/search`) and direct Neo4j (Cypher recency). Does not import graphiti-core.
- D-041 (L4 above port) — confirms the decider is L4 product code, not L3 infrastructure.
- O-022 (timing model for proactive delivery) — decider's intervention-timing logic (cooldown + time-of-day awareness in prompt) is the V1 implementation.
- O-028 (reactive→proactive transition) — decider IS the proactive surface. Reactive surface (MCP `search`/`get_source`) remains alongside it.

**Revisit if:** L4 needs typed node/edge attributes (e.g. edge confidence/explanation). Reviving Stage 6 first requires a graphiti-core version that persists custom attributes as flat Neo4j properties; set `MIKAI_TYPED_EXTRACTION=1` only once that holds.

---

## D-054: FIGS feedback loop — tap redirect + dismissal inference (Discover-analog)
**Date:** 2026-07-13
**Decision:** Every FIGS notification carries a 12-char `notif_id` and its ntfy Click header is rewritten from the raw destination URL to `${TAP_BASE_URL}/t/{notif_id}`. A standalone stdlib HTTP server (`infra/decider/tap_endpoint.py`, port 8210) logs a `TAPPED` event and 302s to the real URL; an hourly cron (`infra/decider/dismissal_inference.py`) marks any SENT older than 24h with no matching TAPPED as `DISMISSED_INFERRED`. All events land in a new `notification_events` table alongside `notification_log` in `~/.mikai/notification_log.db`.

**Why:**

1. **Closing the loop is the Pareto move.** Google Discover works because every tap/skip/dwell/hide becomes training data within minutes — that tight loop is what makes its 0.5s decide-or-skip cards convert. Every other Discover mechanism (two-tower retrieval, freshness prior, diversity penalty) is downstream of the loop. FIGS today has strong substrate (ontology wiki + LLM synthesis) but zero feedback signal, so ranking quality has a low ceiling until acted/dismissed data starts flowing.
2. **Redirect wrapper is the minimum-viable capture mechanism.** ntfy is fire-and-forget — there is no callback when the user taps a card. Wrapping the Click URL in a redirect that logs then 302s is the only zero-UX-cost way to get a `TAPPED` row per real interaction. Works for every action_type FIGS emits.
3. **Startup-engineering discipline: build for today's signal, not tomorrow's infra.** The tap URL doesn't need to be publicly reachable to produce useful data. Phase 1 binds LAN only — probably 70–90% of taps happen on home wifi anyway. When the off-wifi tap becomes a real gap, swap to Tailscale (already installed on this Mac). When someone else needs to tap, cloudflared named tunnel. Each upgrade is a one-line env change; the endpoint, schema, and iPhone flow don't move.
4. **DISMISSED_INFERRED is the negative half of the signal.** Discover treats no-tap as ground truth for "not interested." Without an explicit dismiss button, an SENT that stays untapped after 24h is the closest proxy. Idempotent hourly cron; re-runs are safe. This is the signal that lets ranking know what NOT to surface, which matters as much as what to surface.

**Rejected:**

- **Tap endpoint inside the Graphiti sidecar.** Sidecar's `~/.mikai` mount is read-only (`docker-compose.yml:44`), and every code change forces a container rebuild. Standalone stdlib server on the host writes directly to the FIGS SQLite DB, no docker cycle, no dependency additions in the decider path.
- **FastAPI + uvicorn for the tap endpoint.** Adds a real dependency for what is a ~200-line HTTP server. Stdlib `http.server` with a threading mixin handles the load (personal system, single user) and stays consistent with the decider's stdlib-urllib style.
- **Cloudflared quick tunnel as Phase 1.** URL rotates on restart, forces re-wiring `~/.mikai/tap_base_url` every reboot. Also premature — LAN captures most taps, and cloudflared adds an install (`brew install cloudflared`) plus an always-on tunnel process that Phase 1 doesn't justify.
- **Cloudflared named tunnel + stable DNS.** Correct for Phase 3 when sharing beyond N=1; premature for Phase 1 which just needs the first `TAPPED` row.
- **Tailscale as Phase 1.** Also solid (Tailscale is already installed on this Mac), but requires iPhone Tailscale install first. LAN Phase 1 needs zero user setup, delivers signal today, and Phase 2 promotes to Tailscale in a single env change when off-wifi taps become the real bottleneck.
- **Discrete dismiss button in ntfy Actions.** Would give explicit negative signal instead of inferred, but forces a click even for the "not interested" case and complicates the card UX. Inferred dismissal at 24h costs nothing and lets us upgrade to explicit later without schema change (both just become `event_type` rows).
- **In-place `notification_log` extension with `tapped_at` / `dismissed_at` columns.** Simpler at N=1 but wrong shape — a notification can be tapped multiple times, and dismissed-then-tapped-later is a real case. Event-stream table lets ranking compute time-to-tap, tap-count-per-notif, and re-open-after-dismiss without further schema changes.

**Implementation:**

- **Schema** (`infra/decider/mikai_decide.py:104-176`) — `notification_events` table with columns `notif_id`, `event_type CHECK IN ('SENT','TAPPED','DISMISSED_INFERRED')`, `event_ts`, `dimension`, `action_type`, `source_ids`, `next_step_url`. Indexes on `notif_id` and `(event_type, event_ts)`. `notif_id` column added to `notification_log` for correlation.
- **Dispatch wiring** (`mikai_decide.py:1146-1214, 1490-1516`) — `new_notif_id()` mints 12-char uuid; `log_sent_event()` inserts SENT before dispatch; `build_tap_url()` swaps in `${TAP_BASE_URL}/t/{id}`; `resolve_tap_base_url()` reads env `MIKAI_TAP_BASE_URL` → file `~/.mikai/tap_base_url` → empty (falls back to raw URL untracked); `infer_dimension()` extracts `dim_N` from the LLM's `dimension` field or regex-matches "dim N" in `reasoning` as fallback. The LLM output schema (`mikai_decide.py:793`) now emits an explicit `dimension` field.
- **Tap endpoint** (`infra/decider/tap_endpoint.py`) — stdlib `http.server` + `socketserver.ThreadingMixIn`. `GET /t/{notif_id}` → 302 with real URL, log TAPPED. `GET /healthz` → 200. Rejects non-hex/non-12-char IDs at 404 (not a general open-redirect), rejects unknown IDs at 404 without inserting phantom rows. Runs as `com.mikai.tap-endpoint` LaunchAgent on port 8210 (port 8200 collides with an unrelated `brain.py` uvicorn on this machine).
- **Dismissal cron** (`infra/decider/dismissal_inference.py`) — one SQL: SENT older than `MIKAI_DISMISS_AFTER_HOURS` (default 24) with no matching TAPPED or DISMISSED_INFERRED → insert DISMISSED_INFERRED. Runs as `com.mikai.dismissal-inference` LaunchAgent every 3600s. `--dry-run` flag for ad-hoc inspection.
- **LaunchAgents** — new plists and runners under `infra/decider/launchd/`: `com.mikai.tap-endpoint.plist` + `tap-endpoint-runner.sh` (KeepAlive), `com.mikai.dismissal-inference.plist` + `dismissal-inference-runner.sh` (StartInterval=3600). Install pattern per D-051 (files symlinked into `~/Library/LaunchAgents/`, canonical copies at `~/Library/Application Support/mikai/launchd/`).
- **Phase 1 tunnel** — LAN binding at `http://192.168.88.228:8210`. `~/.mikai/tap_base_url` holds that URL. Works when iPhone is on home wifi; taps from cellular fail closed (no TAPPED row, DISMISSED_INFERRED after 24h — a false-negative, acceptable at this stage).

**Staged progression (documented separately):**

- **Phase 1 (today):** LAN-only redirect. Zero cost, zero deps. Trigger: first TAPPED row in `notification_events`.
- **Phase 2:** Swap `MIKAI_TAP_BASE_URL` to a Tailscale hostname when off-wifi taps become the observable gap. Requires iPhone Tailscale install (5 min, free). Endpoint code and iPhone flow don't change.
- **Phase 3:** Cloudflared named tunnel + stable DNS. Only needed if sharing beyond N=1.
- **Phase 4 (never for N=1):** Edge/CDN-hosted redirect.

**Revisit if:**

- Tap rate stays below ~5% after 2 weeks of accumulating data → the ranking is worse than random and the LLM prompt needs the aggregate signal fed back in as context. This is the next work item — reading `notification_events` counts and injecting a "last-7-day tap-rate by dimension / action_type" block into `build_prompt()`.
- Off-wifi missed taps become a visible product bug → promote to Phase 2 (Tailscale) with a one-line `~/.mikai/tap_base_url` change.
- A real dismiss-button UX becomes worth the friction → add `event_type='DISMISSED_EXPLICIT'` to the CHECK constraint and route via ntfy Actions webhook. Ranking logic treats explicit and inferred the same for now.
- Ranking benefits from finer-grained events (dwell time, back-swipe, snooze) → the event-stream schema absorbs new `event_type` values without breaking existing analytics.

**Related to:**
- D-053 (FIGS as LLM-only decider) — this is the feedback pipe that closes the "LLM judgment vs empirical outcome" loop D-053 explicitly deferred to a later phase.
- D-051 (Pattern B) — new LaunchAgents follow the same App Support pattern; secrets from `~/.mikai/launchd.env`.
- D-041 (L4 above port) — feedback loop lives at L4 alongside FIGS, not in the L3 sidecar.
- ARCH-023 (hybrid ingestion) — future work could ingest `notification_events` into the L3 graph as "user-action edges" (edge type: ACTED_ON, DISMISSED); currently they sit in FIGS-local SQLite only.

---

## D-055: Calendar planner — iCloud CalDAV + approval loop
**Date:** 2026-07-13
**Decision:** MIKAI reads and writes to Apple/iCloud Calendar via CalDAV (`https://caldav.icloud.com`) using an app-specific password. Once per day at 08:00 local, a LaunchAgent fetches today's editable blocks, gathers a candidate pool spanning engineering + life items, asks DeepSeek V3 to pick 2-3 items per block, and dispatches an ntfy card with Approve/Reject action URLs. The actual CalDAV PATCH only fires when the user taps Approve — routed through the tap-endpoint (which already exists from D-054). Nothing is ever written to the user's calendar without an explicit tap; a proposal that isn't resolved within 4h auto-EXPIREs on the next lookup.

**Why:**

1. **The calendar block is another FIGS card.** Same L4 selection logic (LLM ranks in-flight items), different write surface (CalDAV PATCH, not ntfy body). Reuses the FIGS pattern instead of inventing a second one.
2. **CalDAV over EventKit / Calendar.sqlitedb.** The Sumimasen Phase B watcher hit repeated TCC walls trying to read `Calendar.sqlitedb` under launchd. CalDAV is a network protocol with basic auth — no TCC, no Full Disk Access battle, works uniformly whether the LaunchAgent is fired at 08:00 or from a shell. And CalDAV is Apple's own sync backend for iCloud calendars, so a PATCH here is authoritative — direct SQLite writes would be silently overwritten by iCloud on next pull.
3. **Explicit approval loop, not auto-apply.** Writing to Brian's calendar is a hard-to-undo mutation. An LLM misfire that renames a therapy appointment or overwrites a personal reminder is a real product bug. Requiring one tap to approve costs almost nothing on iOS (ntfy Actions render Approve/Reject buttons in Notification Center) and provides the exact safety property Brian asked for: "prompted of the changes."
4. **Stdlib CalDAV client, no third-party deps.** iCloud's CalDAV surface is small: PROPFIND for discovery, REPORT for time-range queries, PUT for updates. Around 300 lines of `urllib` + `xml.etree` covers the entire need. Six unit tests over iCal fold/unfold + property replacement guard the highest-risk piece (the property-replace routine must preserve every VEVENT line except SUMMARY, DESCRIPTION, LAST-MODIFIED, DTSTAMP).
5. **Sole-attendee + ≥90-min editability heuristic.** Brian said "any block where I'm the sole attendee." Adding the duration filter (`MIKAI_PLANNER_MIN_MINUTES`, default 90) rules out reminder alarms and short personal appointments — a work block is at least an hour and a half. Meetings with other attendees are strictly out of scope regardless of duration.

**Rejected:**

- **Google Calendar API.** Brian's calendar is Apple/iCloud. Google Calendar API works only for Google-backed accounts inside Apple Calendar; iCloud calendars aren't reachable that way.
- **Direct `Calendar.sqlitedb` write.** iCloud sync will overwrite anything MIKAI writes locally on the next round-trip. Not a real write path.
- **EventKit via osascript.** TCC-gated (Calendar Automation), flaky under launchd (Sumimasen Phase B keeps hitting this). Even when it works, the write goes to Apple Calendar's local view, which then round-trips through CalDAV anyway — an extra hop with less predictable failure modes.
- **`caldav` PyPI package.** Adds a real dependency for what is ~250 lines of stdlib HTTP + XML. Consistency with the FIGS decider's stdlib-only style wins here.
- **Rich preview page before approval.** Considered a two-tap flow (tap → open detailed diff page → tap Approve). Cut for MVP: ntfy body carries the full title + description preview already, and Notification Center rendering of ntfy Actions gives one-tap Approve. If the ntfy body ever proves insufficient, promote to a `/preview/{id}` route on the tap-endpoint that renders the diff before the Approve button.
- **Auto-apply after N minutes if no reject.** Would remove the friction of an explicit tap, but flips the safety default in the wrong direction. Silent-safe > convenience for a mutating operation.
- **Include shared events (with other attendees).** Would let MIKAI rewrite a meeting title, which changes the title *for other attendees* through iCloud's invitation delta. Sole-attendee filter closes that off entirely.
- **Cron every 3 hours.** The block being rewritten is a work window that spans hours; a mid-day re-propose would just churn. Once a day at 08:00 + `--force` for on-demand refresh is the right cadence.

**Implementation:**

- **Schema** (`infra/decider/mikai_decide.py:150-186`) — new `calendar_proposals` table alongside `notification_events`. Fields: `proposal_id` (12-hex uuid), `event_uid`, `calendar_url`, `event_href`, `event_etag`, `status IN ('PROPOSED','APPLIED','REJECTED','EXPIRED')`, current/proposed title+description, `candidates_json`, `llm_rationale`, `apply_error`. Separate table because SQLite can't ALTER a CHECK constraint on `notification_events`, and the proposal lifecycle (four states, resolvable) is different from the append-only event stream.
- **CalDAV client** (`infra/decider/caldav_client.py`, ~350 lines) — stdlib HTTP + XML. Public API: `discover_principal()`, `discover_home_set()`, `list_calendars()`, `list_events(cal, start, end, sole_attendee_only)`, `patch_event(event, title, description)`, plus the high-level `todays_events()` convenience. Handles method-preserving redirects (urllib's default drops to GET on 301/302, which breaks PROPFIND). iCal fold/unfold + escape/unescape + property replace inside VEVENT are the six unit-tested primitives; every VEVENT line other than SUMMARY / DESCRIPTION / LAST-MODIFIED / DTSTAMP is preserved verbatim. Optimistic concurrency via `If-Match: <etag>` on PUT.
- **Planner** (`infra/decider/calendar_planner.py`, ~300 lines) — gathers git activity (branch, uncommitted, last-7-day log, recent branches) + `docs/OPEN.md` + `~/.mikai/inflight.md` + `docs/USER_NEEDS_REGISTRY.md`, injects into a DeepSeek V3 prompt (~10K chars total), receives structured JSON (title, description, picks, rationale), inserts a PROPOSED row, and dispatches an ntfy card with `Actions: view, Approve, ...; view, Reject, ...`. Deduplication: `already_proposed_today()` guards against re-proposing an event that already has a proposal today, regardless of that proposal's status. `--dry-run` prints the pick without writing; `--force` bypasses the dedup.
- **Approve/Reject routes** on the existing tap-endpoint (`infra/decider/tap_endpoint.py`) — `GET /approve/{proposal_id}` refetches the event by UID (etag may have drifted between propose and approve), calls `client.patch_event()`, marks status APPLIED (with the fresh etag), sends a confirmation ntfy, returns a small HTML success page. `GET /reject/{proposal_id}` just marks REJECTED. Both routes are idempotent — a second tap returns the "already resolved" HTML without side effects, guarded by a `WHERE status = 'PROPOSED'` clause on the UPDATE. Malformed / unknown / expired proposal_ids return 404 or the appropriate resolved-state page.
- **LaunchAgent** (`infra/decider/launchd/`) — `com.mikai.calendar-planner.plist` fires at 08:00 daily via `StartCalendarInterval`; `RunAtLoad=false` so installs and reboots don't trigger unexpected proposals. Runner script (`calendar-planner-runner.sh`) follows Pattern B (D-051) — sources `~/.mikai/launchd.env`, works from the App Support directory, logs to `~/.mikai/logs/calendar-planner.{out,err}.log`.
- **Credentials** — `MIKAI_ICLOUD_USER` (Apple ID email) and `MIKAI_ICLOUD_APP_PASSWORD` (app-specific password from appleid.apple.com) added to `~/.mikai/launchd.env`. The Apple ID password itself never enters the system.

**Approval lifecycle:**

1. 08:00 tick → LLM picks → `INSERT INTO calendar_proposals (status='PROPOSED')` → ntfy card fires with Approve/Reject action URLs.
2. Brian taps **Approve** → tap-endpoint `GET /approve/{id}` → refetch event by UID → `PUT` new SUMMARY + DESCRIPTION → status transitions to APPLIED with the new etag → confirmation ntfy "✓ MIKAI updated your block" → iPhone Calendar refreshes within seconds via CalDAV sync.
3. Brian taps **Reject** → status transitions to REJECTED → no CalDAV write → tomorrow at 08:00, the planner sees "already proposed today" for this event and skips (until the next day).
4. Brian taps neither within 4h → next lookup marks EXPIRED — the safe default.
5. Any failure inside `patch_event` (network / 412 etag drift / 403 auth) records `apply_error` and keeps status PROPOSED so a second tap can retry.

**Revisit if:**

- The rewrite quality is off (too generic, too many stale items) → tighten the prompt or add a git-activity weighting term. The candidate pool `picks[]` array is audited via `candidates_json` in the DB so it's easy to grade retrospectively.
- Brian wants a mid-day re-propose → drop `StartCalendarInterval` in favor of a 3-hour `StartInterval`; add cooldown logic in the planner so the same event isn't re-proposed within N hours of a Reject.
- A shared event should be editable (e.g. "family dinner planning" that Brian owns even though a partner is on it) → add a `MIKAI_PLANNER_INCLUDE_SHARED=1` env flag; keep sole-attendee as the default.
- iCloud CalDAV rate-limits us → back off exponentially in `_request()`; add a token bucket if it becomes a real issue.
- Explicit dismiss button becomes worth the friction upgrade → promote the ntfy `view` action to `http` action + add a `/dismiss/{id}` route (already ~2 lines of code given the existing pattern).

**Related to:**
- D-054 (FIGS feedback loop) — reuses the tap-endpoint infrastructure. `/approve` and `/reject` sit next to `/t/{notif_id}` on the same host, port, DB. Approval taps and notification taps go through the same LaunchAgent.
- D-051 (Pattern B) — new LaunchAgent follows the same App-Support pattern; secrets in `~/.mikai/launchd.env`; symlinks in `~/Library/LaunchAgents/`.
- D-041 (L4 above port) — calendar planner is L4 product code; it does not import graphiti-core or hit the L3Backend port directly. (Future: could pull FIGS candidates from the port instead of loading the needs registry markdown by hand.)
- D-053 (FIGS as LLM-only decider) — same LLM shape: candidate pool → structured JSON → dispatch. The planner is essentially FIGS with a CalDAV write instead of an ntfy send.
- Sumimasen Phase B (`sumimasen_watcher.py`) — Sumimasen READS the calendar to warn about MIKAI-created blocks approaching; the planner WRITES to the calendar to fill them. Both are calendar-shaped surfaces of the same L4 reasoning; Sumimasen closes the "you're about to hit this block" loop, the planner closes the "the block is generic, populate it" loop. Future integration: Sumimasen's context bundle for a rewritten block should show the picks the planner made when it fills it.
