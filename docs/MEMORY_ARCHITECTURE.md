# MIKAI Memory Architecture — Dream + Wiki

**Status:** Design spec (proposed). Not yet ratified into `DECISIONS.md`.
**Date:** 2026-06-27.
**Depends on:** `claude_threads.py` capture (built 2026-06-26), Graphiti L3 (`L3Backend`, ARCH-024), the L3/L4 split (`VISION.md`).
**Supersedes nothing.** Adds a layer above the graph.

---

## 0. One-paragraph summary

MIKAI today is `Capture → Graphiti extraction → graph`. The graph is online,
incremental, append-only, and never runs a global pass that rereads everything
and rewrites it for coherence. This spec adds that pass — **the Dream** (modelled
on Anthropic's Claude Dreaming) — and a second store it maintains — **the Wiki**
(modelled on Karpathy's LLM Wiki). The graph stays as the exhaustive, bitemporal,
queryable **substrate of record**. The wiki is a **lossy, decaying, LLM-native
projection** that the dream rewrites nightly. The key invariant that makes this
safe: **the graph is ground truth, so the wiki is allowed to forget.** Anything
the wiki prunes can be re-derived from the graph; nothing is lost at the system
level.

```
  CAPTURE                 DREAM (consolidate)            STORES
  ┌───────────────┐       ┌────────────────────┐        ┌──────────────────────────────┐
  │ claude-thread │       │ nightly REM dream   │        │ GRAPH  (Graphiti / Neo4j)    │
  │ claude-code   │──────▶│  + periodic deep    │───────▶│  substrate of record:        │
  │ apple-notes   │  raw  │  dream              │ writes │  exhaustive, bitemporal,     │
  │ (7-day buffer)│ episo-│ Orient→Gather→      │  wiki  │  queryable, total recall     │
  └───────────────┘  des  │ Consolidate→Prune   │  +opt  ├──────────────────────────────┤
         │                └─────────┬──────────┘ promote │ WIKI  (~/.mikai/wiki/*.md)   │
         │ Graphiti extraction      │ reads graph        │  dreamed projection:         │
         └─────────────────────────▶│ (substrate)        │  curated, decaying,          │
            (already wired)          └───────────────────▶│  LLM-native, read whole      │
                                                          └──────────────────────────────┘
                                            reads ▲                         ▲ reads
                                      L4 noonchi (real-time)         any LLM session
                                      thread/state/intervention      "who is Brian + now"
```

This mirrors Letta's primary/sleep-time split: **the dream is the sleep-time
agent (maintains memory); L4 noonchi is the primary agent (reads it, acts in
real time).** They are different jobs, not the same job on two schedules.

---

## PART A — THE WIKI (after Karpathy)

### A.1 Three layers (Karpathy's invariant)

| Layer | In MIKAI | Mutability |
|---|---|---|
| **Sources** (raw) | The Graphiti graph + the raw episode buffer | Immutable / append-only. Never edited by the dream. |
| **Wiki** (compiled) | `~/.mikai/wiki/` markdown | LLM-owned. Rewritten by the dream. Disposable. |
| **Schema** (governance) | `~/.mikai/wiki/schema.md` | Human-owned. The most important file. Encodes entity types, the importance function, tier rules, contradiction policy. |

The Karpathy thesis we are buying: *an LLM reasons better over a compiled
narrative it reads whole than over retrieved fragments.* The wiki exists so the
consumer (L4, or any priming LLM) reads **one coherent document**, not RAG chunks.
The graph remains for what text cannot do: multi-hop relational queries,
provenance, scale.

### A.2 Directory layout

```
~/.mikai/wiki/
  schema.md              # governance (human-owned). See A.6.
  index.md               # lean catalog, < 200 lines. Links to pages, grouped by tier. (Karpathy index.md)
  log.md                 # append-only dream journal: every consolidation's diff. (Karpathy log.md)
  pages/
    self.md              # USER MODEL: who Brian is — stable traits, values, working style
    preferences.md       # confirmed preferences / corrections
    people/<slug>.md     # one page per recurring person
    projects/<slug>.md   # one page per project (e.g. MIKAI, the build-company)
    threads/<slug>.md    # TASK MODEL: open threads + state (exploring→decided→acting→stalled)
  archive/               # forgotten / sub-threshold pages. Non-destructive (graph still has provenance).
```

`pages/threads/*` is the **task model** (recency-weighted, fast decay, read by
L4). `self.md` + `preferences.md` + `people/*` are the **user model** (slow
decay, durable). One wiki, two decay regimes — see A.5. This resolves the
task-model vs user-model fork from the design discussion: they are *different
pages with different decay constants*, not different systems.

### A.3 Page format — every fact carries provenance and confidence

A wiki page is markdown for the reader, but each durable claim is annotated so
the dream can score, decay, and revise it. Inline annotation keeps pages
LLM-readable while remaining machine-parseable:

```markdown
# self.md  ·  tier: semantic  ·  decay_half_life_days: 180

Brian is building MIKAI, a task-state-awareness engine ("noonchi"). ^[s=14 conf=0.97 seen=2026-06-26 src=a60ac74e,3e713856 contra=0]

Prefers "intervention timing" over the internal codename in published work. ^[s=2 conf=0.71 seen=2026-06-09 src=… contra=0]
```

The `^[...]` footnote-style tag holds the fact's metadata (A.4). A renderer can
strip tags to produce a clean read-whole document for an LLM, or keep them for
the dream. `src=` are **Graphiti episode UUIDs** — the back-pointer to ground
truth, so any wiki line can be audited or re-derived. This is the provenance the
Karpathy-v2 critics correctly said was missing.

### A.4 Confidence — DEFINED (the gap both source patterns leave open)

Karpathy v2 proposes "confidence" but never defines it. We define it as a pure
function of three observable quantities, computed by the dream — no model
guessing a float:

- `s` — **support**: count of distinct source episodes asserting the fact.
- `c` — **contradiction**: count of distinct source episodes contradicting it
  (the graph already supplies `CONTRADICTS` edges; the dream counts them).
- `last_confirmed` — date of the most recent supporting episode.

```
base(s, c)        = (s + 1) / (s + c + 2)          # Laplace-smoothed support ratio ∈ (0,1)
retention(Δt, H)  = 2 ** (-Δt / H)                 # Ebbinghaus: half-life H days, Δt = days since last_confirmed
confidence        = base(s, c) * retention(Δt, H)  # ∈ (0,1)
```

- **Reinforcement resets the curve.** A new supporting episode does three things:
  `s += 1`, `last_confirmed = today` (so `Δt → 0`, `retention → 1`), and — because
  repeated confirmation should make a fact *stickier* — `H ← H * (1 + ln(1 + s_new)/k)`
  (k a schema constant, default 4). This is the Ebbinghaus "each reinforcement
  flattens the curve" property, made concrete.
- **Contradiction** raises `c`, lowering `base`; the dream additionally sets
  `last_confirmed` only if the *contradicting* episode is newer (most-recent-wins,
  per Anthropic dreaming), which can flip the asserted value while leaving the
  superseded value in `archive/` with its provenance.

### A.5 Memory tiers + decay regimes (Karpathy v2 hierarchy, made operational)

| Tier | Page types | Half-life `H` (default) | Promotes when |
|---|---|---|---|
| **working** | the raw 7-day buffer (not in wiki yet) | n/a (the dream consumes it) | the dream runs |
| **episodic** | `threads/*` (task model) | **14 days** | a thread is referenced across ≥2 sessions |
| **semantic** | `self.md`, `people/*`, `projects/*` | **180 days** | a fact reaches `s ≥ 3` and `conf ≥ 0.6` |
| **procedural** | `preferences.md`, schema-able workflows | **365 days** | a pattern recurs `s ≥ 5` across distinct contexts |

Promotion is upward as evidence accumulates; **forgetting is downward**: when
`confidence < θ_forget` (schema default 0.15), the dream demotes the line to
`archive/` and removes it from the live page. Because the graph retains the
source episodes, demotion is non-destructive — a later confirming episode can
resurrect it. Fast-decaying `threads/*` is why a stalled-then-abandoned thread
quietly disappears from L4's view without anyone deleting anything.

### A.6 `schema.md` — the governance file (human-owned)

The one file the dream may **not** rewrite. It encodes, in prose + a small config
block, everything the dream needs as policy rather than judgment:

```yaml
# schema.md (excerpt)
entity_types: [person, project, thread, preference, decision, value]
importance_signals:        # what makes a fact worth keeping (the "importance function")
  - novelty                # changes a prior belief in the wiki/graph
  - recurrence             # asserted across ≥N distinct sessions
  - decision_linkage       # attached to a stated goal / commitment
  - emotional_salience     # flagged affect in the source
thresholds:
  theta_forget: 0.15
  promote_semantic: {s: 3, conf: 0.6}
  promote_procedural: {s: 5}
half_life_days: {episodic: 14, semantic: 180, procedural: 365}
contradiction_policy: most_recent_wins   # loser → archive/ with provenance
write_authority: propose_diffs           # autonomous | propose_diffs  (see O-050)
```

The "importance function" the design discussion kept circling is **here**, as an
explicit signal list the dream applies in Phase 2 — not a magic number.

---

## PART B — THE DREAM (after Anthropic)

Anthropic's Claude Dreaming: a scheduled offline pass that reads the memory store
+ up to ~100 past transcripts *together* and emits a rewritten memory — duplicates
merged, contradictions resolved most-recent-wins, stale references pruned;
weights untouched. The `dream-skill` replica runs it as four phases:
**Orient → Gather Signal → Consolidate → Prune & Index.** We adopt those four
phases verbatim and bind each to MIKAI's stores.

### B.1 Trigger & cadence

MIKAI is a daemon system (launchd), not an interactive Stop-hook tool, so the
trigger is a launchd job, not a session hook. Two cadences, mirroring the two
decay regimes:

- **REM dream — nightly.** `com.mikai.dream.plist`, daily ~04:00 (after the day's
  `claude_threads` capture, before the 05:15 window job). Scope: the **task
  model** — `threads/*`, last-7-day buffer. Cheap, fast.
- **Deep dream — weekly (Sun) or monthly.** Scope: the **user model** — rereads a
  larger graph slice + all `pages/`, recomputes confidence/decay globally,
  rebuilds `index.md`, compacts `archive/`. Expensive, thorough. This is the
  full-rereads-everything pass Graphiti never does.

State watermark: `~/.mikai/dream_state.json` (`last_rem`, `last_deep`,
`last_episode_seen`). Idempotent: a dream over no-new-signal is a no-op.

### B.2 The four phases, bound to MIKAI

**Phase 1 — Orient.** Read `schema.md`, `index.md`, and the live `pages/`. Pull
`L3Backend.stats()` and `communities()` for graph-side shape. Establishes "what
the wiki currently believes."

**Phase 2 — Gather Signal.** Read new source material *since the watermark* —
the new `claude-thread`/`claude-code`/`apple-notes` episodes — but **targeted, not
full** (Anthropic's "grep, not full reads"). Use `L3Backend.search()` /
`search_nodes()` scoped to the day's new episodes to surface: corrections,
preference shifts, decisions, recurring entities, and **contradictions vs the
current wiki** (cross-check new edges against existing wiki claims). Apply the
`importance_signals` from schema to filter signal from chatter. Output: a typed
changeset (`assert`, `contradict`, `reinforce`, `new_entity`), each carrying
source episode UUIDs.

**Phase 3 — Consolidate.** Apply the changeset to the wiki:
- merge duplicates into existing lines;
- **resolve contradictions** most-recent-wins → loser to `archive/` with provenance;
- **convert relative dates to absolute** ("last week" → `2026-06-20`), per dream-skill;
- update `s`, `c`, `last_confirmed`, recompute `confidence` and `H` (A.4);
- promote tiers where thresholds crossed (A.5);
- *(optional, O-049)* promote high-confidence consolidated facts **back into the
  graph** as synthetic episodes (`group_id="wiki-consolidated"`) via
  `ingest_episode` — closing the loop so deep syntheses become queryable.

**Phase 4 — Prune & Index.** Apply decay across all live lines; demote
sub-`θ_forget` lines to `archive/`; rebuild `index.md` as a **lean < 200-line
catalog** (demoting verbose content to topic pages, per dream-skill); append a
**diff entry to `log.md`** — what was asserted, contradicted, promoted, forgotten,
and why. `log.md` is the dream journal and the audit trail.

### B.3 Which model dreams? (open — see O-048)

Anthropic dreaming = Claude doing the synthesis. MIKAI's stack already wires
**DeepSeek V3** (cheap, consistent with the extraction LLM) and Voyage embeddings.
The dream is a synthesis task where model quality matters more than in extraction.
Options: DeepSeek (cheap, in-stack), or Claude via API (better synthesis, the
namesake) — gated by the subscription-auth ban and the Agent-SDK-credit timing
(memory: lands 2026-06-15). **Recommendation:** DeepSeek for the nightly REM
dream (volume, cost), Claude for the weekly deep dream (quality, low frequency).

### B.4 Read path (the consumers)

- **L4 noonchi (real-time / primary):** reads `pages/threads/*` + `index.md` to
  answer "what is Brian in the middle of, what state, intervene now?" Never reads
  the raw graph for this — the wiki *is* the consolidated task model.
- **Session priming (any LLM):** reads `self.md` + `preferences.md` + `index.md`
  as a single context block — "who is Brian and what's current."
- **Deep / relational queries:** fall through to `L3Backend.search()` / `expand()`
  on the graph. The wiki links carry `src=` UUIDs to jump into the graph.
- *(future, Karpathy-v2)* hybrid retrieval (BM25 + vector + graph traversal, RRF)
  once the wiki outgrows read-whole size. MVP: the wiki is deliberately small
  enough to read whole — that's the point.

---

## PART C — Proposed decisions & open questions

### Proposed (ratify into `DECISIONS.md`)

- **ARCH-026 — Dual-store memory.** Graphiti graph = exhaustive bitemporal
  substrate of record. Karpathy-style markdown wiki = lossy, decaying, LLM-native
  projection. The wiki may forget; the graph may not.
- **ARCH-027 — Dreaming consolidation.** A scheduled offline pass (nightly REM +
  periodic deep), 4 phases after Anthropic (Orient→Gather→Consolidate→Prune),
  rewrites the wiki from graph + buffer. Wiki forgetting is non-destructive
  because the graph retains provenance.
- **D-053 — Confidence is a defined function** of `(support, contradiction,
  recency)` with Ebbinghaus half-life and reinforcement reset (A.4), computed by
  the dream — never a model-guessed float.
- **D-054 — Two decay regimes in one wiki:** episodic `threads/*` (H=14d, task
  model) vs semantic/procedural `self/people/preferences` (H=180/365d, user
  model). Resolves the task-vs-user-model fork.

### Open (track in `OPEN.md`)

- **O-048 — Dream LLM:** DeepSeek vs Claude per cadence (B.3).
- **O-049 — Promote-to-graph:** should the deep dream write `wiki-consolidated`
  synthetic episodes back into Graphiti, or stay read-only on the graph? Risk:
  feedback loop / synthetic facts polluting provenance.
- **O-050 — Write authority:** `autonomous` (dream commits wiki edits) vs
  `propose_diffs` (dream emits a diff Brian approves). Relevant to the
  autonomous-agent posture. Default `propose_diffs` until trusted.
- **O-051 — Relationship to Anthropic's managed-agent dreaming:** it consolidates
  an *agent's* session memory, not a *personal life-graph*. Confirm we build our
  own; watch whether the managed feature ever points at an external store.

---

## PART D — Build order (smallest runnable first)

1. **WikiStore** (`infra/graphiti/wiki.py`): read/write `pages/`, parse `^[...]`
   tags, render clean (tag-stripped) vs annotated, append `log.md`, rebuild
   `index.md`. Pure file I/O + parsing; unit-testable with no LLM.
2. **Confidence/decay module**: the A.4 math as pure functions. Unit tests.
3. **REM dream `--dry-run`** (`infra/graphiti/dream.py`): Phases 1–2 only —
   read wiki + gather signal from the day's buffer via `L3Backend`, print the
   changeset. No writes. Validates signal extraction against real `claude-thread`
   data already in the graph.
4. **Consolidate + Prune** (Phases 3–4) behind `--dry-run` then live; write wiki,
   append `log.md`.
5. **launchd** `com.mikai.dream.plist` (nightly), reusing the
   `claude-threads-runner.sh` env pattern (`~/.mikai/launchd.env`).
6. **Deep dream** cadence + global recompute.
7. *(later)* promote-to-graph (O-049), hybrid retrieval, L4 read integration.

Step 3 is the first thing worth looking at: it runs the dream's *perception* over
the `claude-thread` episodes `claude_threads.py` is already capturing, and shows
the changeset it would consolidate — without touching anything.

---

## PART E — Epistemic critique: five holes (added 2026-06-28)

Parts A–D were pressure-tested against Karpathy's thesis and the wider
memory-systems literature. Five holes surfaced. They are load-bearing — **H2 and
H5 change the spec**, not just annotate it. The root cause is consistent:
Karpathy's LLM Wiki is a **knowledge compiler** (external facts, lint
contradictions away); MIKAI is a **person compiler** (current state, profile,
life-movement). The mechanism transfers; the domain does not, and the gaps live
exactly where the domains diverge.

- **H1 — "ground truth" is overloaded.** The graph is not pure sources. Graphiti
  already *derives* entities/edges — an interpretation, not raw truth. So there
  are **three** layers, not two: raw episodes (evidence) → extracted graph
  (durable, queryable, provenance-bearing *derivation*) → wiki (disposable,
  present-tense *derivation*). Both graph-edges and wiki are derivations.
  "Ground truth" should mean **evidential provenance**, not "the correct
  interpretation." Otherwise stale graph edges get trusted as truth.

- **H2 — "forget" and "track life-movement" contradict in one store.** Movement is
  `X → Y`; you cannot represent it in a store that forgot `X`. Resolution: **three
  retention policies, not one** — live pages = current state (*forgetful*);
  `log.md` = append-only deltas/transitions (*never forgets the movement*); graph
  = full evidence (*never forgets anything*). "Significant movement" lives in the
  append-only log, not the forgetful pages. (Thesis mechanisms: this is M6
  summarization-cascade on the pages + a non-lossy M7 boundary log.)

- **H3 — the profile is the part that must *not* forget, and A.4 would erode it.**
  A.4 counted only new source-episodes as reinforcement, so a stable trait that's
  rarely re-confirmed but frequently *read* decays to nothing. Fix:
  **retrieval is reinforcement** — recency decays since last *access*, not last
  confirmation (Generative Agents). Add `pin: true` (decay off) for
  `projectbrief`-style invariants. (Thesis M2 relevance-decay, corrected to
  count reads.)

- **H4 — Karpathy's "lint contradictions away" erases the movement you want.** For
  knowledge a contradiction is an error (most-recent-wins). For a *person* it is
  often *change to record*. The dream must **classify** each contradiction:
  *state transition* (log it, update current state), *correction* (overwrite,
  old was wrong), or *transient noise/mood* (do **not** touch the profile). This
  is thesis **M5 update-resolution**, specialized to the person domain — and the
  hardest cognitive step.

- **H5 — significance ≠ frequency; A.4 gets it backwards.** A.4 confidence is
  support-count-driven, so a once-said pivotal fact ("I'm getting married", s=1)
  scores low and decays fast — exactly wrong. Split the **two axes A.4 wrongly
  merged**: *confirmation-confidence* (is this true? — support/contradiction/
  recency) vs *importance* (does this matter? — LLM-scored 1–10, frequency-
  independent, à la Generative Agents). **Forgetting is driven by importance, not
  confidence.** A high-importance/low-confidence fact is *verified*, not forgotten.
  This also yields a better dream trigger than a nightly cron: reflect when
  **accumulated importance crosses a threshold** (Generative Agents reflect
  2–3×/day this way).

**Clarified problem statement.** Not "graph remembers, wiki forgets," but:
maintain a **present-tense model of a person** an LLM reads whole, derived from an
immutable evidence base, under **three retention policies** (current state =
forgetful; profile = durable, reinforced by *use*; transitions = permanent
trajectory) and **two scoring axes** (confidence = truth, importance =
significance), with contradictions **classified** (transition / correction /
noise), not linted away. → **two derived stores × three retention policies × two
scoring axes.**

## PART F — Lineage placement & added prior art

Per the thesis's *Four Theoretical Lineages*, this spec sits in **systems
consolidation / event segmentation** (GAM, A-MEM): the dream is importance-/
boundary-triggered consolidation (M7) + summarization cascade (M6) producing a
derived narrative store. It imports the **salience + forgetting** the bitemporal
lineage (L3/Graphiti) structurally lacks — the exact blind spot the thesis
attributes to that lineage ("no salience, no forgetting, no confidence").

Prior art surfaced in this pass that is **not** in the thesis's competitor map:

| System | Contribution to this spec |
|---|---|
| **Generative Agents** (Stanford 2023) — memory stream + reflection + importance(1–10) | Direct precedent for the *person* domain. Source of the importance≠frequency fix (H5), retrieval-as-reinforcement (H3), and the importance-accumulation reflection trigger. |
| **Cline / Roo Memory Bank** — markdown hierarchy | Production validation of the three-retention split (H2): `activeContext.md` (current state) vs `progress.md` (trajectory); `projectbrief.md` = never-overwritten source of truth = the pinned profile (H3). |
| **Memsearch** (Zilliz) | Markdown source-of-truth + rebuildable vector *shadow* index — the "wiki + disposable index" pattern (validates A.2 + future hybrid retrieval). |
| **Memobase** | User-profile-keyed long-term memory — the profile store as a first-class object. |

**New open decision (extends Part C):**

- **O-052 — Two-axis scoring.** Adopt `confidence` (A.4, truth) **and** a separate
  LLM-scored `importance` (1–10, significance, frequency-independent). Decay and
  forgetting key off importance; verification effort keys off low confidence at
  high importance. Supersedes A.4's single-score model. Revise A.4 → A.4a
  (confidence) + A.4b (importance) when ratified.

*Cross-reference: `MEMORY_ARCHITECTURE_THESIS.md` (lineages, M1–M7 mechanisms,
the evaluation-bridge framing this dream operationalizes) and
`EPISTEMIC_DESIGN.md` (the philosophical foundations for forgetting/salience).*

---

## PART G — Contradiction resolution (Socratic, in progress · 2026-06-28)

Parts A–F were written before re-reading this branch's epistemic foundations
(`EPISTEMIC_DESIGN.md`, `EPISTEMIC_EDGE_VOCABULARY.md`, March 2026). Six genuine
contradictions exist between the new dream/wiki design and the older epistemic
design. Repeatedly, **the older design already holds the resolution** — the new
spec drifted from it. Working through each Socratically; resolutions recorded
inline as they converge.

| # | Contradiction | New spec says | Branch (March) says | Status |
|---|---|---|---|---|
| **C1** | Resolve vs Hold | Dream Phase 3 resolves contradictions "most-recent-wins" (Anthropic) | `unresolved_tension` is **priority-0**; "an AI that papers over tensions produces worse output" | OPEN |
| **C2** | Forget vs never-delete | Wiki prunes sub-θ lines; forgetting first-class | Q-E002/§1: old beliefs are *superseded, not deleted*; the trajectory is the value; decay = weight-reduction | OPEN |
| **C3** | Stable-trait profile vs constructed self | `self.md` holds "stable traits," slow decay | §3/Q-E003: self is *constructed, not discovered*; highest-value **unit is the revision event**, not the static belief | OPEN (keystone) |
| **C4** | Importance: recurrence vs intrinsic salience | H5: significance ≠ frequency (LLM-scored 1–10) | Step 4: recurrence is the promotion engine — but Step 1 already elevates a single processed reflection. The **epistemic-type classifier** may be the importance instrument H5 wanted | OPEN |
| **C5** | Where salience/decay lives | Scores live in the wiki; graph stays vanilla | Q-E005 left 3 options (attributes-layer / derive-in-L4 / fork). The wiki is a **fourth** | candidate resolution to Q-E005 |
| **C6** | Two confidence scores | Wiki A.4 defines its own | Edge-vocabulary schema already has node `confidence FLOAT` | OPEN |

### Resolution (2026-06-28): collapse to the simplest stance that keeps the thesis

Brian's directive: *"I need the simplest and most elegant execution of the thesis
so we can get a working prototype. The hard questions get answered as the system
develops."* So every contradiction is resolved by the **cheapest stance that keeps
the base assumptions** — all numeric machinery (A.4 confidence, H5 importance,
decay/tiers, the loss-function profile-learning) is **deferred**, not built.

Brian's cleaner definition of the dream (supersedes Part B's Anthropic 4-phase):
> The dream is a **synthesis function** from (recent threads + current wiki) → an
> updated model of what the user **wants, values, is doing, and is conflicted
> about.** The wiki is that model rendered to be read whole. The graph is the
> immutable substrate it synthesizes from.

| # | Minimal resolution (prototype) |
|---|---|
| **C1** resolve vs hold | Dream **never resolves destructively** — it re-summarizes. Tensions go to a `## Tensions` section, surfaced not collapsed. The graph keeps both regardless. |
| **C2** forget vs delete | "Forget" = **omit from the rendered wiki**. Nothing deleted; graph + `log.md` are truth. No archive machinery. |
| **C3** profile vs constructed self | The wiki is **re-constructed every dream**; the `log.md` diff *is* the revision record. No special revision-node type. |
| **C4** importance | **No numeric importance.** "Weight reflections/decisions/wants over fragments; recurring over one-off" is a *prompt instruction*, not a score. Two-axis math (O-052) deferred. |
| **C5** where scores live | **No scores anywhere.** Graph stays vanilla. (Q-E005 sidestepped for now.) |
| **C6** two confidences | None. Qualitative, in-prompt only. |

### PART H — The minimal prototype (BUILT 2026-06-28)

```
~/.mikai/wiki/
  wiki.md   # read whole. Sections: ## Who · ## Now (state) · ## Tensions · ## Wants
  log.md    # append-only per-dream "what changed" delta = the revision record
```

`dream.py` (on `main` at `infra/graphiti/dream.py`) — **one DeepSeek call**: read
`wiki.md` → pull last 7d of `claude-thread` episodes from Neo4j → rewrite the wiki
under four rules (*surface tensions; weight depth over volume; mark movement;
ground, don't invent*) → write `wiki.md`, append delta to `log.md`. Nightly via
`com.mikai.dream.plist` (RunAtLoad + 06:00, after the 05:15 claude-threads
capture), runner `dream-runner.sh` sourcing `~/.mikai/launchd.env`.

**Fidelity test (Brian's gate "if it passes, continue") — PASSED.**
- *Karpathy*: LLM-owned markdown, read whole, compiled+maintained by the dream;
  `log.md` timeline. (Dropped only `index.md` — a 100+-page scale feature.)
- *Generative Agents*: the dream **is** reflection — synthesis over a recent
  memory stream. (Substituted: in-prompt salience for numeric importance; fixed
  nightly for importance-triggered cadence — both on the deferred list.)
- *MIKAI*: tensions held, not resolved — the third, differentiating ingredient.

**First live run:** dreamed over **138 episodes** (7d, claude-thread) → a 7.3 KB
`wiki.md`. Output correctly **surfaced 6 live tensions** (builder-vs-consumer
framing, INTJ/ENTJ grip, posterior-vs-anterior posture dx, trust-vs-skepticism,
aesthetic-vs-practical, sculptural-vs-vigorous), marked state movement, and
expressed wants in words not numbers. Thesis validated at prototype scale.

**Deferred ("as the system develops"):** numeric confidence/importance (O-052),
decay/tiers/Ebbinghaus (H2/H3 formal), index.md, promote-to-graph (O-049), hybrid
retrieval, importance-triggered cadence, and the information-metabolism /
loss-function profile-learning model. These remain genuine open questions.
