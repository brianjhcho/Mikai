# R2 Headless-vs-Claude.ai QA Comparison

- **Date**: 2026-08-27
- **Vaults tested**: parallel (`wiki-mikai-parallel-test`), serial (`wiki-mikai-new`)
- **Lane C**: paste Claude.ai MIKA TECH project answers manually into the placeholder cells
- **Command**: `claude -p --tools ""` in each vault's `wiki/` dir (subscription-safe, no MCP)

## Q1. What is the Sumimasen intervention pattern and where does it apply?

### Lane A/B (parallel)

```
## Sumimasen — the intervention pattern

**Core principle** (`concepts/sumimasen`): a delivery gate in which "an AI system earns the right to interrupt by demonstrated utility rather than interrupting on a fixed schedule. Named after the Japanese expression of polite apology/excuse-me — the AI announces itself only when it has genuine cause."

It is defined as **the structural inverse of HEARTBEAT.md / cron-based proactivity**: where OpenClaw's HEARTBEAT.md surfaces items *because the clock advanced*, Sumimasen surfaces items *because thread state changed and the change clears a utility threshold*. `concepts/sumimasen` frames each interruption as "a debit that must be covered by demonstrated relevance," and names ChatGPT Pulse's resurfacing of completed projects as the HEARTBEAT failure mode at platform scale.

### Why the pattern exists
`concepts/interruption-asymmetry` supplies the justification: "one bad interrupt costs more trust than many good silences earn" — the invariant that killed Clippy, Google Now, and MyLifeBits. Its prescribed response is a **dismiss-rate gate** ("gate on dismiss rate, not on confidence" — confidence scores are model-internal and poorly calibrated), and it states plainly that "`sumimasen` is its current implementation." `concepts/five-lineages-of-memory` routes the same failure mode to the same answer.

### How it's implemented
Two concrete specifications appear in the wiki:

- **Deterministic V1 rules** (`sources/2026-04-02-agent-memory-640e67`, "Sumimasen Gate Rules (V1)"): "48h cooldown per thread, 7–30d stall window, recency filter, cross-source boost, cap 5/cycle. Deterministic rules only at V1." The corresponding 90-day roadmap gate is "dismiss rate <30% for 14 days."
- **Strict intervention contract at the LLM layer** (`concepts/strict-intervention-contract`, from the MVP build in `sources/2026-08-02-ai-as-a-conversational-research-partner-dec921`): the model defaults to `{"interject": false}` and may only return `true` for three enumerated triggers — (1) an unanswered factual question, (2) a materially wrong factual claim, (3) a conversational stall caused by missing knowledge. Upstream of that sits **reticence control** (~14+ new words and ~2.6 s of silence before Claude is even queried), so false positives are cut before they reach the model.

### Where it applies
1. **Its home layer — MIKAI S4/L4.** `concepts/second-brain-strata` places Sumimasen at S4, the Thalamus / delivery-gate layer, dependent on S3 (`concepts/thread-state-machine`) having classified thread state first. `concepts/thread-state-machine` lists "delivery policy — when interrupting earns its trust cost (the Sumimasen gate)" as the third thing the layer enables.
2. **Push vs. passive surfacing in the EA feed.** `concepts/proactive-personal-intelligence-feed` gates push behind "a high-confidence threshold called the **Sumimasen gate**" — with the threshold value explicitly still open (`queries/when-should-ea-feed-push-vs-surface`: fixed or adaptive? domain-varying? how to recover trust after a false positive?).
3. **Ambient conversational listening.** The café/car use case in the 2026-08-02 source — phone face-up, soft rin bell instead of speech, andon-style UI that "should not glow — it should only signal."
4. **Knowledge-base consolidation proposals.** `concepts/crystallization`: surface a merge proposal "only when redundancy AND confidence are both high, because false proposals erode trust asymmetrically." `sources/2026-07-04-consolidating-multiple-discussion-threads-c6ea03` calls every auto-proposal "a Sumimasen transaction: default to silence."
5. **Write permissions / autonomy.** `concepts/permission-ladder` applies the same threshold logic to write actions — lower the confidence bar, more autonomy, more trust-erosion risk if miscalibrated.
6. **Generalized to actuation.** `concepts/consequence-weighted-action-gate` extends the binary surface-or-silence decision (Tier 1, informational) across all three action tiers: `act iff expected_value(action) > reversibility_weight(tier) × confidence_threshold(tier)`, with Tier 3 (cyber-physical) requiring human-in-the-loop approval. `concepts/kairos-architecture` notes KAIROS implements the Tier 1 version as its act-or-stay-silent tick.
7. **Beyond MIKAI entirely.** `concepts/strict-intervention-contract` generalizes the contract to any ambient agent — meeting assistants that surface only action items, code-review agents that must find a specific defect class, notification agents that default to silence.

### Two notes on the wiki itself
- The slug is fragmented: `concepts/sumimasen` is the real page, but many pages link to a `[[concepts/sumimasen-gate]]` that doesn't exist as a file (`crystallization`, `log.md:250`, the 2026-07-04 sources). Same idea, two slugs.
- **Named open gap**: the 2026-08-02 source flags that always-on multi-party transcription "was treated as unproblematic. No consent or data-handling design was discussed" — a gap if Sumimasen moves past single-user.
```

### Lane A/B (serial)

```
I have enough to answer this from the wiki.

## The pattern

The wiki calls it the **Sumimasen gate** (`concepts/sumimasen-gate`) — named after the Japanese word for a polite, apologetic interruption. The rule:

> "**default to silence; surface a suggestion only when redundancy is high AND confidence is high.**" — `concepts/sumimasen-gate`

The justification is **asymmetric trust cost**: a false positive (interrupting when not warranted) "burns trust in the automation pipeline in a way that a missed suggestion does not." So interruption requires two conditions simultaneously true — high redundancy (a real threshold crossing, not marginal overlap) and high confidence in the detector. The gate deliberately runs on "cheap statistics before any LLM call," so it also functions as a cost filter.

The wiki notes this concept was invoked across MIKAI sources "as if already defined, but was never formally documented" — the concept page is its retroactive canonical definition.

## Where it applies

**1. Ambient conversation — the primary implementation.** `entities/sumimasen-app` is a React MVP that listens passively via Web Speech API and chimes rather than speaks. Concrete parameters: dual trigger of ≥14 new words *and* ≥2.3s silence, then ~1,600 chars sent to Claude under a three-condition intervention contract — interject only for (1) an unanswered factual question, (2) a materially wrong claim, (3) a stall on missing knowledge (`sources/2026-08-02-ai-as-a-conversational-research-partner-dec921`, which calls this thread "the **primary implementation** of that concept"). Reticence modes (Reserved / Balanced / Eager) tune the threshold.

**2. Thread consolidation.** In `concepts/triggered-compaction`, "Every auto-proposal is a [[sumimasen-gate]] transaction."

**3. MIKAI's proactive delivery layer.** This is the broadest application:
- `concepts/executive-assistant-feed` — the per-user interrupt threshold deciding push notification vs. wait; Noonchi's thread-state classification supplies the signal.
- `concepts/atomic-actionable-feed-card` — "only items that cleared the Sumimasen gate reach card format."
- `concepts/second-brain-five-strata` — S4 is the interruption filter implementing "Sumimasen-style utility gating."
- `concepts/interaction-conversion-metric` — the act/dismiss signal from the gate is "the only per-user, online, sparse training signal available."
- `entities/pocket` / `concepts/mikai-two-headless-stack` — Days 61–90 of the plan: a V1 *rule-set* (48h cooldown per item, 7–30 day stall window, recency filter, cap 5 surfaces per cycle), with dismiss rate >50% after Day 90 as the failure signal.

**4. Generalized to actuation.** `concepts/consequence-weighted-action-gate` extends it from attention-management to acting: `act iff E[value | action] > risk_weight(reversibility) × P(harm)`. "As agents gain actuators, the dismiss-rate gate becomes the consequence gate."

## Caveats the wiki itself flags

- It's the same family as JITAI and `concepts/timing-intelligence` — an interruption-worthiness decision.
- The rule-based version is explicitly "a starting gate, not the destination" (`concepts/context-triggered-vs-time-triggered-resurfacing`).
- Two open questions: per-user threshold calibration "is not a solved problem" (`synthesis/mikai-ea-feed-product-definition`), and the 5–20s latency in the app may miss the warm window entirely (`queries/does-sumimasen-latency-break-conversational-warmth`, called "the single largest hypothesis the MVP needs to validate").
```

### Lane C (Claude.ai MIKA TECH)

_(paste answer here)_

---

## Q2. What did Brian decide about mem.ai vs Obsidian for MIKAI's substrate?

### Lane A/B (parallel)

```
Short answer: **the wiki doesn't record a decision.** There's a detailed architectural comparison and two still-open questions, but no page where Brian picks mem.ai or Obsidian as MIKAI's substrate — and in fact neither is MIKAI's substrate today.

**What the files actually say:**

**Neither one is MIKAI's substrate.** `queries/what-infrastructure-is-right-for-mikai` states the current state plainly: "Memory substrate is Neo4j + Graphiti + Voyage AI running locally," on Tailscale + Docker. The open question there is local vs. cloud VM, not Obsidian vs. mem.ai.

**The comparison was framed as an argument about *justification*, not a product choice.** `comparisons/obsidian-vs-mem-ai` concludes: "Neither Obsidian nor Mem.ai addresses the write-heavy regime that MIKAI targets. Both systems are optimized for human sensemaking (read-heavy). MIKAI's typed graph is justified by closed-loop control requirements — bi-temporality, idempotent transitions, provenance — that neither of these systems can fulfill structurally." The source page `2026-08-01-obsidian-vs-mem-ai-graph-architecture-comparison-72932d` adds the design heuristic that came out of it: "Does anything downstream *act* on this assertion without a human reading it first? If no → markdown file. If yes → it has earned its type."

**The one live mem.ai question is narrower and unresolved.** `sources/2026-08-01-mem-ai-account-connection-21ea2f` ends on: "An open design question ... is whether Mem.ai should serve as MIKAI's primary write-back sink, given that Claude already has full CRUD access there." `log.md` (2026-08-27) logs the same thing as unsettled — "MIKAI comparison flagged as inferred (machine asleep); partially answers `queries/can-mikai-close-context-write-back-gap` in Mem.ai's favor" — because MIKAI's own tool manifest couldn't be enumerated at the time.

**The nearest thing to a decision** is a risk flag, not a substrate pick — `log.md`, same date: "Identified MIKAI strategic risk: typed-graph justification must rest on write-heavy/closed-loop requirements, not retrieval."

So: Obsidian-class markdown wins the read-heavy argument (`entities/obsidian`, `concepts/costly-signal-vs-cheap-signal`, `concepts/ontology-tax`), mem.ai holds a real write-back/attachment surface MIKAI hadn't matched (`concepts/attachment-intelligence`), and the choice between them for MIKAI is still open in these files.
```

### Lane A/B (serial)

```
## Short answer

The wiki doesn't record a decision by Brian choosing one tool as MIKAI's substrate. What it records is an **architectural conclusion about which regime each tool belongs to** — plus one question about mem.ai that is explicitly left open. I'll separate what's grounded from what isn't.

## What the pages do establish

**The substrate question is settled by regime, not by tool.** `concepts/read-mostly-vs-write-heavy-regime` states the split directly: it is "the decisive split that determines whether a lightweight markdown system or a typed knowledge graph is the appropriate substrate." Both Obsidian and mem.ai are placed on the *same* side of it — "Tools in this regime: `[[entities/obsidian]]`, `[[entities/mem-ai]]`, Notion, standard wikis" — i.e., read-mostly. MIKAI is placed on the other side, because a closed-loop goal controller needs bi-temporality, provenance, and idempotent state transitions that "plain markdown structurally cannot provide."

So the operative conclusion is: **neither is MIKAI's substrate.** `comparisons/obsidian-vs-mem-ai` says it explicitly — "This comparison defines the read-mostly baseline that MIKAI does not compete against."

**The scope rule that came out of it.** `concepts/control-loop-test` gives the decision rule: "Does anything downstream act on this assertion without a human reading it first?" No → plain markdown file. Yes → it earns a type. Stated consequence: "The typed graph should be exactly as large as the control loop and no larger."

**The strategic warning attached to it.** From `sources/2026-08-01-obsidian-vs-mem-ai-graph-architecture-comparison-72932d`: "If MIKAI justifies its typed layer with retrieval-flavored arguments ('better memory of what I know') in a market where markdown + Claude Code made retrieval free, it loses."

**On Obsidian specifically**, the finding is that it won on *substrate*, not graph — local markdown that outlives the company, zero lock-in, greppable by coding agents; "Obsidian sold files as the product and threw the graph in as a free view." Its graph view is "mostly a screenshot generator."

**On mem.ai**, `comparisons/mem-ai-vs-mikai-connector` notes the one capability it has that MIKAI lacks: bidirectional write access. "mem.ai is the only connector of the two that allows Claude to create, modify, or restructure content within a conversation."

## The one thing explicitly left undecided

That same page frames it as an **"Open Architectural Question"**, not a decision:

> "Should mem.ai be used as a write-back workaround for MIKAI — writing structured output into mem.ai notes when MIKAI's read-only constraint prevents persistence? This would partially compensate for the write-back gap at the cost of data fragmentation across two systems."

## Caveats worth carrying

- That connector comparison flags its own MIKAI column as **inferred, not verified** — MIKAI was offline over Tailscale during the source session, and the page asks for a re-run with a live tool enumeration.
- The source page's own evidence grading says the retrieval argument is "well-supported," but "the MIKAI-specific inferences are logical extrapolations from the framing, not empirically validated claims."
- One page is in mild tension with the others: `synthesis/mikai-metabolism-reframe-vs-retrieval-competitors` lists Mem.ai as "Acquired by ChatGPT / dissolved," while the August 2026 pages describe it as a live $12/month product with an active MCP connector. I can't resolve that from these files.

If you were expecting a recorded decision — e.g. "run the wiki on Obsidian, keep the typed graph for the control loop" — that specific commitment isn't written down anywhere I can find. The regime split and the control-loop test are the closest thing to it, and they're framed as analysis rather than as a choice Brian made.
```

### Lane C (Claude.ai MIKA TECH)

_(paste answer here)_

---

## Q3. How does the L4 task-state machine classify threads (exploring / decided / acting / stalled)?

### Lane A/B (parallel)

```
Here's what the wiki actually says, with one important caveat up front: **the pages describe the state vocabulary, the classification pipeline, and the mechanism candidates — but no page specifies the per-state decision rules** (e.g., what exactly distinguishes `exploring` from `evaluating`). Only `stalled` has a stated criterion.

## The state set

`concepts/mikai-l4-state-machine` gives the canonical lifecycle:

```
exploring → evaluating → decided → acting → stalled → completed
```

`entities/mikai` repeats it (with "deciding" instead of "decided" — a minor inconsistency between pages), and `concepts/timing-intelligence` lists the classification states as "exploring / evaluating / decided / acting / stalled."

Note your question's four-state framing is a subset — the wiki's machine has six states, including `evaluating` and `completed`.

There is also a **second, coarser** state model in the wiki: `concepts/thread-state-machine` classifies threads as **active / stalled / closed**, and `concepts/second-brain-strata` (S3, Prefrontal Layer) uses that same triple. These two pages aren't reconciled with the six-state version anywhere I can find.

## How classification runs

Per `concepts/intention-behavior-gap`, the noonchi retrieval chain is:

1. `get_stats` (orient)
2. `search_graph`
3. `expand_graph` (hops=1)
4. **Classify thread state:** exploring / evaluating / decided / acting / **stalled**
5. Surface the gap
6. Infer one concrete next step

Output format: `THREAD / STATE / LAST ACTIVITY / GAP / NEXT STEP`. `mikai-l4-state-machine` compresses this to **detect thread → classify state → infer next step**, and says the same pipeline runs at both ends of the instruction-density axis (explicit button-press vs. zero-density "shoe stall") — entry point and action license differ, not the machine.

## What the classifier keys on

- **Vocabulary (O-035, resolved):** the activity vocabulary is the L4 spine — goal, constraint, candidate, comparison-criterion, **stall-point**, participant-preference. Epistemic structures (unresolved_tension, contradicts, depends_on) were discarded for this layer. Note `concepts/activity-vocabulary` is linked from several pages but doesn't exist as a file.
- **Mechanism (O-036, open):** the bet is **zero-LLM rule-based** classification (`entities/mikai`; D-026 zero-LLM principle in `concepts/thread-state-machine`). Whether it holds at scale is an open question; if it fails, typed relational edges may return.
- **`stalled` specifically:** `concepts/hawkes-process` is the only page giving a concrete criterion. Fit a self-exciting point process per thread over its episode stream; high λ(t) = `acting`, decay toward baseline μ = transition into `stalled`, and the 90th-percentile inter-event interval gives an expected-next-event threshold that "converts `stalled` from an arbitrary N-day window into a principled threshold." Stated limitation: intensity isn't comparable across reflective (journal) vs. transactional (Gmail, iMessage) sources, and no normalization strategy exists yet.

## Two things worth flagging

- **Accuracy:** `entities/mikai` and `sources/2026-04-02-agent-memory-640e67` record L4 state-classification accuracy at **18.5%** on the SQLite-era implementation, target ≥60% before user expansion.
- **What the states are for:** classification isn't the product — `thread-state-machine` separates state estimation from prioritization (importance × time-decay) and delivery policy (the Sumimasen gate). The stated competitive point is that ChatGPT Pulse and Claude Orbit have subproblem 3 but not 1 and 2, which is why Pulse reminds users of completed projects.

Sources: `concepts/mikai-l4-state-machine`, `concepts/thread-state-machine`, `concepts/intention-behavior-gap`, `concepts/timing-intelligence`, `concepts/hawkes-process`, `concepts/second-brain-strata`, `entities/mikai`, `sources/2026-06-18-task-state-awareness-2-0-b2f08c`, `sources/2026-05-13-task-state-awareness-375542`, `sources/2026-07-01-neural-networks-for-mikai-graph-inference-572b84`.
```

### Lane A/B (serial)

```
## Short answer

The wiki records **six** states, not four — the question's list is a subset. The canonical machine is:

```
exploring → evaluating → decided → acting → stalled → completed
```

That sequence appears verbatim in `sources/2026-06-18-task-state-awareness-2-0-b2f08c.md` under "L4 State Machine," and is repeated in `concepts/instruction-density-axis`.

## Where classification happens in the pipeline

Classification is **step 4 of a five-step retrieval procedure**, not a standalone module. From `concepts/noonchi-retrieval-chain`:

1. `get_stats` orient — baseline node count, recent ingestion, graph health
2. `search_graph` — semantic search across entities/episodes for the current concern
3. `expand_graph` 1-hop — surface adjacent entities, relationships, recent episodes
4. **Classify thread state** — "assign one of five states: exploring / evaluating / decided / acting / stalled"
5. Surface gap + infer next step

Note the discrepancy: the retrieval chain lists five states (dropping `completed`); the state machine lists six. The wiki doesn't reconcile this.

## What the classifier reads

The extraction vocabulary the classifier operates over is the six-term **activity vocabulary** (`concepts/activity-vocabulary`): `goal`, `constraint`, `candidate`, `comparison-criterion`, `stall-point`, `participant-preference`. `stall-point` is defined there as "a thread that has stopped progressing" — that's the only per-state definition the wiki gives. The other five states are named but never individually defined in these files.

Two mechanism claims are grounded:

- **Stall detection is absence-based.** `concepts/snapshot-brain-vs-continuous-ingestion`: "stall onset is the *absence of events* over an interval — detectable only in a continuous stream, not in a static file." This is why the architecture requires continuous ingestion rather than snapshots.
- **The stall threshold is meant to be statistical, not a fixed window.** `sources/2026-07-01-neural-networks-for-mikai-graph-inference-572b84` proposes a per-thread Hawkes process yielding "past the 90th percentile of this thread's inter-event interval — rather than an arbitrary N-day window."

## Design commitments around it

- **Engine is invariant to input quality.** `concepts/instruction-density-axis`: the same state machine handles the high-density "big red button" case and the zero-density inferred shoe-browsing case. Pipeline is always detect thread → classify state → infer next step.
- **Classification is intended to be rule-based (hypothesis O-036).** `concepts/activity-vocabulary` frames typed relational edges as a *fallback*: epistemic vocabulary returns as "L4 plumbing" only if rule-based classification fails. `entities/kairos` cites regex-based frustration detection as supporting evidence that state classification can run "at zero marginal LLM cost."
- **Classification feeds timing, not just retrieval.** `concepts/timing-intelligence`: the classification is the cognitive-state signal that converts into a push/hold decision for the EA feed — e.g. a thread that "classified as 'stalled' three days ago" combined with a calendar event.

## Two caveats from the files

`concepts/second-brain-five-strata` describes the S3 stratum — "the physical implementation of L4" — with a **different, four-state vocabulary**: "active, stalled, blocked, or completed." That doesn't match the six-state machine, and the wiki doesn't note the divergence.

None of these pages describe an implemented classifier — thresholds, transition rules, or evaluation results. `sources/2026-05-13-task-state-awareness-375542` gives only target acceptance criteria for the adjacent `thread_detection` capability (precision ≥0.80, recall ≥0.75, p95 latency 2000ms), and the O-036 test is listed there as an open question: "test not yet run."
```

### Lane C (Claude.ai MIKA TECH)

_(paste answer here)_

---

## Q4. What are the memory-architecture generations (pre-LLM through RAG through memory products) and where does MIKAI sit in that progression?

### Lane A/B (parallel)

```
Grounded in these wiki files. One framing note up front: the wiki doesn't lay this out as a single linear "generations" timeline. Its canonical frame is `concepts/five-lineages-of-memory` — five parallel lineages, each answering a different question, each of which the LLM era *replays* rather than supersedes. "Pre-LLM → RAG → memory products" maps onto that as a replay sequence, not a ladder.

## The pre-LLM lineages

From `concepts/five-lineages-of-memory` (sourced to `sources/2026-08-07-memory-architectures-across-software-history-fd56b8`):

| Lineage | Era | Question | Failure mode |
|---|---|---|---|
| 1 — Memory as Scarcity | 1945–1980s (Von Neumann → Atlas 1962 → Denning 1968) | Speed gap between processor and store | Doesn't fail — **commoditizes** |
| 2 — Memory as Record | 1960s–2010s (IMS → Codd 1970 → ARIES 1992 → BM25 1994 → HNSW 2016) | Store and retrieve facts at scale | Commoditizes on schedule |
| 3 — Memory as Meaning | 1966–2012 (Quillian → Minsky frames 1975 → Schank 1982 → Cyc → Knowledge Graph) | Represent what things *mean* | Knowledge-acquisition bottleneck; post-LLM, ontology fit |
| 4 — Memory as Function | 1885–1990s (Ebbinghaus → Miller → Tulving → ACT-R → Hearsay-II) | How biological memory works | Doesn't fail — commoditizes slowly, "math always available, rarely applied" |
| 5 — Memory as Agent | 1945–2012 (Memex → Remembrance Agent 1996 → Clippy 1997 → Horvitz → MyLifeBits → Google Now 2012) | Surface relevant info *proactively, unasked* | `concepts/interruption-asymmetry` — "the graveyard" |

The cross-cutting claim: "storage and query-triggered retrieval commoditize every generation (filesystems → databases → desktop search → RAG)," while "context-triggered judgment — what deserves attention right now — has never commoditized because it has never been solved."

## The RAG generation

The wiki treats RAG as Lineage 2 replayed, not as a new thing: "RAG is the IR pipeline with a reader stapled on," and it "was commoditized within 18 months of the LLM-era gold rush." The only genuinely new component in the LLM era is *the reader* — in-context learning (2020) "repriced all five lineages simultaneously."

`concepts/llm-wiki-pattern` marks the post-RAG move: "RAG rediscovers; the LLM Wiki compounds" — synthesis over retrieval, with the model as compiler rather than retriever.

## The memory-products generation

Also replay, mapped item by item: "MemGPT is paging. Letta blocks are frames. Zep is temporal databases. Scratchpads are blackboards. Dreaming is sleep replay plus log compaction."

Two product maps in the wiki:

- `synthesis/mikai-vs-agent-memory-ecosystem` — claude-mpm/kuzu-memory (project memory), graphiti-zep (temporal graph), mem0 (flat memory API), Mem.ai (notes). All are scoped to a session/project/conversation, all rely on explicit declarations, all use structural- or factual-relational edges.
- `concepts/second-brain-strata` coverage matrix (S1 capture → S5 execution) — "Mem0 / Zep / Cognee" score full marks on S2 Cortex and blank on S3/S4/S5.

`sources/2026-04-02-agent-memory-640e67` adds the consumer-side version of the same finding: Pocket, Instapaper, Readwise, Mem.ai, Rewind/Limitless, Notion AI each "solved capture or retrieval; no product has closed the full consumption-to-contextual-resurfacing loop."

## Where MIKAI sits

The wiki's position is explicit and is a *layer* claim, not a generation claim:

- **L1/L2/L3 — inherited and commoditizing.** "MIKAI's L1/L2/L3 tiering is this hierarchy borrowed consciously" (Lineage 1, via `concepts/admission-eviction-prefetch`). `entities/mikai` states flatly: "L3: Knowledge graph, preference/fact retrieval — commoditizing."
- **L4 — the structurally durable slot.** "L4 (context-triggered surfacing) remains the unsolved, structurally durable layer." Lineage 5 "stays stuck" because "the reader repriced reading, not deciding-when-to-speak." `concepts/second-brain-strata` makes the same claim as a table: "The empty S3 column across every non-MIKAI row is the core strategic claim: the state layer is the uncovered layer." MIKAI L1–L5 is the only row with all five strata filled.
- **The differentiator** (`synthesis/mikai-vs-agent-memory-ecosystem`): `concepts/epistemic-edge-vocabulary` (`supports`, `contradicts`, `partially_answers`, `unresolved_tension`) *plus* passive behavioral input. "Both must be present… No current shipped tool combines both."
- **The historical answer to the Lineage 5 failure mode**: `concepts/sumimasen` plus the dismiss-rate gate — "the historically derived answer to the interruption-asymmetry, validated by fifty years of Lineage 5 history."

Two counter-data points the wiki keeps in view rather than smoothing over: L4 state-classification accuracy at **18.5%** against a ≥60% gate (`entities/mikai`), and the **15-of-15,108 epistemic-edges** result, described as "direct local evidence that ontology-first lost to schema-on-read" — i.e., MIKAI hitting Lineage 3's own post-LLM failure mode.

The diagnostic the framework exists to support: "identify which lineage it descends from. That lineage's failure mode is the technique's failure mode."

One caveat on scope — `concepts/world-model-progression` also has a five-level ladder, but it's about agent *context quality* (prose → structured state → executable acceptance criteria), not memory-architecture history. Don't conflate the two.
```

### Lane A/B (serial)

```
I have what I need. Here's the picture the wiki actually holds.

## The generational story lives in two overlapping frames

The wiki doesn't use a single "generation 1..N" list. It has **two frames that answer your question from different angles**, plus a third that positions MIKAI.

### Frame 1 — Five lineages across 80 years (`sources/2026-08-07-memory-architectures-across-software-history-fd56b8`)

| Lineage | Era | Core question | LLM-era heir |
|---|---|---|---|
| 1 · Memory as scarcity | 1945–1980s | processor/store speed gap | MemGPT, context-window tiering |
| 2 · Memory as record | 1960s–2010s | log-as-truth, ranking under uncertainty | RAG, Graphiti episode store, Zep bitemporality |
| 3 · Memory as meaning | 1966–2012 | structured knowledge; died on knowledge-acquisition bottleneck | typed graphs over personal corpora |
| 4 · Memory as function | 1885–1990s | principled forgetting/attention (ACT-R) | deterministic relevance scoring |
| 5 · Memory as agent | 1945–2012 | context-triggered surfacing; died on trust every time | L4 / noonchi-style ambient surfacing |

The organizing claim of that page: *"everything sold as 'LLM memory' is a re-derivation of older patterns; the one genuinely new element is the reader."* And its sorting rule — **storage + query-triggered retrieval commoditizes every generation (filesystems → desktop search → RAG); context-triggered judgment never has, because it was never solved.**

### Frame 2 — Three generations of the Memex attempt (`concepts/three-generation-failure-pattern`)

This is the "pre-LLM" chain proper:

1. **Total capture (1990s–2010)** — MyLifeBits, Forget-Me-Not, Stuff I've Seen. Capture worked; sense-making failed. "Search over an unstructured life is just a smaller internet."
2. **Semantic infrastructure (1999–2008)** — WinFS, Semantic Web, NEPOMUK. Died on the **schema-on-write mandate**; the world declined to annotate.
3. **Early assistants (2003–2011)** — CALO → Siri, General Magic, Pattie Maes. Intent inference didn't work yet.

All three died of one missing organ: *a machine that could derive meaning from unstructured personal context without being told.* LLMs are that organ (`concepts/schema-on-read`).

### RAG's place in the progression

`concepts/query-triggered-retrieval` is blunt about it: RAG is IDF (1972) → BM25 (1994) → Salton's SMART → retrieve-then-read (2017 orthodoxy) with a neural reader bolted on. *"The LLM adds a reader at the end of the pipeline but does not change the underlying ranking problem."* Desktop search commoditized personal recall in ~2 years; RAG follows the same 2–3-year trajectory to table stakes.

### The memory-products generation

`concepts/knowledge-acquisition-bottleneck` explains the crowding: LLMs made text-to-structure cheap, so Lineage 3 revived instantly and *"the memory-infra market crowded within 18 months."* The wiki's competitive maps:

- `synthesis/mikai-metabolism-reframe-vs-retrieval-competitors` — Pocket, Instapaper, Readwise, Mem.ai, Rewind/Limitless, Hindsight, Notion AI/Obsidian, ChatGPT/Claude memory. **"Every prior product solved capture or retrieval; none solved the loop between consumption and contextual resurfacing."**
- `concepts/second-brain-five-strata` — the S1–S5 coverage matrix where **the S3 (thread state machine) column is empty for every row except MIKAI**: Mem0/Zep/Cognee have S1+S2 and nothing else; Pulse/Orbit have connectors and a time-triggered gate; OpenClaw has cron only.
- `entities/supermemory` — 81.6% LongMemEval vs 40–60% for standard RAG, yet *"adding Supermemory (or Mem0, Zep) does not meaningfully improve cross-platform state tracking beyond baseline RAG; the MEMTRACK result (60% for GPT-5) holds even with enhanced retrieval."*

## Where MIKAI sits

**At the end of Lineage 5 / Generation 4, not in the RAG generation.** The wiki's own one-line invariant, from `log.md` and invariant #4 of the source page: *"LLMs repriced extraction, not judgment — L3 crowded, L4 stayed empty."*

Concretely:

- **L3** (bitemporal graph, cross-source retrieval) is the substrate MIKAI shares with Graphiti/Zep-class infra — the commoditizing layer.
- **L4 / S3** (thread state machine: active/stalled/blocked/completed, intention-behavior gap) is the claimed unoccupied position. `concepts/context-triggered-surfacing` calls it *"simultaneously the hardest and most durable layer to occupy"* after an 80-year graveyard — Remembrance Agent (1996), Clippy (1997), MyLifeBits (2001), Google Now (2012) — where the failure mode is **interruption asymmetry** (one bad interrupt costs more trust than many good silences earn), not relevance technology.
- `concepts/memex` frames the whole thing: *"You are proposing the oldest unbuilt artifact in computing."*

## Two caveats the wiki states about itself

The source page flags its own tension: it frames context-triggered surfacing as both "died every attempt" and "the durable layer," and *"relies on trust as the sole failure mode without proving that prior attempts failed only on trust rather than on relevance modeling or latency."*

And the positioning is conditional, not achieved. `synthesis/mikai-metabolism-reframe-vs-retrieval-competitors` lists what's still unbuilt — attention weighting (Hindsight is ahead), browser/social ingestion, semantic context-matching beyond the Sumimasen rule-set V1, dismiss/act feedback instrumentation — and concludes: *"Under Option A this is rhetorical; under Options B or C it becomes architecturally true."* `comparisons/hermes-vs-openclaw-vs-mikai-memory` adds the other half: MIKAI has the bitemporal edges and passive cross-source ingestion, but "cannot execute or route — that is Hermes's job."
```

### Lane C (Claude.ai MIKA TECH)

_(paste answer here)_

---

## Q5. What is the noonchi concept and how does it differ from a standard notification system?

### Lane A/B (parallel)

```
## Noonchi

**Origin and name.** `entities/noonchi` — noonchi (눈치) is the Korean concept of "the subtle art of reading a room — sensing mood, intent, and unspoken context from ambient cues." It was first sketched in December 2025 (`journal/2025-12-08`) as an always-on passive AI listener acting as a project manager, whose differentiator from Notta was "prediction, not just transcription." The core prediction target was left open — *"and then what do we predict?"* (`queries/what-should-ai-listening-predict`, still unresolved).

**What it became inside MIKAI.** The concept was absorbed as MIKAI's L4 surfacing layer. Per `concepts/goal-controller`, MIKAI "is a goal controller whose state estimator is the intent graph, whose surfacing engine is implemented via [[entities/noonchi]] (ambient anticipation)." Its mechanism is a retrieval chain (`concepts/intention-behavior-gap`):

1. `get_stats` (orient) → 2. `search_graph` → 3. `expand_graph` (hops=1) → 4. classify thread state: *exploring / evaluating / decided / acting / **stalled*** → 5. surface the gap → 6. infer one concrete next step

There's a second, softer sense in `concepts/mental-load-reduction`: noonchi as "social reading" — an agent that reads social context and acts as an interpersonal intermediary, removing the user from the labor of social navigation. (That page links `[[concepts/noonchi]]`, but no such file exists in this wiki — only `entities/noonchi.md`.)

## How it differs from a standard notification system

`entities/mikai` states the negative definition directly: MIKAI is **"not a Notification Center (stateless, single-source queue)."** The differences the wiki draws out:

| Dimension | Standard notifications | Noonchi |
|---|---|---|
| Trigger | Clock/event arrival | Thread *state change* across sources |
| State | Stateless queue | L4 state machine: exploring → evaluating → decided → acting → stalled → completed (`entities/mikai`) |
| Scope | Single source | Cross-source synthesis (calendar + email + messages) |
| Detection target | "Something happened" | Intention-behavior gap — you signaled intent and never acted (`concepts/intention-behavior-gap`) |
| Delivery default | Push/interrupt | Feed (pull); push is the exception (`concepts/proactive-personal-intelligence-feed`) |
| Payload | An alert | The gap *plus one inferred concrete next step* |

Three specific mechanisms carry the distinction:

**1. Timing intelligence, not event arrival.** `concepts/timing-intelligence` calls this "the unsolved problem in all current executive assistant products as of mid-2026: knowing *when* to surface something, not just *what*." Data access is solved; synthesis isn't. An email about a contract becomes urgent depending on calendar proximity, days unanswered, and counterparty follow-up — "no single-source tool can detect this." Even Lindy AI, which connects Gmail + Calendar + iMessage, "defaults to scheduled digests rather than proactive moment detection."

**2. The Sumimasen gate.** `concepts/sumimasen`: "an AI system earns the right to interrupt by demonstrated utility rather than interrupting on a fixed schedule… the structural inverse of HEARTBEAT.md / cron-based proactivity." Each interruption is "a debit that must be covered by demonstrated relevance." V1 rules per `entities/mikai`: 48h cooldown per thread, 7–30d stall window, recency filter, cross-source boost, cap 5/cycle. The failure mode of the clock-based alternative is named concretely — ChatGPT Pulse resurfacing completed projects.

**3. Margin delivery over interrupt delivery.** `entities/remembrance-agent` (MIT, 1996, described in-source as "noonchi v0") establishes the ancestry: surfacing in a non-blocking channel means "an ignored result costs nothing — it is not a bad interrupt." Every Lineage 5 successor that swapped margin for interrupt (Clippy, Google Now) "lost the one property that made the Remembrance Agent survivable."

## Open, per the wiki

- The push threshold is undefined; `queries/when-should-ea-feed-push-vs-surface` says calibrating it needs a labeled dataset, a signal model, and a trust-erosion evaluation framework.
- `queries/when-does-ambient-surfacing-become-trustworthy` records the asymmetry — "one wrong-moment interruption… costs more in user trust than ten correct surfacings earn" — and asks explicitly: "What is [[entities/noonchi]]'s current confidence model?"
- `concepts/push-vs-pull-architecture` goes further and questions the premise: whether MIKAI's notification layer should be rebuilt from a pull spine entirely "remains explicitly unresolved."
- L4 accuracy was 18.5% on the SQLite-era implementation against a ≥60% target before user expansion (`entities/mikai`).
```

### Lane A/B (serial)

```
## The concept

"Noonchi" appears in the wiki in two related but distinct senses.

**1. The original product sketch** (`entities/noonchi`, from `sources/2025-12-08-dec-2025-acbf96`). The name derives from the Korean 눈치 — "the social intelligence of reading a room, sensing unspoken dynamics, and anticipating what is needed before it is asked." As sketched it was an AI meeting assistant: always-on listening and transcription (comparable to Notta), plus a "sumimasen" attention/interrupt mechanism, plus a **prediction layer** as the differentiator. That page marks the prediction mechanism as unresolved — `queries/what-differentiates-noonchi-from-notta` is the open question, and it lists four candidate readings (next action item / next speaker / next topic / what the user will need) with none chosen.

**2. The intent-inference engine.** By `concepts/noonchi-retrieval-chain`, noonchi has become "MIKAI's intent inference engine" — a five-step procedure over a personal knowledge graph: `get_stats` orient → `search_graph` → `expand_graph` 1-hop → **classify thread state** (exploring / evaluating / decided / acting / stalled) → surface gap + infer next step. It's meant to be encoded as a `mikai-noonchi` SKILL.md, delivering "60–70% of L4 behavior procedurally" (`concepts/skill-md`).

`sources/2026-07-04-organizing-june-notes-036361` records the arc between these: February = concrete sports-commentary app with live contextual awareness → September = generalized thesis about contextual AI awareness → November = "this is how AI gets embedded into our lives, like the iPhone." That source explicitly notes the retrieval-chain page "addresses only the retrieval mechanism" and doesn't capture the full arc.

## How it differs from a standard notification system

The wiki has no single page that stages this comparison directly, so the answer below is assembled from adjacent pages. Four differences are grounded in the files:

**Trigger is contextual state, not a clock or an event.** `synthesis/mikai-ea-feed-product-definition` is explicit: "**Delivery trigger:** Context signal (calendar event in N hours + unresolved email thread + noonchi state = 'decided/acting') crosses the Sumimasen gate threshold. Not a clock trigger. Not a user request." A standard notification fires when its source event occurs; noonchi fires when a *cross-signal synthesis* crosses a threshold.

**It models the user's cognitive state; notification systems don't.** The thread-state classification is the input that ordinary notifiers lack. `concepts/timing-intelligence` frames the gap: "Data access is solved... The bottleneck is not retrieval but the decision of when a piece of information clears the threshold for surfacing vs. being held." And on competitors: "Lindy AI surfaces on request; Reclaim AI and Superhuman operate on schedules. None detect that a specific email requires attention *right now because* of a calendar event in two hours and a related conversation thread that classified as 'stalled' three days ago."

**Default is silence, and the asymmetry is deliberate.** `concepts/sumimasen-gate` defines the gate as "default to silence; surface a suggestion only when redundancy is high AND confidence is high," named after the Japanese apologetic interruption because "any unsolicited proposal carries an implicit trust cost." `concepts/interruption-asymmetry` gives the underlying law: "One bad interrupt costs more trust than many good silences earn... users tolerate missed retrievals as neutral, but irrelevant interruptions as actively hostile." Standard notification systems optimize the opposite way — deliver everything, let the user filter.

**Output shape differs.** `concepts/atomic-actionable-feed-card`: one card = one item = one decision, with exactly act / defer / dismiss and enough context to decide without opening the source. "If timing intelligence is working, the user sees one high-signal card, not a ranked list of twenty."

## Two caveats the files themselves flag

- `concepts/context-triggered-surfacing` places noonchi in an "80-year graveyard" — Remembrance Agent (1996), Clippy (1997), MyLifeBits (2001), Google Now (2012) — all of which failed "not on relevance technology, but on trust." `entities/remembrance-agent` calls itself "effectively noonchi v0." So the difference from a notification system is precisely the axis on which every prior attempt died.
- The push/pull question is **unresolved**. `concepts/push-vs-pull-agent-architecture` argues a push architecture is "structurally an engagement optimizer" and imports the wrong goal function for MIKAI, proposing a hybrid that confines push to high-confidence, time-sensitive signals. Its resolution status as of 2026-06-17: unresolved. So "noonchi differs from a notification system" is currently a design intent, not a settled architecture.
```

### Lane C (Claude.ai MIKA TECH)

_(paste answer here)_

---

## Q6. Which neural network architectures beyond LLMs might MIKAI use for graph inference?

### Lane A/B (parallel)

```
The wiki answers this directly — the primary page is `sources/2026-07-01-neural-networks-for-mikai-graph-inference-572b84.md`, with four supporting concept pages.

## The framing

The wiki's core argument is that "graph neural networks" is the obvious but *wrong near-term answer*. Per `concepts/label-scarce-regime`, MIKAI has ~12,600 nodes, ~20–30 labeled threads planned for MEMTRACK, and one user — a regime "actively hostile to supervised deep learning." So the architectures split into a label-free near-term stack and a label-gated long-term stack.

## Near-term (no labels required)

**L3 / graphing layer — self-supervised structural graph embeddings** (`concepts/self-supervised-graph-representation-learning`):
- **node2vec** — biased random walks + skip-gram; captures local neighborhood (BFS-like) and structural roles (DFS-like) via hyperparameters p and q
- **Deep Graph Infomax (DGI)** — maximizes mutual information between local node representations and a global graph summary
- **Unsupervised GraphSAGE** — neighborhood feature aggregation trained via a link-prediction objective on the graph itself

These encode *where a node sits* rather than *what it means*, complementing Voyage's semantic embeddings. Their concrete payoff, per `concepts/structural-vs-semantic-embeddings`: replacing the hand-tuned FOUNDATIONS §3 `boost` constant (0.08→0.12) with a learned representation — "It collapses a high-dimensional structural signal into one number."

Also listed at L3: multi-scale semantic embedding at 128/256/512 with Reciprocal Rank Fusion, and possibly ColBERT-style late-interaction for short transactional segments.

**L4 / inference layer — Hawkes process**, called "the sleeper pick" (`concepts/hawkes-process`). Multivariate, fit per thread over its timestamped episode stream: λ(t) = μ + Σ_i φ(t − t_i). High λ(t) means `acting`; decay toward μ marks `stalled`; the 90th-percentile inter-event interval replaces an arbitrary N-day window. It's "essentially a zero-LLM statistical model," serving the O-036 design philosophy. Everything else: gradient-boosted trees (XGBoost/LightGBM) or rule-based, per D-026.

**Neural TPP upgrade path** — once parametric form is too rigid and volume exists: **RMTPP** (RNN over event history) and **Transformer Hawkes** (attention-based, better on long sequences).

## Long-term (unlocked by multi-user labels)

1. **Temporal Graph Networks — TGN (Rossi et al. 2020) and TGAT (Xu et al. 2020)** — described as "the architecturally correct model" for Graphiti's bitemporal graph, since every edge carries valid-time and transaction-time and edges are invalidated rather than deleted (726 invalidated edges noted). TGN maintains per-node memory updated by message-passing on each interaction; TGAT uses time-encoding plus attention over the temporal neighborhood. It would *unify* L3 structure and L4 temporal dynamics, currently handled as separate heuristics.
2. **Supervised GNN link prediction** — the ML-native form of the intention-behavior gap: a stated-intent node in Track A with no semantically-adjacent action node in Track B is "the edge that should exist but does not." Near-term this is a heuristic gated by the Hawkes-derived expected window.
3. **PPP RL loop** — already deferred per design spec.

## Two caveats the wiki flags

- **Source-voice mismatch (O-035):** Hawkes assumes a meaningful event stream, but reflective sources (journals) are sparse while transactional ones (Gmail, iMessage) are dense — intensity values aren't comparable across source types, and no normalization strategy is specified.
- **Feature creep:** "If rule-based heuristics hit the 80% target (O-036), the neural machinery is an upgrade path that may never be needed. Prove the baseline first."

The strategic conclusion in `concepts/label-scarce-regime`: "MIKAI's moat cannot live in the model architecture" — it lives in the accumulated graph structure and the feedback loop.
```

### Lane A/B (serial)

```
The wiki answers this directly — there's a dedicated source page, `sources/2026-07-01-neural-networks-for-mikai-graph-inference-572b84`, whose framing question is exactly yours: "beyond LLMs, which neural network architectures best serve MIKAI's graphing (L3) and inference (L4) layers?"

## The reframe: it's a data-regime question, not an architecture question

The source's central move is to reject the architecture menu and ask about data instead. MIKAI's scale — "~12,600 entities, ~20–30 planned labeled threads" — is "actively hostile to supervised deep learning" (`concepts/label-scarce-regime`). So the question becomes "which nets fit a label-scarce, temporally-driven regime today." The source calls the alternative **the GNN trap**: "The moat lives in the graph structure and feedback loop, not the model architecture."

## Fits now (label-free)

**Self-supervised graph representation learning — L3.** node2vec, Deep Graph Infomax, or unsupervised GraphSAGE (`concepts/self-supervised-graph-representation-learning`). These produce *structural* embeddings — topological position — complementary to Voyage's *semantic* embeddings. The payoff is specific: MIKAI currently hand-weights the hybrid ("embedding primary, graph connectivity secondary, boost 0.08→0.12"); structural embeddings let that weighting "be learned rather than manually calibrated" (`concepts/structural-vs-semantic-embeddings`).

**Classical Hawkes / temporal point process — L4.** The source's "sleeper pick." Each timestamped episode raises intensity λ(t), then decays, yielding "a principled stall threshold — 'past the 90th percentile of this thread's inter-event interval' — rather than an arbitrary N-day window." A handful of parameters, fits on minimal data, "essentially a zero-LLM statistical model."

Alongside these: multi-scale embedding at 128/256/512 tokens fused via RRF, and GBT/rule-based per D-026.

## Deferred to multi-user scale

**TGN / TGAT** are called "the architecturally correct future-state model" (`concepts/temporal-graph-networks`). The fit argument is that Graphiti's bitemporal graph — timestamped edges, invalidated rather than deleted, "726+ invalidated edges as illustrative volume" — "is exactly the data structure TGNs are designed for." They'd unify structure and temporal dynamics that heuristics currently handle separately.

**Supervised GNN link prediction.** `concepts/intention-behavior-gap-as-link-prediction` restates the moat in ML terms: a Track A intent node exists but the Track B fulfilling node is absent or its edge stale — "detect the edge that should exist but doesn't." Near-term that's a heuristic gated by the Hawkes window; the GNN is the scaled version.

The sequencing table: **Now** — RRF embeddings + node2vec/DGI + classical Hawkes + GBT; **Mid** — neural TPP (RMTPP, Transformer Hawkes); **Future** — TGN/TGAT + supervised GNN link prediction + PPP RL loop.

## Two caveats the wiki itself raises

The recommendations are conditional, not settled. **O-036** states it plainly: "Prove the rule-based + Hawkes baseline hits your 80% target before reaching for anything trained. If the heuristics clear the bar, the neural graph machinery is an upgrade path you may never need to walk."

And the Hawkes pick has an unresolved tension across pages. The **O-035 bump** notes transactional sources (Gmail, iMessage) yield dense event streams while reflective sources (journaling) yield sparse ones — "Hawkes may work well for transactional threads and poorly for reflective threads, which may be among the most important to track." `concepts/temporal-point-process` pushes further, warning MIKAI's intent space "may be too heterogeneous and novel for the formalism to fit cleanly," violating stationarity assumptions. The source flags an event-density audit as the gate on this.

Worth noting on epistemic status: the source states outright that "all claims are architectural and theoretical. No benchmarks, ablations, or MIKAI-specific experiments are cited" — confidence is "strong theoretical fit," not demonstrated performance. `concepts/neural-network-taxonomy` and `entities/pytorch-geometric` give the broader family map and name PyG as the current standard library, but the concrete MIKAI recommendations all trace to the one 2026-07-01 thread.
```

### Lane C (Claude.ai MIKA TECH)

_(paste answer here)_

---

## Q7. What are Peter Thiel's monopoly mechanisms and how do they apply to MIKAI's positioning?

### Lane A/B (parallel)

```
## The mechanisms (from `concepts/thiel-monopoly-framework`)

The wiki's key move is that the four *Zero to One* characteristics are **not a menu of levers** — they're "observable signatures of having escaped [[mimetic-competition]]," and they run in a fixed sequence:

1. **Proprietary technology** — the entry condition. "Must be 10x better on a dimension that matters, or genuinely new. Incremental improvement invites replication."
2. **Network effects** — the compounding mechanism. "Require starting in an absurdly small market (Facebook began at one university). Cannot be asserted into existence at scale."
3. **Economies of scale** — structural. "Either present in the cost curve or not; not a strategic choice."
4. **Branding** — the terminal ratifying layer. Inverting the order fails: "branding without proprietary substance is theater (cf. Yahoo turnaround attempt)."

Two preconditions sit underneath: a **secret** ("something important and true that few agree with" — the secret's shape determines which mechanism is even available) and **definite optimism** (a specific plan for a specific future; indefinite optimism / lean-startup iteration is "structurally incapable of producing monopoly because it forecloses commitment").

Plus the **distribution asymmetry** (`concepts/distribution-dead-zone`): superior distribution alone can create a monopoly with no product differentiation; the converse does not hold. Distribution is power-law — "one channel working is sufficient; seven channels half-working is fatal."

## How they apply to MIKAI

**1. Proprietary technology is inverted by AI.** This is the wiki's headline conclusion: "When the 10x capability is a purchasable API available to all simultaneously, proprietary technology at the model layer is a lease, not an asset. 'We use a better model' is not a monopoly position." `concepts/mimetic-competition` puts it sharper — the model layer offers *no exit* from the mimetic field, because "all players acquire the same improvement simultaneously." `concepts/picks-and-shovels-thesis-failure` supplies the empirical backing (inference $20/M → $0.07/M tokens in 18 months).

So MIKAI's substitute for mechanism #1 is what "doesn't arrive with the next API release": **accumulated user-specific graph state and epistemic typing** — the `personal-intent-graph` (passive behavioral signal + epistemic edges: `supports`, `contradicts`, `partially_answers`, `unresolved_tension`). `synthesis/mikai-vs-agent-memory-ecosystem` frames this as the claimed whitespace: "Epistemic edges without behavioral input devolves to manual knowledge base curation. Behavioral input without epistemic edges produces fact lists, not intent graphs."

**2. Network effects → start absurdly small.** The action item is literal: "Ship to five external users — Thiel's smallest-market heuristic and the current blocker are the same instruction." Note `concepts/moat-as-integration-assembly` argues the compounding isn't classic cross-user network effects but per-user behavioral accumulation: "the accumulation of user behavior data that makes the system progressively better at predicting relevance for that specific user."

**3. Distribution is the named live risk.** "MIKAI's natural price point as a personal intelligence substrate risks landing in the dead zone" ($1k–$10k/yr). Two exits, no middle: move up to $10k+ with founder-led sales, or move down below the self-serve friction threshold with real viral mechanics. "The choice of channel and price band must be made before beta, not after."

**4. The secret is unwritten.** Action item #1: "Write MIKAI's secret in one sentence — the claim about intent inference that memory-layer companies would disagree with. If it doesn't survive contact with mem0's roadmap, it isn't a secret."

**5. Name the layer.** Action item #2 gives three candidates: "accumulated graph state, epistemic typing, or MCP distribution position." The third connects to `concepts/obligatory-passage-point`, where MIKAI's thesis is that "the user's cognitive state graph becomes the essential substrate every AI surface must route through" — competing with A2A as the next passage point after MCP.

## Caveats the wiki itself raises

- **Falsifiability**: "every failed monopoly attempt is retrospectively reclassified as 'not actually 10x' or 'wrong market'... Action items derived from the framework inherit this epistemological problem."
- **Scope error**: the framework is "a theory of increasing-returns industries generalized into a theory of all business." Software/platforms is the one row with "full fit" — which does favor MIKAI, but the framework's authority elsewhere is weak.
- **Definite optimism vs. `concepts/engine-not-product`**: unremarked in these pages, but MIKAI's surface-agnostic engine rule with a 6-month PMF expiration reads closer to preserved optionality than to Thiel's "specific plan for a specific future."

One cross-link to treat carefully: `concepts/switching-cost-moat` is tagged onto the Thiel pages as related, but its own page attributes it to Zucman and Stiglitz, not Thiel, and it argues the opposite of the data-moat claim — "data is not itself the moat... The moat is in the friction, not the file."
```

### Lane A/B (serial)

```
## The Four Mechanisms

Per `concepts/thiel-monopoly-framework` (from `sources/2026-07-29-thiel-s-monopoly-mechanisms-and-mimetic-competition-theory-0feea8`), Thiel's four characteristics are **a sequence, not a menu** — and critically, they are "the *observable signature* of having escaped [mimetic competition] — not a causal menu to select from."

| # | Mechanism | Role |
|---|---|---|
| 1 | **Proprietary technology** | Entry condition. 10x better on a dimension that matters, or genuinely new. "Incremental improvement invites replication." |
| 2 | **Network effects** | Compounding mechanism — but paradoxically "require starting in an absurdly small market. Cannot be asserted at scale." |
| 3 | **Economies of scale** | "Structural, not strategic; either exist in the cost curve or they don't." |
| 4 | **Branding** | "Terminal ratification layer; inverting this order (brand-first) always fails." |

Upstream of all four sit the preconditions: a **secret** (`concepts/secrets-thiel`), **definite optimism**, and a small-market start. A fifth mechanism the framework treats as co-equal is **distribution** (`concepts/distribution-power-law`): "one channel working is sufficient; seven channels half-working is fatal."

## Application to MIKAI

**1. Mechanism #1 is the one MIKAI cannot have.** This is the sharpest finding in the wiki. `concepts/thiel-monopoly-framework` states it flatly: "AI inverts the proprietary technology condition. When 10x capability is a purchasable API, proprietary technology at the model layer is a lease, not an asset. The framework's most important characteristic is the least available in AI-native markets." The source's phrasing: **"'We use a better model' is not a position."** `concepts/last-mover-advantage` extends this — "the last mover is the incumbent, and the challenger's improvement becomes a feature announcement."

**2. Defensibility must relocate above the model layer.** The wiki names three candidate layers (`queries/what-is-miakis-secret`), none yet chosen:
- **Accumulated user-specific graph state** — "the components that don't arrive with the next API release" (`concepts/compounding-memory-layer`)
- **Epistemic typing** — tagging capture by the faculty that produced it, enabling a structurally different retrieval model
- **MCP distribution position** — explicitly flagged as "a channel advantage rather than a product advantage"

`concepts/integration-assembly-as-moat` offers a competing answer: the moat is assembling all five metabolism components *simultaneously*, because "no one has closed the full loop" — Pocket, Readwise, and Mem0 "each solved one or two components and stalled." Note this is in tension with the graph-state answer; the wiki distinguishes them ("data accumulation is also defensible but takes longer to develop") without resolving which MIKAI should lead with. A third frame, `concepts/switching-cost-moat`, leaves an explicitly "unresolved" tension: whether MIKAI exploits switching costs or dissolves them.

**3. Mechanism #2 says: ship to five users.** The small-market requirement and MIKAI's stated blocker are the same instruction — action item 4 in the source is literally "Ship to five external users."

**4. Distribution is a live structural risk.** `concepts/distribution-power-law`: "MIKAI's natural price point likely lands near the dead zone" ($1k–$10k) — too expensive for self-serve viral spread, too cheap for a salesperson. The implication is binary: move up to founder-led complex/personal sales, or engineer genuine viral distribution with invitation embedded in core function. Compounding this, `concepts/metabolism-monetization-problem` notes MIKAI carries "consumer software unit economics with enterprise-like sales cycles" — value takes 3–6 weeks to manifest.

**5. The unwritten secret is the gating blocker.** The test in `concepts/secrets-thiel`: "would Mem0's roadmap specifically disagree with the claim?" `queries/what-is-miakis-secret` confirms none of the three candidate layers "has been formulated as a one-sentence secret that passes the Mem0 disagreement test." Without it, MIKAI is "competing mimetically with Mem0, Supermemory, and other memory-layer systems on shared assumptions."

## The Ethical Discriminator

`concepts/chokepoint-rent-vs-category-creation` adds a distinction the wiki says Thiel deliberately collapses, forced by Village Axiom G3 (inclusive before extractive): "MIKAI's defensibility argument should route through category creation (accumulated graph state as genuinely new capability that users could not access before) rather than chokepoint rent (toll on existing LLM inference flows). The former satisfies G3; the latter does not, and is also more competitively fragile."

The source's summary verdict: **"Use the framework for building. Do not use it to adjudicate whether what you have built should persist."**

## Caveat the wiki itself raises

`concepts/thiel-monopoly-framework` flags an unfalsifiability problem: the framework rests on "approximately five cases," failed attempts get "retrospectively reclassified as 'not actually 10x' or 'wrong market,'" and "Google's 10x could not have been specified in 1998." It is a theory of increasing-returns industries generalized into a theory of all business.
```

### Lane C (Claude.ai MIKA TECH)

_(paste answer here)_

---

## Q8. What's the difference between agent memory (persistent) and context management (per-session)?

### Lane A/B (parallel)

```
No page in this wiki poses the question in exactly those terms — there is no `agent-memory-vs-context-management` comparison page. But several pages draw the distinction directly, and they agree on where the line falls. Here's the answer assembled from them, with the caveat that I'm composing across pages rather than quoting one.

## The core split: re-derivation vs. accumulation

The sharpest statement is the **query-time vs. write-time** distinction, which lives (unextracted) inside `sources/2026-08-09-memory-management-systems-for-claude-a28e30.md`:

> **Query-time synthesis** — inference runs *when a question is asked*. The question itself supplies the salience function… Full-corpus cost per question. Nothing persists; nothing compounds… **It is re-derivation, not memory.**

> **Write-time promotion** — the standing, question-independent decision — with *no question pending* — of which candidate facts get promoted into durable memory.

That's the whole difference in one line. Context management is per-session because a question is pending and the question does the salience work for free. Memory is persistent because it has to decide what matters with *no question pending* — which requires an **importance function** that is query-independent. The same source's PageRank analogy: BM25/embeddings = query-dependent relevance (context management); PageRank = query-free importance prior computed offline (memory). "Current memory systems have BM25-equivalent relevance and fake PageRank with term frequency."

## The hardware framing

`concepts/llm-os` makes the layering explicit — context window as RAM, retrieval as disk:

| LLM OS Concept | MIKAI Component |
|---|---|
| RAM (context window) | Compiled context preloaded at session start |
| Disk (retrieval) | Intent graph + event log |

And the strategic consequence: "The model is the processor — interchangeable… The state layer is the OS — the accumulated, portable, user-owned context… compounds over time." Per-session context is volatile and fungible; persistent memory is what accrues switching cost.

`concepts/five-lineages-of-memory` says the same thing genealogically: Lineage 1 (Memory as Scarcity) bequeaths the observation that "**a context window is a working set; context assembly is paging**." Context management descends from virtual memory and caching. Persistent memory descends from Lineages 2–3 (record, meaning) — the durable store.

## What each one's hard problem is

They're not just different in duration; they fail differently.

**Context management** decomposes into `concepts/admission-eviction-prefetch` — what enters context, what leaves when it's full, what gets staged before it's asked for. That page's verdict: "Storage is table stakes every generation; systems differentiate on eviction policy and prefetch strategy." Its per-session concerns are things like ordering and format — `concepts/lost-in-the-middle` notes that content placed mid-context gets weaker attention, so "injection format and ordering matter as much as content." That is a purely within-session problem; it doesn't exist for a store on disk.

**Persistent memory**'s hard problem is the importance function and drift. From the sleep-time-compute material in the same 2026-08-09 source: "wrong generalizations persist across sessions" — a bad context assembly costs you one turn, a bad memory write costs you every future session.

## The bridge between them

Two pages cover the crossing:

- `concepts/crystallization` — the operation converting a completed thread into a durable digest, "the batch counterpart of `llm-wiki-pattern`'s continuous incremental compilation." The discipline is non-destructive: raw sources stay immutable, the digest is a projection. Sleep-time compute is "when candidate facts transition from volatile session context into crystallized memory."
- `concepts/context-write-back-gap` — the crossing in the *other* direction is the unsolved half. Inferring traits within a session is solved; "translate those inferences into a CLAUDE.md edit… or any artifact that Claude Code actually reads at session start" is not. "No current system does this autonomously."

## Routing rule

`concepts/context-cost-ladder` gives the practical decision rule, ordered `hooks (zero) → skills (low) → plugins (medium) → MCP (high)`, with the key implication:

> "user prefers less technical detail" belongs in CLAUDE.md, not in a skill, because it is a standing modifier, not a task procedure. **Skills are task-triggered; preferences are session-level.**

Standing/identity-level facts → always-on persistent context. Task-specific procedures → triggered, per-session load.

## One caveat on the framing

`concepts/llm-wiki-pattern` sharpens the stakes: "RAG rediscovers; the LLM Wiki compounds." And `synthesis/mikai-vs-agent-memory-ecosystem` treats scope as a differentiating dimension — "Every existing tool is scoped to a session, a project, or conversations. MIKAI is scoped to the person across their full digital life." So in this wiki's vocabulary, "persistent" isn't one thing: session → project → person is a ladder, and most systems calling themselves memory sit lower on it than the name implies.
```

### Lane A/B (serial)

```
The wiki doesn't label these two things with exactly those phrases, but the distinction is drawn sharply and repeatedly — under different names. Here's how it grounds out.

## The two operations

The cleanest statement is `concepts/query-time-synthesis-vs-write-time-promotion`, which calls this "the core architectural distinction in LLM memory systems: two fundamentally different operations that current implementations conflate under the single word 'memory.'"

- **Query-time synthesis** (≈ per-session context management) "runs at question time. The pending question supplies the salience function... It is re-derivation: full-corpus cost per query, output is ephemeral, nothing persists or compounds across sessions."
- **Write-time promotion** (≈ persistent agent memory) "is a standing decision — made with *no question pending* — about which of many candidate facts get written into durable memory. Salience must be derived without knowing what future queries will ask."

That last clause is the whole difference. Session context has a question to rank against; persistent memory does not, so it "requires a query-independent importance function."

## What per-session context actually is

`concepts/working-set-theory` makes it a systems problem, not a novel one: "A context window is a working set. Context assembly is paging." Denning's 1968 triad — admission, eviction, prefetch — is inherited wholesale, and `concepts/llm-os` gives Karpathy's framing: "context window as RAM, retrieval systems as disk, tools as syscalls, and user sessions as processes."

Within a session the binding constraint is ordering, not just selection. `concepts/attention-as-injection-constraint` argues that because of "lost in the middle," "the *order and structure* of what is injected into context matters as much as the content itself" — and concludes that for MIKAI "this is not primarily an LLM reasoning problem — it is a serialization problem."

## What persistent memory buys

`concepts/compounding-memory-layer` is the sharpest argument for why session-scoped context isn't enough. Its evidence is a diagnosis of six monthly journals: the same inbox concept "is independently reinvented in at least five separate months." The scorecard it gives a well-run manual system — capture: yes, triage: yes, completion verification: yes, **persistence across cycles: no** — is exactly the gap. "The result is a system that processes well within a month but resets between months."

`concepts/llm-os` states the strategic version: "the LLM is the processor, and processors commoditize; the OS that matters is the state layer, and state compounds."

## The boundary between them

The two aren't a clean split — there's an explicit gate. `concepts/memory-promotion-gate` describes "a multi-threshold gating mechanism that separates short-term memory candidates from durable writes, preventing both memory bloat (over-promotion) and information loss (under-promotion)." Without it you get a binary failure: write everything (bloat, signal dilution) or write only surface patterns (missing rare-but-important signals).

Crossing the boundary is supposed to happen out-of-band, not mid-session. `concepts/sleep-time-compute` gives the best practices: "Separate the dreamer from the responder" and "Dreams emit candidates, not commits." `concepts/triggered-compaction` handles the batch case, firing on cheap statistics (fragmentation, redundancy, supersession density) "with no LLM calls until the final synthesis step" — and warns that "false merge > false split in danger" once source retirement follows.

## Where the difficulty actually lives

`sources/2026-08-07-memory-architectures-across-software-history` sorts everything into two families with opposite trajectories: "**Storage + query-triggered retrieval** commoditizes every generation (filesystems → desktop search → RAG)" while "**context-triggered judgment** — what deserves attention *right now* — has never commoditized because it has never been solved." Its fourth invariant: "LLMs repriced extraction, not judgment."

So per-session context management is a solved-ish paging problem being re-solved; persistent memory is only easy on the storage half. The hard half is the promotion decision — and `query-time-synthesis-vs-write-time-promotion` names the specific failure when you fake it with corpus statistics: on a corpus generated by building a personal assistant, tooling terms like "claude/wiki/graphiti" outrank "the Atacama proposal, a one-time financial decision." "The importance ordering inverts from what the user would actually want promoted."

## One more axis worth flagging

`concepts/snapshot-brain-vs-continuous-ingestion` adds a distinction that cuts across this: persistent ≠ current. A snapshot store (CLAUDE.md read at session start, a hand-curated MEMORY.md) persists but degrades — "A snapshot brain accurate on day 0 degrades continuously." Notably, it argues snapshots are *fine* for retrospective recall ("verbatim flat storage... is competitive with extraction-heavy pipelines for pure recall") and wrong for state awareness, because "stall onset is the *absence of events* over an interval — detectable only in a continuous stream, not in a static file."

**Caveat on grounding:** the phrase "agent memory" appears in this wiki mainly as a thread title (`sources/2026-04-02-agent-memory`), covering a broader survey — RAG's limits, Mem0/Graphiti/Letta, the L3-vs-L4 split. The persistent/per-session contrast as you framed it is my mapping onto the wiki's write-time/query-time vocabulary; the wiki doesn't state it under your labels.
```

### Lane C (Claude.ai MIKA TECH)

_(paste answer here)_

---
