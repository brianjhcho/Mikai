# R Candidate Salience — Level 4 (adds IR / KR / Entity-Resolution / Cog-Sci axes) — 2026-08-31

Ranked candidates for the next ingestion round, scored via **weighted concept intersection** (Session-10 spec in `fuzzy-shimmying-wreath.md`).

**Disposable one-shot scorer.** Purpose: schedule which un-ingested wiki-raw sources get the next paid `claude -p` call. Not a peer of the post-ingest salience system (`wiki-salience.md` / `dream_bootstrap.py`); no eval, no versioning. Judged only by downstream post-ingest recall@10 lift. Retire when the wiki-raw backlog drains.

## Universe & filtering

- Total wiki-raw sections: **15747**
- Filtered out — `claude-code` per-turn fragments: **10435**
- Filtered out — malformed `claude-thread` orphans (name missing `::title::idx::role`): **663**
- Unique claude threads (well-formed): **139**
- Other sections (apple-notes, perplexity, ...): **2608**
- Already ingested into parallel vault: **115** files
- Skipped as already-ingested during scoring: **115**
- Skipped as empty body: **0**
- **Candidates evaluated: 2632**

## Scoring — Level 3 formula

```
score = Σ log(1 + in_degree(c))       ← weighted_concept  (MIKAI-central, UNBOUNDED)
      + Σ profile_weight(t)           ← weighted_personal (broader Brian-profile, UNBOUNDED)
      + 3 · goal_overlap              ← 0-1
      + recency                       ← 0-1 (linear decay over 365d)
      + substance                     ← 0-1 (log(turns) or log(bytes))
      + aggregation_bonus             ← 0-1.5 (log-scaled by n_personal_hits, rewards multi-topic dense threads)
```

**Level 3.1 tuning changes:** removed hard-coded noise blacklist (yoga/plants/dining/etc. — false negatives on personal-domain clusters Brian actively cares about); added aggregation bonus so long threads consolidating many personal-vocab topics score above thin single-topic sources. Signal density (weighted_concept + weighted_personal + goal_overlap) is now the sole off-topic discriminator — zero-signal sources naturally rank at bottom.

**weighted_concept** — MIKAI-central signal. Sums `log(1+in-degree)` over concept slugs (min length 5, kebab-case) hit in source body. Max concept weight this run: **3.78**. Vocab: 529 slugs.

**weighted_personal** — broader Brian-profile signal (Level 3 addition). Sums per-token weight from a compiled personal vocabulary. Sources: USER_MODEL.md (1.5), PROFILE.md (1.0), BRAIN.md priorities (0.7), entity slugs (0.5), wisdom/goals/habits/reflections (0.5), queries (0.4), journal tags (0.3). Max personal weight this run: **1.50**. Vocab: 2170 tokens. Tokens already in concept vocab are excluded from this component to avoid double-counting.

Goal source: `~/.mikai/brain/GOALS.md` (10 goals).

### Level 4 additions (4 new axes from `docs/INGESTION_LOG.md` 8-discipline scorecard)

- **axis_a_retrieval** (IR, weight +1.0): overlap with tokens in `wiki/queries/*.md` — predicts which candidates will get queried later.
- **axis_b_novelty** (KR, weight +1.0): 2-3-word kebab-phrases in body NOT already in concept vocab — sources that expand vocabulary score higher.
- **axis_c_alias_risk** (Entity Resolution, weight -0.5): near-matches to existing slugs (substring + prefix + Jaro-Winkler > 0.85) — high risk = likely to produce dupes.
- **axis_g_episodic_score** (Cognitive Science, no direct weight): 0.0=episodic, 1.0=semantic, 0.5=ambiguous. Routing signal only — emitted for downstream page-type placement.

## Top 30 candidates

| # | score | l3.1 | w_conc | w_pers | axA | axB | axC | axG | kind | KB | turns | title |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 58.28 | 56.46 | 10.43 | 42.29 | 1.00 | 1.00 | -0.18 | 0.50 | thread | 39 | 18 | Consolidating architectural decisions across project th |
| 2 | 51.53 | 49.79 | 5.63 | 41.40 | 1.00 | 0.96 | -0.23 | 0.50 | thread | 5 | 2 | Personalized reading list recommendations |
| 3 | 51.13 | 49.37 | 5.53 | 39.92 | 1.00 | 1.00 | -0.23 | 0.50 | perplexity | 40 | — | Ha-Joon Chang, Byung-Chul Han Sandwich there was a thre |
| 4 | 49.98 | 48.17 | 6.92 | 38.20 | 1.00 | 0.93 | -0.12 | 0.00 | thread | 13 | 4 | Synthesizing multiple sources with passive collection |
| 5 | 49.89 | 48.24 | 1.95 | 42.55 | 1.00 | 1.00 | -0.35 | 0.00 | perplexity | 29 | — | Anthropic open ai, and perplexity valuation,   What are |
| 6 | 49.86 | 48.26 | 2.71 | 41.49 | 1.00 | 0.60 | -0.00 | 0.50 | apple-notes | 24 | — | apple-notes::Feb 2025 - David and the Dao |
| 7 | 49.76 | 48.16 | 6.69 | 38.43 | 1.00 | 0.83 | -0.23 | 0.50 | thread | 14 | 6 | MIKAi development and memory challenges |
| 8 | 48.92 | 47.15 | 5.62 | 37.87 | 1.00 | 1.00 | -0.23 | 0.50 | thread | 32 | 21 | Improving project instructions for MIKA TECH (Progressi |
| 9 | 48.43 | 46.66 | 6.11 | 37.74 | 1.00 | 1.00 | -0.23 | 0.50 | thread | 8 | 2 | Modern solutions for the rentiers problem |
| 10 | 48.42 | 46.72 | 0.69 | 41.75 | 1.00 | 1.00 | -0.30 | 0.50 | perplexity | 97 | — | EC Rare Book market research: What is the value of the  |
| 11 | 48.18 | 46.41 | 2.48 | 40.06 | 1.00 | 1.00 | -0.23 | 1.00 | thread | 23 | 14 | Unreciprocated effort and emotional withdrawal patterns |
| 12 | 48.06 | 46.36 | 5.54 | 36.78 | 1.00 | 1.00 | -0.30 | 0.50 | perplexity | 55 | — | Entj 7w8 vs 8w7. I want to know which one I amTo determ |
| 13 | 47.99 | 46.26 | 4.61 | 37.56 | 1.00 | 1.00 | -0.27 | 0.00 | perplexity | 98 | — | (Bot) Options Trading StrategiesVolatility arbitrage (v |
| 14 | 47.70 | 45.88 | 3.74 | 38.48 | 1.00 | 1.00 | -0.18 | 0.50 | perplexity | 20 | — | vancouver from early 2000s to 2021 faced unprecendented |
| 15 | 47.07 | 45.42 | 0.00 | 41.38 | 1.00 | 1.00 | -0.35 | 0.50 | perplexity | 34 | — | can you analyze vancouver brand aritzia and their expan |
| 16 | 47.03 | 45.51 | 0.00 | 40.92 | 1.00 | 1.00 | -0.48 | 0.50 | thread | 326 | 80 | Building a championship roster around Luka in Vancouver |
| 17 | 46.56 | 44.74 | 0.00 | 40.74 | 1.00 | 1.00 | -0.18 | 0.50 | perplexity | 41 | — | I want to fill international village in chinatown with  |
| 18 | 46.43 | 44.75 | 0.00 | 41.43 | 1.00 | 1.00 | -0.32 | 0.50 | perplexity | 10 | — | If AGI is for sure coming, explain the landscape or top |
| 19 | 46.27 | 44.73 | 4.72 | 36.33 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 11 | — | apple-notes::June 2026 |
| 20 | 46.27 | 44.73 | 4.72 | 36.33 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 11 | — | apple-notes::June 2026 |
| 21 | 45.94 | 44.17 | 0.00 | 40.37 | 1.00 | 1.00 | -0.23 | 0.00 | perplexity | 36 | — | Are there any examples of an all ai news YouTube or Spo |
| 22 | 45.77 | 44.09 | 0.00 | 40.13 | 1.00 | 1.00 | -0.32 | 0.50 | perplexity | 32 | — | what to enfj's day dream aboutENFJs most often daydream |
| 23 | 45.56 | 44.02 | 4.72 | 35.66 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 24 | 45.53 | 43.83 | 0.00 | 39.32 | 1.00 | 1.00 | -0.30 | 0.50 | thread | 211 | 111 | Identifying an Alocasia plant |
| 25 | 45.48 | 43.67 | 0.00 | 40.48 | 1.00 | 1.00 | -0.18 | 0.50 | thread | 23 | 4 | Interoperable patient records in Canada |
| 26 | 45.40 | 43.66 | 1.61 | 38.22 | 1.00 | 0.93 | -0.18 | 0.50 | perplexity | 45 | — | I want to put on a bear call for tech stocks related to |
| 27 | 45.27 | 43.63 | 3.56 | 36.30 | 1.00 | 1.00 | -0.37 | 0.00 | perplexity | 36 | — | give me updates of nvda appl and tsla today in the news |
| 28 | 45.16 | 43.62 | 4.72 | 35.31 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 29 | 45.05 | 43.42 | 0.00 | 40.39 | 1.00 | 0.93 | -0.30 | 0.50 | apple-notes | 4 | — | memories |
| 30 | 44.93 | 43.39 | 4.72 | 35.07 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |

### Top concept + personal hits per candidate (top 15)

- **1.** Consolidating architectural decisions across project threads
  - concepts: `intent-graph` (3.13), `dsrp-framework` (2.71), `context-injection` (2.64)
  - personal: `weekly` (1.50), `frozen` (1.50), `decision` (1.50)
- **2.** Personalized reading list recommendations
  - concepts: `techno-republicanism` (2.30), `freedom-as-non-domination` (1.95), `data-unions` (1.39)
  - personal: `claude` (1.50), `primary` (1.50), `context` (1.50)
- **3.** Ha-Joon Chang, Byung-Chul Han Sandwich there was a thread th
  - concepts: `information-metabolism` (1.95), `market-fundamentalism` (1.79), `iphone-convergence-thesis` (1.79)
  - personal: `personal` (1.50), `reasoning` (1.50), `claude` (1.50)
- **4.** Synthesizing multiple sources with passive collection
  - concepts: `personal-intent-graph` (3.78), `intent-graph` (3.13)
  - personal: `personal` (1.50), `decision` (1.50), `claude` (1.50)
- **5.** Anthropic open ai, and perplexity valuation,   What are thei
  - concepts: `model-context-protocol` (1.95)
  - personal: `hosted` (1.50), `reasoning` (1.50), `claude` (1.50)
- **6.** apple-notes::Feb 2025 - David and the Dao
  - concepts: `consumer-groups` (2.71)
  - personal: `personal` (1.50), `germaine` (1.50), `nothing` (1.50)
- **7.** MIKAi development and memory challenges
  - concepts: `intent-graph` (3.13), `information-metabolism` (1.95), `orchestration-agent` (1.61)
  - personal: `decision` (1.50), `traversable` (1.50), `reasoning` (1.50)
- **8.** Improving project instructions for MIKA TECH (Progressive St
  - concepts: `intent-graph` (3.13), `intent-and-goal-map` (1.39), `village-councils` (1.10)
  - personal: `weekly` (1.50), `decision` (1.50), `reasoning` (1.50)
- **9.** Modern solutions for the rentiers problem
  - concepts: `dsrp-framework` (2.71), `rent-seeking` (1.79), `rentier-capitalism` (1.61)
  - personal: `claude` (1.50), `choice` (1.50), `durable` (1.50)
- **10.** EC Rare Book market research: What is the value of the rare 
  - concepts: `information-asymmetry` (0.69)
  - personal: `hosted` (1.50), `decision` (1.50), `primary` (1.50)
- **11.** Unreciprocated effort and emotional withdrawal patterns
  - concepts: `consolidation-as-displacement` (2.48)
  - personal: `decision` (1.50), `claude` (1.50), `primary` (1.50)
- **12.** Entj 7w8 vs 8w7. I want to know which one I amTo determine w
  - concepts: `wu-wei` (2.83), `consumer-groups` (2.71)
  - personal: `personal` (1.50), `autonomous` (1.50), `decision` (1.50)
- **13.** (Bot) Options Trading StrategiesVolatility arbitrage (vol ar
  - concepts: `long-straddle` (1.61), `iron-condor` (1.61), `bull-call-spread` (1.39)
  - personal: `weekly` (1.50), `hosted` (1.50), `decision` (1.50)
- **14.** vancouver from early 2000s to 2021 faced unprecendented grow
  - concepts: `information-metabolism` (1.95), `iphone-convergence-thesis` (1.79)
  - personal: `reasoning` (1.50), `claude` (1.50), `reframed` (1.50)
- **15.** can you analyze vancouver brand aritzia and their expansion 
  - concepts: —
  - personal: `weekly` (1.50), `decision` (1.50), `primary` (1.50)

## Recommended next batch (top 30)

- Total volume: **1362KB** across 30 sources
- Est. wall-clock: **~12min** at workers=8, **~100min** at workers=1 (assumes ~200s/source average)
- Would land as R3-2026-08-31-mikai-followup

| # | score | w_conc | w_pers | title | KB | filename |
|---|---|---|---|---|---|---|
| 1 | 58.28 | 10.43 | 42.29 | Consolidating architectural decisions across project threads | 39 | `2026-03-10-consolidating-architectural-decisions-across-project-threads-ea3aba.md` |
| 2 | 51.53 | 5.63 | 41.40 | Personalized reading list recommendations | 5 | `2026-03-07-personalized-reading-list-recommendations-0eb4d7.md` |
| 3 | 51.13 | 5.53 | 39.92 | Ha-Joon Chang, Byung-Chul Han Sandwich there was a thread th | 40 | `2026-03-19-ha-joon-chang-byung-chul-han-sandwich-there-was-a-thread-tha-5b63a0.md` |
| 4 | 49.98 | 6.92 | 38.20 | Synthesizing multiple sources with passive collection | 13 | `2026-02-22-synthesizing-multiple-sources-with-passive-collection-6aba25.md` |
| 5 | 49.89 | 1.95 | 42.55 | Anthropic open ai, and perplexity valuation,   What are thei | 29 | `2026-03-19-anthropic-open-ai-and-perplexity-valuation-what-are-their-re-5f7671.md` |
| 6 | 49.86 | 2.71 | 41.49 | apple-notes::Feb 2025 - David and the Dao | 24 | `2026-07-04-apple-notes-feb-2025-david-and-the-dao-562159.md` |
| 7 | 49.76 | 6.69 | 38.43 | MIKAi development and memory challenges | 14 | `2026-02-18-mikai-development-and-memory-challenges-ef2298.md` |
| 8 | 48.92 | 5.62 | 37.87 | Improving project instructions for MIKA TECH (Progressive St | 32 | `2026-03-07-improving-project-instructions-for-mika-tech-progressive-st-f048af.md` |
| 9 | 48.43 | 6.11 | 37.74 | Modern solutions for the rentiers problem | 8 | `2026-02-18-modern-solutions-for-the-rentiers-problem-ede432.md` |
| 10 | 48.42 | 0.69 | 41.75 | EC Rare Book market research: What is the value of the rare  | 97 | `2026-03-19-ec-rare-book-market-research-what-is-the-value-of-the-rare-b-17c258.md` |
| 11 | 48.18 | 2.48 | 40.06 | Unreciprocated effort and emotional withdrawal patterns | 23 | `2026-08-07-unreciprocated-effort-and-emotional-withdrawal-patterns-6ffe64.md` |
| 12 | 48.06 | 5.54 | 36.78 | Entj 7w8 vs 8w7. I want to know which one I amTo determine w | 55 | `2026-03-19-entj-7w8-vs-8w7-i-want-to-know-which-one-i-amto-determine-wh-be7b3f.md` |
| 13 | 47.99 | 4.61 | 37.56 | (Bot) Options Trading StrategiesVolatility arbitrage (vol ar | 98 | `2026-03-19-bot-options-trading-strategiesvolatility-arbitrage-vol-arb-i-40937e.md` |
| 14 | 47.70 | 3.74 | 38.48 | vancouver from early 2000s to 2021 faced unprecendented grow | 20 | `2026-03-19-vancouver-from-early-2000s-to-2021-faced-unprecendented-grow-c5665b.md` |
| 15 | 47.07 | 0.00 | 41.38 | can you analyze vancouver brand aritzia and their expansion  | 34 | `2026-03-19-can-you-analyze-vancouver-brand-aritzia-and-their-expansion-3b49b5.md` |
| 16 | 47.03 | 0.00 | 40.92 | Building a championship roster around Luka in Vancouver | 326 | `2026-07-07-building-a-championship-roster-around-luka-in-vancouver-d563a3.md` |
| 17 | 46.56 | 0.00 | 40.74 | I want to fill international village in chinatown with buddi | 41 | `2026-03-19-i-want-to-fill-international-village-in-chinatown-with-buddi-959b6f.md` |
| 18 | 46.43 | 0.00 | 41.43 | If AGI is for sure coming, explain the landscape or topograp | 10 | `2026-03-19-if-agi-is-for-sure-coming-explain-the-landscape-or-topograph-c84f94.md` |
| 19 | 46.27 | 4.72 | 36.33 | apple-notes::June 2026 | 11 | `2026-07-12-apple-notes-june-2026-c067f3.md` |
| 20 | 46.27 | 4.72 | 36.33 | apple-notes::June 2026 | 11 | `2026-07-13-apple-notes-june-2026-c067f3.md` |
| 21 | 45.94 | 0.00 | 40.37 | Are there any examples of an all ai news YouTube or Spotify  | 36 | `2026-03-19-are-there-any-examples-of-an-all-ai-news-youtube-or-spotify-a2fcf1.md` |
| 22 | 45.77 | 0.00 | 40.13 | what to enfj's day dream aboutENFJs most often daydream abou | 32 | `2026-03-19-what-to-enfj-s-day-dream-aboutenfjs-most-often-daydream-abou-477cde.md` |
| 23 | 45.56 | 4.72 | 35.66 | apple-notes::June 2026 | 10 | `2026-07-11-apple-notes-june-2026-c067f3.md` |
| 24 | 45.53 | 0.00 | 39.32 | Identifying an Alocasia plant | 211 | `2026-06-15-identifying-an-alocasia-plant-df96d3.md` |
| 25 | 45.48 | 0.00 | 40.48 | Interoperable patient records in Canada | 23 | `2026-02-21-interoperable-patient-records-in-canada-9c68e1.md` |
| 26 | 45.40 | 1.61 | 38.22 | I want to put on a bear call for tech stocks related to ai a | 45 | `2026-03-19-i-want-to-put-on-a-bear-call-for-tech-stocks-related-to-ai-a-b2dc55.md` |
| 27 | 45.27 | 3.56 | 36.30 | give me updates of nvda appl and tsla today in the newsHere' | 36 | `2026-03-19-give-me-updates-of-nvda-appl-and-tsla-today-in-the-newshere-725656.md` |
| 28 | 45.16 | 4.72 | 35.31 | apple-notes::June 2026 | 10 | `2026-07-09-apple-notes-june-2026-c067f3.md` |
| 29 | 45.05 | 0.00 | 40.39 | memories | 4 | `2026-03-19-memories-fc9f32.md` |
| 30 | 44.93 | 4.72 | 35.07 | apple-notes::June 2026 | 10 | `2026-07-09-apple-notes-june-2026-c067f3.md` |

## Appendix — next 200 candidates (rank 31+, brief)

- 31. **44.90** [w_conc=4.72, apple-notes, 10KB] apple-notes::June 2026
- 32. **44.49** [w_conc=4.03, apple-notes, 10KB] apple-notes::June 2026
- 33. **44.41** [w_conc=4.03, apple-notes, 10KB] apple-notes::June 2026
- 34. **44.34** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 35. **44.33** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 36. **44.31** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 37. **44.31** [w_conc=4.03, apple-notes, 10KB] apple-notes::June 2026
- 38. **44.29** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 39. **44.22** [w_conc=0.00, thread, 109KB] Sphagnum moss vs peat moss for DIY Monstera poles
- 40. **43.88** [w_conc=2.20, perplexity, 13KB] How valuable is OCR data from social media. A lot i imagineYour instinct is righ
- 41. **43.44** [w_conc=0.00, perplexity, 97KB] assessed property value vs fair market value?Assessed property value and fair ma
- 42. **43.26** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 43. **43.25** [w_conc=4.03, apple-notes, 11KB] apple-notes::June 2026
- 44. **43.25** [w_conc=0.00, perplexity, 16KB] never split the difference, book on negotiation and communication“Never Split th
- 45. **43.24** [w_conc=0.00, perplexity, 16KB] What startups have come out of ihub that are significant? What startups are ther
- 46. **43.22** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 47. **43.20** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 48. **43.20** [w_conc=4.51, thread, 10KB] Building credibility for a Google acquisition
- 49. **43.17** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 50. **43.16** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 51. **43.16** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 52. **43.16** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 53. **43.08** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 54. **43.05** [w_conc=0.69, thread, 65KB] Specialty coffee product scaling and market distribution
- 55. **43.01** [w_conc=0.00, thread, 41KB] Anarchist digital spaces beyond Bitcoin
- 56. **42.98** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 57. **42.91** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 58. **42.89** [w_conc=0.00, thread, 33KB] Kenya travel recommendations around Nairobi
- 59. **42.87** [w_conc=2.08, perplexity, 17KB] Wha are ai agent swarmsAI agent swarms are groups of specialized AI agents that 
- 60. **42.82** [w_conc=4.03, apple-notes, 9KB] apple-notes::June 2026
- 61. **42.80** [w_conc=4.32, perplexity, 17KB] Forget a recession. What Canadians are living through is worse. can you explain 
- 62. **42.63** [w_conc=0.00, thread, 30KB] Where writers migrate as platforms decay
- 63. **42.59** [w_conc=0.00, perplexity, 21KB] Can you read the transcript of this video: https://www.youtube.com/watch?v=_mwm6
- 64. **42.43** [w_conc=0.00, thread, 9KB] Manus AI compared to LangGraph and n8n
- 65. **42.29** [w_conc=0.00, perplexity, 7KB] Where is the state of Ai agents right now? How powerful are they in producing ac
- 66. **41.96** [w_conc=9.36, thread, 5KB] Building MIKAI prototype from PRD
- 67. **41.95** [w_conc=2.20, thread, 174KB] Wind-resistant plants for apartment living
- 68. **41.79** [w_conc=0.00, thread, 19KB] Scraping social media data for AI training
- 69. **41.62** [w_conc=0.00, perplexity, 23KB] Below is the problem my engineering team is trying to solve. Give me a high leve
- 70. **41.50** [w_conc=2.71, perplexity, 85KB] what is the first home buyers account in canadaThe First Home Savings Account (F
- 71. **41.42** [w_conc=3.00, perplexity, 27KB] tell me many variants of loss leader strategy across many industries. Bridge the
- 72. **41.41** [w_conc=0.00, perplexity, 99KB] In frostpunk 2 what is the best strategy: tech, exploration, etcFor Frostpunk 2 
- 73. **41.30** [w_conc=0.00, perplexity, 38KB] can you give me an overview of henderson development in canada as well as their 
- 74. **41.26** [w_conc=0.00, perplexity, 12KB] So how has Peter thiel executed on this philosophy?Peter Thiel has executed this
- 75. **41.24** [w_conc=1.61, thread, 23KB] Kenya's renewable energy advantages and scalability
- 76. **41.14** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] what the moat looks like in features — strategic-synthesis-2026-06-14: 2. The de
- 77. **41.14** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] what the moat looks like in features — strategic-insights: 2. The depth thesis —
- 78. **41.11** [w_conc=0.00, thread, 24KB] Digital assistant that adapts to you, not the other way arou
- 79. **41.11** [w_conc=0.00, perplexity, 32KB] what do the people of south korea, yantai, qingdao and dalian have in commonPeop
- 80. **41.10** [w_conc=0.69, thread, 9KB] Identifying productivity theater in daily habits
- 81. **40.83** [w_conc=0.00, perplexity, 99KB] My cats poo is dark brown and it’s almost black, but we’re worried by looking at
- 82. **40.63** [w_conc=0.00, thread, 10KB] Beyond the LLM hype: what AI has actually delivered
- 83. **40.50** [w_conc=0.00, perplexity, 10KB] It seems like the concept of AI agents have existed since the 80s. I remember re
- 84. **40.43** [w_conc=0.00, perplexity, 31KB] I want to create a business service that acts as broker for leases, and interior
- 85. **40.39** [w_conc=0.00, perplexity, 14KB] Who is the content creator or social media head that is the best at assessing ne
- 86. **40.25** [w_conc=0.69, thread, 26KB] Agentic marketplace for used goods
- 87. **40.11** [w_conc=5.33, apple-notes, 4KB] The Hard Truth about 2nd Brain: Rewind AI's & Consumer Adaptation
- 88. **40.06** [w_conc=6.11, apple-notes, 4KB] Modern solutions for the rentiers problem
- 89. **39.97** [w_conc=6.45, thread, 6KB] Mapping economic chokepoints for strategic advantage
- 90. **39.95** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 91. **39.94** [w_conc=0.00, perplexity, 65KB] I want to hook up my voice memos so that the automatically get inserted into rea
- 92. **39.87** [w_conc=0.00, perplexity, 23KB] David defeated the philistines with a stone and momentumDavid defeated Goliath b
- 93. **39.83** [w_conc=2.83, perplexity, 16KB] what is the definition of ditzy. can you analyze in it the context of a socionic
- 94. **39.69** [w_conc=0.00, thread, 30KB] Best iPhone generation to buy: first or stabilized iteration
- 95. **39.63** [w_conc=2.08, perplexity, 27KB] are there any other companies like scale ai but at lower valuations? can you giv
- 96. **39.53** [w_conc=0.00, perplexity, 40KB] What were the rewards for bitcoin mining from 2012-2016Introverted-intuition tak
- 97. **39.42** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 98. **39.41** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 99. **39.27** [w_conc=0.69, perplexity, 33KB] Using first principles I want to find out why housing costs are so expensive. We
- 100. **39.25** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 101. **39.25** [w_conc=3.14, thread, 12KB] Steve Jobs' prioritization meeting story
- 102. **39.22** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 103. **39.19** [w_conc=1.95, perplexity, 10KB] What is the core problem and core solution for international village mall. Expla
- 104. **39.19** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 105. **39.16** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 106. **39.16** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 107. **39.15** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 108. **39.12** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 109. **39.11** [w_conc=0.00, perplexity, 14KB] The first business that I want to build out for in international villages mall i
- 110. **39.09** [w_conc=1.61, perplexity, 27KB] I want to create a webapp tool that: allows you to search youtube explore page a
- 111. **39.09** [w_conc=0.00, perplexity, 14KB] can you give me a description of the eyes of and estj vs entj vs intjHere is a d
- 112. **39.08** [w_conc=0.00, perplexity, 11KB] Simulation Modelling: personality, business physics ~~ movement of people within
- 113. **39.08** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 114. **39.06** [w_conc=0.00, perplexity, 27KB] a fully transcend entj will act more like a?A fully realized, transcendent ENTJ 
- 115. **39.05** [w_conc=0.00, thread, 25KB] Private equity investment targets
- 116. **39.05** [w_conc=0.00, perplexity, 15KB] We know a start of founder that started his original business in 2012 and had fa
- 117. **39.00** [w_conc=2.08, perplexity, 12KB] Cna you do an analysis of the coffee commodities market? What account for the pr
- 118. **38.96** [w_conc=1.39, perplexity, 13KB] There’s an social principle where if the size of a community grows to over 500, 
- 119. **38.92** [w_conc=0.00, thread, 86KB] Forward head posture root causes
- 120. **38.92** [w_conc=0.69, perplexity, 15KB] i like Ha-Joon Chang, are there any other like him, who would be the best from p
- 121. **38.82** [w_conc=2.20, perplexity, 20KB] From everything we have discussed in this space called International Village, gi
- 122. **38.75** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 123. **38.62** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 124. **38.61** [w_conc=0.00, perplexity, 15KB] https://youtu.be/frqiUkjxAOE?si=rlTjy7QvhXn4gS_H  Can yo summarize this videoChr
- 125. **38.60** [w_conc=0.00, thread, 59KB] Crypto transfer phone scam
- 126. **38.55** [w_conc=0.00, perplexity, 29KB] Mark and I close university friends and have also been roommates after college t
- 127. **38.49** [w_conc=0.00, perplexity, 15KB] Tell me about the tax-free zone in Songdo, Incheon, Korea. What counts as R&D? S
- 128. **38.28** [w_conc=2.08, perplexity, 25KB] Give me the gdp per capita (ppp and nominal) of these countries: Kenya Mexico, V
- 129. **38.25** [w_conc=4.50, thread, 4KB] Project problem framing analysis
- 130. **38.22** [w_conc=0.00, thread, 6KB] Anthropic blocks Claude Pro OAuth tokens
- 131. **38.19** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 132. **38.17** [w_conc=0.00, perplexity, 19KB] In the Vancouver market, retail and f&b are struggling because of their low marg
- 133. **38.17** [w_conc=2.08, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 134. **38.16** [w_conc=0.00, perplexity, 18KB] For tech jobs, typically the big 5 was considered optimal. I want the next up an
- 135. **38.15** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 136. **38.14** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 137. **38.10** [w_conc=2.08, apple-notes, 5KB] apple-notes::July 2026
- 138. **38.03** [w_conc=2.08, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 139. **38.02** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 140. **38.02** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 7. Paths forward, ranked by historical viability
- 141. **38.02** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 7. Paths forward, ranked by historical viability
- 142. **37.99** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 143. **37.97** [w_conc=0.00, perplexity, 6KB] describe the the I's that is shown in this video: https://www.youtube.com/watch?
- 144. **37.79** [w_conc=0.00, perplexity, 22KB] I had a dream catcher when I was young , do cats act as a dream catcher?Cats are
- 145. **37.69** [w_conc=0.00, perplexity, 8KB] I want to create business model and plan to present for federal and provincial g
- 146. **37.64** [w_conc=0.00, perplexity, 13KB] what is a split-screen cycle in economicsA split-screen cycle in economics refer
- 147. **37.51** [w_conc=0.00, perplexity, 31KB] Chochu trading co.  Beyond goods: how to circumvent tariffs If we import Chinese
- 148. **37.48** [w_conc=0.00, perplexity, 16KB] is weride a chinese company? What are the prices for their robo sweepers and sim
- 149. **37.46** [w_conc=0.00, perplexity, 18KB] the apartments by international village mall and roger's arena, is that area cal
- 150. **37.41** [w_conc=4.03, apple-notes, 7KB] apple-notes::June 2026
- 151. **37.40** [w_conc=4.03, apple-notes, 7KB] apple-notes::June 2026
- 152. **37.40** [w_conc=4.03, apple-notes, 7KB] apple-notes::June 2026
- 153. **37.37** [w_conc=4.03, apple-notes, 7KB] apple-notes::June 2026
- 154. **37.36** [w_conc=0.69, perplexity, 9KB] It seems like to an entj, while an esfp is an activity partner, they can often t
- 155. **37.35** [w_conc=0.00, perplexity, 12KB] International village in downtown Vancouver has huge vacancy right now, and they
- 156. **37.31** [w_conc=0.00, perplexity, 4KB] How did ai fix the roaming the internet and performing actions problem, list the
- 157. **37.13** [w_conc=4.03, apple-notes, 7KB] apple-notes::June 2026
- 158. **37.08** [w_conc=0.00, thread, 17KB] Andre Iguodala's personality type
- 159. **37.07** [w_conc=0.00, perplexity, 35KB] i'm being interview for a job as a starting engineer at a ai tech startup in can
- 160. **37.05** [w_conc=0.00, perplexity, 17KB] how did bob rennie start his firm, what was the startBob Rennie started his firm
- 161. **37.03** [w_conc=4.03, apple-notes, 7KB] apple-notes::June 2026
- 162. **37.03** [w_conc=0.00, thread, 13KB] Continuing markdown conversations on Perplexity
- 163. **37.01** [w_conc=4.03, apple-notes, 7KB] apple-notes::June 2026
- 164. **36.94** [w_conc=4.03, apple-notes, 7KB] apple-notes::June 2026
- 165. **36.90** [w_conc=2.08, perplexity, 40KB] Our cat that we’ve had for three weeks now who’s peed for the first time when we
- 166. **36.81** [w_conc=0.00, perplexity, 8KB] Dr Arthur Brooks  https://youtu.be/5mpyFuyIQ14?si=OGjygtIocomSlz7q  What persona
- 167. **36.79** [w_conc=4.03, apple-notes, 7KB] apple-notes::June 2026
- 168. **36.75** [w_conc=0.00, perplexity, 47KB] what are the highest rated cat vets in vancouverI can’t reliably rank “highest r
- 169. **36.68** [w_conc=0.00, perplexity, 19KB] What happening in the market today particularly in the tech sector, and you look
- 170. **36.66** [w_conc=4.74, apple-notes, 2KB] MIKAI Feature: Ai directed content
- 171. **36.55** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] the OS-absorbs-the-assistant stress test — strategic-insights: 1. Threat landsca
- 172. **36.54** [w_conc=0.00, perplexity, 7KB] I love playing catan, eu4, civilization, poker. What are the the skills in those
- 173. **36.53** [w_conc=4.03, apple-notes, 7KB] apple-notes::June 2026
- 174. **36.52** [w_conc=0.00, thread, 9KB] WiFi-based motion tracking for physio apps
- 175. **36.48** [w_conc=4.03, apple-notes, 7KB] apple-notes::June 2026
- 176. **36.47** [w_conc=0.00, perplexity, 8KB] as an entj, my ti has always been weak in school, so understand a chain of relat
- 177. **36.46** [w_conc=0.00, perplexity, 29KB] can you do a case study on instant financial https://www.instant.co/ and how the
- 178. **36.45** [w_conc=4.03, apple-notes, 7KB] apple-notes::June 2026
- 179. **36.44** [w_conc=2.08, perplexity, 5KB] what is the status of ai agents right now? What actions can they perform? What a
- 180. **36.43** [w_conc=0.00, perplexity, 13KB] wealth management firm and industry overviewIntroverted Intuition – Key Insight 
- 181. **36.36** [w_conc=0.00, perplexity, 24KB] Toyota hybrid suv that is the highest ratedThe highest-rated Toyota hybrid SUV r
- 182. **36.34** [w_conc=2.83, perplexity, 9KB] what is the taoist principle of acting and not tryingThe Taoist principle of act
- 183. **36.32** [w_conc=0.00, thread, 43KB] INTJ's ideal personality match
- 184. **36.30** [w_conc=0.00, perplexity, 25KB] Best cafes in Nairobi that tech workers work at. I usually go to coffee shops li
- 185. **36.30** [w_conc=0.00, perplexity, 12KB] Activist investor invests 2b into workdayAn activist investor, Elliott Investmen
- 186. **36.23** [w_conc=0.00, perplexity, 58KB] I sit a lot during the day, I vape, and game on the computer a couple hours a da
- 187. **36.21** [w_conc=0.00, perplexity, 24KB] I was caught smoking outside the Nairobi airport and a police officer want to ta
- 188. **36.07** [w_conc=0.00, perplexity, 7KB] Below are my notes for International Villages project I've been working on this 
- 189. **35.99** [w_conc=0.00, thread, 9KB] Derek's systems thinking and applications to AI and geopolit
- 190. **35.99** [w_conc=0.00, perplexity, 9KB] I looking for a Vancouver economic group that believes in Georgiam or Joseph sti
- 191. **35.98** [w_conc=0.00, perplexity, 10KB] Restaurants in Vancouver are dying right now because people don’t have enough di
- 192. **35.96** [w_conc=0.00, perplexity, 22KB] Fed chair update and what it means for the market, why did trump want Jerome Pow
- 193. **35.87** [w_conc=0.00, perplexity, 34KB] Can I self inject this?Self-injecting GHK-Cu (Copper Peptide) purchased online i
- 194. **35.86** [w_conc=0.00, perplexity, 10KB] what are creative ways that ai agent can chagne the coffee industryAI agents are
- 195. **35.82** [w_conc=2.08, apple-notes, 5KB] apple-notes::July 2026
- 196. **35.73** [w_conc=1.10, thread, 19KB] Low voltage electrical companies in BC for Patrick
- 197. **35.67** [w_conc=0.00, perplexity, 7KB] What are the key things that create good managers vs good creatorsThe most criti
- 198. **35.55** [w_conc=0.00, perplexity, 15KB] Can you break down why on average 400 K to build a condo unit in Canada?Short an
- 199. **35.50** [w_conc=0.00, perplexity, 5KB] If AGI is for sure coming, explain the landscape or topography of AGI as an anal
- 200. **35.42** [w_conc=0.00, thread, 12KB] Finding the weak link in AI's circular economy
- 201. **35.39** [w_conc=3.40, apple-notes, 4KB] Making AI invisible through personalized knowledge architecture
- 202. **35.31** [w_conc=0.00, thread, 17KB] Electrician career paths in BC for low-voltage experience
- 203. **35.29** [w_conc=0.00, perplexity, 9KB] What happened to activist investing? Is there an investing principle or an organ
- 204. **35.28** [w_conc=0.00, thread, 6KB] Nairobi's infrastructure gaps and AI-enhanced tools
- 205. **35.28** [w_conc=3.40, claude, 4KB] claude: Making AI invisible through personalized knowledge architect
- 206. **35.22** [w_conc=2.08, perplexity, 11KB] If you were to ask all the tech ceos incubators on how to build an mvp in this a
- 207. **35.13** [w_conc=0.00, perplexity, 7KB] Can you ask my mentors what they think of this? Is this true or can you focus on
- 208. **35.11** [w_conc=0.00, perplexity, 27KB] I want to inquire into this commcerical property: https://www.realtor.ca/real-es
- 209. **35.09** [w_conc=0.00, perplexity, 23KB] It’s not creditors, I have my business listed as a sole proprietorship and I owe
- 210. **35.06** [w_conc=1.61, perplexity, 17KB] how much does a used container cost so I can grow mushrooms in them, what is the
- 211. **35.05** [w_conc=2.08, perplexity, 24KB] Is there such thing as our cats not wanting to come into me and my partner‘s roo
- 212. **34.89** [w_conc=0.00, perplexity, 20KB] In sports, and with my friends, I seem to alway be encouraging, and give thought
- 213. **34.82** [w_conc=3.14, thread, 14KB] 💬 A system that surfaces all the…
- 214. **34.80** [w_conc=2.64, thread, 4KB] Finding your ideal sports coaching philosophy
- 215. **34.74** [w_conc=0.00, perplexity, 11KB] how to get rid of fear, or to act in fear, I'm scared of sudden movements and sc
- 216. **34.74** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 9. Why no consumer Glean exists
- 217. **34.74** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 9. Why no consumer Glean exists
- 218. **34.73** [w_conc=0.00, perplexity, 10KB] who is the modern dasy gertrude steinThere is no widely recognized figure in con
- 219. **34.72** [w_conc=4.03, apple-notes, 6KB] apple-notes::June 2026
- 220. **34.59** [w_conc=0.00, perplexity, 8KB] Difference between psychology and psychiatry and other disciplines within that f
- 221. **34.50** [w_conc=0.00, perplexity, 49KB] where does qatar airways rank in qualitty and comfortQatar Airways ranks #1 in t
- 222. **34.47** [w_conc=1.95, perplexity, 3KB] “Based on everything you know about me from our full chat history and memory, gi
- 223. **34.44** [w_conc=2.56, apple-notes, 5KB] #toknowthyself
- 224. **34.42** [w_conc=4.03, apple-notes, 6KB] apple-notes::June 2026
- 225. **34.39** [w_conc=2.83, perplexity, 12KB] People want to feel like they are the smartest person, or the most ethical, or t
- 226. **34.39** [w_conc=0.00, thread, 39KB] Rent vs. buy analysis for Vancouver
- 227. **34.35** [w_conc=4.03, apple-notes, 6KB] apple-notes::June 2026
- 228. **34.35** [w_conc=0.00, perplexity, 10KB] Singapore developed by creating an economy, focussed on foreign electronics ship
- 229. **34.24** [w_conc=4.51, apple-notes, 4KB] Building credibility for a Google acquisition
- 230. **34.21** [w_conc=1.39, perplexity, 10KB] Is n8n the best workflow? What are adjacent tools? How does it work?N8n is a pow

_(2402 additional low-score candidates omitted; see JSON for full list.)_
