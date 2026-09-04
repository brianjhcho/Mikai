# Vault comparison report

- **Vault A (headless port)**: `/Users/briancho/.mikai/wiki-golden`
- **Vault B (desktop app 0.6.8)**: `/Users/briancho/Desktop/Golden-wiki comparison`

## Page-type distribution

| type | Vault A | Vault B | delta | confound |
|------|---------|---------|-------|----------|
| `concepts` | 159 | 215 | -56 |  |
| `entities` | 60 | 62 | -2 |  |
| `sources` | 46 | 46 | +0 |  |
| `queries` | 16 | 36 | -20 |  |
| `journal` | 27 | 0 | +27 | **template mismatch** |
| `goals` | 5 | 0 | +5 | **template mismatch** |
| `habits` | 2 | 0 | +2 | **template mismatch** |
| `reflections` | 0 | 0 | +0 | **template mismatch** |
| `comparisons` | 0 | 5 | -5 |  |
| `synthesis` | 0 | 1 | -1 |  |
| `media` | 0 | 0 | +0 |  |
| **total** | **315** | **365** | **-50** | |

## Source coverage

- Shared sources (same filename in both `raw/sources/`): **46**
- Only in Vault A: **0**
- Only in Vault B: **0**
- Of shared sources, English-only (< 2% non-ASCII): **46** (100%)

## Source-summary page comparison (clean surface — Surface A)

### Body richness (words per source-summary)

| stat | Vault A | Vault B | ratio A/B |
|------|---------|---------|-----------|
| median | 528 | 450 | 1.17 |
| mean   | 770 | 464 | 1.66 |
| p90    | 1206 | 634 | — |

### Wikilink density (outgoing links per source-summary)

| stat | Vault A | Vault B | ratio A/B |
|------|---------|---------|-----------|
| median | 2 | 9 | 0.22 |
| mean   | 4.1 | 9.3 | 0.44 |
| p90    | 10 | 15 | — |

### Per-source wikilink target overlap

- Median Jaccard: **0.00**
- Mean Jaccard:   **0.03**
- Sources with ≥ 50% overlap: **1 / 46**

### Frontmatter agreement

- Same `title`:   **8 / 46** (17%)
- Same `tags` (set-equal):   **0 / 46** (0%)
- Same `related` (set-equal): **0 / 46** (0%)

## Concept-slug overlap (Surface A + C)

- **Full concept Jaccard**: 10.00%
- **Concept Jaccard on English-only sources**: 10.00%
- **Entity Jaccard**: 22.00%
- Reference nondeterminism baseline (same pipeline, two runs, historical): **~7%**

## Language check (Surface B — confounded)

- Concept pages with > 5% non-ASCII body content — **Vault A: 0, Vault B: 0**
- Root cause on Vault A: headless CLI never seeds `outputLanguage: "en"`. Fix identified; not yet applied.

## Confound ledger

| # | confound | affected surface | status |
|---|---|---|---|
| 1 | Template mismatch (Personal Growth vs Generic) | page-type distribution — journal/goals/habits/reflections | reported above; not port bug |
| 2 | Version drift (0.6.9 vendored vs 0.6.8 desktop) | unknown per-release prompt diffs | small; treat as noise floor |
| 3 | outputLanguage drift on headless | non-English concept pages on Vault A | fix identified in `mikai-cli/ingest.ts`; not applied yet |
| 4 | `.obsidian/` empty seeding on headless | future vault initialization only | **fixed 2026-08-18** in `init-project.ts` |
