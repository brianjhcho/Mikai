All context needed is in hand (dream_bootstrap.py subcommand structure, consolidation.py's existing LLM-cluster pattern, the Budget/backup/audit house conventions). Here is the brief.

---

# MIKAI Salience Formula — Strategic Brief II

## 1. Post-1991 evolution of the base-level activation formula

**ACT-R itself.** Anderson & Schooler (1991) showed memory decay mirrors environmental need-odds; the operational form in ACT-R is Bᵢ = ln(Σⱼ (t−tⱼ)⁻ᵈ), with d ≈ 0.5. Two refinements matter. First, Anderson et al. (2004, "An Integrated Theory of the Mind") embed base-level activation in a sum with *spreading activation* from the current context (Σ Wⱼ·Sⱼᵢ) plus noise — recency alone never determines retrieval; context always co-drives it. Your w₄ term is exactly this slot. Second, a computational approximation (I believe due to Petrov, mid-2000s — hedging on the exact citation) lets you compute base-level from just *n* (occurrence count) and lifetime *L* — roughly ln(n/(1−d)) − d·ln(L) — instead of storing every timestamp. Both apply directly to MIKAI. Pavlik & Anderson (2005) further showed decay rate should depend on spacing (crammed mentions decay faster than spaced ones) — real for your corpus (a burst of 40 mentions in one debugging night ≠ 40 mentions over 3 months), but a v2 refinement.

**Information retrieval.** BM25 (Robertson et al., Okapi/TREC era) contributed *saturating* term frequency — tf/(tf+k) — because the 5th occurrence carries less evidence than the 2nd. Your log(density) already encodes this instinct. Learning-to-rank (RankNet, Burges 2005; ListNet, Cao et al. 2007; LambdaMART) contributed the deeper lesson: hand-set weights on hand-designed features lose to weights fit against relevance judgments, and *listwise* objectives (optimize the ranking, not per-item scores) win. Applies to MIKAI later: your w₁–w₄ should eventually be fit from your own labels (Section 3 produces exactly those labels). Not now — you have zero labels.

**Neural memory systems.** Compressive Transformers (Rae et al. 2019) learn what to compress vs. discard via reconstruction loss — elegant, but requires training infrastructure you shouldn't build. RetroMAE (Xiao et al. 2022) improves dense-retrieval embeddings; relevant only in that it says: don't hand-roll similarity, use a strong off-the-shelf embedder for your max-sim term (you have Voyage). The directly applicable precedent is **Generative Agents (Park et al. 2023)**: their memory-stream retrieval score is α·recency + β·importance + γ·relevance, with *importance* being an LLM-rated scalar per memory. That is your formula's missing limb, published and validated.

**Recommendation.** The 1991 spine is right, but your current form has a bug: *density and the recency sum double-count the same evidence* — in ACT-R, occurrence count IS the number of terms in the sum, and the log wraps the whole sum. Adopt:

**S(c, t) = w₁·ln(Σᵢ (t−tᵢ)⁻ᵈ) + w₂·spread(c) + w₃·max-sim(c, goals ∪ profile) + w₄·I(c)**

- Term 1: ACT-R base-level activation, d = 0.5 fixed. Subsumes density and recency in one principled term.
- spread(c): count of distinct source streams (Notes / Claude threads / code) mentioning c — your original insight, kept; it's cross-context validity evidence ACT-R lacks.
- max-sim: cosine of c's embedding against the active goal/profile set (ACT-R's spreading-activation slot).
- I(c): LLM-rated importance, 1–10, rated once and cached (Generative Agents). Optional in v1.

This is still recognizably *your* formula — it's the 1991 core plus one 2004 correction plus one 2023 term.

## 2. Hybrid LLM + formula design

The formula is the deterministic core: given cached LLM outputs, every score is reproducible. The LLM appears at exactly four bounded points, each producing a small cached artifact, never scoring freely.

**E1 — Concept canonicalization (defines "c" itself).** (a) Decides whether surface forms are the same concept ("dream mechanic" = "dream pass" ≠ "dream_bootstrap.py"). (b) Feeds the *occurrence set* — which sections count as mentions of c, hence the tᵢ list, spread, everything. (c) Formula-only fails because aliasing and polysemy aren't string problems; `consolidation.py` already encodes this lesson — deterministic thresholds handle cosine > 0.90 and < 0.75, LLM adjudicates only the ambiguous band. Same pattern here.

**E2 — Goal inference.** (a) Extracts the active goal set from the corpus ("learn Chinese," "proposal spot," "ship MIKAI Sunday") — goals are induced, not declared. (b) Feeds the *reference set* on the right side of max-sim. It is not a term and not a weight: structurally, goal-inference is an LLM-computed **input to w₃'s comparison set**, refreshed at dream cadence, not per-score. (c) Formula-only fails because goals are latent and stated obliquely across dozens of sections; no deterministic extractor gets "wants to propose in China" from scattered fragments. Note the asymmetry: **intent-inference (current task) is NOT an LLM entry point** — the current task is recoverable near-deterministically as the embedding centroid of the last N sections / active thread, so it enters max-sim as a cheap query-time vector. Goals = slow + LLM; intent = fast + embedding. Keeping intent out of the LLM path keeps surfacing latency and cost at zero.

**E3 — Importance rating I(c).** (a) One cached scalar per concept: "how consequential is this to this user's life, 1–10." (b) Feeds the w₄ additive term. (c) This is the one failure the formula *provably* cannot fix: a single mention of "biopsy result Thursday" loses to 40 mentions of "docker-compose" on every frequency-derived term. Consequence requires world knowledge. This is the strongest justification in the whole hybrid.

**E4 — Promotion gate at the threshold.** (a) Reviews only the K concepts nearest the promotion cutoff each night and votes promote/veto. (b) Feeds a *gate condition*, never a score adjustment — the ranking stays formula-determined. (c) Formula-only fails on page-worthiness: "localhost:8100" is dense, recent, spread across streams, and garbage. Junk detection is semantic.

Everything else — decay, ranking, thresholds, demotion — stays deterministic.

## 3. Test protocol: LLM salience judgment on real corpus

**Sample.** A 90-day slice, stratified across the three source streams — roughly 300–500 sections. This matches the dream-narrative window, is small enough to run repeatedly, and large enough to contain ~50–100 candidate concepts. Do not test on the full 27MB: it confounds context-length effects with judgment quality.

**LLM output format.** All three, structured: a ranked top-30 concept list, a 0–100 score per concept, and a one-sentence rationale each. The *ranking* is what gets scored; scores feed calibration analysis; rationales are for error analysis only (they tell you *which* formula term the LLM is implicitly using when it disagrees).

**Ground truth.** Brian's gold labels — but pooled, not free-form: build the candidate pool as the union of LLM picks, formula picks, and ~15 random ontology entities (so neither system defines the universe), shuffle, and Brian labels each: must-promote / maybe / no. Multiple LLM votes are a *robustness check* (is the LLM's ranking stable across 3 runs?), not truth. The embedding baseline (rank by max-sim to goals alone) is a *comparator*, not truth.

**Metrics.** Primary: NDCG@20 against graded gold labels, for three systems — formula-only, LLM-only, and a simple rank-fusion hybrid. Secondary: precision@10 on must-promote; Kendall τ between LLM and formula rankings (tells you whether they even disagree — if τ > 0.8, the hybrid question is moot); agreement rate at the promotion threshold. Skip calibration curves until scores are used numerically.

**Falsification.** The hybrid hypothesis is dead if *both*: (1) the concepts the LLM ranks highly that the formula misses are predominantly labeled "no" (LLM-unique precision under ~30%), and (2) fused NDCG@20 ≤ formula-only NDCG within run-to-run noise. That result says the LLM's judgment is either redundant with frequency+goal-similarity or actively noisy — keep E1/E2 (structural roles) and drop E3/E4 (judgment roles).

**Minimum afternoon test (~3 hours).** 30-day slice (~150 sections), one goal set. *First*, before seeing any output, Brian free-lists his top 10 salient concepts from memory — this is the anchoring-free gold. Then: run the formula ranking and one LLM ranking, compute recall@10 of his list for each, and hand-inspect the disjoint picks. If the LLM recovers things Brian listed that the formula missed, the hybrid has legs. One prompt, one spreadsheet, real signal.

## 4. Dream mechanic as canonicalization + more

The biological frame is sound: complementary learning systems (McClelland, McNaughton & O'Reilly 1995) — fast episodic store replayed offline into a slow semantic store — is *literally* the capture-buffer → wiki architecture. Per function:

**Episodic → semantic consolidation.** (a) Needed — it's the wiki's core job. (b) Yes; `narrative` and `ontology` already do it (Stickgold and Walker's sleep-consolidation work says replay is selective and gist-extracting, which is what a prompted recap does). (c) MVP: exists. (d) Failure mode: **confabulation loops** — the narrative asserts a wrong generalization, gets re-ingested, becomes "fact." Guard: narrative must cite source section IDs and mark inference vs. record.

**Pattern extraction / abstraction.** (a) Needed — this *is* promotion: recurring concept → own page. (b) Yes, as formula-ranks + LLM-gates (E4). (c) MVP: the `promote` subcommand in Section 5. (d) Failure: premature abstraction — junk pages, wiki sprawl, wikilink rot. Guard: threshold + hard cap on promotions per night.

**Emotional processing / affect down-regulation.** (Walker's "overnight therapy" claim; Payne's work on sleep preferentially consolidating emotional elements.) (a) Mostly *not* needed — MIKAI is a task engine, and machine-labeling the user's emotional life is high-creep, low-value. The only defensible analog is stall/frustration detection, which is an L4 concern, not a dream concern. (b/c/d) Skip. Building it wrong poisons trust in everything else.

**Creative recombination / associative binding.** (Sleep, REM especially, favors remote associations — Stickgold's group; Wamsley on dream incorporation.) (a) Deferrable but highest-upside: cross-thread bridges ("your Chinese-learning and proposal-spot threads intersect") are exactly the noonchi product. (b) Weakly but usefully: sample concept pairs with high salience, low co-occurrence, moderate embedding similarity; ask for a real connection. (c) MVP: a `connect` subcommand writing to a quarantined "Connections (speculative)" section. (d) Failure: hallucinated links presented as fact. Guard: suggestions never auto-merge into pages; user promotes them.

**Pruning / forgetting.** (Crick & Mitchison 1983 framed dreaming as reverse learning — unlearning parasitic associations.) (a) Needed — the wiki grows monotonically; salience decay is the principled demotion signal. (b) Mostly *doesn't need* the LLM: the formula decays scores deterministically; LLM only vetoes archival of low-frequency/high-importance items. (c) MVP: `decay` subcommand — recompute S nightly, move below-threshold pages to `archive/`, never delete. (d) Failure: catastrophic forgetting of dormant-but-vital (tax deadlines, relationship facts). Guard: I(c) floor + archive-not-delete + audit line in log.md.

**Order:** 1. `promote` (it's the Consolidation Layer itself), 2. `decay` (meaningless until pages exist to demote — but needed soon after), 3. `connect` (needs a populated concept graph to recombine), never `affect`.

## 5. Simplicity-first: minimum viable Consolidation Layer

**The MVP is one new subcommand: `dream_bootstrap.py promote`.** Zero new infrastructure — it reuses `load_index()`, the `Budget` LLM wrapper, `backup()`, and the log.md audit convention already in the file.

Nightly flow:

1. **Candidates** come from `wiki-ontology.md` — entity extraction is already done; do not build a new extractor. Mention detection per candidate = normalized string match (via the existing name normalization) against dated wiki sections. Crude, fine for proper nouns.
2. **Score** each candidate with the simplest formula: S = ln(Σᵢ (t−tᵢ)⁻⁰·⁵) + spread(c) + goal-overlap(c), where goal-overlap is keyword/embedding similarity between the candidate's mention contexts and USER_MODEL.md's "Current" section. All weights = 1, d = 0.5, hand-set threshold. No I(c), no LLM gate.
3. **Promote** the top N (cap: 10/night) above threshold: write a stub page `~/.mikai/wiki/concepts/<slug>.md` containing the name, the per-term score breakdown, wikilinks to every mentioning section, and one 3-sentence LLM summary (one Budget-capped call per promoted concept — the only LLM usage in the MVP). Idempotent: existing pages get their link list and score refreshed, not rewritten.
4. **Ledger:** write `wiki-salience.md` — every scored candidate, ranked, with the term-by-term breakdown. This is the audit surface *and* it is exactly the labeling instrument Section 3's test needs. Append one audit line to log.md; support `--dry-run`.

That's 4–6 hours: a scoring loop, a page writer, a report writer, all against existing plumbing.

**Explicitly OUT, and why deferring is safe:**

- **I(c) LLM importance term and the E4 promotion gate** — add only after the afternoon test shows where the formula fails; additive terms bolt onto a ledger that already prints per-term breakdowns.
- **LLM canonicalization band (E1)** — ontology extraction plus `consolidation.py`'s existing cluster-merge already cover the worst aliasing; duplicate concept pages are annoying, not corrupting.
- **`decay` / demotion** — nothing exists to demote yet; monotonic growth is harmless for weeks at this corpus size.
- **`connect`** — speculative output needs a populated concept layer to recombine, and needs the quarantine design done carefully.
- **Learned weights / listwise ranking** — requires labels; the ledger + Section 3 protocol generate them as a byproduct of normal use.
- **Intent/current-task term** — it's a query-time surfacing concern (L4), not a nightly consolidation input; adding it to the dream would smear two layers together, violating D-041's spirit.

Every deferral is safe for the same structural reason: the formula is additive and the ledger exposes each term. New terms, learned weights, and LLM gates all slot in without rearchitecting — which is precisely the property a magnum-opus primitive should have.