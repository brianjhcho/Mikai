# MIKAI Wiki Ingestion Log

Per-round tracking of what was ingested, what worked, what broke, and what to change next round. Complements the per-vault `.ingest-batches/*.md` manifests (which record the source list) with the *reasoning* and *learnings*.

Substrate: nashsu vendored (v0.6.9) + MIKAI mikai-template, headless CLI at `infra/nashsu/vendor/src/mikai-cli/ingest.ts`. Two vaults maintained in lockstep for A/B: `~/.mikai/wiki-mikai-parallel-test/` (workers=8) and `~/.mikai/wiki-mikai-new/` (workers=1).

Selection lineage:
- **R1** — hand-curated 46 "golden set" (2026-08-15)
- **R2** — keyword-filtered claude-thread candidates, hand-reviewed to 13 (2026-08-27)
- **R3** — Level 3.1 deterministic salience scorer, top-15 auto (2026-08-31)
- **R4** — Level 3.1 + Brian-curated Claude.ai project sidebars (in-flight)

---

## R1 — Golden set (2026-08-15)

**Selected**: 46 sources hand-picked by Brian, spanning oldest 100 wiki-raw sections; mix of Claude threads (biggest MIKAI conversations) + Apple Notes journals.

**Output**:
- Parallel: 372 pages / 121,860 words / 106 wisdom quotes / 46/46 sources
- Serial: 355 pages / 121,493 words / 100 wisdom quotes / 45/46 sources (1 dropped)

**Wall clock**: Parallel 52 min · Serial 5h 20m

### Problems

- Serial dropped 1 source (`self-skill-creation-tools`) — 46-min `claude -p` call completed but nashsu skipped the cache write (truncated `queries/can-mikai-l4-ride-honcho-as-user-model-substrate.md` couldn't be repaired). Parallel produced this source without error.
- Fragmentation surfaced: 262 semantically-adjacent concept pairs across the two vaults (e.g. `dormant-agent-model` (S) vs `agent-dormancy` (P)). Confirmed cross-vault concept slug Jaccard = 17.09% — well above the 7% baseline of pure LLM nondeterminism.
- Serial had TWO truncation errors on cross-referencing pages (`comparisons/dalio-vs-village-on-debt.md`, `queries/can-mikai-l4-ride-honcho-as-user-model-substrate.md`) — LLM hit an implicit output-length ceiling on complex synthesis pages. Parallel had zero truncation errors.

### Insights

- Parallel wins on almost every axis: coverage (46 vs 45), journal decomposition (27 vs 4 pages), wikilink density (1894 vs 1804), wisdom quotes (106 vs 100/101), and 6× wall clock.
- Serial wins only on concept consolidation (196 vs 174) and comparisons (3 vs 0) — the warm-index densifies analytical page types but homogenizes routing (fewer journals/goals/habits).
- 245 files produced from 46 sources = ~5.3 files/source average. Big threads (~150-300 KB) produce 15-30 files each; short apple-notes produce 3-8.

### Future decisions

- **Ship parallel to production** — recall lift + throughput dominates the concept-consolidation loss.
- **Investigate MCP loop overhead** — one call took 72 min without `--tools ""`; nashsu spawns nashsu-llm-wiki + oh-my-claudecode MCP servers on every `claude -p`. Consider passing `--tools ""` to eliminate.
- Post-ingest concept dedup needed (`src/lib/dedup.ts` already exists in nashsu vendor tree — dormant, only wired to UI).

### Verdict

Baseline for all subsequent A/B. Not yet swapped to production (deferred pending broader-corpus test).

---

## R2 — MIKAI-topic Claude threads (2026-08-27)

**Selected**: 13 threads discovered via wiki-raw keyword filter (`mikai`, `noonchi`, `sumimasen`, `l3`, `l4`, `graphiti`, `nashsu`, `cockpit`, plus body scan). Manually curated from 17 keyword-hit matches; 3 already in R1 vault; 1 excluded (Wind-resistant plants — false positive).

Manifest: `~/.mikai/wiki-mikai-{parallel-test,new}/.ingest-batches/R2-2026-08-27-mikai-threads.md`

**Output** (parallel vault):
- pages 372 → 460 (+88)
- words 121,860 → 163,315 (+41,455)
- concepts 174 → 215 (+41); entities 57 → 75 (+18); goals 7 → 16 (+9); sources 46 → 59 (+13)

**Output** (serial vault):
- pages 355 → 502 (+147)
- concepts 196 → 274 (+78); entities 56 → 95 (+39); comparisons 3 → 6 (+3)
- 2 truncation ERRs (Debt mechanisms, self-skill-creation) — same LLM-length pattern as R1

**Wall clock**: Parallel ~30 min · Serial ~2 h

### Problems

- Wiki-raw stale check surfaced: `~/.mikai/wiki-raw/wiki.md` last modified 2026-08-11. Threads Brian created in his Claude.ai MIKA TECH project after that date (e.g. "MIKAI projection versus consolidation mechanics") ARE NOT in the candidate pool. `com.mikai.claude-threads` LaunchAgent deliberately stopped during Graphiti deprecation; no reactivation yet.
- False-positive noise in keyword filter: "Wind-resistant plants for apartment living" (163KB, 144 turns) matched via casual MIKAI mention in body. Skipped from R2.
- Serial truncation pattern held: cross-thread synthesis pages (`comparisons/dalio-vs-village-on-debt.md`) hit output-length ceiling. Parallel had none.

### Insights

- Parallel R2 continued the pattern: better coverage, more segmentation, no truncation.
- **Recursive contamination confirmed**: Build C QA harness answers cited the R2 comparison report itself as a source of Sumimasen context — the report we wrote into `wiki/comparisons/` now pollutes future retrieval. Fix: filter comparisons/ from retrieval or add a same-day filter analogous to the mikai_ask same-day-claude-code filter.
- Same-topic thread concentration is real: 4 of the 13 candidates were about MIKAI product design directly (agent memory, task-state, harnesses, mem.ai); the others were adjacent (systems-thinking, second-brain, memory).

### Future decisions

- **Wire nashsu's `dedup-runner.ts` into headless CLI** — nashsu already ships LLM-based cross-slug dedup (built for UI-triggered maintenance action), but our headless path never invokes it. This is Phase 1 of the Session-11 plan.
- **Reactivate `claude-threads-runner.sh` OR one-shot manual capture** — needed before R4 can consider post-Aug-11 threads.
- Consider adding `wiki/comparisons/*` to retrieval-side exclusion filter (product surface, not substrate).

### Verdict

Parallel ships. Serial's density gains on concepts/entities/comparisons are real but paired with truncation risk that gets worse as the vault grows.

---

## R3 — Level 3.1 deterministic salience (2026-08-31)

**Selected**: 15 sources auto-picked by `eval/r3_candidate_salience.py` (Level 3.1). Formula: `weighted_concept_intersection + weighted_personal_intersection + 3·goal_overlap + recency + substance + aggregation_bonus`. No blacklist — off-topic filtered by signal-density alone.

Scoring lineage:
- **Level 2** — swapped saturated `concept_overlap` count for `Σ log(1+in-degree)` weighted intersection (min slug length 5). Ranking became discriminating. But noise blacklist gave false-negatives on personal-domain clusters.
- **Level 3** — added `weighted_personal` from a compiled Brian-profile vocabulary (USER_MODEL.md 1.5 · PROFILE.md 1.0 · BRAIN.md priorities 0.7 · entity/wisdom/goal slugs 0.5 · journal tags 0.3). Length-normalized so long bodies don't linearly accumulate hits.
- **Level 3.1** — removed noise blacklist entirely + added `aggregation_bonus` for multi-topic dense threads. Yoga rose #8 → #6 after Brian correctly identified it as a health/posture cluster, not off-topic.

Reports: `eval/reports/r3_candidates_level3-1_2026-08-31.{md,json}`
Manifest: `~/.mikai/wiki-mikai-{parallel-test,new}/.ingest-batches/R3-2026-08-31-mikai-followup.md`

**Output** (parallel vault, mid-flight at time of writing):
- 74 of 76 sources committed (46 R1 cache-hits + 13 R2 cache-hits + 15 new R3, minus 4 duplicate patterns from bridge regex matches). Weighted yoga last source, still running.
- New R3 pages: ~224 committed pre-yoga; "My Mentors" thread alone produced 47.

**Output** (serial vault): 37/76, ~1h in, will continue overnight.

**Wall clock**: Parallel expected ~1.5-2h total (long tail from big threads: Chip war 37 min, My Mentors 22 min, Dining room 22 min, ENTJ vs INTJ 13 min).

### Problems

- Initial Level 1 output was unusable — `concept_overlap` saturated at 1.00 for every candidate (naive substring hits on 645 short slugs). Rank collapsed to `goal_overlap × 3`.
- Level 2 fixed with weighted intersection but retained a hardcoded noise blacklist which Brian caught as false-negative on legitimate personal-domain clusters (yoga = health/posture, plants = home life, dining = domestic).
- Level 3 first pass had scale runaway (390 units) because personal-vocab hits accumulated linearly on long bodies. Fixed with log length-normalization.
- Bridge regex matches "MIKA/REMY TECH" produced 3 duplicates (one main thread + 2 perplexity-wrapped variants). Not fatal, just extra ingest cost.
- Recursive contamination NOW EVEN WORSE: R3 will find R2 comparison + R3 candidate-list report in `wiki/comparisons/`. Retrieval-side filter definitely needed.

### Insights

- **Ranking is a levels-of-refinement problem, not one-shot design.** Iterative sanity-check with Brian caught yoga false-negative and led to material scoring improvement (blacklist removal + aggregation bonus).
- **Personal-vocab is a much richer signal than concept-vocab alone** — 1,278 personal tokens vs 210 concept slugs. Personal signal dominates but length-normalization keeps it well-scaled.
- **Serial produces denser extractions per source** — consistently more files per source (e.g. Chip war: serial 24 files vs parallel 16). Warm-index bias helping analytical page types.
- **Aggregation bonus works** — it moved the ranking of long dense threads up meaningfully without swamping short high-signal picks.

### Future decisions

- **Phase 1: wire nashsu's dedup-runner into headless CLI** (post-R3, deferred from R2)
- **Phase 3.3: post-ingest community detection** — after each ingest, run Louvain over the wikilink graph → cluster labels become implicit "project" buckets. Uses the extraction LLM's own linking decisions as ground truth. Autonomous alternative to hand-curating project keywords.
- **Retrieval-side filter for `wiki/comparisons/*`** — stop the recursive contamination cycle.
- **Fine-tune weights per Brian's feedback** — level 3.2 could weight `weighted_personal` slightly lower once the vocab grows beyond current ~1,300 tokens (natural cap emerges).

### Verdict

**Parallel R3 complete 2026-08-31.** 665 pages / 281k words / 118 wisdom quotes / 76 sources.

Deltas from post-R2 baseline: +205 pages, +117k words, +107 concepts, +63 entities, +8 comparisons, +2 wisdom.

**12 pages/source average** — 2.3× the R1 rate. Level 3.1 picks were dense: My Mentors → 47 files, Society-of-conglomerate-brands → 26, Dining room → 19, Weighted yoga → 15, Chip war → 16, Kenyan fruits → 11, Reborn Rich → 14, Varoufakis/Stiglitz → 14, ENTJ-thread → 14.

Level 3.1 ranking is meaningfully better than Level 2. Yoga (health/posture cluster) surfaced correctly; false positives filtered by signal density alone. Serial R3 still running; verdict on cross-vault comparison deferred.

Wall clock: **parallel ~4h** (spanning R1+R2 cache-hits + 15 R3 fresh + huge tail from Chip war 37 min + My Mentors 22 min + Dining room 22 min + Weighted yoga 49 min).

---

## R4 — Level 3.1 top 30 against refreshed wiki-raw (2026-08-31)

**Selected**: 30 sources auto-picked by Level 3.1 scorer against the fresh wiki-raw (69 → 139 unique claude threads after 2026-08-30 22:18 refresh). Serial vault SKIPPED — parallel is canonical (v4) per Brian's decision.

Manifest: `~/.mikai/wiki-mikai-parallel-test/.ingest-batches/R4-2026-08-31-level3-1-top30.md`

**Output**: 665 → **1012 pages** (+347, largest single-round delta). Concepts +219, entities +53, wisdom +38 quotes, queries +26, sources +39. Words 281k → 445k.

**Errors**: 1 (`Developer opportunities in emerging markets` — nashsu couldn't repair a truncated `wiki/log.md` on write; other pages from that source landed).

**Wall clock**: ~4.5h parallel workers=8. Bimodal: MIKAI-foundation threads 40-50 min each, perplexity queries 100-800s.

### Insights

- **Vault crossed 1000 pages.** Fragmentation pair-count now expected to exceed R3's 319 (parallel).
- **Level 4 scorer landed in parallel with the ingest** (in `eval/r3_candidate_salience.py`). Adds Axis A (retrieval hit potential), B (vocabulary novelty), C (alias risk), G (episodic/semantic) from the 8-discipline framework. R5 will use Level 4.
- **8-discipline evaluation framework formalized** at bottom of this doc. Grounds the "second brain" folk term in real academic fields (IR, KR, ER, Graph, Recommender, PIM, Cognitive Memory, HCI/JITAI).
- **Truncation ERR on log.md is the growth-scaling issue Fable predicted** — as index grows, LLM-driven index-line append hits output length ceilings. Doesn't lose content but loses log entries.
- **Wiki-raw refresh unlocked 70 new claude threads** (69 → 139); several MIKAI-foundational threads that couldn't previously be ingested rose to the top of L3.1's rank (Build Discussion Semantic Search, Voice Notes Memory Architecture, Making AI Invisible).

### Future decisions (log for next session)

- **R5 planning gate**: NEXT ROUND should be a **dedup pass, not more ingest.** 500+ fragmentation pairs projected; ingesting more without dedup compounds debt.
- **Wire nashsu dedup with Fable's 3 modifications** — retire-not-delete, confidence-banded execution, feed-bodies-not-descriptions. ~1 day work.
- **Fix `wiki/comparisons/*` recursive contamination** — session reports written into vault leak into retrieval. Relocate to `.mikai-reports/` or add retrieval-side filter. ~10 min.
- **Upstream bug fixes to nashsu** — wisdom language-guard exemption + parseFileBlocks split-separator. Reduce technical-debt drift.
- **Enable embeddings via Ollama** (subscription-auth safe) — unlocks dormant nashsu machinery: dedup gets embedding pre-filter, retrieval gets vector-augmented Surface B.
- **Hierarchy induction pass** (new module — Louvain over wikilink graph, LLM cluster naming, parent hub creation). Handles the ~400+ pair residue dedup can't merge.
- **Level 4 tuning** — axB (novelty) currently over-weights off-topic novel content (basketball, plants). Gate novelty by personal-relevance threshold. axG heuristic too coarse.

### Verdict

Ingested. Wiki at 1012 pages / 445k words / 156 wisdom quotes. **Not ready to ship** without dedup pass. Next-round order: R5 = dedup, R6 = hierarchy, R7 = next batch of new ingest.

---

## Divergence audit — vs vanilla nashsu (2026-08-31)

### Necessary (couldn't run headless at all without them)

| Divergence | Location | Rationale |
|---|---|---|
| Node fs shim | `infra/nashsu/shims/fs-shim.ts` | Nashsu fs = Tauri Rust; we're Node |
| Tauri-core shim | `infra/nashsu/shims/tauri-core.ts` | Same |
| Node claude-p transport | `infra/nashsu/transport/claude-cli-transport.ts` | Nashsu spawns via Rust; we via Node child_process |
| tsconfig-node.json | `infra/nashsu/tsconfig-node.json` | Path alias overrides |
| Headless CLI | `src/mikai-cli/ingest.ts`, `init-project.ts` | Nashsu has no headless entrypoint |
| Suppress embeddings/multimodal/mineru at store-seed | `src/mikai-cli/ingest.ts` | Those code paths need the Rust `invoke` we can't provide |

**Risk**: none material. Well-documented, reproducible from `infra/nashsu/patches/`.

### Enhancement (chose to add — patch-tracked)

| Divergence | Rationale | Risk |
|---|---|---|
| Worker clamp [1,5] → [1,16] in `src/lib/ingest-queue.ts:91` | Throughput at 8-16 workers | Merge conflict on nashsu v0.7+ — patch file mitigates |
| `mikaiTemplate` (wisdom page-type + conventions) in `src/lib/templates.ts` | Personal-graph needs quote-aggregation surface | Same |
| `.obsidian/` seeding + graph.json filter in `init-project.ts` | Obsidian-usability out of box | Same |
| Force `outputLanguage: "English"` via setState | Nashsu was dropping pages with foreign-language quotes | Same |

### Bug fixes (found during use, patched locally, NOT upstreamed)

| Fix | What it addresses | Correctness note |
|---|---|---|
| Wisdom language-guard exemption in `src/lib/ingest.ts` | Wisdom pages contain quote-language content; guard was dropping them | **Coarse workaround** — exempts wisdom pages wholesale from the language check |
| `parseFileBlocks` split-separator preprocessor | LLM emits `---\nEND FILE---` on separate lines, breaking parser | Correct fix |

**Refinement to file upstream (2026-08-31 clarification)**: the language guard's right shape is **content-aware, not page-type-aware**. Rule: narrative prose must be English (concept/entity/journal/source/wisdom/query/etc. all follow this); blockquote lines (`^>` in body) preserve source language verbatim, so they get SKIPPED by the check. This applies to all page types uniformly:
- Concept page in Korean prose → drop (bug — LLM output the summary in the source's language)
- Wisdom page with English intro + Korean quotes + English attribution → keep
- English concept page with a Korean quote in its `## Notable Quotes` section → keep

Current patch (wisdom-page exemption) is too broad — it lets a wisdom page with 100% Korean prose through. Upstream fix should scope the check to non-blockquote lines only, not to page type.

**Risk**: **technical debt.** If nashsu fixes these differently in v0.7, reconciliation needed. **Action logged: file upstream issues (both fixes) + refactor language-guard exemption to blockquote-aware once accepted.**

### Dormant nashsu capabilities we HAVE NOT USED

- `src/lib/dedup.ts` + `dedup_embedding.ts` + `dedup-runner.ts` — cross-slug LLM dedup — never invoked (UI-only wiring)
- `src/lib/embedding.ts` — RAG chunk + vector search — explicitly disabled at store-seed
- Nashsu review-stage stub — running default

**Risk**: we're using **~70% of nashsu's designed capability.** Dormant 30% includes exactly the mechanisms that would solve today's biggest quality issue (fragmentation).

### MIKAI-invented layers (no nashsu equivalent)

| Layer | State | Risk |
|---|---|---|
| Two-vault parallel/serial A/B methodology | Retired at v4 (parallel canonical) | Doubled ingest cost R1-R3; produced real insights |
| Candidate salience scorer L1→L4 | Active, disposable per Fable | Scheduling infra outside nashsu, not architectural drift |
| Session reports written INTO `wiki/comparisons/` | **Active problem** | Recursive contamination in retrieval, flagged in Build C QA test |

### Verdict — was "ingesting verbatim with nashsu" the right call?

**Yes, and we're mostly holding that discipline.** All source-file modifications inline-marked or patch-tracked. Node runtime translation well-documented. Divergences serve either necessity (Tauri→Node) or capability nashsu didn't ship (headless CLI).

**Where we've drifted from original commitment:**
1. Not using dormant capabilities — dedup + embeddings shipped, ignored. Restoring these = Session-12 work
2. `comparisons/` contamination — pure MIKAI-added noise in substrate. Fixable in ~10 min
3. Haven't upstreamed bug fixes — technical debt grows with each nashsu upgrade

---

## Evaluation framework — the 8 disciplines MIKAI borrows from

MIKAI's second-brain problem sits at the intersection of ~8 well-formed academic + engineering fields. Naming them properly gives the ranker + review process rigor. The dedup vs hierarchy vs alias distinction (Fable's 2026-08-31 analysis) shows why: "second brain" as folk term collapses genuinely different sub-problems.

The formal problem MIKAI solves is **knowledge base construction (KBC)** — well-studied in NLP/IR. Six sub-problems that each need different mechanisms:

1. **Extraction fidelity** — does the LLM extract a real, atomic idea? (nashsu Pass-1)
2. **Naming / slug canonicalization** — same idea → same slug across independent extractions? (dedup, Fable Q1)
3. **Placement** — right page type (concept vs entity vs journal)? (page-type routing)
4. **Consolidation** — same-idea-different-slug → merged? (dedup)
5. **Hierarchy** — related-but-distinct concepts → organized under parent hubs? (Dream Pass)
6. **Retrieval readiness** — downstream consumers can find the right page? (mikai_ask)

### The 8 disciplines

| # | Discipline | What it studies | MIKAI borrows |
|---|---|---|---|
| 1 | Information Retrieval (IR) | Ranked access to text corpora at query time | precision@K, recall@K, MRR, NDCG, BM25, embedding retrieval, reranking |
| 2 | Knowledge Representation (KR) | Formal encoding of what a system knows | ontologies, taxonomies, controlled vocabularies |
| 3 | Entity Resolution / Record Linkage | Deciding when two records refer to the same real-world thing | blocking, pairwise matching, transitive closure, canonicalization (Fellegi-Sunter 1969) |
| 4 | Graph Theory / Network Science | Structure of interconnected entities | PageRank, in-degree centrality, Louvain community detection |
| 5 | Recommender Systems | What content to surface to a specific user | content-based, hybrid, explore/exploit |
| 6 | Personal Information Management (PIM) | How individuals capture / find / re-find their own info | Memex (Bush 1945), Malone's piles-vs-files (1983), keep/find/re-find split (Jones) |
| 7 | Cognitive Science of Memory | How human memory works | episodic vs semantic vs procedural (Tulving 1972); encoding specificity; spaced repetition |
| 8 | HCI / Ambient Systems | Attention-aware interfaces | Weiser's Calm Computing (1991); JITAI (Nahum-Shani); interruption cost |

Adjacent: Software Engineering (event sourcing, CRDT, versioning) powers Dream's non-destructive supersession invariant. NLP / Information Extraction is nashsu's Pass-1 pipeline.

### The 8-axis candidate scorecard

For each un-ingested source, rate 0-3 on each axis. Total possible: 24. **The pre-ingest ranker aims to compute as many of these deterministically as possible; unautomated axes stay human-judgment for now.**

| Axis | Discipline | Question | Automated in Level 3.1? | Automatable? |
|---|---|---|---|---|
| A. Retrieval hit potential | IR | Will future queries land on pages this produces? | No | Yes — overlap against `queries/*.md` tokens |
| B. Vocabulary novelty | KR | Introduces slugs the vault doesn't have? | No | Yes — new noun-phrase count vs existing concept set |
| C. Alias risk | Entity Resolution | Will produce dupes of existing concepts? | No | Yes — edit distance / substring / embedding sim against existing slugs |
| D. Hub-formation likelihood | Graph Theory | Will its central concept become a high-in-degree hub? | Partially (via `weighted_concept`) | Yes — Louvain cluster membership + centrality predict |
| E. Personal-preference signal | Recommender | Reflects a Brian-topic engaged with repeatedly? | Yes (`weighted_personal`) | Fully automated |
| F. Keep-vs-find balance | PIM | Would Brian want this re-findable? | No | Hard — requires future-query prediction |
| G. Episodic vs semantic | Cognitive Science | Time-anchored moment or timeless idea? | No | Yes — title date-pattern heuristic + body tense/frame analysis |
| H. Attention-worthiness | HCI/JITAI | Would surfacing this earn its trust cost? | No | Hard — requires downstream Sumimasen model |

**Fully automatable (5 of 8)**: A, B, C, D, G. These become Level 4 features.
**Requires human or downstream model (3 of 8)**: F, H (near-impossible without user feedback loop) and partially E (already automated but weighting is judgment-based).

### Success criteria per pass

- **Ingest pre-scorer** (this doc's ranker): success = downstream post-ingest recall@10 lift on GOALS.md (Fable's Session-10 verdict). Not a peer of any of the passes below.
- **Nashsu dedup pass** (Phase 1, wire when Fable's 3 modifications land): success = **true-duplicate merges executed**, not pair-count reduction. Aliases only (~30-80 pairs in current vault).
- **Dream pass** (deferred, design in `docs/DREAM_PASS.md`): success = threshold-banded merge inbox + hierarchy hub creation. Handles the ~200-500 missing-hierarchy residue that dedup can't touch.
- **Lint pass** (docs/LINT_PASS.md): success = broken-wikilink count + orphan-page count reduced. Structural only.

The four passes are **complementary, not competing** — each addresses a different sub-problem of KBC.

---

## Standing checklist for every ingestion round

- [ ] Bridge sources into `raw/sources/` for both vaults
- [ ] Write manifest to both `.ingest-batches/` dirs
- [ ] Fire parallel (workers=8) and serial (workers=1) in background with `caffeinate`
- [ ] Arm monitor task filtering `[nashsu-cli] (OK|FAIL|ERR)` on the log
- [ ] Report pages/words/wisdom deltas on completion
- [ ] Copy comparison report into both vaults' `wiki/comparisons/` for Obsidian browsability
- [ ] Update THIS DOC with per-round problems / insights / future decisions
