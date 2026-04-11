# MIKAI — Cleanup Candidates

*Compiled: 2026-04-10*
*Repo state: `main` at commit `4efa463`*
*Method: five parallel analysis agents + targeted verification. Every candidate has a file/line citation and an estimated blast radius. Nothing has been removed. This is a worklist for Brian to review.*

## How to read this doc

Each candidate has:
- **What** — the file, directory, dependency, or pattern
- **Why stale** — specific evidence, with file:line citations where applicable
- **Confidence** — `certain`, `likely`, or `possible`
- **Blast radius** — estimated impact if removed. `zero` = nothing else references it; `small` = 1-2 other files affected; `medium` = 3-10 files or a single critical import chain; `large` = 10+ files or a load-bearing contract
- **Recommended action** — what to do with it (delete, archive, refactor, verify first, leave)

Candidates are grouped by theme, with the most urgent at the top. Confidence levels are stated per entry, not per section.

## ⚠️ Known broken state on `main`

These are not optional cleanups — they are active bugs introduced by recent commits that need a decision.

### B1. `engine/inference/rule-engine.ts` — broken import

**What**: `engine/inference/rule-engine.ts:14` contains `import { supabase } from '../../lib/supabase.js';`. Commit `4efa463` deleted `lib/supabase.ts`. The file no longer compiles.

**Why stale**: Verified directly:
```
14:import { supabase } from '../../lib/supabase.js';
```
And from the same commit's file list:
```
 delete mode 100644 lib/supabase.ts
```

**Confidence**: certain

**Blast radius**: The file has one importer chain — `engine/scheduler/daily-sync.sh` invokes `npm run run-rule-engine`, which runs `engine/inference/run-rule-engine.js`, which almost certainly delegates to `rule-engine.ts`. If the scheduler is triggered (via `launchctl load` or manual `npm run scheduler:run`), stage 7 crashes. Currently dormant because:
- `launchd` plist is not loaded on Brian's machine
- Nobody calls `npm run run-rule-engine` manually in day-to-day work

But "currently unused" is not the same as "not broken."

**Recommended action**: One of three choices.
1. **Delete the rule engine entirely.** Track B stall scoring is an artifact of the pre-L4 design. L4 state classification supersedes it. If Track B is no longer part of the product direction, delete `engine/inference/` wholesale.
2. **Fix the import.** Restore the rule engine to a working state by removing the `lib/supabase.ts` dependency and replacing it with SQLite via `lib/store-sqlite.ts`. Only makes sense if Track B is still planned.
3. **Gut the file but keep it as a stub.** Replace its implementation with a `throw new Error('rule-engine removed, use L4')` so anyone who invokes it gets a clear failure.

I recommend option 1 — delete — because L4 already does what Track B tried to do, and keeping broken code on main is worse than keeping no code.

### B2. Main's MCP server has hard Supabase coupling

**What**: `surfaces/mcp/server.ts` on `main` unconditionally imports `@supabase/supabase-js` and creates a Supabase client during module load.

**Why stale**: Verified:
```
29:import { createClient }        from '@supabase/supabase-js';
65:const SUPABASE_URL = process.env.SUPABASE_URL;
66:const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY;
69:if (!process.env.MIKAI_LOCAL && (!SUPABASE_URL || !SUPABASE_KEY)) {
70:  process.stderr.write('MIKAI MCP: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY\n');
79:const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
```

The `MIKAI_LOCAL` flag gates *behavior* but not *imports*. The `@supabase/supabase-js` package is a hard dependency of the file.

**Confidence**: certain

**Blast radius**: If `@supabase/supabase-js` is removed from `package.json` before this coupling is fixed, `npm run mcp` fails to boot and Claude Desktop loses its MCP surface entirely. Large blast radius, but only at the moment someone tries to remove the dep.

**Recommended action**: Do not remove `@supabase/supabase-js` from `package.json` until the MCP server rewrite in `wip/2026-04-10-presplit` (861 lines, Supabase-free) lands on main. That rewrite removes this import. Until then, the dep stays.

Adjacent: `surfaces/mcp/claude-desktop-config.json` contains placeholder `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` env vars for users. If Supabase is dropped, that config needs updating too.

### B3. `engine/ingestion/ingest-direct.ts` is hard-wired to Supabase

**What**: Every source connector in `sources/*/sync.js` calls `ingestNotes()` from `engine/ingestion/ingest-direct.ts`. That file throws if `SUPABASE_URL` is unset.

**Why stale**: Verified:
```
145:  const supabaseUrl = process.env.SUPABASE_URL;
149:    throw new Error('SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env.local');
```

**Confidence**: certain

**Blast radius**: Medium-large. All four source connectors (apple-notes, gmail, imessage, local-files) depend on this file via the `cleanContent` + `ingestNotes` path. If `ingest-direct.ts` is deleted or its Supabase writes are removed without replacement, all source syncs fail. The scheduler's stages 1-4 stop working.

**Recommended action**: This is a refactor, not a deletion. Either:
1. Add a SQLite write path to `ingest-direct.ts` (writes to `~/.mikai/mikai.db` when `MIKAI_LOCAL=true`, same dual-backend pattern the MCP server uses), OR
2. Rewrite it to write to Graphiti via the sidecar HTTP client (`POST /episode`), OR
3. Leave it alone for now; flag for the post-cleanup refactor pass.

I recommend option 3 — leave for now — because this is the kind of change that needs its own design session, and cleanup should focus on removing dead code, not rewriting live paths.

## Certain cleanup (safe to remove, near-zero blast radius)

### C1. Empty directories

- `apps/web/` — empty
- `surfaces/web/` — empty (Next.js removed per D-039)

**Confidence**: certain
**Blast radius**: zero (nothing in them to break)
**Recommended action**: `rmdir` both.

### C2. PuppyGraph experiment artifacts

**What**: Phase 1.5 PuppyGraph experiment concluded 2026-03-28 with decision ARCH-018 ("stay on Supabase" — note that Supabase itself has since been replaced by Graphiti, so this decision is doubly obsolete). The experiment's files are dead:
- `engine/eval/puppygraph-experiment.md`
- `engine/eval/puppygraph-schema.json`
- `engine/eval/puppygraph-schema.yaml`
- `engine/eval/results/puppygraph-comparison-2026-03-15.json` (if present)

**Why stale**: Experiment complete, decision documented, no code references. These are historical artifacts.

**Confidence**: certain
**Blast radius**: zero
**Recommended action**: Move to `private/archive/puppygraph-experiment/` (preserve history in local-only archive) or delete. Don't leave them in `engine/eval/` where they pollute the active eval directory.

### C3. `scripts/cleanup-noisy-nodes.js`

**What**: One-shot cleanup script from 2026-03-25 that deletes specific noisy Track B nodes from Supabase.

**Why stale**: File header says "One-time cleanup... These were created before the boilerplate filter was added/enhanced." Targets Supabase. No npm script references it.

**Confidence**: certain
**Blast radius**: zero
**Recommended action**: Delete.

### C4. `scripts/cleanup-sources.js`

**What**: `npm run cleanup` → `node scripts/cleanup-sources.js`. Deletes test/debug source records from Supabase.

**Why stale**: Targets Supabase, debug-only utility, last changed 2026-03-13.

**Confidence**: likely (not certain only because the npm script entry exists)
**Blast radius**: zero
**Recommended action**: Delete the file and remove the `cleanup` npm script entry.

### C5. `scripts/test-generalization.js`

**What**: One-off validation script from 2026-03-25 testing whether the extraction prompt generalizes to non-Brian content (O-025).

**Why stale**: Targets Supabase, not invoked from package.json. Imports `lib/ingest-pipeline.ts` which is itself transitional (see L2).

**Confidence**: certain
**Blast radius**: zero
**Recommended action**: Delete. O-025 remains an open question regardless.

### C6. `scripts/supabase-to-sqlite.ts`

**What**: Migration script that backfills the local SQLite database from Supabase.

**Why stale**: Already deleted in commit `4efa463`. Verify it's gone (the wip safety snapshot re-added it during the branch reorganization, so it may reappear in diffs).

**Confidence**: certain (already done)
**Blast radius**: zero
**Recommended action**: Verify absence. If it reappears, delete again.

### C7. `lib/supabase.ts`

**What**: Supabase client wrapper.

**Why stale**: Already deleted in commit `4efa463`.

**Confidence**: certain (already done)
**Blast radius**: Introduced the B1 bug above. The grep that cleared the deletion was incorrect (regex didn't match `supabase.js'` because of the `.js` suffix before the closing quote).

**Recommended action**: Already gone from `main`. Fix B1 separately.

## Likely cleanup (probably safe, requires light verification)

### L1. `lib/embeddings.ts` — Voyage AI client

**What**: Remote Voyage AI embedding calls via raw `fetch`. Exports a function nothing imports anymore.

**Why stale**: The MCP server has an inline copy of the embed logic (with comment "the MCP server is a standalone process and cannot import @/ aliases"). The SQLite path uses `lib/embeddings-local.ts` (Nomic). Supabase-era `build-graph.js` and `build-segments.js` might still import `lib/embeddings.ts` — that needs grep-verification before removal.

**Confidence**: likely
**Blast radius**: small (1-2 files in the Supabase-era build path may still import it)
**Recommended action**: Grep for `from '.*embeddings'` (not `embeddings-local`) and verify. If only Supabase-era scripts import it, delete alongside those scripts. Do not delete until after the Supabase ingestion pipeline is cleaned up or refactored.

### L2. `lib/ingest-pipeline.ts` — extraction prompt + chunk utilities

**What**: Claude Haiku reasoning-map extraction prompt and chunk utilities from the Track A era.

**Why stale**: Imported only by `scripts/test-generalization.js` (C5, itself stale) and possibly `engine/graph/build-graph.js`. Graphiti uses DeepSeek extraction via the sidecar, not this prompt.

**Confidence**: likely
**Blast radius**: depends on whether `build-graph.js` still imports it. If yes, small-medium. If no, zero.
**Recommended action**: Grep to confirm importers. If only the Supabase-era `build-graph.js` uses it, the two files can be deleted together as part of the Supabase-pipeline teardown. If Brian still values the extraction prompt as a reference for a future Graphiti-aware extraction pass, move it to `docs/prompts/` as a reference file instead of deleting.

### L3. Supabase-era eval scripts

**What**:
- `engine/eval/eval-nodes.ts`
- `engine/eval/eval-stall.ts`
- `engine/eval/eval-segments.ts`
- `engine/eval/test-suite.ts`
- `engine/eval/harvest-seeds.mjs`
- `engine/eval/eval-brief-routing.ts` (+ `.md`)

**Why stale**: All reference Supabase via inline `createClient` calls or `SUPABASE_URL` env vars. They're validation / testing utilities for the Supabase-backed pipeline. Package.json has `"test"`, `"test:brief"`, `"test:segments"`, `"test:retrieval"`, `"test:cost"` scripts pointing at `test-suite.ts`.

**Confidence**: likely (these were active testing infrastructure but now target a dead backend)
**Blast radius**: zero at runtime (they're standalone). Medium at process level (if Brian was using `npm test` for sanity checks, those commands now fail).
**Recommended action**: Don't delete in the same pass. First decide whether any of these need to be ported to the Graphiti era (probably yes — you'll want eval tooling for Graphiti's graph quality). Leave the files in place, mark them deprecated in comments, and build replacements before removing.

### L4. `engine/graph/build-graph.js` and `engine/graph/build-segments.js`

**What**: Track A (Claude Haiku) extraction and Track C (zero-LLM) segmentation scripts from the Supabase era.

**Why stale**: Both write to Supabase. `build-graph.js` calls Claude Haiku via `lib/ingest-pipeline.ts`. `build-segments.js` calls Voyage AI via `lib/embeddings.ts`. Graphiti has its own extraction (DeepSeek in the sidecar) and its own concept of episodes, so the "build-graph" concept doesn't map onto it. Track B is folded into `build-graph.js` per CLAUDE.md.

**Confidence**: likely
**Blast radius**: medium. These are called by the scheduler (stages 6, 8). If the Supabase ingestion path is being abandoned entirely, both can go. If Brian still wants Track C segmentation (which is local and cheap and produces useful passages), the segmentation half should be ported to write to local SQLite via `build-segments-local.ts` — which already exists.

**Recommended action**: Keep `build-segments-local.ts` (SQLite variant). Delete `build-segments.js` (Supabase variant) alongside the rest of the Supabase ingestion pipeline. Delete `build-graph.js` if Track A extraction is fully replaced by Graphiti's DeepSeek extraction. Both deletions are dependent on the scheduler being retired or reworked.

### L5. `engine/graph/smart-split.js`

**What**: Source-adaptive text splitting utility used by both `build-segments.js` (Supabase) and `build-segments-local.ts` (SQLite).

**Why stale**: Not stale. Keep. Listed here only to flag that deleting `build-segments.js` does NOT mean deleting `smart-split.js`.

**Confidence**: not stale (active dependency)
**Blast radius**: N/A
**Recommended action**: Keep.

### L6. `infra/supabase/` directory

**What**: Legacy SQL migrations, schema files, and search queries from the Supabase era.

**Why stale**: Nothing in TypeScript imports SQL directly; these files are used manually (or were used manually) when setting up the Supabase project. Once Supabase is fully retired, these are historical.

**Confidence**: likely
**Blast radius**: zero (no code imports SQL files)
**Recommended action**: Move to `private/archive/supabase/` for historical reference, or delete. Do it in the same pass as the Supabase ingestion pipeline teardown.

### L7. `scripts/perplexity-playwright.ts`

**What**: Playwright script to scrape Perplexity threads, bypassing Cloudflare.

**Why stale**: Standalone export script. Not invoked from package.json. Depends on `playwright` (optional dep). If Brian still refreshes Perplexity data manually, this is active. If he's switched to another mechanism or abandoned Perplexity ingestion, it's dead.

**Confidence**: possible (depends on current workflow)
**Blast radius**: zero
**Recommended action**: Ask Brian before removing.

### L8. `scripts/watch-claude-exports.js` and `scripts/watch-claude-code.js`

**What**: File watchers for Claude Desktop exports and Claude Code session captures.

**Why stale**: `watch-claude-code.js` is called by `engine/scheduler/daily-sync.sh` stage 5, so it's still in the scheduler flow. `watch-claude-exports.js` has an npm script entry (`"watch-claude"`) but isn't in the scheduler — probably a dev utility.

**Confidence**:
- `watch-claude-code.js`: active, not stale
- `watch-claude-exports.js`: possibly stale

**Blast radius**: zero for `watch-claude-exports.js`
**Recommended action**: Keep `watch-claude-code.js`. Verify `watch-claude-exports.js` usage with Brian before removing.

### L9. `scripts/embed-local.ts` and `scripts/test-embeddings-local.ts`

**What**: Standalone scripts for running local Nomic embeddings and testing them.

**Why stale**: `embed-local.ts` imports `lib/store-sqlite.ts` and `lib/embeddings-local.ts`. It's a utility that embeds sources on demand. `test-embeddings-local.ts` is a test harness. Neither is in the scheduler or the live MCP path.

**Confidence**: possible (may still be useful utilities)
**Blast radius**: zero
**Recommended action**: Keep unless Brian confirms they're dead.

## Possible cleanup (require Brian's input or more investigation)

### P1. `engine/l3/` — all of it

**What**: The entire `engine/l3/` directory: `entity-resolution.ts`, `hybrid-search.ts`, `invalidate-edges.ts` (untracked/wip), `migrate-bitemporal.ts`, `run-entity-resolution.ts`, `run-l3-upgrade.ts`, `sync-fts.ts`, `types.ts`.

**Why stale**: These are the SQLite-era L3 implementation. Bitemporal edges, BM25/FTS5, hybrid search with RRF, entity resolution across sources, edge invalidation. All of this is being replaced by Graphiti's native capabilities in the new architecture.

**Confidence**: likely stale in the long run, but actively used today
**Blast radius**: **large**. `surfaces/mcp/server.ts` imports `searchSegmentsHybrid` and `hybridGraphSearch` from `hybrid-search.ts`. `engine/l4/graph-enrichment.ts` reads from the `edges` table directly. Removing this directory before the L3Backend refactor is a breaking change.

**Recommended action**: Do not delete in this cleanup pass. Flag for the upcoming L3Backend refactor (Option 4 redesign session). When that session lands, `engine/l3/` goes away entirely.

### P2. SQLite `nodes` and `edges` tables

**What**: The SQLite schema in `lib/store-sqlite.ts` defines tables for the full MIKAI L3 graph: `nodes`, `edges`, plus FTS5 mirrors `fts_nodes` and `fts_edges`.

**Why stale**: Graphiti (Neo4j) will own the knowledge graph. SQLite's role in the post-refactor architecture is L4 state (`threads`, `thread_members`, `delivery_events`) plus the segment cache (`segments`, `fts_segments`).

**Confidence**: likely (stale after refactor, live today)
**Blast radius**: large. Same as P1 — removing these tables breaks the MCP server and L4.
**Recommended action**: Flag for the L3Backend refactor. Drop tables only after the refactor is complete.

### P3. `lib/store-sqlite.ts` — partial cleanup

**What**: The file defines SQLite schema for all of `sources`, `nodes`, `edges`, `segments`, plus helpers.

**Why stale**: Half of it (nodes, edges) will be obsolete after Graphiti is fully wired. Half (segments, sources, L4 tables) stays.

**Confidence**: likely partially stale
**Blast radius**: large (it's the highest fan-in file in the repo — 8 importers)
**Recommended action**: Do not touch in this cleanup pass. Refactor-only candidate.

### P4. `engine/eval/l4-threads-to-label.json`

**What**: 270KB JSON file of candidate L4 threads awaiting ground-truth labels.

**Why stale**: Large data file in the source tree. Not code, not stale per se, just heavy.

**Confidence**: not stale
**Blast radius**: N/A
**Recommended action**: Consider moving to `engine/eval/fixtures/` or gitignoring if the file is regenerated by tooling. Flagged for cleanliness, not removal.

### P5. `YOUTUBE_RECS_PROMPT.md` at repo root

**What**: Untracked markdown file at the repo root with YouTube recommendation prompt strategy.

**Why stale**: Doesn't belong at repo root. Per memory references, it may belong in the CMS project (separate repo).

**Confidence**: possible misplacement, not stale
**Blast radius**: zero
**Recommended action**: Move to `docs/` or move to the CMS project repo. Confirm with Brian.

### P6. `.env.local` Supabase entries

**What**: `.env.local` likely contains `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and possibly `VOYAGE_API_KEY` (if only used for Supabase-era paths) that are no longer needed if the Supabase pipeline is retired.

**Why stale**: Depends on which backend paths are live.

**Confidence**: possible
**Blast radius**: could break live code paths that still require these vars (ingestion pipeline, MCP server's Supabase fallback)
**Recommended action**: Do not remove from `.env.local` until the code paths that read them are removed or refactored.

### P7. `.env.example` outdated

**What**: `.env.example` (596 bytes, dated 2026-03-24) predates the Graphiti adoption and probably doesn't document `DEEPSEEK_API_KEY`, `NEO4J_URI`, `NEO4J_PASSWORD`, or explain `MIKAI_LOCAL`.

**Why stale**: Documentation, out of sync with actual env needs.

**Confidence**: likely
**Blast radius**: zero (it's documentation)
**Recommended action**: Rewrite in the post-cleanup doc refresh pass, alongside the `docs/ARCHITECTURE.md` rewrite. Low priority.

### P8. `engine/ingestion/ingest-cli.ts`

**What**: CLI wrapper around `ingest-direct.ts`. Used via `npm run ingest`.

**Why stale**: Transitive dependency on the broken Supabase ingestion path. If `ingest-direct.ts` is refactored or removed, this goes too.

**Confidence**: possible (depends on ingest-direct.ts decision)
**Blast radius**: small
**Recommended action**: Decide alongside ingest-direct.ts.

### P9. `.omc/` state artifacts inside `infra/graphiti/`

**What**: The `.omc/` directory (from oh-my-claudecode agent state) appears inside `infra/graphiti/`. Already gitignored, but represents agent scratch space that escaped the project root.

**Why stale**: Not stale, just misplaced.

**Confidence**: possible (gitignored, won't affect git)
**Blast radius**: zero
**Recommended action**: Nothing required. Flagged only because it's unusual to see `.omc/` outside the project root.

## Notes on the L4 side

`engine/l4/` is not being cleaned up in this pass. It lives on `feat/l4-testing` with active development, state classification accuracy is below the quality gate, and the domain plugin interface is a live evolution path. Cleanup on the L4 side happens in that branch, on its own timeline. Nothing in `engine/l4/` is a cleanup candidate today, even though `graph-enrichment.ts` will need to be ported to L3Backend when the refactor lands.

## Recommended cleanup order (once approved)

If you approve this list, I suggest executing the cleanup in this order, committing each group separately so blast radius is contained:

1. **Fix the broken state first.** Decide on B1 (rule-engine.ts). Either delete or restore.
2. **Empty directories and obvious experiment artifacts** (C1, C2). Zero blast radius.
3. **One-off scripts** (C3, C4, C5). Zero blast radius.
4. **Verify and remove orphaned lib files** (L1, L2). Grep first, then delete.
5. **Supabase-era build pipeline** (L3, L4, L6). This is a group — `build-graph.js`, `build-segments.js`, the eval scripts, `infra/supabase/`, and `ingest-direct.ts`. Do not split, because they depend on each other. Requires Brian to decide whether to port segment building to SQLite-only or delete entirely.
6. **Doc refresh** — defer to after the L3Backend refactor, since the target architecture isn't fully crystallized yet.
7. **Structural cleanup** (P1, P2, P3) — defer entirely to the L3Backend refactor session. Do not touch in a cleanup-only pass.

## Summary count

- **Broken state needing immediate decision**: 3 items (B1-B3)
- **Certain deletions, zero blast radius**: 7 items (C1-C7)
- **Likely deletions, small-medium blast radius**: 9 items (L1-L9)
- **Possible deletions, requires investigation or Brian's input**: 9 items (P1-P9)
- **Total candidates**: 28 items

Approximately 15-20 of these can be executed today on a cleanup branch with confidence. The remaining 8-13 are either refactor-pass candidates or depend on product direction decisions.
