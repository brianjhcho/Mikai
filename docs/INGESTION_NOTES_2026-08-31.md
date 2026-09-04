# Ingestion Notes — end of 2026-08-31

Written after R5 completed + R6 fired, so state is mid-R6.

## Where we are

Vault: `~/.mikai/wiki-mikai-parallel-test/` (v5, canonical)
Pipeline: nashsu vendored (v0.6.9) headless CLI, MIKAI template, workers=8, `claude-sonnet-4-6` via `claude -p` (subscription auth, no API key)

| dir | R0 (v1 golden) | pre-R5 | post-R5 | now (mid-R6) |
|---|---|---|---|---|
| concepts | 174 | 541 | 678 | 678 (R6 running) |
| entities | 82 | 191 | 248 | 248 |
| sources | 46 | 115 | 143 | 143 |
| wisdom | 12 | 22 | 27 | 27 |
| journal | 27 | 28 | 28 | 28 |
| goals | 9 | 18 | 22 | 22 |
| queries | 21 | 69 | 76 | 76 |

**Rounds completed:**
- R1 (2026-08-15) — 46 hand-curated golden sources
- R2 (2026-08-27) — +13 MIKAI-topic Claude threads via keyword filter
- R3 (2026-08-31) — +15 via Level 3.1 salience scorer
- R4 (2026-08-31) — +7 via Level 3.1 against refreshed wiki-raw
- R5 (2026-08-31) — +28 via Level 4 scorer (added axA/B/C/G axes); 2 failures (Luka roster page truncation, memories `claude -p` transient failure)
- R6 (in flight) — Level 4 top-30 minus R5 dupes = ~11 truly new + 19 cache-hit re-emits

## What's working

**nashsu extraction with MIKAI template + wisdom page-type** — produces coherent concept pages, wisdom collections with attributed quotes, per-source summaries, cross-linked wikilinks. Concept/entity yield per source averages ~4-5 concepts + ~2 entities.

**Level 4 salience scorer** (`eval/r3_candidate_salience.py`) — deterministic pre-ingest ranker. Weighted concept intersection + personal-vocab weighting + goal overlap + 4 axes (retrieval potential, vocabulary novelty, alias risk, episodic vs semantic). Successfully surfaced MIKAI-central + Brian-profile-relevant sources at top of R5 and R6 rankings.

**Retroactive dedup — 3-stage cascade** (blocking → matching → resolution):
- **Stage 1 (blocking):** cheap similarity heuristics on slug + Ollama embed cosine over all pairs (146K pairs at N=541 in ~50s)
- **Stage 2 (matching):** LLM judge on the HIGH-cosine survivors (~33 pairs at cosine ≥ 0.88). Verdicts: MERGE / KEEP / HUB with reasoning
- **Stage 3 (resolution):** retire-not-delete — canonical page rewritten with LLM-synthesized combined body, losing page becomes `retired_to:` redirect
- R5 result: **7 MERGE, 24 KEEP, 2 HUB** (33/33 judged, no PARSE_FAIL or ERROR)
- LLM judgment quality is strong: correctly kept Sharpe/Sortino, high/low voltage, MBTI childhood-type siblings, Dalio cycle sub-mechanisms as distinct. Correctly merged information-asymmetry/asymmetric-information, extended-mind/extended-mind-thesis, too-many-platforms-problem/platform-fragmentation.

**Ollama** — `nomic-embed-text` (768-dim, ~275MB) via brew. 541 concept bodies embedded in 50s. Vector cache at `~/.mikai/wiki-mikai-parallel-test/.embed-cache/`.

## What's broken or deferred

**Write-time embeddings in nashsu (Path A wiring)** — deferred.
Reason: nashsu's embedding path has TWO layers of Rust dependency, not one.
- Provider HTTP (`embedding_fetch`, `embedding_fetch_batch`) — Rust makes the outbound Ollama call. Shimmable via HTTP in Node (~30-60 min).
- Vector store (`vector_upsert_chunks`, `vector_search_chunks`, `vector_delete_page`, `vector_count_chunks`) — Rust runs a LanceDB v2 database. Not trivially shimmable — LanceDB v2 is a Rust-native format.

Real cost: hours to days (three options — ship Rust binary in headless mode, rewrite vector store in Node, or hand-roll SQLite-backed ANN index). Session-7's "deferred to V.006" note underestimated scope. Retroactive post-ingest dedup keeps working meanwhile — treat as the current standard pattern, not a workaround.

**Bridge script's already-check bug** — the general bridge and the R5/R6 bridge script both check `filename in already_files` where `filename` is the scorer's synthetic hash-derived name, which never matches the bridge's disk-filename hash. Result: R6 candidate ranking included ~19 R5 dupes; only a manual slug-substring dedup catches them.
Fix location: `eval/r3_candidate_salience.py` line ~399 — replace exact-filename check with slug-substring match against `raw/sources/*.md` filenames (strip `\d{4}-\d{2}-\d{2}-<slug>-<hash>.md` down to slug, membership check).

**June 2026 apple-note** — failed to bridge in both R5 and R6. Scorer emits title `apple-notes::June 2026` but no exact `source == "apple-notes: June 2026"` record exists in wiki.index that matches the scorer's `earliest_date`. Investigation deferred; probably a title-normalization mismatch (multiple June 2026 notes exist with slightly different display titles).

**R5 residual failures** — 2 sources didn't complete:
- `2026-07-07-building-a-championship-roster-around-luka-in-vancouver-d563a3.md` — one concept page `bbgm-wemby-inverse-slot-rule.md` hit max_tokens truncation the LLM couldn't repair. Source landed 19 other files.
- `2026-03-19-memories-348b68.md` — `claude -p` exited with code 1 (transient LLM failure, likely rate limit). Retried in R6.

## Key architecture decisions from today

**Post-ingest dedup is the standard, not a workaround.** Given the write-time wiring cost, we do dedup retroactively as a bounded phase after each round. Fable's 3 rules apply: retire-not-delete, confidence-banded execution (HIGH ≥ 0.88, MEDIUM 0.80-0.88, LOW 0.72-0.80), feed bodies not descriptions.

**The 3-stage cascade is now the load-bearing pattern.**
Blocking (cheap filter: Ollama cosine over all pairs) → Matching (LLM judge on HIGH pairs only, ~30-50 per round) → Resolution (retire-not-delete + LLM re-synthesis to preserve both bodies' unique claims).

**LLM judge must output BOTH verdict AND direction.** R5's synthesizer used the JSON's default `retire`/`retire_to` (assigned by body-size heuristic) instead of the LLM's stated preferred direction. Pair 5 (`personal-intent-graph` ↔ `intent-graph`) got flipped — LLM said intent-graph should retire, but body-size heuristic said personal-intent-graph should retire. Fixed manually; for R6+ the judge prompt should output `winner: <slug>` and synthesizer must honor that.

**CLI invocation MUST include `--tsconfig src/mikai-cli/tsconfig.json`.** Without it, tsx uses vendor's root tsconfig, path aliases don't apply, every write hits the original Tauri code and fails with `window is not defined`. Setup.sh usage-hint updated today.

**Bash word-splitting is a bad pattern for source lists.** Shell-side `$SRCS` from concatenated filenames can collapse into ONE argument if quoting is wrong or CLI parsing is unusual. Safer: no positional args, let nashsu walk `raw/sources/` and let content-sha256 cache handle deduping the already-processed. Content-hash cache is the load-bearing safety net for re-bridged files.

**Nashsu content-hash cache saves us on re-bridges.** Bridge script overwriting files with identical content = same sha256 = cache hit. Neutralizes the R6 slug-dedup bug that would otherwise cost 2-4 hours of LLM re-runs.

## Ranking-quality observations

**Level 4 scorer produced good top-30 for both R5 and R6.** Highest-concept-density picks (Building MIKAI prototype from PRD, Consolidating architectural decisions, MIKA TECH improving instructions) surfaced correctly. Personal-vocab bonus correctly ranked Brian's own thought-heavy threads above generic perplexity queries. Aggregation bonus (2026-08-31 tuning) prevents single-topic thin sources from crowding out dense multi-topic threads.

**axB (novelty) working** — top rows in R5 and R6 mostly show `axB=1.0`, meaning the ranker is finding sources that introduce new kebab-phrases beyond current concept vocab.

**axC (alias risk) working as a penalty** — Luka basketball thread scored -0.48 (highest alias risk in R5 top-40), correctly indicating overlap with existing basketball/team concepts.

**June 2026 apple-note stack ranking issue** — 13 same-titled Apple notes cluster in mid-table with identical scores because the scorer can't disambiguate them. The apple-notes dedup-by-title in my R5/R6 selection code caps at 1 per title to avoid over-bridging.

## What's on the immediate horizon

**When R6 completes (~30-60 min):**
1. Post-R6 embed dedup pass (~5-10 min) — run Ollama embed on new concepts, cosine over the ~800-concept pool
2. LLM-judge new HIGH pairs (bounded, ~10-15 pairs likely, ~2-5 min)
3. Apply MERGE verdicts + resynthesize canonicals (retire-not-delete)
4. Consider hierarchy induction pass for the 2 HUB verdicts from R5 (create `nt-social-alienation` parent, promote `surplus-allocation` to hub-with-children)

**Before R7:**
- Fix the bridge already-check bug in the scorer (proper slug-substring dedup) — one-line fix, saves the bridge-dupe waste next round
- Investigate June 2026 title mapping — probably needs the bridge to fall back to source-startswith when exact-source doesn't match
- Consider whether R7 should re-refresh wiki-raw (last refresh 2026-08-30, may have more post-Aug-30 threads by then)

**Longer horizon (real engineering task):**
- Wire write-time dedup properly — decide between (a) shipping Tauri Rust binary headlessly, (b) Node-native vector store rewrite (hnswlib-node or SQLite+FAISS), or (c) accepting post-ingest as permanent standard
- Hierarchy induction pass (Louvain over wikilink graph + LLM cluster naming + parent hub creation) — the 24 KEEP verdicts from R5 that are parent/child relationships suggest hierarchy is undermodeled currently

## Metrics summary

R5 (end-to-end):
- 29 sources bridged, 27 landed cleanly, 2 failed
- +137 concepts (from 541 → 678, ratio 4.7 concepts/source)
- +57 entities (2 per source)
- +26 per-source summaries
- +5 wisdom pages (from 22 → 27)
- Ingest wall-clock: ~40-70 min at workers=8 (best: 0s cache-hit; worst: 906s = 15min for Alocasia 211KB/111-turn thread)
- Dedup wall-clock: ~10 min (Ollama embed ~50s + 33 LLM judge + 7 resynthesize)
- 7 dupes merged, vault effective concept count = 671 (678 - 7 redirects)

R6 (in flight): ~11 truly new sources + 19 R5-dupe cache-hits. Expected +40-60 concepts.
