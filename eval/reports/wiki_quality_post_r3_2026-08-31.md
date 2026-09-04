# MIKAI Wiki Quality Report — Post-R3 (2026-08-31)

Two-vault quality assessment after R3 ingest completion.

| vault | pages | in-degree entries |
|---|---|---|
| parallel | 663 | 558 |
| serial | 714 | 629 |

## Verdict

**State of the wiki**: Both vaults are functionally usable substrates but carry substantial fragmentation and orphan debt. Parallel has 663 pages with 16% orphan rate and 5% broken wikilinks; serial has 714 pages with 12% orphan rate and 3% broken wikilinks. Concept fragmentation (semantically-adjacent slug pairs) sits at **319 pairs (parallel)** vs **609 pairs (serial)** — the 262-pair problem from R1+R2 has grown substantially. Neither vault should ship to production without a dedup pass.

**Top-3 defects surfaced (aggregate across samples):**
- **stub**: 16 occurrences in the sampled set
- **unresolved_related**: 13 occurrences in the sampled set
- **unresolved_wl**: 10 occurrences in the sampled set

**Recommendation**: **Ship parallel.** Lower fragmentation + comparable orphan rate.


## Vault-wide metrics

### Broken wikilinks (references pointing to non-existent pages)

| vault | total wikilinks | unresolved | ratio |
|---|---|---|---|
| parallel | 2787 | 144 | 5.2% |
| serial | 2896 | 100 | 3.5% |

### Fragmentation (semantically-adjacent concept pairs)

- **parallel**: 322 concept pages, 319 adjacent pairs
- **serial**: 388 concept pages, 609 adjacent pairs

**parallel — first 15 fragmentation pairs:**

  - `action-friction` ↔ `action-rubric` (shared:action)
  - `action-friction` ↔ `action-tier-hierarchy` (shared:action)
  - `action-friction` ↔ `configuration-friction` (shared:friction)
  - `action-friction` ↔ `consequence-weighted-action-gate` (shared:action)
  - `action-friction` ↔ `unified-action-inbox` (shared:action)
  - `action-rubric` ↔ `action-tier-hierarchy` (shared:action)
  - `action-rubric` ↔ `consequence-weighted-action-gate` (shared:action)
  - `action-rubric` ↔ `unified-action-inbox` (shared:action)
  - `action-tier-hierarchy` ↔ `consequence-weighted-action-gate` (shared:action)
  - `action-tier-hierarchy` ↔ `unified-action-inbox` (shared:action)
  - `adhd-conscientiousness-overlap` ↔ `conscientiousness-complementarity` (shared:conscientiousness)
  - `agency-model-for-work` ↔ `asset-light-trading-model` (shared:model)
  - `agency-model-for-work` ↔ `time-model` (shared:model)
  - `agency-model-for-work` ↔ `vertical-integration-counter-model` (shared:model)
  - `agency-model-for-work` ↔ `viable-system-model` (shared:model)
  _(304 more; see JSON for full list)_

**serial — first 15 fragmentation pairs:**

  - `act-r-base-level-activation` ↔ `species-level-telos` (shared:level)
  - `act-r-base-level-activation` ↔ `spreading-activation` (shared:activation)
  - `act-r-base-level-activation` ↔ `token-level-scheduling` (shared:level)
  - `action-friction` ↔ `action-tier-reversibility` (shared:action)
  - `action-friction` ↔ `consequence-weighted-action-gate` (shared:action)
  - `action-friction` ↔ `three-action-tiers` (shared:action)
  - `action-friction` ↔ `unified-action-inbox` (shared:action)
  - `action-tier-reversibility` ↔ `consequence-weighted-action-gate` (shared:action)
  - `action-tier-reversibility` ↔ `three-action-tiers` (shared:action)
  - `action-tier-reversibility` ↔ `unified-action-inbox` (shared:action)
  - `activity-vocabulary` ↔ `epistemic-edge-vocabulary` (shared:vocabulary)
  - `addiction-vs-passion` ↔ `dreams-as-addiction` (shared:addiction)
  - `adhd-conscientiousness-overlap` ↔ `conscientiousness-facets` (shared:conscientiousness)
  - `adhd-conscientiousness-overlap` ↔ `low-conscientiousness-entj` (shared:conscientiousness)
  - `adhd-conscientiousness-overlap` ↔ `partner-conscientiousness-complementarity` (shared:conscientiousness)
  _(594 more; see JSON for full list)_

### Orphan pages (zero incoming wikilinks)

| vault | orphan count | % of vault |
|---|---|---|
| parallel | 105 | 15.8% |
| serial | 85 | 11.9% |

### Page-type routing collisions (same slug in multiple subdirs)

- **parallel**: 0 collisions
- **serial**: 0 collisions

### Top-10 most central pages (highest in-degree)

**parallel:**
  - 66× `entities/mikai`
  - 41× `entities/noonchi`
  - 34× `concepts/sumimasen`
  - 27× `concepts/personal-intent-graph`
  - 27× `concepts/attention-as-path-determinant`
  - 22× `concepts/information-asymmetry-north-star`
  - 20× `concepts/value-creation-vs-impact-creation`
  - 19× `goals/career-synthesis-finance-ai`
  - 19× `entities/germaine`
  - 18× `entities/openclaw`

**serial:**
  - 50× `concepts/imperfect-forward-motion`
  - 37× `concepts/personal-intent-graph`
  - 31× `entities/mikai`
  - 26× `entities/noonchi`
  - 23× `concepts/love-first-principle`
  - 19× `concepts/fantasy-vs-ideality`
  - 18× `entities/ray-dalio`
  - 18× `concepts/wave-substrate-split`
  - 16× `concepts/event-sourcing-for-intent-graph`
  - 16× `concepts/iphone-convergence-thesis`

### Non-English content (body >5% non-ASCII)

- **parallel**: 0 pages
- **serial**: 1 pages
  - 5.6% `entities/hansol-group`

### Frontmatter field consistency (fraction of pages with each field, by type)

**parallel:**

| subdir | pages | type | title | created | updated | tags | related | sources |
|---|---|---|---|---|---|---|---|---|
| concepts | 321 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| entities | 138 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| sources | 76 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| queries | 43 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| journal | 28 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| wisdom | 18 | 100% | 89% | 100% | 100% | 100% | 100% | 100% |
| goals | 16 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| habits | 4 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| reflections | 2 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| synthesis | 5 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| comparisons | 12 | 42% | 42% | 42% | 42% | 42% | 42% | 42% |

**serial:**

| subdir | pages | type | title | created | updated | tags | related | sources |
|---|---|---|---|---|---|---|---|---|
| concepts | 387 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| entities | 157 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| sources | 76 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| queries | 43 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| journal | 4 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| wisdom | 15 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| goals | 10 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| habits | 1 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| synthesis | 5 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| comparisons | 16 | 56% | 56% | 56% | 56% | 56% | 56% | 56% |

### Cross-vault differences (pages unique to one vault)

- Pages in both vaults: **306**
- Only in parallel: **357**
- Only in serial: **408**

## Sample-based per-page inspection

Per subdir: 3 random pages, 3 top-in-degree, 3 top-recent-mtime.

### parallel vault

#### concepts

**parallel/concepts/`surplus-allocation`** (random)
  - words=299 | h2=4 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=5 | related=9 | sources=1
  - ✓ clean

**parallel/concepts/`strict-intervention-contract`** (random)
  - words=402 | h2=5 | wikilinks=7 (1 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=4 | related=5 | sources=1
  - **DEFECTS**: unresolved_related:1

**parallel/concepts/`oligopoly-stagnation`** (random)
  - words=285 | h2=4 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=5 | related=8 | sources=1
  - ✓ clean

**parallel/concepts/`noonchi`** (top_indeg)
  - words=228 | h2=4 | wikilinks=3 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=6 | related=4 | sources=1
  - ✓ clean

**parallel/concepts/`sumimasen`** (top_indeg)
  - words=264 | h2=3 | wikilinks=5 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=5 | related=6 | sources=1
  - ✓ clean

**parallel/concepts/`personal-intent-graph`** (top_indeg)
  - words=237 | h2=3 | wikilinks=7 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=5 | related=8 | sources=1
  - ✓ clean

**parallel/concepts/`fitness-media-evaluation-filter`** (top_mtime)
  - words=279 | h2=2 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=5 | related=3 | sources=1
  - ✓ clean

**parallel/concepts/`axial-elongation`** (top_mtime)
  - words=273 | h2=4 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=5 | related=3 | sources=1
  - ✓ clean

**parallel/concepts/`thoracic-outlet-syndrome`** (top_mtime)
  - words=356 | h2=4 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=7 | related=3 | sources=1
  - ✓ clean


#### entities

**parallel/entities/`vannevar-bush`** (random)
  - words=110 | h2=1 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=4 | related=5 | sources=1
  - ✓ clean

**parallel/entities/`claude-mpm`** (random)
  - words=188 | h2=3 | wikilinks=5 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=5 | related=6 | sources=1
  - ✓ clean

**parallel/entities/`aegaeon`** (random)
  - words=278 | h2=4 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=5 | related=5 | sources=1
  - ✓ clean

**parallel/entities/`mikai`** (top_indeg)
  - words=1334 | h2=16 | wikilinks=26 (4 unresolved) | quotes=1 (attr=0)
  - fm: type=entity | tags=17 | related=39 | sources=4
  - **DEFECTS**: unresolved_related:10

**parallel/entities/`noonchi`** (top_indeg)
  - words=228 | h2=4 | wikilinks=3 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=6 | related=4 | sources=1
  - ✓ clean

**parallel/entities/`germaine`** (top_indeg)
  - words=423 | h2=5 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=3 | related=4 | sources=2
  - ✓ clean

**parallel/entities/`coach-q-wiley`** (top_mtime)
  - words=110 | h2=2 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=4 | related=3 | sources=1
  - ✓ clean

**parallel/entities/`keith-baar`** (top_mtime)
  - words=242 | h2=3 | wikilinks=3 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=5 | related=3 | sources=1
  - ✓ clean

**parallel/entities/`aegaeon`** (top_mtime)
  - words=278 | h2=4 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=5 | related=5 | sources=1
  - ✓ clean


#### sources

**parallel/sources/`2026-01-08-jan-2026-5604c3`** (random)
  - words=694 | h2=8 | wikilinks=10 (0 unresolved) | quotes=4 (attr=0)
  - fm: type=source | tags=8 | related=14 | sources=1
  - **DEFECTS**: truncation_marker:TRUNCATED

**parallel/sources/`2022-08-10-august-2022-a55fa3`** (random)
  - words=478 | h2=5 | wikilinks=3 (1 unresolved) | quotes=3 (attr=0)
  - fm: type=source | tags=6 | related=2 | sources=1
  - **DEFECTS**: unresolved_wl:1/3

**parallel/sources/`2023-05-04-may-2023-af1a10`** (random)
  - words=250 | h2=3 | wikilinks=7 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=4 | related=6 | sources=1
  - ✓ clean

**parallel/sources/`2025-05-13-may-2025-39cfa4`** (top_indeg)
  - words=454 | h2=8 | wikilinks=9 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=7 | related=10 | sources=1
  - ✓ clean

**parallel/sources/`2023-10-09-october-2023-18e6ee`** (top_indeg)
  - words=575 | h2=6 | wikilinks=8 (0 unresolved) | quotes=5 (attr=0)
  - fm: type=source | tags=7 | related=8 | sources=1
  - ✓ clean

**parallel/sources/`2025-03-02-march-2025-35500f`** (top_indeg)
  - words=354 | h2=2 | wikilinks=12 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=9 | related=9 | sources=1
  - ✓ clean

**parallel/sources/`2026-06-02-weighted-yoga-for-flexibility-and-alignment-83cccc`** (top_mtime)
  - words=1395 | h2=7 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=11 | related=12 | sources=1
  - ✓ clean

**parallel/sources/`2026-03-19-chip-war-and-geopolitical-strategy-of-usa-vs-china-what-is-i-de13df`** (top_mtime)
  - words=774 | h2=6 | wikilinks=22 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=6 | related=14 | sources=1
  - ✓ clean

**parallel/sources/`2026-05-28-dining-room-layout-and-color-coordination-strategy-bd5f22`** (top_mtime)
  - words=1631 | h2=14 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=6 | related=15 | sources=1
  - **DEFECTS**: unresolved_related:2


#### queries

**parallel/queries/`when-should-ea-feed-push-vs-surface`** (random)
  - words=266 | h2=3 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=6 | related=4 | sources=1
  - ✓ clean

**parallel/queries/`why-no-inflation-post-2009`** (random)
  - words=257 | h2=5 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=6 | related=3 | sources=1
  - ✓ clean

**parallel/queries/`if-anthropic-ships-personalization-what-narrows-mikai`** (random)
  - words=226 | h2=3 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=5 | related=6 | sources=1
  - ✓ clean

**parallel/queries/`can-ai-fix-public-information-quality`** (top_indeg)
  - words=279 | h2=6 | wikilinks=3 (1 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=6 | related=2 | sources=1
  - **DEFECTS**: unresolved_related:1, unresolved_wl:1/3

**parallel/queries/`how-to-channel-restlessness-without-scattering`** (top_indeg)
  - words=284 | h2=5 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=7 | related=4 | sources=1
  - ✓ clean

**parallel/queries/`what-is-ai-infrastructure-topography`** (top_indeg)
  - words=153 | h2=3 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=7 | related=1 | sources=1
  - ✓ clean

**parallel/queries/`which-capitalism-phase-comes-after-financialisation`** (top_mtime)
  - words=407 | h2=5 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=5 | related=9 | sources=1
  - ✓ clean

**parallel/queries/`does-conglomerate-roll-up-always-suppress-innovation`** (top_mtime)
  - words=296 | h2=5 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=4 | related=5 | sources=1
  - ✓ clean

**parallel/queries/`is-technofeudalism-a-new-system-or-extreme-capitalism`** (top_mtime)
  - words=419 | h2=5 | wikilinks=4 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=5 | related=10 | sources=1
  - ✓ clean


#### journal

**parallel/journal/`2023-10-30`** (random)
  - words=153 | h2=0 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=journal | tags=5 | related=3 | sources=1
  - ✓ clean

**parallel/journal/`2026-07-03`** (random)
  - words=230 | h2=0 | wikilinks=4 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=journal | tags=5 | related=11 | sources=1
  - ✓ clean

**parallel/journal/`2025-03-02`** (random)
  - words=422 | h2=4 | wikilinks=6 (0 unresolved) | quotes=2 (attr=0)
  - fm: type=journal | tags=8 | related=6 | sources=1
  - ✓ clean

**parallel/journal/`2026-03-19`** (top_indeg)
  - words=304 | h2=4 | wikilinks=4 (0 unresolved) | quotes=1 (attr=0)
  - fm: type=journal | tags=6 | related=4 | sources=1
  - ✓ clean

**parallel/journal/`2024-07-26`** (top_indeg)
  - words=188 | h2=0 | wikilinks=5 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=journal | tags=6 | related=7 | sources=1
  - ✓ clean

**parallel/journal/`2025-03-02`** (top_indeg)
  - words=422 | h2=4 | wikilinks=6 (0 unresolved) | quotes=2 (attr=0)
  - fm: type=journal | tags=8 | related=6 | sources=1
  - ✓ clean

**parallel/journal/`2026-03-19`** (top_mtime)
  - words=304 | h2=4 | wikilinks=4 (0 unresolved) | quotes=1 (attr=0)
  - fm: type=journal | tags=6 | related=4 | sources=1
  - ✓ clean

**parallel/journal/`2026-06-18`** (top_mtime)
  - words=229 | h2=0 | wikilinks=4 (2 unresolved) | quotes=0 (attr=0)
  - fm: type=journal | tags=3 | related=8 | sources=1
  - **DEFECTS**: unresolved_related:1, unresolved_wl:2/4

**parallel/journal/`2026-07-03`** (top_mtime)
  - words=230 | h2=0 | wikilinks=4 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=journal | tags=5 | related=11 | sources=1
  - ✓ clean


#### wisdom

**parallel/wisdom/`will-and-action`** (random)
  - words=339 | h2=6 | wikilinks=15 (0 unresolved) | quotes=7 (attr=6)
  - fm: type=wisdom | tags=6 | related=5 | sources=1
  - ✓ clean

**parallel/wisdom/`ganas-and-determination`** (random)
  - words=205 | h2=2 | wikilinks=15 (0 unresolved) | quotes=8 (attr=7)
  - fm: type=wisdom | tags=6 | related=5 | sources=1
  - ✓ clean

**parallel/wisdom/`attention-and-effort`** (random)
  - words=236 | h2=5 | wikilinks=12 (6 unresolved) | quotes=6 (attr=6)
  - fm: type=wisdom | tags=6 | related=3 | sources=1
  - **DEFECTS**: unresolved_related:2, unresolved_wl:6/12

**parallel/wisdom/`avoidance-and-self-knowledge`** (top_indeg)
  - words=64 | h2=0 | wikilinks=2 (1 unresolved) | quotes=1 (attr=1)
  - fm: type=wisdom | tags=5 | related=1 | sources=1
  - **DEFECTS**: fm_missing_title, unresolved_wl:1/2, stub:64w

**parallel/wisdom/`faith-and-perception`** (top_indeg)
  - words=243 | h2=4 | wikilinks=12 (0 unresolved) | quotes=6 (attr=6)
  - fm: type=wisdom | tags=7 | related=2 | sources=1
  - **DEFECTS**: fm_missing_title

**parallel/wisdom/`consciousness-and-impermanence`** (top_indeg)
  - words=303 | h2=2 | wikilinks=8 (0 unresolved) | quotes=7 (attr=7)
  - fm: type=wisdom | tags=7 | related=3 | sources=1
  - ✓ clean

**parallel/wisdom/`capitalism-surplus-and-power`** (top_mtime)
  - words=238 | h2=4 | wikilinks=10 (0 unresolved) | quotes=5 (attr=1)
  - fm: type=wisdom | tags=6 | related=7 | sources=1
  - **DEFECTS**: unattributed_quotes:1/5

**parallel/wisdom/`power-mercy-and-red-lines`** (top_mtime)
  - words=275 | h2=4 | wikilinks=14 (0 unresolved) | quotes=7 (attr=7)
  - fm: type=wisdom | tags=6 | related=3 | sources=1
  - ✓ clean

**parallel/wisdom/`will-and-action`** (top_mtime)
  - words=339 | h2=6 | wikilinks=15 (0 unresolved) | quotes=7 (attr=6)
  - fm: type=wisdom | tags=6 | related=5 | sources=1
  - ✓ clean


#### goals

**parallel/goals/`financial-autonomy`** (random)
  - words=132 | h2=2 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=3 | related=2 | sources=1
  - ✓ clean

**parallel/goals/`career-synthesis-finance-ai`** (random)
  - words=174 | h2=4 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=6 | related=3 | sources=1
  - ✓ clean

**parallel/goals/`build-follow-through-system`** (random)
  - words=178 | h2=5 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=5 | related=3 | sources=1
  - ✓ clean

**parallel/goals/`career-synthesis-finance-ai`** (top_indeg)
  - words=174 | h2=4 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=6 | related=3 | sources=1
  - ✓ clean

**parallel/goals/`democratize-physiotherapy-ai`** (top_indeg)
  - words=233 | h2=4 | wikilinks=3 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=5 | related=3 | sources=1
  - ✓ clean

**parallel/goals/`ship-mikai-wedge`** (top_indeg)
  - words=164 | h2=2 | wikilinks=5 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=4 | related=6 | sources=1
  - ✓ clean

**parallel/goals/`financial-autonomy`** (top_mtime)
  - words=132 | h2=2 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=3 | related=2 | sources=1
  - ✓ clean

**parallel/goals/`producer-value-capture-coffee`** (top_mtime)
  - words=134 | h2=2 | wikilinks=3 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=4 | related=4 | sources=1
  - ✓ clean

**parallel/goals/`found-or-join-at-a-seam`** (top_mtime)
  - words=128 | h2=2 | wikilinks=4 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=4 | related=6 | sources=1
  - ✓ clean


#### habits

**parallel/habits/`microdosing-lsd`** (random)
  - words=95 | h2=3 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=habit | tags=5 | related=2 | sources=1
  - **DEFECTS**: stub:95w

**parallel/habits/`weekly-self-critique`** (random)
  - words=147 | h2=3 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=habit | tags=5 | related=3 | sources=1
  - ✓ clean

**parallel/habits/`intermittent-fasting`** (random)
  - words=59 | h2=2 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=habit | tags=4 | related=1 | sources=1
  - **DEFECTS**: stub:59w

**parallel/habits/`journaling`** (top_indeg)
  - words=109 | h2=2 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=habit | tags=4 | related=0 | sources=1
  - ✓ clean

**parallel/habits/`intermittent-fasting`** (top_indeg)
  - words=59 | h2=2 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=habit | tags=4 | related=1 | sources=1
  - **DEFECTS**: stub:59w

**parallel/habits/`microdosing-lsd`** (top_indeg)
  - words=95 | h2=3 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=habit | tags=5 | related=2 | sources=1
  - **DEFECTS**: stub:95w

**parallel/habits/`weekly-self-critique`** (top_mtime)
  - words=147 | h2=3 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=habit | tags=5 | related=3 | sources=1
  - ✓ clean

**parallel/habits/`intermittent-fasting`** (top_mtime)
  - words=59 | h2=2 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=habit | tags=4 | related=1 | sources=1
  - **DEFECTS**: stub:59w

**parallel/habits/`microdosing-lsd`** (top_mtime)
  - words=95 | h2=3 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=habit | tags=5 | related=2 | sources=1
  - **DEFECTS**: stub:95w


#### reflections

**parallel/reflections/`monthly-2021-10`** (random)
  - words=266 | h2=8 | wikilinks=7 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=reflection | tags=7 | related=7 | sources=1
  - ✓ clean

**parallel/reflections/`monthly-2025-10`** (random)
  - words=97 | h2=2 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=reflection | tags=4 | related=1 | sources=1
  - **DEFECTS**: stub:97w

**parallel/reflections/`monthly-2025-10`** (top_indeg)
  - words=97 | h2=2 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=reflection | tags=4 | related=1 | sources=1
  - **DEFECTS**: stub:97w

**parallel/reflections/`monthly-2021-10`** (top_indeg)
  - words=266 | h2=8 | wikilinks=7 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=reflection | tags=7 | related=7 | sources=1
  - ✓ clean

**parallel/reflections/`monthly-2025-10`** (top_mtime)
  - words=97 | h2=2 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=reflection | tags=4 | related=1 | sources=1
  - **DEFECTS**: stub:97w

**parallel/reflections/`monthly-2021-10`** (top_mtime)
  - words=266 | h2=8 | wikilinks=7 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=reflection | tags=7 | related=7 | sources=1
  - ✓ clean


#### synthesis

**parallel/synthesis/`dalio-in-the-village`** (random)
  - words=755 | h2=7 | wikilinks=9 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=5 | related=14 | sources=1
  - ✓ clean

**parallel/synthesis/`mikai-metabolism-reframe`** (random)
  - words=666 | h2=6 | wikilinks=7 (1 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=5 | related=11 | sources=1
  - ✓ clean

**parallel/synthesis/`mikai-vs-agent-memory-ecosystem`** (random)
  - words=328 | h2=4 | wikilinks=7 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=5 | related=8 | sources=1
  - ✓ clean

**parallel/synthesis/`dalio-in-the-village`** (top_indeg)
  - words=755 | h2=7 | wikilinks=9 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=5 | related=14 | sources=1
  - ✓ clean

**parallel/synthesis/`mikai-metabolism-reframe`** (top_indeg)
  - words=666 | h2=6 | wikilinks=7 (1 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=5 | related=11 | sources=1
  - ✓ clean

**parallel/synthesis/`mikai-vs-agent-memory-ecosystem`** (top_indeg)
  - words=328 | h2=4 | wikilinks=7 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=5 | related=8 | sources=1
  - ✓ clean

**parallel/synthesis/`conglomerate-capitalism-mechanisms`** (top_mtime)
  - words=570 | h2=5 | wikilinks=8 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=6 | related=23 | sources=1
  - ✓ clean

**parallel/synthesis/`dalio-in-the-village`** (top_mtime)
  - words=755 | h2=7 | wikilinks=9 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=5 | related=14 | sources=1
  - ✓ clean

**parallel/synthesis/`mikai-metabolism-reframe`** (top_mtime)
  - words=666 | h2=6 | wikilinks=7 (1 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=5 | related=11 | sources=1
  - ✓ clean


#### comparisons

**parallel/comparisons/`r3_candidates_level3-1_2026-08-31`** (random)
  - words=5328 | h2=5 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=? | tags=0 | related=0 | sources=0
  - **DEFECTS**: fm_missing_type, fm_missing_title, fm_missing_created, fm_missing_updated, runaway:5328w

**parallel/comparisons/`serial_vs_parallel_2026-08-26`** (random)
  - words=3274 | h2=24 | wikilinks=53 (5 unresolved) | quotes=0 (attr=0)
  - fm: type=? | tags=0 | related=0 | sources=0
  - **DEFECTS**: fm_missing_type, fm_missing_title, fm_missing_created, fm_missing_updated, truncation_marker:TRUNCATED, runaway:3274w

**parallel/comparisons/`build_c_qa_2026-08-30`** (random)
  - words=14626 | h2=86 | wikilinks=20 (6 unresolved) | quotes=6 (attr=0)
  - fm: type=? | tags=0 | related=0 | sources=0
  - **DEFECTS**: fm_missing_type, fm_missing_title, fm_missing_created, fm_missing_updated, truncation_marker:TRUNCATED, runaway:14626w

**parallel/comparisons/`obsidian-vs-mem-ai`** (top_indeg)
  - words=498 | h2=8 | wikilinks=6 (2 unresolved) | quotes=0 (attr=0)
  - fm: type=comparison | tags=7 | related=7 | sources=1
  - **DEFECTS**: unresolved_wl:2/6

**parallel/comparisons/`hiccup-vs-howie`** (top_indeg)
  - words=390 | h2=3 | wikilinks=6 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=comparison | tags=5 | related=8 | sources=1
  - ✓ clean

**parallel/comparisons/`folo-vs-trendradar`** (top_indeg)
  - words=311 | h2=4 | wikilinks=3 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=comparison | tags=6 | related=7 | sources=1
  - ✓ clean

**parallel/comparisons/`r4_candidates_2026-08-31`** (top_mtime)
  - words=5186 | h2=5 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=? | tags=0 | related=0 | sources=0
  - **DEFECTS**: fm_missing_type, fm_missing_title, fm_missing_created, fm_missing_updated, runaway:5186w

**parallel/comparisons/`warm-walnut-vs-smoked-oak`** (top_mtime)
  - words=426 | h2=4 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=comparison | tags=4 | related=5 | sources=1
  - ✓ clean

**parallel/comparisons/`hiccup-vs-howie`** (top_mtime)
  - words=390 | h2=3 | wikilinks=6 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=comparison | tags=5 | related=8 | sources=1
  - ✓ clean


### serial vault

#### concepts

**serial/concepts/`t-shaped-founder`** (random)
  - words=446 | h2=5 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=6 | related=4 | sources=1
  - ✓ clean

**serial/concepts/`memex`** (random)
  - words=269 | h2=2 | wikilinks=4 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=5 | related=6 | sources=1
  - ✓ clean

**serial/concepts/`tension-release-through-expression`** (random)
  - words=225 | h2=3 | wikilinks=2 (0 unresolved) | quotes=1 (attr=0)
  - fm: type=concept | tags=5 | related=3 | sources=1
  - ✓ clean

**serial/concepts/`imperfect-forward-motion`** (top_indeg)
  - words=302 | h2=4 | wikilinks=5 (0 unresolved) | quotes=3 (attr=3)
  - fm: type=concept | tags=6 | related=2 | sources=1
  - ✓ clean

**serial/concepts/`personal-intent-graph`** (top_indeg)
  - words=736 | h2=6 | wikilinks=9 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=11 | related=14 | sources=2
  - ✓ clean

**serial/concepts/`love-first-principle`** (top_indeg)
  - words=363 | h2=5 | wikilinks=6 (2 unresolved) | quotes=2 (attr=2)
  - fm: type=concept | tags=5 | related=4 | sources=1
  - **DEFECTS**: unresolved_related:2, unresolved_wl:2/6

**serial/concepts/`reconfigure-type-signature`** (top_mtime)
  - words=223 | h2=2 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=9 | related=6 | sources=1
  - ✓ clean

**serial/concepts/`gartner-time-model`** (top_mtime)
  - words=177 | h2=2 | wikilinks=3 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=7 | related=5 | sources=1
  - ✓ clean

**serial/concepts/`transaction-cost-value-framing`** (top_mtime)
  - words=206 | h2=3 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=concept | tags=10 | related=5 | sources=1
  - ✓ clean


#### entities

**serial/entities/`joseph-dirand`** (random)
  - words=210 | h2=3 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=4 | related=7 | sources=1
  - ✓ clean

**serial/entities/`stafford-beer`** (random)
  - words=66 | h2=0 | wikilinks=3 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=7 | related=4 | sources=1
  - **DEFECTS**: stub:66w

**serial/entities/`microsoft-recall`** (random)
  - words=258 | h2=2 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=6 | related=5 | sources=1
  - ✓ clean

**serial/entities/`mikai`** (top_indeg)
  - words=591 | h2=6 | wikilinks=11 (1 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=6 | related=11 | sources=1
  - **DEFECTS**: unresolved_related:1

**serial/entities/`noonchi`** (top_indeg)
  - words=172 | h2=3 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=5 | related=3 | sources=1
  - ✓ clean

**serial/entities/`ray-dalio`** (top_indeg)
  - words=422 | h2=4 | wikilinks=13 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=11 | related=21 | sources=1
  - **DEFECTS**: unresolved_related:1

**serial/entities/`saas-management-platforms`** (top_mtime)
  - words=187 | h2=3 | wikilinks=4 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=7 | related=8 | sources=1
  - ✓ clean

**serial/entities/`project-cybersyn`** (top_mtime)
  - words=100 | h2=0 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=8 | related=4 | sources=1
  - ✓ clean

**serial/entities/`stafford-beer`** (top_mtime)
  - words=66 | h2=0 | wikilinks=3 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=entity | tags=7 | related=4 | sources=1
  - **DEFECTS**: stub:66w


#### sources

**serial/sources/`2026-05-13-task-state-awareness-375542`** (random)
  - words=1159 | h2=12 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=9 | related=18 | sources=1
  - ✓ clean

**serial/sources/`2026-06-25-self-skill-creation-tools-across-tech-stack-9b0435`** (random)
  - words=804 | h2=7 | wikilinks=13 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=16 | related=16 | sources=1
  - ✓ clean

**serial/sources/`2023-08-02-july-2023-27d2b1`** (random)
  - words=271 | h2=5 | wikilinks=6 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=7 | related=6 | sources=1
  - ✓ clean

**serial/sources/`2026-03-06-march-2026-9140a8`** (top_indeg)
  - words=556 | h2=5 | wikilinks=16 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=8 | related=13 | sources=1
  - **DEFECTS**: truncation_marker:TRUNCATED

**serial/sources/`2023-07-04-july-2023-27d2b1`** (top_indeg)
  - words=575 | h2=12 | wikilinks=5 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=9 | related=9 | sources=1
  - ✓ clean

**serial/sources/`2015-05-09-may-2015-bf4604`** (top_indeg)
  - words=553 | h2=8 | wikilinks=3 (0 unresolved) | quotes=5 (attr=0)
  - fm: type=source | tags=7 | related=3 | sources=1
  - ✓ clean

**serial/sources/`2026-06-25-self-skill-creation-tools-across-tech-stack-9b0435`** (top_mtime)
  - words=804 | h2=7 | wikilinks=13 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=16 | related=16 | sources=1
  - ✓ clean

**serial/sources/`2026-06-24-debt-mechanisms-and-personal-financial-philosophy-412573`** (top_mtime)
  - words=631 | h2=3 | wikilinks=14 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=14 | related=22 | sources=1
  - **DEFECTS**: unresolved_related:1, h1_title_mismatch

**serial/sources/`2026-06-02-weighted-yoga-for-flexibility-and-alignment-83cccc`** (top_mtime)
  - words=1006 | h2=6 | wikilinks=25 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=source | tags=9 | related=16 | sources=1
  - ✓ clean


#### queries

**serial/queries/`can-ai-automate-company-setup`** (random)
  - words=193 | h2=4 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=6 | related=3 | sources=1
  - ✓ clean

**serial/queries/`who-is-chiang-in-the-village-debt-framework`** (random)
  - words=358 | h2=4 | wikilinks=3 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=5 | related=6 | sources=1
  - ✓ clean

**serial/queries/`does-greatness-require-ego`** (random)
  - words=288 | h2=4 | wikilinks=3 (0 unresolved) | quotes=1 (attr=0)
  - fm: type=query | tags=6 | related=4 | sources=1
  - ✓ clean

**serial/queries/`how-to-integrate-drive-with-joy`** (top_indeg)
  - words=272 | h2=4 | wikilinks=2 (0 unresolved) | quotes=1 (attr=0)
  - fm: type=query | tags=5 | related=4 | sources=1
  - ✓ clean

**serial/queries/`velocity-of-money-vs-supply-as-market-driver`** (top_indeg)
  - words=240 | h2=4 | wikilinks=1 (1 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=4 | related=0 | sources=1
  - **DEFECTS**: unresolved_wl:1/1

**serial/queries/`does-adhd-explain-low-c-in-this-entj-profile`** (top_indeg)
  - words=375 | h2=6 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=6 | related=4 | sources=1
  - ✓ clean

**serial/queries/`does-enterprise-stated-strategy-vs-revealed-config-gap-constitute-pmf`** (top_mtime)
  - words=254 | h2=4 | wikilinks=3 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=6 | related=5 | sources=1
  - ✓ clean

**serial/queries/`what-is-mikai-execute-layer-architecture`** (top_mtime)
  - words=234 | h2=3 | wikilinks=6 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=6 | related=7 | sources=1
  - ✓ clean

**serial/queries/`can-mikai-l4-ride-honcho-as-user-model-substrate`** (top_mtime)
  - words=280 | h2=4 | wikilinks=4 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=query | tags=6 | related=5 | sources=1
  - ✓ clean


#### journal

**serial/journal/`2015-05-09`** (random)
  - words=684 | h2=0 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=journal | tags=7 | related=3 | sources=1
  - ✓ clean

**serial/journal/`2022-08`** (random)
  - words=131 | h2=3 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=journal | tags=5 | related=4 | sources=1
  - ✓ clean

**serial/journal/`2022-06`** (random)
  - words=259 | h2=3 | wikilinks=5 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=journal | tags=7 | related=6 | sources=1
  - ✓ clean

**serial/journal/`2021-10`** (top_indeg)
  - words=279 | h2=4 | wikilinks=6 (0 unresolved) | quotes=1 (attr=0)
  - fm: type=journal | tags=6 | related=6 | sources=1
  - ✓ clean

**serial/journal/`2022-08`** (top_indeg)
  - words=131 | h2=3 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=journal | tags=5 | related=4 | sources=1
  - ✓ clean

**serial/journal/`2015-05-09`** (top_indeg)
  - words=684 | h2=0 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=journal | tags=7 | related=3 | sources=1
  - ✓ clean

**serial/journal/`2022-08`** (top_mtime)
  - words=131 | h2=3 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=journal | tags=5 | related=4 | sources=1
  - ✓ clean

**serial/journal/`2022-06`** (top_mtime)
  - words=259 | h2=3 | wikilinks=5 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=journal | tags=7 | related=6 | sources=1
  - ✓ clean

**serial/journal/`2021-10`** (top_mtime)
  - words=279 | h2=4 | wikilinks=6 (0 unresolved) | quotes=1 (attr=0)
  - fm: type=journal | tags=6 | related=6 | sources=1
  - ✓ clean


#### wisdom

**serial/wisdom/`authentic-leadership-and-impact`** (random)
  - words=175 | h2=0 | wikilinks=10 (3 unresolved) | quotes=5 (attr=5)
  - fm: type=wisdom | tags=5 | related=4 | sources=1
  - ✓ clean

**serial/wisdom/`wu-wei-and-flow`** (random)
  - words=230 | h2=7 | wikilinks=15 (6 unresolved) | quotes=7 (attr=7)
  - fm: type=wisdom | tags=7 | related=5 | sources=1
  - **DEFECTS**: unresolved_related:1, unresolved_wl:6/15

**serial/wisdom/`inner-voice-and-creative-authority`** (random)
  - words=215 | h2=5 | wikilinks=17 (0 unresolved) | quotes=7 (attr=7)
  - fm: type=wisdom | tags=6 | related=5 | sources=1
  - ✓ clean

**serial/wisdom/`faith-presence-and-imperfect-action`** (top_indeg)
  - words=247 | h2=4 | wikilinks=14 (0 unresolved) | quotes=7 (attr=7)
  - fm: type=wisdom | tags=7 | related=2 | sources=1
  - ✓ clean

**serial/wisdom/`movement-through-hesitation`** (top_indeg)
  - words=315 | h2=4 | wikilinks=17 (0 unresolved) | quotes=8 (attr=8)
  - fm: type=wisdom | tags=8 | related=4 | sources=1
  - ✓ clean

**serial/wisdom/`wu-wei-and-flow`** (top_indeg)
  - words=230 | h2=7 | wikilinks=15 (6 unresolved) | quotes=7 (attr=7)
  - fm: type=wisdom | tags=7 | related=5 | sources=1
  - **DEFECTS**: unresolved_related:1, unresolved_wl:6/15

**serial/wisdom/`execution-and-product-philosophy`** (top_mtime)
  - words=240 | h2=7 | wikilinks=15 (0 unresolved) | quotes=7 (attr=7)
  - fm: type=wisdom | tags=6 | related=6 | sources=1
  - ✓ clean

**serial/wisdom/`systems-and-leverage`** (top_mtime)
  - words=150 | h2=0 | wikilinks=12 (0 unresolved) | quotes=6 (attr=6)
  - fm: type=wisdom | tags=6 | related=5 | sources=1
  - ✓ clean

**serial/wisdom/`quest-and-the-long-game`** (top_mtime)
  - words=319 | h2=3 | wikilinks=14 (2 unresolved) | quotes=8 (attr=7)
  - fm: type=wisdom | tags=8 | related=7 | sources=1
  - **DEFECTS**: unresolved_related:1


#### goals

**serial/goals/`build-architecture-judgment`** (random)
  - words=93 | h2=2 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=3 | related=6 | sources=1
  - **DEFECTS**: stub:93w

**serial/goals/`propose-to-germaine`** (random)
  - words=68 | h2=1 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=3 | related=1 | sources=1
  - **DEFECTS**: stub:68w

**serial/goals/`coffee-producer-infrastructure`** (random)
  - words=142 | h2=3 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=5 | related=4 | sources=1
  - ✓ clean

**serial/goals/`ship-mikai-wedge`** (top_indeg)
  - words=139 | h2=3 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=4 | related=5 | sources=1
  - ✓ clean

**serial/goals/`systematic-trading-process`** (top_indeg)
  - words=226 | h2=5 | wikilinks=3 (0 unresolved) | quotes=1 (attr=0)
  - fm: type=goal | tags=4 | related=3 | sources=1
  - ✓ clean

**serial/goals/`ai-physio-platform`** (top_indeg)
  - words=181 | h2=5 | wikilinks=4 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=5 | related=3 | sources=1
  - ✓ clean

**serial/goals/`financial-autonomy`** (top_mtime)
  - words=83 | h2=1 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=3 | related=2 | sources=1
  - **DEFECTS**: stub:83w

**serial/goals/`coffee-producer-infrastructure`** (top_mtime)
  - words=142 | h2=3 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=5 | related=4 | sources=1
  - ✓ clean

**serial/goals/`add-lean-mass`** (top_mtime)
  - words=63 | h2=1 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=goal | tags=3 | related=0 | sources=1
  - **DEFECTS**: stub:63w


#### habits

**serial/habits/`weekly-self-evaluation`** (random)
  - words=197 | h2=4 | wikilinks=1 (0 unresolved) | quotes=1 (attr=0)
  - fm: type=habit | tags=5 | related=3 | sources=1
  - ✓ clean

**serial/habits/`weekly-self-evaluation`** (top_indeg)
  - words=197 | h2=4 | wikilinks=1 (0 unresolved) | quotes=1 (attr=0)
  - fm: type=habit | tags=5 | related=3 | sources=1
  - ✓ clean

**serial/habits/`weekly-self-evaluation`** (top_mtime)
  - words=197 | h2=4 | wikilinks=1 (0 unresolved) | quotes=1 (attr=0)
  - fm: type=habit | tags=5 | related=3 | sources=1
  - ✓ clean


#### synthesis

**serial/synthesis/`mikai-as-goal-controller`** (random)
  - words=576 | h2=6 | wikilinks=17 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=7 | related=16 | sources=1
  - ✓ clean

**serial/synthesis/`mikai-ea-feed-product-definition`** (random)
  - words=559 | h2=7 | wikilinks=4 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=6 | related=9 | sources=1
  - ✓ clean

**serial/synthesis/`mikai-self-vs-project-positioning`** (random)
  - words=408 | h2=4 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=6 | related=10 | sources=1
  - ✓ clean

**serial/synthesis/`mikai-as-goal-controller`** (top_indeg)
  - words=576 | h2=6 | wikilinks=17 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=7 | related=16 | sources=1
  - ✓ clean

**serial/synthesis/`mikai-ea-feed-product-definition`** (top_indeg)
  - words=559 | h2=7 | wikilinks=4 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=6 | related=9 | sources=1
  - ✓ clean

**serial/synthesis/`mikai-self-vs-project-positioning`** (top_indeg)
  - words=408 | h2=4 | wikilinks=1 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=6 | related=10 | sources=1
  - ✓ clean

**serial/synthesis/`conglomerate-capitalism-and-rent-extraction`** (top_mtime)
  - words=452 | h2=4 | wikilinks=13 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=8 | related=20 | sources=2
  - ✓ clean

**serial/synthesis/`mikai-as-goal-controller`** (top_mtime)
  - words=576 | h2=6 | wikilinks=17 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=7 | related=16 | sources=1
  - ✓ clean

**serial/synthesis/`mikai-ea-feed-product-definition`** (top_mtime)
  - words=559 | h2=7 | wikilinks=4 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=synthesis | tags=6 | related=9 | sources=1
  - ✓ clean


#### comparisons

**serial/comparisons/`claude-vs-chatgpt-for-mika`** (random)
  - words=371 | h2=4 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=comparison | tags=8 | related=5 | sources=1
  - ✓ clean

**serial/comparisons/`obsidian-vs-mem-ai`** (random)
  - words=456 | h2=6 | wikilinks=10 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=comparison | tags=8 | related=10 | sources=1
  - ✓ clean

**serial/comparisons/`r3_candidates_level3-1_2026-08-31`** (random)
  - words=5328 | h2=5 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=? | tags=0 | related=0 | sources=0
  - **DEFECTS**: fm_missing_type, fm_missing_title, fm_missing_created, fm_missing_updated, runaway:5328w

**serial/comparisons/`hermes-vs-openclaw-vs-mikai-memory`** (top_indeg)
  - words=369 | h2=2 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=comparison | tags=7 | related=6 | sources=1
  - ✓ clean

**serial/comparisons/`mcp-vs-skill-md-vs-a2a`** (top_indeg)
  - words=278 | h2=2 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=comparison | tags=6 | related=5 | sources=1
  - ✓ clean

**serial/comparisons/`isfj-vs-enfp-life-partner`** (top_indeg)
  - words=573 | h2=5 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=comparison | tags=8 | related=4 | sources=1
  - ✓ clean

**serial/comparisons/`r4_candidates_2026-08-31`** (top_mtime)
  - words=5186 | h2=5 | wikilinks=0 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=? | tags=0 | related=0 | sources=0
  - **DEFECTS**: fm_missing_type, fm_missing_title, fm_missing_created, fm_missing_updated, runaway:5186w

**serial/comparisons/`isfj-vs-enfp-life-partner`** (top_mtime)
  - words=573 | h2=5 | wikilinks=2 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=comparison | tags=8 | related=4 | sources=1
  - ✓ clean

**serial/comparisons/`hiccup-vs-howie`** (top_mtime)
  - words=377 | h2=3 | wikilinks=4 (0 unresolved) | quotes=0 (attr=0)
  - fm: type=comparison | tags=6 | related=8 | sources=1
  - ✓ clean


## Sample-set defect summary (across all sampled pages)

- **stub**: 16
- **unresolved_related**: 13
- **unresolved_wl**: 10
- **fm_missing_title**: 8
- **fm_missing_type**: 6
- **fm_missing_created**: 6
- **fm_missing_updated**: 6
- **runaway**: 6
- **truncation_marker**: 4
- **unattributed_quotes**: 1
- **h1_title_mismatch**: 1
