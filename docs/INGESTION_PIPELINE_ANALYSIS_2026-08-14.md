# Ingestion Pipeline — 2026-08-14 Analysis Bundle

> **What this file is:** Preserved record of the two Fable-5 analyses run today (architecture + retrospective), the truncation-oversight finding, and the ranked fix plan. Complements `docs/DECISIONS.md` (ADRs) with the narrative + reasoning behind them.

## Timeline of today's work

- **09:00** — Parallelism-safety A/B test: same 50 sources, `N_WORKERS=1` vs `N_WORKERS=8` in isolated `MIKAI_WIKI_DIR` vaults. Result: 8.04× speedup, structurally safe.
- **09:15** — Option A migration: flat `sources/` (166 buckets → 0), category demoted to frontmatter metadata.
- **09:30** — First chain run (5 batches × 200): fresh200 + backfill_0/200 succeeded; backfill_400/600 + fresh_1920 hit quota exhaustion mid-batch and returned 0/200. Chain runner had no fail-fast; burned 75 min firing doomed calls.
- **14:00** — Chain runner patched with fail-fast + probe-then-fire. Restart chain (6 batches, incl. retries for 41 missed sources) ran clean in 72 min.
- **15:15** — Session end state: 1,108 → 2,115 sources · 143 → 482 concepts · 199 → 1,396 cache · 166 → 0 bucket subdirs.
- **16:00-17:00** — Two Fable-5 architect analyses: target architecture + session retrospective.
- **17:30** — Discovered `MAX_EXCERPT=4000` truncation oversight during nashsu code verification for P3 fix design.

## Fable 5 — Target Architecture Analysis (2026-08-14 09:20)

### The five problems (P1-P5), disambiguated

- **P1 — Fidelity.** Wiki page accurately represents source. **Structurally capped**: Pass 2 Generation never sees the source body, only Pass 1's compressed JSON. Overview prose is synthesis-of-a-synthesis. `smoke_ingest_v2.py:173-176`. Fix: give Pass 2 the excerpted body.
- **P2 — Placement.** `## Touches` has high precision/recall. **Rich-get-richer biased**: Analysis only sees top-40-by-salience concept directory. At 482 concepts, top-40 = 8% of vocabulary. `smoke_ingest_v2.py:391-395`. Fix: full slug directory (~1k tokens, affordable via prompt cache).
- **P3 — Segmentation.** Multi-topic notes fragment appropriately. **Owner: nobody.** `MAX_EXCERPT=4000` truncates all source types uniformly. Fix: chunk-and-consolidate for long sources (see nashsu constants below).
- **P4 — Vocabulary stability.** Rerun yields same slugs. 7% overlap between arms (n≈45 pair). Mitigation is codomain constraint + SHA-cache write-once, not temperature (unavailable via `claude -p`).
- **P5 — Cluster legibility.** Louvain territory. Dropped from write-side — it's a graph-view diagnostic, not a placement mechanism.

Coupling: P2 depends on P4 (can't link into unstable vocabulary), both depend on P3 (multi-topic blob links poorly to everything).

### Classical patterns still load-bearing

Medallion (bronze/silver/gold) maps one-to-one: `wiki-raw/` = bronze, `sources/` = silver, `concepts/` = gold. Event sourcing holds: `wiki.md` is the event log; sources/concepts are projections. Kappa beats Lambda (SHA cache = dbt incremental). Actively harmful: schema-on-write typed extraction (Stage 6 lesson), ETL-style prose normalization.

### LLM-era breaks and mitigations

Determinism → codomain constraint + write-once cache. Cheap re-runs → prompt-versioning + SHA cache. Testable transforms → golden-set evals (LangChain/LlamaIndex converged here). Schema stability → code owns frontmatter, LLM emits prose only. Incremental composability → accept within-batch staleness, let dream pass reconcile.

### Segmentation reality (corrected 2026-08-14 evening)

Both Karpathy and nashsu treat "one source" as atomic and rely on placement (routing to multiple concept pages) for topic distribution. Neither pre-splits by topic or source type. Fable's earlier "stream-typed splitter registry" was extrapolation, not lifted pattern.

**Karpathy** (llm-wiki.md gist, 2026-04-04): "A single source might touch 10-15 wiki pages." No chunk size, no source-type differentiation. Punts segmentation to implementer.

**nashsu** (`src/lib/ingest.ts`): chunks ONLY on context-window overflow, not by topic:
```
LONG_SOURCE_MIN_BUDGET             = 8_000
LONG_SOURCE_MAX_SINGLE_PASS_BUDGET = 300_000
LONG_SOURCE_CHUNK_MIN              = 12_000
LONG_SOURCE_CHUNK_MAX              = 60_000
LONG_SOURCE_DIGEST_MAX             = 15_000
LONG_SOURCE_CHUNK_ANALYSIS_MAX     = 40_000
```

Trigger: `if (enrichedSourceContent.length > sourceBudget)` → `analyzeLongSourceInChunks` splits into 12k-60k chunks, analyzes each, consolidates into merged `sourceContext`, then feeds Generation.

## Fable 5 — Session Retrospective (2026-08-14 15:45)

### What today proved vs. hypothesized

- Parallelism safety: sharper than hypothesized (8.04× near-linear).
- Bucket sprawl: solved by construction as predicted (166 → 0 via flatten).
- LLM nondeterminism dominates slug drift: confirmed but squishy (n≈45).
- Quota constraint: much sharper than assumed — quota is a *mid-flight failure mode*, not a budget line. Chain runner without fail-fast burned 75 min on doomed calls.
- Two-step pipeline reliability: 997/1000 succeed after retries. Exactly 1 deterministic-fail source out of ~1,200 (0.08%).

### Five most consequential insights (ranked)

1. **Control plane is the bottleneck, not the LLM.** Everything that went wrong today was orchestration — no fail-fast, no quota probe, no persistent retry state. The passes themselves ran at 96-100%. Chain runner graduates from scratchpad to owned infrastructure.
2. **SHA cache is reliability, not just cost.** Retries were nearly free (retry_1720: 9 recoveries in 92s). Cache-skip converts 96% first-pass into 99.9% corpus. Treat "rerun the window" as standard recovery.
3. **The 25-min cold-start cluster is a structured-output problem the platform has solved.** `claude -p --json-schema` exists; API has Structured Outputs beta. Our wrapper silently ignores `json_mode=True` (`infra/mikai_llm/__init__.py:225-228`). Wiring it deletes the parse-failure class in one move.
4. **Nondeterminism is contained at write, but pressure moved to review.** ~3,000 new inbox items today, 8,391 total lines. Vocabulary problem is no longer "will slugs drift" but "who adjudicates the inbox" — nobody does currently.
5. **Backfill is now a scheduling problem.** 200 sources ≈ 20-24 min at 8 workers → full 19k corpus ≈ 30-38h chopped into quota windows. Cron + probe + fail-fast = corpus finishes itself in ~2-3 weeks of idle time.

### Convergence with state of the art

- Two-step Analysis+Generation: **table stakes** (nashsu 16.4k★ identical, claude-mem ~65k★ multi-stage). Graphiti v0.29.0 collapsed then re-split — emerging rule: "pass boundaries follow failure modes."
- SHA-cache incrementality: **table stakes** (nashsu identical).
- Parallel workers over shared state: **we're ahead** (nashsu is serial-queue) — but nashsu has crash recovery + retry state; we don't. They have durability, we have throughput; we need both.
- Dedup-on-write: **we're ahead** — Cognee issue #3629 is still designing LLM-judge canonicalization; our `find_near_duplicate_concept` is live.
- Flat file substrate: matches nashsu + Karpathy. We lack a first-class `index.md` catalog.

### Divergence, and whether it's right

- **Graph abandonment**: today's evidence supports it. mem0 v3 deleted ~4k lines of graph store code (PR #4805, 2026-04-14) for spaCy entity-linking. We got 482 cross-linked concept pages with zero graph infra. mem0's hosted platform kept the graph — asymmetry: graphs survive where ops cost is amortized by a company. Single-user substrate: files won.
- **DSPy self-improving pipelines**: distraction. Real-world pattern is offline prompt tuning (arXiv 2507.03620), then paste. Skip framework, keep the accidental asset: `MIKAI_WIKI_DIR` cloned-vault harness is the eval loop offline optimization needs.
- **Auto-mint vs. Karpathy's approval gate**: 339 concepts auto-minted today. Necessary at batch scale, but 8,391-line inbox is the deferred bill.
- **Hallucination guards**: Graphiti v0.29.1 added 250-char attribute caps + schema-echo defenses. We have only frontmatter-presence check (`smoke_ingest_v2.py:234-237`). Behind here.

### Category-level takeaways (mid-2026)

- **Table stakes settled**: immutable raw layer, content-hash incrementality, multi-pass LLM shaping, markdown-file substrate, local search. Everyone converged independently.
- **Still fundamentally hard**: vocabulary/entity canonicalization at scale (Cognee open, Graphiti degrades, our inbox); quota-bound control plane (nobody ships good backpressure); evaluation (nobody has a fitness function for "is the wiki good").
- **Two-axis fragmentation**: graph vs. files (Zep doubled down; mem0/Karpathy/nashsu/us went files) + human-gated vs. auto-write.
- **Quiet shift**: reliability engineering has displaced extraction cleverness as the differentiator. Today was 90% ops, 10% quality. That ratio is the finding.

## The MAX_EXCERPT=4000 oversight (discovered 2026-08-14 evening)

**Root cause**: constant set during MVP single-call smoke tests, inherited by two-step v2 without re-evaluation, no principled connection to Sonnet's ~200K token / ~800K char context capacity.

**Empirical impact**: for the Frostpunk source (103,858 bytes), LLM only saw first 4,000 chars = ~96% content invisible. Applies to every source over 4KB — including all substantial Claude threads, Perplexity threads, long notes. Overview/Touches/category all derived from truncated slice; `## Body` preserves raw content for humans but LLM never reasoned over it.

**Corrected framing**: this is NOT a segmentation-by-topic problem. Both Karpathy and nashsu treat source as atomic + let placement fan out to multiple concept pages. What we lack is **context-overflow chunking**. Nashsu handles it via `analyzeLongSourceInChunks` with 12k-60k chunk sizes and consolidation.

**Fix path**:
1. Raise `MAX_EXCERPT` from 4000 to 12000 (matches nashsu `LONG_SOURCE_CHUNK_MIN`). One-line change. Recovers content for sources up to ~40k chars.
2. For sources > 40k: port nashsu's `analyzeLongSourceInChunks` pattern — split into 12k-60k pieces, run Pass 1 per chunk, consolidate into merged sourceContext, single Pass 2. Recovers 100% of long-source content.
3. NO source-type dispatch — treat everything uniformly (per Karpathy + nashsu).

## Ranked fix plan (final order after truncation-oversight)

1. **A — `--json-schema` on Pass 1** (`infra/mikai_llm/__init__.py`). ~30-60 min. Deletes 25-min cold-start + JSON parse-fail class. Test streaming compat first (`--output-format stream-json` + `--json-schema` interaction unverified).
2. **C+ — Pass-2-sees-body + MAX_EXCERPT→12k + code-owned frontmatter** (`smoke_ingest_v2.py`). ~half day. Highest fidelity lift; closes broken-link bug in `_write_source_file_from_llm`.
3. **P3 chunk-and-consolidate for sources > 40k** (new). ~half day. Port nashsu's `analyzeLongSourceInChunks`. Recovers full content of long sources.
4. **D — Full 482-slug directory in Pass 1** (`smoke_ingest_B.py:72-108`). ~30 min. Removes rich-get-richer placement bias.
5. **A/B measurement** on 50-source isolated vaults, Fable-fixed vs current. ~1 hour. Prove lift before committing quota to more ingest.
6. **B — Persistent ingest queue** (nashsu-style, replacing chain scripts). ~1 day. Crash recovery, per-source retry state, quota backoff. Kills the class of orchestration failures we saw today.
7. **E — Inbox triage LLM-judge pass** (consolidate 8,391 lines into mint/merge/drop). ~half day. Prevents inbox from becoming a landfill.
8. **Poison-pill lane** — quarantine the 1 deterministic-fail source after N failures instead of retrying forever. Trivial.

Total: ~3 days focused work + measurement, then resume backfill on improved pipeline for remaining 92.7% of corpus.

## Session artifacts (preserved for future reference)

- Backup: `~/.mikai/wiki-backup-2026-08-14-0828/` (pre-chain snapshot)
- Test vaults (parallelism A/B): `~/.mikai/wiki-test-{serial,parallel}/`
- Logs: `/tmp/mikai_test_logs/{serial,parallel,fresh200,backfill_*,retry_*,fresh_1920*,chain_restart}.log`
- Scratchpad code: `smoke_ingest_v2.py` (patched flat-write), `smoke_ingest_B.py` (patched flat-write), `run_parallelism_test.py`, `dedup_source_files.py`, `chain_ingest.sh`, `chain_restart.sh`

## Adversarial pass (from Fable §7)

- 8.04× speedup is one 50-source run. Larger batches under quota throttling could compress it.
- 7% slug divergence is n≈45, single pair. Ranking of "nondeterminism dominates" could reshuffle after structured outputs remove parse noise.
- `--json-schema` compat with our streaming wrapper is untested. Verify before betting improvement #1 on it.
- 5-hour quota window is inferred from one exhaustion event. Older strata may fail at higher rates than today's 0.08% deterministic-fail rate.
- Karpathy gist doesn't prescribe chunking. Our nashsu-port isn't the only defensible design; the "stream-typed splitter" Fable proposed earlier isn't lifted from either reference and would be MIKAI-original if we pursued it.
