# MIKAI Research Synthesis — reconciled 2026-07-15

> **What this is:** a single reconciled reading of the entire MIKAI research corpus (~18 docs, March–July 2026), with contradictions resolved. Built by reading every research doc in full and cross-checking each claim against the committed `DECISIONS.md`/`STATUS.md` and the live runtime. Where docs disagree, the resolution and its authority are stated.
>
> **Method / tiebreaker order:** (1) committed `DECISIONS.md` entry, (2) live runtime / `STATUS.md`, (3) recency. A doc's age is the single best predictor of reliability here — the corpus stratifies almost perfectly by date.

---

## 0. The reliability gradient (read this first)

The corpus is not a flat set of peers. It is three strata:

| Stratum | Docs | Trust for *current* planning |
|---|---|---|
| **Superseded (Mar–Apr 2026)** | memory-thesis / MEMORY_ARCHITECTURE_THESIS, INTENT_INTELLIGENCE_MANIFESTO, EPISTEMIC_DESIGN, EPISTEMIC_EDGE_VOCABULARY, l3-extraction-survey, l4-papers / L4_RESEARCH_INTEGRATION, NOONCHI_STRATEGIC_ANALYSIS, cleanup-2026-04-11 | **Lineage/rationale only.** Every one assumes a stack (Supabase/SQLite, typed extraction, epistemic-vocabulary-forward) that main has moved past. |
| **Engineering-durable (Apr 2026)** | graphiti-review / GRAPHITI_BEST_PRACTICES_REVIEW, philosophical-lineage | Engineering findings still accurate; deployment specifics stale. |
| **Current (Jun–Jul 2026)** | l4-port-gap-2026-06, strategic-research-2026-06, system-inventory-2026-06, consolidation-approaches-2026-07, dreaming-comparison-2026-06 | **Authoritative.** Reconcile prototype/design against the live port + runtime. |

**Structural defect in the corpus itself:** three of the "superseded" docs exist as **byte-identical duplicate pairs** — one copy archived on main, one copy *unmarked-live* on the `navy-windshield` worktree:
- `memory-thesis.md` (archived) == `MEMORY_ARCHITECTURE_THESIS.md` (reads "Active")
- `graphiti-review.md` (archived) == `GRAPHITI_BEST_PRACTICES_REVIEW.md`
- `l4-papers.md` (archived) == `L4_RESEARCH_INTEGRATION.md`

A June doc (`dreaming-comparison`) even cites the un-archived March twin as authoritative, propagating stale Supabase/Tier framing forward. **De-dupe these pairs; keep one copy with a correct status header.**

---

## 1. Resolved contradictions

### A. Storage substrate — Supabase/SQLite → **Graphiti + Neo4j** ✅ SETTLED
All Mar–Apr docs assume Supabase/pgvector or SQLite+sqlite-vec with `Track A/B/C` segments and `smart-split.js`. **Resolution:** Graphiti+Neo4j is the default L3 (ARCH-019), behind the `L3Backend` port (ARCH-024). SQLite lives on only as the *first-class alternate* `LocalAdapter` (ARCH-025), informed by Mnemosyne. Any doc showing Supabase DDL is dead on the stack.

### B. Layer numbering — inverted ✅ SETTLED
memory-thesis/MEMORY_ARCHITECTURE_THESIS define **L3 = intention-behavior gap, L4 = task-state**. **Resolution:** current canon is **L3 = knowledge graph, L4 = task-state awareness** (CLAUDE.md). The old "L3 intention-gap" is now a *sub-capability inside L4*. Reading old "L3" as the graph port will misalign you.

### C. Typed extraction → **native extraction** ✅ SETTLED (revival gated)
`l3-extraction-survey` (D-049) commits the whole Stage-6 thesis to deterministic source-conditional typed Pydantic extraction. **Resolution:** typed extraction is **DISABLED by default** on main (D-052, 2026-06-09); ingestion uses graphiti **native** extraction, `graphiti-core` pinned `==0.28.2`. Consequence: the Cognee-derived per-source schemas and Honcho-derived `confidence` edges are **aspirational, not live** — the live graph is **~99% generic edges (≈15 epistemic of ~15,108)**. Revival is gated on a graphiti-core version that persists custom attributes as flat properties. The Mem0-second-pass and OWL-ontology *rejections* still hold.

### D. Epistemic edges — moat → **commodity feature** ✅ SETTLED (and the walk-back was smaller than it looks)
Surface read: early docs sell the epistemic vocabulary, later docs demote it. **Closer read (important):** the early docs *never actually claimed the vocabulary alone was the moat* — the Manifesto locates the moat in the *inference model + behavioral feedback*; EPISTEMIC_DESIGN locates it in *signal-type discrimination* (reactive vs reflective vs generative); the Vocabulary doc is literally licensed "**open for adoption by other memory systems.**" **Resolution:** epistemic edges = replicable commodity; moat = the four L4 capabilities (cross-app task-state tracking, reasoning-stage classification, next-step inference, intention-behavior gap) — VISION §2, D-041. The docs were already hedging toward this in April.

### E. L4 — "DONE" → **unbuilt on main** ✅ SETTLED (factually)
l4-papers/L4_RESEARCH_INTEGRATION mark the L4 pipeline ✅ DONE (2026-03-28). **Resolution:** that "done" work is a **SQLite/TypeScript prototype on `feat/l4-testing`, not on main** (l4-port-gap-2026-06). Porting it onto the `L3Backend` port is a *structural rewrite* (Python-in-sidecar; a separate `~/.mikai/l4.db` for L4 state; delete the SQLite `resolveEntities`/`invalidateEdges` — native to GraphitiAdapter). The pure logic survives (OmniActions CoT, intervention-timing rules, Union-Find, `delivery_events`). **O-036 ("rule-based classification >80%") was never measured.**

### F. Two different "consolidation" referents ⚠️ REAL OPEN QUESTION (not doc drift)
"Consolidation" means two unrelated operations in the corpus: (1) **entity-node merging in the graph** (`consolidation-approaches-2026-07`, the "Echoes" bridging — dedupe `ocean farming`/`Ocean farming`); (2) **curator writing user-owned markdown identity files** (`dreaming-comparison`, `system-inventory` identity folder). Neither doc cross-references the other. The runtime already runs **both** (`consolidation.py` *and* the Dream → `~/.mikai/wiki/`). **Resolution:** these are distinct; the dual-memory reconciliation (graph = ground truth, wiki/identity = lossy rendered projection) is stated in the memory-architecture spec but **not yet reconciled with node-consolidation** — genuinely open.

### G. Forgetting — active pruning → **never-delete** ✅ SETTLED
memory-thesis prescribes relevance-decay + confidence-pruning (actually dropping nodes, M2/Supermemory). Later consensus (dreaming-comparison, consolidation V2, the wiki invariant) is **never delete; supersede into `history/`; forget = omit from the rendered view; graph is truth.** **Resolution:** never-delete wins. Node-merge is reversible via `merged_from`; a ~5% false-merge rate is accepted because unmerge is cheap.

### H. Numeric machinery (confidence/decay/tiers) — prescribed → **deferred** ✅ SETTLED
memory-thesis + EPISTEMIC_* prescribe confidence floats (start 0.5, ±evidence), decay half-lives, Tier-0–3 promotion gates. EPISTEMIC_DESIGN's own **2026-04-20 addendum** admits graphiti-core implements *none* of it ("vapor at the storage layer"). **Resolution:** all numeric scoring is **deferred**; the shipped system uses vanilla Graphiti + in-prompt salience, no stored scores (per the 2026-06-28 minimal-prototype directive). Revive only as the system develops.

### I. The product noun — ❌ UNRESOLVED (this is O-043, the live gate)
Four competing headline framings: **intent intelligence** (Manifesto) → **noonchi / task-state awareness** (NOONCHI_STRATEGIC) → **Problem Reasoning State Awareness** (system-inventory-2026-06, proposed as the superset of the other two) → **personal OS** (the runtime wiki + `private/strategy`). **Resolution:** *not resolved.* `system-inventory` proposes "Problem Reasoning State Awareness" as the unifier, but `strategic-research-2026-06` holds O-043 (core noun) open and says it **gates all L4/feature work** — every decision downstream is taste-based until it's answered. This is the single most load-bearing open item.

### J. Substrate as moat → **substrate is commodity** ✅ SETTLED
`strategic-insights-2026-05` treats the Graphiti corpus as a 2–3-year moat. `strategic-research-2026-06` reports **Cognee benchmarks better than Graphiti** (auto-generated ontologies) and **Mnemosyne mirrors the LocalAdapter design**; `system-inventory` corroborates. **Resolution:** substrate is buy-vs-build and replaceable via the port; **moat lives in the product layer above.** "A great memory layer without a control stack gets used by someone else's control plane" — the corpus's own strategic-risk statement.

### K. Runtime — "Claude Code Routines" → **launchd (Pattern B)** ✅ SETTLED (by reality)
`system-inventory` proposes Claude Code Routines (Anthropic-native cron) as the runtime, replacing a custom daemon. **Resolution:** the shipped runtime is **launchd LaunchAgents** (`com.mikai.*`, Pattern B, D-051). Note the live constraint: headless `claude -p` for the Surface Engine leans on Max auth — see the subscription-auth policy risk.

### L. Anthropic Dreaming — live platform risk (R8) ✅ CURRENT, real
`dreaming-comparison` + `system-inventory`: Anthropic Dreaming (released **2026-05-06**) is the manifesting platform risk, compressing the moat window ~12mo → ~6mo (ship target Q4 → Q3 2026). **MIKAI's wedge vs Dreaming:** cross-source ingestion + user-owned markdown + per-use-case retrieval recipes + a mentor-authoring layer. Keep this in view; it is not stale.

### M. The Graphiti candidate-cap patch — assumed-live → **was LOST** ⚠️ ACTION
`strategic-insights` + CLAUDE.md assume the D-042 candidate-cap patch is live. `system-inventory` **proved it was silently lost since the 2026-06-09 native switch** (verified via `docker exec`, `node_operations.py:299`). **Resolution:** re-apply via Dockerfile bake-in and verify on the running container. *(Note: the sidecar was rebuilt 2026-07-15 during the OAuth fix — patch-presence on the current image is unverified and should be checked.)*

---

## 2. What SURVIVED — the durable core (unchanged since March)

Despite all the substrate churn, the *concept* has been stable since `NOONCHI_STRATEGIC_ANALYSIS` (2026-03-26):

- **MIKAI = task-state awareness engine (noonchi).** "The AI that knows what you're stuck on." Not a memory system, not a second brain.
- **Engine vs Surface (D-001):** the L4 reasoning layer is the asset; surfaces are replaceable dispatchers.
- **Action, not engagement:** optimize for the user *acting*; default to silence (Sumimasen / Intervention Timing); dismiss-rate gate <30%.
- **The intention-behavior gap** (Track A said vs Track B did) is the deepest moat capability.
- **Four moat capabilities nobody else builds:** cross-app task-state tracking, reasoning-stage classification, next-step inference, intention-behavior gap.
- **Reasoning-state machine:** exploring → evaluating → decided → acting → stalled → completed.
- **Adopt memory infra, build the layer above.** Zero-LLM classification where possible; one LLM call per thread for next-step inference.

This is the through-line. Everything the research corpus fought about was *how to build it*, not *what it is*.

---

## 3. What is GENUINELY open (real questions, not doc drift)

1. **O-043 — the core noun** (intent-intelligence / noonchi / Problem-Reasoning-State / personal-OS). Gates all feature work.
2. **O-044 through O-047** — noticer vs executor (the Rubicon), vertical vs horizontal, user & discovery path, the 18-month moat.
3. **Dual-memory reconciliation** — how node-consolidation (graph) and the Dream wiki/identity files relate; what "importance" means for each (task-model fast-decay vs user-model slow-decay).
4. **L4-on-main** — the structural port from the SQLite/TS prototype; the 4 blocking design decisions in `l4-port-gap-2026-06`.
5. **O-036** — is rule-based state classification actually >80%? Never measured.
6. **O-035 / O-025** — does extraction generalize beyond Brian's reflective writing to activity sources (iMessage, calendar)?
7. **Typed-extraction revival** — gated on a graphiti-core version that persists custom attributes.

---

## 4. The one-paragraph reconciled picture (as of 2026-07-15)

MIKAI is a **task-state awareness engine** whose concept has been stable since March 2026 and whose *implementation* has churned underneath it. The substrate is now **Graphiti + Neo4j behind an `L3Backend` port** (SQLite/Supabase dead; LocalAdapter preserved as a first-class alternate). Extraction runs **native, not typed** — so the epistemic-edge vocabulary that dominates the early docs barely exists in the live graph, and that's fine, because **epistemic edges were never the moat**; the moat is the four L4 capabilities above the graph. **L4 itself is unbuilt on main** — a SQLite/TS prototype awaiting a structural port — and the only operational product surface is the **Surface Engine** (`mikai_decide.py` + loss function + User Needs Registry + Dimensions), *which none of the research docs describe*. Consolidation, forgetting, and importance have converged on a **never-delete, graph-is-truth, wiki-is-lossy-projection** model with all numeric scoring deferred. The live strategic pressure is **Anthropic Dreaming** (a ~6-month window), and the whole feature roadmap is gated on **O-043–O-047**, which remain unanswered. In short: *the concept is settled, the substrate is settled, the product layer is not built, and the strategic noun is not chosen.*

---

## 5. Meta-finding

The research corpus is **simultaneously ahead of and behind the code**: it contains design (typed extraction, epistemic vocabulary, L4 pipeline) that the runtime bypassed, and it omits the one thing the runtime actually ships (the Surface Engine). This is the same fragmentation problem MIKAI exists to solve, reproduced in its own repo — research, docs, and runtime each holding a different version of the truth, with no consolidation pass reconciling them. This document is that pass, for the research layer.
