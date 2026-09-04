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

**weighted_concept** — MIKAI-central signal. Sums `log(1+in-degree)` over concept slugs (min length 5, kebab-case) hit in source body. Max concept weight this run: **3.37**. Vocab: 320 slugs.

**weighted_personal** — broader Brian-profile signal (Level 3 addition). Sums per-token weight from a compiled personal vocabulary. Sources: USER_MODEL.md (1.5), PROFILE.md (1.0), BRAIN.md priorities (0.7), entity slugs (0.5), wisdom/goals/habits/reflections (0.5), queries (0.4), journal tags (0.3). Max personal weight this run: **1.50**. Vocab: 1692 tokens. Tokens already in concept vocab are excluded from this component to avoid double-counting.

Goal source: `~/.mikai/brain/GOALS.md` (10 goals).

### Level 4 additions (4 new axes from `docs/INGESTION_LOG.md` 8-discipline scorecard)

- **axis_a_retrieval** (IR, weight +1.0): overlap with tokens in `wiki/queries/*.md` — predicts which candidates will get queried later.
- **axis_b_novelty** (KR, weight +1.0): 2-3-word kebab-phrases in body NOT already in concept vocab — sources that expand vocabulary score higher.
- **axis_c_alias_risk** (Entity Resolution, weight -0.5): near-matches to existing slugs (substring + prefix + Jaro-Winkler > 0.85) — high risk = likely to produce dupes.
- **axis_g_episodic_score** (Cognitive Science, no direct weight): 0.0=episodic, 1.0=semantic, 0.5=ambiguous. Routing signal only — emitted for downstream page-type placement.

## Top 30 candidates

| # | score | l3.1 | w_conc | w_pers | axA | axB | axC | axG | kind | KB | turns | title |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 42.81 | 40.93 | 0.00 | 37.18 | 1.00 | 1.00 | -0.12 | 0.50 | thread | 39 | 18 | Consolidating architectural decisions across project th |
| 2 | 42.74 | 40.98 | 1.39 | 35.73 | 1.00 | 1.00 | -0.23 | 1.00 | thread | 23 | 14 | Unreciprocated effort and emotional withdrawal patterns |
| 3 | 42.64 | 40.88 | 4.61 | 32.17 | 1.00 | 1.00 | -0.23 | 0.00 | perplexity | 98 | — | (Bot) Options Trading StrategiesVolatility arbitrage (v |
| 4 | 42.50 | 40.80 | 0.00 | 37.06 | 1.00 | 1.00 | -0.30 | 0.00 | perplexity | 29 | — | Anthropic open ai, and perplexity valuation,   What are |
| 5 | 42.36 | 40.54 | 1.79 | 34.83 | 1.00 | 1.00 | -0.18 | 0.50 | perplexity | 40 | — | Ha-Joon Chang, Byung-Chul Han Sandwich there was a thre |
| 6 | 41.97 | 40.20 | 0.00 | 36.88 | 1.00 | 1.00 | -0.23 | 0.50 | perplexity | 10 | — | If AGI is for sure coming, explain the landscape or top |
| 7 | 41.89 | 40.16 | 2.83 | 33.29 | 1.00 | 1.00 | -0.27 | 0.50 | perplexity | 55 | — | Entj 7w8 vs 8w7. I want to know which one I amTo determ |
| 8 | 41.53 | 39.95 | 0.00 | 35.36 | 1.00 | 1.00 | -0.41 | 0.50 | thread | 326 | 80 | Building a championship roster around Luka in Vancouver |
| 9 | 41.47 | 39.66 | 3.37 | 33.24 | 1.00 | 0.93 | -0.12 | 0.00 | thread | 13 | 4 | Synthesizing multiple sources with passive collection |
| 10 | 41.41 | 39.68 | 0.00 | 35.16 | 1.00 | 1.00 | -0.27 | 0.50 | thread | 211 | 111 | Identifying an Alocasia plant |
| 11 | 41.39 | 39.66 | 0.00 | 35.38 | 1.00 | 1.00 | -0.27 | 0.50 | perplexity | 97 | — | EC Rare Book market research: What is the value of the  |
| 12 | 41.34 | 39.66 | 0.00 | 35.71 | 1.00 | 1.00 | -0.32 | 0.50 | perplexity | 32 | — | what to enfj's day dream aboutENFJs most often daydream |
| 13 | 41.33 | 39.63 | 0.00 | 35.60 | 1.00 | 1.00 | -0.30 | 0.50 | perplexity | 34 | — | can you analyze vancouver brand aritzia and their expan |
| 14 | 41.06 | 39.41 | 1.61 | 34.76 | 1.00 | 0.83 | -0.18 | 0.50 | thread | 14 | 6 | MIKAi development and memory challenges |
| 15 | 41.03 | 39.05 | 0.00 | 36.29 | 1.00 | 0.98 | -0.00 | 0.50 | thread | 5 | 2 | Personalized reading list recommendations |
| 16 | 40.43 | 38.73 | 3.56 | 31.39 | 1.00 | 1.00 | -0.30 | 0.00 | perplexity | 36 | — | give me updates of nvda appl and tsla today in the news |
| 17 | 40.41 | 38.64 | 0.00 | 34.83 | 1.00 | 1.00 | -0.23 | 0.00 | perplexity | 36 | — | Are there any examples of an all ai news YouTube or Spo |
| 18 | 40.38 | 38.49 | 0.00 | 35.31 | 1.00 | 1.00 | -0.12 | 0.50 | thread | 23 | 4 | Interoperable patient records in Canada |
| 19 | 40.20 | 38.38 | 1.79 | 32.92 | 1.00 | 1.00 | -0.18 | 0.50 | perplexity | 20 | — | vancouver from early 2000s to 2021 faced unprecendented |
| 20 | 40.15 | 38.55 | 0.00 | 34.49 | 1.00 | 0.60 | -0.00 | 0.50 | apple-notes | 24 | — | apple-notes::Feb 2025 - David and the Dao |
| 21 | 39.91 | 38.01 | 4.03 | 31.22 | 1.00 | 0.90 | -0.00 | 0.00 | thread | 10 | 2 | Building credibility for a Google acquisition |
| 22 | 39.83 | 38.10 | 0.00 | 34.52 | 1.00 | 1.00 | -0.27 | 0.50 | perplexity | 21 | — | Can you read the transcript of this video: https://www. |
| 23 | 39.71 | 38.02 | 0.00 | 34.98 | 1.00 | 0.93 | -0.23 | 0.50 | apple-notes | 4 | — | memories |
| 24 | 39.53 | 37.72 | 1.10 | 32.96 | 1.00 | 1.00 | -0.18 | 0.50 | thread | 32 | 21 | Improving project instructions for MIKA TECH (Progressi |
| 25 | 39.48 | 37.66 | 1.39 | 33.46 | 1.00 | 1.00 | -0.18 | 0.50 | thread | 8 | 2 | Modern solutions for the rentiers problem |
| 26 | 39.44 | 37.55 | 0.00 | 33.03 | 1.00 | 1.00 | -0.12 | 0.50 | thread | 109 | 59 | Sphagnum moss vs peat moss for DIY Monstera poles |
| 27 | 39.36 | 37.48 | 2.20 | 32.01 | 1.00 | 1.00 | -0.12 | 0.50 | perplexity | 13 | — | How valuable is OCR data from social media. A lot i ima |
| 28 | 38.98 | 37.17 | 0.00 | 33.34 | 1.00 | 0.93 | -0.12 | 0.50 | perplexity | 45 | — | I want to put on a bear call for tech stocks related to |
| 29 | 38.97 | 36.97 | 0.00 | 33.52 | 1.00 | 1.00 | -0.00 | 0.50 | perplexity | 16 | — | never split the difference, book on negotiation and com |
| 30 | 38.91 | 37.03 | 0.00 | 33.56 | 1.00 | 1.00 | -0.12 | 0.50 | thread | 30 | 13 | Where writers migrate as platforms decay |

### Top concept + personal hits per candidate (top 15)

- **1.** Consolidating architectural decisions across project threads
  - concepts: —
  - personal: `durable` (1.50), `claude` (1.50), `history` (1.50)
- **2.** Unreciprocated effort and emotional withdrawal patterns
  - concepts: `consolidation-as-displacement` (1.39)
  - personal: `claude` (1.50), `people` (1.50), `partner` (1.50)
- **3.** (Bot) Options Trading StrategiesVolatility arbitrage (vol ar
  - concepts: `long-straddle` (1.61), `iron-condor` (1.61), `bull-call-spread` (1.39)
  - personal: `germaine` (1.50), `weekly` (1.50), `decision` (1.50)
- **4.** Anthropic open ai, and perplexity valuation,   What are thei
  - concepts: —
  - personal: `agents` (1.50), `pushed` (1.50), `claude` (1.50)
- **5.** Ha-Joon Chang, Byung-Chul Han Sandwich there was a thread th
  - concepts: `iphone-convergence-thesis` (1.79)
  - personal: `durable` (1.50), `claude` (1.50), `people` (1.50)
- **6.** If AGI is for sure coming, explain the landscape or topograp
  - concepts: —
  - personal: `durable` (1.50), `dependencies` (1.50), `incident` (1.50)
- **7.** Entj 7w8 vs 8w7. I want to know which one I amTo determine w
  - concepts: `wu-wei` (2.83)
  - personal: `germaine` (1.50), `choice` (1.50), `people` (1.50)
- **8.** Building a championship roster around Luka in Vancouver
  - concepts: —
  - personal: `runway` (1.50), `refuses` (1.50), `durable` (1.50)
- **9.** Synthesizing multiple sources with passive collection
  - concepts: `personal-intent-graph` (3.37)
  - personal: `claude` (1.50), `history` (1.50), `deciding` (1.50)
- **10.** Identifying an Alocasia plant
  - concepts: —
  - personal: `defect` (1.50), `deliberately` (1.50), `claude` (1.50)
- **11.** EC Rare Book market research: What is the value of the rare 
  - concepts: —
  - personal: `durable` (1.50), `evaluating` (1.50), `history` (1.50)
- **12.** what to enfj's day dream aboutENFJs most often daydream abou
  - concepts: —
  - personal: `weekly` (1.50), `people` (1.50), `partner` (1.50)
- **13.** can you analyze vancouver brand aritzia and their expansion 
  - concepts: —
  - personal: `runway` (1.50), `end-to-end` (1.50), `weekly` (1.50)
- **14.** MIKAi development and memory challenges
  - concepts: `orchestration-agent` (1.61)
  - personal: `claude` (1.50), `history` (1.50), `people` (1.50)
- **15.** Personalized reading list recommendations
  - concepts: —
  - personal: `evaluating` (1.50), `claude` (1.50), `people` (1.50)

## Recommended next batch (top 15)

- Total volume: **1034KB** across 15 sources
- Est. wall-clock: **~6min** at workers=8, **~50min** at workers=1 (assumes ~200s/source average)
- Would land as R3-2026-08-31-mikai-followup

| # | score | w_conc | w_pers | title | KB | filename |
|---|---|---|---|---|---|---|
| 1 | 42.81 | 0.00 | 37.18 | Consolidating architectural decisions across project threads | 39 | `2026-03-10-consolidating-architectural-decisions-across-project-threads-ea3aba.md` |
| 2 | 42.74 | 1.39 | 35.73 | Unreciprocated effort and emotional withdrawal patterns | 23 | `2026-08-07-unreciprocated-effort-and-emotional-withdrawal-patterns-6ffe64.md` |
| 3 | 42.64 | 4.61 | 32.17 | (Bot) Options Trading StrategiesVolatility arbitrage (vol ar | 98 | `2026-03-19-bot-options-trading-strategiesvolatility-arbitrage-vol-arb-i-40937e.md` |
| 4 | 42.50 | 0.00 | 37.06 | Anthropic open ai, and perplexity valuation,   What are thei | 29 | `2026-03-19-anthropic-open-ai-and-perplexity-valuation-what-are-their-re-5f7671.md` |
| 5 | 42.36 | 1.79 | 34.83 | Ha-Joon Chang, Byung-Chul Han Sandwich there was a thread th | 40 | `2026-03-19-ha-joon-chang-byung-chul-han-sandwich-there-was-a-thread-tha-5b63a0.md` |
| 6 | 41.97 | 0.00 | 36.88 | If AGI is for sure coming, explain the landscape or topograp | 10 | `2026-03-19-if-agi-is-for-sure-coming-explain-the-landscape-or-topograph-c84f94.md` |
| 7 | 41.89 | 2.83 | 33.29 | Entj 7w8 vs 8w7. I want to know which one I amTo determine w | 55 | `2026-03-19-entj-7w8-vs-8w7-i-want-to-know-which-one-i-amto-determine-wh-be7b3f.md` |
| 8 | 41.53 | 0.00 | 35.36 | Building a championship roster around Luka in Vancouver | 326 | `2026-07-07-building-a-championship-roster-around-luka-in-vancouver-d563a3.md` |
| 9 | 41.47 | 3.37 | 33.24 | Synthesizing multiple sources with passive collection | 13 | `2026-02-22-synthesizing-multiple-sources-with-passive-collection-6aba25.md` |
| 10 | 41.41 | 0.00 | 35.16 | Identifying an Alocasia plant | 211 | `2026-06-15-identifying-an-alocasia-plant-df96d3.md` |
| 11 | 41.39 | 0.00 | 35.38 | EC Rare Book market research: What is the value of the rare  | 97 | `2026-03-19-ec-rare-book-market-research-what-is-the-value-of-the-rare-b-17c258.md` |
| 12 | 41.34 | 0.00 | 35.71 | what to enfj's day dream aboutENFJs most often daydream abou | 32 | `2026-03-19-what-to-enfj-s-day-dream-aboutenfjs-most-often-daydream-abou-477cde.md` |
| 13 | 41.33 | 0.00 | 35.60 | can you analyze vancouver brand aritzia and their expansion  | 34 | `2026-03-19-can-you-analyze-vancouver-brand-aritzia-and-their-expansion-3b49b5.md` |
| 14 | 41.06 | 1.61 | 34.76 | MIKAi development and memory challenges | 14 | `2026-02-18-mikai-development-and-memory-challenges-ef2298.md` |
| 15 | 41.03 | 0.00 | 36.29 | Personalized reading list recommendations | 5 | `2026-03-07-personalized-reading-list-recommendations-0eb4d7.md` |

## Appendix — next 200 candidates (rank 31+, brief)

- 31. **38.90** [w_conc=0.00, perplexity, 41KB] I want to fill international village in chinatown with budding entrepreneurs fro
- 32. **38.82** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] what the moat looks like in features — strategic-synthesis-2026-06-14: 2. The de
- 33. **38.82** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] what the moat looks like in features — strategic-insights: 2. The depth thesis —
- 34. **38.75** [w_conc=0.00, thread, 41KB] Anarchist digital spaces beyond Bitcoin
- 35. **38.54** [w_conc=0.00, perplexity, 7KB] Where is the state of Ai agents right now? How powerful are they in producing ac
- 36. **38.25** [w_conc=0.00, thread, 9KB] Manus AI compared to LangGraph and n8n
- 37. **38.00** [w_conc=2.20, thread, 174KB] Wind-resistant plants for apartment living
- 38. **37.54** [w_conc=0.00, thread, 9KB] Identifying productivity theater in daily habits
- 39. **37.46** [w_conc=0.00, perplexity, 23KB] Below is the problem my engineering team is trying to solve. Give me a high leve
- 40. **37.39** [w_conc=0.00, perplexity, 97KB] assessed property value vs fair market value?Assessed property value and fair ma
- 41. **37.33** [w_conc=0.00, perplexity, 99KB] My cats poo is dark brown and it’s almost black, but we’re worried by looking at
- 42. **37.27** [w_conc=0.00, thread, 65KB] Specialty coffee product scaling and market distribution
- 43. **37.07** [w_conc=0.00, thread, 24KB] Digital assistant that adapts to you, not the other way arou
- 44. **37.07** [w_conc=0.00, perplexity, 17KB] Wha are ai agent swarmsAI agent swarms are groups of specialized AI agents that 
- 45. **36.89** [w_conc=0.00, thread, 33KB] Kenya travel recommendations around Nairobi
- 46. **36.74** [w_conc=0.00, perplexity, 10KB] It seems like the concept of AI agents have existed since the 80s. I remember re
- 47. **36.71** [w_conc=0.00, perplexity, 12KB] So how has Peter thiel executed on this philosophy?Peter Thiel has executed this
- 48. **36.45** [w_conc=0.00, perplexity, 16KB] What startups have come out of ihub that are significant? What startups are ther
- 49. **36.43** [w_conc=2.83, perplexity, 16KB] what is the definition of ditzy. can you analyze in it the context of a socionic
- 50. **36.09** [w_conc=0.00, apple-notes, 11KB] apple-notes::June 2026
- 51. **36.09** [w_conc=0.00, apple-notes, 11KB] apple-notes::June 2026
- 52. **36.07** [w_conc=0.00, perplexity, 99KB] In frostpunk 2 what is the best strategy: tech, exploration, etcFor Frostpunk 2 
- 53. **36.02** [w_conc=0.00, thread, 19KB] Scraping social media data for AI training
- 54. **35.96** [w_conc=0.00, perplexity, 6KB] describe the the I's that is shown in this video: https://www.youtube.com/watch?
- 55. **35.71** [w_conc=0.00, perplexity, 14KB] The first business that I want to build out for in international villages mall i
- 56. **35.70** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 57. **35.68** [w_conc=0.00, thread, 10KB] Beyond the LLM hype: what AI has actually delivered
- 58. **35.66** [w_conc=0.00, perplexity, 27KB] a fully transcend entj will act more like a?A fully realized, transcendent ENTJ 
- 59. **35.61** [w_conc=0.00, perplexity, 14KB] Who is the content creator or social media head that is the best at assessing ne
- 60. **35.53** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 7. Paths forward, ranked by historical viability
- 61. **35.53** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 7. Paths forward, ranked by historical viability
- 62. **35.53** [w_conc=0.00, perplexity, 32KB] what do the people of south korea, yantai, qingdao and dalian have in commonPeop
- 63. **35.47** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 64. **35.45** [w_conc=0.00, perplexity, 38KB] can you give me an overview of henderson development in canada as well as their 
- 65. **35.41** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 66. **35.31** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 67. **35.29** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 68. **35.28** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 69. **35.28** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 70. **35.28** [w_conc=0.00, thread, 86KB] Forward head posture root causes
- 71. **35.27** [w_conc=0.00, thread, 30KB] Best iPhone generation to buy: first or stabilized iteration
- 72. **35.26** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 73. **35.26** [w_conc=0.00, perplexity, 29KB] Mark and I close university friends and have also been roommates after college t
- 74. **35.25** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 75. **35.12** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 76. **35.10** [w_conc=0.00, thread, 26KB] Agentic marketplace for used goods
- 77. **35.00** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 78. **34.96** [w_conc=1.39, perplexity, 13KB] There’s an social principle where if the size of a community grows to over 500, 
- 79. **34.93** [w_conc=0.00, perplexity, 40KB] What were the rewards for bitcoin mining from 2012-2016Introverted-intuition tak
- 80. **34.92** [w_conc=1.39, thread, 23KB] Kenya's renewable energy advantages and scalability
- 81. **34.89** [w_conc=0.00, perplexity, 15KB] https://youtu.be/frqiUkjxAOE?si=rlTjy7QvhXn4gS_H  Can yo summarize this videoChr
- 82. **34.88** [w_conc=0.00, perplexity, 65KB] I want to hook up my voice memos so that the automatically get inserted into rea
- 83. **34.79** [w_conc=1.95, perplexity, 10KB] What is the core problem and core solution for international village mall. Expla
- 84. **34.78** [w_conc=0.00, perplexity, 23KB] David defeated the philistines with a stone and momentumDavid defeated Goliath b
- 85. **34.55** [w_conc=2.08, perplexity, 40KB] Our cat that we’ve had for three weeks now who’s peed for the first time when we
- 86. **34.54** [w_conc=0.00, perplexity, 31KB] I want to create a business service that acts as broker for leases, and interior
- 87. **34.46** [w_conc=0.00, thread, 6KB] Anthropic blocks Claude Pro OAuth tokens
- 88. **34.41** [w_conc=0.00, apple-notes, 11KB] apple-notes::June 2026
- 89. **34.34** [w_conc=0.00, thread, 17KB] Andre Iguodala's personality type
- 90. **34.33** [w_conc=0.00, perplexity, 15KB] We know a start of founder that started his original business in 2012 and had fa
- 91. **34.29** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 92. **34.27** [w_conc=0.00, thread, 59KB] Crypto transfer phone scam
- 93. **34.25** [w_conc=0.00, perplexity, 14KB] can you give me a description of the eyes of and estj vs entj vs intjHere is a d
- 94. **34.22** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 95. **34.20** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 96. **34.19** [w_conc=0.00, perplexity, 11KB] Simulation Modelling: personality, business physics ~~ movement of people within
- 97. **34.19** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 98. **34.18** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 99. **34.15** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 100. **34.14** [w_conc=0.00, perplexity, 17KB] Forget a recession. What Canadians are living through is worse. can you explain 
- 101. **34.14** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 102. **34.12** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 103. **34.11** [w_conc=0.00, perplexity, 15KB] i like Ha-Joon Chang, are there any other like him, who would be the best from p
- 104. **34.09** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 105. **34.06** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 106. **34.03** [w_conc=1.61, perplexity, 27KB] I want to create a webapp tool that: allows you to search youtube explore page a
- 107. **34.01** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 108. **33.91** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 109. **33.85** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] the OS-absorbs-the-assistant stress test — strategic-insights: 1. Threat landsca
- 110. **33.82** [w_conc=2.08, perplexity, 12KB] Cna you do an analysis of the coffee commodities market? What account for the pr
- 111. **33.80** [w_conc=2.83, perplexity, 9KB] what is the taoist principle of acting and not tryingThe Taoist principle of act
- 112. **33.74** [w_conc=0.00, perplexity, 13KB] what is a split-screen cycle in economicsA split-screen cycle in economics refer
- 113. **33.71** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 114. **33.68** [w_conc=0.00, perplexity, 18KB] the apartments by international village mall and roger's arena, is that area cal
- 115. **33.62** [w_conc=0.00, perplexity, 4KB] How did ai fix the roaming the internet and performing actions problem, list the
- 116. **33.62** [w_conc=0.00, perplexity, 8KB] I want to create business model and plan to present for federal and provincial g
- 117. **33.61** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 118. **33.59** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 119. **33.57** [w_conc=0.00, thread, 12KB] Steve Jobs' prioritization meeting story
- 120. **33.55** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 121. **33.54** [w_conc=0.00, perplexity, 15KB] Tell me about the tax-free zone in Songdo, Incheon, Korea. What counts as R&D? S
- 122. **33.50** [w_conc=0.00, thread, 43KB] INTJ's ideal personality match
- 123. **33.49** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 124. **33.49** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 125. **33.45** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 126. **33.40** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 127. **33.38** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 128. **33.33** [w_conc=0.00, perplexity, 85KB] what is the first home buyers account in canadaThe First Home Savings Account (F
- 129. **33.33** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 130. **33.22** [w_conc=0.00, perplexity, 33KB] Using first principles I want to find out why housing costs are so expensive. We
- 131. **33.18** [w_conc=0.00, perplexity, 7KB] What are the key things that create good managers vs good creatorsThe most criti
- 132. **33.15** [w_conc=0.00, thread, 25KB] Private equity investment targets
- 133. **33.15** [w_conc=0.00, perplexity, 12KB] Activist investor invests 2b into workdayAn activist investor, Elliott Investmen
- 134. **33.10** [w_conc=0.00, perplexity, 58KB] I sit a lot during the day, I vape, and game on the computer a couple hours a da
- 135. **33.03** [w_conc=0.00, perplexity, 35KB] i'm being interview for a job as a starting engineer at a ai tech startup in can
- 136. **33.01** [w_conc=0.00, perplexity, 8KB] Dr Arthur Brooks  https://youtu.be/5mpyFuyIQ14?si=OGjygtIocomSlz7q  What persona
- 137. **32.98** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 138. **32.95** [w_conc=0.00, thread, 13KB] Continuing markdown conversations on Perplexity
- 139. **32.92** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 9. Why no consumer Glean exists
- 140. **32.92** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 9. Why no consumer Glean exists
- 141. **32.90** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026
- 142. **32.88** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 143. **32.84** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 144. **32.83** [w_conc=0.00, perplexity, 19KB] In the Vancouver market, retail and f&b are struggling because of their low marg
- 145. **32.75** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 146. **32.74** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 147. **32.70** [w_conc=0.00, perplexity, 9KB] It seems like to an entj, while an esfp is an activity partner, they can often t
- 148. **32.60** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 149. **32.59** [w_conc=0.00, perplexity, 19KB] What happening in the market today particularly in the tech sector, and you look
- 150. **32.57** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 151. **32.57** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 152. **32.52** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 153. **32.48** [w_conc=0.00, perplexity, 7KB] I love playing catan, eu4, civilization, poker. What are the the skills in those
- 154. **32.43** [w_conc=0.00, thread, 9KB] WiFi-based motion tracking for physio apps
- 155. **32.38** [w_conc=0.00, perplexity, 22KB] I had a dream catcher when I was young , do cats act as a dream catcher?Cats are
- 156. **32.31** [w_conc=1.95, thread, 6KB] Mapping economic chokepoints for strategic advantage
- 157. **32.30** [w_conc=0.00, perplexity, 47KB] what are the highest rated cat vets in vancouverI can’t reliably rank “highest r
- 158. **32.30** [w_conc=0.00, perplexity, 31KB] Chochu trading co.  Beyond goods: how to circumvent tariffs If we import Chinese
- 159. **32.26** [w_conc=0.00, perplexity, 24KB] Toyota hybrid suv that is the highest ratedThe highest-rated Toyota hybrid SUV r
- 160. **32.21** [w_conc=0.00, perplexity, 7KB] Can you ask my mentors what they think of this? Is this true or can you focus on
- 161. **32.14** [w_conc=0.00, perplexity, 13KB] wealth management firm and industry overviewIntroverted Intuition – Key Insight 
- 162. **32.07** [w_conc=0.00, perplexity, 27KB] are there any other companies like scale ai but at lower valuations? can you giv
- 163. **32.04** [w_conc=0.00, perplexity, 6KB] https://www.youtube.com/watch?v=ssYt09bCgUY  summarize this videoThe video intro
- 164. **32.03** [w_conc=0.00, perplexity, 8KB] as an entj, my ti has always been weak in school, so understand a chain of relat
- 165. **31.99** [w_conc=0.00, perplexity, 12KB] International village in downtown Vancouver has huge vacancy right now, and they
- 166. **31.94** [w_conc=0.00, perplexity, 27KB] tell me many variants of loss leader strategy across many industries. Bridge the
- 167. **31.85** [w_conc=0.00, perplexity, 16KB] is weride a chinese company? What are the prices for their robo sweepers and sim
- 168. **31.83** [w_conc=1.61, apple-notes, 2KB] MIKAI Feature: Ai directed content
- 169. **31.83** [w_conc=0.00, perplexity, 8KB] Difference between psychology and psychiatry and other disciplines within that f
- 170. **31.80** [w_conc=0.00, thread, 9KB] Derek's systems thinking and applications to AI and geopolit
- 171. **31.78** [w_conc=0.00, thread, 12KB] Finding the weak link in AI's circular economy
- 172. **31.77** [w_conc=0.00, perplexity, 22KB] Fed chair update and what it means for the market, why did trump want Jerome Pow
- 173. **31.77** [w_conc=0.00, perplexity, 20KB] In sports, and with my friends, I seem to alway be encouraging, and give thought
- 174. **31.73** [w_conc=2.08, perplexity, 24KB] Is there such thing as our cats not wanting to come into me and my partner‘s roo
- 175. **31.71** [w_conc=1.39, apple-notes, 4KB] Modern solutions for the rentiers problem
- 176. **31.64** [w_conc=4.03, apple-notes, 4KB] Building credibility for a Google acquisition
- 177. **31.58** [w_conc=0.00, perplexity, 20KB] From everything we have discussed in this space called International Village, gi
- 178. **31.55** [w_conc=0.00, perplexity, 25KB] Best cafes in Nairobi that tech workers work at. I usually go to coffee shops li
- 179. **31.49** [w_conc=0.00, perplexity, 5KB] If AGI is for sure coming, explain the landscape or topography of AGI as an anal
- 180. **31.47** [w_conc=0.00, perplexity, 29KB] can you do a case study on instant financial https://www.instant.co/ and how the
- 181. **31.46** [w_conc=1.39, perplexity, 11KB] What has accounted for qqq rising to new high in the last 3 months?The primary d
- 182. **31.40** [w_conc=0.00, perplexity, 24KB] I was caught smoking outside the Nairobi airport and a police officer want to ta
- 183. **31.40** [w_conc=1.95, perplexity, 3KB] “Based on everything you know about me from our full chat history and memory, gi
- 184. **31.40** [w_conc=0.00, thread, 17KB] Electrician career paths in BC for low-voltage experience
- 185. **31.38** [w_conc=0.00, perplexity, 9KB] I looking for a Vancouver economic group that believes in Georgiam or Joseph sti
- 186. **31.35** [w_conc=0.00, perplexity, 34KB] Can I self inject this?Self-injecting GHK-Cu (Copper Peptide) purchased online i
- 187. **31.28** [w_conc=0.00, perplexity, 5KB] what is the status of ai agents right now? What actions can they perform? What a
- 188. **31.20** [w_conc=0.00, perplexity, 18KB] For tech jobs, typically the big 5 was considered optimal. I want the next up an
- 189. **31.14** [w_conc=0.00, perplexity, 9KB] What happened to activist investing? Is there an investing principle or an organ
- 190. **31.13** [w_conc=0.00, perplexity, 7KB] Below are my notes for International Villages project I've been working on this 
- 191. **31.11** [w_conc=0.00, perplexity, 36KB] what is the weight range for a 22cm black domestic shorthairFor an adult domesti
- 192. **31.06** [w_conc=0.00, perplexity, 17KB] how did bob rennie start his firm, what was the startBob Rennie started his firm
- 193. **31.03** [w_conc=0.00, perplexity, 10KB] Restaurants in Vancouver are dying right now because people don’t have enough di
- 194. **30.95** [w_conc=0.00, perplexity, 11KB] how to get rid of fear, or to act in fear, I'm scared of sudden movements and sc
- 195. **30.83** [w_conc=2.83, perplexity, 12KB] People want to feel like they are the smartest person, or the most ethical, or t
- 196. **30.82** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] what to copy from enterprise, what to skip — strategic-synthesis-2026-06-14: 10.
- 197. **30.82** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] what to copy from enterprise, what to skip — strategic-insights: 10. MIKAI archi
- 198. **30.72** [w_conc=0.00, perplexity, 20KB] When the market swings down dramatically like today, where does that capital go?
- 199. **30.64** [w_conc=0.00, perplexity, 27KB] I want to inquire into this commcerical property: https://www.realtor.ca/real-es
- 200. **30.63** [w_conc=0.00, perplexity, 25KB] Give me the gdp per capita (ppp and nominal) of these countries: Kenya Mexico, V
- 201. **30.62** [w_conc=0.00, apple-notes, 4KB] Mika architecture ideas
- 202. **30.58** [w_conc=1.61, perplexity, 17KB] how much does a used container cost so I can grow mushrooms in them, what is the
- 203. **30.57** [w_conc=2.08, apple-notes, 5KB] #toknowthyself
- 204. **30.57** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026
- 205. **30.55** [w_conc=0.00, perplexity, 23KB] It’s not creditors, I have my business listed as a sole proprietorship and I owe
- 206. **30.47** [w_conc=0.00, perplexity, 10KB] what are creative ways that ai agent can chagne the coffee industryAI agents are
- 207. **30.47** [w_conc=0.00, perplexity, 24KB] What do people say entj and intj look like and appear outwardly, respectively  S
- 208. **30.34** [w_conc=0.00, perplexity, 5KB] https://www.perplexity.ai/page/canada-to-reinvent-economy-ami-xls3GS9CRuidp6jHBt
- 209. **30.28** [w_conc=0.00, perplexity, 3KB] what other agents operate like openclawSeveral other agents follow a similar “au
- 210. **30.27** [w_conc=0.00, thread, 39KB] Rent vs. buy analysis for Vancouver
- 211. **30.20** [w_conc=0.00, perplexity, 10KB] Singapore developed by creating an economy, focussed on foreign electronics ship
- 212. **30.19** [w_conc=0.00, thread, 4KB] Project problem framing analysis
- 213. **30.17** [w_conc=0.00, perplexity, 45KB] For an entj, describe relationships with esfp vs enfpAs an ENTJ, your relationsh
- 214. **30.17** [w_conc=0.00, thread, 4KB] Finding your ideal sports coaching philosophy
- 215. **30.17** [w_conc=0.00, thread, 3KB] OpenClaw vs Claude Code capabilities
- 216. **30.05** [w_conc=0.00, perplexity, 8KB] what is the most powerful reasoning model out there right nowIntroverted Intuiti
- 217. **30.03** [w_conc=1.61, apple-notes, 4KB] Making AI invisible through personalized knowledge architecture
- 218. **30.02** [w_conc=0.00, perplexity, 6KB] they say that in one year of dedicated work, you can be better than 95% of your 
- 219. **29.92** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 3. The product
- 220. **29.92** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 3. The product
- 221. **29.85** [w_conc=0.00, thread, 19KB] Low voltage electrical companies in BC for Patrick
- 222. **29.84** [w_conc=0.00, perplexity, 11KB] I feel confused and disheartened because I’m Fighting with Germaine about commun
- 223. **29.82** [w_conc=0.00, perplexity, 6KB] can you detail benjamin franklin's journaling style and his reasoning for itBenj
- 224. **29.73** [w_conc=0.00, perplexity, 31KB] i want to fill international village mall in chinatown, I'm considering many opt
- 225. **29.70** [w_conc=2.83, perplexity, 39KB] I want to understand modern and cutting edge relationships between the autonomic
- 226. **29.66** [w_conc=1.61, claude, 4KB] claude: Making AI invisible through personalized knowledge architect
- 227. **29.66** [w_conc=0.00, perplexity, 11KB] If you were to ask all the tech ceos incubators on how to build an mvp in this a
- 228. **29.64** [w_conc=0.00, thread, 6KB] Nairobi's infrastructure gaps and AI-enhanced tools
- 229. **29.59** [w_conc=0.00, thread, 13KB] AI compute investment versus emerging efficient alternatives
- 230. **29.52** [w_conc=0.00, perplexity, 15KB] Can you break down why on average 400 K to build a condo unit in Canada?Short an

_(2402 additional low-score candidates omitted; see JSON for full list.)_
