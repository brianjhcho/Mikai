# Noise Diagnostic — end of 2026-08-09

Inventory of what today's builds produced. What's signal, what's
noise, what to remove/consolidate.

## 1. Concept pages — signal vs noise

30 total pages in `~/.mikai/wiki/concepts/`.

### Signal — real content (11 pages, keep)

| Slug | Source of value | LLM summary quality |
|---|---|---|
| kenya | 100 mentions across 5 streams, real "Where to move" content | ✓ real content ("listed first among candidate cities") |
| brian | 336 mentions, 2016 self-directed Apple Notes captured | ✓ real |
| apple | 1632 mentions (fruit + Inc mixed) | mixed |
| gmail | 289 mentions | ✓ real |
| graphiti | 591 mentions, MIKAI's L3 backend | ✓ real |
| wiki | 566 mentions, the substrate itself | ✓ real |
| martin | 76 mentions, 7 sources — the interesting spread-wins-over-density case | ✓ honest ("two unrelated referents") |
| claude, claude-code | Anthropic's model + CLI | ✓ real |
| mikai | 3033 mentions, the product | ✓ real |
| posture-and-workout | HAND-AUTHORED today from grep + USER_MODEL | ✓ real but shallow (missed the 803-turn thread) |

### NOISE — extraction artifacts from MIKAI's own system-prompt turns (9 pages, candidates for demotion)

These n-grams got extracted from claude-code sessions where MIKAI's
own system prompt was captured as a wiki.md section. They're not
concepts Brian thinks about — they're prompt boilerplate:

- `default-surface-engine` — from prompt scaffolding
- `toggle-rode` — extraction artifact (no such concept exists)
- `beea475f` — hash-looking, extraction garbage
- `primary-request` — literally a system-prompt section header
- `live-sources` — from prompt scaffolding
- `choice-while-building` — from prompt scaffolding
- `real-and-finite` — from prompt scaffolding
- `solo-builder` — from prompt scaffolding (though arguable — Brian
  IS a solo builder)
- `identity-brian-cho` — from prompt scaffolding (though arguable)

All have LLM summaries that HONESTLY say "the excerpts do not
support a summary" — no hallucination but no useful content either.

**Recommended action**: delete these 9 pages OR move to an
`~/.mikai/wiki/concepts/_deprecated/` folder for reference.

### NOISE — conversation-vocab that shouldn't be concepts (10 pages, candidates for stopword expansion)

These are fragments of English conversation that dominated the
lowercase-extraction top-20:

- `ingested` (7.61 base, 9475 mentions — mostly from ingest metadata)
- `assistant` (7.29 base, mostly from claude-thread headers)
- `right` (5.89 base)
- `agent` (6.72 base)
- `three` (5.58 base)
- `session` (5.43 base)
- `thread` (6.29 base)
- `decision` (5.17 base)
- `project` (5.11 base)
- (`meet-mikai` — arguable, promoted via G-axis but no real content)

**Recommended action**: expand `_NGRAM_STOP` in `dream_bootstrap.py`
to include these conversation-vocab words. Delete their pages OR
demote to `_deprecated/`.

### Total: 19 of 30 concept pages are noise (63%)

Only ~11 pages carry real information. The rest are byproducts of
the extraction pipeline that Fable's SEMANTIC_CLUSTERING_GAP.md
diagnosed.

---

## 2. Files/state that can be removed

### Old wiki.md backups (safe to delete after verifying wiki.md integrity)

```
~/.mikai/wiki/wiki.md.bak-pre-backfill-20260806T044346Z
~/.mikai/wiki/wiki.md.bak-pre-backfill-20260806T044406Z
~/.mikai/wiki/wiki.md.bak-pre-backfill-20260806T044517Z
```

~90MB total. From August 6 backfill session. wiki.md itself is
current source of truth.

### Old FTS backups

```
~/.mikai/wiki/wiki.fts.db.pre-dedup-20260807T155608.bak
```

~100MB. FTS is disposable (rebuilt from wiki.index). Delete.

### Old lint reports (accumulating)

`~/.mikai/wiki/concepts/lint-report-YYYY-MM-DD.md` will grow over
time. Currently 1 file. Add a cleanup rule: keep last 7, delete
older.

### Concept-inbox (5 suggestions from Build 5 first run)

`~/.mikai/wiki/concept-inbox.md` has 5 suggested new concepts from
the 5-source Build 5 test. Not noise — needs Brian's review to
either mint or reject.

---

## 3. Design decisions revisited (what was wrong today)

### Auto-stoplist included `mikai`
- **Cause**: auto-generator walks the repo, treats every dir name as
  a stoplisted term. `~/.mikai/` matched.
- **Effect**: MIKAI's own name was excluded from candidates in v003.
  Cost the recall@10 hit on "MIKAI and ambient computing" goal.
- **Fix**: create `~/.mikai/brain/self-corpus-stoplist.txt` with a
  curated list. Omit `mikai`, `brain`, `wiki`, `dream`, `cockpit`,
  etc. — these are meaningful.

### G-axis noise band
- **Cause**: Binary token-set cosine with pooled context sets
  thousands of tokens wide. Denominator `sqrt(|ctx|·|goal|)` is
  dominated by context-set size, not topical alignment.
- **Effect**: G column collapsed to 0.03–0.11 range. Zero
  discriminative power.
- **Fix (v005+)**: Voyage embeddings instead of token-set cosine.
  Or IDF-weight tokens. Fable's brief specified embedding cosine
  ≥ 0.85 as the threshold.

### MIKAI-goal-bloat
- **Cause**: "MIKAI and ambient computing" goal text has 40+ tokens
  (mikai, ambient, computing, task, state, awareness, agent, memory,
  noonchi, consolidation, attention, engine, karpathy, dream,
  salience, personal, ai, infrastructure, executive, assistant, wiki,
  brain, promote, layer, ...). Wins max cosine against nearly
  everything.
- **Effect**: Every G-promoted page tagged `best_goal: "MIKAI and
  ambient computing"` regardless of actual topical alignment (kenya
  matched to MIKAI when it should match "where to settle a family").
- **Fix**: Rewrite MIKAI goal to be narrower ("shipping MIKAI to
  consumers, closing the agentic loop, current architecture
  decisions"). Cuts token count from ~40 to ~15.

### Extraction pipeline is one-directional
- **Cause**: `run_promote` reads ontology + wiki.md n-grams as
  candidate sources. Doesn't read `concepts/*.md` back.
- **Effect**: Hand-authored pages don't act as attractors for future
  extraction. Structural dead-end for the "write a page, watch it
  gather semantically-related evidence" workflow.
- **Fix**: Fable's E5. Embed concept pages, use as cluster seeds.
  See `docs/SEMANTIC_CLUSTERING_GAP.md` for full brief.

### Excerpt sampling for LLM summaries used `mentions[:8]`
- **Cause**: Oldest 8 mentions. For recent concepts (e.g. `mikai`
  which existed since ~2024), the oldest 8 are 2013 Apple Notes
  that happen to contain the substring "mikai" — false positives.
- **Effect**: LLM summary of `mikai.md` correctly said "the excerpts
  do not support any claim about MIKAI" — because the sampled
  excerpts were unrelated 2013 notes.
- **Fix**: sample most recent 8 OR diversified sample (2 oldest + 2
  middle + 4 recent).

### Karpathy-shape page format is thin vs. reference
- **Cause**: Build 4 rendered TL;DR + Why + Notes + Sources. But the
  reference format (Independent-Mindedness example) has: Summary
  callout + Key Points structured bullets + How-to callout + dense
  Notes SYNTHESIS PROSE + Related + References + inline yellow
  highlights.
- **Effect**: MIKAI's pages read as audit-shaped, not knowledge-
  shaped.
- **Fix**: Upgrade Build 4 template. Notes section becomes prose-with-
  wikilinks explaining CONNECTIONS between concepts, not a bullet
  list of related slugs. Add Related section for pure wikilinks
  separately. Add References section for external URLs. Adopt
  Obsidian callout syntax.

---

## 4. Consolidation candidates

### Redundant concepts (should merge)

- `claude` + `claude-code` + `meet-mikai` — all MIKAI/Claude-adjacent
  identity. Merge into one page + aliases.
- `mikai` + `identity-brian-cho` — merge (identity-brian-cho was
  extracted from MIKAI's own system prompt describing Brian).

### Empty-content pages (delete or refill)

The 9 extraction-artifact pages all have "no summary supported by
excerpts" — should be deleted.

---

## 5. Cleanup action list (order by safety)

1. **Delete FTS backup** — `~/.mikai/wiki/wiki.fts.db.pre-dedup-*.bak`.
   Rebuildable from wiki.index. ~100MB saved. **Zero risk.**
2. **Delete 9 extraction-artifact concept pages** — `default-surface-engine`,
   `toggle-rode`, `beea475f`, `primary-request`, `live-sources`,
   `choice-while-building`, `real-and-finite`, `solo-builder`,
   `identity-brian-cho`. **Low risk** (LLM summaries confirm they
   contain nothing).
3. **Demote conversation-vocab pages** — move `ingested`, `assistant`,
   `right`, `agent`, `three`, `session`, `thread`, `decision`,
   `project` to `~/.mikai/wiki/concepts/_deprecated/`. **Low risk**
   (deprecated dir, easy to restore).
4. **Delete wiki.md backups** — `~/.mikai/wiki/wiki.md.bak-pre-backfill-*`.
   **Medium risk** — verify wiki.md integrity first (byte count,
   section count, FTS index consistency).
5. **Expand stopword list** — add conversation-vocab so future
   extraction doesn't create these pages again. Code change to
   `dream_bootstrap.py::_NGRAM_STOP`. **Zero risk** (can revert).
6. **Create user-authored `self-corpus-stoplist.txt`** — omit `mikai`,
   `brain`, `wiki`, `dream`, `cockpit`. Solves the goal-hit issue.
   **Zero risk**.
7. **Rewrite MIKAI goal in GOALS.md** — narrow to shipping/agentic-
   loop/architecture. Solves best_goal-bloat. **Zero risk**.
8. **Rerun `karpathy_rerender.py`** — pages get updated with the
   fixed template + narrower stoplist takes effect.
9. **Rerun eval v005** — measure post-cleanup recall@10.

Steps 1-3 alone would reduce concept-page count from 30 → 11 (only
real-content pages remaining), matching what a "curated wiki"
actually looks like. Steps 4-9 are architectural cleanup.

**Net gain**: after cleanup, the concept-page inventory becomes
Karpathy-style (small, curated, meaningful) instead of Consolidation-
MVP-style (30 pages, 63% noise).
