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

## CHANGE-012: mikai-wiki-v1 search — live-embed on cache miss (fix)
**Date:** 2026-09-28 · **Files:** `infra/mikai-mcp/src/search.ts`, `infra/mikai-mcp/dist/src/search.js` (rebuilt)
**Plain-English:** Replaces the silent `continue` on cache-miss in `semanticSearch()` with a `loadOrEmbed()` call — same helper already used for the query itself and mirroring `dedup_embed.py`'s convention. If a page's cached embedding is missing (because its body was modified after the last embed pass), the search now embeds the current body via Ollama, caches it, and includes the page in scoring instead of skipping it.
**Why:** Bug found 2026-09-27 when `mikai_wiki_search` for "MIKAI intent graph" returned semantically-adjacent pages but not `personal-intent-graph` itself. Root cause: canonicalization + CANON-8 wrap modified `personal-intent-graph.md`, invalidating its cached SHA-keyed embedding, and the search silently skipped it. Bias direction was bad — most-worked-on pages became least-findable. Fix restores expected behavior.
**Blast radius:** First search after a large edit gets slower by (missing-page count × ~200ms Ollama latency). Second search hits cache. On a static vault, no change vs prior behavior. If Ollama is unreachable, the outer try/catch on the query-embed step falls back to lexical search unchanged.
**Approver said:** "fix it" (2026-09-28)
**Revert:** `git revert <SHA-of-CHANGE-012-commit>` — restores the silent-skip behavior.
**Watch for:** Ollama connection storms if hundreds of pages are stale simultaneously (embed calls are sequential — bounded but slow). If this becomes a problem, batch or parallelize embed calls in the loop.

---

## Template for future entries

```
## CHANGE-NNN: <name>
**Date:** YYYY-MM-DD · **Files:** paths touched
**Plain-English:** what this actually does when it fires (2-3 sentences)
**Why:** the problem it solves + why this approach vs alternatives
**Blast radius:** what breaks if it misbehaves + max cost to session/vault
**Approver said:** the specific words Brian used to approve
**Revert:** the exact command(s) to undo
**Watch for:** predicted failure modes + when to check them
```
