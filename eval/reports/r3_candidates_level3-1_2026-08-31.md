# R3 Candidate Salience — Level 3.1 (aggregation-aware, no-blacklist) — 2026-08-31

Ranked candidates for the next ingestion round, scored via **weighted concept intersection** (Session-10 spec in `fuzzy-shimmying-wreath.md`).

**Disposable one-shot scorer.** Purpose: schedule which un-ingested wiki-raw sources get the next paid `claude -p` call. Not a peer of the post-ingest salience system (`wiki-salience.md` / `dream_bootstrap.py`); no eval, no versioning. Judged only by downstream post-ingest recall@10 lift. Retire when the wiki-raw backlog drains.

## Universe & filtering

- Total wiki-raw sections: **15055**
- Filtered out — `claude-code` per-turn fragments: **10435**
- Filtered out — malformed `claude-thread` orphans (name missing `::title::idx::role`): **663**
- Unique claude threads (well-formed): **69**
- Other sections (apple-notes, perplexity, ...): **2608**
- Already ingested into parallel vault: **59** files
- Skipped as already-ingested during scoring: **59**
- Skipped as empty body: **0**
- **Candidates evaluated: 2618**

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

**weighted_concept** — MIKAI-central signal. Sums `log(1+in-degree)` over concept slugs (min length 5, kebab-case) hit in source body. Max concept weight this run: **3.33**. Vocab: 210 slugs.

**weighted_personal** — broader Brian-profile signal (Level 3 addition). Sums per-token weight from a compiled personal vocabulary. Sources: USER_MODEL.md (1.5), PROFILE.md (1.0), BRAIN.md priorities (0.7), entity slugs (0.5), wisdom/goals/habits/reflections (0.5), queries (0.4), journal tags (0.3). Max personal weight this run: **1.50**. Vocab: 1278 tokens. Tokens already in concept vocab are excluded from this component to avoid double-counting.

Goal source: `~/.mikai/brain/GOALS.md` (10 goals).

## Top 30 candidates

| # | score | w_conc | w_pers | goal | rec | subst | agg | kind | KB | turns | title |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 54.76 | 3.18 | 47.33 | 0.40 | 0.55 | 1.00 | 1.50 | perplexity | 52 | — | Expand on the ideas explored in MIKA/REMY TECH, what technol |
| 2 | 54.67 | 1.39 | 49.02 | 0.41 | 0.55 | 1.00 | 1.50 | perplexity | 49 | — | My Mentors: Based on my threads, conceptual inquiries, I wan |
| 3 | 50.98 | 0.00 | 46.72 | 0.41 | 0.55 | 0.98 | 1.50 | perplexity | 45 | — | what are the capabilities of n8n and open claw. Contextualiz |
| 4 | 49.01 | 0.00 | 44.95 | 0.36 | 0.55 | 0.92 | 1.50 | perplexity | 34 | — | I want to compare https://www.wikiwand.com/en/articles/Fran% |
| 5 | 45.54 | 0.00 | 40.69 | 0.52 | 0.81 | 0.98 | 1.50 | thread | 122 | 27 | Determining ENTJ vs INTJ personality type |
| 6 | 45.39 | 2.20 | 38.25 | 0.50 | 0.94 | 1.00 | 1.50 | thread | 953 | 329 | Weighted yoga for flexibility and alignment |
| 7 | 45.38 | 0.00 | 41.59 | 0.31 | 0.55 | 0.81 | 1.50 | perplexity | 22 | — | Translate the following Ni whitepaper using Si and Te langua |
| 8 | 45.25 | 0.00 | 41.00 | 0.40 | 0.55 | 1.00 | 1.50 | perplexity | 55 | — | Chip war and Geopolitical strategy of USA vs CHINA   what is |
| 9 | 44.17 | 3.69 | 36.31 | 0.39 | 0.55 | 0.96 | 1.50 | perplexity | 40 | — | What does an entj with low conscientiousness look like, does |
| 10 | 43.60 | 0.00 | 39.31 | 0.41 | 0.55 | 1.00 | 1.50 | perplexity | 51 | — | What happens in a society where all the brands become conglo |
| 11 | 43.31 | 0.00 | 39.06 | 0.40 | 0.55 | 1.00 | 1.50 | perplexity | 74 | — | Kenyan fruits: Can I wash fruits at a luxury apartments in N |
| 12 | 43.00 | 2.20 | 35.95 | 0.52 | 0.81 | 1.00 | 1.50 | thread | 371 | 84 | Dining room layout and color coordination strategy |
| 13 | 42.05 | 0.00 | 37.51 | 0.49 | 0.55 | 1.00 | 1.50 | perplexity | 62 | — | Who are the characters from reborn rich based onCore Insight |
| 14 | 41.99 | 2.20 | 35.45 | 0.43 | 0.55 | 1.00 | 1.50 | perplexity | 77 | — | Can you explain this image with more science or information. |
| 15 | 41.87 | 0.00 | 37.92 | 0.31 | 0.55 | 0.97 | 1.50 | perplexity | 41 | — | what do Yanis Varoufakis and joseph stiglitz have in common, |
| 16 | 41.70 | 0.00 | 37.77 | 0.31 | 0.55 | 0.96 | 1.50 | perplexity | 40 | — | I want to understand what kind of economist I am. I'm lookin |
| 17 | 40.73 | 0.00 | 36.60 | 0.36 | 0.55 | 0.98 | 1.50 | perplexity | 44 | — | How do people use Ni in their first function, and what about |
| 18 | 40.49 | 0.00 | 36.63 | 0.32 | 0.55 | 0.87 | 1.50 | perplexity | 28 | — | Rewriting the Rules of the American Economy“Rewriting the Ru |
| 19 | 39.82 | 0.00 | 35.80 | 0.34 | 0.55 | 0.96 | 1.50 | perplexity | 40 | — | semis vs software portfolio strategy, why is there software  |
| 20 | 39.71 | 0.00 | 35.92 | 0.28 | 0.55 | 0.90 | 1.50 | perplexity | 32 | — | I want to be with people that are slightly critical about th |
| 21 | 39.44 | 0.00 | 35.05 | 0.45 | 0.55 | 1.00 | 1.50 | perplexity | 68 | — | what is the profitability of 3d ocean farmingBased on the pr |
| 22 | 38.80 | 3.18 | 32.61 | 0.17 | 0.55 | 0.46 | 1.49 | apple-notes | 4 | — | projects |
| 23 | 38.75 | 0.00 | 35.22 | 0.22 | 0.55 | 0.82 | 1.50 | perplexity | 22 | — | I keep asking this structural and economic question in my th |
| 24 | 38.51 | 0.00 | 34.62 | 0.33 | 0.55 | 0.87 | 1.50 | perplexity | 27 | — | What does the bible say about the ideal wifeThe Bible’s visi |
| 25 | 38.40 | 3.18 | 32.26 | 0.15 | 0.55 | 0.46 | 1.50 | apple-notes | 4 | — | Building moats beyond model improvement |
| 26 | 38.20 | 0.00 | 33.91 | 0.41 | 0.55 | 1.00 | 1.50 | perplexity | 67 | — | Kenya Tourism questions is it cheap to get scube certified i |
| 27 | 37.74 | 0.00 | 33.71 | 0.34 | 0.55 | 0.97 | 1.50 | perplexity | 42 | — | Pull up Alex Karp’s phd thesis and explain the concepts arou |
| 28 | 37.66 | 0.00 | 33.92 | 0.27 | 0.55 | 0.88 | 1.50 | perplexity | 29 | — | Anthropic open ai, and perplexity valuation,   What are thei |
| 29 | 37.61 | 4.61 | 28.91 | 0.35 | 0.55 | 1.00 | 1.50 | perplexity | 98 | — | (Bot) Options Trading StrategiesVolatility arbitrage (vol ar |
| 30 | 37.52 | 0.00 | 33.97 | 0.23 | 0.55 | 0.80 | 1.50 | perplexity | 21 | — | Can you explain all the companies in the supply chain ecosys |

### Top concept + personal hits per candidate (top 15)

- **1.** Expand on the ideas explored in MIKA/REMY TECH, what technol
  - concepts: `personal-intent-graph` (3.18)
  - personal: `shortlist` (1.50), `threads` (1.50), `claude` (1.50)
- **2.** My Mentors: Based on my threads, conceptual inquiries, I wan
  - concepts: `mimetic-competition` (1.39)
  - personal: `evidence` (1.50), `stakes` (1.50), `threads` (1.50)
- **3.** what are the capabilities of n8n and open claw. Contextualiz
  - concepts: —
  - personal: `remote` (1.50), `stakes` (1.50), `threads` (1.50)
- **4.** I want to compare https://www.wikiwand.com/en/articles/Fran%
  - concepts: —
  - personal: `deciding` (1.50), `threads` (1.50), `claude` (1.50)
- **5.** Determining ENTJ vs INTJ personality type
  - concepts: —
  - personal: `evidence` (1.50), `abandoned` (1.50), `stakes` (1.50)
- **6.** Weighted yoga for flexibility and alignment
  - concepts: `space-between` (2.20)
  - personal: `reverses` (1.50), `evidence` (1.50), `stakes` (1.50)
- **7.** Translate the following Ni whitepaper using Si and Te langua
  - concepts: —
  - personal: `evidence` (1.50), `compression` (1.50), `entities` (1.50)
- **8.** Chip war and Geopolitical strategy of USA vs CHINA   what is
  - concepts: —
  - personal: `deciding` (1.50), `threads` (1.50), `claude` (1.50)
- **9.** What does an entj with low conscientiousness look like, does
  - concepts: `implementation-intentions` (2.08), `information-diet` (1.61)
  - personal: `evidence` (1.50), `stakes` (1.50), `context` (1.50)
- **10.** What happens in a society where all the brands become conglo
  - concepts: —
  - personal: `compression` (1.50), `entities` (1.50), `context` (1.50)
- **11.** Kenyan fruits: Can I wash fruits at a luxury apartments in N
  - concepts: —
  - personal: `evidence` (1.50), `remote` (1.50), `threads` (1.50)
- **12.** Dining room layout and color coordination strategy
  - concepts: `space-between` (2.20)
  - personal: `evidence` (1.50), `remote` (1.50), `deciding` (1.50)
- **13.** Who are the characters from reborn rich based onCore Insight
  - concepts: —
  - personal: `evidence` (1.50), `stakes` (1.50), `context` (1.50)
- **14.** Can you explain this image with more science or information.
  - concepts: `space-between` (2.20)
  - personal: `evidence` (1.50), `check-in` (1.50), `breathing` (1.50)
- **15.** what do Yanis Varoufakis and joseph stiglitz have in common,
  - concepts: —
  - personal: `evidence` (1.50), `threads` (1.50), `claude` (1.50)

## Recommended next batch (top 15)

- Total volume: **2055KB** across 15 sources
- Est. wall-clock: **~6min** at workers=8, **~50min** at workers=1 (assumes ~200s/source average)
- Would land as R3-2026-08-31-mikai-followup

| # | score | w_conc | w_pers | title | KB | filename |
|---|---|---|---|---|---|---|
| 1 | 54.76 | 3.18 | 47.33 | Expand on the ideas explored in MIKA/REMY TECH, what technol | 52 | `2026-03-19-expand-on-the-ideas-explored-in-mika-remy-tech-what-technolo-da8841.md` |
| 2 | 54.67 | 1.39 | 49.02 | My Mentors: Based on my threads, conceptual inquiries, I wan | 49 | `2026-03-19-my-mentors-based-on-my-threads-conceptual-inquiries-i-want-t-79f21b.md` |
| 3 | 50.98 | 0.00 | 46.72 | what are the capabilities of n8n and open claw. Contextualiz | 45 | `2026-03-19-what-are-the-capabilities-of-n8n-and-open-claw-contextualize-85decc.md` |
| 4 | 49.01 | 0.00 | 44.95 | I want to compare https://www.wikiwand.com/en/articles/Fran% | 34 | `2026-03-19-i-want-to-compare-https-www-wikiwand-com-en-articles-fran-c3-6d79aa.md` |
| 5 | 45.54 | 0.00 | 40.69 | Determining ENTJ vs INTJ personality type | 122 | `2026-03-12-determining-entj-vs-intj-personality-type-c199e4.md` |
| 6 | 45.39 | 2.20 | 38.25 | Weighted yoga for flexibility and alignment | 953 | `2026-06-02-weighted-yoga-for-flexibility-and-alignment-83cccc.md` |
| 7 | 45.38 | 0.00 | 41.59 | Translate the following Ni whitepaper using Si and Te langua | 22 | `2026-03-19-translate-the-following-ni-whitepaper-using-si-and-te-langua-55611a.md` |
| 8 | 45.25 | 0.00 | 41.00 | Chip war and Geopolitical strategy of USA vs CHINA   what is | 55 | `2026-03-19-chip-war-and-geopolitical-strategy-of-usa-vs-china-what-is-i-de13df.md` |
| 9 | 44.17 | 3.69 | 36.31 | What does an entj with low conscientiousness look like, does | 40 | `2026-03-19-what-does-an-entj-with-low-conscientiousness-look-like-does-42ce4e.md` |
| 10 | 43.60 | 0.00 | 39.31 | What happens in a society where all the brands become conglo | 51 | `2026-03-19-what-happens-in-a-society-where-all-the-brands-become-conglo-095746.md` |
| 11 | 43.31 | 0.00 | 39.06 | Kenyan fruits: Can I wash fruits at a luxury apartments in N | 74 | `2026-03-19-kenyan-fruits-can-i-wash-fruits-at-a-luxury-apartments-in-na-6951a1.md` |
| 12 | 43.00 | 2.20 | 35.95 | Dining room layout and color coordination strategy | 371 | `2026-05-28-dining-room-layout-and-color-coordination-strategy-bd5f22.md` |
| 13 | 42.05 | 0.00 | 37.51 | Who are the characters from reborn rich based onCore Insight | 62 | `2026-03-19-who-are-the-characters-from-reborn-rich-based-oncore-insight-238e6f.md` |
| 14 | 41.99 | 2.20 | 35.45 | Can you explain this image with more science or information. | 77 | `2026-03-19-can-you-explain-this-image-with-more-science-or-information-ab9e4b.md` |
| 15 | 41.87 | 0.00 | 37.92 | what do Yanis Varoufakis and joseph stiglitz have in common, | 41 | `2026-03-19-what-do-yanis-varoufakis-and-joseph-stiglitz-have-in-common-d483d1.md` |

## Appendix — next 200 candidates (rank 31+, brief)

- 31. **37.45** [w_conc=0.00, perplexity, 15KB] explain derek Cabrera dsrp method in a way that I can understand fully the conce
- 32. **37.21** [w_conc=0.00, thread, 211KB] Identifying an Alocasia plant
- 33. **37.07** [w_conc=0.00, perplexity, 16KB] Describe the lessons and insights that Huozhi Zhuan wrote about commerce and the
- 34. **36.84** [w_conc=0.00, perplexity, 32KB] what to enfj's day dream aboutENFJs most often daydream about guiding or support
- 35. **36.79** [w_conc=0.00, perplexity, 34KB] can you analyze vancouver brand aritzia and their expansion over the last few ye
- 36. **36.64** [w_conc=0.00, perplexity, 35KB] I don’t understand the difference between a brand and business then, it’s seems 
- 37. **36.54** [w_conc=0.00, perplexity, 97KB] EC Rare Book market research: What is the value of the rare books market compare
- 38. **36.35** [w_conc=0.00, thread, 326KB] Building a championship roster around Luka in Vancouver
- 39. **36.20** [w_conc=0.00, thread, 23KB] Unreciprocated effort and emotional withdrawal patterns
- 40. **36.14** [w_conc=0.00, perplexity, 32KB] i want a comprehensive understanding of why countries want or not want foreign d
- 41. **35.86** [w_conc=0.00, perplexity, 10KB] If AGI is for sure coming, explain the landscape or topography of AGI as an anal
- 42. **35.75** [w_conc=0.00, perplexity, 36KB] Are there any examples of an all ai news YouTube or Spotify podcast?Yes, there a
- 43. **35.27** [w_conc=0.00, thread, 109KB] Sphagnum moss vs peat moss for DIY Monstera poles
- 44. **35.07** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] what the moat looks like in features — strategic-synthesis-2026-06-14: 2. The de
- 45. **35.07** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] what the moat looks like in features — strategic-insights: 2. The depth thesis —
- 46. **35.03** [w_conc=2.20, perplexity, 13KB] How valuable is OCR data from social media. A lot i imagineYour instinct is righ
- 47. **34.71** [w_conc=0.00, perplexity, 16KB] never split the difference, book on negotiation and communication“Never Split th
- 48. **34.63** [w_conc=0.00, perplexity, 21KB] Can you read the transcript of this video: https://www.youtube.com/watch?v=_mwm6
- 49. **34.55** [w_conc=3.56, perplexity, 36KB] give me updates of nvda appl and tsla today in the newsHere's a concise summary 
- 50. **34.53** [w_conc=0.00, perplexity, 7KB] Where is the state of Ai agents right now? How powerful are they in producing ac
- 51. **34.46** [w_conc=0.00, apple-notes, 24KB] apple-notes::Feb 2025 - David and the Dao
- 52. **34.35** [w_conc=0.00, apple-notes, 4KB] memories
- 53. **34.13** [w_conc=0.00, perplexity, 55KB] Entj 7w8 vs 8w7. I want to know which one I amTo determine whether you are an EN
- 54. **34.10** [w_conc=0.00, perplexity, 40KB] Ha-Joon Chang, Byung-Chul Han Sandwich there was a thread that talked about how 
- 55. **33.87** [w_conc=0.00, perplexity, 41KB] I want to fill international village in chinatown with budding entrepreneurs fro
- 56. **33.64** [w_conc=2.20, thread, 174KB] Wind-resistant plants for apartment living
- 57. **33.53** [w_conc=0.00, thread, 41KB] Anarchist digital spaces beyond Bitcoin
- 58. **33.44** [w_conc=0.00, perplexity, 23KB] Below is the problem my engineering team is trying to solve. Give me a high leve
- 59. **33.42** [w_conc=0.00, perplexity, 45KB] I want to put on a bear call for tech stocks related to ai and ai compute, and I
- 60. **33.41** [w_conc=0.00, thread, 9KB] Identifying productivity theater in daily habits
- 61. **33.33** [w_conc=0.00, perplexity, 20KB] vancouver from early 2000s to 2021 faced unprecendented growth in their housing 
- 62. **32.98** [w_conc=0.00, perplexity, 17KB] Wha are ai agent swarmsAI agent swarms are groups of specialized AI agents that 
- 63. **32.93** [w_conc=0.00, thread, 65KB] Specialty coffee product scaling and market distribution
- 64. **32.53** [w_conc=0.00, perplexity, 99KB] My cats poo is dark brown and it’s almost black, but we’re worried by looking at
- 65. **32.44** [w_conc=0.00, apple-notes, 11KB] apple-notes::June 2026
- 66. **32.44** [w_conc=0.00, apple-notes, 11KB] apple-notes::June 2026
- 67. **32.36** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 7. Paths forward, ranked by historical viability
- 68. **32.36** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 7. Paths forward, ranked by historical viability
- 69. **32.35** [w_conc=0.00, perplexity, 97KB] assessed property value vs fair market value?Assessed property value and fair ma
- 70. **32.34** [w_conc=0.00, perplexity, 10KB] It seems like the concept of AI agents have existed since the 80s. I remember re
- 71. **32.22** [w_conc=0.00, perplexity, 14KB] The first business that I want to build out for in international villages mall i
- 72. **32.13** [w_conc=0.00, perplexity, 12KB] So how has Peter thiel executed on this philosophy?Peter Thiel has executed this
- 73. **32.12** [w_conc=0.00, perplexity, 16KB] What startups have come out of ihub that are significant? What startups are ther
- 74. **32.04** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 75. **31.97** [w_conc=0.00, perplexity, 99KB] In frostpunk 2 what is the best strategy: tech, exploration, etcFor Frostpunk 2 
- 76. **31.91** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 77. **31.85** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 78. **31.77** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 79. **31.72** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 80. **31.72** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 81. **31.71** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 82. **31.69** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 83. **31.68** [w_conc=0.00, thread, 86KB] Forward head posture root causes
- 84. **31.68** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 85. **31.58** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 86. **31.57** [w_conc=0.00, perplexity, 38KB] can you give me an overview of henderson development in canada as well as their 
- 87. **31.49** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 88. **30.98** [w_conc=0.00, perplexity, 29KB] Mark and I close university friends and have also been roommates after college t
- 89. **30.96** [w_conc=0.00, perplexity, 15KB] https://youtu.be/frqiUkjxAOE?si=rlTjy7QvhXn4gS_H  Can yo summarize this videoChr
- 90. **30.92** [w_conc=0.00, apple-notes, 11KB] apple-notes::June 2026
- 91. **30.89** [w_conc=2.08, perplexity, 40KB] Our cat that we’ve had for three weeks now who’s peed for the first time when we
- 92. **30.84** [w_conc=0.00, perplexity, 14KB] Who is the content creator or social media head that is the best at assessing ne
- 93. **30.81** [w_conc=0.00, perplexity, 65KB] I want to hook up my voice memos so that the automatically get inserted into rea
- 94. **30.70** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 95. **30.65** [w_conc=0.00, thread, 30KB] Best iPhone generation to buy: first or stabilized iteration
- 96. **30.63** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 97. **30.62** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 98. **30.61** [w_conc=1.95, perplexity, 10KB] What is the core problem and core solution for international village mall. Expla
- 99. **30.59** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 100. **30.59** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 101. **30.55** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 102. **30.55** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 103. **30.55** [w_conc=0.00, perplexity, 17KB] Forget a recession. What Canadians are living through is worse. can you explain 
- 104. **30.54** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 105. **30.52** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 106. **30.49** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 107. **30.47** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 108. **30.46** [w_conc=0.00, perplexity, 31KB] I want to create a business service that acts as broker for leases, and interior
- 109. **30.45** [w_conc=0.00, perplexity, 27KB] a fully transcend entj will act more like a?A fully realized, transcendent ENTJ 
- 110. **30.39** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 111. **30.30** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 112. **30.30** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 113. **30.27** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 114. **30.27** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 115. **30.26** [w_conc=0.00, thread, 59KB] Crypto transfer phone scam
- 116. **30.23** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 117. **30.22** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 118. **30.16** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 119. **30.15** [w_conc=0.00, perplexity, 11KB] Simulation Modelling: personality, business physics ~~ movement of people within
- 120. **30.09** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 9. Why no consumer Glean exists
- 121. **30.09** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 9. Why no consumer Glean exists
- 122. **30.08** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 123. **30.05** [w_conc=0.00, thread, 17KB] Andre Iguodala's personality type
- 124. **30.05** [w_conc=0.00, perplexity, 14KB] can you give me a description of the eyes of and estj vs entj vs intjHere is a d
- 125. **30.01** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 126. **30.01** [w_conc=0.00, perplexity, 33KB] Using first principles I want to find out why housing costs are so expensive. We
- 127. **29.96** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 128. **29.92** [w_conc=0.00, perplexity, 18KB] the apartments by international village mall and roger's arena, is that area cal
- 129. **29.89** [w_conc=1.61, perplexity, 27KB] I want to create a webapp tool that: allows you to search youtube explore page a
- 130. **29.84** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 131. **29.81** [w_conc=0.00, strategic-synthesis-2026-06-14, 4KB] the OS-absorbs-the-assistant stress test — strategic-insights: 1. Threat landsca
- 132. **29.78** [w_conc=0.00, perplexity, 16KB] what is the definition of ditzy. can you analyze in it the context of a socionic
- 133. **29.76** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 134. **29.75** [w_conc=0.00, perplexity, 23KB] David defeated the philistines with a stone and momentumDavid defeated Goliath b
- 135. **29.75** [w_conc=0.00, thread, 12KB] Steve Jobs' prioritization meeting story
- 136. **29.72** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026
- 137. **29.66** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 138. **29.65** [w_conc=0.00, perplexity, 13KB] what is a split-screen cycle in economicsA split-screen cycle in economics refer
- 139. **29.64** [w_conc=0.00, perplexity, 40KB] What were the rewards for bitcoin mining from 2012-2016Introverted-intuition tak
- 140. **29.61** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 141. **29.58** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 142. **29.46** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 143. **29.45** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 144. **29.44** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 145. **29.41** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 146. **29.31** [w_conc=0.00, perplexity, 4KB] perplexity: Expand on the ideas explored in MIKA/REMY TECH, what technol
- 147. **29.31** [w_conc=0.00, perplexity, 4KB] perplexity: Expand on the ideas explored in MIKA/REMY TECH, what technol
- 148. **29.29** [w_conc=1.61, apple-notes, 2KB] MIKAI Feature: Ai directed content
- 149. **29.16** [w_conc=0.00, perplexity, 15KB] We know a start of founder that started his original business in 2012 and had fa
- 150. **29.10** [w_conc=0.00, perplexity, 32KB] what do the people of south korea, yantai, qingdao and dalian have in commonPeop
- 151. **29.03** [w_conc=2.08, perplexity, 12KB] Cna you do an analysis of the coffee commodities market? What account for the pr
- 152. **28.98** [w_conc=0.00, perplexity, 4KB] How did ai fix the roaming the internet and performing actions problem, list the
- 153. **28.95** [w_conc=0.00, perplexity, 8KB] Dr Arthur Brooks  https://youtu.be/5mpyFuyIQ14?si=OGjygtIocomSlz7q  What persona
- 154. **28.93** [w_conc=0.00, perplexity, 6KB] describe the the I's that is shown in this video: https://www.youtube.com/watch?
- 155. **28.93** [w_conc=0.00, perplexity, 15KB] Tell me about the tax-free zone in Songdo, Incheon, Korea. What counts as R&D? S
- 156. **28.91** [w_conc=0.00, perplexity, 85KB] what is the first home buyers account in canadaThe First Home Savings Account (F
- 157. **28.91** [w_conc=0.00, perplexity, 19KB] In the Vancouver market, retail and f&b are struggling because of their low marg
- 158. **28.84** [w_conc=0.00, perplexity, 8KB] as an entj, my ti has always been weak in school, so understand a chain of relat
- 159. **28.76** [w_conc=0.00, perplexity, 13KB] There’s an social principle where if the size of a community grows to over 500, 
- 160. **28.71** [w_conc=0.00, perplexity, 58KB] I sit a lot during the day, I vape, and game on the computer a couple hours a da
- 161. **28.64** [w_conc=0.00, perplexity, 35KB] i'm being interview for a job as a starting engineer at a ai tech startup in can
- 162. **28.61** [w_conc=0.00, perplexity, 12KB] Activist investor invests 2b into workdayAn activist investor, Elliott Investmen
- 163. **28.61** [w_conc=0.00, perplexity, 47KB] what are the highest rated cat vets in vancouverI can’t reliably rank “highest r
- 164. **28.60** [w_conc=2.08, apple-notes, 4KB] MIKA projects synthesis Mar 25
- 165. **28.47** [w_conc=0.00, perplexity, 6KB] https://www.youtube.com/watch?v=ssYt09bCgUY  summarize this videoThe video intro
- 166. **28.46** [w_conc=0.00, perplexity, 20KB] In sports, and with my friends, I seem to alway be encouraging, and give thought
- 167. **28.41** [w_conc=0.00, perplexity, 7KB] I love playing catan, eu4, civilization, poker. What are the the skills in those
- 168. **28.19** [w_conc=0.00, perplexity, 8KB] I want to create business model and plan to present for federal and provincial g
- 169. **28.17** [w_conc=0.00, perplexity, 9KB] It seems like to an entj, while an esfp is an activity partner, they can often t
- 170. **28.16** [w_conc=0.00, perplexity, 24KB] Toyota hybrid suv that is the highest ratedThe highest-rated Toyota hybrid SUV r
- 171. **28.12** [w_conc=0.00, perplexity, 13KB] wealth management firm and industry overviewIntroverted Intuition – Key Insight 
- 172. **28.05** [w_conc=0.00, perplexity, 19KB] What happening in the market today particularly in the tech sector, and you look
- 173. **28.05** [w_conc=0.00, perplexity, 7KB] Can you ask my mentors what they think of this? Is this true or can you focus on
- 174. **27.99** [w_conc=0.00, perplexity, 12KB] International village in downtown Vancouver has huge vacancy right now, and they
- 175. **27.93** [w_conc=0.00, perplexity, 27KB] are there any other companies like scale ai but at lower valuations? can you giv
- 176. **27.84** [w_conc=0.00, thread, 12KB] Finding the weak link in AI's circular economy
- 177. **27.82** [w_conc=0.00, perplexity, 29KB] can you do a case study on instant financial https://www.instant.co/ and how the
- 178. **27.81** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] what to copy from enterprise, what to skip — strategic-synthesis-2026-06-14: 10.
- 179. **27.81** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] what to copy from enterprise, what to skip — strategic-insights: 10. MIKAI archi
- 180. **27.80** [w_conc=2.08, perplexity, 24KB] Is there such thing as our cats not wanting to come into me and my partner‘s roo
- 181. **27.78** [w_conc=0.00, perplexity, 7KB] What are the key things that create good managers vs good creatorsThe most criti
- 182. **27.75** [w_conc=0.00, perplexity, 11KB] how to get rid of fear, or to act in fear, I'm scared of sudden movements and sc
- 183. **27.69** [w_conc=0.00, perplexity, 9KB] what is the taoist principle of acting and not tryingThe Taoist principle of act
- 184. **27.65** [w_conc=0.00, perplexity, 22KB] I had a dream catcher when I was young , do cats act as a dream catcher?Cats are
- 185. **27.52** [w_conc=0.00, perplexity, 10KB] Restaurants in Vancouver are dying right now because people don’t have enough di
- 186. **27.51** [w_conc=0.00, perplexity, 22KB] Fed chair update and what it means for the market, why did trump want Jerome Pow
- 187. **27.50** [w_conc=0.00, perplexity, 16KB] is weride a chinese company? What are the prices for their robo sweepers and sim
- 188. **27.46** [w_conc=0.00, perplexity, 9KB] I looking for a Vancouver economic group that believes in Georgiam or Joseph sti
- 189. **27.37** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026
- 190. **27.37** [w_conc=0.00, perplexity, 7KB] Below are my notes for International Villages project I've been working on this 
- 191. **27.32** [w_conc=0.00, perplexity, 27KB] tell me many variants of loss leader strategy across many industries. Bridge the
- 192. **27.29** [w_conc=1.61, apple-notes, 4KB] Making AI invisible through personalized knowledge architecture
- 193. **27.13** [w_conc=1.39, perplexity, 11KB] What has accounted for qqq rising to new high in the last 3 months?The primary d
- 194. **27.12** [w_conc=0.00, perplexity, 5KB] If AGI is for sure coming, explain the landscape or topography of AGI as an anal
- 195. **27.05** [w_conc=0.00, perplexity, 36KB] what is the weight range for a 22cm black domestic shorthairFor an adult domesti
- 196. **27.04** [w_conc=0.00, perplexity, 34KB] Can I self inject this?Self-injecting GHK-Cu (Copper Peptide) purchased online i
- 197. **27.01** [w_conc=0.00, perplexity, 15KB] i like Ha-Joon Chang, are there any other like him, who would be the best from p
- 198. **26.99** [w_conc=0.00, thread, 14KB] 💬 A system that surfaces all the…
- 199. **26.98** [w_conc=0.00, perplexity, 31KB] Chochu trading co.  Beyond goods: how to circumvent tariffs If we import Chinese
- 200. **26.98** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-synthesis-2026-06-14: 3. The product
- 201. **26.98** [w_conc=0.00, strategic-synthesis-2026-06-14, 3KB] strategic-insights: 3. The product
- 202. **26.94** [w_conc=0.00, perplexity, 17KB] how did bob rennie start his firm, what was the startBob Rennie started his firm
- 203. **26.93** [w_conc=1.61, claude, 4KB] claude: Making AI invisible through personalized knowledge architect
- 204. **26.89** [w_conc=0.00, perplexity, 9KB] What happened to activist investing? Is there an investing principle or an organ
- 205. **26.87** [w_conc=0.00, thread, 19KB] Low voltage electrical companies in BC for Patrick
- 206. **26.85** [w_conc=0.00, perplexity, 25KB] Best cafes in Nairobi that tech workers work at. I usually go to coffee shops li
- 207. **26.80** [w_conc=0.00, perplexity, 20KB] When the market swings down dramatically like today, where does that capital go?
- 208. **26.80** [w_conc=0.00, perplexity, 5KB] what is the status of ai agents right now? What actions can they perform? What a
- 209. **26.78** [w_conc=0.00, perplexity, 20KB] From everything we have discussed in this space called International Village, gi
- 210. **26.78** [w_conc=0.00, perplexity, 8KB] Difference between psychology and psychiatry and other disciplines within that f
- 211. **26.77** [w_conc=0.00, perplexity, 6KB] can you detail benjamin franklin's journaling style and his reasoning for itBenj
- 212. **26.64** [w_conc=0.00, perplexity, 11KB] I feel confused and disheartened because I’m Fighting with Germaine about commun
- 213. **26.54** [w_conc=0.00, thread, 4KB] Finding your ideal sports coaching philosophy
- 214. **26.54** [w_conc=0.00, perplexity, 5KB] Tell me what is limited with perplexity’s memory capabilities to understand my t
- 215. **26.49** [w_conc=0.00, apple-notes, 4KB] apple-notes::July 2026
- 216. **26.42** [w_conc=0.00, perplexity, 23KB] It’s not creditors, I have my business listed as a sole proprietorship and I owe
- 217. **26.33** [w_conc=0.00, apple-notes, 4KB] Mika architecture ideas
- 218. **26.26** [w_conc=0.00, perplexity, 45KB] For an entj, describe relationships with esfp vs enfpAs an ENTJ, your relationsh
- 219. **26.24** [w_conc=0.00, perplexity, 18KB] For tech jobs, typically the big 5 was considered optimal. I want the next up an
- 220. **26.17** [w_conc=0.00, perplexity, 3KB] what other agents operate like openclawSeveral other agents follow a similar “au
- 221. **26.16** [w_conc=0.00, thread, 39KB] Rent vs. buy analysis for Vancouver
- 222. **26.12** [w_conc=0.00, perplexity, 15KB] Can you break down why on average 400 K to build a condo unit in Canada?Short an
- 223. **26.09** [w_conc=0.00, apple-notes, 4KB] The Hard Truth about 2nd Brain: Rewind AI's & Consumer Adaptation
- 224. **26.08** [w_conc=0.00, perplexity, 24KB] What do people say entj and intj look like and appear outwardly, respectively  S
- 225. **26.06** [w_conc=0.00, perplexity, 25KB] Give me the gdp per capita (ppp and nominal) of these countries: Kenya Mexico, V
- 226. **26.04** [w_conc=0.00, perplexity, 27KB] I want to inquire into this commcerical property: https://www.realtor.ca/real-es
- 227. **26.02** [w_conc=0.00, perplexity, 8KB] what is the most powerful reasoning model out there right nowIntroverted Intuiti
- 228. **26.01** [w_conc=0.00, apple-notes, 4KB] Below are my notes for International Villages project I've been working on this 
- 229. **25.98** [w_conc=0.00, strategic-synthesis-2026-06-14, 2KB] strategic-synthesis-2026-06-14: 13. The honest critical assessment
- 230. **25.98** [w_conc=0.00, strategic-synthesis-2026-06-14, 2KB] strategic-insights: 13. The honest critical assessment

_(2388 additional low-score candidates omitted; see JSON for full list.)_
