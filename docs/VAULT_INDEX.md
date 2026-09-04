# Vault Index — nashsu port test vaults

Version history of the wiki vaults produced during the "verbatim nashsu port" investigation.
Each version isolates a specific configuration under test. Keep them all until decisions land.

Naming convention: `V.NNN - short-slug` — three-digit zero-padded version + descriptive slug.
New vaults get the next V.NNN in sequence. Rename when a vault's state fundamentally changes;
don't rename when it just gets more data appended.

Production wiki (`~/.mikai/wiki/`) is NOT versioned this way — that is the live substrate,
touched only by production ingestion, unrelated to this test series.

## Versions

| # | path | pipeline | template | model | workers | notes |
|---|---|---|---|---|---|---|
| V.001 | `~/.mikai/V.001 - wiki-golden/` | headless | Personal Growth | sonnet-4-5 | 16 | Original golden-set run. Contaminated: 32% non-English pages (Korean, German, Swahili, French). Language guard not enforced because `outputLanguage="auto"`. First real parity comparison against V.002. Contents preserved under `wiki.contaminated-2026-08-18/` for regression testing. |
| V.002 | `~/Desktop/V.002 - wiki-desktop/` | desktop 0.6.8 | Generic | sonnet-4-6 | 1 (concurrent-parser) | Desktop app's own ingest of the same 46 sources. Reference implementation. |
| V.003 | `~/.mikai/V.003 - wiki-obsidian/` | headless | Personal Growth | sonnet-4-6 | (uninit) | Fresh vault created after fixing `.obsidian/` seeding bug (init-project.ts). Empty — no ingest yet. Purpose: verify Obsidian compatibility parity. |
| V.004 | `~/.mikai/V.004 - wiki-generic/` | headless | Generic | sonnet-4-6 | 1 | Single-source apples-to-apples test against V.002. Only test using Generic template on headless pipeline. Isolates template as a variable. |

## Planned next versions

| # | intended purpose |
|---|---|
| V.005 | Full 46-source re-ingest of the golden set with: sonnet-4-6, Personal Growth, outputLanguage="English", `.obsidian/` seeded, `--workers 1` (serial). Definitive quality baseline for the port. |
| V.006 | Same as V.005 but with `--workers 16` and a two-phase ingest patch (parallel Pass-1, serial commit + index refresh). Tests whether the two-phase design recovers wikilink density without the serial time cost. |

## Fixed bugs referenced by version

- **outputLanguage** (32% non-English on V.001): fixed 2026-08-18 in `src/mikai-cli/ingest.ts:166` — seed `useWikiStore.setState({ outputLanguage: "English" })` before autoIngest.
- **`.obsidian/` empty seeding** (V.001's `.obsidian/*.json` were `{}`): fixed 2026-08-18 in `src/mikai-cli/init-project.ts` — mirror the three JSON blobs from `src-tauri/src/commands/project.rs` L196-235.
- **Model version drift** (V.001 hardcoded sonnet-4-5; desktop uses 4-6): fixed 2026-08-18 in `src/mikai-cli/ingest.ts:41`.

## Known open issues (not yet fixed)

- **Merge failures under parallel load** — `[page-merge] LLM merge failed ... claude -p exited with code 1` on 12+ occasions during the 16-worker V.001 run. Falls to lossy concatenation. Fix: retry-with-backoff around merge call in `src/lib/page-merge.ts`, OR restructure into two-phase parallel-prep / serial-commit ingest.
- **Wikilink density on cold-index sources** — headless-16-worker mode leaves early-in-queue sources with near-zero wikilinks because they Pass-2 against a nearly-empty index. Same fix as above.
- **Concept-slug overlap ~10%** between V.001 and V.002 — dominated by LLM nondeterminism at temperature undefined (`claude -p` ignores temperature/seed on subscription auth). Not fixable at code level.

## References

- Comparison scripts:
  - `infra/nashsu/bridge/compare_vaults.py` — page-count, wikilink-density, concept-Jaccard, language audit
- Reports:
  - `eval/reports/vault_comparison_2026-08-18.md` — V.001 (pre-fix) vs V.002
  - `eval/reports/vault_comparison_2026-08-18_post-fix.md` — V.001 (post-fix, still contaminated) vs V.002
- Plan file: `~/.claude/plans/fuzzy-shimmying-wreath.md` — full history through Session-6 addendum
