# Concept navigation — deferred options (A and B)

**Status:** Deferred, not rejected. 2026-08-07.

**Context.** Brian's stated goal: ask MIKAI a question and get grouped
insights across many threads, so he doesn't have to hold 15 claude.ai
tabs open. Two `make ask` probes on 2026-08-07 (against `Task State
Awareness 2.0` and `AGENT MEMORY`) showed the raw corpus contains the
material but retrieval quality is inconsistent — one query synthesized
cleanly across threads, the other returned mostly header-only fragments.
Chose path **C (retrieval-only fixes, no new storage layer)** as the
first move because the AGENT MEMORY answer proved the substrate can
already close-the-tabs when retrieval returns real content.

Path C keeps ENTITY_MODEL.md unchanged (entities = people, orgs, things,
places — concepts stay in prose). If C proves insufficient after
retrieval is clean, revisit A vs B.

The rendering/schema question — **freeform topic pages (Karpathy shape)
vs schema-driven files (Gemini shape)** — is settled independently: if
A or B is ever built, files must be freeform prose with `[[wikilinks]]`,
never a pre-committed template. Structure follows content, not the
other way around. Gemini's "Definition / Core State Variables / Failure
Vectors / Architectural Relationships" template is the exact
schema-invention failure mode we've pushed back on repeatedly.

---

## Option A — Expand entities to include concepts

Loosen ENTITY_MODEL.md so concepts (Task State Awareness, Agent Memory,
Sumimasen, Noonchi, etc.) become first-class entities alongside people,
orgs, things, places.

**Pros**

- Concepts get first-class navigation — dedicated pages, walkable via
  `ENTANGLED WITH` edges, findable via existing entity retrieval.
- The cockpit's cross-thread `ENTANGLED WITH` edges (memory:
  `entity-model-2026-08`) would light up on the topics you actually
  think about.
- Directly enables "close 15 tabs safe" — the concept page IS the
  tab-collapse.
- Symmetric with how Brian already thinks — he refers to "AGENT MEMORY"
  and "Task State Awareness 2.0" as *entities*, not as prose fragments.

**Cons**

- **Boundary erosion.** "Task State Awareness" — clearly a concept.
  "state" alone? "awareness"? Concept boundaries aren't sharp the way
  proper nouns are. Every dream pass now has to draw a line and defend
  it.
- **No canonical name resolver.** "Sarah Chen" resolves to itself.
  "Task State Awareness" vs "task state awareness" vs "TSA 2.0" vs
  "task-state awareness" — no natural canonicalization. Same problem
  Wikipedia solves with redirects, which is real infrastructure.
- **Sprawl.** 375 entities is human-legible. Concept expansion likely
  5–10x's that. Ontology stops being scannable.
- **Extraction cost jumps.** Proper-noun extraction is well-studied
  (spaCy does it in milliseconds). Concept extraction is a real LLM job
  per section — nightly dream pass gets slower and more expensive.
- **Discipline drift.** Every future contributor will re-litigate the
  boundary. The current rule is defensible in one sentence ("nouns that
  name real things"). "Nouns that name real things or concepts" isn't.

---

## Option B — Add a separate concept layer

Introduce a new `wiki-concepts.md` (or `wiki/concepts/*.md`) alongside
the existing entity ontology. Keep ENTITY_MODEL.md pure. Concepts get
their own freeform Karpathy-shape pages with `[[wikilinks]]` back to
raw thread sections.

**Pros**

- Doesn't touch ENTITY_MODEL.md — the "nouns name real things" rule
  stays defensible.
- Karpathy-native: one file per concept, freeform prose, wikilinks —
  matches the actual gist Fable's research turn cited.
- Cheaper to iterate: a bad concept file is deleted; a bad expanded
  entity model requires a doctrine rewrite.

**Cons**

- **Two navigable substrates** — entities and concepts. Every consumer
  (mikai_ask, cockpit, Inspector) now has to know about both. Twice the
  retrieval surface, twice the "did we look everywhere" question.
- **Same boundary problem, different location.** "What counts as a
  concept worth its own page?" still has to be answered. Solved once
  per file instead of doctrinally, but still solved by someone.
- **New dream pass** — `dream concepts` subcommand to write and refresh
  concept pages. More cron, more LLM cost, more failure surface.
- **Stale-file risk.** Concept pages are precomputed summaries; they
  drift the moment new source material arrives. Requires invalidation
  rules or acceptance of staleness between dream runs.

---

## Path C — Query-time synthesis only (chosen 2026-08-07)

No new storage layer. Fix the retrieval pipeline so mikai_ask reliably
returns real content across thread boundaries, then let the LLM
synthesize on demand.

**Rationale.** The AGENT MEMORY probe on 2026-08-07 produced exactly
the format Brian wanted — 4 themes across threads, timestamped
citations, honest boundary-marking ("The substrate is silent on…").
Zero new files. Zero new schema. When retrieval works, C works. When
retrieval doesn't work, neither A nor B saves us — both assume
retrieval returns real content.

**Cost model.** Every ask = one LLM call. Slower than reading a
precomputed page (~10-30s vs instant), but no drift, no invalidation,
no schema.

**Revisit A vs B if:**

- After retrieval fixes land, cross-thread synthesis quality is still
  inconsistent → likely A (need static concept nodes).
- LLM cost per ask becomes prohibitive OR ask latency crosses ~60s →
  likely B (precompute the hot concepts).
- Brian starts asking for "which concepts do I keep circling?" as a
  discovery question (not just "what did I decide about X?") → likely
  A (concepts as first-class navigation targets).

---

## Related

- `docs/ENTITY_MODEL.md` — the doctrine Option A would loosen.
- `docs/RETRIEVAL_STACK.md` — where path C's fixes land.
- Memory `entity-model-2026-08` — current file-first entity approach.
- 2026-08-07 `make ask` probes — first-run TSA 2.0 (failed retrieval),
  first-run AGENT MEMORY (successful cross-thread synthesis).
