# R Candidate Salience — Level 4 (adds IR / KR / Entity-Resolution / Cog-Sci axes) — 2026-09-01

Ranked candidates for the next ingestion round, scored via **weighted concept intersection** (Session-10 spec in `fuzzy-shimmying-wreath.md`).

**Disposable one-shot scorer.** Purpose: schedule which un-ingested wiki-raw sources get the next paid `claude -p` call. Not a peer of the post-ingest salience system (`wiki-salience.md` / `dream_bootstrap.py`); no eval, no versioning. Judged only by downstream post-ingest recall@10 lift. Retire when the wiki-raw backlog drains.

## Universe & filtering

- Total wiki-raw sections: **15747**
- Filtered out — `claude-code` per-turn fragments: **10435**
- Filtered out — malformed `claude-thread` orphans (name missing `::title::idx::role`): **663**
- Unique claude threads (well-formed): **139**
- Other sections (apple-notes, perplexity, ...): **2608**
- Already ingested into parallel vault: **155** files
- Skipped as already-ingested during scoring: **132**
- Skipped as empty body: **0**
- **Candidates evaluated: 2615**

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

**weighted_concept** — MIKAI-central signal. Sums `log(1+in-degree)` over concept slugs (min length 5, kebab-case) hit in source body. Max concept weight this run: **3.76**. Vocab: 715 slugs.

**weighted_personal** — broader Brian-profile signal (Level 3 addition). Sums per-token weight from a compiled personal vocabulary. Sources: USER_MODEL.md (1.5), PROFILE.md (1.0), BRAIN.md priorities (0.7), entity slugs (0.5), wisdom/goals/habits/reflections (0.5), queries (0.4), journal tags (0.3). Max personal weight this run: **1.50**. Vocab: 2696 tokens. Tokens already in concept vocab are excluded from this component to avoid double-counting.

Goal source: `~/.mikai/brain/GOALS.md` (10 goals).

### Level 4 additions (4 new axes from `docs/INGESTION_LOG.md` 8-discipline scorecard)

- **axis_a_retrieval** (IR, weight +1.0): overlap with tokens in `wiki/queries/*.md` — predicts which candidates will get queried later.
- **axis_b_novelty** (KR, weight +1.0): 2-3-word kebab-phrases in body NOT already in concept vocab — sources that expand vocabulary score higher.
- **axis_c_alias_risk** (Entity Resolution, weight -0.5): near-matches to existing slugs (substring + prefix + Jaro-Winkler > 0.85) — high risk = likely to produce dupes.
- **axis_g_episodic_score** (Cognitive Science, no direct weight): 0.0=episodic, 1.0=semantic, 0.5=ambiguous. Routing signal only — emitted for downstream page-type placement.

## Top 40 candidates

| # | score | l3.1 | w_conc | w_pers | axA | axB | axC | axG | kind | KB | turns | title |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 61.16 | 59.57 | 11.70 | 43.95 | 1.00 | 1.00 | -0.41 | 0.50 | perplexity | 40 | — | Ha-Joon Chang, Byung-Chul Han Sandwich there was a thre |
| 2 | 58.59 | 56.99 | 11.84 | 41.57 | 1.00 | 1.00 | -0.40 | 0.50 | perplexity | 21 | — | Can you read the transcript of this video: https://www. |
| 3 | 56.86 | 55.29 | 3.58 | 47.67 | 1.00 | 1.00 | -0.43 | 0.50 | perplexity | 34 | — | can you analyze vancouver brand aritzia and their expan |
| 4 | 56.75 | 55.16 | 3.09 | 48.00 | 1.00 | 0.60 | -0.00 | 0.50 | apple-notes | 24 | — | apple-notes::Feb 2025 - David and the Dao |
| 5 | 56.18 | 54.30 | 5.03 | 45.84 | 1.00 | 1.00 | -0.12 | 0.50 | perplexity | 16 | — | What startups have come out of ihub that are significan |
| 6 | 55.21 | 53.54 | 1.61 | 47.65 | 1.00 | 1.00 | -0.32 | 0.50 | perplexity | 97 | — | EC Rare Book market research: What is the value of the  |
| 7 | 54.84 | 53.22 | 2.40 | 47.09 | 1.00 | 1.00 | -0.38 | 0.00 | perplexity | 29 | — | Anthropic open ai, and perplexity valuation,   What are |
| 8 | 53.82 | 52.12 | 7.72 | 40.37 | 1.00 | 1.00 | -0.30 | 0.50 | perplexity | 55 | — | Entj 7w8 vs 8w7. I want to know which one I amTo determ |
| 9 | 53.38 | 51.68 | 4.03 | 43.99 | 1.00 | 1.00 | -0.30 | 0.50 | perplexity | 20 | — | vancouver from early 2000s to 2021 faced unprecendented |
| 10 | 53.26 | 51.65 | 5.99 | 41.56 | 1.00 | 1.00 | -0.38 | 0.00 | perplexity | 98 | — | (Bot) Options Trading StrategiesVolatility arbitrage (v |
| 11 | 53.02 | 51.02 | 5.60 | 41.97 | 1.00 | 1.00 | -0.00 | 0.50 | perplexity | 16 | — | never split the difference, book on negotiation and com |
| 12 | 52.68 | 51.00 | 2.89 | 44.15 | 1.00 | 1.00 | -0.32 | 0.50 | perplexity | 32 | — | what to enfj's day dream aboutENFJs most often daydream |
| 13 | 52.28 | 50.58 | 0.00 | 46.58 | 1.00 | 1.00 | -0.30 | 0.50 | perplexity | 41 | — | I want to fill international village in chinatown with  |
| 14 | 52.01 | 50.43 | 5.16 | 41.49 | 1.00 | 1.00 | -0.43 | 0.00 | perplexity | 36 | — | give me updates of nvda appl and tsla today in the news |
| 15 | 51.55 | 49.81 | 0.00 | 46.01 | 1.00 | 1.00 | -0.27 | 0.00 | perplexity | 36 | — | Are there any examples of an all ai news YouTube or Spo |
| 16 | 50.75 | 49.13 | 1.61 | 44.49 | 1.00 | 0.93 | -0.30 | 0.50 | apple-notes | 4 | — | memories |
| 17 | 50.38 | 48.71 | 0.00 | 45.39 | 1.00 | 1.00 | -0.32 | 0.50 | perplexity | 10 | — | If AGI is for sure coming, explain the landscape or top |
| 18 | 50.33 | 48.63 | 2.89 | 41.91 | 1.00 | 0.93 | -0.23 | 0.50 | perplexity | 45 | — | I want to put on a bear call for tech stocks related to |
| 19 | 50.08 | 48.36 | 11.78 | 33.60 | 1.00 | 0.90 | -0.18 | 0.50 | apple-notes | 4 | — | Modern solutions for the rentiers problem |
| 20 | 49.95 | 48.21 | 0.69 | 43.37 | 1.00 | 1.00 | -0.27 | 0.00 | perplexity | 97 | — | assessed property value vs fair market value?Assessed p |
| 21 | 49.35 | 47.67 | 3.69 | 40.55 | 1.00 | 1.00 | -0.32 | 0.50 | perplexity | 17 | — | Wha are ai agent swarmsAI agent swarms are groups of sp |
| 22 | 49.01 | 47.78 | 5.73 | 38.65 | 1.00 | 0.23 | -0.00 | 0.50 | perplexity | 17 | — | Forget a recession. What Canadians are living through i |
| 23 | 48.84 | 47.31 | 4.85 | 38.78 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 11 | — | apple-notes::June 2026 |
| 24 | 48.84 | 47.30 | 4.85 | 38.77 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 11 | — | apple-notes::June 2026 |
| 25 | 47.95 | 46.42 | 4.85 | 37.92 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 26 | 47.61 | 46.07 | 4.85 | 37.63 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 27 | 47.39 | 45.69 | 2.71 | 39.89 | 1.00 | 1.00 | -0.30 | 0.00 | thread | 23 | 4 | Kenya's renewable energy advantages and scalability |
| 28 | 47.36 | 45.82 | 4.85 | 37.38 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 29 | 47.32 | 45.43 | 2.08 | 40.09 | 1.00 | 1.00 | -0.12 | 0.50 | perplexity | 13 | — | How valuable is OCR data from social media. A lot i ima |
| 30 | 47.31 | 45.77 | 4.85 | 37.30 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 31 | 47.02 | 45.48 | 4.16 | 37.77 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 32 | 47.01 | 45.47 | 4.16 | 37.76 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 33 | 46.98 | 45.45 | 4.16 | 37.74 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 34 | 46.97 | 45.43 | 4.16 | 37.71 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 35 | 46.96 | 45.43 | 4.16 | 37.71 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 9 | — | apple-notes::June 2026 |
| 36 | 46.95 | 45.41 | 4.16 | 37.68 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 37 | 46.87 | 45.33 | 4.16 | 37.58 | 1.00 | 0.54 | -0.00 | 0.50 | apple-notes | 10 | — | apple-notes::June 2026 |
| 38 | 46.62 | 44.74 | 0.00 | 41.69 | 1.00 | 1.00 | -0.12 | 0.50 | thread | 19 | 4 | Scraping social media data for AI training |
| 39 | 46.21 | 44.48 | 0.00 | 40.66 | 1.00 | 1.00 | -0.27 | 0.50 | perplexity | 38 | — | can you give me an overview of henderson development in |
| 40 | 46.05 | 44.24 | 0.00 | 40.31 | 1.00 | 1.00 | -0.18 | 0.50 | perplexity | 32 | — | what do the people of south korea, yantai, qingdao and  |

### Top concept + personal hits per candidate (top 15)

- **1.** Ha-Joon Chang, Byung-Chul Han Sandwich there was a thread th
  - concepts: `individuation-of-systemic-problems` (2.30), `market-fundamentalism` (2.20), `information-metabolism` (2.08)
  - personal: `cleaner` (1.50), `compiled` (1.50), `nothing` (1.50)
- **2.** Can you read the transcript of this video: https://www.youtu
  - concepts: `bids-for-connection` (1.79), `hedonic-adaptation` (1.79), `fearful-avoidant-attachment` (1.61)
  - personal: `nothing` (1.50), `context` (1.50), `better` (1.50)
- **3.** can you analyze vancouver brand aritzia and their expansion 
  - concepts: `fast-fashion-decline` (1.39), `challenger-sportswear-brands` (1.10), `solarpunk-minimal` (1.10)
  - personal: `choice` (1.50), `context` (1.50), `direct` (1.50)
- **4.** apple-notes::Feb 2025 - David and the Dao
  - concepts: `consumer-groups` (3.09)
  - personal: `nothing` (1.50), `context` (1.50), `better` (1.50)
- **5.** What startups have come out of ihub that are significant? Wh
  - concepts: `regulatory-capture` (2.83), `silicon-savannah` (2.20)
  - personal: `closing` (1.50), `context` (1.50), `constrained` (1.50)
- **6.** EC Rare Book market research: What is the value of the rare 
  - concepts: `information-asymmetry` (1.61)
  - personal: `evaluating` (1.50), `hosted` (1.50), `proposal` (1.50)
- **7.** Anthropic open ai, and perplexity valuation,   What are thei
  - concepts: `model-context-protocol` (2.40)
  - personal: `closing` (1.50), `pushed` (1.50), `hosted` (1.50)
- **8.** Entj 7w8 vs 8w7. I want to know which one I amTo determine w
  - concepts: `consumer-groups` (3.09), `wu-wei` (2.83), `enneagram-8w7` (1.79)
  - personal: `choice` (1.50), `autonomous` (1.50), `context` (1.50)
- **9.** vancouver from early 2000s to 2021 faced unprecendented grow
  - concepts: `information-metabolism` (2.08), `iphone-convergence-thesis` (1.95)
  - personal: `cleaner` (1.50), `context` (1.50), `reframed` (1.50)
- **10.** (Bot) Options Trading StrategiesVolatility arbitrage (vol ar
  - concepts: `iron-condor` (1.61), `long-straddle` (1.61), `bull-call-spread` (1.39)
  - personal: `closing` (1.50), `observed` (1.50), `hosted` (1.50)
- **11.** never split the difference, book on negotiation and communic
  - concepts: `tactical-empathy` (2.20), `calibrated-questions` (1.79), `ackerman-bargaining-model` (1.61)
  - personal: `choice` (1.50), `treats` (1.50), `proposal` (1.50)
- **12.** what to enfj's day dream aboutENFJs most often daydream abou
  - concepts: `socionics-intertype-relations` (1.79), `maladaptive-daydreaming` (1.10)
  - personal: `closing` (1.50), `treats` (1.50), `direct` (1.50)
- **13.** I want to fill international village in chinatown with buddi
  - concepts: —
  - personal: `evaluating` (1.50), `hosted` (1.50), `proposal` (1.50)
- **14.** give me updates of nvda appl and tsla today in the newsHere'
  - concepts: `market-psychology` (1.95), `iron-butterfly` (1.61), `long-straddle` (1.61)
  - personal: `context` (1.50), `direct` (1.50), `evidence` (1.50)
- **15.** Are there any examples of an all ai news YouTube or Spotify 
  - concepts: —
  - personal: `choice` (1.50), `nothing` (1.50), `hosted` (1.50)

## Recommended next batch (top 30)

- Total volume: **904KB** across 30 sources
- Est. wall-clock: **~12min** at workers=8, **~100min** at workers=1 (assumes ~200s/source average)
- Would land as R3-2026-09-01-mikai-followup

| # | score | w_conc | w_pers | title | KB | filename |
|---|---|---|---|---|---|---|
| 1 | 61.16 | 11.70 | 43.95 | Ha-Joon Chang, Byung-Chul Han Sandwich there was a thread th | 40 | `2026-03-19-ha-joon-chang-byung-chul-han-sandwich-there-was-a-thread-tha-5b63a0.md` |
| 2 | 58.59 | 11.84 | 41.57 | Can you read the transcript of this video: https://www.youtu | 21 | `2026-03-19-can-you-read-the-transcript-of-this-video-https-www-youtube-638be7.md` |
| 3 | 56.86 | 3.58 | 47.67 | can you analyze vancouver brand aritzia and their expansion  | 34 | `2026-03-19-can-you-analyze-vancouver-brand-aritzia-and-their-expansion-3b49b5.md` |
| 4 | 56.75 | 3.09 | 48.00 | apple-notes::Feb 2025 - David and the Dao | 24 | `2026-07-04-apple-notes-feb-2025-david-and-the-dao-562159.md` |
| 5 | 56.18 | 5.03 | 45.84 | What startups have come out of ihub that are significant? Wh | 16 | `2026-03-19-what-startups-have-come-out-of-ihub-that-are-significant-wha-260e5a.md` |
| 6 | 55.21 | 1.61 | 47.65 | EC Rare Book market research: What is the value of the rare  | 97 | `2026-03-19-ec-rare-book-market-research-what-is-the-value-of-the-rare-b-17c258.md` |
| 7 | 54.84 | 2.40 | 47.09 | Anthropic open ai, and perplexity valuation,   What are thei | 29 | `2026-03-19-anthropic-open-ai-and-perplexity-valuation-what-are-their-re-5f7671.md` |
| 8 | 53.82 | 7.72 | 40.37 | Entj 7w8 vs 8w7. I want to know which one I amTo determine w | 55 | `2026-03-19-entj-7w8-vs-8w7-i-want-to-know-which-one-i-amto-determine-wh-be7b3f.md` |
| 9 | 53.38 | 4.03 | 43.99 | vancouver from early 2000s to 2021 faced unprecendented grow | 20 | `2026-03-19-vancouver-from-early-2000s-to-2021-faced-unprecendented-grow-c5665b.md` |
| 10 | 53.26 | 5.99 | 41.56 | (Bot) Options Trading StrategiesVolatility arbitrage (vol ar | 98 | `2026-03-19-bot-options-trading-strategiesvolatility-arbitrage-vol-arb-i-40937e.md` |
| 11 | 53.02 | 5.60 | 41.97 | never split the difference, book on negotiation and communic | 16 | `2026-03-19-never-split-the-difference-book-on-negotiation-and-communica-c4a827.md` |
| 12 | 52.68 | 2.89 | 44.15 | what to enfj's day dream aboutENFJs most often daydream abou | 32 | `2026-03-19-what-to-enfj-s-day-dream-aboutenfjs-most-often-daydream-abou-477cde.md` |
| 13 | 52.28 | 0.00 | 46.58 | I want to fill international village in chinatown with buddi | 41 | `2026-03-19-i-want-to-fill-international-village-in-chinatown-with-buddi-959b6f.md` |
| 14 | 52.01 | 5.16 | 41.49 | give me updates of nvda appl and tsla today in the newsHere' | 36 | `2026-03-19-give-me-updates-of-nvda-appl-and-tsla-today-in-the-newshere-725656.md` |
| 15 | 51.55 | 0.00 | 46.01 | Are there any examples of an all ai news YouTube or Spotify  | 36 | `2026-03-19-are-there-any-examples-of-an-all-ai-news-youtube-or-spotify-a2fcf1.md` |
| 16 | 50.75 | 1.61 | 44.49 | memories | 4 | `2026-03-19-memories-fc9f32.md` |
| 17 | 50.38 | 0.00 | 45.39 | If AGI is for sure coming, explain the landscape or topograp | 10 | `2026-03-19-if-agi-is-for-sure-coming-explain-the-landscape-or-topograph-c84f94.md` |
| 18 | 50.33 | 2.89 | 41.91 | I want to put on a bear call for tech stocks related to ai a | 45 | `2026-03-19-i-want-to-put-on-a-bear-call-for-tech-stocks-related-to-ai-a-b2dc55.md` |
| 19 | 50.08 | 11.78 | 33.60 | Modern solutions for the rentiers problem | 4 | `2026-03-19-modern-solutions-for-the-rentiers-problem-05add8.md` |
| 20 | 49.95 | 0.69 | 43.37 | assessed property value vs fair market value?Assessed proper | 97 | `2026-03-19-assessed-property-value-vs-fair-market-value-assessed-proper-978af9.md` |
| 21 | 49.35 | 3.69 | 40.55 | Wha are ai agent swarmsAI agent swarms are groups of special | 17 | `2026-03-19-wha-are-ai-agent-swarmsai-agent-swarms-are-groups-of-special-02c38a.md` |
| 22 | 49.01 | 5.73 | 38.65 | Forget a recession. What Canadians are living through is wor | 17 | `2026-03-19-forget-a-recession-what-canadians-are-living-through-is-wors-889efc.md` |
| 23 | 48.84 | 4.85 | 38.78 | apple-notes::June 2026 | 11 | `2026-07-12-apple-notes-june-2026-c067f3.md` |
| 24 | 48.84 | 4.85 | 38.77 | apple-notes::June 2026 | 11 | `2026-07-13-apple-notes-june-2026-c067f3.md` |
| 25 | 47.95 | 4.85 | 37.92 | apple-notes::June 2026 | 10 | `2026-07-11-apple-notes-june-2026-c067f3.md` |
| 26 | 47.61 | 4.85 | 37.63 | apple-notes::June 2026 | 10 | `2026-07-09-apple-notes-june-2026-c067f3.md` |
| 27 | 47.39 | 2.71 | 39.89 | Kenya's renewable energy advantages and scalability | 23 | `2026-02-20-kenya-s-renewable-energy-advantages-and-scalability-e7a244.md` |
| 28 | 47.36 | 4.85 | 37.38 | apple-notes::June 2026 | 10 | `2026-07-09-apple-notes-june-2026-c067f3.md` |
| 29 | 47.32 | 2.08 | 40.09 | How valuable is OCR data from social media. A lot i imagineY | 13 | `2026-03-19-how-valuable-is-ocr-data-from-social-media-a-lot-i-imagineyo-e87a25.md` |
| 30 | 47.31 | 4.85 | 37.30 | apple-notes::June 2026 | 10 | `2026-07-10-apple-notes-june-2026-c067f3.md` |

## Appendix — next 200 candidates (rank 41+, brief)

- 41. **45.99** [w_conc=3.00, perplexity, 27KB] tell me many variants of loss leader strategy across many industries. Bridge the
- 42. **45.96** [w_conc=2.20, thread, 174KB] Wind-resistant plants for apartment living
- 43. **45.85** [w_conc=4.16, apple-notes, 9KB] apple-notes::June 2026
- 44. **45.79** [w_conc=4.16, apple-notes, 9KB] apple-notes::June 2026
- 45. **45.78** [w_conc=4.16, apple-notes, 9KB] apple-notes::June 2026
- 46. **45.75** [w_conc=4.16, apple-notes, 9KB] apple-notes::June 2026
- 47. **45.75** [w_conc=4.16, apple-notes, 9KB] apple-notes::June 2026
- 48. **45.75** [w_conc=4.16, apple-notes, 9KB] apple-notes::June 2026
- 49. **45.74** [w_conc=4.16, apple-notes, 9KB] apple-notes::June 2026
- 50. **45.68** [w_conc=4.16, apple-notes, 9KB] apple-notes::June 2026
- 51. **45.63** [w_conc=4.16, apple-notes, 11KB] apple-notes::June 2026
- 52. **45.60** [w_conc=4.16, apple-notes, 9KB] apple-notes::June 2026
- 53. **45.51** [w_conc=4.16, apple-notes, 9KB] apple-notes::June 2026
- 54. **45.43** [w_conc=4.16, apple-notes, 9KB] apple-notes::June 2026
- 55. **45.37** [w_conc=9.63, thread, 6KB] Mapping economic chokepoints for strategic advantage
- 56. **45.28** [w_conc=0.00, perplexity, 12KB] So how has Peter thiel executed on this philosophy?Peter Thiel has executed this
- 57. **45.12** [w_conc=3.09, perplexity, 85KB] what is the first home buyers account in canadaThe First Home Savings Account (F
- 58. **45.05** [w_conc=1.61, thread, 26KB] Agentic marketplace for used goods
- 59. **45.03** [w_conc=0.00, perplexity, 31KB] I want to create a business service that acts as broker for leases, and interior
- 60. **44.89** [w_conc=0.00, perplexity, 7KB] Where is the state of Ai agents right now? How powerful are they in producing ac
- 61. **44.66** [w_conc=0.00, perplexity, 23KB] Below is the problem my engineering team is trying to solve. Give me a high leve
- 62. **44.36** [w_conc=0.00, perplexity, 10KB] It seems like the concept of AI agents have existed since the 80s. I remember re
- 63. **44.24** [w_conc=0.00, perplexity, 99KB] My cats poo is dark brown and it’s almost black, but we’re worried by looking at
- 64. **44.24** [w_conc=0.00, perplexity, 99KB] In frostpunk 2 what is the best strategy: tech, exploration, etcFor Frostpunk 2 
- 65. **44.02** [w_conc=1.61, thread, 9KB] Identifying productivity theater in daily habits
- 66. **44.01** [w_conc=0.00, perplexity, 23KB] David defeated the philistines with a stone and momentumDavid defeated Goliath b
- 67. **43.78** [w_conc=0.00, thread, 10KB] Beyond the LLM hype: what AI has actually delivered
- 68. **43.66** [w_conc=0.00, perplexity, 27KB] a fully transcend entj will act more like a?A fully realized, transcendent ENTJ 
- 69. **43.64** [w_conc=2.08, perplexity, 27KB] are there any other companies like scale ai but at lower valuations? can you giv
- 70. **43.63** [w_conc=0.69, perplexity, 33KB] Using first principles I want to find out why housing costs are so expensive. We
- 71. **43.61** [w_conc=9.71, thread, 5KB] Building MIKAI prototype from PRD
- 72. **43.50** [w_conc=0.00, perplexity, 18KB] For tech jobs, typically the big 5 was considered optimal. I want the next up an
- 73. **43.36** [w_conc=0.00, perplexity, 40KB] What were the rewards for bitcoin mining from 2012-2016Introverted-intuition tak
- 74. **43.29** [w_conc=0.00, perplexity, 65KB] I want to hook up my voice memos so that the automatically get inserted into rea
- 75. **43.27** [w_conc=0.00, perplexity, 14KB] Who is the content creator or social media head that is the best at assessing ne
- 76. **43.17** [w_conc=0.00, thread, 24KB] Digital assistant that adapts to you, not the other way arou
- 77. **43.06** [w_conc=1.79, perplexity, 29KB] Mark and I close university friends and have also been roommates after college t
- 78. **42.89** [w_conc=2.08, perplexity, 25KB] Give me the gdp per capita (ppp and nominal) of these countries: Kenya Mexico, V
- 79. **42.82** [w_conc=2.40, perplexity, 20KB] From everything we have discussed in this space called International Village, gi
- 80. **42.82** [w_conc=1.95, perplexity, 10KB] What is the core problem and core solution for international village mall. Expla
- 81. **42.82** [w_conc=1.39, perplexity, 13KB] There’s an social principle where if the size of a community grows to over 500, 
- 82. **42.80** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] what the moat looks like in features — strategic-synthesis-2026-06-14: 2. The de
- 83. **42.80** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] what the moat looks like in features — strategic-insights: 2. The depth thesis —
- 84. **42.68** [w_conc=0.00, perplexity, 11KB] Simulation Modelling: personality, business physics ~~ movement of people within
- 85. **42.67** [w_conc=0.00, thread, 30KB] Best iPhone generation to buy: first or stabilized iteration
- 86. **42.62** [w_conc=0.00, thread, 59KB] Crypto transfer phone scam
- 87. **42.37** [w_conc=0.00, perplexity, 15KB] We know a start of founder that started his original business in 2012 and had fa
- 88. **42.36** [w_conc=0.69, perplexity, 15KB] i like Ha-Joon Chang, are there any other like him, who would be the best from p
- 89. **42.31** [w_conc=1.61, perplexity, 27KB] I want to create a webapp tool that: allows you to search youtube explore page a
- 90. **42.16** [w_conc=1.61, perplexity, 9KB] It seems like to an entj, while an esfp is an activity partner, they can often t
- 91. **42.11** [w_conc=0.00, perplexity, 14KB] can you give me a description of the eyes of and estj vs entj vs intjHere is a d
- 92. **42.11** [w_conc=0.00, thread, 25KB] Private equity investment targets
- 93. **42.10** [w_conc=0.00, perplexity, 15KB] Tell me about the tax-free zone in Songdo, Incheon, Korea. What counts as R&D? S
- 94. **42.07** [w_conc=2.08, perplexity, 12KB] Cna you do an analysis of the coffee commodities market? What account for the pr
- 95. **41.95** [w_conc=0.00, perplexity, 17KB] how did bob rennie start his firm, what was the startBob Rennie started his firm
- 96. **41.91** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 97. **41.91** [w_conc=1.61, thread, 6KB] Anthropic blocks Claude Pro OAuth tokens
- 98. **41.79** [w_conc=2.83, perplexity, 16KB] what is the definition of ditzy. can you analyze in it the context of a socionic
- 99. **41.72** [w_conc=5.44, apple-notes, 4KB] The Hard Truth about 2nd Brain: Rewind AI's & Consumer Adaptation
- 100. **41.71** [w_conc=0.00, perplexity, 12KB] International village in downtown Vancouver has huge vacancy right now, and they
- 101. **41.68** [w_conc=0.00, perplexity, 19KB] In the Vancouver market, retail and f&b are struggling because of their low marg
- 102. **41.51** [w_conc=1.39, perplexity, 24KB] I was caught smoking outside the Nairobi airport and a police officer want to ta
- 103. **41.46** [w_conc=0.00, perplexity, 15KB] https://youtu.be/frqiUkjxAOE?si=rlTjy7QvhXn4gS_H  Can yo summarize this videoChr
- 104. **41.44** [w_conc=0.00, perplexity, 31KB] Chochu trading co.  Beyond goods: how to circumvent tariffs If we import Chinese
- 105. **41.43** [w_conc=1.10, thread, 13KB] Continuing markdown conversations on Perplexity
- 106. **41.39** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 107. **41.35** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 108. **41.33** [w_conc=0.00, perplexity, 8KB] Dr Arthur Brooks  https://youtu.be/5mpyFuyIQ14?si=OGjygtIocomSlz7q  What persona
- 109. **41.31** [w_conc=3.14, thread, 12KB] Steve Jobs' prioritization meeting story
- 110. **41.21** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 111. **41.16** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 112. **41.15** [w_conc=0.00, perplexity, 19KB] What happening in the market today particularly in the tech sector, and you look
- 113. **41.15** [w_conc=0.00, perplexity, 7KB] I love playing catan, eu4, civilization, poker. What are the the skills in those
- 114. **41.14** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 115. **41.13** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 116. **41.12** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 117. **41.12** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 118. **41.09** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 119. **41.07** [w_conc=0.00, perplexity, 14KB] The first business that I want to build out for in international villages mall i
- 120. **41.02** [w_conc=2.08, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 121. **40.99** [w_conc=0.00, perplexity, 18KB] the apartments by international village mall and roger's arena, is that area cal
- 122. **40.97** [w_conc=0.00, perplexity, 4KB] How did ai fix the roaming the internet and performing actions problem, list the
- 123. **40.87** [w_conc=4.85, thread, 4KB] Project problem framing analysis
- 124. **40.81** [w_conc=0.00, perplexity, 13KB] what is a split-screen cycle in economicsA split-screen cycle in economics refer
- 125. **40.79** [w_conc=0.00, thread, 86KB] Forward head posture root causes
- 126. **40.76** [w_conc=0.00, perplexity, 22KB] I had a dream catcher when I was young , do cats act as a dream catcher?Cats are
- 127. **40.70** [w_conc=0.00, perplexity, 16KB] is weride a chinese company? What are the prices for their robo sweepers and sim
- 128. **40.69** [w_conc=0.00, thread, 17KB] Andre Iguodala's personality type
- 129. **40.68** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 130. **40.66** [w_conc=0.00, perplexity, 8KB] I want to create business model and plan to present for federal and provincial g
- 131. **40.63** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 132. **40.59** [w_conc=2.08, perplexity, 5KB] what is the status of ai agents right now? What actions can they perform? What a
- 133. **40.18** [w_conc=0.00, perplexity, 47KB] what are the highest rated cat vets in vancouverI can’t reliably rank “highest r
- 134. **40.17** [w_conc=2.08, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 135. **40.14** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 136. **40.11** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 137. **40.11** [w_conc=0.00, thread, 43KB] INTJ's ideal personality match
- 138. **40.09** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 139. **40.05** [w_conc=2.08, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 140. **40.01** [w_conc=0.00, perplexity, 35KB] i'm being interview for a job as a starting engineer at a ai tech startup in can
- 141. **39.99** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 142. **39.96** [w_conc=2.08, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 143. **39.94** [w_conc=2.08, apple-notes, 5KB] apple-notes::July 2026
- 144. **39.93** [w_conc=0.00, perplexity, 5KB] If AGI is for sure coming, explain the landscape or topography of AGI as an anal
- 145. **39.86** [w_conc=0.00, perplexity, 10KB] what are creative ways that ai agent can chagne the coffee industryAI agents are
- 146. **39.84** [w_conc=0.00, thread, 6KB] Nairobi's infrastructure gaps and AI-enhanced tools
- 147. **39.84** [w_conc=0.00, perplexity, 25KB] Best cafes in Nairobi that tech workers work at. I usually go to coffee shops li
- 148. **39.68** [w_conc=0.00, perplexity, 6KB] describe the the I's that is shown in this video: https://www.youtube.com/watch?
- 149. **39.51** [w_conc=1.39, perplexity, 9KB] I looking for a Vancouver economic group that believes in Georgiam or Joseph sti
- 150. **39.48** [w_conc=0.00, perplexity, 12KB] Activist investor invests 2b into workdayAn activist investor, Elliott Investmen
- 151. **39.47** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 7. Paths forward, ranked by historical viability
- 152. **39.47** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 7. Paths forward, ranked by historical viability
- 153. **39.46** [w_conc=2.08, perplexity, 40KB] Our cat that we’ve had for three weeks now who’s peed for the first time when we
- 154. **39.26** [w_conc=0.00, perplexity, 29KB] can you do a case study on instant financial https://www.instant.co/ and how the
- 155. **39.25** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 156. **39.23** [w_conc=0.00, perplexity, 8KB] as an entj, my ti has always been weak in school, so understand a chain of relat
- 157. **39.21** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 158. **39.08** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 159. **39.08** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 160. **38.93** [w_conc=0.00, perplexity, 24KB] Toyota hybrid suv that is the highest ratedThe highest-rated Toyota hybrid SUV r
- 161. **38.88** [w_conc=0.00, perplexity, 7KB] Below are my notes for International Villages project I've been working on this 
- 162. **38.82** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 163. **38.80** [w_conc=0.00, perplexity, 13KB] wealth management firm and industry overviewIntroverted Intuition – Key Insight 
- 164. **38.71** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 165. **38.69** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 166. **38.65** [w_conc=0.00, perplexity, 9KB] What happened to activist investing? Is there an investing principle or an organ
- 167. **38.65** [w_conc=0.00, thread, 12KB] Finding the weak link in AI's circular economy
- 168. **38.64** [w_conc=7.54, apple-notes, 4KB] Building credibility for a Google acquisition
- 169. **38.63** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 170. **38.59** [w_conc=0.00, perplexity, 22KB] Fed chair update and what it means for the market, why did trump want Jerome Pow
- 171. **38.56** [w_conc=0.00, perplexity, 10KB] Restaurants in Vancouver are dying right now because people don’t have enough di
- 172. **38.51** [w_conc=0.00, perplexity, 34KB] Can I self inject this?Self-injecting GHK-Cu (Copper Peptide) purchased online i
- 173. **38.49** [w_conc=0.00, thread, 17KB] Electrician career paths in BC for low-voltage experience
- 174. **38.49** [w_conc=1.10, thread, 19KB] Low voltage electrical companies in BC for Patrick
- 175. **38.48** [w_conc=0.00, perplexity, 49KB] where does qatar airways rank in qualitty and comfortQatar Airways ranks #1 in t
- 176. **38.48** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 177. **38.39** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] the OS-absorbs-the-assistant stress test — strategic-insights: 1. Threat landsca
- 178. **38.35** [w_conc=0.00, perplexity, 58KB] I sit a lot during the day, I vape, and game on the computer a couple hours a da
- 179. **38.34** [w_conc=0.00, perplexity, 7KB] What are the key things that create good managers vs good creatorsThe most criti
- 180. **38.23** [w_conc=0.00, thread, 9KB] WiFi-based motion tracking for physio apps
- 181. **38.21** [w_conc=0.00, perplexity, 10KB] Singapore developed by creating an economy, focussed on foreign electronics ship
- 182. **38.15** [w_conc=3.09, apple-notes, 5KB] International Villages
- 183. **38.13** [w_conc=0.00, perplexity, 15KB] Can you break down why on average 400 K to build a condo unit in Canada?Short an
- 184. **38.12** [w_conc=0.00, perplexity, 10KB] who is the modern dasy gertrude steinThere is no widely recognized figure in con
- 185. **38.04** [w_conc=0.00, perplexity, 31KB] i want to fill international village mall in chinatown, I'm considering many opt
- 186. **38.02** [w_conc=4.74, apple-notes, 2KB] MIKAI Feature: Ai directed content
- 187. **38.00** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 188. **37.95** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 189. **37.92** [w_conc=4.16, apple-notes, 7KB] apple-notes::June 2026
- 190. **37.92** [w_conc=2.40, perplexity, 5KB] In comparison to the explosion of personal computing and Internet technology in 
- 191. **37.86** [w_conc=0.00, perplexity, 20KB] In sports, and with my friends, I seem to alway be encouraging, and give thought
- 192. **37.86** [w_conc=0.00, perplexity, 27KB] I want to inquire into this commcerical property: https://www.realtor.ca/real-es
- 193. **37.82** [w_conc=0.00, perplexity, 10KB] are there traders in the coffee commodities markets that make a living from itYe
- 194. **37.79** [w_conc=2.08, perplexity, 11KB] If you were to ask all the tech ceos incubators on how to build an mvp in this a
- 195. **37.78** [w_conc=0.00, perplexity, 23KB] It’s not creditors, I have my business listed as a sole proprietorship and I owe
- 196. **37.68** [w_conc=2.08, apple-notes, 5KB] apple-notes::July 2026
- 197. **37.58** [w_conc=0.69, perplexity, 26KB] what accounted for the dip in the markets on friday? Give me hedge fund level an
- 198. **37.54** [w_conc=0.00, thread, 9KB] Derek's systems thinking and applications to AI and geopolit
- 199. **37.42** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 9. Why no consumer Glean exists
- 200. **37.42** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 9. Why no consumer Glean exists
- 201. **37.41** [w_conc=2.83, perplexity, 9KB] what is the taoist principle of acting and not tryingThe Taoist principle of act
- 202. **37.39** [w_conc=0.00, perplexity, 12KB] Are there any other books like this? What are the most authoritative books and a
- 203. **37.36** [w_conc=1.95, perplexity, 3KB] “Based on everything you know about me from our full chat history and memory, gi
- 204. **37.21** [w_conc=0.00, perplexity, 45KB] For an entj, describe relationships with esfp vs enfpAs an ENTJ, your relationsh
- 205. **37.18** [w_conc=2.08, perplexity, 24KB] Is there such thing as our cats not wanting to come into me and my partner‘s roo
- 206. **37.17** [w_conc=0.00, apple-notes, 4KB] Mika architecture ideas
- 207. **37.13** [w_conc=2.71, thread, 4KB] Finding your ideal sports coaching philosophy
- 208. **37.07** [w_conc=1.61, perplexity, 17KB] how much does a used container cost so I can grow mushrooms in them, what is the
- 209. **37.02** [w_conc=0.00, thread, 39KB] Rent vs. buy analysis for Vancouver
- 210. **37.02** [w_conc=3.69, apple-notes, 4KB] Making AI invisible through personalized knowledge architecture
- 211. **36.92** [w_conc=0.00, perplexity, 14KB] how big in the coffee market annuallyThe global coffee market is roughly $176–25
- 212. **36.91** [w_conc=3.69, claude, 4KB] claude: Making AI invisible through personalized knowledge architect
- 213. **36.89** [w_conc=0.00, perplexity, 5KB] https://www.perplexity.ai/page/canada-to-reinvent-economy-ami-xls3GS9CRuidp6jHBt
- 214. **36.89** [w_conc=0.00, thread, 15KB] Millionaires in China by age
- 215. **36.88** [w_conc=0.00, perplexity, 39KB] What are some of the rarest mines in the world for components for high techIntro
- 216. **36.82** [w_conc=2.71, apple-notes, 5KB] #toknowthyself
- 217. **36.73** [w_conc=0.00, perplexity, 34KB] Health benefits of digestifsDigestifs, alcoholic beverages traditionally served 
- 218. **36.63** [w_conc=2.83, perplexity, 12KB] People want to feel like they are the smartest person, or the most ethical, or t
- 219. **36.61** [w_conc=0.00, perplexity, 7KB] Can you ask my mentors what they think of this? Is this true or can you focus on
- 220. **36.59** [w_conc=0.00, perplexity, 20KB] What is the price of a new Tesla right now for a model three what is the best op
- 221. **36.58** [w_conc=0.00, perplexity, 20KB] When the market swings down dramatically like today, where does that capital go?
- 222. **36.45** [w_conc=0.00, perplexity, 11KB] how to get rid of fear, or to act in fear, I'm scared of sudden movements and sc
- 223. **36.44** [w_conc=0.00, perplexity, 10KB] what do you need to understand about geopoliticals and the economy to operate a 
- 224. **36.39** [w_conc=1.39, perplexity, 10KB] Is n8n the best workflow? What are adjacent tools? How does it work?N8n is a pow
- 225. **36.38** [w_conc=0.00, perplexity, 24KB] What do people say entj and intj look like and appear outwardly, respectively  S
- 226. **36.37** [w_conc=1.39, perplexity, 11KB] What has accounted for qqq rising to new high in the last 3 months?The primary d
- 227. **36.34** [w_conc=1.61, thread, 9KB] Canadian dollar weakness against the US dollar
- 228. **36.24** [w_conc=4.16, apple-notes, 6KB] apple-notes::June 2026
- 229. **36.21** [w_conc=0.00, thread, 14KB] Portable X-ray scanning for potato trucks
- 230. **36.19** [w_conc=0.00, perplexity, 10KB] Or international Village Mall I want to find out the square foot a dollar per sq
- 231. **36.12** [w_conc=3.14, thread, 14KB] 💬 A system that surfaces all the…
- 232. **36.05** [w_conc=0.00, perplexity, 36KB] what is the weight range for a 22cm black domestic shorthairFor an adult domesti
- 233. **35.97** [w_conc=0.00, perplexity, 10KB] In the recent six month run up of the stock market into heavy tech industries wh
- 234. **35.96** [w_conc=0.00, perplexity, 20KB] https://www.youtube.com/watch?v=bfUOPDOLHvE  explain the pitfalls of private equ
- 235. **35.95** [w_conc=4.16, apple-notes, 6KB] apple-notes::June 2026
- 236. **35.90** [w_conc=2.64, perplexity, 8KB] where is the best coffee produced in the world right now? Where does Kenya rank?
- 237. **35.90** [w_conc=4.16, apple-notes, 6KB] apple-notes::June 2026
- 238. **35.89** [w_conc=0.00, perplexity, 29KB] How much do medical offices like a family doctors office make? What about physio
- 239. **35.83** [w_conc=0.00, thread, 7KB] Innovative distribution methods
- 240. **35.80** [w_conc=0.00, perplexity, 12KB] what is best way to format my system prompt for perplexity if I want information

_(2375 additional low-score candidates omitted; see JSON for full list.)_
