# Vault comparison report

- **Vault A (headless port)**: `/Users/briancho/.mikai/wiki-golden`
- **Vault B (desktop app 0.6.8)**: `/Users/briancho/Desktop/Golden-wiki comparison`

## Page-type distribution

| type | Vault A | Vault B | delta | confound |
|------|---------|---------|-------|----------|
| `concepts` | 192 | 215 | -23 |  |
| `entities` | 68 | 62 | +6 |  |
| `sources` | 46 | 46 | +0 |  |
| `queries` | 25 | 36 | -11 |  |
| `journal` | 30 | 0 | +30 | **template mismatch** |
| `goals` | 12 | 0 | +12 | **template mismatch** |
| `habits` | 3 | 0 | +3 | **template mismatch** |
| `reflections` | 3 | 0 | +3 | **template mismatch** |
| `comparisons` | 0 | 5 | -5 |  |
| `synthesis` | 1 | 1 | +0 |  |
| `media` | 0 | 0 | +0 |  |
| **total** | **380** | **365** | **+15** | |

## Source coverage

- Shared sources (same filename in both `raw/sources/`): **46**
- Only in Vault A: **0**
- Only in Vault B: **0**
- Of shared sources, English-only (< 2% non-ASCII): **46** (100%)

## Source-summary page comparison (clean surface — Surface A)

### Body richness (words per source-summary)

| stat | Vault A | Vault B | ratio A/B |
|------|---------|---------|-----------|
| median | 566 | 450 | 1.26 |
| mean   | 590 | 464 | 1.27 |
| p90    | 1020 | 634 | — |

### Wikilink density (outgoing links per source-summary)

| stat | Vault A | Vault B | ratio A/B |
|------|---------|---------|-----------|
| median | 2 | 9 | 0.22 |
| mean   | 3.3 | 9.3 | 0.36 |
| p90    | 8 | 15 | — |

### Per-source wikilink target overlap

- Median Jaccard: **0.00**
- Mean Jaccard:   **0.04**
- Sources with ≥ 50% overlap: **1 / 46**

### Frontmatter agreement

- Same `title`:   **6 / 46** (13%)
- Same `tags` (set-equal):   **0 / 46** (0%)
- Same `related` (set-equal): **0 / 46** (0%)

## Concept-slug overlap (Surface A + C)

- **Full concept Jaccard**: 10.30%
- **Concept Jaccard on English-only sources**: 10.33%
- **Entity Jaccard**: 34.02%
- Reference nondeterminism baseline (same pipeline, two runs, historical): **~7%**

## Language check (Surface B — confounded)

- Concept pages with > 5% non-ASCII body content — **Vault A: 20, Vault B: 0**
- Root cause on Vault A: headless CLI never seeds `outputLanguage: "en"`. Fix identified; not yet applied.
- Vault A flagged files (first 10): `active-nihilism-적극적-허무주의.md, build-ports-not-palaces-실용-인프라-우선주의.md, closed-loop-goal-controller.md, contribution-over-passion-열정보다-기여.md, convergence-guarantee.md, eisenhower-matrix-중요도-긴급도-우선순위-프레임워크.md, event-sourcing.md, farmers-heart-principle-bbb-원칙.md, ganas-용기와-결단력.md, implementation-intentions.md`

## Confound ledger

| # | confound | affected surface | status |
|---|---|---|---|
| 1 | Template mismatch (Personal Growth vs Generic) | page-type distribution — journal/goals/habits/reflections | reported above; not port bug |
| 2 | Version drift (0.6.9 vendored vs 0.6.8 desktop) | unknown per-release prompt diffs | small; treat as noise floor |
| 3 | outputLanguage drift on headless | non-English concept pages on Vault A | fix identified in `mikai-cli/ingest.ts`; not applied yet |
| 4 | `.obsidian/` empty seeding on headless | future vault initialization only | **fixed 2026-08-18** in `init-project.ts` |
