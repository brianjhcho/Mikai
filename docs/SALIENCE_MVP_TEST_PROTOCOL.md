# Salience MVP — Test Protocol & Session Concerns

Everything gathered in the 2026-08-07 → 2026-08-08 session for testing
what was built. Reference this while you look at `wiki-salience.md`
and the first ten `~/.mikai/wiki/concepts/*.md` pages.

## What shipped

**One new subcommand:** `python3 -m infra.graphiti.dream_bootstrap promote`

**Formula (all weights = 1, hand-set threshold = 4.0, d = 0.5):**
```
S(c, t) = ln(Σᵢ (t − tᵢ)⁻⁰·⁵)  +  spread(c)  +  goal_overlap(c)
         └── base_activation (ACT-R) ─┘  └ distinct ┘  └ ∩ USER_MODEL.md ┘
                                          streams        Current
```

**Outputs:**
- `~/.mikai/wiki/concepts/<slug>.md` — one page per promoted concept
- `~/.mikai/wiki/wiki-salience.md` — ranked ledger of every scored candidate

**Candidate sources (no taxonomy):**
- `wiki-ontology.md` entities (375 proper nouns)
- N-gram extraction from `wiki.md` (capitalized 2-4 word phrases, freq ≥ 5,
  filtered by leading-stopword and min non-stopword-char rules)

---

## The formal name we adopted

**Consolidation Layer.** From complementary learning systems theory
(McClelland, McNaughton & O'Reilly 1995) — the hippocampus-to-neocortex
transfer where episodic traces get promoted into durable semantic
structure. Not "salience," not "attention," not "importance." The score
this layer computes is a **consolidation priority.**

The magnum-opus salience formula is that consolidation priority.

---

## Concerns / variables to hold in mind while reviewing the output

### 1. The formula bug Fable caught

The original brief-I form was:
```
S = w₁·log(density) + w₂·Σᵢ(t−tᵢ)⁻ᵈ + w₃·spread + w₄·max-sim
```
Bug: `density` and the recency sum double-counted the same evidence. In
ACT-R, occurrence count IS the number of terms in the sum, and `log`
wraps the whole sum. The MVP uses the corrected form (single term for
recency-weighted activation). If the concept pages you now see look
right, that's evidence the correction was right too.

### 2. What's OUT (all deliberately deferred, all reversible)

Per Fable's brief II, none of these were in scope for the MVP because
each of them requires the ledger to already exist before it can be
built or tuned.

| Deferred | Why safe to defer |
|---|---|
| **I(c) — LLM importance rating (E3)** | Add only after ledger shows where formula fails. Additive term slots in without rearchitecting. |
| **LLM canonicalization (E1)** | Existing ontology cluster-merge covers the worst aliasing. Duplicate concept pages are annoying, not corrupting. |
| **Promotion gate (E4)** | Junk detection layer. Deferred until we see if the formula alone produces junk pages. |
| **`decay` / demotion** | Nothing to demote yet. Monotonic growth harmless for weeks at current corpus size. |
| **`connect` / creative recombination** | Speculative output needs populated concept layer to recombine over. |
| **Learned weights** | Requires labels — the ledger + afternoon test protocol generate them as a byproduct. |
| **Intent inference (current task)** | L4 concern, not consolidation. Fast + embedding, keeps surfacing latency at zero. Adding it here would violate D-041. |
| **Embedding-based goal_overlap** | Keyword overlap is enough to prove the term earns its place. Voyage embedding upgrade is v2. |
| **Emotional processing** | Never. Machine-labeling emotional life is high-creep, low-value. |

### 3. The Karpathy governance problem MIKAI is trying to solve

Karpathy hand-writes his wiki. He decides what deserves a page.
Because a human is in the loop, he doesn't need canonicalization
infrastructure, salience gates, or automated promotion.

MIKAI has NO human at authoring time (that's the whole point). So
governance has to be programmatic. The MVP implements Karpathy's
*pattern* (freeform pages + wikilinks) with automation's *scale*, and
the salience formula is what replaces Karpathy's human judgment about
"does this deserve a page?"

Read the concept pages you get with that lens: they replace Karpathy's
"I'll write one about that" moment. Are they the pages Karpathy WOULD
have written for himself in your position?

### 4. Entity vs concept: unified in MVP

You explicitly rejected the entity/concept split for the MVP —
"Karpathy move, no taxonomy, one bucket." So `promote` uses both
sources (ontology + n-grams) with the same formula, writes to one
directory, uses one ledger.

**What this reveals:** the current top-10 is entity-biased because
ontology entities have N=100+ mentions while extracted concept n-grams
have N=5-15. Weights all = 1 means the concept n-grams get buried.
This isn't a bug — it's calibration data. You'll want to tune weights
(likely boost `spread` and lower `base_activation`'s effective weight)
if you want concepts to compete with entities on equal footing.

### 5. The canonicalization tax — deferred but real

Wikipedia's hard-won lesson: notability is easy, redirects are what
keep one topic = one page. In the ledger, you'll see:
- `claude`, `claude-code`, `Claude Code` as 3 separate candidates
- `mikai` and probably `MIKAI` as separate rows
- Various variants of concepts appearing separately

These are the exact problems E1 (LLM canonicalization) would solve.
For now, the duplication is visible in the ledger but not resolved.

### 6. Salience is non-stationary — the reframe

"Worthy" is NOT a property of the concept. It's a property of
(concept × current goals × time). What matters today ("MIKAI Sunday
build") is ambient in 2 months. What was ambient in May ("Graphiti
patching") is background now.

**The MVP doesn't have demotion yet.** Every promoted page stays
promoted forever. Fine for now (corpus size is small) but the entire
architecture is only safe long-term when `decay` ships. Once demotion
is cheap, promotion errors become cheap. Currently, promotion errors
are irreversible.

### 7. The consistency wobble

A frontier LLM shown good evidence makes reasonable one-shot promotion
calls. What it CANNOT do is hold a stable threshold across thousands
of independent calls over months. Uncalibrated per-item judgment
drifts.

The MVP's design commitment: **make the score deterministic. Let the
LLM only do what needs language understanding.** The MVP's ONLY LLM
call per pass is the 3-sentence summary per promoted concept. Everything
else is math. This is why weights are visible and inspectable in every
concept page's "Salience breakdown" section — you can debug why a
concept did or didn't promote just by reading the page.

### 8. What Brian said he wants that the MVP does NOT yet support

Your exact quote from earlier this session:
> "give some inductive things that I want (users can say: I want to
> learn chinese, I want to pick a proposal spot in China, I need to
> finish so and so build for MIKAI by Sunday)"

**The MVP's `goal_overlap` term reads from USER_MODEL.md Current
section only.** There's no way to inject inductive goals mid-test
without editing USER_MODEL.md and rerunning. This is a gap for the
afternoon test protocol below — a v2 addition would be a
`--inductive-goals` flag that adds tokens to the goal set.

For the current test: if you want to test inductive goals, edit
USER_MODEL.md's Current section to include the goal statements, then
rerun `promote --dry-run` to see how rankings shift.

### 9. Retrieval bugs still open (unrelated to MVP but affecting Test §)

From the session's earlier work on retrieval quality:

- **Bug #1 shipped:** Wiki ingest dedup fix — content-diff no longer
  bypasses (header_ts, source, name) match. Prevents future duplicate
  writes.
- **Bug #5 shipped:** Same-day claude-code contamination filter in
  `_fts_hits()`. Kills recursive-contamination retrieval failure.
- **FTS slug dedup shipped:** `WikiFTS.build()` now dedups by slug.
  Historic duplicates in FTS demoted.
- **Bug #2 pending:** Destructive rewrite of `wiki.md` to eliminate
  historical duplicates. Requires explicit approval.
- **Bug #3 pending:** Parent-document retrieval (return full turn +
  surrounding turns when a match is scored). Would fix human-side
  retrieval bias.
- **Bug #4 pending:** BM25 title-boost for exact thread-name matches.

None of these affect the promote MVP directly (it uses WikiIndex not
FTS), but they affect the `mikai_ask` retrieval that would consume
these concept pages once wikilinks are wired.

---

## The afternoon test protocol (Fable's spec)

Design of a real 3-hour test that tells you whether LLM + formula
beats formula alone.

### Setup

- **Sample:** 30-day slice (~150 sections). Do not test on the full
  27MB — confounds context-length effects with judgment quality.
- **One goal set:** whatever's in USER_MODEL.md Current right now.
- **Before looking at anything else:** free-list your top 10 salient
  concepts from memory. This is the anchoring-free gold — write it in
  a text file, do NOT peek at the ledger first.

### Compare

- **Formula ranking:** already in `wiki-salience.md`, top 10 by S.
- **LLM-only ranking:** one prompt asking the LLM to rank the same
  candidate pool by salience given the same goal set.
- **Hybrid:** simple rank-fusion (average rank across the two systems).

### Metrics

- **Primary:** recall@10 of your free-listed gold for each system.
- **Secondary:** hand-inspect the disjoint picks. What does each system
  see that the other missed? Rationales for divergence tell you which
  formula term the LLM is implicitly weighting differently.

### Falsification

**The hybrid hypothesis dies if BOTH:**
1. Concepts the LLM ranks highly that the formula misses are
   predominantly labeled "no" in your gold (LLM-unique precision under
   ~30%), AND
2. Fused NDCG@20 ≤ formula-only NDCG within run-to-run noise.

That result says LLM judgment is either redundant with frequency +
goal-similarity, or actively noisy. Keep E1/E2 (structural roles),
drop E3/E4 (judgment roles). This is the strongest evidence the
formula's design was correct without LLM augmentation.

### What signals the hybrid IS working

- LLM recovers concepts from your gold list that the formula missed.
- LLM's rationales pattern-match to a specific term you can then boost
  in the formula (e.g., "LLM consistently ranks concepts by 'you'd
  need this at 3am' — that's I(c), you should add it to the formula").

---

## Reading the ledger and the concept pages

### What the ledger shows

```
| Rank | Concept | S | base | spread | goal | mentions | Promoted? |
```

Every scored candidate. The per-term breakdown lets you diagnose why
each promoted or didn't:
- **High base, low spread:** intense in one stream, not spread.
  Probably a burst of debugging chatter, not durable.
- **Low base, high spread:** appears in many sources but rarely.
  Could be genuinely important cross-context OR could be a common
  word appearing incidentally.
- **High goal_overlap:** the concept name literally shares tokens
  with your USER_MODEL.md Current section. Trust this term more than
  the others for "does this match what Brian is thinking about right
  now."

### What each concept page shows

```yaml
---
name: <full name>
slug: <kebab-case>
kind: entity|concept
promoted_at: <ISO ts>
salience_score: <S>
n_mentions: <int>
---

# <Name>

<3-sentence LLM-authored summary from 8 mention excerpts>

## Salience breakdown
- **S = <total>**
- base_activation: <value>
- spread: <n> (stream1, stream2, ...)
- goal_overlap: <n>

## Mentions (<N> sections)
- [[ts — section name]] (source: ...)
- ...
```

**Trust check on the LLM summary:** the prompt explicitly forbids
invention and instructs "if the excerpts don't support a claim, say
so plainly." If a summary makes a claim the excerpts can't support,
that's a signal to look at.

### The three questions to hold while reviewing

1. **Would Karpathy have written this page for himself?** If not,
   which formula term is over-weighting this candidate?
2. **What's missing from the top 10 that should be there?** If you
   free-listed concepts that don't appear, that's the recall@10 gap
   — either the formula doesn't see them, or they didn't cross the
   threshold at cap=10.
3. **What's promoted that shouldn't be?** If a candidate feels
   generic or unimportant, look at its breakdown. Which term inflated
   its score? That term needs a weight adjustment.

---

## Weight-tuning hypotheses (evidence-driven, not speculative)

Based on the dry-run ranking (before the real run), likely tuning
directions:

**If concept n-grams (Task State Awareness, Agent Memory, Consolidation
Layer) are missing from top 20:**
- Lower `base_activation` weight (currently effectively 1) or apply a
  log-cap. Ontology entities dominate on raw mention count; capping
  base_activation would let spread and goal_overlap matter more.
- OR: raise the mention threshold for ontology entries so only the
  top 50 entities compete, leaving room for concepts.

**If `claude` / `claude-code` / `Claude Code` all promote as separate:**
- Deferred E1 canonicalization is the real fix. Interim: hand-add
  aliases to a `~/.mikai/wiki/concept-aliases.json` file that the
  scoring step consults.

**If `goal_overlap` is 0 for concepts that should score:**
- Your USER_MODEL.md Current section vocabulary doesn't match the
  concept's name tokens. Either expand Current with the concept
  vocabulary (immediate fix) or upgrade to embedding-based similarity
  (v2 — proper fix, requires Voyage).

**If the top 10 is stable across days:**
- Good sign. Salience is durable at your current corpus size.
- Once `decay` ships and demotion is cheap, we can measure churn as
  a first-class quality metric.

---

## Session-open threads (not affecting MVP but still queued)

- Entity inbox review (`docs/ENTITY_INBOX_REVIEW.html`) — 30 proposals
  awaiting your verdict. Not blocking; the MVP treats entities and
  concepts uniformly.
- Doctrine reconciliation (docs on this branch vs main) — pending
  your scope call (A/B/C).
- Consolidation architecture diagram (`docs/CONSOLIDATION_ARCHITECTURE.html`)
  — still uses the pre-Fable-II formula shape. Should update to reflect
  the corrected form (base_activation subsumes density + recency).

---

## What to do after reading the output

1. **Free-list first.** Before opening `wiki-salience.md`, write your
   top 10 salient concepts from memory to a text file. This is the gold.
2. **Read the ledger.** Note which of your gold appear in the ledger's
   top 20. That's your baseline recall.
3. **Read the 10 concept pages.** Do the LLM summaries hold up against
   the excerpts? Are the per-term breakdowns interpretable?
4. **Decide weight tuning.** Based on where the gaps are.
5. **Then, and only then:** run the afternoon test comparing formula
   vs LLM-only vs hybrid on the same candidate pool.

Every step is reversible. The formula is additive. New terms bolt on
without rearchitecting. That's the property a magnum-opus primitive
should have.
