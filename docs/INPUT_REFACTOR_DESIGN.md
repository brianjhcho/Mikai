# Input Refactor Design — High-Curation Sources Layer

**Date**: 2026-08-09
**Status**: DESIGN — needs Brian's alignment on 4 questions before
code fires.
**Related**: `docs/SEMANTIC_CLUSTERING_GAP.md` (E5),
`docs/SALIENCE_MVP_DIAGNOSIS.md`, `docs/DAY_LOG_2026-08-09.md`,
`docs/NOISE_DIAGNOSTIC_2026-08-09.md`.

---

## The philosophy shift

**Was:** LOW-curation input (daemons capture everything) + HIGH-filter
output (salience formula ranks). Result: pollution from
system-prompt turns, incidental conversation, boilerplate. Fable's
diagnostic showed this bloats top-20 with `assistant`/`ingested`/
`session`.

**Is now (per Brian's 2026-08-09 call):** HIGH-curation input
(explicit sources folder, per-file, immutable, categorized) + LOW-
filter output (concept pages synthesize across curated sources).
Karpathy's Layer 1 philosophy.

Both models CAN be true simultaneously (curated `sources/` for
high-signal material + `raw/` for automated capture the salience
formula still processes) — but the primary emphasis is on `sources/`.

---

## The proposed directory structure

```
~/.mikai/wiki/
├── SCHEMA.md              ← LLM instruction doc (Karpathy CLAUDE.md pattern)
├── sources/               ← IMMUTABLE curated raw material (Layer 1)
│   ├── ai/
│   ├── health-and-fitness/
│   ├── psychology/
│   ├── career-and-tech/
│   ├── domestic/
│   ├── settle-and-family/
│   ├── consumer-and-economics/
│   ├── proposal/
│   ├── ocean-farming-and-street-cleaners/
│   └── mikai/
├── raw/                   ← LEGACY: wiki.md + backups (append-only,
│   │                        daemon-captured, low-signal)
│   ├── wiki.md            ← existing 30MB append-only log
│   ├── wiki.index
│   ├── wiki.fts.db
│   └── *.bak-*
├── concepts/              ← EXISTING: Karpathy-shape concept pages
│   ├── index.md
│   ├── log.md
│   └── <slug>.md
├── concept-inbox.md       ← EXISTING: Build 5 suggestions
├── wiki-salience.md       ← EXISTING: salience ledger
├── wiki-narrative.md      ← EXISTING: 30-day dream narrative
└── wiki-ontology.md       ← EXISTING: ontology extraction
```

Categories match Brian's 10 goals from `GOALS.md`, one-to-one, so
category pick at ingest time doubles as goal-alignment tagging.

---

## Categorization mechanism (Q3 below)

Two options, differing on where the labor lives:

**Option A — LLM classifier at ingest time**
- New material → LLM sees content + list of Brian's 10 categories
  (from GOALS.md) → picks one, or suggests a new category
- Cost: 1 LLM call per ingested source (Haiku-tier, ~$0.0002 each)
- Latency: adds ~2s per ingest
- Fail-safe: uncategorized items land in `sources/_uncategorized/`
  for manual review

**Option B — Rule-based classification via source stream + keyword**
- apple-notes with fitness keywords → `health-and-fitness/`
- claude-thread name pattern-match → route
- Fails silently for anything not matching → `_uncategorized/`
- Cost: zero (deterministic)
- Latency: negligible
- Quality: only as good as the rule set

Fable's earlier briefs strongly recommend LLM at bounded points +
deterministic elsewhere. This is one of those bounded points —
per-source classification is a well-defined, gradeable task. **My
recommendation: Option A.**

---

## Migration path — the ~8000 existing wiki.md sections

Three options:

**M1 — In-place, no migration.** Leave wiki.md as the archive of
past capture. New material from today forward routes to `sources/`.
Old material stays in wiki.md and gets processed by the existing
salience formula.
- Pro: zero risk, zero migration cost
- Con: two universes to reason about (old wiki.md vs new sources/)

**M2 — Bulk migrate wiki.md → per-source files under `sources/`.**
Every existing section becomes a file, categorized retroactively via
Option A LLM classifier.
- Pro: one universe, clean architecture
- Con: 8000 LLM calls (~$1-2 at Haiku), 8000 filesystem writes,
  migration script bug risk, wiki.md indexing paths break

**M3 — Migrate only "high-signal" existing sections.** Use the
salience ledger's top-N (say top-500 sections by S) + all Brian-
originated Apple Notes + all curated claude-threads. Leave the rest
in wiki.md as archive.
- Pro: high-signal migration only, ~500 LLM calls
- Con: judgment call on what's "high-signal enough"

**My recommendation: M1 for now.** The refactor is about GOING
FORWARD from today. Old wiki.md stays as archive. If M2/M3 is worth
doing later, it can be a separate one-shot script. Doesn't block
shipping the new sources/ pattern.

---

## Ingestion flow (new)

```
   New material arrives
         │
         ▼
   Curation gate (Option A LLM classifier + confidence threshold)
         │
    ┌────┴────┐
    │         │
  keep      reject/uncategorized
    │         │
    ▼         ▼
sources/<category>/<slug>.md        (dropped or _uncategorized/)
    │
    ▼
Build 5 ingest-source pass touches related concept pages
    │
    ▼
Weekly cluster/consolidate pass (future E5)
```

Old daemons (Apple Notes watcher, claude-threads runner, claude-code
sessions) keep writing to `raw/wiki.md` for archival. NEW ingestion
targets `sources/` via the curation gate. Over time, `raw/` becomes
history and `sources/` becomes primary.

---

## SCHEMA.md — the LLM instruction doc

Written at `~/.mikai/wiki/SCHEMA.md`. Every write path (Build 4
rerender, Build 5 ingest, hand-authoring) reads it. Content includes:

- Directory structure (this doc's Section 2)
- Categories (from GOALS.md)
- Page anatomy for `sources/<category>/*.md`: frontmatter
  (title, source, date, category, tags), one-paragraph capture, no
  editing after save (immutability)
- Page anatomy for `concepts/*.md`: TL;DR + Key Points + callouts
  (Obsidian syntax) + dense Notes SYNTHESIS PROSE + Related +
  References
- L3/L4 boundary rule (wikilinks to concept pages only; goal names
  as backticks, never wikilinks)
- Naming conventions: kebab-case slugs, no plurals, singular head +
  variant aliases
- Curation gate rule: LLM classifier picks category or `_uncategorized/`

Karpathy's `CLAUDE.md` served the same role. `flsteven87/llm-wiki-
mcp` puts it at `wiki/CLAUDE.md`. Ours goes at `wiki/SCHEMA.md` to
avoid confusion with the project's `CLAUDE.md`.

---

## 4 alignment questions before code fires

**Q1: Directory scheme — flat categories or nested?**
- (a) Flat: `sources/ai/*.md`, `sources/health-and-fitness/*.md` etc.
  (proposed above, matches Karpathy)
- (b) Nested by date: `sources/2026/08/ai/*.md`. Better filesystem
  scale (fewer files per dir), harder Obsidian graph browsing.
- (c) Nested by category then date: `sources/ai/2026/08/*.md`.
- **Recommend: (a) flat** until ~500 files per dir becomes a problem.

**Q2: LLM classifier at ingest — commit to Option A?**
- Option A costs ~$0.0002 per source, adds 2s latency
- Option B is free but has classification quality gaps
- **Recommend: A**, with `_uncategorized/` fallback for low-
  confidence classifications.

**Q3: Migration — commit to M1 (leave wiki.md as archive)?**
- Any counter-argument? Do you want the ~8000 existing sections
  retroactively migrated?
- **Recommend: M1** — refactor is about going forward.

**Q4: Categories — final list matches GOALS.md 10?**
Proposed list from GOALS.md:
1. `ai/` (from "MIKAI and ambient computing" — but this is meta;
   maybe rename `personal-ai/` or `mikai-build/`)
2. `health-and-fitness/` ("posture and workout optimization")
3. `psychology/` ("self-development — psychology, MBTI, friendships")
4. `career-and-tech/` ("finding a tech job or starting a tech company")
5. `domestic/` ("domestic matters — plants, cat, interior")
6. `settle-and-family/` ("where to settle a family" + "taking care of parents")
7. `consumer-and-economics/` ("consumer groups and political economics")
8. `proposal/` ("proposal spot in China")
9. `ocean-farming-and-street-cleaners/` ("3D ocean farming and robot street cleaners")

Plus utility categories:
- `_uncategorized/` — LLM couldn't confidently classify
- `_meta/` — MIKAI's own build/architecture notes (avoids polluting real categories)

That's 9 goal categories + 2 utility = 11 total. Manageable.

- Should any be merged? split?
- **Recommend: as above**, but flexible on naming per your read.

---

## What I'll code once you sign off

Order:

1. `~/.mikai/wiki/SCHEMA.md` — the instruction doc. ~30 min. **No
   Q's needed** — I can draft, you edit.

2. `infra/graphiti/sources_writer.py` — new module. Given
   `(content, source_stream, timestamp, name)`:
   - Calls LLM classifier (Option A) → category
   - Slugifies name → filename
   - Writes to `~/.mikai/wiki/sources/<category>/<slug>.md` with
     schema-compliant frontmatter
   - Skips if file exists (immutability at filesystem level)
   - Returns path
   ~2 hours.

3. Wire existing ingestion daemons (`claude_threads.py`,
   `mcp_ingest`, `sync.py`) to ALSO call `sources_writer.append(...)`
   in parallel with their existing wiki.md append. ~1 hour.

4. Build 5's `ingest_source.py` grows to know about
   `sources/<category>/` — reads from there in addition to wiki.md.
   ~30 min.

5. Category-specific `index.md` files (e.g., `sources/ai/index.md`)
   — one auto-generated TOC per category. ~30 min.

Total: ~4-5 hours of code once Q1-Q4 answered.

---

## What this refactor does NOT do (deferred to later builds)

- **Doesn't touch wiki.md.** M1 = leave as archive. wiki.md-backed
  ingestion daemons keep running.
- **Doesn't add Voyage embeddings.** E5 (semantic assignment) is
  separate. Categorization is text-based classification, cheaper.
- **Doesn't change concept pages format.** Build 4's Karpathy-shape
  stays. The Notes-synthesis-prose upgrade (from the reference-page
  analysis) is a separate task.
- **Doesn't add the callout / highlight syntax** to concept pages.
  Also a separate task.

Those are Build 9 / Build 10 territory. This design is scoped to the
sources/ layer + SCHEMA.md + categorization.

---

## Fall-back if refactor stalls

If for any reason we can't ship all 5 steps: at minimum ship steps
1-2 (SCHEMA.md + sources_writer.py). That gives Brian a place to
manually drop material into `sources/<category>/`, even before
daemons are wired.
