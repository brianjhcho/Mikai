# Architecture Ideas — nashsu port + wiki ingest

Ideas captured during the port investigation that aren't bugs but potential
architectural changes worth evaluating. Not commitments — think of this as the
"maybe someday" list. Move items to `docs/DECISIONS.md` when adopted, or to
`docs/OPEN.md` when actively debated.

## 1. Smart merge-before-write ingest pattern

**Observation (Brian, 2026-08-18):** For every new source, the current pipeline
generates candidate wiki pages first, then tries to merge each candidate into
whatever exists. This means every shared entity (mikai, hermes-agent, etc.)
takes 2× LLM calls per source that touches it: generate then merge. On a 46-source
run this compounds heavily and creates 12+ merge collisions under parallel load.

**Alternative pattern:**

```
1. LLM reads new source
2. LLM queries the wiki (semantic search over embeddings)
   for existing pages related to the source's themes
3. LLM decides per theme:
     "this is genuinely new" → create a new page
     "this belongs on existing page X" → append/refine there directly
4. Write only the decisions that survived step 3
```

**Trade-offs:**
- FEWER LLM calls per source (no separate merge round)
- FEWER merge collisions (LLM makes structural decisions upfront)
- REQUIRES vector embeddings to be enabled during ingest (step 2 depends on
  semantic retrieval; slug-listing alone is too weak a signal)
- REQUIRES prompt design that outputs structured "add-to" vs "create-new"
  decisions the write pipeline can execute deterministically
- CHANGES upstream nashsu's ingest architecture — significant deviation

**Cost estimate:** ~1-2 weeks engineering to prototype; probably 2× that to ship
with parity confidence against current pipeline.

**When to reconsider:** if the merge-failure problem on parallel runs proves
unfixable via simple retry-with-backoff, OR if we ever migrate off nashsu and
own the ingest pattern ourselves.

## 2. Two-phase parallel ingest with serial commit

Fable-5's parallelism postmortem: nashsu's `[1,5]` worker clamp wasn't rate-limit
politeness, it was semantic — low concurrency lets `wiki/index.md` accumulate so
each Pass-2 sees a richer link universe.

**Fix without giving up throughput:** Pass-1 (source analysis) runs parallel;
Pass-2 (page generation + write) serializes through a commit coordinator that
refreshes the wiki-state snapshot each source sees.

Concrete: modify `src/lib/ingest.ts` to split its two passes; add a barrier
around the write-and-index-update block. Preserves ~80% of 16-worker throughput
while restoring wikilink density.

**Cost estimate:** 2-3 days engineering + verification against V.005 serial baseline.

## 3. Retry-with-backoff on page-merge

Simple, small, high-leverage. Current code (`src/lib/page-merge.ts`) falls straight
to lossy concatenation on `claude -p` exit-code-1. Under 16-worker load, we see
12+ merge failures per full ingest.

Add: retry 3× with exponential backoff (2s, 8s, 32s), THEN fall to concatenation.
Doesn't change architecture; just recovers transient rate-limit failures.

**Cost estimate:** ~2 hours implementation + test.

## 4. Semantic-extraction evaluation harness

Formal acceptance metric for "is the ingest good enough":

Sample corpus: the 46 sources already in golden-set (V.001-V.004) — journals +
Claude threads + cross-language content + abbreviated-month backfill. This spans
the real variety of Brian's content.

Human evaluation protocol per source:
1. Coverage — did we capture the important semantic content?
2. Attribution — do `sources:` frontmatter fields correctly cite origins?
3. No fabrication — do wikilinks resolve to real pages?
4. No language drift — is body in target language?
5. Decomposability — are concept-worthy ideas in their own pages, not buried?

Ship gate: 80% coverage, 100% attribution, <5% dangling, 100% language pass,
≥3/5 decomposability across the sample.

**Cost estimate:** ~2-3 hours human scoring per pipeline being evaluated.
Reusable across future ports/pipelines.

## 5. Headless HTTP wrapper for autonomous MCP access

Long-term: MIKAI's autonomous daemons need graph/search access without requiring
the LLM Wiki desktop app to be running. Options considered:

- **A** — keep tailscale-serving the desktop app (works today, requires app open)
- **B** — build a thin Node/Python HTTP service on top of the wiki files that
  exposes MCP-over-HTTP, runs as LaunchAgent, no app dependency
- **C** — extract nashsu's search + graph modules into MIKAI daemons (heaviest)

Recommend B when the "app must be running" constraint bites in real use. Not
before. See earlier discussion in `~/.claude/plans/fuzzy-shimmying-wreath.md`.

## Not in scope for this doc

- Bug fixes (those go in `docs/OPEN.md` or straight to code)
- Production ingestion changes (production `~/.mikai/wiki/` decisions live in
  `docs/DECISIONS.md`)
- Feature ideas unrelated to ingest/port (those need their own home)
