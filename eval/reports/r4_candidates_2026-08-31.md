# R4 Candidate Salience — Level 3.1 (aggregation-aware, no-blacklist) — 2026-08-31

Ranked candidates for the next ingestion round, scored via **weighted concept intersection** (Session-10 spec in `fuzzy-shimmying-wreath.md`).

**Disposable one-shot scorer.** Purpose: schedule which un-ingested wiki-raw sources get the next paid `claude -p` call. Not a peer of the post-ingest salience system (`wiki-salience.md` / `dream_bootstrap.py`); no eval, no versioning. Judged only by downstream post-ingest recall@10 lift. Retire when the wiki-raw backlog drains.

## Universe & filtering

- Total wiki-raw sections: **15747**
- Filtered out — `claude-code` per-turn fragments: **10435**
- Filtered out — malformed `claude-thread` orphans (name missing `::title::idx::role`): **663**
- Unique claude threads (well-formed): **139**
- Other sections (apple-notes, perplexity, ...): **2608**
- Already ingested into parallel vault: **76** files
- Skipped as already-ingested during scoring: **76**
- Skipped as empty body: **0**
- **Candidates evaluated: 2671**

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

**weighted_concept** — MIKAI-central signal. Sums `log(1+in-degree)` over concept slugs (min length 5, kebab-case) hit in source body. Max concept weight this run: **3.37**. Vocab: 313 slugs.

**weighted_personal** — broader Brian-profile signal (Level 3 addition). Sums per-token weight from a compiled personal vocabulary. Sources: USER_MODEL.md (1.5), PROFILE.md (1.0), BRAIN.md priorities (0.7), entity slugs (0.5), wisdom/goals/habits/reflections (0.5), queries (0.4), journal tags (0.3). Max personal weight this run: **1.50**. Vocab: 1680 tokens. Tokens already in concept vocab are excluded from this component to avoid double-counting.

Goal source: `~/.mikai/brain/GOALS.md` (10 goals).

## Top 30 candidates

| # | score | w_conc | w_pers | goal | rec | subst | agg | kind | KB | turns | title |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 59.88 | 5.31 | 49.89 | 0.55 | 0.53 | 1.00 | 1.50 | thread | 293 | 204 | Build Discussion: Semantic search across LLM conversation hi |
| 2 | 56.39 | 8.44 | 43.93 | 0.37 | 0.53 | 0.88 | 1.50 | thread | 37 | 19 | Synthesizing yearly insights and personal patterns |
| 3 | 54.57 | 1.61 | 48.31 | 0.56 | 0.52 | 0.97 | 1.50 | thread | 136 | 26 | Developer opportunities in emerging markets |
| 4 | 49.96 | 4.98 | 41.86 | 0.23 | 0.52 | 0.41 | 1.50 | thread | 17 | 3 | Building moats beyond model improvement |
| 5 | 49.46 | 0.00 | 45.90 | 0.29 | 0.54 | 0.65 | 1.50 | thread | 36 | 8 | Voice notes memory system architecture |
| 6 | 48.35 | 1.61 | 42.80 | 0.31 | 0.55 | 0.96 | 1.50 | perplexity | 40 | — | I want to understand what kind of economist I am. I'm lookin |
| 7 | 47.62 | 3.22 | 40.01 | 0.45 | 0.55 | 1.00 | 1.50 | perplexity | 68 | — | what is the profitability of 3d ocean farmingBased on the pr |
| 8 | 46.31 | 1.61 | 40.84 | 0.32 | 0.55 | 0.87 | 1.50 | perplexity | 28 | — | Rewriting the Rules of the American Economy“Rewriting the Ru |
| 9 | 46.24 | 5.26 | 37.04 | 0.35 | 0.55 | 0.83 | 1.50 | thread | 72 | 16 | Why INTJs envy ESTP spontaneity |
| 10 | 45.30 | 1.61 | 39.90 | 0.28 | 0.55 | 0.90 | 1.50 | perplexity | 32 | — | I want to be with people that are slightly critical about th |
| 11 | 45.10 | 1.61 | 39.96 | 0.28 | 0.48 | 0.71 | 1.50 | thread | 37 | 10 | Making AI invisible through personalized knowledge architect |
| 12 | 45.06 | 3.37 | 38.17 | 0.32 | 0.47 | 0.61 | 1.50 | thread | 41 | 7 | Prediction markets and forecasting accuracy |
| 13 | 44.72 | 3.37 | 38.01 | 0.27 | 0.51 | 0.53 | 1.50 | thread | 16 | 5 | AI tools becoming obsolete to newer models |
| 14 | 43.79 | 1.61 | 38.65 | 0.22 | 0.55 | 0.82 | 1.50 | perplexity | 22 | — | I keep asking this structural and economic question in my th |
| 15 | 43.49 | 0.00 | 39.36 | 0.36 | 0.55 | 0.98 | 1.50 | perplexity | 44 | — | How do people use Ni in their first function, and what about |
| 16 | 43.45 | 1.61 | 38.22 | 0.28 | 0.47 | 0.83 | 1.50 | thread | 60 | 16 | Importing Perplexity threads into Claude projects |
| 17 | 42.96 | 1.61 | 37.80 | 0.23 | 0.55 | 0.80 | 1.50 | perplexity | 21 | — | Can you explain all the companies in the supply chain ecosys |
| 18 | 42.79 | 4.98 | 34.85 | 0.15 | 0.55 | 0.46 | 1.50 | apple-notes | 4 | — | Building moats beyond model improvement |
| 19 | 42.76 | 0.00 | 38.75 | 0.34 | 0.55 | 0.96 | 1.50 | perplexity | 40 | — | semis vs software portfolio strategy, why is there software  |
| 20 | 42.37 | 0.00 | 38.48 | 0.33 | 0.55 | 0.87 | 1.50 | perplexity | 27 | — | What does the bible say about the ideal wifeThe Bible’s visi |
| 21 | 42.34 | 0.00 | 38.84 | 0.25 | 0.50 | 0.75 | 1.50 | thread | 27 | 12 | Vertical integration opportunities in personal AI agents |
| 22 | 42.31 | 1.61 | 37.19 | 0.24 | 0.55 | 0.73 | 1.50 | perplexity | 16 | — | Describe the lessons and insights that Huozhi Zhuan wrote ab |
| 23 | 42.01 | 0.00 | 38.38 | 0.23 | 0.53 | 0.90 | 1.50 | thread | 22 | 20 | The Hard Truth about 2nd Brain: Rewind AI's & Consumer Adapt |
| 24 | 41.82 | 0.00 | 37.53 | 0.41 | 0.55 | 1.00 | 1.50 | perplexity | 67 | — | Kenya Tourism questions is it cheap to get scube certified i |
| 25 | 41.60 | 1.61 | 36.57 | 0.21 | 0.55 | 0.73 | 1.50 | perplexity | 15 | — | explain derek Cabrera dsrp method in a way that I can unders |
| 26 | 41.51 | 0.00 | 37.49 | 0.34 | 0.55 | 0.97 | 1.50 | perplexity | 42 | — | Pull up Alex Karp’s phd thesis and explain the concepts arou |
| 27 | 41.42 | 0.00 | 38.29 | 0.23 | 0.46 | 0.47 | 1.50 | thread | 17 | 4 | N8n and OpenClaw capabilities comparison |
| 28 | 41.18 | 3.37 | 34.79 | 0.17 | 0.55 | 0.46 | 1.50 | apple-notes | 4 | — | projects |
| 29 | 41.08 | 1.61 | 35.55 | 0.33 | 0.55 | 0.90 | 1.50 | perplexity | 32 | — | i want a comprehensive understanding of why countries want o |
| 30 | 41.01 | 0.00 | 37.01 | 0.34 | 0.55 | 0.92 | 1.50 | perplexity | 35 | — | I don’t understand the difference between a brand and busine |

### Top concept + personal hits per candidate (top 15)

- **1.** Build Discussion: Semantic search across LLM conversation hi
  - concepts: `personal-intent-graph` (3.37), `capital-velocity` (1.95)
  - personal: `closing` (1.50), `manual` (1.50), `merged` (1.50)
- **2.** Synthesizing yearly insights and personal patterns
  - concepts: `productive-dopamine` (2.48), `permission-wound` (2.08), `consolidation-as-displacement` (1.39)
  - personal: `closing` (1.50), `manual` (1.50), `choice` (1.50)
- **3.** Developer opportunities in emerging markets
  - concepts: `value-added-processing` (1.61)
  - personal: `closing` (1.50), `manual` (1.50), `choice` (1.50)
- **4.** Building moats beyond model improvement
  - concepts: `personal-intent-graph` (3.37), `iphone-convergence-thesis` (1.61)
  - personal: `manual` (1.50), `direct` (1.50), `claude` (1.50)
- **5.** Voice notes memory system architecture
  - concepts: —
  - personal: `manual` (1.50), `choice` (1.50), `direct` (1.50)
- **6.** I want to understand what kind of economist I am. I'm lookin
  - concepts: `iphone-convergence-thesis` (1.61)
  - personal: `choice` (1.50), `deliberately` (1.50), `claude` (1.50)
- **7.** what is the profitability of 3d ocean farmingBased on the pr
  - concepts: `value-added-processing` (1.61), `iphone-convergence-thesis` (1.61)
  - personal: `merged` (1.50), `deliberately` (1.50), `direct` (1.50)
- **8.** Rewriting the Rules of the American Economy“Rewriting the Ru
  - concepts: `iphone-convergence-thesis` (1.61)
  - personal: `claude` (1.50), `highest` (1.50), `threads` (1.50)
- **9.** Why INTJs envy ESTP spontaneity
  - concepts: `te-se-loop` (2.08), `permission-wound` (2.08), `ni-fi-loop` (1.10)
  - personal: `direct` (1.50), `claude` (1.50), `highest` (1.50)
- **10.** I want to be with people that are slightly critical about th
  - concepts: `iphone-convergence-thesis` (1.61)
  - personal: `choice` (1.50), `direct` (1.50), `claude` (1.50)
- **11.** Making AI invisible through personalized knowledge architect
  - concepts: `orchestration-agent` (1.61)
  - personal: `manual` (1.50), `choice` (1.50), `direct` (1.50)
- **12.** Prediction markets and forecasting accuracy
  - concepts: `personal-intent-graph` (3.37)
  - personal: `closing` (1.50), `merged` (1.50), `choice` (1.50)
- **13.** AI tools becoming obsolete to newer models
  - concepts: `personal-intent-graph` (3.37)
  - personal: `closing` (1.50), `direct` (1.50), `claude` (1.50)
- **14.** I keep asking this structural and economic question in my th
  - concepts: `iphone-convergence-thesis` (1.61)
  - personal: `deliberately` (1.50), `claude` (1.50), `reframed` (1.50)
- **15.** How do people use Ni in their first function, and what about
  - concepts: —
  - personal: `compression` (1.50), `pushed` (1.50), `threads` (1.50)

## Recommended next batch (top 15)

- Total volume: **924KB** across 15 sources
- Est. wall-clock: **~6min** at workers=8, **~50min** at workers=1 (assumes ~200s/source average)
- Would land as R3-2026-08-31-mikai-followup

| # | score | w_conc | w_pers | title | KB | filename |
|---|---|---|---|---|---|---|
| 1 | 59.88 | 5.31 | 49.89 | Build Discussion: Semantic search across LLM conversation hi | 293 | `2026-03-05-build-discussion-semantic-search-across-llm-conversation-hi-76f0ce.md` |
| 2 | 56.39 | 8.44 | 43.93 | Synthesizing yearly insights and personal patterns | 37 | `2026-03-05-synthesizing-yearly-insights-and-personal-patterns-70149f.md` |
| 3 | 54.57 | 1.61 | 48.31 | Developer opportunities in emerging markets | 136 | `2026-02-19-developer-opportunities-in-emerging-markets-80e3ec.md` |
| 4 | 49.96 | 4.98 | 41.86 | Building moats beyond model improvement | 17 | `2026-03-07-building-moats-beyond-model-improvement-a581c8.md` |
| 5 | 49.46 | 0.00 | 45.90 | Voice notes memory system architecture | 36 | `2026-03-15-voice-notes-memory-system-architecture-ad484e.md` |
| 6 | 48.35 | 1.61 | 42.80 | I want to understand what kind of economist I am. I'm lookin | 40 | `2026-03-19-i-want-to-understand-what-kind-of-economist-i-am-i-m-looking-3611b3.md` |
| 7 | 47.62 | 3.22 | 40.01 | what is the profitability of 3d ocean farmingBased on the pr | 68 | `2026-03-19-what-is-the-profitability-of-3d-ocean-farmingbased-on-the-pr-27cb86.md` |
| 8 | 46.31 | 1.61 | 40.84 | Rewriting the Rules of the American Economy“Rewriting the Ru | 28 | `2026-03-19-rewriting-the-rules-of-the-american-economy-rewriting-the-ru-6ed1a4.md` |
| 9 | 46.24 | 5.26 | 37.04 | Why INTJs envy ESTP spontaneity | 72 | `2026-03-18-why-intjs-envy-estp-spontaneity-9fcb4a.md` |
| 10 | 45.30 | 1.61 | 39.90 | I want to be with people that are slightly critical about th | 32 | `2026-03-19-i-want-to-be-with-people-that-are-slightly-critical-about-th-958bb8.md` |
| 11 | 45.10 | 1.61 | 39.96 | Making AI invisible through personalized knowledge architect | 37 | `2026-02-18-making-ai-invisible-through-personalized-knowledge-architect-835d8a.md` |
| 12 | 45.06 | 3.37 | 38.17 | Prediction markets and forecasting accuracy | 41 | `2026-02-18-prediction-markets-and-forecasting-accuracy-8fef69.md` |
| 13 | 44.72 | 3.37 | 38.01 | AI tools becoming obsolete to newer models | 16 | `2026-03-07-ai-tools-becoming-obsolete-to-newer-models-3c5a55.md` |
| 14 | 43.79 | 1.61 | 38.65 | I keep asking this structural and economic question in my th | 22 | `2026-03-19-i-keep-asking-this-structural-and-economic-question-in-my-th-a8c8e3.md` |
| 15 | 43.49 | 0.00 | 39.36 | How do people use Ni in their first function, and what about | 44 | `2026-03-19-how-do-people-use-ni-in-their-first-function-and-what-about-b4d535.md` |

## Appendix — next 200 candidates (rank 31+, brief)

- 31. **40.98** [w_conc=1.39, thread, 23KB] Unreciprocated effort and emotional withdrawal patterns
- 32. **40.93** [w_conc=0.00, thread, 39KB] Consolidating architectural decisions across project threads
- 33. **40.80** [w_conc=0.00, perplexity, 29KB] Anthropic open ai, and perplexity valuation,   What are their revenues?Here are 
- 34. **40.79** [w_conc=4.61, perplexity, 98KB] (Bot) Options Trading StrategiesVolatility arbitrage (vol arb) is a trading stra
- 35. **40.36** [w_conc=1.61, perplexity, 40KB] Ha-Joon Chang, Byung-Chul Han Sandwich there was a thread that talked about how 
- 36. **40.20** [w_conc=0.00, perplexity, 10KB] If AGI is for sure coming, explain the landscape or topography of AGI as an anal
- 37. **40.16** [w_conc=2.83, perplexity, 55KB] Entj 7w8 vs 8w7. I want to know which one I amTo determine whether you are an EN
- 38. **39.71** [w_conc=0.00, thread, 326KB] Building a championship roster around Luka in Vancouver
- 39. **39.66** [w_conc=0.00, perplexity, 97KB] EC Rare Book market research: What is the value of the rare books market compare
- 40. **39.58** [w_conc=0.00, thread, 211KB] Identifying an Alocasia plant
- 41. **39.53** [w_conc=0.00, perplexity, 32KB] what to enfj's day dream aboutENFJs most often daydream about guiding or support
- 42. **39.52** [w_conc=0.00, perplexity, 34KB] can you analyze vancouver brand aritzia and their expansion over the last few ye
- 43. **39.52** [w_conc=3.37, thread, 13KB] Synthesizing multiple sources with passive collection
- 44. **39.41** [w_conc=1.61, thread, 14KB] MIKAi development and memory challenges
- 45. **39.05** [w_conc=0.00, thread, 5KB] Personalized reading list recommendations
- 46. **38.64** [w_conc=0.00, perplexity, 36KB] Are there any examples of an all ai news YouTube or Spotify podcast?Yes, there a
- 47. **38.62** [w_conc=3.56, perplexity, 36KB] give me updates of nvda appl and tsla today in the newsHere's a concise summary 
- 48. **38.55** [w_conc=0.00, apple-notes, 24KB] apple-notes::Feb 2025 - David and the Dao
- 49. **38.34** [w_conc=0.00, thread, 23KB] Interoperable patient records in Canada
- 50. **38.20** [w_conc=1.61, perplexity, 20KB] vancouver from early 2000s to 2021 faced unprecendented growth in their housing 
- 51. **38.10** [w_conc=0.00, perplexity, 21KB] Can you read the transcript of this video: https://www.youtube.com/watch?v=_mwm6
- 52. **38.02** [w_conc=0.00, apple-notes, 4KB] memories
- 53. **38.01** [w_conc=4.03, thread, 10KB] Building credibility for a Google acquisition
- 54. **37.72** [w_conc=1.10, thread, 32KB] Improving project instructions for MIKA TECH (Progressive St
- 55. **37.66** [w_conc=1.39, thread, 8KB] Modern solutions for the rentiers problem
- 56. **37.55** [w_conc=0.00, thread, 109KB] Sphagnum moss vs peat moss for DIY Monstera poles
- 57. **37.33** [w_conc=2.20, perplexity, 13KB] How valuable is OCR data from social media. A lot i imagineYour instinct is righ
- 58. **37.17** [w_conc=0.00, perplexity, 45KB] I want to put on a bear call for tech stocks related to ai and ai compute, and I
- 59. **37.01** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] what the moat looks like in features — strategic-synthesis-2026-06-14: 2. The de
- 60. **37.01** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] what the moat looks like in features — strategic-insights: 2. The depth thesis —
- 61. **36.97** [w_conc=0.00, perplexity, 16KB] never split the difference, book on negotiation and communication“Never Split th
- 62. **36.91** [w_conc=0.00, thread, 30KB] Where writers migrate as platforms decay
- 63. **36.88** [w_conc=0.00, perplexity, 41KB] I want to fill international village in chinatown with budding entrepreneurs fro
- 64. **36.88** [w_conc=0.00, thread, 41KB] Anarchist digital spaces beyond Bitcoin
- 65. **36.54** [w_conc=0.00, perplexity, 7KB] Where is the state of Ai agents right now? How powerful are they in producing ac
- 66. **36.31** [w_conc=0.00, thread, 9KB] Manus AI compared to LangGraph and n8n
- 67. **36.12** [w_conc=2.20, thread, 174KB] Wind-resistant plants for apartment living
- 68. **35.87** [w_conc=0.00, thread, 9KB] Identifying productivity theater in daily habits
- 69. **35.65** [w_conc=0.00, perplexity, 23KB] Below is the problem my engineering team is trying to solve. Give me a high leve
- 70. **35.52** [w_conc=0.00, perplexity, 99KB] My cats poo is dark brown and it’s almost black, but we’re worried by looking at
- 71. **35.50** [w_conc=0.00, perplexity, 97KB] assessed property value vs fair market value?Assessed property value and fair ma
- 72. **35.45** [w_conc=0.00, thread, 65KB] Specialty coffee product scaling and market distribution
- 73. **35.34** [w_conc=0.00, perplexity, 17KB] Wha are ai agent swarmsAI agent swarms are groups of specialized AI agents that 
- 74. **35.22** [w_conc=0.00, thread, 24KB] Digital assistant that adapts to you, not the other way arou
- 75. **34.89** [w_conc=0.00, thread, 33KB] Kenya travel recommendations around Nairobi
- 76. **34.86** [w_conc=0.00, perplexity, 10KB] It seems like the concept of AI agents have existed since the 80s. I remember re
- 77. **34.82** [w_conc=0.00, perplexity, 12KB] So how has Peter thiel executed on this philosophy?Peter Thiel has executed this
- 78. **34.61** [w_conc=2.83, perplexity, 16KB] what is the definition of ditzy. can you analyze in it the context of a socionic
- 79. **34.57** [w_conc=0.00, perplexity, 16KB] What startups have come out of ihub that are significant? What startups are ther
- 80. **34.55** [w_conc=0.00, apple-notes, 11KB] apple-notes::June 2026
- 81. **34.55** [w_conc=0.00, apple-notes, 11KB] apple-notes::June 2026
- 82. **34.53** [w_conc=0.00, perplexity, 99KB] In frostpunk 2 what is the best strategy: tech, exploration, etcFor Frostpunk 2 
- 83. **34.31** [w_conc=0.00, perplexity, 6KB] describe the the I's that is shown in this video: https://www.youtube.com/watch?
- 84. **34.16** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 85. **34.01** [w_conc=0.00, thread, 19KB] Scraping social media data for AI training
- 86. **33.99** [w_conc=0.00, perplexity, 27KB] a fully transcend entj will act more like a?A fully realized, transcendent ENTJ 
- 87. **33.93** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 88. **33.87** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 7. Paths forward, ranked by historical viability
- 89. **33.87** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 7. Paths forward, ranked by historical viability
- 90. **33.87** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 91. **33.79** [w_conc=0.00, thread, 10KB] Beyond the LLM hype: what AI has actually delivered
- 92. **33.78** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 93. **33.75** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 94. **33.75** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 95. **33.74** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 96. **33.73** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 97. **33.72** [w_conc=0.00, perplexity, 14KB] The first business that I want to build out for in international villages mall i
- 98. **33.71** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 99. **33.63** [w_conc=0.00, perplexity, 38KB] can you give me an overview of henderson development in canada as well as their 
- 100. **33.61** [w_conc=0.00, perplexity, 29KB] Mark and I close university friends and have also been roommates after college t
- 101. **33.61** [w_conc=0.00, perplexity, 14KB] Who is the content creator or social media head that is the best at assessing ne
- 102. **33.58** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 103. **33.53** [w_conc=0.00, perplexity, 32KB] what do the people of south korea, yantai, qingdao and dalian have in commonPeop
- 104. **33.47** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 105. **33.45** [w_conc=0.00, thread, 30KB] Best iPhone generation to buy: first or stabilized iteration
- 106. **33.35** [w_conc=0.00, thread, 86KB] Forward head posture root causes
- 107. **33.26** [w_conc=0.00, perplexity, 40KB] What were the rewards for bitcoin mining from 2012-2016Introverted-intuition tak
- 108. **33.25** [w_conc=0.00, thread, 26KB] Agentic marketplace for used goods
- 109. **33.14** [w_conc=1.39, perplexity, 13KB] There’s an social principle where if the size of a community grows to over 500, 
- 110. **32.97** [w_conc=0.00, perplexity, 65KB] I want to hook up my voice memos so that the automatically get inserted into rea
- 111. **32.92** [w_conc=1.39, thread, 23KB] Kenya's renewable energy advantages and scalability
- 112. **32.91** [w_conc=0.00, perplexity, 17KB] Forget a recession. What Canadians are living through is worse. can you explain 
- 113. **32.89** [w_conc=0.00, perplexity, 15KB] https://youtu.be/frqiUkjxAOE?si=rlTjy7QvhXn4gS_H  Can yo summarize this videoChr
- 114. **32.87** [w_conc=2.08, perplexity, 40KB] Our cat that we’ve had for three weeks now who’s peed for the first time when we
- 115. **32.87** [w_conc=0.00, apple-notes, 11KB] apple-notes::June 2026
- 116. **32.87** [w_conc=1.95, perplexity, 10KB] What is the core problem and core solution for international village mall. Expla
- 117. **32.83** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 118. **32.78** [w_conc=0.00, perplexity, 23KB] David defeated the philistines with a stone and momentumDavid defeated Goliath b
- 119. **32.75** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 120. **32.69** [w_conc=0.00, thread, 6KB] Anthropic blocks Claude Pro OAuth tokens
- 121. **32.68** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 122. **32.67** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 123. **32.65** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 124. **32.65** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 125. **32.61** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 126. **32.60** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 127. **32.60** [w_conc=0.00, perplexity, 14KB] can you give me a description of the eyes of and estj vs entj vs intjHere is a d
- 128. **32.59** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 129. **32.55** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 130. **32.53** [w_conc=0.00, thread, 17KB] Andre Iguodala's personality type
- 131. **32.49** [w_conc=0.00, perplexity, 11KB] Simulation Modelling: personality, business physics ~~ movement of people within
- 132. **32.48** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 133. **32.47** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 134. **32.45** [w_conc=0.00, perplexity, 15KB] We know a start of founder that started his original business in 2012 and had fa
- 135. **32.43** [w_conc=0.00, perplexity, 31KB] I want to create a business service that acts as broker for leases, and interior
- 136. **32.41** [w_conc=0.00, thread, 59KB] Crypto transfer phone scam
- 137. **32.37** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 138. **32.37** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 139. **32.36** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 140. **32.32** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 141. **32.27** [w_conc=2.83, perplexity, 9KB] what is the taoist principle of acting and not tryingThe Taoist principle of act
- 142. **32.26** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 143. **32.26** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 144. **32.23** [w_conc=0.00, perplexity, 15KB] i like Ha-Joon Chang, are there any other like him, who would be the best from p
- 145. **32.22** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 146. **32.21** [w_conc=1.61, perplexity, 27KB] I want to create a webapp tool that: allows you to search youtube explore page a
- 147. **32.17** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 148. **32.15** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 149. **32.09** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 150. **32.03** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] the OS-absorbs-the-assistant stress test — strategic-insights: 1. Threat landsca
- 151. **32.01** [w_conc=2.08, perplexity, 12KB] Cna you do an analysis of the coffee commodities market? What account for the pr
- 152. **31.98** [w_conc=0.00, perplexity, 33KB] Using first principles I want to find out why housing costs are so expensive. We
- 153. **31.97** [w_conc=0.00, perplexity, 13KB] what is a split-screen cycle in economicsA split-screen cycle in economics refer
- 154. **31.90** [w_conc=0.00, perplexity, 18KB] the apartments by international village mall and roger's arena, is that area cal
- 155. **31.84** [w_conc=0.00, thread, 43KB] INTJ's ideal personality match
- 156. **31.80** [w_conc=0.00, perplexity, 4KB] How did ai fix the roaming the internet and performing actions problem, list the
- 157. **31.74** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 158. **31.72** [w_conc=0.00, perplexity, 8KB] I want to create business model and plan to present for federal and provincial g
- 159. **31.66** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026
- 160. **31.65** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 161. **31.61** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 162. **31.57** [w_conc=0.00, thread, 12KB] Steve Jobs' prioritization meeting story
- 163. **31.51** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 164. **31.51** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 165. **31.40** [w_conc=0.00, perplexity, 85KB] what is the first home buyers account in canadaThe First Home Savings Account (F
- 166. **31.37** [w_conc=0.00, perplexity, 15KB] Tell me about the tax-free zone in Songdo, Incheon, Korea. What counts as R&D? S
- 167. **31.36** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 168. **31.36** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 9. Why no consumer Glean exists
- 169. **31.36** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 9. Why no consumer Glean exists
- 170. **31.34** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 171. **31.34** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 172. **31.29** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 173. **31.21** [w_conc=0.00, thread, 25KB] Private equity investment targets
- 174. **31.21** [w_conc=0.00, perplexity, 8KB] Dr Arthur Brooks  https://youtu.be/5mpyFuyIQ14?si=OGjygtIocomSlz7q  What persona
- 175. **31.20** [w_conc=0.00, perplexity, 7KB] What are the key things that create good managers vs good creatorsThe most criti
- 176. **31.11** [w_conc=0.00, perplexity, 12KB] Activist investor invests 2b into workdayAn activist investor, Elliott Investmen
- 177. **31.11** [w_conc=0.00, perplexity, 35KB] i'm being interview for a job as a starting engineer at a ai tech startup in can
- 178. **31.04** [w_conc=0.00, perplexity, 6KB] https://www.youtube.com/watch?v=ssYt09bCgUY  summarize this videoThe video intro
- 179. **31.00** [w_conc=0.00, perplexity, 58KB] I sit a lot during the day, I vape, and game on the computer a couple hours a da
- 180. **30.94** [w_conc=0.00, thread, 13KB] Continuing markdown conversations on Perplexity
- 181. **30.91** [w_conc=0.00, perplexity, 19KB] In the Vancouver market, retail and f&b are struggling because of their low marg
- 182. **30.88** [w_conc=0.00, perplexity, 9KB] It seems like to an entj, while an esfp is an activity partner, they can often t
- 183. **30.79** [w_conc=0.00, perplexity, 8KB] as an entj, my ti has always been weak in school, so understand a chain of relat
- 184. **30.77** [w_conc=0.00, perplexity, 19KB] What happening in the market today particularly in the tech sector, and you look
- 185. **30.77** [w_conc=0.00, perplexity, 20KB] In sports, and with my friends, I seem to alway be encouraging, and give thought
- 186. **30.70** [w_conc=0.00, perplexity, 22KB] I had a dream catcher when I was young , do cats act as a dream catcher?Cats are
- 187. **30.60** [w_conc=0.00, perplexity, 7KB] I love playing catan, eu4, civilization, poker. What are the the skills in those
- 188. **30.58** [w_conc=1.95, thread, 6KB] Mapping economic chokepoints for strategic advantage
- 189. **30.53** [w_conc=0.00, perplexity, 47KB] what are the highest rated cat vets in vancouverI can’t reliably rank “highest r
- 190. **30.53** [w_conc=0.00, perplexity, 31KB] Chochu trading co.  Beyond goods: how to circumvent tariffs If we import Chinese
- 191. **30.49** [w_conc=0.00, perplexity, 24KB] Toyota hybrid suv that is the highest ratedThe highest-rated Toyota hybrid SUV r
- 192. **30.46** [w_conc=0.00, thread, 9KB] WiFi-based motion tracking for physio apps
- 193. **30.38** [w_conc=0.00, perplexity, 13KB] wealth management firm and industry overviewIntroverted Intuition – Key Insight 
- 194. **30.34** [w_conc=0.00, perplexity, 27KB] are there any other companies like scale ai but at lower valuations? can you giv
- 195. **30.29** [w_conc=0.00, perplexity, 27KB] tell me many variants of loss leader strategy across many industries. Bridge the
- 196. **30.25** [w_conc=2.56, apple-notes, 4KB] MIKA projects synthesis Mar 25
- 197. **30.23** [w_conc=0.00, perplexity, 7KB] Can you ask my mentors what they think of this? Is this true or can you focus on
- 198. **30.17** [w_conc=0.00, perplexity, 12KB] International village in downtown Vancouver has huge vacancy right now, and they
- 199. **30.09** [w_conc=0.00, perplexity, 22KB] Fed chair update and what it means for the market, why did trump want Jerome Pow
- 200. **30.06** [w_conc=1.61, apple-notes, 2KB] MIKAI Feature: Ai directed content
- 201. **30.02** [w_conc=0.00, perplexity, 8KB] Difference between psychology and psychiatry and other disciplines within that f
- 202. **29.98** [w_conc=0.00, thread, 9KB] Derek's systems thinking and applications to AI and geopolit
- 203. **29.97** [w_conc=1.39, apple-notes, 4KB] Modern solutions for the rentiers problem
- 204. **29.89** [w_conc=0.00, thread, 12KB] Finding the weak link in AI's circular economy
- 205. **29.88** [w_conc=2.08, perplexity, 24KB] Is there such thing as our cats not wanting to come into me and my partner‘s roo
- 206. **29.84** [w_conc=4.03, apple-notes, 4KB] Building credibility for a Google acquisition
- 207. **29.80** [w_conc=0.00, perplexity, 9KB] What happened to activist investing? Is there an investing principle or an organ
- 208. **29.80** [w_conc=0.00, perplexity, 10KB] Restaurants in Vancouver are dying right now because people don’t have enough di
- 209. **29.78** [w_conc=1.95, perplexity, 3KB] “Based on everything you know about me from our full chat history and memory, gi
- 210. **29.75** [w_conc=0.00, perplexity, 9KB] I looking for a Vancouver economic group that believes in Georgiam or Joseph sti
- 211. **29.74** [w_conc=0.00, perplexity, 29KB] can you do a case study on instant financial https://www.instant.co/ and how the
- 212. **29.71** [w_conc=0.00, perplexity, 16KB] is weride a chinese company? What are the prices for their robo sweepers and sim
- 213. **29.68** [w_conc=0.00, perplexity, 20KB] From everything we have discussed in this space called International Village, gi
- 214. **29.66** [w_conc=0.00, perplexity, 25KB] Best cafes in Nairobi that tech workers work at. I usually go to coffee shops li
- 215. **29.61** [w_conc=0.00, perplexity, 5KB] If AGI is for sure coming, explain the landscape or topography of AGI as an anal
- 216. **29.59** [w_conc=0.00, perplexity, 7KB] Below are my notes for International Villages project I've been working on this 
- 217. **29.43** [w_conc=0.00, perplexity, 5KB] what is the status of ai agents right now? What actions can they perform? What a
- 218. **29.40** [w_conc=0.00, thread, 17KB] Electrician career paths in BC for low-voltage experience
- 219. **29.35** [w_conc=0.00, perplexity, 34KB] Can I self inject this?Self-injecting GHK-Cu (Copper Peptide) purchased online i
- 220. **29.34** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026
- 221. **29.31** [w_conc=0.00, perplexity, 18KB] For tech jobs, typically the big 5 was considered optimal. I want the next up an
- 222. **29.31** [w_conc=1.39, perplexity, 11KB] What has accounted for qqq rising to new high in the last 3 months?The primary d
- 223. **29.28** [w_conc=0.00, perplexity, 24KB] I was caught smoking outside the Nairobi airport and a police officer want to ta
- 224. **29.23** [w_conc=0.00, perplexity, 36KB] what is the weight range for a 22cm black domestic shorthairFor an adult domesti
- 225. **29.14** [w_conc=0.00, apple-notes, 4KB] Mika architecture ideas
- 226. **29.07** [w_conc=0.00, perplexity, 20KB] When the market swings down dramatically like today, where does that capital go?
- 227. **29.06** [w_conc=0.00, perplexity, 17KB] how did bob rennie start his firm, what was the startBob Rennie started his firm
- 228. **29.02** [w_conc=0.00, perplexity, 11KB] how to get rid of fear, or to act in fear, I'm scared of sudden movements and sc
- 229. **28.93** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] what to copy from enterprise, what to skip — strategic-synthesis-2026-06-14: 10.
- 230. **28.93** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] what to copy from enterprise, what to skip — strategic-insights: 10. MIKAI archi

_(2441 additional low-score candidates omitted; see JSON for full list.)_
