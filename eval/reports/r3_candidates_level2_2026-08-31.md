# R3 Candidate Salience — Level 2 — 2026-08-31

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

## Scoring — Level 2 formula

```
score = Σ log(1 + in_degree(c))       ← weighted_concept (UNBOUNDED)
      + 3 · goal_overlap              ← 0-1
      + recency                       ← 0-1 (linear decay over 365d)
      + substance                     ← 0-1 (log(turns) or log(bytes))
      − noise_penalty                 ← 0 or 1 (title off-topic match)
```

`weighted_concept` sums `log(1+in-degree)` over concept slugs (min length 5, kebab-case) that appear in the source body with whole-word matching. In-degree = count of `[[slug]]` wikilinks pointing at each concept across the vault. Max weight in this run: **3.33** (highest-in-degree concept). A MIKAI-central source typically scores 5-15 concept units; an off-topic source scores 0.

Goal source: `~/.mikai/brain/GOALS.md` (10 goals). Concept vocabulary: 210 slugs with weight > 0.

## Top 30 candidates

| # | score | w_conc | goal | rec | subst | noise | kind | KB | turns | title |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 7.21 | 4.61 | 0.35 | 0.55 | 1.00 | 0.00 | perplexity | 98 | — | (Bot) Options Trading StrategiesVolatility arbitrage (vol ar |
| 2 | 6.36 | 3.69 | 0.39 | 0.55 | 0.96 | 0.00 | perplexity | 40 | — | What does an entj with low conscientiousness look like, does |
| 3 | 5.93 | 3.18 | 0.40 | 0.55 | 1.00 | 0.00 | perplexity | 52 | — | Expand on the ideas explored in MIKA/REMY TECH, what technol |
| 4 | 5.84 | 3.56 | 0.27 | 0.55 | 0.94 | 0.00 | perplexity | 36 | — | give me updates of nvda appl and tsla today in the newsHere' |
| 5 | 5.04 | 2.20 | 0.43 | 0.55 | 1.00 | 0.00 | perplexity | 77 | — | Can you explain this image with more science or information. |
| 6 | 4.70 | 3.18 | 0.17 | 0.55 | 0.46 | 0.00 | apple-notes | 4 | — | projects |
| 7 | 4.64 | 3.18 | 0.15 | 0.55 | 0.46 | 0.00 | apple-notes | 4 | — | Building moats beyond model improvement |
| 8 | 4.64 | 2.20 | 0.50 | 0.94 | 1.00 | 1.00 | thread | 953 | 329 | Weighted yoga for flexibility and alignment |
| 9 | 4.55 | 2.20 | 0.52 | 0.81 | 1.00 | 1.00 | thread | 371 | 84 | Dining room layout and color coordination strategy |
| 10 | 4.15 | 1.39 | 0.41 | 0.55 | 1.00 | 0.00 | perplexity | 49 | — | My Mentors: Based on my threads, conceptual inquiries, I wan |
| 11 | 4.06 | 2.20 | 0.34 | 0.82 | 1.00 | 1.00 | thread | 174 | 144 | Wind-resistant plants for apartment living |
| 12 | 3.97 | 2.20 | 0.17 | 0.55 | 0.70 | 0.00 | perplexity | 13 | — | How valuable is OCR data from social media. A lot i imagineY |
| 13 | 3.75 | 1.95 | 0.20 | 0.55 | 0.64 | 0.00 | perplexity | 10 | — | What is the core problem and core solution for international |
| 14 | 3.72 | 2.94 | 0.10 | 0.00 | 0.46 | 0.00 | apple-notes | 5 | — | #Ni |
| 15 | 3.60 | 2.20 | 0.06 | 0.55 | 0.69 | 0.00 | perplexity | 13 | — | How to roast peppers they are long peppers in the ovenRoast  |
| 16 | 3.58 | 1.61 | 0.18 | 0.55 | 0.86 | 0.00 | perplexity | 27 | — | I want to create a webapp tool that: allows you to search yo |
| 17 | 3.47 | 2.08 | 0.12 | 0.56 | 0.46 | 0.00 | apple-notes | 4 | — | MIKA projects synthesis Mar 25 |
| 18 | 3.28 | 1.95 | 0.14 | 0.55 | 0.38 | 0.00 | perplexity | 3 | — | “Based on everything you know about me from our full chat hi |
| 19 | 3.22 | 2.08 | 0.21 | 0.55 | 0.96 | 1.00 | perplexity | 40 | — | Our cat that we’ve had for three weeks now who’s peed for th |
| 20 | 3.14 | 1.39 | 0.14 | 0.55 | 0.77 | 0.00 | perplexity | 18 | — | I think with Tesla sales slumping in Europe and BYD becoming |
| 21 | 3.12 | 2.08 | 0.22 | 0.55 | 0.83 | 1.00 | perplexity | 24 | — | Is there such thing as our cats not wanting to come into me  |
| 22 | 3.02 | 1.39 | 0.14 | 0.55 | 0.65 | 0.00 | perplexity | 11 | — | What has accounted for qqq rising to new high in the last 3  |
| 23 | 2.98 | 1.61 | 0.12 | 0.55 | 0.47 | 0.00 | perplexity | 5 | — | https://www.wsj.com/tech/ai/yann-lecun-ai-meta-0058b13c  Tel |
| 24 | 2.90 | 2.20 | 0.08 | 0.00 | 0.46 | 0.00 | apple-notes | 5 | — | Germaine 2025 |
| 25 | 2.89 | 0.00 | 0.45 | 0.55 | 1.00 | 0.00 | perplexity | 68 | — | what is the profitability of 3d ocean farmingBased on the pr |
| 26 | 2.85 | 1.61 | 0.07 | 0.55 | 0.46 | 0.00 | claude | 4 | — | claude: Making AI invisible through personalized knowledge a |
| 27 | 2.85 | 1.61 | 0.07 | 0.55 | 0.46 | 0.00 | apple-notes | 4 | — | Making AI invisible through personalized knowledge architect |
| 28 | 2.82 | 2.08 | 0.01 | 0.53 | 0.16 | 0.00 | apple-notes | 0 | — | MIKAI Feature: The execution gap |
| 29 | 2.80 | 0.00 | 0.41 | 0.55 | 1.00 | 0.00 | perplexity | 51 | — | What happens in a society where all the brands become conglo |
| 30 | 2.79 | 2.08 | 0.17 | 0.55 | 0.67 | 1.00 | perplexity | 12 | — | Cna you do an analysis of the coffee commodities market? Wha |

### Top concept hits per candidate (top 15)

- **1.** (Bot) Options Trading StrategiesVolatility arbitrage (vol ar — `iron-condor` (1.61), `long-straddle` (1.61), `bull-call-spread` (1.39)
- **2.** What does an entj with low conscientiousness look like, does — `implementation-intentions` (2.08), `information-diet` (1.61)
- **3.** Expand on the ideas explored in MIKA/REMY TECH, what technol — `personal-intent-graph` (3.18)
- **4.** give me updates of nvda appl and tsla today in the newsHere' — `market-psychology` (1.95), `long-straddle` (1.61)
- **5.** Can you explain this image with more science or information. — `space-between` (2.20)
- **6.** projects — `personal-intent-graph` (3.18)
- **7.** Building moats beyond model improvement — `personal-intent-graph` (3.18)
- **8.** Weighted yoga for flexibility and alignment — `space-between` (2.20)
- **9.** Dining room layout and color coordination strategy — `space-between` (2.20)
- **10.** My Mentors: Based on my threads, conceptual inquiries, I wan — `mimetic-competition` (1.39)
- **11.** Wind-resistant plants for apartment living — `space-between` (2.20)
- **12.** How valuable is OCR data from social media. A lot i imagineY — `lost-in-the-middle` (2.20)
- **13.** What is the core problem and core solution for international — `third-place` (1.95)
- **14.** #Ni — `tenacious-joy` (2.94)
- **15.** How to roast peppers they are long peppers in the ovenRoast  — `space-between` (2.20)

## Recommended next batch (top 15)

- Total volume: **1907KB** across 15 sources
- Est. wall-clock: **~6min** at workers=8, **~50min** at workers=1 (assumes ~200s/source average)
- Would land as R3-2026-08-31-mikai-followup

| # | score | w_conc | title | KB | filename |
|---|---|---|---|---|---|
| 1 | 7.21 | 4.61 | (Bot) Options Trading StrategiesVolatility arbitrage (vol ar | 98 | `2026-03-19-bot-options-trading-strategiesvolatility-arbitrage-vol-arb-i-40937e.md` |
| 2 | 6.36 | 3.69 | What does an entj with low conscientiousness look like, does | 40 | `2026-03-19-what-does-an-entj-with-low-conscientiousness-look-like-does-42ce4e.md` |
| 3 | 5.93 | 3.18 | Expand on the ideas explored in MIKA/REMY TECH, what technol | 52 | `2026-03-19-expand-on-the-ideas-explored-in-mika-remy-tech-what-technolo-da8841.md` |
| 4 | 5.84 | 3.56 | give me updates of nvda appl and tsla today in the newsHere' | 36 | `2026-03-19-give-me-updates-of-nvda-appl-and-tsla-today-in-the-newshere-725656.md` |
| 5 | 5.04 | 2.20 | Can you explain this image with more science or information. | 77 | `2026-03-19-can-you-explain-this-image-with-more-science-or-information-ab9e4b.md` |
| 6 | 4.70 | 3.18 | projects | 4 | `2026-03-19-projects-700e65.md` |
| 7 | 4.64 | 3.18 | Building moats beyond model improvement | 4 | `2026-03-19-building-moats-beyond-model-improvement-5137ef.md` |
| 8 | 4.64 | 2.20 | Weighted yoga for flexibility and alignment | 953 | `2026-06-02-weighted-yoga-for-flexibility-and-alignment-83cccc.md` |
| 9 | 4.55 | 2.20 | Dining room layout and color coordination strategy | 371 | `2026-05-28-dining-room-layout-and-color-coordination-strategy-bd5f22.md` |
| 10 | 4.15 | 1.39 | My Mentors: Based on my threads, conceptual inquiries, I wan | 49 | `2026-03-19-my-mentors-based-on-my-threads-conceptual-inquiries-i-want-t-79f21b.md` |
| 11 | 4.06 | 2.20 | Wind-resistant plants for apartment living | 174 | `2026-04-03-wind-resistant-plants-for-apartment-living-e5bf8b.md` |
| 12 | 3.97 | 2.20 | How valuable is OCR data from social media. A lot i imagineY | 13 | `2026-03-19-how-valuable-is-ocr-data-from-social-media-a-lot-i-imagineyo-e87a25.md` |
| 13 | 3.75 | 1.95 | What is the core problem and core solution for international | 10 | `2026-03-19-what-is-the-core-problem-and-core-solution-for-international-375dd1.md` |
| 14 | 3.72 | 2.94 | #Ni | 5 | `2024-05-14-ni-092f60.md` |
| 15 | 3.60 | 2.20 | How to roast peppers they are long peppers in the ovenRoast  | 13 | `2026-03-19-how-to-roast-peppers-they-are-long-peppers-in-the-ovenroast-b29968.md` |

## Appendix — next 200 candidates (rank 31+, brief)

- 31. **2.78** [w_conc=0.00, perplexity, 97KB] EC Rare Book market research: What is the value of the rare books market compare
- 32. **2.77** [w_conc=0.00, perplexity, 45KB] what are the capabilities of n8n and open claw. Contextualize it on a high level
- 33. **2.76** [w_conc=1.61, perplexity, 4KB] are you able to find me many different visual representations in video games tha
- 34. **2.75** [w_conc=0.00, perplexity, 55KB] Chip war and Geopolitical strategy of USA vs CHINA   what is included in the pro
- 35. **2.75** [w_conc=0.00, perplexity, 74KB] Kenyan fruits: Can I wash fruits at a luxury apartments in Nairobi with the tapw
- 36. **2.68** [w_conc=1.39, apple-notes, 4KB] Building credibility for a Google acquisition
- 37. **2.68** [w_conc=1.95, thread, 8KB] Why restaurants fail during recessions
- 38. **2.66** [w_conc=0.00, perplexity, 97KB] assessed property value vs fair market value?Assessed property value and fair ma
- 39. **2.64** [w_conc=1.61, perplexity, 2KB] maket neutral options trading strategies vs news based tech options strategiesMa
- 40. **2.64** [w_conc=1.61, apple-notes, 2KB] MIKAI Feature: Ai directed content
- 41. **2.63** [w_conc=0.00, perplexity, 44KB] How do people use Ni in their first function, and what about their 2nd. Make sur
- 42. **2.61** [w_conc=2.08, perplexity, 10KB] How well are cats able to be trained to listen to voice command commands we are 
- 43. **2.57** [w_conc=1.39, perplexity, 5KB] If I wanted to buy options for a slow decline of Tesla over the next couple of m
- 44. **2.57** [w_conc=0.00, perplexity, 34KB] I want to compare https://www.wikiwand.com/en/articles/Fran%C3%A7ois_Pinault wit
- 45. **2.56** [w_conc=0.00, apple-notes, 24KB] apple-notes::Feb 2025 - David and the Dao
- 46. **2.54** [w_conc=0.00, perplexity, 55KB] Entj 7w8 vs 8w7. I want to know which one I amTo determine whether you are an EN
- 47. **2.53** [w_conc=0.00, perplexity, 34KB] can you analyze vancouver brand aritzia and their expansion over the last few ye
- 48. **2.53** [w_conc=0.00, perplexity, 42KB] Pull up Alex Karp’s phd thesis and explain the concepts around itAlex Karp’s PhD
- 49. **2.51** [w_conc=0.00, perplexity, 40KB] semis vs software portfolio strategy, why is there software aversion right now?I
- 50. **2.51** [w_conc=0.00, perplexity, 35KB] I don’t understand the difference between a brand and business then, it’s seems 
- 51. **2.50** [w_conc=2.08, apple-notes, 2KB] Leadership and Self Growth
- 52. **2.50** [w_conc=0.00, perplexity, 41KB] I want to fill international village in chinatown with budding entrepreneurs fro
- 53. **2.46** [w_conc=0.00, perplexity, 32KB] what to enfj's day dream aboutENFJs most often daydream about guiding or support
- 54. **2.45** [w_conc=0.00, perplexity, 41KB] what do Yanis Varoufakis and joseph stiglitz have in common, how are they differ
- 55. **2.44** [w_conc=0.00, perplexity, 40KB] I want to understand what kind of economist I am. I'm looking at joseph stiglitz
- 56. **2.43** [w_conc=0.00, perplexity, 32KB] what do the people of south korea, yantai, qingdao and dalian have in commonPeop
- 57. **2.43** [w_conc=0.00, perplexity, 32KB] i want a comprehensive understanding of why countries want or not want foreign d
- 58. **2.42** [w_conc=2.08, apple-notes, 1KB] Man’s unempowerment
- 59. **2.42** [w_conc=0.00, perplexity, 40KB] Ha-Joon Chang, Byung-Chul Han Sandwich there was a thread that talked about how 
- 60. **2.39** [w_conc=0.00, perplexity, 45KB] For an entj, describe relationships with esfp vs enfpAs an ENTJ, your relationsh
- 61. **2.39** [w_conc=0.00, perplexity, 27KB] What does the bible say about the ideal wifeThe Bible’s vision of the ideal wife
- 62. **2.38** [w_conc=0.00, perplexity, 40KB] What were the rewards for bitcoin mining from 2012-2016Introverted-intuition tak
- 63. **2.37** [w_conc=1.61, apple-notes, 4KB] ——Energy Trading
- 64. **2.36** [w_conc=0.00, thread, 23KB] Unreciprocated effort and emotional withdrawal patterns
- 65. **2.36** [w_conc=0.00, perplexity, 28KB] Rewriting the Rules of the American Economy“Rewriting the Rules of the American 
- 66. **2.36** [w_conc=0.00, perplexity, 33KB] Using first principles I want to find out why housing costs are so expensive. We
- 67. **2.35** [w_conc=0.00, thread, 122KB] Determining ENTJ vs INTJ personality type
- 68. **2.34** [w_conc=0.00, perplexity, 27KB] tell me many variants of loss leader strategy across many industries. Bridge the
- 69. **2.33** [w_conc=0.00, perplexity, 27KB] a fully transcend entj will act more like a?A fully realized, transcendent ENTJ 
- 70. **2.33** [w_conc=0.00, perplexity, 45KB] I want to put on a bear call for tech stocks related to ai and ai compute, and I
- 71. **2.33** [w_conc=2.08, apple-notes, 0KB] Episode 6
- 72. **2.33** [w_conc=2.20, perplexity, 3KB] How high are normal dining chairs from the ground the seat partMost standard din
- 73. **2.32** [w_conc=0.00, perplexity, 38KB] can you give me an overview of henderson development in canada as well as their 
- 74. **2.32** [w_conc=0.00, perplexity, 85KB] what is the first home buyers account in canadaThe First Home Savings Account (F
- 75. **2.30** [w_conc=0.00, perplexity, 36KB] Are there any examples of an all ai news YouTube or Spotify podcast?Yes, there a
- 76. **2.29** [w_conc=0.00, thread, 59KB] Crypto transfer phone scam
- 77. **2.29** [w_conc=0.00, perplexity, 22KB] Translate the following Ni whitepaper using Si and Te language (from definitions
- 78. **2.29** [w_conc=0.00, perplexity, 32KB] I want to be with people that are slightly critical about the world and want it 
- 79. **2.28** [w_conc=0.00, thread, 39KB] Rent vs. buy analysis for Vancouver
- 80. **2.28** [w_conc=2.08, perplexity, 5KB] we got a new cat tree from costco and we thought our cat would love it but he is
- 81. **2.27** [w_conc=0.00, perplexity, 31KB] I want to create a business service that acts as broker for leases, and interior
- 82. **2.26** [w_conc=0.00, perplexity, 58KB] I sit a lot during the day, I vape, and game on the computer a couple hours a da
- 83. **2.25** [w_conc=0.00, perplexity, 39KB] What are some of the rarest mines in the world for components for high techIntro
- 84. **2.25** [w_conc=0.00, perplexity, 34KB] Health benefits of digestifsDigestifs, alcoholic beverages traditionally served 
- 85. **2.24** [w_conc=0.00, perplexity, 29KB] Mark and I close university friends and have also been roommates after college t
- 86. **2.24** [w_conc=0.00, perplexity, 29KB] Anthropic open ai, and perplexity valuation,   What are their revenues?Here are 
- 87. **2.24** [w_conc=0.00, perplexity, 35KB] i'm being interview for a job as a starting engineer at a ai tech startup in can
- 88. **2.23** [w_conc=0.00, perplexity, 23KB] David defeated the philistines with a stone and momentumDavid defeated Goliath b
- 89. **2.22** [w_conc=0.00, perplexity, 44KB] I’m doing a 36 hour fast to achieve autophagy and I want to understand how to be
- 90. **2.21** [w_conc=0.00, perplexity, 65KB] I want to hook up my voice memos so that the automatically get inserted into rea
- 91. **2.21** [w_conc=0.00, perplexity, 49KB] where does qatar airways rank in qualitty and comfortQatar Airways ranks #1 in t
- 92. **2.21** [w_conc=0.00, perplexity, 33KB] i want to take my friend to new york and show him very interesting experiences? 
- 93. **2.21** [w_conc=0.00, thread, 36KB] 💬 I feel pressure around my orbi…
- 94. **2.19** [w_conc=0.00, perplexity, 39KB] I want to understand modern and cutting edge relationships between the autonomic
- 95. **2.19** [w_conc=0.00, apple-notes, 11KB] apple-notes::June 2026
- 96. **2.19** [w_conc=0.00, perplexity, 36KB] what is the weight range for a 22cm black domestic shorthairFor an adult domesti
- 97. **2.18** [w_conc=0.00, perplexity, 31KB] Chochu trading co.  Beyond goods: how to circumvent tariffs If we import Chinese
- 98. **2.18** [w_conc=0.00, apple-notes, 11KB] apple-notes::June 2026
- 99. **2.17** [w_conc=0.00, perplexity, 34KB] Can I self inject this?Self-injecting GHK-Cu (Copper Peptide) purchased online i
- 100. **2.17** [w_conc=0.00, perplexity, 20KB] vancouver from early 2000s to 2021 faced unprecendented growth in their housing 
- 101. **2.16** [w_conc=0.00, perplexity, 25KB] Give me the gdp per capita (ppp and nominal) of these countries: Kenya Mexico, V
- 102. **2.15** [w_conc=0.00, perplexity, 24KB] I was caught smoking outside the Nairobi airport and a police officer want to ta
- 103. **2.15** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 104. **2.12** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 105. **2.11** [w_conc=0.00, thread, 19KB] Low voltage electrical companies in BC for Patrick
- 106. **2.10** [w_conc=0.00, apple-notes, 11KB] apple-notes::June 2026
- 107. **2.10** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 108. **2.10** [w_conc=0.00, perplexity, 27KB] are there any other companies like scale ai but at lower valuations? can you giv
- 109. **2.09** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 110. **2.09** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 111. **2.09** [w_conc=0.00, thread, 326KB] Building a championship roster around Luka in Vancouver
- 112. **2.09** [w_conc=0.00, perplexity, 29KB] How much do medical offices like a family doctors office make? What about physio
- 113. **2.08** [w_conc=0.00, perplexity, 21KB] Can you read the transcript of this video: https://www.youtube.com/watch?v=_mwm6
- 114. **2.08** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 115. **2.06** [w_conc=0.00, perplexity, 31KB] azaleic acid what kind of skin treatment is this considered?Azelaic acid is cons
- 116. **2.06** [w_conc=0.00, perplexity, 20KB] From everything we have discussed in this space called International Village, gi
- 117. **2.06** [w_conc=0.00, apple-notes, 10KB] apple-notes::June 2026
- 118. **2.06** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 119. **2.06** [w_conc=0.00, perplexity, 16KB] is weride a chinese company? What are the prices for their robo sweepers and sim
- 120. **2.06** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 121. **2.06** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 122. **2.06** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 123. **2.05** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 124. **2.05** [w_conc=0.00, perplexity, 21KB] Can you explain all the companies in the supply chain ecosystem for Ai, not the 
- 125. **2.04** [w_conc=0.00, perplexity, 31KB] i want to fill international village mall in chinatown, I'm considering many opt
- 126. **2.04** [w_conc=0.00, perplexity, 37KB] How to get commercial real estate licence in bc the fastestTo get a commercial r
- 127. **2.04** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 128. **2.04** [w_conc=0.00, perplexity, 62KB] Who are the characters from reborn rich based onCore Insight: The Soonyang Group
- 129. **2.04** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 130. **2.03** [w_conc=0.00, perplexity, 26KB] what accounted for the dip in the markets on friday? Give me hedge fund level an
- 131. **2.03** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 132. **2.03** [w_conc=0.00, perplexity, 24KB] Toyota hybrid suv that is the highest ratedThe highest-rated Toyota hybrid SUV r
- 133. **2.03** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 134. **2.03** [w_conc=0.00, thread, 109KB] Sphagnum moss vs peat moss for DIY Monstera poles
- 135. **2.03** [w_conc=0.00, perplexity, 22KB] I keep asking this structural and economic question in my threads, but why is th
- 136. **2.03** [w_conc=0.00, perplexity, 15KB] Tell me about the tax-free zone in Songdo, Incheon, Korea. What counts as R&D? S
- 137. **2.02** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 138. **2.02** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 139. **2.02** [w_conc=0.00, thread, 211KB] Identifying an Alocasia plant
- 140. **2.02** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 141. **2.02** [w_conc=0.00, perplexity, 24KB] What do people say entj and intj look like and appear outwardly, respectively  S
- 142. **2.01** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 143. **2.01** [w_conc=0.00, perplexity, 29KB] can you do a case study on instant financial https://www.instant.co/ and how the
- 144. **2.01** [w_conc=0.00, perplexity, 23KB] Below is the problem my engineering team is trying to solve. Give me a high leve
- 145. **2.01** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 146. **2.01** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 147. **2.01** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 148. **2.01** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 149. **2.01** [w_conc=0.00, thread, 41KB] Anarchist digital spaces beyond Bitcoin
- 150. **2.01** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 151. **2.01** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 152. **2.01** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 153. **2.01** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 154. **2.00** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 155. **2.00** [w_conc=0.00, perplexity, 16KB] Describe the lessons and insights that Huozhi Zhuan wrote about commerce and the
- 156. **2.00** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 157. **2.00** [w_conc=0.00, apple-notes, 9KB] apple-notes::June 2026
- 158. **2.00** [w_conc=0.00, apple-notes, 7KB] apple-notes::July 2026 - Small Empires
- 159. **2.00** [w_conc=0.00, perplexity, 21KB] what do kenyans think of asian tourists in their country?Kenyans generally view 
- 160. **1.99** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 161. **1.99** [w_conc=0.00, perplexity, 18KB] For tech jobs, typically the big 5 was considered optimal. I want the next up an
- 162. **1.99** [w_conc=0.00, perplexity, 31KB] how far is 300000 km300,000 km is 186,411 miles—about 4.6 times the distance aro
- 163. **1.98** [w_conc=0.00, perplexity, 13KB] wealth management firm and industry overviewIntroverted Intuition – Key Insight 
- 164. **1.98** [w_conc=0.00, perplexity, 25KB] there was a group that my family bought insurance from 10 years ago called oikos
- 165. **1.98** [w_conc=0.00, perplexity, 20KB] https://www.youtube.com/watch?v=bfUOPDOLHvE  explain the pitfalls of private equ
- 166. **1.98** [w_conc=0.00, perplexity, 27KB] I want to inquire into this commcerical property: https://www.realtor.ca/real-es
- 167. **1.97** [w_conc=0.00, perplexity, 20KB] In sports, and with my friends, I seem to alway be encouraging, and give thought
- 168. **1.96** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 169. **1.96** [w_conc=0.00, perplexity, 22KB] according to their own blog, their skincare cream 2.0 is the best [https://regim
- 170. **1.96** [w_conc=0.00, perplexity, 18KB] the apartments by international village mall and roger's arena, is that area cal
- 171. **1.96** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 172. **1.95** [w_conc=0.00, perplexity, 16KB] never split the difference, book on negotiation and communication“Never Split th
- 173. **1.95** [w_conc=0.00, perplexity, 27KB] what is a 40 pyeong apartment in songdo costA typical 40 pyeong (about 132 m²) a
- 174. **1.94** [w_conc=0.00, perplexity, 13KB] There’s an social principle where if the size of a community grows to over 500, 
- 175. **1.94** [w_conc=0.00, perplexity, 15KB] We know a start of founder that started his original business in 2012 and had fa
- 176. **1.94** [w_conc=0.00, perplexity, 17KB] how much does a used container cost so I can grow mushrooms in them, what is the
- 177. **1.94** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 178. **1.94** [w_conc=0.00, perplexity, 13KB] what is a split-screen cycle in economicsA split-screen cycle in economics refer
- 179. **1.93** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 180. **1.93** [w_conc=0.00, perplexity, 17KB] Wha are ai agent swarmsAI agent swarms are groups of specialized AI agents that 
- 181. **1.93** [w_conc=0.00, perplexity, 16KB] What startups have come out of ihub that are significant? What startups are ther
- 182. **1.93** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 183. **1.93** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 184. **1.93** [w_conc=0.00, apple-notes, 6KB] apple-notes::July 2026 - Small Empires
- 185. **1.92** [w_conc=0.00, perplexity, 16KB] what is the definition of ditzy. can you analyze in it the context of a socionic
- 186. **1.92** [w_conc=0.00, perplexity, 15KB] explain derek Cabrera dsrp method in a way that I can understand fully the conce
- 187. **1.92** [w_conc=0.00, perplexity, 19KB] In the Vancouver market, retail and f&b are struggling because of their low marg
- 188. **1.92** [w_conc=0.00, perplexity, 17KB] In planet coaster, what do you want to set ticket prices atSet ride tickets roug
- 189. **1.92** [w_conc=0.00, perplexity, 22KB] Fed chair update and what it means for the market, why did trump want Jerome Pow
- 190. **1.91** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 191. **1.91** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026 - Small Empires
- 192. **1.91** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026
- 193. **1.91** [w_conc=0.00, perplexity, 25KB] What is the best internet source for food and beverage scene in NairobiHere are 
- 194. **1.91** [w_conc=0.00, perplexity, 17KB] Forget a recession. What Canadians are living through is worse. can you explain 
- 195. **1.90** [w_conc=0.00, perplexity, 11KB] Simulation Modelling: personality, business physics ~~ movement of people within
- 196. **1.90** [w_conc=0.00, perplexity, 14KB] The first business that I want to build out for in international villages mall i
- 197. **1.89** [w_conc=0.00, perplexity, 23KB] Best exercises to correct forward head posture.   I believe that pelvic tilt, ri
- 198. **1.89** [w_conc=0.00, perplexity, 25KB] what do you call income or profit in a fund after taxes, tax deductions are take
- 199. **1.88** [w_conc=0.00, perplexity, 17KB] how did bob rennie start his firm, what was the startBob Rennie started his firm
- 200. **1.88** [w_conc=1.10, apple-notes, 0KB] 2026 trading
- 201. **1.87** [w_conc=0.00, apple-notes, 5KB] apple-notes::July 2026
- 202. **1.87** [w_conc=0.00, perplexity, 15KB] https://youtu.be/frqiUkjxAOE?si=rlTjy7QvhXn4gS_H  Can yo summarize this videoChr
- 203. **1.87** [w_conc=0.00, perplexity, 19KB] What happening in the market today particularly in the tech sector, and you look
- 204. **1.86** [w_conc=0.00, apple-notes, 7KB] apple-notes::June 2026
- 205. **1.86** [w_conc=0.00, apple-notes, 7KB] apple-notes::June 2026
- 206. **1.86** [w_conc=0.00, apple-notes, 7KB] apple-notes::June 2026
- 207. **1.86** [w_conc=0.00, perplexity, 23KB] We are going into manhatten after a black pink concert and we want a unique and 
- 208. **1.86** [w_conc=0.00, perplexity, 14KB] Who is the content creator or social media head that is the best at assessing ne
- 209. **1.85** [w_conc=0.00, perplexity, 17KB] average yearly salary chart 1970 to nowIntroverted Intuition – Most Important Po
- 210. **1.85** [w_conc=0.00, thread, 12KB] Steve Jobs' prioritization meeting story
- 211. **1.85** [w_conc=0.00, apple-notes, 7KB] apple-notes::June 2026
- 212. **1.85** [w_conc=0.00, perplexity, 17KB] Can you take this photo of a signature and turn it into a image with just the si
- 213. **1.85** [w_conc=0.00, apple-notes, 7KB] apple-notes::June 2026
- 214. **1.85** [w_conc=0.00, apple-notes, 7KB] apple-notes::June 2026
- 215. **1.85** [w_conc=0.00, apple-notes, 7KB] apple-notes::June 2026
- 216. **1.84** [w_conc=0.00, apple-notes, 7KB] apple-notes::June 2026
- 217. **1.84** [w_conc=0.00, apple-notes, 7KB] apple-notes::June 2026
- 218. **1.84** [w_conc=0.00, perplexity, 15KB] i like Ha-Joon Chang, are there any other like him, who would be the best from p
- 219. **1.84** [w_conc=0.00, perplexity, 25KB] The stock markets grows on average of 8% per year, but the trend is that is has 
- 220. **1.84** [w_conc=0.00, apple-notes, 7KB] apple-notes::June 2026
- 221. **1.84** [w_conc=0.00, apple-notes, 7KB] apple-notes::June 2026
- 222. **1.84** [w_conc=0.00, apple-notes, 7KB] apple-notes::June 2026
- 223. **1.84** [w_conc=0.00, perplexity, 20KB] What is the price of a new Tesla right now for a model three what is the best op
- 224. **1.83** [w_conc=0.00, perplexity, 18KB] does restoration hardware offer good value for their price?Restoration Hardware 
- 225. **1.83** [w_conc=0.00, perplexity, 18KB] Are you able to understand jungian cognitive functions and its evolution into so
- 226. **1.83** [w_conc=1.61, apple-notes, 0KB] Yes looking forward to old or higher gears are important and good…
- 227. **1.83** [w_conc=0.00, perplexity, 23KB] I want to know bc labour laws. Someone we are representing as a consultant accid
- 228. **1.82** [w_conc=0.00, perplexity, 10KB] If AGI is for sure coming, explain the landscape or topography of AGI as an anal
- 229. **1.82** [w_conc=0.00, perplexity, 23KB] It’s not creditors, I have my business listed as a sole proprietorship and I owe
- 230. **1.82** [w_conc=0.00, perplexity, 20KB] what percentage of a homes value in bc is property tax?In BC, property tax on a 

_(2388 additional low-score candidates omitted; see JSON for full list.)_
