# LINT_PASS — structural hygiene for the wiki

**Status:** design, 2026-08-11. Implementation target: `infra/graphiti/lint_pass.py`. Legacy predecessor `infra/graphiti/dream_lint.py` (misnamed — it does lint work, not dream work) will be renamed as part of this build. All prior `dream_lint.py` references in code + launchd should update to `lint_pass.py`.

**Pipeline position:**

```
raw sources → wiki.md capture → sources/*.md → concepts/*.md ← [LINT PASS] → [DREAM PASS] → L4 salience
                                                                    ↓
                                                             lint-report-YYYY-MM-DD.md
```

Lint runs **after ingest**, **before dream**. It operates on the concept-page layer (and optionally sources/) and produces a report — never mutates content semantically.

---

## Design principle

**Structural, deterministic, non-destructive.** Lint flags issues; it never merges concepts, resolves contradictions, or rewrites prose. All those are Dream's job.

**Precedent (from research 2026-08-11):**
- **Karpathy gist**: lint "flags only; LLM proposes updates, never writes them unilaterally"
- **kytmanov/obsidian-llm-wiki-local**: `olw maintain` explicit design principle: "Do not use LLM aliases as automatic merge authority"
- **danvega/karpathy-wiki**: `WikiLinterAgent` produces `LintReport`; separate `WikiCompilerAgent` handles semantic writes
- **rohitg00 LLM Wiki v2**: lint auto-fixes structural issues (orphans, broken refs) but explicitly avoids concept-merging

None of the reference implementations put semantic merging inside their lint pass. MIKAI adopts the same discipline.

---

## Inputs

- `~/.mikai/wiki/concepts/*.md` (all concept pages)
- `~/.mikai/wiki/concepts/index.md` (canonical page list)
- `~/.mikai/wiki/sources/**/*.md` (all source files — for wikilink resolution)
- `~/.mikai/wiki/SCHEMA.md` (governance rules to enforce)
- `~/.mikai/brain/GOALS.md` (for goal-evidence gap check)

## Checks (all deterministic)

### 1. Broken wikilinks
For every `[[slug]]` in prose: does `concepts/<slug>.md` exist?
- **Reports:** page path, line number, missing slug
- **Never auto-creates the target** (Karpathy discipline — don't invent)

### 2. Orphan pages
Concept page with **zero** incoming `[[wikilink]]` from other concept pages OR from any source file's `## Touches` section, AND not listed in `index.md`.
- **Reports:** page slug, last-modified, size
- **Never auto-retires** (defer to Dream + human)

### 3. Malformed frontmatter
Missing required fields per SCHEMA: `title`, `slug`, `authored`, `minted` OR `rerendered`.
Wrong types: `salience` not float, `tags` not list, `aliases` not list.
- **Reports:** page path, missing/malformed field
- **Never auto-fixes** — LLM shouldn't guess frontmatter

### 4. Format violations
Slug in filename doesn't match `slug:` field. Filename not kebab-case. Slug uses plural form. Slug collides with a `GOALS.md` goal name (L4 leak).
- **Reports:** page path, violation type
- **Never auto-renames** — renames break wikilinks; human owns this

### 5. Duplicate-slug files
Two files whose slugs differ only by case, whitespace, or trivial variant (e.g. `mikai.md` + `MIKAI.md`; `posture.md` + `postures.md`).
- **Reports:** collision pairs
- **Never auto-merges** — that's Dream's job

### 6. Stub / synthesis-pending pages
Concept page containing "no synthesis yet" or "awaiting re-synthesis" or `TL;DR: _(auto-minted...)_` pattern.
- **Reports:** page slug + minted date + touch_count
- **Suggests** running Dream on the page (does not run it)

### 7. Goal-evidence gaps (from existing `dream_lint.py`)
Every goal in `GOALS.md` should have at least one concept page tagged `best_goal:` matching it.
- **Reports:** goals with zero matching concepts
- **Never auto-mints** the gap-filling concept — human seeds it

### 8. Inbox size + recurring-suggestion drift
- **Reports:** count of pending inbox suggestions, breakdown by recurring vs. one-off, top-N recurring by hit count
- Signals when a Dream promotion pass would be productive

---

## Output

`~/.mikai/wiki/lint-report-YYYY-MM-DD.md` — deterministic, machine-readable-ish markdown. Section per check. Numeric counts at top. Detail below.

Example:

```markdown
# Lint report — 2026-08-11
Total: 87 concept pages, 809 source files.

## Broken wikilinks (4)
- concepts/dual-memory-short-term-graph-long-term-store.md:23 → [[graph-substrate]] (missing)
- ...

## Orphan pages (12)
- concepts/mikai.md (401B, minted 2026-08-06)
- ...

## Stubs pending synthesis (0)
_(none)_

## Goal-evidence gaps (3/10)
- "ocean farming and street cleaners" — 0 matching concepts
- ...

## Suggested actions
- Run `dream --stubs-only` — 0 stubs (skip)
- Run `dream --consolidate` — 87 pages, threshold-scan advisable
```

## Cadence

- **Post-ingest hook** — after every ingest batch (e.g. after `smoke_ingest_B.py`)
- **Daily scheduled** — via launchd (or manual `python3 -m infra.graphiti.lint_pass`)
- **Pre-Dream** — always run first; Dream reads the lint report to skip already-known issues

## What lint MUST NOT do (both modes)

Explicit non-goals:
- Never merges duplicate concepts (Dream Pass job)
- Never rewrites TL;DR / Notes
- Never renames or moves files
- Never deletes anything (retirement is Dream Pass job)
- Never calls the LLM

All of the above are Dream Pass responsibilities. Lint stays boringly mechanical, LLM-free, and non-destructive in both modes.

## `--fix` mode — opt-in deterministic auto-repair

Extends the default report-only behavior with a bounded auto-repair pass matching kytmanov's `olw maintain --fix` pattern (verified 2026-08-12 against `kytmanov/obsidian-llm-wiki-local/src/obsidian_llm_wiki/pipeline/maintain.py`). Only fires when `--fix` is passed. `--dry-run` shows what would happen without writing.

**Operations (deterministic, no LLM):**

1. **Alias rewrite** — for each broken `[[foo]]` wikilink, check if `foo` matches an existing concept's `aliases:` frontmatter. If UNAMBIGUOUS (only one canonical claims the alias), rewrite `[[foo]]` → `[[canonical]]` in the source page. Ambiguous aliases (same alias claimed by two pages) are skipped to avoid wrong overwrites.

2. **Bounded stub creation** — for broken targets referenced ≥ `MIN_REFS_FOR_STUB` (default: 3) times across the corpus, create a stub `.md` file with `authored: stub` frontmatter and a `> [!warning]` callout marking it as awaiting synthesis. Sorted by reference count (most-referenced first). Capped at `MAX_STUBS_PER_RUN` (default: 5) per run.

**Tunable constants** (in `infra/graphiti/dream_lint.py`):
- `MAX_STUBS_PER_RUN = 5` — matches kytmanov's default
- `MIN_REFS_FOR_STUB = 3` — MIKAI-specific tightening (kytmanov has no threshold, stubs any broken link). Prevents random typos from becoming stubs.

**Safety:** `--dry-run` gate available; `--fix` is opt-in (not default); never mutates hand-authored pages; never creates a stub if the file already exists; never deletes.

**Usage:**
```
python3 -m infra.graphiti.dream_lint                # report-only (default)
python3 -m infra.graphiti.dream_lint --dry-run      # preview --fix actions
python3 -m infra.graphiti.dream_lint --fix          # apply deterministic fixes
```

**Empirical result (2026-08-12 first run):** 29 broken → 10 broken. 1 alias rewrite + 3 stubs (for `dual-memory-consolidation-problem` [8 refs], `entity-model-2026-08` [7 refs], `mikai-consumer-product-bet` [3 refs]). 19 wikilinks resolved in one pass with zero LLM calls.

---

## Reference implementations

- `kytmanov/obsidian-llm-wiki-local` — `olw maintain` / `olw lint` (Rust CLI)
- `danvega/karpathy-wiki` — `WikiLinterAgent` (Java)
- `infra/graphiti/dream_lint.py` (existing MIKAI predecessor — to be renamed `lint_pass.py`) — broken links, orphans, goal gaps, inbox counts

## What this doc covers

Only the structural hygiene pass. Semantic consolidation lives in `DREAM_PASS.md`. Salience computation lives at L4 (currently `dream_bootstrap.py`, needs rename to `salience_pass.py`).
