# R Candidate Salience — Level 4 (adds IR / KR / Entity-Resolution / Cog-Sci axes) — 2026-09-01

Ranked candidates for the next ingestion round, scored via **weighted concept intersection** (Session-10 spec in `fuzzy-shimmying-wreath.md`).

**Disposable one-shot scorer.** Purpose: schedule which un-ingested wiki-raw sources get the next paid `claude -p` call. Not a peer of the post-ingest salience system (`wiki-salience.md` / `dream_bootstrap.py`); no eval, no versioning. Judged only by downstream post-ingest recall@10 lift. Retire when the wiki-raw backlog drains.

## Universe & filtering

- Total wiki-raw sections: **15747**
- Filtered out — `claude-code` per-turn fragments: **10435**
- Filtered out — malformed `claude-thread` orphans (name missing `::title::idx::role`): **663**
- Unique claude threads (well-formed): **139**
- Other sections (apple-notes, perplexity, ...): **2608**
- Already ingested into parallel vault: **144** files
- Skipped as already-ingested during scoring: **126**
- Skipped as empty body: **0**
- **Candidates evaluated: 2621**

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

**weighted_concept** — MIKAI-central signal. Sums `log(1+in-degree)` over concept slugs (min length 5, kebab-case) hit in source body. Max concept weight this run: **3.81**. Vocab: 594 slugs.

**weighted_personal** — broader Brian-profile signal (Level 3 addition). Sums per-token weight from a compiled personal vocabulary. Sources: USER_MODEL.md (1.5), PROFILE.md (1.0), BRAIN.md priorities (0.7), entity slugs (0.5), wisdom/goals/habits/reflections (0.5), queries (0.4), journal tags (0.3). Max personal weight this run: **1.50**. Vocab: 2333 tokens. Tokens already in concept vocab are excluded from this component to avoid double-counting.

Goal source: `~/.mikai/brain/GOALS.md` (10 goals).

### Level 4 additions (4 new axes from `docs/INGESTION_LOG.md` 8-discipline scorecard)

- **axis_a_retrieval** (IR, weight +1.0): overlap with tokens in `wiki/queries/*.md` — predicts which candidates will get queried later.
- **axis_b_novelty** (KR, weight +1.0): 2-3-word kebab-phrases in body NOT already in concept vocab — sources that expand vocabulary score higher.
- **axis_c_alias_risk** (Entity Resolution, weight -0.5): near-matches to existing slugs (substring + prefix + Jaro-Winkler > 0.85) — high risk = likely to produce dupes.
- **axis_g_episodic_score** (Cognitive Science, no direct weight): 0.0=episodic, 1.0=semantic, 0.5=ambiguous. Routing signal only — emitted for downstream page-type placement.

## Top 40 candidates

| # | score | l3.1 | w_conc | w_pers | axA | axB | axC | axG | kind | KB | turns | title |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 52.94 | 51.35 | 3.09 | 44.19 | 1.00 | 0.60 | -0.00 | 0.50 | apple-notes | 24 | — | apple-notes::Feb 2025 - David and the Dao |
| 2 | 52.62 | 50.92 | 5.97 | 41.03 | 1.00 | 1.00 | -0.30 | 0.50 | perplexity | 40 | — | Ha-Joon Chang, Byung-Chul Han Sandwich there was a thre |
| 3 | 52.50 | 50.87 | 2.40 | 44.73 | 1.00 | 1.00 | -0.37 | 0.00 | perplexity | 29 | — | Anthropic open ai, and perplexity valuation,   What are |
| 4 | 52.05 | 50.35 | 1.10 | 44.98 | 1.00 | 1.00 | -0.30 | 0.50 | perplexity | 97 | — | EC Rare Book market research: What is the value of the  |
| 5 | 51.09 | 49.43 | 5.99 | 39.34 | 1.00 | 1.00 | -0.35 | 0.00 | perplexity | 98 | — | (Bot) Options Trading StrategiesVolatility arbitrage (v |
| 6 | 49.60 | 47.90 | 5.92 | 37.94 | 1.00 | 1.00 | -0.30 | 0.50 | perplexity | 55 | — | Entj 7w8 vs 8w7. I want to know which one I amTo determ |
| 7 | 49.44 | 47.63 | 4.03 | 39.93 | 1.00 | 1.00 | -0.18 | 0.50 | perplexity | 20 | — | vancouver from early 2000s to 2021 faced unprecendented |
| 8 | 49.37 | 47.64 | 0.00 | 43.84 | 1.00 | 1.00 | -0.27 | 0.00 | perplexity | 36 | — | Are there any examples of an all ai news YouTube or Spo |
| 9 | 48.72 | 46.90 | 0.00 | 42.90 | 1.00 | 1.00 | -0.18 | 0.50 | perplexity | 41 | — | I want to fill international village in chinatown with  |
| 10 | 48.54 | 46.89 | 0.00 | 42.86 | 1.00 | 1.00 | -0.35 | 0.50 | perplexity | 34 | — | can you analyze vancouver brand aritzia and their expan |
| 11 | 48.53 | 46.86 | 0.00 | 43.54 | 1.00 | 1.00 | -0.32 | 0.50 | perplexity | 10 | — | If AGI is for sure coming, explain the landscape or top |
| 12 | 47.94 | 46.40 | 4.85 | 37.87 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 11 | — | apple-notes::June 2026 |
| 13 | 47.94 | 46.40 | 4.85 | 37.86 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 11 | — | apple-notes::June 2026 |
| 14 | 47.25 | 45.57 | 0.00 | 41.61 | 1.00 | 1.00 | -0.32 | 0.50 | perplexity | 32 | — | what to enfj's day dream aboutENFJs most often daydream |
| 15 | 47.24 | 45.70 | 4.85 | 37.20 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 16 | 47.06 | 45.18 | 2.30 | 39.45 | 1.00 | 1.00 | -0.12 | 0.50 | perplexity | 16 | — | What startups have come out of ihub that are significan |
| 17 | 46.88 | 45.34 | 4.85 | 36.89 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 18 | 46.80 | 45.21 | 3.56 | 37.87 | 1.00 | 1.00 | -0.40 | 0.00 | perplexity | 36 | — | give me updates of nvda appl and tsla today in the news |
| 19 | 46.67 | 44.93 | 1.61 | 39.49 | 1.00 | 0.93 | -0.18 | 0.50 | perplexity | 45 | — | I want to put on a bear call for tech stocks related to |
| 20 | 46.63 | 45.10 | 4.85 | 36.65 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 21 | 46.59 | 45.05 | 4.85 | 36.58 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 22 | 46.28 | 44.74 | 4.16 | 37.03 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 23 | 46.27 | 44.73 | 4.16 | 37.02 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 24 | 46.24 | 44.71 | 4.16 | 36.99 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 25 | 46.23 | 44.69 | 4.16 | 36.98 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 26 | 46.22 | 44.69 | 4.16 | 36.97 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 27 | 46.21 | 44.67 | 4.16 | 36.94 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 28 | 46.18 | 44.56 | 0.00 | 41.52 | 1.00 | 0.93 | -0.30 | 0.50 | apple-notes | 4 | — | memories |
| 29 | 46.13 | 44.60 | 4.16 | 36.85 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 30 | 45.10 | 43.56 | 4.16 | 35.89 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 31 | 45.04 | 43.51 | 4.16 | 35.83 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 32 | 45.03 | 43.49 | 4.16 | 35.81 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 33 | 45.00 | 43.47 | 4.16 | 35.80 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 34 | 45.00 | 43.46 | 4.16 | 35.79 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 35 | 45.00 | 43.46 | 4.16 | 35.79 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 36 | 44.99 | 43.45 | 4.16 | 35.78 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 37 | 44.93 | 43.39 | 4.16 | 35.73 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 38 | 44.92 | 43.38 | 4.16 | 35.62 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 11 | — | apple-notes::June 2026 |
| 39 | 44.84 | 43.31 | 4.16 | 35.65 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 40 | 44.83 | 42.95 | 2.20 | 37.49 | 1.00 | 1.00 | -0.12 | 0.50 | perplexity | 13 | — | How valuable is OCR data from social media. A lot i ima |

### Top concept + personal hits per candidate (top 15)

- **1.** apple-notes::Feb 2025 - David and the Dao
  - concepts: `consumer-groups` (3.09)
  - personal: `people` (1.50), `rather` (1.50), `nothing` (1.50)
- **2.** Ha-Joon Chang, Byung-Chul Han Sandwich there was a thread th
  - concepts: `information-metabolism` (2.08), `iphone-convergence-thesis` (1.95), `market-fundamentalism` (1.95)
  - personal: `compiled` (1.50), `cleaner` (1.50), `claude` (1.50)
- **3.** Anthropic open ai, and perplexity valuation,   What are thei
  - concepts: `model-context-protocol` (2.40)
  - personal: `hosted` (1.50), `constrained` (1.50), `current` (1.50)
- **4.** EC Rare Book market research: What is the value of the rare 
  - concepts: `information-asymmetry` (1.10)
  - personal: `hosted` (1.50), `constrained` (1.50), `current` (1.50)
- **5.** (Bot) Options Trading StrategiesVolatility arbitrage (vol ar
  - concepts: `iron-condor` (1.61), `long-straddle` (1.61), `bull-call-spread` (1.39)
  - personal: `observed` (1.50), `hosted` (1.50), `current` (1.50)
- **6.** Entj 7w8 vs 8w7. I want to know which one I amTo determine w
  - concepts: `consumer-groups` (3.09), `wu-wei` (2.83), `enneagram-8w7` (0.00)
  - personal: `current` (1.50), `people` (1.50), `autonomous` (1.50)
- **7.** vancouver from early 2000s to 2021 faced unprecendented grow
  - concepts: `information-metabolism` (2.08), `iphone-convergence-thesis` (1.95)
  - personal: `constrained` (1.50), `current` (1.50), `cleaner` (1.50)
- **8.** Are there any examples of an all ai news YouTube or Spotify 
  - concepts: —
  - personal: `hosted` (1.50), `current` (1.50), `merged` (1.50)
- **9.** I want to fill international village in chinatown with buddi
  - concepts: —
  - personal: `hosted` (1.50), `current` (1.50), `people` (1.50)
- **10.** can you analyze vancouver brand aritzia and their expansion 
  - concepts: —
  - personal: `constrained` (1.50), `current` (1.50), `runway` (1.50)
- **11.** If AGI is for sure coming, explain the landscape or topograp
  - concepts: —
  - personal: `dependencies` (1.50), `current` (1.50), `agentic` (1.50)
- **12.** apple-notes::June 2026
  - concepts: `information-metabolism` (2.08), `human-in-the-loop` (2.08), `3d-ocean-farming` (0.69)
  - personal: `claude` (1.50), `people` (1.50), `rather` (1.50)
- **13.** apple-notes::June 2026
  - concepts: `information-metabolism` (2.08), `human-in-the-loop` (2.08), `3d-ocean-farming` (0.69)
  - personal: `claude` (1.50), `people` (1.50), `rather` (1.50)
- **14.** what to enfj's day dream aboutENFJs most often daydream abou
  - concepts: —
  - personal: `current` (1.50), `weekly` (1.50), `people` (1.50)
- **15.** apple-notes::June 2026
  - concepts: `information-metabolism` (2.08), `human-in-the-loop` (2.08), `3d-ocean-farming` (0.69)
  - personal: `claude` (1.50), `people` (1.50), `rather` (1.50)

## Recommended next batch (top 30)

- Total volume: **769KB** across 30 sources
- Est. wall-clock: **~12min** at workers=8, **~100min** at workers=1 (assumes ~200s/source average)
- Would land as R3-2026-09-01-mikai-followup

| # | score | w_conc | w_pers | title | KB | filename |
|---|---|---|---|---|---|---|
| 1 | 52.94 | 3.09 | 44.19 | apple-notes::Feb 2025 - David and the Dao | 24 | `2026-07-04-apple-notes-feb-2025-david-and-the-dao-562159.md` |
| 2 | 52.62 | 5.97 | 41.03 | Ha-Joon Chang, Byung-Chul Han Sandwich there was a thread th | 40 | `2026-03-19-ha-joon-chang-byung-chul-han-sandwich-there-was-a-thread-tha-5b63a0.md` |
| 3 | 52.50 | 2.40 | 44.73 | Anthropic open ai, and perplexity valuation,   What are thei | 29 | `2026-03-19-anthropic-open-ai-and-perplexity-valuation-what-are-their-re-5f7671.md` |
| 4 | 52.05 | 1.10 | 44.98 | EC Rare Book market research: What is the value of the rare  | 97 | `2026-03-19-ec-rare-book-market-research-what-is-the-value-of-the-rare-b-17c258.md` |
| 5 | 51.09 | 5.99 | 39.34 | (Bot) Options Trading StrategiesVolatility arbitrage (vol ar | 98 | `2026-03-19-bot-options-trading-strategiesvolatility-arbitrage-vol-arb-i-40937e.md` |
| 6 | 49.60 | 5.92 | 37.94 | Entj 7w8 vs 8w7. I want to know which one I amTo determine w | 55 | `2026-03-19-entj-7w8-vs-8w7-i-want-to-know-which-one-i-amto-determine-wh-be7b3f.md` |
| 7 | 49.44 | 4.03 | 39.93 | vancouver from early 2000s to 2021 faced unprecendented grow | 20 | `2026-03-19-vancouver-from-early-2000s-to-2021-faced-unprecendented-grow-c5665b.md` |
| 8 | 49.37 | 0.00 | 43.84 | Are there any examples of an all ai news YouTube or Spotify  | 36 | `2026-03-19-are-there-any-examples-of-an-all-ai-news-youtube-or-spotify-a2fcf1.md` |
| 9 | 48.72 | 0.00 | 42.90 | I want to fill international village in chinatown with buddi | 41 | `2026-03-19-i-want-to-fill-international-village-in-chinatown-with-buddi-959b6f.md` |
| 10 | 48.54 | 0.00 | 42.86 | can you analyze vancouver brand aritzia and their expansion  | 34 | `2026-03-19-can-you-analyze-vancouver-brand-aritzia-and-their-expansion-3b49b5.md` |
| 11 | 48.53 | 0.00 | 43.54 | If AGI is for sure coming, explain the landscape or topograp | 10 | `2026-03-19-if-agi-is-for-sure-coming-explain-the-landscape-or-topograph-c84f94.md` |
| 12 | 47.94 | 4.85 | 37.87 | apple-notes::June 2026 | 11 | `2026-07-12-apple-notes-june-2026-c067f3.md` |
| 13 | 47.94 | 4.85 | 37.86 | apple-notes::June 2026 | 11 | `2026-07-13-apple-notes-june-2026-c067f3.md` |
| 14 | 47.25 | 0.00 | 41.61 | what to enfj's day dream aboutENFJs most often daydream abou | 32 | `2026-03-19-what-to-enfj-s-day-dream-aboutenfjs-most-often-daydream-abou-477cde.md` |
| 15 | 47.24 | 4.85 | 37.20 | apple-notes::June 2026 | 10 | `2026-07-11-apple-notes-june-2026-c067f3.md` |
| 16 | 47.06 | 2.30 | 39.45 | What startups have come out of ihub that are significant? Wh | 16 | `2026-03-19-what-startups-have-come-out-of-ihub-that-are-significant-wha-260e5a.md` |
| 17 | 46.88 | 4.85 | 36.89 | apple-notes::June 2026 | 10 | `2026-07-09-apple-notes-june-2026-c067f3.md` |
| 18 | 46.80 | 3.56 | 37.87 | give me updates of nvda appl and tsla today in the newsHere' | 36 | `2026-03-19-give-me-updates-of-nvda-appl-and-tsla-today-in-the-newshere-725656.md` |
| 19 | 46.67 | 1.61 | 39.49 | I want to put on a bear call for tech stocks related to ai a | 45 | `2026-03-19-i-want-to-put-on-a-bear-call-for-tech-stocks-related-to-ai-a-b2dc55.md` |
| 20 | 46.63 | 4.85 | 36.65 | apple-notes::June 2026 | 10 | `2026-07-09-apple-notes-june-2026-c067f3.md` |
| 21 | 46.59 | 4.85 | 36.58 | apple-notes::June 2026 | 10 | `2026-07-10-apple-notes-june-2026-c067f3.md` |
| 22 | 46.28 | 4.16 | 37.03 | apple-notes::June 2026 | 9 | `2026-07-03-apple-notes-june-2026-c067f3.md` |
| 23 | 46.27 | 4.16 | 37.02 | apple-notes::June 2026 | 9 | `2026-07-03-apple-notes-june-2026-c067f3.md` |
| 24 | 46.24 | 4.16 | 36.99 | apple-notes::June 2026 | 9 | `2026-07-03-apple-notes-june-2026-c067f3.md` |
| 25 | 46.23 | 4.16 | 36.98 | apple-notes::June 2026 | 10 | `2026-07-04-apple-notes-june-2026-c067f3.md` |
| 26 | 46.22 | 4.16 | 36.97 | apple-notes::June 2026 | 9 | `2026-07-04-apple-notes-june-2026-c067f3.md` |
| 27 | 46.21 | 4.16 | 36.94 | apple-notes::June 2026 | 10 | `2026-07-04-apple-notes-june-2026-c067f3.md` |
| 28 | 46.18 | 0.00 | 41.52 | memories | 4 | `2026-03-19-memories-fc9f32.md` |
| 29 | 46.13 | 4.16 | 36.85 | apple-notes::June 2026 | 10 | `2026-07-09-apple-notes-june-2026-c067f3.md` |
| 30 | 45.10 | 4.16 | 35.89 | apple-notes::June 2026 | 9 | `2026-06-26-apple-notes-june-2026-c067f3.md` |

## Appendix — next 200 candidates (rank 41+, brief)

- 41. **44.79** [w_conc=0.00, perplexity, 97KB] assessed property value vs fair market value?Assessed property value and fair ma
- 42. **44.76** [w_conc=4.16, apple-notes, 9KB] apple-notes::June 2026
- 43. **44.67** [w_conc=4.16, apple-notes, 9KB] apple-notes::June 2026
- 44. **44.58** [w_conc=1.10, thread, 65KB] Specialty coffee product scaling and market distribution
- 45. **44.56** [w_conc=4.88, perplexity, 17KB] Forget a recession. What Canadians are living through is worse. can you explain 
- 46. **44.38** [w_conc=2.08, perplexity, 17KB] Wha are ai agent swarmsAI agent swarms are groups of specialized AI agents that 
- 47. **44.34** [w_conc=0.00, perplexity, 16KB] never split the difference, book on negotiation and communication“Never Split th
- 48. **44.10** [w_conc=0.00, thread, 30KB] Where writers migrate as platforms decay
- 49. **44.09** [w_conc=0.00, thread, 41KB] Anarchist digital spaces beyond Bitcoin
- 50. **44.08** [w_conc=0.00, thread, 33KB] Kenya travel recommendations around Nairobi
- 51. **44.02** [w_conc=8.76, apple-notes, 4KB] Modern solutions for the rentiers problem
- 52. **43.88** [w_conc=0.00, perplexity, 21KB] Can you read the transcript of this video: https://www.youtube.com/watch?v=_mwm6
- 53. **43.69** [w_conc=4.51, thread, 10KB] Building credibility for a Google acquisition
- 54. **43.32** [w_conc=0.00, thread, 9KB] Manus AI compared to LangGraph and n8n
- 55. **43.31** [w_conc=0.00, perplexity, 7KB] Where is the state of Ai agents right now? How powerful are they in producing ac
- 56. **43.30** [w_conc=0.00, thread, 19KB] Scraping social media data for AI training
- 57. **43.01** [w_conc=0.00, perplexity, 12KB] So how has Peter thiel executed on this philosophy?Peter Thiel has executed this
- 58. **42.99** [w_conc=9.71, thread, 5KB] Building MIKAI prototype from PRD
- 59. **42.80** [w_conc=8.41, thread, 6KB] Mapping economic chokepoints for strategic advantage
- 60. **42.75** [w_conc=0.00, thread, 10KB] Beyond the LLM hype: what AI has actually delivered
- 61. **42.73** [w_conc=0.00, perplexity, 32KB] what do the people of south korea, yantai, qingdao and dalian have in commonPeop
- 62. **42.72** [w_conc=3.09, perplexity, 85KB] what is the first home buyers account in canadaThe First Home Savings Account (F
- 63. **42.69** [w_conc=0.00, perplexity, 38KB] can you give me an overview of henderson development in canada as well as their 
- 64. **42.64** [w_conc=1.61, thread, 23KB] Kenya's renewable energy advantages and scalability
- 65. **42.62** [w_conc=2.20, thread, 174KB] Wind-resistant plants for apartment living
- 66. **42.61** [w_conc=0.00, perplexity, 23KB] Below is the problem my engineering team is trying to solve. Give me a high leve
- 67. **42.61** [w_conc=1.10, thread, 9KB] Identifying productivity theater in daily habits
- 68. **42.59** [w_conc=3.00, perplexity, 27KB] tell me many variants of loss leader strategy across many industries. Bridge the
- 69. **42.46** [w_conc=0.00, perplexity, 99KB] In frostpunk 2 what is the best strategy: tech, exploration, etcFor Frostpunk 2 
- 70. **42.35** [w_conc=0.00, thread, 24KB] Digital assistant that adapts to you, not the other way arou
- 71. **42.14** [w_conc=0.00, perplexity, 10KB] It seems like the concept of AI agents have existed since the 80s. I remember re
- 72. **42.07** [w_conc=0.00, perplexity, 99KB] My cats poo is dark brown and it’s almost black, but we’re worried by looking at
- 73. **41.99** [w_conc=1.10, thread, 26KB] Agentic marketplace for used goods
- 74. **41.93** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] what the moat looks like in features — strategic-synthesis-2026-06-14: 2. The de
- 75. **41.93** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] what the moat looks like in features — strategic-insights: 2. The depth thesis —
- 76. **41.61** [w_conc=0.00, perplexity, 31KB] I want to create a business service that acts as broker for leases, and interior
- 77. **41.49** [w_conc=2.08, perplexity, 27KB] are there any other companies like scale ai but at lower valuations? can you giv
- 78. **41.28** [w_conc=0.00, perplexity, 23KB] David defeated the philistines with a stone and momentumDavid defeated Goliath b
- 79. **41.20** [w_conc=0.00, perplexity, 14KB] Who is the content creator or social media head that is the best at assessing ne
- 80. **41.15** [w_conc=0.00, perplexity, 27KB] a fully transcend entj will act more like a?A fully realized, transcendent ENTJ 
- 81. **41.10** [w_conc=5.44, apple-notes, 4KB] The Hard Truth about 2nd Brain: Rewind AI's & Consumer Adaptation
- 82. **41.05** [w_conc=0.00, perplexity, 65KB] I want to hook up my voice memos so that the automatically get inserted into rea
- 83. **40.94** [w_conc=0.00, perplexity, 40KB] What were the rewards for bitcoin mining from 2012-2016Introverted-intuition tak
- 84. **40.82** [w_conc=0.00, thread, 30KB] Best iPhone generation to buy: first or stabilized iteration
- 85. **40.77** [w_conc=1.39, perplexity, 13KB] There’s an social principle where if the size of a community grows to over 500, 
- 86. **40.76** [w_conc=0.69, perplexity, 33KB] Using first principles I want to find out why housing costs are so expensive. We
- 87. **40.72** [w_conc=1.95, perplexity, 10KB] What is the core problem and core solution for international village mall. Expla
- 88. **40.71** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 89. **40.62** [w_conc=0.00, perplexity, 15KB] We know a start of founder that started his original business in 2012 and had fa
- 90. **40.46** [w_conc=1.61, perplexity, 27KB] I want to create a webapp tool that: allows you to search youtube explore page a
- 91. **40.45** [w_conc=2.83, perplexity, 16KB] what is the definition of ditzy. can you analyze in it the context of a socionic
- 92. **40.45** [w_conc=0.00, perplexity, 11KB] Simulation Modelling: personality, business physics ~~ movement of people within
- 93. **40.35** [w_conc=0.69, perplexity, 15KB] i like Ha-Joon Chang, are there any other like him, who would be the best from p
- 94. **40.33** [w_conc=0.00, perplexity, 18KB] For tech jobs, typically the big 5 was considered optimal. I want the next up an
- 95. **40.18** [w_conc=0.00, thread, 25KB] Private equity investment targets
- 96. **40.17** [w_conc=2.40, perplexity, 20KB] From everything we have discussed in this space called International Village, gi
- 97. **40.15** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 98. **40.14** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 99. **40.07** [w_conc=0.00, perplexity, 14KB] can you give me a description of the eyes of and estj vs entj vs intjHere is a d
- 100. **39.99** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 101. **39.97** [w_conc=2.08, perplexity, 12KB] Cna you do an analysis of the coffee commodities market? What account for the pr
- 102. **39.95** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 103. **39.94** [w_conc=1.10, perplexity, 9KB] It seems like to an entj, while an esfp is an activity partner, they can often t
- 104. **39.92** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 105. **39.91** [w_conc=0.00, perplexity, 14KB] The first business that I want to build out for in international villages mall i
- 106. **39.90** [w_conc=0.00, thread, 59KB] Crypto transfer phone scam
- 107. **39.90** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 108. **39.90** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 109. **39.88** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 110. **39.88** [w_conc=0.00, perplexity, 15KB] Tell me about the tax-free zone in Songdo, Incheon, Korea. What counts as R&D? S
- 111. **39.87** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 112. **39.82** [w_conc=3.14, thread, 12KB] Steve Jobs' prioritization meeting story
- 113. **39.80** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 114. **39.72** [w_conc=0.00, perplexity, 15KB] https://youtu.be/frqiUkjxAOE?si=rlTjy7QvhXn4gS_H  Can yo summarize this videoChr
- 115. **39.64** [w_conc=0.00, thread, 86KB] Forward head posture root causes
- 116. **39.53** [w_conc=0.00, perplexity, 29KB] Mark and I close university friends and have also been roommates after college t
- 117. **39.49** [w_conc=0.00, perplexity, 4KB] How did ai fix the roaming the internet and performing actions problem, list the
- 118. **39.48** [w_conc=1.39, perplexity, 24KB] I was caught smoking outside the Nairobi airport and a police officer want to ta
- 119. **39.42** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 120. **39.38** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 121. **39.31** [w_conc=0.00, perplexity, 19KB] In the Vancouver market, retail and f&b are struggling because of their low marg
- 122. **39.18** [w_conc=0.00, thread, 6KB] Anthropic blocks Claude Pro OAuth tokens
- 123. **39.17** [w_conc=2.08, perplexity, 25KB] Give me the gdp per capita (ppp and nominal) of these countries: Kenya Mexico, V
- 124. **39.12** [w_conc=4.85, thread, 4KB] Project problem framing analysis
- 125. **38.99** [w_conc=0.00, perplexity, 22KB] I had a dream catcher when I was young , do cats act as a dream catcher?Cats are
- 126. **38.97** [w_conc=2.08, perplexity, 5KB] what is the status of ai agents right now? What actions can they perform? What a
- 127. **38.97** [w_conc=0.00, perplexity, 8KB] Dr Arthur Brooks  https://youtu.be/5mpyFuyIQ14?si=OGjygtIocomSlz7q  What persona
- 128. **38.96** [w_conc=0.00, perplexity, 18KB] the apartments by international village mall and roger's arena, is that area cal
- 129. **38.86** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 130. **38.86** [w_conc=2.08, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 131. **38.85** [w_conc=0.00, perplexity, 8KB] I want to create business model and plan to present for federal and provincial g
- 132. **38.84** [w_conc=1.39, perplexity, 9KB] I looking for a Vancouver economic group that believes in Georgiam or Joseph sti
- 133. **38.83** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 134. **38.83** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 135. **38.82** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 136. **38.82** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 137. **38.81** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 138. **38.81** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 7. Paths forward, ranked by historical viability
- 139. **38.81** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 7. Paths forward, ranked by historical viability
- 140. **38.79** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 141. **38.76** [w_conc=0.00, perplexity, 12KB] International village in downtown Vancouver has huge vacancy right now, and they
- 142. **38.76** [w_conc=0.00, perplexity, 31KB] Chochu trading co.  Beyond goods: how to circumvent tariffs If we import Chinese
- 143. **38.75** [w_conc=0.00, perplexity, 6KB] describe the the I's that is shown in this video: https://www.youtube.com/watch?
- 144. **38.73** [w_conc=2.08, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 145. **38.70** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 146. **38.70** [w_conc=0.00, perplexity, 13KB] what is a split-screen cycle in economicsA split-screen cycle in economics refer
- 147. **38.67** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 148. **38.62** [w_conc=2.08, apple-notes, 5KB] apple-notes::July 2026
- 149. **38.55** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 150. **38.49** [w_conc=0.00, perplexity, 17KB] how did bob rennie start his firm, what was the startBob Rennie started his firm
- 151. **38.45** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 152. **38.43** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 153. **38.42** [w_conc=0.00, perplexity, 19KB] What happening in the market today particularly in the tech sector, and you look
- 154. **38.38** [w_conc=0.00, thread, 17KB] Andre Iguodala's personality type
- 155. **38.36** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 156. **38.33** [w_conc=0.00, perplexity, 5KB] If AGI is for sure coming, explain the landscape or topography of AGI as an anal
- 157. **38.21** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 158. **38.10** [w_conc=0.00, perplexity, 16KB] is weride a chinese company? What are the prices for their robo sweepers and sim
- 159. **38.04** [w_conc=0.00, perplexity, 7KB] I love playing catan, eu4, civilization, poker. What are the the skills in those
- 160. **38.03** [w_conc=0.00, thread, 13KB] Continuing markdown conversations on Perplexity
- 161. **37.90** [w_conc=0.00, perplexity, 47KB] what are the highest rated cat vets in vancouverI can’t reliably rank “highest r
- 162. **37.87** [w_conc=0.00, perplexity, 35KB] i'm being interview for a job as a starting engineer at a ai tech startup in can
- 163. **37.83** [w_conc=2.08, perplexity, 40KB] Our cat that we’ve had for three weeks now who’s peed for the first time when we
- 164. **37.73** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 165. **37.68** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 166. **37.68** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] the OS-absorbs-the-assistant stress test — strategic-insights: 1. Threat landsca
- 167. **37.66** [w_conc=0.00, perplexity, 24KB] Toyota hybrid suv that is the highest ratedThe highest-rated Toyota hybrid SUV r
- 168. **37.66** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 169. **37.41** [w_conc=0.00, thread, 43KB] INTJ's ideal personality match
- 170. **37.41** [w_conc=0.00, perplexity, 25KB] Best cafes in Nairobi that tech workers work at. I usually go to coffee shops li
- 171. **37.35** [w_conc=0.00, perplexity, 10KB] what are creative ways that ai agent can chagne the coffee industryAI agents are
- 172. **37.26** [w_conc=0.00, perplexity, 29KB] can you do a case study on instant financial https://www.instant.co/ and how the
- 173. **37.26** [w_conc=4.74, apple-notes, 2KB] MIKAI Feature: Ai directed content
- 174. **37.25** [w_conc=0.00, thread, 6KB] Nairobi's infrastructure gaps and AI-enhanced tools
- 175. **37.22** [w_conc=0.00, perplexity, 12KB] Activist investor invests 2b into workdayAn activist investor, Elliott Investmen
- 176. **37.19** [w_conc=0.00, perplexity, 8KB] as an entj, my ti has always been weak in school, so understand a chain of relat
- 177. **37.17** [w_conc=0.00, perplexity, 7KB] Below are my notes for International Villages project I've been working on this 
- 178. **37.15** [w_conc=0.00, perplexity, 58KB] I sit a lot during the day, I vape, and game on the computer a couple hours a da
- 179. **37.11** [w_conc=0.00, thread, 9KB] WiFi-based motion tracking for physio apps
- 180. **37.04** [w_conc=0.00, perplexity, 13KB] wealth management firm and industry overviewIntroverted Intuition – Key Insight 
- 181. **37.03** [w_conc=0.00, perplexity, 7KB] What are the key things that create good managers vs good creatorsThe most criti
- 182. **36.94** [w_conc=0.00, perplexity, 34KB] Can I self inject this?Self-injecting GHK-Cu (Copper Peptide) purchased online i
- 183. **36.81** [w_conc=2.83, perplexity, 9KB] what is the taoist principle of acting and not tryingThe Taoist principle of act
- 184. **36.76** [w_conc=0.00, perplexity, 10KB] Restaurants in Vancouver are dying right now because people don’t have enough di
- 185. **36.58** [w_conc=0.00, thread, 17KB] Electrician career paths in BC for low-voltage experience
- 186. **36.56** [w_conc=1.10, thread, 19KB] Low voltage electrical companies in BC for Patrick
- 187. **36.54** [w_conc=0.00, perplexity, 23KB] It’s not creditors, I have my business listed as a sole proprietorship and I owe
- 188. **36.51** [w_conc=0.00, perplexity, 22KB] Fed chair update and what it means for the market, why did trump want Jerome Pow
- 189. **36.41** [w_conc=0.00, perplexity, 15KB] Can you break down why on average 400 K to build a condo unit in Canada?Short an
- 190. **36.38** [w_conc=0.00, thread, 12KB] Finding the weak link in AI's circular economy
- 191. **36.35** [w_conc=2.08, apple-notes, 5KB] apple-notes::July 2026
- 192. **36.35** [w_conc=0.00, thread, 9KB] Derek's systems thinking and applications to AI and geopolit
- 193. **36.28** [w_conc=0.00, perplexity, 9KB] What happened to activist investing? Is there an investing principle or an organ
- 194. **36.17** [w_conc=3.69, apple-notes, 4KB] Making AI invisible through personalized knowledge architecture
- 195. **36.09** [w_conc=0.00, perplexity, 20KB] In sports, and with my friends, I seem to alway be encouraging, and give thought
- 196. **36.09** [w_conc=2.08, perplexity, 24KB] Is there such thing as our cats not wanting to come into me and my partner‘s roo
- 197. **36.09** [w_conc=0.00, perplexity, 7KB] Can you ask my mentors what they think of this? Is this true or can you focus on
- 198. **36.06** [w_conc=3.69, claude, 4KB] claude: Making AI invisible through personalized knowledge architect
- 199. **36.01** [w_conc=0.00, perplexity, 49KB] where does qatar airways rank in qualitty and comfortQatar Airways ranks #1 in t
- 200. **35.97** [w_conc=4.16, apple-notes, 6KB] apple-notes::June 2026
- 201. **35.93** [w_conc=2.71, thread, 4KB] Finding your ideal sports coaching philosophy
- 202. **35.90** [w_conc=1.95, perplexity, 3KB] “Based on everything you know about me from our full chat history and memory, gi
- 203. **35.89** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 9. Why no consumer Glean exists
- 204. **35.89** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 9. Why no consumer Glean exists
- 205. **35.86** [w_conc=2.40, perplexity, 5KB] In comparison to the explosion of personal computing and Internet technology in 
- 206. **35.78** [w_conc=0.00, perplexity, 12KB] Are there any other books like this? What are the most authoritative books and a
- 207. **35.77** [w_conc=2.08, perplexity, 11KB] If you were to ask all the tech ceos incubators on how to build an mvp in this a
- 208. **35.75** [w_conc=0.00, perplexity, 10KB] who is the modern dasy gertrude steinThere is no widely recognized figure in con
- 209. **35.73** [w_conc=0.00, perplexity, 11KB] how to get rid of fear, or to act in fear, I'm scared of sudden movements and sc
- 210. **35.67** [w_conc=4.16, apple-notes, 6KB] apple-notes::June 2026
- 211. **35.66** [w_conc=0.00, perplexity, 27KB] I want to inquire into this commcerical property: https://www.realtor.ca/real-es
- 212. **35.62** [w_conc=4.16, apple-notes, 6KB] apple-notes::June 2026
- 213. **35.52** [w_conc=0.00, perplexity, 10KB] Singapore developed by creating an economy, focussed on foreign electronics ship
- 214. **35.50** [w_conc=1.61, perplexity, 17KB] how much does a used container cost so I can grow mushrooms in them, what is the
- 215. **35.49** [w_conc=0.00, thread, 39KB] Rent vs. buy analysis for Vancouver
- 216. **35.46** [w_conc=2.56, apple-notes, 5KB] #toknowthyself
- 217. **35.46** [w_conc=0.00, perplexity, 31KB] i want to fill international village mall in chinatown, I'm considering many opt
- 218. **35.44** [w_conc=4.16, apple-notes, 5KB] apple-notes::June 2026
- 219. **35.40** [w_conc=4.16, apple-notes, 5KB] apple-notes::June 2026
- 220. **35.38** [w_conc=4.16, apple-notes, 5KB] apple-notes::June 2026
- 221. **35.38** [w_conc=4.16, apple-notes, 6KB] apple-notes::June 2026
- 222. **35.34** [w_conc=2.83, perplexity, 12KB] People want to feel like they are the smartest person, or the most ethical, or t
- 223. **35.33** [w_conc=4.16, apple-notes, 5KB] apple-notes::June 2026
- 224. **35.32** [w_conc=4.16, apple-notes, 5KB] apple-notes::June 2026
- 225. **35.32** [w_conc=3.14, thread, 14KB] 💬 A system that surfaces all the…
- 226. **35.29** [w_conc=4.16, apple-notes, 5KB] apple-notes::June 2026
- 227. **35.25** [w_conc=4.16, apple-notes, 5KB] apple-notes::June 2026
- 228. **35.24** [w_conc=1.39, perplexity, 11KB] What has accounted for qqq rising to new high in the last 3 months?The primary d
- 229. **35.18** [w_conc=3.09, apple-notes, 5KB] International Villages
- 230. **35.14** [w_conc=0.00, perplexity, 5KB] https://www.perplexity.ai/page/canada-to-reinvent-economy-ami-xls3GS9CRuidp6jHBt
- 231. **35.08** [w_conc=0.00, perplexity, 8KB] Difference between psychology and psychiatry and other disciplines within that f
- 232. **35.03** [w_conc=0.00, perplexity, 20KB] When the market swings down dramatically like today, where does that capital go?
- 233. **35.02** [w_conc=0.00, perplexity, 26KB] what accounted for the dip in the markets on friday? Give me hedge fund level an
- 234. **34.94** [w_conc=4.16, apple-notes, 5KB] apple-notes::June 2026
- 235. **34.93** [w_conc=0.00, perplexity, 10KB] are there traders in the coffee commodities markets that make a living from itYe
- 236. **34.89** [w_conc=0.00, perplexity, 34KB] Health benefits of digestifsDigestifs, alcoholic beverages traditionally served 
- 237. **34.88** [w_conc=4.51, apple-notes, 4KB] Building credibility for a Google acquisition
- 238. **34.83** [w_conc=1.39, perplexity, 10KB] Is n8n the best workflow? What are adjacent tools? How does it work?N8n is a pow
- 239. **34.78** [w_conc=4.16, apple-notes, 5KB] apple-notes::June 2026
- 240. **34.78** [w_conc=0.00, perplexity, 36KB] what is the weight range for a 22cm black domestic shorthairFor an adult domesti

_(2381 additional low-score candidates omitted; see JSON for full list.)_
