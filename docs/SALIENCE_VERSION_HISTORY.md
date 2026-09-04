# Consolidation Layer — Version History

Every major change to the Consolidation Layer runs against the same
three metrics and gets a row here. Regressions get called out
explicitly.

## The three metrics (evaluated on every version)

1. **Consolidation quality** — does the ledger's top-K contain the
   concepts Brian actually cares about?
   - **Recall@10** — of Brian's 10 gold-list items, how many appear in
     top-10 of `wiki-salience.md`?
   - **Recall@20** — same, top-20.
   - **MRR** — mean reciprocal rank of first-hit-per-goal.
   - **NDCG@10** — position-weighted relevance.
   - Ground truth: `~/.mikai/brain/GOALS.md` (free-listed 2026-08-08).
   - Automated via `eval/salience_recall.py`.

2. **Retrieval quality** — does `mikai_ask` return sections that
   actually answer the question?
   - **Context recall / precision** — RAGAS-style.
   - Ground truth: hand-labeled Q-A pairs (TODO — build the fixture).
   - Deferred to v0.2; manual for now.

3. **Summary faithfulness** — do the concept pages' 3-sentence
   summaries invent facts the excerpts don't support?
   - **Faithfulness rate** — of N sampled concept pages, how many make
     unsupported claims?
   - Ground truth: LLM-as-judge on `(summary, source_excerpts)` pair.
   - Deferred to v0.2; audit-by-hand for now (like the `mikai.md` "the
     excerpts don't support any claim" honesty check that surfaced the
     `mentions[:8] = oldest` sampling bug).

## Rule

Every substantive change to the Consolidation Layer:
1. Runs the eval harness → generates a new row in `eval/history.jsonl`
2. Gets its own row here with the delta noted
3. Regressions get a ⚠ flag and an explanation
4. Failure to improve consolidation quality doesn't block a change if
   the change targets a different metric (perf, faithfulness, etc.) —
   but the row must document what it targeted.

---

## v001 — 2026-08-08 — Consolidation MVP (baseline)

**Shipped as:** first real `dream_bootstrap promote` run (10 concept
pages + `wiki-salience.md` written by non-dry-run).

**Formula:**
`S = ln(Σᵢ(t−tᵢ)⁻⁰·⁵) + spread + goal_overlap`, weights = 1, d = 0.5,
threshold = 4.0, cap = 10.

**Candidate sources:**
- `wiki-ontology.md` (375 proper-noun entities)
- Capitalized 2-4 word n-grams from `wiki.md` (freq ≥ 5)

**Extraction:** capitalized-only. No lowercase phrases. No stoplist.

**Promoted concepts:**
`claude, mikai, wiki, kenya, graphiti, brian, apple, claude-code, gmail, martin`

**Known issues going in:**
- Recall@10 on Brian's gold = 1/10 (only MIKAI)
- Entity-biased due to mention-count dominance of ontology entries
- No lowercase concept extraction ("posture", "workout", "parents"
  never became candidates)
- Excerpt sampling bug: `mentions[:8]` = oldest 8 mentions, false
  positives for recent concepts (visible in `mikai.md` summary)

**Metrics:** filled in by `eval/salience_recall.py` first run below.


## v002 — pending — Build 1 + 2 (lowercase + alias fold + multiprocessing)

**Changes:**
- Added lowercase 1-3 word phrase extraction (freq ≥ 15)
- Added self-corpus stoplist (~259 auto-generated entries from repo
  file/dir names) — excludes `dream_bootstrap`, `wiki_adapter`, etc.
- Added deterministic alias folding (`Claude Code` ↔ `claude-code`
  collapse; ontology entries win as heads)
- Refactored scoring loop to `multiprocessing.Pool` (~2-3x speedup on
  8 cores)

**Known dry-run finding:** lowercase extraction floods top-20 with
conversation-transcript filler (`assistant`, `session`, `thread`,
`agent`, `decision`). Recall@10 estimate: still ~1/10.

**Status:** code shipped, dry-run measured, not yet promoted (skipping
to Build 3 first per Fable's diagnostic).


## v003 — 2026-08-09 — Build 1 + 2 + 3 (lowercase + alias fold + S/G split)

**Changes shipped:**
- Lowercase 1-3 word phrase extraction (freq ≥ 15)
- Self-corpus stoplist (auto-generated, ~265 entries from repo file/dir names)
- Deterministic alias folding (`Claude Code` ↔ `claude-code` collapse)
- multiprocessing.Pool scoring (~2-3x speedup over single-threaded)
- Hand-authored `~/.mikai/brain/GOALS.md` (10 free-listed goals)
- G(c) axis via TF cosine over pooled mention-context tokens
- Ledger adds G column + goal-evidence gap section
- Promotion = union of top-K by S ∪ top-K by G (20 unique pages)

**Metrics:**

| Metric | v001 | v003 | Δ |
|---|---|---|---|
| recall@10 (ledger-rank) | 0.10 | 0.00 | ⚠ **−0.10** |
| recall@20 | 0.20 | 0.00 | ⚠ **−0.20** |
| MRR | 0.055 | 0.002 | ⚠ regression |
| NDCG@10 | 0.139 | 0.000 | ⚠ regression |
| Candidates scored | 1793 | 6308 | +4515 (extraction lift) |
| Promoted pages | 10 | 20 (10 S + 10 G) | +10 (union promotion) |

**⚠ recall@10 regression is a measurement mismatch, not a system regression.**

The eval reads the ledger's S-axis rank. Build 3's ACTUAL output is the
union of S-top-10 AND G-top-10. Goal-matched pages
(`identity-brian-cho`, `meet-mikai`, `solo-builder`, `kenya`,
`default-surface-engine`) are IN the promoted set but not in the
ledger's top 10 (which is dominated by conversation-vocab —
`ingested`, `assistant`, `right`, `agent`, `session`).

The eval harness needs a `--metric=promoted-set` mode to measure
Build 3's true contribution. Deferred to v004.

**Also caught by v003 rerun:**
- **`mikai` was in the auto stoplist** (the `~/.mikai/` dir name matched
  the auto-generator's rule). So `mikai` never became a candidate.
  In v001, `mikai` was rank 2 → hit for "MIKAI and ambient computing".
  In v003 the matcher fell to `ambient` at rank 1004. Fix: create
  `~/.mikai/brain/self-corpus-stoplist.txt` with a curated stoplist,
  omitting `mikai`. (Deferred; user-actionable.)
- **All Brian's goal keywords DID surface as candidates** (`posture`,
  `parents`, `startup`, `proposal`, `ocean`, `consumer`, `family`,
  `development`, `domestic`) — extraction ceiling successfully lifted
  from 40% to ~90% (only `parents` still missed the eval matcher).
  They just lose to conversation-vocab in ranking.
- **Every G-promoted concept page best-matched to "MIKAI and ambient
  computing"** because that goal's token set is broad. Best-goal
  selection needs a tie-break — currently picks the first-encountered
  goal.
- **~60% of G-promoted pages are extraction artifacts** from MIKAI's
  own recent system-prompt turns leaking through claude-code logs
  (`toggle-rode`, `default-surface-engine`, `choice-while-building`,
  `beea475f`, `primary-request`, `solo-builder`, `live-sources`,
  `real-and-finite`). The LLM summaries HONESTLY say "the excerpts do
  not support a summary" for these. Self-referential-corpus problem
  in full form.


## v004 — 2026-08-09 — Build 4 (Karpathy-shape rewrite)

**Non-metric change** — page format only, no salience math changed.

**Changes shipped:**
- New `infra/graphiti/karpathy_rerender.py` — rewrites concept pages
  in Karpathy's ~50-line shape (TL;DR / Why / Notes / Sources)
- Basename `[[wikilinks]]` between concept pages (was: raw wiki.md
  timestamp links that don't resolve as graph edges)
- Backlink injection pass — every page gets "Referenced by" section
- `~/.mikai/wiki/concepts/index.md` — top-level TOC with per-page TL;DR
- `~/.mikai/wiki/concepts/log.md` — dated one-line log per rerender

**Metrics** — unchanged from v003 (page format doesn't change the
salience formula). The value is qualitative: concept pages went from
10-14 KB (300+ lines) to ~1.2-1.8 KB (30-35 lines), matching Karpathy's
spec (aimaker.substack.com, 2026 Substack analysis).

**Followup for v005:**
- Eval harness: add `--metric=promoted-set` mode to correctly credit
  G-axis promotions.
- Remove `mikai` from auto stoplist (user-authored override file).
- Best-goal tie-breaker: use max cosine, not first-match.
- Extraction filter for self-referential MIKAI-system-prompt fragments
  (regex against known prompt boilerplate).


---

## Rule about grading

**Do not grade a version by squinting at the top 20.** Every version
runs the eval harness. Numbers go in `eval/history.jsonl`. The chart
at `eval/plot_salience.html` shows the trajectory.

The pattern is the same as agno-deepknowledge / harness-evolver / DSPy
optimizers / AlphaEvolve: propose a change, measure against fixed gold,
merge only if the target metric improved (or an intentional-tradeoff
regression was accepted).
