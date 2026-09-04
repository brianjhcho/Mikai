# Vault comparison report

- **Serial (workers=1, 5h20m)**: `/Users/briancho/.mikai/wiki-mikai-new`
- **Parallel (workers=8, 52min)**: `/Users/briancho/.mikai/wiki-mikai-parallel-test`

## Page-type distribution

| type | Serial (workers=1, 5h20m) | Parallel (workers=8, 52min) | delta | confound |
|------|---------|---------|-------|----------|
| `concepts` | 196 | 174 | +22 |  |
| `entities` | 56 | 57 | -1 |  |
| `sources` | 45 | 46 | -1 |  |
| `queries` | 25 | 34 | -9 |  |
| `journal` | 4 | 27 | -23 |  |
| `goals` | 4 | 7 | -3 |  |
| `habits` | 1 | 4 | -3 |  |
| `reflections` | 0 | 2 | -2 |  |
| `comparisons` | 4 | 1 | +3 |  |
| `synthesis` | 4 | 3 | +1 |  |
| `media` | 0 | 0 | +0 |  |
| **total** | **339** | **355** | **-16** | |

## Source coverage

- Shared sources (same filename in both `raw/sources/`): **46**
- Only in Serial (workers=1, 5h20m): **0**
- Only in Parallel (workers=8, 52min): **0**
- Of shared sources, English-only (< 2% non-ASCII): **46** (100%)

## Source-summary page comparison (clean surface — Surface A)

### Body richness (words per source-summary)

| stat | Serial (workers=1, 5h20m) | Parallel (workers=8, 52min) | ratio A/B |
|------|---------|---------|-----------|
| median | 534 | 501 | 1.07 |
| mean   | 602 | 596 | 1.01 |
| p90    | 1034 | 1023 | — |

### Wikilink density (outgoing links per source-summary)

| stat | Serial (workers=1, 5h20m) | Parallel (workers=8, 52min) | ratio A/B |
|------|---------|---------|-----------|
| median | 8 | 7 | 1.14 |
| mean   | 8.7 | 7.0 | 1.24 |
| p90    | 14 | 12 | — |

### Per-source wikilink target overlap

- Median Jaccard: **0.06**
- Mean Jaccard:   **0.09**
- Sources with ≥ 50% overlap: **0 / 45**

### Frontmatter agreement

- Same `title`:   **5 / 45** (11%)
- Same `tags` (set-equal):   **0 / 45** (0%)
- Same `related` (set-equal): **0 / 45** (0%)

## Concept-slug overlap (Surface A + C)

- **Full concept Jaccard**: 17.09%
- **Concept Jaccard on English-only sources**: 17.09%
- **Entity Jaccard**: 34.52%
- Reference nondeterminism baseline (same pipeline, two runs, historical): **~7%**

## Concept-slug differences (not just Jaccard percent)

- Concepts only in Serial (workers=1, 5h20m): **142**
  - `activity-vocabulary, addiction-vs-passion, agency-career-model, agent-harness, ai-development-phases, ai-legal-automation, ai-personality-farming, ai-public-information-mediation, ambient-computing, artist-entrepreneur-split, atomic-actionable-feed-card, attention-anchors, attention-as-injection-constraint, attention-economics, bdi-agent-theory, behavioral-trace-memory, beta, bidding-lease-system, bilt-four-phase-agent-architecture, brand-as-identity-substitute, browser-as-primary-capture-surface, build-ports-not-palaces, capture-loop-wedge, carry-rule, closed-loop-goal-controller, communication-degradation-loop, comprehensive-autofill-for-systems-change, consumer-quality-platform, consumer-unity, context-compiler, context-gatekeeper-risk, context-triggered-vs-time-triggered-resurfacing, convergence-guarantee, cross-ecosystem-user-owned-layer, culture-industry, culture-marketplace, dalio-deflationary-cycle, demo-ability-problem, democratized-physio, device-as-io-surface, device-proliferation-as-mikai-oxygen, dia-wedge, digital-supply-chain-transparency, dormant-agent-model, dreams-as-addiction, dynamic-social-pricing, enduring-human-need, entp-statelessness, event-sourcing-for-intent-graph, executive-assistant-feed, external-verifiability, faithfulness-invariant, fear-of-mistakes, follow-through-as-system, food-system-reform, four-hour-study-sweet-spot, general-manager-agent, generational-wealth-decay, goal-verification-partition, graph-not-folders-capture-model, housing-speculation-neutralization, imperfect-forward-motion, importance-prior, information-clustering, infrastructure-as-a-service, instruction-density-axis, integration-assembly-as-moat, intelligence-vs-judgment-work, intelligent-browser, interaction-conversion-metric, joy-as-performance-enabler, knowledge-graph-vs-neural-network, llm-product-development-mistakes, llm-wiki, love-first-principle, machine-readable-acceptance-criteria, memex, memory-promotion-gate, metabolism-mismatch, metabolism-monetization-problem, micro-randomized-trial, mikai-models-the-self, mikai-two-headless-stack, model-context-protocol, nature-as-dopamine-baseline, neural-network-taxonomy, news-saturation-threshold, noble-purpose, noonchi-retrieval-chain, observe-think-act-loop, outcome-oriented-ai, phase-change-materials, pm-as-agent-translation-layer, position-before-force, positive-reinforcement-leadership, potential-without-execution, predictive-ml-layer, protocol-stack-three-layers, psychology-policy-weighting-model, purpose-driven-purchasing, push-vs-pull-agent-architecture, query-time-synthesis-vs-write-time-promotion, re-entrant-deferral-surface, reading-people, relative-impact, religion-as-process-orientation, respect-as-confidentiality, return-skew, reward-signal-design, scope-minimization-as-credibility, se-first-product-strategy, second-brain-five-strata, skill-md, skill-routing-taxonomy, skills-vs-tools-distinction, sleep-time-compute, snapshot-brain-vs-continuous-ingestion, specialized-medicine-advocacy, spiritual-bypass, strength-first-development, sumimasen-gate, supply-chain-of-excellence, technology-philosophy-infusion, tension-release-through-expression, the-cave, the-space-between, the-why-sandwich, three-generation-failure-pattern, three-layer-governance-model, three-mikai-repositioning-options, three-pillar-life-quality, trading-checklist-discipline, transactive-memory, triggered-compaction, two-sets-of-three, unrefined-function-as-product, vigilance-vs-freedom, whale-shrimp-dynamic, wonder-as-purpose, workflow-inversion, working-knowledge, world-model-as-agent-instruction`
- Concepts only in Parallel (workers=8, 52min): **120**
  - `action-rubric, action-tier-hierarchy, agency-model-for-work, agent-dormancy, ai-farm, ai-harness, assembled-context-retrieval, asset-bubbles, attention-as-path-determinant, brand-as-surrogate-community, brand-purpose-signaling, brand-vs-business, browser-agent-architecture, business-cycle-leading-indicators, capability-portfolio-control-layer, capability-portfolio-management, church-as-process-orientation, configuration-friction, consequence-weighted-action-gate, consumer-cooperative-power, consumption-to-resurfacing-loop, context-cost-ladder, context-injection-retrieval, context-write-back-gap, conversational-polling, credit-assignment-problem, debt-deflationary-cycle, degradation-of-digital-communication, dynamic-psychology-policy-weighting, dynamic-tool-discovery, ego-shedding-for-higher-cause, energy-as-master-variable, engine-not-product, extended-mind, extraverted-sensing-se-development, fascia-breathing-addiction-loop, food-system-excellence, four-hour-deep-work-rhythm, generative-synthesis-vs-discriminative-classification, goal-controller, good-regulator-theorem, hub-and-spoke-architecture, human-on-the-loop, ideal-and-its-expressions, information-diet, information-saturation-lag, innovation-vs-invention, intelligent-browsing, intent-first-interfaces, intent-layer-for-ambient-computing, intention-behavior-gap, introverted-intuition-ni, introverted-sensing-si, invisible-value-problem, kairos-architecture, knowledge-vs-working-knowledge, kuzu-memory, llm-product-retrofit-mistakes, llm-wiki-pattern, lost-in-the-middle, lsm-compaction, mape-k-loop, market-psychology, markets-psychology-vs-physics, memex-vision, mental-load-reduction, mikai-l4-state-machine, missionary-mindset, moat-as-integration-assembly, ni-over-reliance-in-trading, oapi, outcome-first-ai, ownership-vs-final-say, passion-vs-contribution, phase-change-materials-thermoregulation, picks-and-shovels-thesis-failure, plan-and-execute-pattern, plenitude-of-distraction, pm-translation-layer, positive-reinforcement, proactive-personal-intelligence-feed, project-state-graph-vs-cognitive-state-graph, push-vs-pull-architecture, reflective-router, relational-space, requisite-variety, retail-incubation-pipeline, return-skewness, sales-first-execution, sandwich-feedback, scientist-identity, second-brain-strata, seven-stage-skill-pipeline, shared-memory-blocks, skills-vs-tools-taxonomy, snapshot-architecture, space-between, stated-strategy-vs-revealed-configuration, substrate-beneath-surfaces, substrate-vs-destination, sumimasen, systems-change-autofill, taoism-entrepreneurship-duality, technology-externalization-ladder, technology-philosophy-harmonization, tenacious-joy, tensions-released-through-expression, thread-state-machine, three-pillars-of-wellbeing, three-selfs-taxonomy, time-model, time-triggered-vs-context-triggered-resurfacing, trap-door-effect, upper-lower-cross-syndrome, value-creation-vs-impact-creation, viable-system-model, vigilance-vs-creativity, visionary-vs-executor, whale-shrimp-dynamics, world-model-progression`
- Semantically-adjacent pairs across the two sides (substring or shared ≥4-char token): **262**
  _If most of the "only in" concepts pair up here, the apparent concept-count difference is mostly re-slugging, not genuine consolidation._

  | Serial (workers=1, 5h20m) | Parallel (workers=8, 52min) | reason |
  |---|---|---|
  | `addiction-vs-passion` | `fascia-breathing-addiction-loop` | shared:addiction |
  | `addiction-vs-passion` | `passion-vs-contribution` | shared:passion |
  | `agency-career-model` | `agency-model-for-work` | shared:agency,model |
  | `agency-career-model` | `time-model` | shared:model |
  | `agency-career-model` | `viable-system-model` | shared:model |
  | `agency-career-model` | `world-model-progression` | shared:model |
  | `agent-harness` | `agent-dormancy` | shared:agent |
  | `agent-harness` | `ai-harness` | shared:harness |
  | `agent-harness` | `browser-agent-architecture` | shared:agent |
  | `ai-development-phases` | `extraverted-sensing-se-development` | shared:development |
  | `ai-public-information-mediation` | `information-diet` | shared:information |
  | `ai-public-information-mediation` | `information-saturation-lag` | shared:information |
  | `ambient-computing` | `intent-layer-for-ambient-computing` | substring |
  | `atomic-actionable-feed-card` | `proactive-personal-intelligence-feed` | shared:feed |
  | `attention-anchors` | `attention-as-path-determinant` | shared:attention |
  | `attention-as-injection-constraint` | `attention-as-path-determinant` | shared:attention |
  | `attention-as-injection-constraint` | `context-injection-retrieval` | shared:injection |
  | `attention-economics` | `attention-as-path-determinant` | shared:attention |
  | `bdi-agent-theory` | `agent-dormancy` | shared:agent |
  | `bdi-agent-theory` | `browser-agent-architecture` | shared:agent |
  | `behavioral-trace-memory` | `kuzu-memory` | shared:memory |
  | `behavioral-trace-memory` | `shared-memory-blocks` | shared:memory |
  | `bidding-lease-system` | `food-system-excellence` | shared:system |
  | `bidding-lease-system` | `viable-system-model` | shared:system |
  | `bilt-four-phase-agent-architecture` | `agent-dormancy` | shared:agent |
  | `bilt-four-phase-agent-architecture` | `browser-agent-architecture` | shared:agent,architecture |
  | `bilt-four-phase-agent-architecture` | `four-hour-deep-work-rhythm` | shared:four |
  | `bilt-four-phase-agent-architecture` | `hub-and-spoke-architecture` | shared:architecture |
  | `bilt-four-phase-agent-architecture` | `kairos-architecture` | shared:architecture |
  | `bilt-four-phase-agent-architecture` | `phase-change-materials-thermoregulation` | shared:phase |
  | `bilt-four-phase-agent-architecture` | `push-vs-pull-architecture` | shared:architecture |
  | `bilt-four-phase-agent-architecture` | `snapshot-architecture` | shared:architecture |
  | `brand-as-identity-substitute` | `brand-as-surrogate-community` | shared:brand |
  | `brand-as-identity-substitute` | `brand-purpose-signaling` | shared:brand |
  | `brand-as-identity-substitute` | `brand-vs-business` | shared:brand |
  | `brand-as-identity-substitute` | `scientist-identity` | shared:identity |
  | `browser-as-primary-capture-surface` | `browser-agent-architecture` | shared:browser |
  | `capture-loop-wedge` | `consumption-to-resurfacing-loop` | shared:loop |
  | `capture-loop-wedge` | `fascia-breathing-addiction-loop` | shared:loop |
  | `capture-loop-wedge` | `human-on-the-loop` | shared:loop |
  _(truncated at 40; 222 more pairs)_

## Wisdom capture (ship-gate criterion: ≥5 attributed quotes per page)

| stat | Serial (workers=1, 5h20m) | Parallel (workers=8, 52min) |
|------|---------|---------|
| Wisdom pages | 15 | 16 |
| Total attributed quotes | 101 | 106 |
| Median quotes/page | 7 | 6.5 |
| p90 quotes/page | 8 | 9 |
| Weak pages (< 5 quotes) | 0 | 2 |
| Pages with zero attribution | 0 | 0 |

- Parallel (workers=8, 52min) weak pages: `avoidance-and-self-knowledge, potential-and-actualization`

## Qualitative side-by-side (3 shared sources: light / medium / heavy)


### Sample — `2024-07-10-july-2024-1b5fde.md` (light, 0.6KB)

**Serial (workers=1, 5h20m) source-summary body (first 2500 chars):**

```
# July 2024 Journal Entry (July 10)

A study note cataloguing options strategies and investment themes under active investigation. The entry is definitional rather than experiential — strategies are matched to volatility regimes, and several are flagged for further study.

## Investment Themes of Interest

- Commodities: Energy, Lithium
- Cloud Compute Supply Chain / [[concepts/infrastructure-as-a-service]]
- Real Estate Supply Chain
- Sourcing picks / screeners (process tool)

## Options Strategies

| Strategy | Volatility Regime | Key Characteristic |
|----------|------------------|--------------------|
| [[concepts/iron-condor]] | Range-bound, low volatility | Sells OTM call spread + OTM put spread |
| [[concepts/long-straddle]] | Increasing volatility | Buys call + put at same strike |
| [[concepts/bull-call-spread]] | Moderate directional | Caps upside; cheaper premiums |
| [[concepts/calendar-spread]] | *Under study* | Near-term sell, longer-dated buy |

## Volatility Concepts

- **[[concepts/relative-vs-absolute-volatility]]:** Open question noted explicitly.
- **[[concepts/beta]]:** Defined as benchmarked volatility relative to the S&P 500.

## Study Status

Calendar Spread is explicitly marked "further study needed." The directional bias framing of the Long Straddle may indicate interest in a skewed straddle or risk reversal rather than a pure straddle — ambiguity worth tracking.

## Connections

This entry continues the trading-knowledge arc begun in earlier journal entries. See [[sources/2024-07-08-july-2024-1b5fde]] for the adjacent entry from the same study period. These strategies are building blocks toward [[goals/systematic-trading-process]].
```

**Parallel (workers=8, 52min) source-summary body (first 2500 chars):**

```
# July 2024 Apple Notes — Options Strategies and Thematic Investing

Personal study notes from July 2024 cataloguing four options strategies and a set of thematic macro investment buckets. Evidence strength is low — these are declarative notes with no citations or data.

## Thematic Investment Themes

The author identifies several sector-level themes as frameworks for stock sourcing:

- **Commodities**: Energy, Lithium
- **Cloud Compute Supply Chain / IaaS** (infrastructure-as-a-service)
- **Real Estate Supply Chain**

Stock screeners and sourcing methods are flagged as a next operational step, without naming specific tools.

## Options Strategy Taxonomy

Four strategies are catalogued, each paired with a market condition:

| Strategy | Market Condition | Notes |
|---|---|---|
| [[concepts/iron-condor]] | Range-bound, low volatility | Sell OTM call spread + OTM put spread |
| [[concepts/long-straddle]] | High volatility, no directional bias | Buy call + put at same strike |
| [[concepts/bull-call-spread]] | Moderately bullish | Caps profit; cheaper premiums |
| [[concepts/calendar-spread]] | — | Further study needed |

## Conceptual Gap: Relative vs. Absolute Volatility

The author pauses to ask: *what is relative volatility vs. absolute volatility?* A partial answer is given — [[concepts/relative-vs-absolute-volatility]] — identifying Beta benchmarked to SP500 as the relative volatility measure. This conflates directional co-movement (Beta) with relative volatility more precisely defined (e.g., implied vol ratios or realized vol comparisons). See [[queries/what-is-relative-vs-absolute-volatility]] for the open question.

## Connections

- Extends the trading methodology thread from [[sources/2023-05-04-may-2023-af1a10]]
- Directly supports [[goals/build-trading-checklist]] — the options taxonomy is exactly the kind of vocabulary a checklist encodes
- Thematic macro buckets relate to the finance side of [[goals/career-synthesis-finance-ai]]
```

**Concept pages attributed to this source**

- Serial (workers=1, 5h20m): `beta, bull-call-spread, calendar-spread, infrastructure-as-a-service, iron-condor, long-straddle, relative-vs-absolute-volatility`
- Parallel (workers=8, 52min): `bull-call-spread, calendar-spread, iron-condor, long-straddle, relative-vs-absolute-volatility`

**Wisdom pages attributed to this source**

- Serial (workers=1, 5h20m): `—`
- Parallel (workers=8, 52min): `—`


### Sample — `2026-07-15-claude-as-an-executive-assistant-platform-45e405.md` (medium, 39.3KB)

**Serial (workers=1, 5h20m) source-summary body (first 2500 chars):**

```
# Claude as an Executive Assistant Platform

An 18-turn thread (2026-07-15 → 2026-08-06) examining whether Claude's subscription tier can power an executive assistant and command-centre use case. Covers Anthropic's June 2026 Agent SDK credit change, the three-way proactive briefing race (Pulse, Orbit, Gemini), the IG "company brain" architecture, the five-strata second brain framework, the read-it-later category bifurcation, and Hermes deployment economics on Anthropic Max.

## Context

The thread originates from a practical frustration: a Max subscriber wants a proactive notification system — one that understands wiki state, task priority, and time — and needs to know whether subscription credits or raw API costs are the right infrastructure choice. The thread expands into structured analysis of the full proactive AI landscape, the "second brain" genre, read-it-later category consolidation, and Hermes family deployment.

## Key Findings

### 1. Subscription and API as Intentional Dual Surfaces

Anthropic's June 15, 2026 [[agent-sdk-credit-system]] change resolved the subscription-vs-API cost question: subscription plans now bundle a separate monthly Agent SDK credit ($20 Pro / $100 Max 5x / $200 Max 20x) covering programmatic and harness use. This is a deliberate prototyping tier alongside the production API key tier. A D-026-style architecture (deterministic scoring, LLM only at synthesis) fits comfortably within the Max credit and is unlikely to overflow to raw API pricing.

### 2. The Three-Way Proactive Briefing Race

[[chatgpt-pulse]] (OpenAI, September 2025), [[claude-orbit]] (Anthropic, May 2026 research preview), and Gemini Proactive Assistance have all converged on the morning briefing card as the primary proactive form factor. All three share the same structural defect: nightly re-derivation of relevance from connector data with no persistent task-state model. Pulse's acknowledged failure mode — reminding users of already-completed projects — is a direct symptom of stateless re-derivation. The [[second-brain-five-strata]] Prefrontal Layer (S3) is empty in every platform-scale briefing product.

### 3. The IG "Company Brain" Is L1 in L5 Costume

The viral Instagram "AI agents as company" + "second brain" format reduces to: a root context file loaded once, 137 SKILL.md files organized into 7 folder-namespaces named as an org chart, Claude Code as the runtime, and a TTS layer for delivery. The constellation visualization implies a knowledge graph t
```

**Parallel (workers=8, 52min) source-summary body (first 2500 chars):**

```
# Claude as an Executive Assistant Platform

An 18-turn conversation thread spanning 2026-07-15 to 2026-08-06. The inciting question is whether a Claude Max subscription can power an external notification and executive-assistant system without incurring raw API costs. The thread expands into a competitive landscape analysis of proactive AI briefing products, a structural critique of the Instagram "second brain" and "AI company in a box" demos, and a formal decomposition of the read-it-later function. First mention of MIKAI L5 as an Executor Stage appears here.

## Key Findings

### Agent SDK Credit System resolves the cost dilemma
Anthropic's June 15, 2026 policy change bundled a monthly Agent SDK credit into subscription plans — $20 on Pro, $100 on Max 5x, $200 on Max 20x — covering headless `claude -p`, third-party harnesses such as [[entities/openclaw]] and [[entities/hermes-agent]], and Claude Code. For a D-026-style architecture (deterministic scoring, LLM reserved for synthesis and NLG), a Max credit pool is unlikely to be exhausted. See [[concepts/agent-sdk-credit-system]] for details; note the dollar figures are dated June 2026 and subject to change.

### Proactive briefing space: no competitor has a task-state model
[[entities/chatgpt-pulse]] (September 2025) and [[entities/claude-orbit]] (May 2026 research preview) both operate via nightly re-derivation of relevance from connector data. Pulse's admitted failure mode — resurfacing already-completed projects — is a direct symptom of the absent state machine. This validates MIKAI's L4 thesis while leaving that layer unbuilt by the labs. See [[concepts/thread-state-machine]].

### Instagram "second brain" demos are L1 wearing an L5 costume
The "137 agents across 7 directors" are 137 markdown skill files in 7 folders. Memory is a load-once snapshot with no ingestion loop and no proactive channel. The constellation visualization implies a knowledge graph that does not exist. The posts are a paid Fish Audio partnership and a waitlist lead-gen. Architecture is Claude Code (interactive CLI) + flat context files + TTS API. See [[concepts/snapshot-architecture]] and [[entities/openclaw]] for pattern lineage.

### The read-it-later category is undergoing an extinction event
Pocket shut down mid-2025. The surviving form is MCP-native: Burn 451, Readplace, and Noverload expose native MCP servers, making save-piles available as agent context rather than as standalone apps. Readwise Reader is the most polished
```

**Concept pages attributed to this source**

- Serial (workers=1, 5h20m): `agent-sdk-credit-system, deferred-cognition-with-preserved-intent, second-brain-five-strata, skill-routing-taxonomy, snapshot-brain-vs-continuous-ingestion`
- Parallel (workers=8, 52min): `agent-sdk-credit-system, deferred-cognition-with-preserved-intent, second-brain-strata, snapshot-architecture, sumimasen, thread-state-machine`

**Wisdom pages attributed to this source**

- Serial (workers=1, 5h20m): `—`
- Parallel (workers=8, 52min): `—`


### Sample — `2026-03-20-llm-best-use-case-competitive-positioning-0419ac.md` (heavy, 138.0KB)

**Serial (workers=1, 5h20m) source-summary body (first 2500 chars):**

```
# LLM Best Use Case and Competitive Positioning

A 28-turn Claude thread spanning 2026-03-20 to 2026-06-21. Brian queries MIKAI's knowledge graph for competitive positioning, probes how MIKAI differs from Claude's Cowork and connector features, then extends into multi-agent orchestration architecture, the Bilt/Letta production case study, an eight-mistake taxonomy for LLM product development, ambient computing infrastructure, and a skills-vs-tools conceptual taxonomy. Two artifacts were produced: `MIKAI_AI_Ecosystem_Intelligence.md` (Turn 008 ecosystem primer) and `MIKAI_Session_Summary_Thread_Insights.md` (Turn 028 dense export).

## Market Context

- AI agent market: $5.1B (2024) → $47.1B (2030), 44.8% CAGR
- Anthropic: ~40% enterprise LLM spend (up from ~12% two years prior); OpenAI dropped from ~50% to barely 25%
- Gartner: 1,445% surge in multi-agent system inquiries, Q1 2024 → Q2 2025
- GPT-3.5 inference cost: $20/million tokens (late 2022) → $0.07 (late 2024); 280× reduction in 18 months
- 24 of top 30 documented agents released or received major agentic updates in 2024–2025
- [[model-context-protocol]]: 20 of top 30 agents support it; OpenAPI spec donated to [[agentic-ai-foundation]], December 2025

## MIKAI Competitive Positioning

The thread diagnoses the memory and context layer as "significantly under-built" across the ecosystem. MIKAI's moat is the [[personal-intent-graph]] — typed epistemic relationships (see [[epistemic-edge-vocabulary]]) that are portable across AI surfaces and compound over time. This distinguishes it from:

- **Granola**: live conversation capture, invisible — ambient capture commoditizes
- **Mem0**: memory layer for agents, developer-facing; does fact extraction but misses intent modeling
- **Mem.ai**: beautiful capture, still fundamentally a notes app
- **Howie**: narrow scope, real PMF
- **[[graphiti]] (Zep)**: temporal graph engine, closest to MIKAI's edge model — but uses factual-relational edges, not epistemic
- **Claude Cowork/connectors**: capability extensions, session-scoped; structurally different axis from MIKAI's persistent, portable user modeling

Active tension: portability as moat ↔ iPhone convergence thesis (iPhone's power came from lock-in). Explicitly unresolved.

Quarterly risk: if Anthropic ships deep personalization natively, MIKAI differentiation narrows. Flagged for quarterly revisit.

## MPM vs. MIKAI vs. OMC

The thread clarifies three non-overlapping tools:

- **[[claude-mpm]]**: project-state
```

**Parallel (workers=8, 52min) source-summary body (first 2500 chars):**

```
# LLM Best Use Case — Competitive Positioning (March–June 2026)

A 28-turn Claude conversation (2026-03-20 → 2026-06-21) analyzing MIKAI's competitive positioning within the AI agent landscape. The thread spans three major arcs: (1) MIKAI strategy and competitor mapping with a six-lens cross-disciplinary analysis of AI agents; (2) multi-agent orchestration state-of-the-art, MPM vs. OMC, MIKAI vs. the graph memory ecosystem, Bilt/Letta case study, and the LLM paradigm shift; (3) zero-configuration ambient agent infrastructure, skills vs. tools taxonomy, eight LLM product retrofit mistakes, and MIKAI architecture validation.

## Key Claims

1. MIKAI's moat is the [[epistemic-edge-vocabulary]] + passive behavioral input layer — no current shipped tool combines both.
2. MIKAI's three-role LLM design (Track A extraction, terminal desire synthesis, natural language delivery) is architecturally correct against all eight [[llm-product-retrofit-mistakes]] patterns.
3. The retrieval decision — what to inject into context — is the highest-leverage engineering surface in the MIKAI system, more important than the content itself. See [[context-injection-retrieval]].
4. MIKAI's [[personal-intent-graph]] is the missing layer separating current dynamic discovery (2025) from genuine ambient computing (2026+); without it, the user still has to ask.
5. LLMs are the intelligence layer that finally makes IBM's 2001 [[autonomic-computing]] vision achievable.
6. [[claude-mpm]] and [[oh-my-claude-omc]] solve adjacent but distinct problems; [[teammatetool]] is the likely canonical native primitive.
7. MPM's kuzu-memory is a project state graph; MIKAI is a cognitive state graph — different observation target, input method, edge type, and inference goal. See [[project-state-graph-vs-cognitive-state-graph]].
8. [[bilt]]/[[letta]] architecture proves [[agent-dormancy]] as the core cost lever at scale.
9. [[plan-and-execute-pattern]]: ~10× cost difference between frontier supervisor and cheap worker.
10. [[lost-in-the-middle]]: MIKAI's injection format and ordering matter as much as content.
11. [[picks-and-shovels-thesis-failure]]: Anthropic's 40% enterprise LLM spend is trust/safety framing, not model capability alone.
12. LLMs break the previous AI paradigm: ambiguity resolved at inference, not pre-processed upfront. See [[generative-synthesis-vs-discriminative-classification]].
13. MCP Registry OpenAPI specification donated by Anthropic to [[agentic-ai-foundation]], December 2025;
```

**Concept pages attributed to this source**

- Serial (workers=1, 5h20m): `ambient-computing, attention-as-injection-constraint, autonomic-computing, bilt-four-phase-agent-architecture, dormant-agent-model, epistemic-edge-vocabulary, general-manager-agent, inscription-gap, intelligence-vs-judgment-work, llm-product-development-mistakes, model-context-protocol, obligatory-passage-point, personal-intent-graph, skills-vs-tools-distinction, workflow-inversion, zero-configuration-ambient-agent-infrastructure`
- Parallel (workers=8, 52min): `agent-dormancy, autonomic-computing, configuration-friction, context-injection-retrieval, conversational-polling, dynamic-tool-discovery, engine-not-product, epistemic-edge-vocabulary, generative-synthesis-vs-discriminative-classification, human-on-the-loop, inscription-gap, intent-layer-for-ambient-computing, kuzu-memory, llm-product-retrofit-mistakes, lost-in-the-middle, obligatory-passage-point, personal-intent-graph, picks-and-shovels-thesis-failure, plan-and-execute-pattern, project-state-graph-vs-cognitive-state-graph, shared-memory-blocks, skills-vs-tools-taxonomy, substrate-beneath-surfaces, technology-externalization-ladder, zero-configuration-ambient-agent-infrastructure`

**Wisdom pages attributed to this source**

- Serial (workers=1, 5h20m): `—`
- Parallel (workers=8, 52min): `—`


## Confound ledger

_Same code, same corpus, same template. Only variable: `--workers 1` vs `--workers 8`._

| # | confound | affected surface | status |
|---|---|---|---|
| 1 | LLM nondeterminism (`claude -p` has no temperature/seed) | any measure of exact overlap | inherent; ~7% baseline Jaccard applies |
| 2 | Warm-index effect (serial sees accumulated wiki, parallel workers don't) | concept consolidation vs fragmentation | **phenomenon under study**, not a confound |
| 3 | 1 source dropped from serial vault | source coverage | flagged in coverage section; parallel is superset there |
