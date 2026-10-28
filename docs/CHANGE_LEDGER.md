# MIKAI Change Ledger

**Purpose:** append-only record of every operational mechanism (hook, script, MCP server, config change) added to MIKAI. Complements `docs/DECISIONS.md` (architectural decisions) by capturing the *reversibility* half: what a mechanism does, how to undo it, and what to watch for.

**Discipline:** every new mechanism gets an entry BEFORE it lands. Approval by Brian is approval of the ledger entry, not just the proposal. Written this way so a future session (or Brian in six weeks) can audit "why is this here" without reading git log + memory.

**Format per entry:**
- **Date, Files, Plain-English** (what it does when it fires)
- **Why** (problem solved + why this approach)
- **Blast radius** (what breaks if misbehaves)
- **Approver said** (Brian's approval words, quoted)
- **Revert** (exact command)
- **Watch for** (predicted failure modes)

---

## CHANGE-001: Alias-table bootstrap (CANON-1)
**Date:** 2026-09-13 · **Files:** `infra/nashsu/bridge/build_aliases.py`
**Plain-English:** One-shot Python script. Walks `wiki/concepts|entities|wisdom/*.md`, finds retire stubs (pages with `retired_to:` frontmatter), extracts each stub's title + slug, writes those as `aliases:` frontmatter on the canonical target page. Also emits `wiki/.aliases-index.json` — flat `{alias_slug: canonical_slug}` map for runtime lookup.
**Why:** 22 retire stubs existed in the vault (from prior R5 dedup passes) but the winner pages didn't advertise their aliases. Canonicalization needs a lookup index to route new mentions correctly. Bootstrap makes the alias map self-describing on disk.
**Blast radius:** Modifies frontmatter of 22 canonical pages in `~/.mikai/wiki-mikai-parallel-test`. No production vault writes. Idempotent (adding same alias twice is a no-op due to sorted-set dedup).
**Approver said:** "Do all 3" (approving the whole CANON-1..4 plan)
**Revert:** `git checkout <pre-9/13-SHA> -- infra/nashsu/bridge/build_aliases.py` + regenerate the vault's aliases by removing `aliases:` lines from the 22 canonical pages + deleting `wiki/.aliases-index.json`. Reversible via retire stub → canonical mapping (still on disk).
**Watch for:** Alias collisions if two retire stubs point to different canonicals with same title. Detected at build_aliases run time (would warn on stderr).

---

## CHANGE-002: Canonicalization hook (CANON-2)
**Date:** 2026-09-13 · **Files:** `infra/nashsu/bridge/canonicalize.py`, `infra/nashsu/cli/ingest.ts`, `infra/nashsu/vendor/src/mikai-cli/ingest.ts`
**Plain-English:** After each source's ingest completes, the CLI wrapper spawns `canonicalize.py` per newly-written knowledge page. That script runs 3-tier resolution: (1) exact alias match, (2) embedding kNN via Ollama over existing pages, (3) LLM adjudication only when kNN finds candidates ≥ cosine 0.75. If a match is found, the just-written page is retired as a redirect stub + its body appended to the canonical + the proposed slug added to canonical's `aliases:`. Verdict logged to `.canonicalization-log.jsonl` with archive copy in `.canonicalization-archive/`.
**Why:** Prevents duplicate concept-slug creation at ingest time (the "link-at-birth" mechanism, per `docs/CONSOLIDATION_ARCHITECTURE.md` §5a Wikipedia-redirect model). Without this, every new source could mint a synonym of an existing canonical.
**Blast radius:** Modifies vault state per-ingest. Kill switch: `MIKAI_CANONICALIZE=0` env var OR `--no-canonicalize` CLI flag. Fully reversible via `canonicalize_undo.py` (byte-identical round-trip verified).
**Approver said:** "yes implement the elegant minimum" (approving canonicalization as the write-time mechanism)
**Revert:** `git revert <SHA-of-CANON-2-commit>` + run `canonicalize_undo.py --last N` per log entry to reverse applied merges.
**Watch for:** Tier-3 LLM adjudication timeouts (180s per page). False-positive merges (LLM says merge when concept is actually distinct). Cost: bounded to ≤1 `claude -p` call per newly-written knowledge page, only when tier-2 finds candidates.

---

## CHANGE-003: Aliases feed forward into pre_extract_topk (CANON-3)
**Date:** 2026-09-13 · **Files:** `infra/nashsu/bridge/pre_extract_topk.py`
**Plain-English:** Extended `load_page_metadata()` to include each canonical's `aliases:` list. Neighbor block emitted before extraction now shows `[[concepts/foo]] — Foo Title (cosine 0.892) (also: alias1, alias2)` inline. LLM reading the extraction prompt sees the aliases and routes mentions accordingly.
**Why:** Closes the loop between CANON-1's alias bootstrap and the LLM's slug-choice decisions during generation. Without this, the LLM only sees canonical titles — misses "intent-graph" → `personal-intent-graph` synonym unless it hits the alias-index at write time.
**Blast radius:** Adds ~50-200 chars to the extraction prompt per source. No LLM cost change (prompt already includes the neighbor block).
**Approver said:** "Do all 3"
**Revert:** `git checkout <pre-9/13-SHA> -- infra/nashsu/bridge/pre_extract_topk.py`
**Watch for:** Alias contamination if `build_aliases.py` wrote noisy aliases (e.g., Swahili-translated stub titles). Currently benign (append-only), but if it grows large, prompt tokens balloon.

---

## CHANGE-004: Canonicalization undo tool (CANON-4)
**Date:** 2026-09-13 · **Files:** `infra/nashsu/bridge/canonicalize_undo.py`
**Plain-English:** Reads `.canonicalization-log.jsonl`, reverses individual entries: restores loser file from `.canonicalization-archive/`, strips fenced merge-block from canonical body via regex, removes exact alias set (per logged `aliases_added` field) from canonical frontmatter + `.aliases-index.json`. Byte-identical round-trip verified against test canary.
**Why:** Reversibility guarantee. Every write from canonicalize.py has an undo path.
**Blast radius:** Modifies vault state (reverses prior CANON-2 applications). `--dry-run` supported.
**Approver said:** "Do all 3"
**Revert:** N/A — undo tool itself is idempotent; deleting the script has no effect on vault.
**Watch for:** Undoing a CANON-2 merge won't reverse the subsequent SessionStart hook's cache. If the same source is re-ingested, canonicalize.py may re-fire and re-apply.

---

## CHANGE-005: Accretion mechanism (CANON-5) — PARKED
**Date:** 2026-09-16 (built), NOT APPLIED · **Files:** `infra/nashsu/bridge/accrete.py`
**Plain-English:** Per-source LLM-adjudicated density enrichment. For each canonical the source wikilinks to, cosine-gate at 0.55, then LLM decides whether the source has NEW material about the concept. If yes, appends a synthesized paragraph to the canonical (fenced, reversible, source-cited).
**Why:** Density criterion (2) of consolidation completeness. Canonicalization handles duplicate slugs but not "same-concept fresh-angle" content. Accretion fills that gap.
**Blast radius:** Would add up to top-N=5 LLM calls per source (~4-5 min extra ingest time). PARKED because: (a) not in stated architecture (CONSOLIDATION_ARCHITECTURE.md doesn't specify accretion as a separate mechanism), (b) per your 2026-09-17 directive "don't diverge from stated architecture until measurement justifies."
**Approver said:** Approved BUILD ("Do all the tasks"), then implicit PARK via "I don't want to diverge aggressively from the Nashsu or the karpathy architecture."
**Revert:** N/A (never applied). If accretion is applied later: build an `accrete_undo.py` mirror of CANON-4 first.
**Watch for:** If someone runs `accrete.py --apply` without knowing it's parked, the vault gains LLM-authored content. Prevention: leave the CLI flag `--dry-run` as the default? (Currently defaults to apply.) Consider a `MIKAI_ACCRETE_UNPARK=1` guard.

---

## CHANGE-006: Referential integrity measurement (CANON-7)
**Date:** 2026-09-16 · **Files:** `infra/nashsu/bridge/referential_integrity.py`
**Plain-English:** Measurement-only. Sweeps every page's body for bare-text mentions of known canonical titles/aliases; reports the fraction that are wikilinks vs bare. Baseline: 51.78%.
**Why:** To test whether Fable's audit claim ("SLUG DISCIPLINE replaces enrichWithWikilinks") was correct. It wasn't — 48% of mentions are bare.
**Blast radius:** Zero. Read-only, no LLM calls, ~4 min sweep of ~2000 pages.
**Approver said:** "Do all the tasks"
**Revert:** `rm infra/nashsu/bridge/referential_integrity.py` — no state.
**Watch for:** Regex false-positives inflate bare-mention count. The 51.78% is a lower bound; real rate may be 55-65%.

---

## CHANGE-007: Deterministic bare-mention wrapping (CANON-8)
**Date:** 2026-09-17 · **Files:** `infra/nashsu/bridge/wrap_bare_mentions.py`
**Plain-English:** Zero-LLM mechanical pass. Walks pages, finds unambiguous whole-word matches to canonical titles/aliases, wraps them in `[[]]`. Skips code fences, headers, existing wikilinks. Caps at 3 wraps per (page × canonical) to avoid oversaturation. Logs to `.link-wrap-log.jsonl` + archives originals to `.link-wrap-archive/`.
**Why:** Closes the referential integrity gap CANON-7 measured. Fable was right to remove per-page LLM enrichment (cost); wrong to assume prompt guidance covered the mechanical job. This IS the mechanical job.
**Blast radius:** APPLIED 2026-09-17: 1669 pages modified, 8496 wraps added. Referential integrity 51.78% → 72.46%. Fully reversible via `.link-wrap-archive/`.
**Approver said:** "Apply Canon 8"
**Revert:** For each entry in `.link-wrap-log.jsonl`: restore corresponding file from `.link-wrap-archive/`. No `wrap_undo.py` exists yet — build if needed.
**Watch for:** Wraps inside partial-word contexts if regex `\b` fails on edge cases (unicode word boundaries, hyphenated compounds). Spot-check a sample of wrapped pages for readability.

---

## CHANGE-008: Headless MCP server v1 (`mikai-wiki-v1`)
**Date:** 2026-09-20 · **Files:** `infra/mikai-mcp/` (package: `src/index.ts`, `src/vault.ts`, `src/search.ts`, `src/chat.ts`, `package.json`, `tsconfig.json`, `README.md`)
**Plain-English:** Sibling to nashsu's `llm-wiki-mcp-server` but Desktop-independent. Reads the vault directly from disk. Six MCP tools: `mikai_wiki_status`, `mikai_wiki_search` (semantic kNN via Ollama), `mikai_wiki_read_file`, `mikai_wiki_list`, `mikai_wiki_graph`, `mikai_wiki_chat` (RAG via `claude -p`). Client points at any vault via `MIKAI_WIKI_ROOT` env var.
**Why:** Nashsu's MCP requires the Desktop app running. Headless retrieval was blocked without this. New mechanism scoped to READ-side; doesn't touch ingest/consolidation architecture.
**Blast radius:** Runs as a Node.js subprocess when Claude Code launches. Costs a few MB RAM. Read-only for v1 — no vault writes.
**Approver said:** "Set up the MCP for the headless" (implicit approval when asking to activate it)
**Revert:** `rm -rf infra/mikai-mcp/` + remove the entry from `~/.claude.json` mcpServers.
**Watch for:** Ollama unreachable → semantic search falls back to lexical (bounded degradation). `claude -p` timeout on chat → returns partial result. If vault has >10K pages, search may become slow (currently brute-force cosine).

---

## CHANGE-009: SessionStart hook + branch manifest infrastructure
**Date:** 2026-09-27 · **Files:** `.claude/settings.json`, `.claude/hooks/session-start-branch-context.sh`, `docs/branches/feat-pure-file-brain.md`, `CLAUDE.md` (branch context + docs router refresh + do-not lines), `.gitignore` (un-ignore `.claude/settings.json` + `.claude/hooks/`)
**Plain-English:** On every session start, the hook shell script runs `git branch --show-current`, looks for `docs/branches/<branch>.md`, greps its `**Constitution:**` line, and emits a JSON `additionalContext` reminder. Also audits `docs/*.md` vs CLAUDE.md's router table; flags unrouted docs as a system-reminder. Fires in every worktree launch (Superset, tmux, terminal — identical).
**Why:** Combat two failure modes: (a) drift into recency bias without re-anchoring to the branch constitution, (b) discoverability decay as new docs accumulate unrouted.
**Blast radius:** Adds ~500-800 tokens to the session start context. If the shell script fails silently, no injection happens (fail-open — session proceeds normally). Only touches per-session context, not any persistent state.
**Approver said:** "yes implement the elegant minimum"
**Revert:** `git revert 08adfd6 c090eef 23c3f3f` (three commits: the SessionStart hook, the gitignore un-ignore, the CLAUDE.md + manifest additions).
**Watch for:** 28 unrouted docs currently flagged — the noise repeats every session until addressed (see CHANGE-011). If Anthropic changes SessionStart hook schema, the shell script may break silently.

---

## CHANGE-010: PreCompact hook (added then reverted)
**Date added:** 2026-09-27 (23c3f3f) · **Date reverted:** 2026-09-27 (08adfd6)
**Files touched:** `.claude/hooks/pre-compact-preserve-context.sh` (deleted), `.claude/settings.json` (PreCompact entry removed)
**Plain-English:** Was supposed to inject branch manifest reference into the compact summary. Reverted because CLAUDE.md's Branch context section is part of the system prompt (not the conversation history being compacted), so it survives compaction unchanged. The hook was redundant.
**Why reverted:** You caught the redundancy: "when we compact, claude auto compacts and then retrieves from memory again."
**Approver said:** "Option A" (drop PreCompact entirely)
**Revert of revert:** N/A — this entry documents that the hook was tried and dropped. Do not re-add without demonstrating what CLAUDE.md's routing can't cover (per Anthropic issue #43733: session-specific state like open TaskCreate list or approved-this-session decisions).
**Watch for:** Future proposals to re-add PreCompact should be measured against "does this preserve state CLAUDE.md can't?" before landing.

---

## CHANGE-011: Router freshness — 28 unrouted docs flagged (OPEN)
**Date flagged:** 2026-09-27 · **Files:** `CLAUDE.md` (docs router), various `docs/*.md`
**Plain-English:** The SessionStart hook's freshness audit reports 28 docs that exist under `docs/` but aren't referenced in CLAUDE.md's docs router table. Sample: `SALIENCE_FORMULA.md`, `DREAM_WIKI_RUNTIME.md`, `RETRIEVAL_STACK.md`, `SEGMENTATION_FRAMEWORK.md`, `SURFACE_ENGINE_DECISION.md`, `USER_CONTEXT_SUBSTRATE.md`, `STAGE-5-OAUTH-PLAN.md`, and 22 more.
**Why:** Discoverability decayed over 6 months as docs accumulated post-March. Some are current-architecture (should route), some are session-artifact / archived (should move to `docs/research/`).
**Blast radius:** No runtime cost — just my ability to find these docs. Their content is fine on disk.
**Approver said:** "Let's do all 4" (approving triage as part of the four-task cleanup).
**Revert:** N/A — this is remediation work, not a mechanism.
**Watch for:** Same category of drift will recur without ADR-template discipline (per CLAUDE.md do-not rule added 2026-09-27: every new ADR must checkbox "router updated ☐").

---

## CHANGE-013: Write-time semantic gate (ARCH-034) — BUILT, NOT WIRED
**Date:** 2026-09-11 (built), NOT APPLIED · **Files:** `infra/nashsu/bridge/write_time_gate.py`, `infra/nashsu/bridge/test_write_time_gate.py`
**Plain-English:** Two-tier gate that intercepts nashsu's stage-1 GENUINELY-NEW mentions before stage-2 writes them. Tier 1 (cosine ≥ 0.95) hard-redirects deterministically, no LLM. Tier 2 (0.85-0.95) calls `claude -p` to adjudicate MERGE-into-existing vs KEEP-as-new. Tier 3 (<0.85) passthrough. Report-only against the vault; produces a decisions JSON that the ingest.ts caller would rewrite the analysis text with. Never wired into ingest.
**Why:** ARCH-034 answers O-050 (mention-level compression) with a two-tier design that avoids the ~30% false-positive rate the single-threshold probe had. Was built to validate the approach; validation-only chunk 2 test never fired.
**Blast radius:** Zero at rest (report-only, not called from ingest.ts). If wired: adds one Ollama embed per proposed mention + one `claude -p` per tier-2 candidate. Degrades to Tier 3 passthrough if Ollama unreachable — never blocks ingest.
**Approver said:** N/A — built during the O-050 investigation, not landed as a mechanism.
**Revert:** N/A (never applied). If wired later: kill switch via `MIKAI_GATE_TIER2_LLM=0` disables tier-2 LLM; removing the wiring in `ingest.ts` disables the whole gate.
**Watch for:** Tier-2 false-positives (LLM says MERGE when concepts are related-but-distinct — the 28.9% hit-rate at cosine ≥ 0.85 was 30% false-positive on the initial probe). **Unpark contract:** validate on chunk 2 (91 Claude threads) with success bar <15 new HIGH-cosine pairs post-ingest; if passed, wire into ingest.ts + add CHANGE-013b entry on activation.

---

## CHANGE-014: Post-hoc dedup apply tool (apply_dedup.py) — DOWNGRADED per D-068
**Date:** 2026-09-14 (built) · **Files:** `infra/nashsu/bridge/apply_dedup.py`
**Plain-English:** Two-phase R5 dedup applier. Phase `judge`: read-only, asks `claude -p` MERGE/KEEP/HUB per HIGH-cosine pair from a prior dedup report, writes incremental verdicts JSON (safe to re-run). Phase `apply`: destructive, backs up vault as tarball, LLM-merges MERGE-pair bodies into canonical, writes retire stub for loser with `retired_to:` frontmatter. Never deletes — retire stubs are the reversibility record.
**Why:** Was the primary compression mechanism before canonicalization (CANON-2) landed. D-068 downgrades it: post-hoc dedup is now a safety net that runs periodically, not the primary path. Canonicalization at write time catches ~12% of proposed pages before they mint duplicates; apply_dedup handles the residual.
**Blast radius:** Modifies vault state on `--phase apply` (only when explicitly invoked). Vault-tarball backup written before any change. Inbound wikilinks still point at retired slugs — needs `rewrite-retire-stubs.ts` follow-up (documented in the script's `--help`).
**Approver said:** Built during R5 pass; approved implicitly ("do all the tasks"). D-068 downgrade approved via "canonicalization is now the primary mechanism."
**Revert:** Restore vault from the tarball written at apply-time. Per-verdict undo not implemented (unlike `canonicalize_undo.py`).
**Watch for:** LLM-authored merged body diverges from the two source bodies in ways that neither reviewer notices. Run against a subset first; spot-check merge quality. **Unpark contract:** if canonicalization catch rate drops below 8% or corpus grows past 3000 pages, re-evaluate whether apply_dedup should run as a scheduled safety-net cron (currently manual).

---

## CHANGE-015: Dream pass — periodic cluster consolidation (dream_pass.py) — BUILT, NO CRON
**Date:** 2026-09-15 (built) · **Files:** `infra/nashsu/bridge/dream_pass.py`, `infra/nashsu/bridge/dream_pass_sample.py`
**Plain-English:** ARCH-035 production dream pass. Louvain community detection over the wikilink graph, then per-community LLM adjudication (`claude -p`) proposing consolidation moves. Handles oversized "blob" communities (50+ pages) via recursive Louvain sub-clustering + embedding k-means fallback. Report-only: emits a markdown report + verdicts JSON with an inert `apply_plan`. No apply-phase written.
**Why:** ARCH-035 crystallization principle needs a periodic pass that catches concepts which SHOULD be one canonical but weren't caught at write time (canonicalization gets slug-similar pairs; dream pass gets structurally-clustered pairs the ingest LLM missed). Sample script (`dream_pass_sample.py`) was the proof-of-concept for one Louvain level; `dream_pass.py` adds the recursion needed for real-scale communities.
**Blast radius:** Zero at rest (report-only, never called on a schedule). If run manually: one Louvain pass + N `claude -p` calls per community (bounded by --max-clusters). Never writes to the vault.
**Approver said:** N/A — built during the ARCH-035 design pass, not landed as a scheduled mechanism.
**Revert:** N/A (report-only, no state to reverse).
**Watch for:** Recursive Louvain on very-dense communities can loop or produce degenerate partitions — the max-recursion + k-means fallback are the guards. LLM adjudication quality on 15-page communities is untested at scale. **Unpark contract:** run against the current vault, inspect the report, decide whether apply-phase is worth building. If yes: (a) build `dream_pass_apply.py` mirroring `canonicalize.py`'s archive+log pattern, (b) schedule as weekly cron, (c) add CHANGE-015b on activation.

---

## CHANGE-012: mikai-wiki-v1 search — live-embed on cache miss (fix)
**Date:** 2026-09-28 · **Files:** `infra/mikai-mcp/src/search.ts`, `infra/mikai-mcp/dist/src/search.js` (rebuilt)
**Plain-English:** Replaces the silent `continue` on cache-miss in `semanticSearch()` with a `loadOrEmbed()` call — same helper already used for the query itself and mirroring `dedup_embed.py`'s convention. If a page's cached embedding is missing (because its body was modified after the last embed pass), the search now embeds the current body via Ollama, caches it, and includes the page in scoring instead of skipping it.
**Why:** Bug found 2026-09-27 when `mikai_wiki_search` for "MIKAI intent graph" returned semantically-adjacent pages but not `personal-intent-graph` itself. Root cause: canonicalization + CANON-8 wrap modified `personal-intent-graph.md`, invalidating its cached SHA-keyed embedding, and the search silently skipped it. Bias direction was bad — most-worked-on pages became least-findable. Fix restores expected behavior.
**Blast radius:** First search after a large edit gets slower by (missing-page count × ~200ms Ollama latency). Second search hits cache. On a static vault, no change vs prior behavior. If Ollama is unreachable, the outer try/catch on the query-embed step falls back to lexical search unchanged.
**Approver said:** "fix it" (2026-09-28)
**Revert:** `git revert <SHA-of-CHANGE-012-commit>` — restores the silent-skip behavior.
**Watch for:** Ollama connection storms if hundreds of pages are stale simultaneously (embed calls are sequential — bounded but slow). If this becomes a problem, batch or parallelize embed calls in the loop.

---

## CHANGE-013: Write-time semantic gate (ARCH-034) — PARKED
**Date:** 2026-09-11 (built + tested), NOT WIRED · **Files:** `infra/nashsu/bridge/write_time_gate.py`, `infra/nashsu/bridge/test_write_time_gate.py`
**Plain-English:** Standalone pre-write gate. For each GENUINELY NEW mention nashsu's stage-1 analysis proposes, embeds the mention and cosines it against existing title+first-paragraph embeddings. Tier 1 (≥0.95) hard-redirects with no LLM call. Tier 2 (0.85-0.95) asks `claude -p` MERGE-or-KEEP. Tier 3 (<0.85) passes through unchanged. Tested standalone at cosine ≥0.85: 28.9% hit rate on 20 known-synonym-coining sources.
**Why:** Complements CANON-2 (post-write canonicalization) with pre-write mention-level detection. §5a called for mention-level, not just page-level. Landed as ARCH-034 design.
**Blast radius (if wired):** One extra embed per proposed mention. Tier 2 adds one `claude -p` per ambiguous mention (~180s timeout). Wired via env `MIKAI_GATE=1` — not set by default.
**Approver said:** Approved BUILD ("Do all the tasks"), then implicit PARK by 2026-09-17 "don't diverge from stated architecture without measurement."
**Unpark contract:** Chunk 2 (91 Claude threads) ingest with two-tier gate active. Success = <15 new HIGH-cosine pairs generated (baseline: current post-hoc dedup catches ~30 HIGH pairs per 91-thread chunk). Failure mode observed: ~30% false-positives at 0.85 threshold (enfj↔entj, hilton↔hyatt). Need Tier 2 to reject those before unpark.
**Revert:** N/A (never wired into ingest CLI). If wired: `git revert <SHA>` + unset `MIKAI_GATE`.
**Watch for:** False-positive rate at Tier 1 threshold — 0.95 is calibrated for title+first-paragraph proxy, may need retuning for body-embedding.

---

## CHANGE-014: Post-hoc dedup (apply_dedup.py) — DOWNGRADED per D-068
**Date:** 2026-08 (built), 2026-09 (downgraded) · **Files:** `infra/nashsu/bridge/apply_dedup.py`
**Plain-English:** Two-phase LLM-adjudicated dedup pass over an R5 dedup report. Phase `judge` (read-only): asks `claude -p` MERGE/KEEP/HUB per HIGH-cosine pair, writes verdicts incrementally. Phase `apply` (destructive): backs up vault, LLM-merges bodies for MERGE verdicts, writes canonical + retire stub. Never deletes.
**Why:** Was the primary dedup mechanism before ARCH-036 landed. Now the SAFETY NET — canonicalization at write-time (CANON-2) prevents most duplicates before they land; apply_dedup catches whatever slips through. Kept on disk because periodic runs are still useful.
**Blast radius:** Destructive in `apply` phase — vault backup mandatory. `judge` phase is safe to re-run.
**Approver said:** Original approval predates ledger. Downgrade approved by 2026-09-22 branch manifest ("Session-5's post-ingest dedup as standard — confidence DOWNGRADED" → D-068).
**Unpark contract:** Not parked — kept as safety-net. Run after every N=100 new sources OR when consolidation-completeness measurement shows partition correctness <85%.
**Revert:** `rm infra/nashsu/bridge/apply_dedup.py` — no state. Vault backups (from `apply` phase) restore the pre-run state.
**Watch for:** LLM merge quality on adjacent-but-distinct pairs. `judge` phase verdicts are auditable; spot-check MERGE decisions before running `apply`.

---

## CHANGE-015: Dream pass (dream_pass.py + dream_pass_sample.py) — PARKED
**Date:** 2026-09 (built), NOT SCHEDULED · **Files:** `infra/nashsu/bridge/dream_pass.py`, `infra/nashsu/bridge/dream_pass_sample.py`
**Plain-English:** ARCH-035 periodic offline consolidation. Louvain community detection over the wikilink graph → LLM adjudication per community for merge/split/keep verdicts. `dream_pass_sample.py` is the 3-15-page proof-of-concept; `dream_pass.py` adds recursive sub-clustering for large "blob" communities (50+ pages) with k-means fallback when Louvain can't decompose further.
**Why:** Karpathy crystallization principle (ARCH-035) — the wiki should crystallize into dense canonical pages over time. Canonicalization prevents new duplicates at write-time; dream pass consolidates what's already scattered across near-identical pages.
**Blast radius (if scheduled):** One `claude -p` call per Louvain community (~15-30 communities per run). Recursive sub-clustering can multiply this if the graph has large blobs. Fully reversible via same archive+log pattern as CANON-2.
**Approver said:** Approved BUILD (ARCH-035 in DECISIONS.md). No scheduling approval — awaiting corpus measurement.
**Unpark contract:** Consolidation-completeness measurement (weekly cron per next-branch plan) shows density-median-words plateauing OR partition correctness declining. Then schedule dream_pass as weekly cron. Ecosystem evidence (OpenAI Dreaming V3: 67.9% → 82.8% factual recall; Letta sleep-time compute) supports this direction.
**Revert:** N/A (never scheduled). If scheduled via cron: `crontab -r` or remove the specific line; existing pages retain their pre-dream state via canonicalization archive.
**Watch for:** LLM adjudication cost per community — recursive sub-clustering on blob communities can spike. Cap `--max-recursion` conservatively. Community boundaries may cross concept boundaries; spot-check merge verdicts before landing.

---

## Template for future entries

```
## CHANGE-016: Surface Engine reads files instead of Neo4j
**Date:** 2026-10-13 · **Branch:** `feat/brain-hands-hermes` · **Files:** `infra/decider/mikai_decide.py` (188+/676−), new `infra/decider/brain_context.py`, new `infra/decider/tests/test_brain_context.py`
**Plain-English:** The notification decider no longer queries the deprecated Graphiti/Neo4j graph. Each tick it reads thread files (`~/.mikai/brain/threads/*.md`: state, quiet days, next step), the priority docs (BRAIN.md, GOALS.md, USER_MODEL.md) and the wiki pages those threads name, plus the existing iMessage/Calendar/Gmail adapters and needs registry, then asks `claude -p` whether to interrupt. Dispatch (ntfy), cooldown, logging and the tap/dismiss loop are unchanged.
**Why:** The engine went dormant on 2026-08-07 after the graph was deprecated; its August output was the product. Files are the active substrate.
**Blast radius:** Read-only on all MIKAI files. Writes only to `~/.mikai/notification_log.db` (as before). When scheduled, sends real push notifications to Brian's phone. Other modules that import from `mikai_decide` (calendar planner, tap endpoint, dismissal inference, daily brief, CLI) still import cleanly; 53/53 decider tests pass.
**Approver said:** "In parallel do the six tasks that you defined" (build). Landing approval: "Commit now" (2026-10-13). Not switched on; scheduled job still unloaded.
**Revert:** `git revert <commit>`. Scheduled job stays off until `launchctl load ~/Library/LaunchAgents/com.mikai.figs-decide.plist`; unload with `launchctl unload` of the same path.
**Watch for:** Threads go stale (current files show 69–70 days quiet because nobody updated them), which makes everything look "stalled". Only 1 wiki page enriches the prompt because threads rarely name entities. iMessage excerpts (60 items) go into the `claude -p` prompt.

---

## CHANGE-017: MCP task-state + feedback tools
**Date:** 2026-10-13 · **Files:** `infra/mikai-mcp/src/index.ts`, `src/vault.ts`, new `src/threads.ts`, new `src/feedback.ts`, new `test/task-state.test.mjs`
**Plain-English:** `mikai-wiki-v1` gains four tools: `mikai_threads_list`, `mikai_thread_get`, `mikai_get_stalled_threads` (read thread files) and `mikai_record_feedback` (records ACTED / DISMISSED / SNOOZED / NOT_RELEVANT for a surfaced item). Any MCP client — Claude Code, Hermes — can read task-state and log explicit replies.
**Why:** Step 2 of the Oct 11 brief (task-state over MCP) and the explicit-label half of the dismiss-rate loop.
**Blast radius:** The three read tools are read-only. `mikai_record_feedback` is the first write path in the MCP server: it inserts rows into a new additive `notification_feedback` table in `~/.mikai/notification_log.db`; existing tables are untouched. 8/8 tests pass.
**Approver said:** "In parallel do the six tasks that you defined" (build). Landing approval: "Commit now" (2026-10-13).
**Revert:** `git revert <commit>`; the extra table can stay (nothing reads it except the dismiss-rate script) or be dropped with `DROP TABLE notification_feedback`.
**Watch for:** A chatty agent recording feedback it inferred rather than what Brian said — feedback rows record a `source`; the dismiss-rate report should count only explicit user replies.

---

## CHANGE-018: Hermes Agent installed and wired to MIKAI over MCP (outside the repo)
**Date:** 2026-10-13 · **Files:** outside the repo: `~/.hermes/` (Hermes v0.21.7, own uv/Python), `~/.hermes/config.yaml` (backup `config.yaml.bak-pre-mikai`), `~/.local/bin/hermes`, PATH line in `~/.zprofile`. In repo: `infra/hermes/README.md` (reproduction notes).
**Plain-English:** Hermes runs on Brian's Claude subscription via the official `claude-subscription-directsdk` plugin (no API key) and connects to `mikai-wiki-v1` as an MCP server (10 tools discovered, one live tool call verified). No gateway, no background service, no messages sent. iMessage (BlueBubbles) is not connected — needs Brian's identity decision and permissions.
**Why:** "MIKAI brain, Hermes hands" dogfood loop.
**Blast radius:** Each Hermes turn draws on the same subscription pool as interactive Claude use (~62K tokens for a trivial turn, mostly Hermes's own system prompt). Nothing runs unattended.
**Approver said:** "In parallel do the six tasks that you defined".
**Revert:** `rm -rf ~/.hermes ~/.local/bin/hermes` and remove the PATH line from `~/.zprofile`; `git revert` for the README.
**Watch for:** Token cost per turn before any schedule is added (trim skills/toolsets). Anthropic policy on third-party harnesses is contested — personal use only. When BlueBubbles is added, restrict to Brian's own handle.

---

## CHANGE-019: Dismiss-rate measurement (measurement only)
**Date:** 2026-10-13 · **Files:** new `eval/dismiss_rate.py`, `eval/test_dismiss_rate.py`, `eval/reports/dismiss-rate-2026-10-13.md` (draft, not published)
**Plain-English:** Reads `notification_log.db` read-only and computes the dismiss rate with explicit and inferred labels reported separately, plus failure counts. Today: 100% from 3 inferred data points — the report says this means almost nothing yet.
**Why:** Step 4/5 of the brief: start the log and publish one honest benchmark.
**Blast radius:** Zero (read-only). 12/12 tests pass.
**Approver said:** "In parallel do the six tasks that you defined". Publishing externally needs separate approval.
**Revert:** delete the three files.
**Watch for:** Publishing before ≥20 explicitly rated items.

---

## CHANGE-NNN: <name>
**Date:** YYYY-MM-DD · **Files:** paths touched
**Plain-English:** what this actually does when it fires (2-3 sentences)
**Why:** the problem it solves + why this approach vs alternatives
**Blast radius:** what breaks if it misbehaves + max cost to session/vault
**Approver said:** the specific words Brian used to approve
**Revert:** the exact command(s) to undo
**Watch for:** predicted failure modes + when to check them
```

---

## CHANGE-020: Surface Engine mirrors sent items to iMessage via Hermes
**Date:** 2026-10-24 · **Branch:** `feat/brain-hands-hermes` · **Files:** new `infra/decider/imessage_dispatch.py`, new `infra/decider/tests/test_imessage_dispatch.py`, `infra/decider/mikai_decide.py` (+30/−7, new `imessage_status` log column); outside the repo: `~/Library/Application Support/mikai/launchd/figs-decide-runner.sh` (`export MIKAI_IMESSAGE=1`, backup `.bak-pre-imessage`)
**Plain-English:** When the Surface Engine sends a notification over ntfy, it also texts the same item to Brian's iMessage through `hermes send` (Photon), ending with `ref: <notif_id>` and "Reply: done · snooze · not relevant". Off unless `MIKAI_IMESSAGE=1`. A failed text never blocks the ntfy push; its status is logged per decision.
**Why:** Replies must be matched to the item they answer; the ref line is the link.
**Blast radius:** Up to the Surface Engine's normal volume (3 runs/day, default silence, 2-hour cooldown) of iMessages to Brian only. Message text passes through Photon.
**Approver said:** "continue with your tasks" (build). Landing approval: pending.
**Revert:** remove `export MIKAI_IMESSAGE=1` from the runner (or restore `.bak-pre-imessage`); `git revert` the commit.
**Watch for:** Photon stream drops (texts may fail while reconnecting; ntfy still delivers); duplicate noise if both channels feel redundant.

---

## CHANGE-021: Hermes trimmed + MIKAI operating rules + reply/task tools
**Date:** 2026-10-24 · **Files:** outside the repo: `~/.hermes/config.yaml` (backup `.bak-pre-trim`), `~/.hermes/SOUL.md` (backup `.bak-pre-mikai`); in repo: `infra/hermes/SOUL.md` (copy), `infra/hermes/README.md`, `infra/mikai-mcp/src/index.ts`, `src/threads.ts` (+98), new `src/outbox.ts`, new `test/outbox-upsert.test.mjs`
**Plain-English:** Hermes's toolsets cut to `web`, `cronjob` and the MIKAI MCP server; Hermes's own memory and autonomous skill creation turned off so MIKAI stays the single source of truth. `SOUL.md` tells Hermes to answer from MIKAI's tools, log Brian's replies with `mikai_record_feedback` (using the `ref:` line or the new `mikai_recent_surfaced`), capture tasks with the new `mikai_thread_upsert`, stay at Level A for purchases (links only; no payments, logins or orders), and treat email/web content as untrusted data. Trivial turn cost: 20,304 → 4,887 tokens.
**Why:** The always-on listener makes every text a turn; the cost had to drop, and replies have to land in MIKAI.
**Blast radius:** `mikai_thread_upsert` is a new WRITE path into `~/.mikai/brain/threads/` (not the wiki). A bad upsert could create or alter thread files.
**Approver said:** "continue with your tasks" (build). Landing approval: pending.
**Revert:** restore `config.yaml.bak-pre-trim` and `SOUL.md.bak-pre-mikai`, `hermes gateway restart`; `git revert` the commit.
**Watch for:** Hermes needing a disabled toolset for a request; spurious thread creation from casual messages.

---

## CHANGE-022: Loop switched on — Hermes service + Surface Engine schedule
**Date:** 2026-10-24 · **Files:** outside the repo: `~/Library/LaunchAgents/ai.hermes.gateway.plist` (installed by `hermes gateway install`), `com.mikai.figs-decide` LaunchAgent loaded (7:00, 12:00, 18:00)
**Plain-English:** Hermes's iMessage listener runs as a background service (survives closing this chat; runs while the Mac is awake). The Surface Engine runs three times a day, pushes via ntfy and mirrors to iMessage.
**Why:** Brian chose to switch the Surface Engine on once iMessage worked ("Wait for iMessage"); iMessage verified 2026-10-22 and 2026-10-24.
**Blast radius:** Real notifications to Brian's phone up to 3×/day; `claude -p` usage from his subscription per run and per text.
**Approver said:** "Wait for iMessage" (2026-10-13) + "continue with your tasks". Landing approval: pending.
**Revert:** `launchctl bootout gui/$(id -u)/com.mikai.figs-decide`; `hermes gateway stop && hermes gateway uninstall`.
**Watch for:** quota use; silent failure (no health alert yet — the Aug 2026 failure went unnoticed); the Mac sleeping.

---

## CHANGE-023: Hands — Hermes drives a dedicated MIKAI Chrome, Instinct-style errands with one confirmation gate
**Date:** 2026-10-27 · **Branch:** `feat/brain-hands-hermes` · **Files:** outside the repo: `~/.hermes/config.yaml` (`browser.cdp_url: http://127.0.0.1:9222`, `browser.restrict_evaluate: true`, browser toolset enabled for the photon platform; backup `config.yaml.bak-pre-hands`), `~/.hermes/SOUL.md` ("Doing things" section replaces the links-only Level A policy; backup `SOUL.md.bak-pre-hands`), `~/.mikai/browser-profile/` (separate Chrome user-data dir, mode 700). In repo: `infra/hermes/SOUL.md` copy, branch manifest do-not rule rewritten.
**Plain-English:** MIKAI can now use a web browser to finish errands (search, compare, fill forms, book, buy, check in) inside its own Chrome profile, which is signed only into the sites Brian chooses. Before anything that pays, orders, books, cancels or messages someone else, it texts Brian one summary and waits for "yes".
**Why:** Brian: "I want it to work like Instinct." The market values agents that finish the job; MIKAI's prior links-only policy left out the hands.
**Blast radius:** An agent with logged-in sessions can spend money or change bookings on the sites signed into the MIKAI profile. Bounded by: the confirmation gate (an instruction in SOUL.md, not code-enforced), payment only via methods saved on those sites, the separate profile (no access to Brian's everyday logins), restrict_evaluate blocking cookie/storage/form-value reads from page scripts. The control port listens on 127.0.0.1 only.
**Approver said:** "I want it to work like Instinct" (2026-10-27).
**Revert:** `cp ~/.hermes/config.yaml.bak-pre-hands ~/.hermes/config.yaml && cp ~/.hermes/SOUL.md.bak-pre-hands ~/.hermes/SOUL.md && launchctl kickstart -k gui/$(id -u)/ai.hermes.gateway`; quit the MIKAI Chrome; optionally delete `~/.mikai/browser-profile/` to sign out of everything.
**Watch for:** Prompt injection from web pages steering a logged-in session (untrusted-content rule applies; no code-level enforcement yet). The gate being skipped because it is only an instruction — first test errands should be watched. MIKAI Chrome not running after a reboot (browser tool will fail; needs a launch-at-login job). Sites blocking automation (Amazon).

---

## CHANGE-024: Script onboarding for testers (`mikai-setup` / `mikai-uninstall`)
**Date:** 2026-10-27 · **Files:** `infra/onboarding/{mikai-setup, mikai-uninstall, export-apple-notes.js, templates/SOUL.md.tmpl, templates/com.mikai.chrome.plist.tmpl}`, `docs/ONBOARDING_GUIDE.md`, router row, status note in `docs/ONBOARDING_PLAN.md`
**Plain-English:** A tester runs one script on their own Mac. It installs Hermes on their own Claude login, connects MIKAI's tools, writes MIKAI's rules with their name, gives MIKAI its own Chrome, sets up their own iMessage line through Photon, walks them through Full Disk Access, and optionally imports their Apple Notes read-only. `mikai-uninstall` backs up and removes all of it.
**Why:** Brian: "we should have two things finished by the end of the session. Instinct like actions, and user onboarding."
**Blast radius:** Only the tester's `~/.hermes`, `~/.mikai` and LaunchAgents. Existing Hermes config and rules are backed up before changes. Nothing in the repo runs on its own. Tested with `--dry-run` and `--test` in sandbox homes; never run for real on Brian's Mac (it would point at `wiki-brian` and replace his rules).
**Approver said:** "we should have two things finished by the end of the session. Instinct like actions, and user onboarding"
**Revert:** run `infra/onboarding/mikai-uninstall` on the tester's Mac; `git rm -r infra/onboarding docs/ONBOARDING_GUIDE.md`.
**Watch for:** Anthropic's third-party subscription rules (distributing a setup that runs each tester's own subscription through Hermes's plugin is a grey area). Hermes CLI prompts changing and silently cancelling steps (`mcp add` already did once; setup now verifies). Unpinned npm deps on fresh clones (`package-lock.json` is gitignored).

---

## CHANGE-025: Reply matching, thread writes, calendar + messages reading, proactive iMessage on
**Date:** 2026-10-24 to 2026-10-27 · **Files:** `infra/mikai-mcp/src/{outbox.ts, apple.ts, threads.ts, index.ts}` + tests; `infra/decider/{imessage_dispatch.py, mikai_decide.py}` + tests; `eval/dismiss_rate.py` + test; outside the repo: `MIKAI_IMESSAGE=1` in `~/.mikai/launchd.env`, `com.mikai.figs-decide` LaunchAgent loaded, `~/Library/LaunchAgents/com.mikai.chrome.plist`.
**Plain-English:** (1) Every iMessage MIKAI sends is recorded in an outbox, so a bare "done" reply is logged against the right item (`mikai_recent_surfaced`, `notif_id: "latest"`). (2) Hermes can create and update task threads from chat (`mikai_thread_upsert`; the wiki stays read-only; every edit backs up the old file to `threads/.history/`). (3) Hermes can read the user's Apple Calendar and recent iMessages, read-only (`mikai_calendar_events`, `mikai_recent_messages`; needs Full Disk Access for Hermes's Node). (4) The Surface Engine runs at 7:00/12:00/18:00 and sends to iMessage as well as ntfy. (5) Replies stored in `notification_feedback` now count in the dismiss rate. (6) MIKAI's Chrome starts at login.
**Why:** To make the reply loop work (the first test "done" had no context), and to give MIKAI Instinct-like awareness and proactivity.
**Blast radius:** Thread files under `~/.mikai/brain/threads/` can now be written by Hermes (backed up per edit). Up to three proactive notifications a day reach Brian's phone (2-hour cooldown, default silence). Calendar and message contents are sent to Anthropic when Hermes reads them for a reply.
**Approver said:** "continue with your tasks" (2026-10-24); "I want it to do everything instinct can do" (2026-10-27).
**Revert:** `launchctl bootout gui/$(id -u)/com.mikai.figs-decide`; remove the `MIKAI_IMESSAGE=1` line from `~/.mikai/launchd.env`; `rm ~/Library/LaunchAgents/com.mikai.chrome.plist`; revert the listed repo files with git and rebuild `infra/mikai-mcp`; restore any thread from `~/.mikai/brain/threads/.history/`.
**Watch for:** Wrong-item matches on "done" when several items are recent. Thread churn from over-eager upserts. Full Disk Access revoked by a Hermes update that changes its bundled Node path. Message text steering replies (marked untrusted, not code-enforced).
