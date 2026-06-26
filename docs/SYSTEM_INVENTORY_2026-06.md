# MIKAI System Inventory — 2026-06

**Generated:** 2026-06-22
**Purpose:** Surface every part of the MIKAI system originally planned (in docs + code) and reconcile against what this June 2026 conversation thread surfaced as new. Each concept gets a status (current / superseded / reframe / deprecated) and a pointer to where it now lives.
**Companion docs:** `docs/COMPARISON_MIKAI_vs_DREAMING.md`, `docs/architecture_visual.html`

---

## How to read this doc

- **Section A** inventories every markdown doc under `docs/` — title, original purpose, status, key concepts, dependencies.
- **Section B** inventories code components — `infra/graphiti/` scripts, sidecar endpoints, MCP tools — distinguishing what's built from what's planned.
- **Section C** consolidates everything this conversation thread surfaced as new — three-skills architecture, Claude Routines path, Dreaming platform signal, Apple Notes integration paths, Problem Reasoning State Awareness framing.
- **Section D** is the reconciliation map — every concept from A and B mapped to the new framing in C. Survival status: ✅ intact / 🔄 reframed / ⛔ superseded / 🗑 deprecated.

---

# Section A — MIKAI project files (docs/)

## A.1 `ARCHITECTURE.md`

| Field | Value |
|---|---|
| Title | MIKAI Architecture & Technical Stack |
| Date | 2026-03-24 |
| Original purpose | Pre-Graphiti technical stack reference. Documents Supabase/SQLite + 3-track extraction pipeline (Track A LLM, Track B rules, Track C segments) + 8 MCP tools |
| Status | ⛔ SUPERSEDED by `ARCH-019` (Graphiti is sole L3 backend) and `CURRENT_STACK.md` |
| Key concepts contributed | Three-track extraction pipeline; epistemic edge vocabulary as schema; 30-min sync cadence; 8 MCP tools (6 read + 2 write); Supabase pgvector schema |
| Dependencies | `EPISTEMIC_EDGE_VOCABULARY.md`, `EPISTEMIC_DESIGN.md` |
| What survives | Three-track ingestion conceptually (Track A = LLM extraction, Track B = behavioral, Track C = chunks) maps to Graphiti's episode types; epistemic edge vocab still valid |
| What's gone | Supabase schema; pgvector; Nomic embeddings; the entire pre-Graphiti backend assumption |

## A.2 `ARCHITECTURE_GAPS.md`

| Field | Value |
|---|---|
| Title | MIKAI Architecture Gaps & Risk Triggers |
| Date | March 2026 |
| Original purpose | Identifies 7 structural gaps (P0 + P1 + P2 + P3) blocking beta and creating competitive disadvantage |
| Status | 🔄 PARTIALLY REFRAMED — Graphiti adoption resolves several gaps; others remain |
| Key concepts contributed | Gap-driven roadmapping; honest competitive table vs Mem0/Hindsight; "epistemic edge vocabulary stored but barely queried" critique |
| Dependencies | `EPISTEMIC_EDGE_VOCABULARY.md`, `EPISTEMIC_DESIGN.md`, `ARCHITECTURE.md` |
| Resolved by Graphiti | Gap 4 (conflict resolution via entity resolution), Gap 5 (temporal validity via bitemporal edges), partial Gap 3 (hybrid search via Graphiti's vec+BM25+RRF) |
| Still open | Gap 1 (write path from MCP tools — add_note exists but `mark_resolved` doesn't), Gap 6 (epistemic edges still under-leveraged in retrieval scoring), Gap 7 (single-tenant) |

## A.3 `CLEANUP_CANDIDATES.md`

| Field | Value |
|---|---|
| Title | MIKAI Cleanup Candidates (April 2026 cleanup inventory) |
| Date | April 2026 (per file content) |
| Original purpose | Per-file deletion rationale for the 2026-04-11 cleanup that retired v0.2/v0.3 code |
| Status | ✅ CURRENT (historical record of the cleanup) |
| Key concepts contributed | The cleanup that removed all TypeScript code paths in favor of Graphiti-only on main |
| Dependencies | `CURRENT_STACK.md` |
| What survives | Useful as historical reference for what was deleted; informs which legacy branches hold what |

## A.4 `CURRENT_STACK.md`

| Field | Value |
|---|---|
| Title | MIKAI — Current Stack & Infrastructure Reference |
| Date | 2026-04-10 |
| Original purpose | Snapshot of actual running state at the moment of Graphiti adoption (`4efa463`). Documents the v0.3 → v0.4 fracture: live MCP path still reads SQLite, Graphiti infra committed but not wired |
| Status | 🔄 REFRAMED — the fracture has since closed; main is Graphiti-only |
| Key concepts contributed | The three-eras model (v0.1/v0.2 Supabase, v0.3 SQLite, v0.4 Graphiti); the 6,990-entity Graphiti graph that has since grown to 12,849; the patched `node_operations.py` (which is now unpatched again post-2026-06-09 native-extraction switch) |
| Dependencies | `GRAPHITI_INTEGRATION.md` |
| Update needed | Refresh to reflect current state — entity count, native-extraction switch, patch loss, live Claude.ai connector |

## A.5 `DECISIONS.md`

| Field | Value |
|---|---|
| Title | MIKAI Decision Log |
| Date | Active, last appended 2026 |
| Original purpose | Append-only log of architectural and product decisions with Date/Decision/Why/Rejected/Revisit-if format |
| Status | ✅ CURRENT — primary authority for resolved decisions |
| Key concepts contributed | D-001 (engine not product), D-002 (intent map + profile as outputs), D-005 (Supabase pgvector — now superseded), D-039 (MCP sole surface), ARCH-019 (Graphiti sole L3) |
| Dependencies | Every other doc |
| Pending additions | D-009 (curator architecture), D-010 (identity-folder-as-product-output), D-011 (curator as Claude Code Skill + Routine) — all queued per `.omc/plans/tier2-curator-identity-layer.md` |

## A.6 `EPISTEMIC_DESIGN.md`

| Field | Value |
|---|---|
| Title | MIKAI: Epistemic & Cognitive Design Foundations |
| Date | March 2026 |
| Original purpose | Philosophical design reference. Explicitly NOT a build document — informs extraction prompt design, graph schema decisions, evaluation criteria |
| Status | ✅ CURRENT — foundational philosophical reference |
| Key concepts contributed | Three content types (fragment / structured ideation / processed reflection) with epistemic weighting rules; neuroscience grounding (memory consolidation as reconstruction; episodic vs semantic memory distinction; self-model as constructed not discovered) |
| Dependencies | `PHILOSOPHICAL_LINEAGE.md` |
| Why it still matters | The curator agent's quality criteria for what gets promoted should follow these typologies: fragments need recurrence to promote; processed reflections promote on first occurrence with high confidence |

## A.7 `EPISTEMIC_EDGE_VOCABULARY.md`

| Field | Value |
|---|---|
| Title | Epistemic Edge Vocabulary Specification v1.0 |
| Date | March 2026 |
| Original purpose | Open specification of node types (concept/question/decision/tension/project) and edge types (supports/contradicts/depends_on/partially_answers/unresolved_tension/extends) with priority ordering for retrieval |
| Status | ✅ CURRENT — formal spec governs Graphiti edge interpretation |
| Key concepts contributed | 5 node types, 6 edge types, priority ordering (unresolved_tension=0 highest, extends=5 lowest), extraction quality standard ("at least 2 tension/question nodes out of 5-7"), first-person content rule |
| Dependencies | `EPISTEMIC_DESIGN.md` |
| Conversation extension | The curator skill uses `contradicts` and `unresolved_tension` edges as Tier 2 promotion triggers and as input to `concerns/contradictions.md` |

## A.8 `GRAPHITI_BEST_PRACTICES_REVIEW.md`

| Field | Value |
|---|---|
| Title | Graphiti Best Practices Review |
| Date | 2026-04-11 |
| Original purpose | Grades graphiti-core (B-/C+ overall) against 8 industry best practices. Identifies the scaling cliff at 4500+ entities |
| Status | ✅ CURRENT (and increasingly load-bearing as graph grows) |
| Key concepts contributed | Identification of `_resolve_with_llm` candidate-spread bug; the patch (cap at 50 + strip attributes); per-dimension grades for the dependency |
| Dependencies | `GRAPHITI_INTEGRATION.md`, `UPSTREAM_PR_DRAFT.md` |
| Status note | The patch this doc describes was LOST during the 2026-06-09 native-extraction switch. Re-applying it is task #1 in `.omc/plans/tier2-curator-identity-layer.md` follow-up session 1. The patch is now confirmed missing via this conversation's docker inspection. |

## A.9 `GRAPHITI_INTEGRATION.md`

| Field | Value |
|---|---|
| Title | Graphiti Integration — Architecture Insights & Scaling Lessons |
| Date | 2026-04-08 |
| Original purpose | Deep dive into Graphiti's 4-step entity resolution pipeline and the context window overflow root cause |
| Status | ✅ CURRENT (mechanism unchanged; patch status changed) |
| Key concepts contributed | Step-by-step resolution pipeline (extract → candidate collection → deterministic resolution → LLM disambiguation); the math (80 candidates × 40K tokens at 4500+ entities = 3.2M tokens); the in-place site-packages patch |
| Dependencies | `GRAPHITI_BEST_PRACTICES_REVIEW.md`, `UPSTREAM_PR_DRAFT.md` |
| Conversation extension | This conversation confirmed the patch is no longer active. Verified via docker exec into `mikai-graphiti` container. Line 299 area shows the unbounded `**candidate.attributes` is back. Re-apply scheduled. |

## A.10 `INTENT_INTELLIGENCE_MANIFESTO.md`

| Field | Value |
|---|---|
| Title | Intent Intelligence: A Manifesto |
| Date | (within 2026 H1) |
| Original purpose | Public-facing product manifesto. Frames MIKAI as intent intelligence layer (Layer 3 in their 3-layer model) — solving the gap between stated intentions and actual behavior |
| Status | 🔄 REFRAMED — vocabulary survives, framing as headline supersedes |
| Key concepts contributed | "Memory is what you said. Intent intelligence is what you meant"; three layers (Layer 1 Memory Interface, Layer 2 Memory Infrastructure, Layer 3 Intention-Behavior Gap Detection); action-not-engagement; epistemic edges; Sumimasen principle; the persistent assistant living in your shoulder |
| Dependencies | `EPISTEMIC_EDGE_VOCABULARY.md`, `EPISTEMIC_DESIGN.md`, `NOONCHI_STRATEGIC_ANALYSIS.md` |
| Conversation finding | "Stalled intentions" framing now lives as `concerns/active.md` signal, not as the headline product. The intent-intelligence pattern survives as one downstream project, not as MIKAI's product positioning. Brian's actual product framing surfaced this turn: Problem Reasoning State Awareness — which subsumes intent intelligence as one slice. |

## A.11 `L4_RESEARCH_INTEGRATION.md`

| Field | Value |
|---|---|
| Title | L4 Research Integration: Build Spec for Claude Code |
| Date | 2026-03-28 |
| Original purpose | Translates 5 research papers into actionable L4 architecture decisions. Maps ProMemAssist, OmniActions, etc. to L4 pipeline stages |
| Status | 🔄 REFRAMED — the research patterns survive; the L4-as-headline-product framing is downstream of the curator/identity layer |
| Key concepts contributed | ProMemAssist (working memory timing gate / Sumimasen); OmniActions (7 general + 17 specific action categories); Inner Thoughts (delivery context); ProAgent (proactive planning); the threads schema + delivery_score field design |
| Dependencies | `NOONCHI_STRATEGIC_ANALYSIS.md`, `MEMORY_ARCHITECTURE_THESIS.md` |
| Conversation finding | The five papers are the right substrate for the noonchi product layer (now framed as a downstream consumer of identity files, not the headline). The action-category taxonomy from OmniActions is useful as a retrieval recipe for `projects/next-action-inference.md`. The Sumimasen timing gate becomes the delivery scoring inside any push-mode project. |

## A.12 `MEMORY_ARCHITECTURE_THESIS.md`

| Field | Value |
|---|---|
| Title | MIKAI Memory Architecture Thesis |
| Date | March 2026 |
| Original purpose | Strategic reference for all architecture decisions. Defines the Tier 0-3 evaluation bridge (short-term → evaluation → long-term → inference) and the 4-layer architecture (L4 task-state awareness, L3 intention-behavior gap, L2 memory infrastructure, L1 memory interface) |
| Status | ✅ FOUNDATIONAL — Tier 0-3 spec is the basis for the curator architecture being executed |
| Key concepts contributed | The two-phase memory model (short-term + long-term, with evaluation bridge); Tier 0 (structural split — built), Tier 1 (recurrence/contradiction/stall checks — partly built), Tier 2 (pattern promotion + conflict resolution — NOT BUILT), Tier 3 (intent synthesis — partial); the competitor evaluation matrix |
| Dependencies | `NOONCHI_STRATEGIC_ANALYSIS.md`, `EPISTEMIC_DESIGN.md`, `ARCHITECTURE_GAPS.md` |
| Conversation finding | **This is the doc the current build plan re-elevates.** Tier 2 promotion pipeline was specced here 11 weeks ago and abandoned when the project pivoted to the noonchi framing. The curator agent IS the Tier 2 build. The plan at `.omc/plans/tier2-curator-identity-layer.md` is a direct continuation. |

## A.13 `NOONCHI_STRATEGIC_ANALYSIS.md`

| Field | Value |
|---|---|
| Title | Noonchi Strategic Analysis: Task-State Awareness Is the Product |
| Date | 2026-03-26 |
| Original purpose | Pivots competitive differentiation from epistemic edges to task-state awareness ("MIKAI is not a memory system. MIKAI is a task-state awareness engine") |
| Status | 🔄 REFRAMED — task-state awareness is the destination, not the headline product or the current build target |
| Key concepts contributed | The six-state model (exploring/evaluating/decided/acting/stalled/completed); thread detection across apps; reasoning-stage classification; next-step inference; honest admission that epistemic edges aren't a defensible moat alone |
| Dependencies | `MEMORY_ARCHITECTURE_THESIS.md`, `L4_RESEARCH_INTEGRATION.md` |
| Conversation finding | Brian explicitly corrected: task-state awareness is the destination product; the Village curator is the first step that makes it buildable. Noonchi vocabulary survives in `concerns/active.md` and as one project recipe. The noonchi headline framing supersedes — replaced by Problem Reasoning State Awareness which subsumes both intent intelligence and task-state awareness. |

## A.14 `OPEN_QUESTIONS.md`

| Field | Value |
|---|---|
| Title | MIKAI Open Questions & Active Tensions |
| Date | Active |
| Original purpose | Tracking unresolved questions (O-001 through O-024+). Don't paper over with confident answers |
| Status | ✅ CURRENT — active question log |
| Key concepts contributed | O-001 (surface first), O-002 (passive collection privacy), O-006 (hyperscaler bundling — directly relevant to Dreaming risk), O-008 (engine evaluation methodology), O-011 (Mode A/B/C routing), O-012 (passive capture / trust cliff proportionality) |
| Dependencies | All other docs |
| Conversation finding | O-006 (hyperscaler bundling) is now actively manifesting via Dreaming. Should be updated with Scenarios 1/2/3 from `COMPARISON_MIKAI_vs_DREAMING.md`. O-008 (evaluation) becomes more important — what does curator quality look like in measurable terms? |

## A.15 `PHILOSOPHICAL_LINEAGE.md`

| Field | Value |
|---|---|
| Title | MIKAI Philosophical Lineage |
| Date | 2026-04-23 |
| Original purpose | Foundational reference tracing MIKAI's intellectual lineage from Vannevar Bush (1945) through Licklider, Engelbart, Kay, Weiser, Seely Brown to present ambient agents |
| Status | ✅ CURRENT — foundational reference |
| Key concepts contributed | The Memex association principle; man-computer symbiosis; Engelbart's augmentation; the Dynabook; Weiser's calm computing; the through-line that computing's highest purpose is ambient augmentation, not engagement; the Xerox PARC vision as still-unbuilt |
| Dependencies | None internal |
| Why it still matters | The curator pattern is calm-tech — runs silently, surfaces consolidated representation only when retrieved. Aligned with the lineage. |

## A.16 `SEGMENTATION_FRAMEWORK.md`

| Field | Value |
|---|---|
| Title | Segmentation Framework: Source-Adaptive Normalization for Cross-App Thread Detection |
| Date | 2026-03-29 |
| Original purpose | Defines how MIKAI normalizes heterogeneous sources into segments of comparable information density |
| Status | ✅ CURRENT — ingestion contract |
| Key concepts contributed | Source-specific splitters (`splitGmail`, `splitAppleNote`, `splitIMessage`); metadata enrichment before embedding (Anthropic's Contextual Retrieval — 49% failure reduction); per-source minimum thresholds (15/10/20 words); the canonical segment schema |
| Dependencies | None |
| Conversation finding | The framework is upstream of the curator. Adding new sources (Spotify, Letterboxd) means adding new adapters here first. The `mikai-thread-linker` skill depends on this working well — cross-source thread detection requires segments of comparable density. |

## A.17 `STRATEGIC_INSIGHTS_2026-05.md`

| Field | Value |
|---|---|
| Title | MIKAI Strategic & Product Insights |
| Date | 2026-05 (synthesized to file 2026-06-10) |
| Original purpose | Standing strategic reference: TL;DR + threat landscape stress test + depth thesis (D1-D7) + product (Demo A/B/C) + tensions + historical pattern + 5 paths forward + enterprise architecture + why no consumer Glean + MIKAI architecture |
| Status | 🔄 REFRAMED — go-to-market notes for α, not the product spec |
| Key concepts contributed | Indie operator ICP; Demo A/B/C staging; the 5-scenario stress test (R8 risk = Anthropic absorbs auto-curation); 5 paths forward (Path 1 acquired exit 45%, Path 2 vertical specialist 20%, Path 3 infrastructure 15%, Path 4 independent 5%, Path 5 enterprise pivot 15%); 12-axis cost comparison vs Glean |
| Dependencies | `PHILOSOPHICAL_LINEAGE.md`, `MEMORY_ARCHITECTURE_THESIS.md` |
| Conversation finding | The strategic frame survives. The product framing inside it (indie operator + Sunday review) is one application of α, not the only one. The R8 risk (Anthropic absorbs auto-curation) is now manifesting via Dreaming — timeline compressed from 12 to 6 months. |

## A.18 `UPSTREAM_PR_DRAFT.md`

| Field | Value |
|---|---|
| Title | Upstream PR Draft: Configurable Resolution Candidate Cap |
| Date | (within 2026 H1) |
| Original purpose | Draft PR text for upstreaming the MIKAI candidate-cap patch to graphiti-core |
| Status | ✅ CURRENT — pending submission |
| Key concepts contributed | The exact fix (cap candidates at 50, strip attributes); cost curves; testing methodology; explanation of why this should be configurable |
| Dependencies | `GRAPHITI_INTEGRATION.md`, `GRAPHITI_BEST_PRACTICES_REVIEW.md` |
| Conversation finding | Re-applying the patch (lost in 2026-06-09 native-extraction switch) is upstream of the curator build. The upstream PR is the right long-term solution but local re-application is the right short-term action. |

---

# Section B — Components that exist as code

## B.1 `infra/graphiti/sidecar/main.py`

The FastAPI sidecar at `localhost:8100`. Existing endpoints:

| Endpoint | Purpose | Status |
|---|---|---|
| `GET /health` | Liveness check | ✅ Built |
| `POST /search` | Edge search (vec + BM25 + RRF) | ✅ Built |
| `POST /episode` | Single episode ingestion | ✅ Built |
| `POST /episode/bulk` | Bulk episode ingestion (skips edge invalidation) | ✅ Built |
| `POST /communities` | Community detection summaries | ✅ Built |
| `GET /stats` | Entity/edge/episode/community/orphan counts | ✅ Built |
| `POST /nodes/search` | Node-level hybrid search | ✅ Built |
| `GET /nodes/{uuid}` | Fetch single entity node | ✅ Built |
| `POST /nodes/{uuid}/expand` | 1-hop BFS from a node | ✅ Built |
| `POST /edges/between` | All edges between a UUID set | ✅ Built |
| `POST /history` | Bitemporal point-in-time search | ✅ Built |

**Curator-required additions (planned):**

| Endpoint | Purpose | Status |
|---|---|---|
| `GET /curator/deltas?since=ISO` | Episodes + edges created/invalidated since timestamp | 📋 Planned (follow-up session 1) |

## B.2 `infra/graphiti/scripts/`

| Script | Purpose | Status |
|---|---|---|
| `import_sequential.py` | One-episode-at-a-time import for Notes/Claude/Perplexity with retry + delay | ✅ Built; used today |
| `bulk_import.py` | Batch import via `/episode/bulk` (batch size 10, 30s delay) — fragile at scale | ✅ Built; limited use |
| `import_remaining_notes.py` | Incremental Apple Notes import (diff vs prior dump) | ✅ Built |
| `import_apple_notes.py` | Direct osascript Apple Notes import | ✅ Built |
| `import_from_dump.py` | Apple Notes from dump file with retry logic | ✅ Built |
| `read_notes.applescript` | AppleScript to dump Notes to `/tmp/mikai_notes_raw.txt` | ✅ Built |
| `add_nomic_embeddings.py` | Backfill Nomic dual-embedding column | ✅ Built |
| `embedding_comparison.py` | Analysis of embedding quality | ✅ Built |
| `compare_thread.py` | Per-thread comparison analytics | ✅ Built |
| `compare_quick.py` | Quick comparison utility | ✅ Built |
| `run_community_detection.py` | Community labeling pass | ✅ Built |
| `run_community_fast.py` | Faster community detection variant | ✅ Built |

**Curator-required additions (planned):**

| Component | Purpose | Status |
|---|---|---|
| `~/.claude/skills/mikai-curator/SKILL.md` | Operationalized curator brief installed as Claude Code skill | 📋 Planned (this session authoring) |
| `~/.claude/skills/mikai-thread-linker/SKILL.md` | Cross-thread topic clustering skill | 📋 Planned |
| `~/.claude/skills/deep-analyze/SKILL.md` | Meta-reasoning disambiguate-formalize-gap-find routine | 📋 Planned |
| `infra/recipes/executor.py` | Generic retrieval recipe runner | 📋 Planned (follow-up session 2) |

## B.3 MCP tools currently exposed

(From the MIKAI MCP server reachable via `mcp__claude_ai_MIKAI__*`)

| Tool | Purpose | Status |
|---|---|---|
| `add_note` | Save a note/insight as a new episode (with auto-extraction) | ✅ Built |
| `search` | Edge-search (compressed facts via hybrid search) | ✅ Built |
| `get_source` | Retrieve original episode prose | ✅ Built |
| `get_history` | Bitemporal point-in-time query | ✅ Built |
| `get_stats` | Graph snapshot | ✅ Built |

**Curator-required additions (planned):**

| Tool | Purpose | Status |
|---|---|---|
| `mikai_run_project(project_name, user_query)` | Execute a retrieval recipe against identity + graph | 📋 Planned (follow-up session 2) |
| `mark_resolved(node_uuid)` | Per `ARCHITECTURE_GAPS.md` Gap 1 — still missing | 📋 Planned |

## B.4 Runtime infrastructure

| Component | Purpose | Status |
|---|---|---|
| Docker Compose stack | `mikai-graphiti` (FastAPI sidecar) + `mikai-neo4j` containers | ✅ Built, running |
| Cloudflare tunnel | Anthropic MCP proxy → laptop sidecar via cloudflared | ✅ Built, intermittent |
| Pattern B LaunchAgents | Laptop-as-home-server via `~/Library/Application Support/mikai/launchd/` | ✅ Built (per O-042 closure) |
| Live Claude.ai connector | Streams conversation turns into Graphiti as episodes | ✅ Verified 2026-05-19 |
| Apple Notes ingestion pipeline | osascript dump → `import_from_dump.py` → episodes | ✅ Built, manual trigger |
| Claude Code Routines | Anthropic-native cron for scheduled skill execution | ✅ Available (May/June 2026 Anthropic release) — to be configured for `mikai-curator` |

## B.5 Graph state (as of 2026-06-15)

| Metric | Count |
|---|---|
| Entities | 12,849 |
| Relationships (edges) | 18,510 |
| Episodes | 3,455 |
| Communities | 50 |
| Orphan entities | 2,057 (16.0%) |

---

# Section C — What this conversation surfaced as new

The MIKAI thread that produced this inventory ran from roughly 2026-06-14 to 2026-06-22. It surfaced significant new architecture and product framing not yet in any existing doc.

## C.1 The Problem Reasoning State Awareness framing

The user's articulation of what MIKAI is actually for, in his own words: *a system that recognizes when current thinking belongs to an existing problem-thread, auto-consolidates new insights into a stable representation, and surfaces the consolidated reasoning chain next time you pick up the thread.*

This subsumes:
- The intent-intelligence framing from `INTENT_INTELLIGENCE_MANIFESTO.md` (stalled intentions = one signal class)
- The noonchi task-state framing from `NOONCHI_STRATEGIC_ANALYSIS.md` (task state = one signal class)
- The original Village pattern from the user's earliest March 19 Claude thread (mentor projects = one downstream consumer)

It generalizes them. Problem reasoning state awareness = cross-thread problem-clustering (L3) + auto-consolidation into stable representation (curator) + state surfacing on re-engagement (thread-linker).

## C.2 The three-skills architecture

Replaces "one curator" with three composable Claude Code skills:

| Skill | Purpose | Triggered by |
|---|---|---|
| `mikai-curator` | Tier 2 consolidation: read graph deltas, decide NOOP/APPEND/SUPERSEDE/TENSION/DEFER/SKIP_PINNED, write identity files with episode citations | Cron via Routines (daily) |
| `mikai-thread-linker` | Detects "current work belongs to existing problem-thread X", surfaces consolidated project file | Loaded automatically in every session via description match |
| `deep-analyze` | Meta-reasoning routine: disambiguate → formalize → find gaps → synthesize | Fuzzy match on complexity signals ("stress test", "what am I missing", "are there gaps") |

The deep-analyze skill produces the high-value reasoning that the curator most wants to consolidate. The thread-linker makes the curator's output useful in the moment.

## C.3 Claude Code Routines as the runtime

Replaces custom Python daemon / external cron / LaunchAgent fork with Anthropic's native scheduling primitive shipped May/June 2026:

- Three CLI tools: `cron_create`, `cron_list`, `cron_delete`
- Triggers: scheduled cadences (hourly/daily/weekly), GitHub events, API calls
- Runs on Anthropic-managed cloud — continues even if laptop offline
- Max plan: 15 routines/day cap (curator runs once/day = well under)
- First-party OAuth → Max-legitimate, no overage credits burned

This closes the question of "where does the curator run." Answer: as a Claude Code skill scheduled via Routines.

## C.4 Anthropic Dreaming as platform-risk signal

Anthropic released Dreaming on 2026-05-06 as a research preview. Mechanism similarity to MIKAI's curator is striking. Scope difference is fundamental (agent self-improvement vs cross-source user-knowledge-consolidation).

Implications:
- The R8 risk from `STRATEGIC_INSIGHTS_2026-05.md` ("Anthropic absorbs auto-curation in next 12 months") timeline compressed from 12 to ~6 months
- MIKAI's wedge clarified to four properties: cross-source ingestion + user-owned files + per-use-case recipe library + mentor authoring layer
- Ship target compressed from Q4 2026 to Q3 2026
- See `docs/COMPARISON_MIKAI_vs_DREAMING.md` for full analysis

## C.5 Apple Notes integration paths

Three distinct ways to add Apple Notes to "the repository":

| Path | Target | Status | Use for |
|---|---|---|---|
| A. Apple Notes Connector | Claude Desktop UI | ✅ Available (Pro/Team subscription) | Read-on-demand within Claude Desktop only |
| B. Apple Notes MCP server (community-built) | Claude Code | ✅ Available (multiple options: NotesY, ALucek/apple-notes, LeetaoGoooo) | Real-time Notes read access from Claude Code skills |
| C. MIKAI graph ingestion via osascript | Graphiti substrate | ✅ Built (`infra/graphiti/scripts/import_apple_notes.py`) | Cross-source thread detection — Notes participate as episodes alongside Claude conversations |

Recommendation: **Path C is the right one** for the curator use case. Path B is complementary for real-time reads.

## C.6 The identity folder schema

A user-owned filesystem schema for MIKAI's output:

```
~/mikai/identity/
├── core/         — slow-changing identity (values, goals, perspectives, voice, people, constraints)
├── taste/        — preference signals (film, food, music, travel, furniture, reading)
├── mentors/      — Village mentor briefs (Brian-authored skeletons, curator-filled evidence)
├── concerns/     — current thinking state (active, contradictions, deferred, resolved)
├── projects/     — downstream consumers (Village mentor / weekend planner / taste-furniture / etc)
└── history/      — append-only curator audit trail
```

Per-file frontmatter includes `file_type`, `last_updated`, `last_updated_by`, `cited_episodes`, `confidence`, `pinned_sections`, optional `supersedes`, optional `revisit_after`.

Key invariants:
- Never delete (supersedes move files to `history/`)
- Pinned sections immune to curator overwrite
- Every body change cites ≥1 episode UUID
- SUPERSEDE requires decision quorum (≥2 supporting episodes new, ≤1 old in 60d, explicit-change verb signal)

## C.7 The retrieval recipe pattern

A "project" is a markdown file in `~/mikai/identity/projects/` defining how a downstream LLM use case reads identity + graph:

```yaml
project_name: village-mentor-maya-angelou
reads_from: [core/voice.md, core/values.md, mentors/maya-angelou.md, taste/reading.md, concerns/active.md]
graph_recipe:
  embed_query: "{{user_query}}"
  filters: { valid_at_now: true, include_sources: [apple-notes, claude-thread] }
  num_results: 12
prompt: | ...
```

Recipes are content, not code. Brian authors them. A generic recipe executor (planned, follow-up session 2) reads the recipe and runs it.

## C.8 The patch-loss finding

The `node_operations.py:299` candidate-cap patch documented in `CLAUDE.md` and `GRAPHITI_INTEGRATION.md` is no longer active in the running container. Verified this session via `docker exec mikai-graphiti grep -n "max_candidates..." | head -10` — line 299 shows the unbounded `**candidate.attributes` spread is back.

Lost during the 2026-06-09 native-extraction switch (when graphiti-core was upgraded/pinned to 0.28.2). Re-application strategy: bake patch into Dockerfile so it survives future rebuilds. Pending in `.omc/plans/tier2-curator-identity-layer.md` follow-up session 1 task #1.

## C.9 The MCP-search-vs-get_source insight

The graph stores both edges (compressed facts) and episodes (full reasoning prose). The default `search` returns edges only; reasoning-recovery requires `get_source`. This is a retrieval-API design point, not a storage problem — Graphiti is the right substrate.

Implication: the MCP tool surface should make the dual-retrieval pattern explicit. Either via updated tool descriptions, a routing tool, or an enriched edge format with a `reasoning` field alongside `fact`.

## C.10 The meta-pattern as a skill (deep-analyze)

Brian named his own recurring cognitive routine: *disambiguate → formalize → find gaps in my logic and reasoning*. This routine is itself a skill candidate. Sketch in conversation:

```markdown
---
name: deep-analyze
description: Triggered on complexity signals ("stress test", "what am I missing")
---
# Pass 1: Disambiguate — name 2-4 hidden ambiguities
# Pass 2: Formalize — precise restatement, define vague terms
# Pass 3: Find gaps — hidden constraints, missing evidence, unstated tradeoffs, tacit goals
# Pass 4: Synthesize — formalized question + critical gaps + recommendation
```

When deep-analyze runs and produces a structured pass, that output becomes high-value input for the curator. The two skills compose.

---

# Section D — Reconciliation map

Every concept from Sections A and B, mapped to the new framing in Section C. Survival status notation:
- ✅ INTACT — survives unchanged
- 🔄 REFRAMED — survives but repositioned in the new architecture
- ⛔ SUPERSEDED — replaced by a newer mechanism
- 🗑 DEPRECATED — removed entirely
- 📋 PENDING — planned but not yet built

## D.1 Concept-level reconciliation

| Concept | Source doc/code | Status | New location / framing |
|---|---|---|---|
| Three-track extraction pipeline | `ARCHITECTURE.md` | ⛔ SUPERSEDED | Replaced by Graphiti's single extraction path with bitemporal edges |
| Supabase pgvector backend | `ARCHITECTURE.md`, D-005 | ⛔ SUPERSEDED | ARCH-019 chose Graphiti + Neo4j |
| 30-minute sync cadence | `ARCHITECTURE.md` | 🔄 REFRAMED | Now controlled by Claude Code Routines (daily for curator; ingestion as needed) |
| 8 MCP tools (6 read + 2 write) | `ARCHITECTURE.md` | 🔄 REFRAMED | Existing MIKAI MCP tools (add_note, search, get_source, get_history, get_stats); additions for `mikai_run_project` and `mark_resolved` pending |
| Epistemic edge vocabulary | `EPISTEMIC_EDGE_VOCABULARY.md` | ✅ INTACT | Used by Graphiti as edge types; curator uses `contradicts` and `unresolved_tension` as Tier 2 signals |
| Five node types (concept/question/decision/tension/project) | `EPISTEMIC_EDGE_VOCABULARY.md` | ✅ INTACT | Still the extraction target |
| Six edge types with priority ordering | `EPISTEMIC_EDGE_VOCABULARY.md` | ✅ INTACT | Priority ordering informs retrieval recipe filters |
| Extraction quality standard ("at least 2 tension/question nodes") | `EPISTEMIC_EDGE_VOCABULARY.md` | ✅ INTACT | Curator's quality check |
| Three content types (fragment/structured/processed) | `EPISTEMIC_DESIGN.md` | ✅ INTACT | Curator promotion rules: fragments need recurrence to promote (Tier 2 trigger 1); processed reflections promote on first occurrence |
| Memory consolidation as reconstruction | `EPISTEMIC_DESIGN.md` | ✅ INTACT | Identity files reconstruct from graph episodes on each curator run |
| Episodic vs semantic memory distinction | `EPISTEMIC_DESIGN.md` | ✅ INTACT | `concerns/active.md` = episodic; `core/*.md` + `taste/*.md` = semantic |
| Self-model as constructed | `EPISTEMIC_DESIGN.md` | ✅ INTACT | Identity layer is constructed from corpus, never claimed as ground truth |
| Stalled intentions surfacing (`get_stalled`) | `INTENT_INTELLIGENCE_MANIFESTO.md` | 🔄 REFRAMED | Becomes one entry in `concerns/active.md`; surfaces via task-state project recipe, not as MIKAI's headline product |
| Intention-behavior gap detection (Layer 3) | `INTENT_INTELLIGENCE_MANIFESTO.md` | 🔄 REFRAMED | Subsumed into Problem Reasoning State Awareness; one of many signal classes the curator tracks |
| Three layers (Interface / Infrastructure / Intent) | `INTENT_INTELLIGENCE_MANIFESTO.md` | 🔄 REFRAMED | Replaced by the layered architecture in `architecture_visual.html` (Source → L3 substrate → Skills → Identity layer → Downstream projects) |
| Action-not-engagement | `INTENT_INTELLIGENCE_MANIFESTO.md` | ✅ INTACT | Foundational stance; calm-tech-aligned |
| The persistent assistant in your shoulder | `INTENT_INTELLIGENCE_MANIFESTO.md` | ✅ INTACT | The MIKAI long-term vision; downstream of identity-layer-as-substrate |
| Tier 0 (segment ingestion) | `MEMORY_ARCHITECTURE_THESIS.md` | ✅ INTACT | Built into Graphiti's episode ingestion |
| Tier 1 (recurrence/contradiction/stall checks) | `MEMORY_ARCHITECTURE_THESIS.md` | 🔄 PARTIALLY BUILT | Graphiti's entity resolution + edge invalidation handles parts; explicit recurrence check needed for curator |
| Tier 2 (pattern promotion + conflict resolution) | `MEMORY_ARCHITECTURE_THESIS.md` | 📋 PENDING | This is the curator agent — being built per `.omc/plans/tier2-curator-identity-layer.md` |
| Tier 3 (intent synthesis) | `MEMORY_ARCHITECTURE_THESIS.md` | 📋 PENDING | The retrieval recipe executor — follow-up session 2 |
| Four-layer architecture (L1-L4) | `MEMORY_ARCHITECTURE_THESIS.md` | 🔄 REFRAMED | Maps to: L1 MCP+files (built) → L2 Graphiti substrate (built) → L3 identity layer (pending) → L4 downstream projects (pending) |
| Six-state task-state model (exploring/.../completed) | `NOONCHI_STRATEGIC_ANALYSIS.md` | 🔄 REFRAMED | Survives in `concerns/active.md` schema as a state hint, not as the user-facing product surface |
| Thread detection across apps | `NOONCHI_STRATEGIC_ANALYSIS.md`, `SEGMENTATION_FRAMEWORK.md` | ✅ INTACT and EXPANDED | Becomes the `mikai-thread-linker` skill |
| Reasoning-stage classification | `NOONCHI_STRATEGIC_ANALYSIS.md` | 🔄 REFRAMED | One of many curator decision factors, not standalone |
| Next-step inference | `NOONCHI_STRATEGIC_ANALYSIS.md`, `L4_RESEARCH_INTEGRATION.md` | 🔄 REFRAMED | Becomes a downstream project (`projects/next-action.md`) per `OmniActions` taxonomy |
| Action-optimized delivery (`<30%` dismiss rate) | `NOONCHI_STRATEGIC_ANALYSIS.md`, `MEMORY_ARCHITECTURE_THESIS.md` | ✅ INTACT | Curator quality target; surfaces via dismiss CLI (deferred) |
| ProMemAssist Sumimasen timing gate | `L4_RESEARCH_INTEGRATION.md` | 🔄 REFRAMED | Becomes delivery-scoring inside push-mode projects |
| OmniActions taxonomy (7 general + 17 specific) | `L4_RESEARCH_INTEGRATION.md` | ✅ INTACT | Retrieval recipe for action-inference projects |
| ProAgent proactive planning | `L4_RESEARCH_INTEGRATION.md` | 🔄 REFRAMED | Downstream project recipe |
| Honcho dialectic user modeling (referenced via Hermes) | Conversation only | 📋 OPTIONAL | Candidate component to borrow for curator's user-model layer |
| Personal Knowledge Graph framing | Graph search this session | ✅ INTACT | MIKAI = PKG (data-owner-centric), not agent-memory (process-centric) |
| Hermes Agent as runtime reference | Conversation only | 🔄 REFRAMED | Hermes does adjacent work; OMC+Claude Code is the Max-legitimate equivalent runtime |
| Cognee architecture inspiration | Graph search this session | ✅ INTACT | PM agent already shipped L3 improvements based on Cognee assessment |
| Karpathy wiki-style memory mapping | Graph search this session | ✅ INTACT | Identity folder schema is the wiki-style realization |
| Letta tiered memory (core/recall/archival) | Conversation only | ✅ INTACT | Inspiration for `core/` (slow-changing) vs `concerns/` (fast-changing) |
| TME, ProAgentBench, Sensible Agent, A-MEM, GAM citations | `STRATEGIC_INSIGHTS_2026-05.md` Appendix A | ✅ INTACT | External research grounding; cite in future external materials |
| Indie operator ICP | `STRATEGIC_INSIGHTS_2026-05.md` | 🔄 REFRAMED | One target segment, not the only one; Brian's own use case validates the build |
| Demo A/B/C staging | `STRATEGIC_INSIGHTS_2026-05.md` | 🔄 REFRAMED | Demo B (Sunday review) is one downstream project; not the headline product |
| Five paths forward (acquired exit / vertical specialist / infrastructure / independent / enterprise) | `STRATEGIC_INSIGHTS_2026-05.md` | ✅ INTACT | Path 1 (acquired exit) remains modal baseline; Path 2 vertical specialist optimized-for; Path 3 infrastructure kept as optionality |
| R8 risk: Anthropic absorbs auto-curation | `STRATEGIC_INSIGHTS_2026-05.md` | 🔄 ACTIVE — TIMELINE COMPRESSED | From 12mo to 6mo via Dreaming release; see `COMPARISON_MIKAI_vs_DREAMING.md` |
| `node_operations.py:299` patch | `GRAPHITI_INTEGRATION.md`, `UPSTREAM_PR_DRAFT.md` | ⛔ LOST (verified this session) — 📋 RE-APPLY PENDING | Lost during 2026-06-09 native-extraction switch; re-apply via Dockerfile baked-in step |
| Source-adaptive segmentation | `SEGMENTATION_FRAMEWORK.md` | ✅ INTACT | Required upstream of curator; new source types need adapters |
| Metadata enrichment (49% failure reduction) | `SEGMENTATION_FRAMEWORK.md` | ✅ INTACT | Standard ingestion practice |
| Identity 360 / YouTube / Instagram inference parallel | Conversation only | 🔄 REFRAMED | Works partially — behavioral signal sources are domain-limited and partially API-locked; MIKAI's coverage uneven by domain |
| Computer Use ingestion architecture | Conversation graph this session (March 2026 thread) | ✅ INTACT | Path for locked sources (iMessage, WhatsApp); architecture from March thread still valid |
| LocalAdapter (ARCH-025) with Hermes 3/4 via Ollama | Conversation graph this session (May 17 thread) | ✅ INTACT | Privacy-pure SKU for M-series Max/Ultra users; deferred |
| The Village mentor pattern | Original March 19 Claude thread + this session | ✅ INTACT | One downstream project type; first proof point per Brian's correction |
| Auto-update of project files | Original March 19 thread + this session | ✅ FOUNDATIONAL | This IS the curator |

## D.2 Code-level reconciliation

| Component | Status | Note |
|---|---|---|
| Graphiti sidecar (FastAPI) | ✅ INTACT, EXTEND | Add `/curator/deltas` endpoint |
| `import_sequential.py` | ✅ INTACT | Curator runs downstream |
| `bulk_import.py` | ✅ INTACT with caveat | Single-episode mode preferred while patch is missing |
| `import_apple_notes.py` | ✅ INTACT | Cross-source ingestion path C |
| MIKAI MCP tools (add_note/search/get_source/get_history/get_stats) | ✅ INTACT | Curator and recipe executor both call these |
| Graphiti `node_operations.py` patch | ⛔ LOST | Re-apply pending |
| Live Claude.ai connector | ✅ INTACT | Ingests conversation turns including this thread |
| Pattern B LaunchAgents | ✅ INTACT | Curator runs via Routines instead of new LaunchAgent |
| `~/.claude/skills/mikai-curator/SKILL.md` | 📋 PENDING | Authoring task this session per plan |
| `~/.claude/skills/mikai-thread-linker/SKILL.md` | 📋 PENDING | Authoring task this session per plan |
| `~/.claude/skills/deep-analyze/SKILL.md` | 📋 PENDING | Authoring task this session per plan |
| `infra/recipes/executor.py` | 📋 PENDING | Follow-up session 2 |

## D.3 What this conversation deprecates entirely

| Concept | Source | Why deprecated |
|---|---|---|
| Supabase as backend | `ARCHITECTURE.md` (era v0.1/v0.2), D-005 | Superseded by ARCH-019 (Graphiti). Already gone from main since 2026-04-11 cleanup. |
| Local SQLite path (v0.3) | `CURRENT_STACK.md` | Superseded by ARCH-019. Already deleted in cleanup. |
| `MIKAI_LOCAL` runtime flag | `CURRENT_STACK.md` | No longer relevant — there's only Graphiti. |
| Three-track extraction as separate scripts | `ARCHITECTURE.md` | Graphiti's extraction unifies them. |
| Pre-Graphiti MCP server (`surfaces/mcp/server.ts`) | `CURRENT_STACK.md` | Replaced by the Graphiti-backed MIKAI MCP server. |
| Custom Python daemon for the curator | Earlier in this conversation | Replaced by Claude Code skill + Routines. |
| LaunchAgent for the curator specifically | Earlier in this conversation | Replaced by Routines (LaunchAgent still used for Pattern B sidecar lifecycle). |
| Hermes Agent fork as curator runtime | Earlier in this conversation | Replaced by OMC + Claude Code (Max-legitimate). |

## D.4 What's queued for the upcoming sessions

| Session | Work | Status |
|---|---|---|
| **This session** (in flight) | Three deliverables: comparison doc, HTML viz, this inventory | 2 of 3 complete, this is #3 |
| **Authoring session α v0** | Per `.omc/plans/tier2-curator-identity-layer.md` Section 7 | Pending Brian approval of revised plan with three-skills update |
| **Engineering session 1** | Re-apply `node_operations.py` patch (via Dockerfile); build `/curator/deltas` endpoint; write curator skill; install Routine; first dry-run | Pending session 1 completion |
| **Engineering session 2** | Build recipe executor; expose MCP tool; author 2 more project files; end-to-end test | Pending session 1 completion |
| **Engineering session 3** | mikai-thread-linker skill build; deep-analyze skill polish; feedback loop (dismiss CLI) | Pending session 2 completion |
| **Strategic monitoring** | Watch Dreaming preview docs for generalization to Projects / user content | Ongoing, weekly cadence |

---

## Cross-reference index

| If you want to know about... | Read |
|---|---|
| The current build plan | `.omc/plans/tier2-curator-identity-layer.md` |
| How MIKAI compares to Dreaming | `docs/COMPARISON_MIKAI_vs_DREAMING.md` |
| Visual representation of both architectures | `docs/architecture_visual.html` |
| The strategic positioning (5 paths forward, etc.) | `docs/STRATEGIC_INSIGHTS_2026-05.md` |
| The intellectual lineage of MIKAI's vision | `docs/PHILOSOPHICAL_LINEAGE.md` |
| The original Tier 0-3 evaluation bridge spec | `docs/MEMORY_ARCHITECTURE_THESIS.md` |
| The epistemic edge taxonomy | `docs/EPISTEMIC_EDGE_VOCABULARY.md` |
| Why epistemic typing matters | `docs/EPISTEMIC_DESIGN.md` |
| The Graphiti patch story | `docs/GRAPHITI_INTEGRATION.md`, `docs/GRAPHITI_BEST_PRACTICES_REVIEW.md`, `docs/UPSTREAM_PR_DRAFT.md` |
| How sources get normalized | `docs/SEGMENTATION_FRAMEWORK.md` |
| Active unresolved questions | `docs/OPEN_QUESTIONS.md` |
| Settled decisions | `docs/DECISIONS.md` |
| Stack snapshot as of April 2026 | `docs/CURRENT_STACK.md` (update pending) |
| The pre-Graphiti era | `docs/ARCHITECTURE.md` (superseded but historically useful) |
| Pre-Graphiti gaps | `docs/ARCHITECTURE_GAPS.md` |
| The cleanup history | `docs/CLEANUP_CANDIDATES.md` |

---

*Inventory generated 2026-06-22 as Deliverable 3 of the autopilot run. Companions: `COMPARISON_MIKAI_vs_DREAMING.md` (Deliverable 1), `architecture_visual.html` (Deliverable 2).*
