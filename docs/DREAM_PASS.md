# DREAM_PASS — semantic consolidation for the wiki

**Status:** design, 2026-08-11. Implementation target: `infra/graphiti/dream_pass.py` (concept-level consolidation) + `infra/graphiti/dream_apply.py` (post-approval executor). Supersedes/refines `docs/DREAM_WIKI_RUNTIME.md` for the concept-page layer (that doc's original design lived in `infra/graphiti/dream.py` which read the now-deprecated Neo4j graph; `dream.py` will move to `infra/graphiti/legacy/dream_graph.py`).

> **⚠ Deferred (2026-08-12).** Full dream_pass implementation is deferred until the full corpus is ingested and the Karpathy substrate is stable. When work resumes, this doc needs the following revisions to match Brian's 2026-08-12 architectural corrections:
> - **Remove "surface tensions don't resolve" invariant** — that was conflating data-management concerns with attention-allocation concerns. L2 (data management) resolves; L4 surface engine handles attention pressure separately.
> - **Adopt recency-wins with explicit invalidation** per Vectorize/Hindsight (May 2026). Losers move to `_retired/` with `superseded_by` breadcrumb (rohitg00 v2 pattern). Non-destructive, safe because L1 sources preserve full audit trail.
> - **Autonomous merge execution** — remove the human-approval gate for high-confidence merges. Thresholds TBD but roughly: LLM-conf ≥ 0.85 AND Jaccard ≥ 0.45 → auto-execute; borderline (0.7-0.85) → inbox for optional review; below 0.7 → skip. This matches Mem0/OpenClaw pattern. Justified because MIKAI's L4 target user is a *consumer of surfaced attention*, not a *curator of substrate* — the human-in-the-loop model of Karpathy's lint-only design doesn't fit.
> - **`dream_apply.py`** becomes optional (only used for borderline proposals that landed in inbox). Auto-executed merges happen inline during dream_pass.
> - **Cluster-level dedup** — pairwise proposals had a magnet-page problem in the 2026-08-11 test run (3 pages all pointed at `conversation-history-as-corpus`). Cluster detection needed before autonomous merges to avoid the N-1 pairwise-execution bug where the target no longer exists after the first merge.
>
> **Do not build these changes now.** Wait until (a) full corpus ingest completes and (b) the Karpathy Wiki architecture (sources/, concepts/, autonomous ingest pipeline, lint pass running) is operationally stable. Consolidation is Phase 2 work.

**Pipeline position:**

```
raw sources → wiki.md capture → sources/*.md → concepts/*.md → LINT PASS → [DREAM PASS] → L4 salience
                                                                                 ↓
                                                                    consolidations, re-syntheses, tension surfacings
```

Dream runs **after Lint**, at low cadence (nightly or weekly), and is the only LLM-heavy pass in the pipeline. It reads concept pages + their source citations, detects semantic redundancy, and produces denser wiki content — never destructively.

---

## Design principles

**1. Surface tensions, don't resolve them.** MIKAI's load-bearing invariant, inherited from prior dream work + Park et al's Generative Agents. Contradictions across the corpus become first-class content, not resolution decisions.

**Precedent context (from research 2026-08-11):** this is a *minority position* among memory-consolidation systems. Mem0 auto-classifies to DELETE. Vectorize's default is recency-wins. Karpathy's own posture (secondhand) flags contradictions and lets the LLM pick a winner. Only Park et al. and `penfieldlabs` (typed-edge implementation) preserve contradictions as first-class data. MIKAI joins that lineage explicitly.

**2. Non-destructive supersession over destructive merge.** From `rohitg00 LLM Wiki v2`: when two concept pages consolidate, the losing page gets `superseded_by: <canonical-slug>` frontmatter and moves to `concepts/_retired/`. Its citations transfer to the canonical page. Retrieval routes via alias table. **Nothing is lost.**

**3. Human approval for every merge.** From `kytmanov/obsidian-llm-wiki-local`: production systems that ship semantic merges have publicly hit "silent deletion" failures. MIKAI's default is proposals to `concept-inbox.md`; human approves before any concept-page mutation.

**4. Ground, don't invent.** Every claim in the merged synthesis must trace to a source in the merged Sources section.

**5. Weight depth over volume.** 3 rich sources beat 20 citation dumps. When re-synthesizing, prioritize sources with high evidence-density.

**6. Mark movement.** Note state transitions in synthesis prose ("exploring → decided → acting → stalled" or "believed X in 2015 → revised to Y in 2018").

The four MIKAI dream rules from `docs/DREAM_WIKI_RUNTIME.md` (surface tensions / weight depth / mark movement / ground don't invent) apply here at the concept-page level, just as they applied at the wiki.md level in the original design.

---

## Inputs

- `~/.mikai/wiki/concepts/*.md` (all concept pages, ~70 currently)
- `~/.mikai/wiki/sources/**/*.md` (source bodies referenced by concept pages)
- Latest `lint-report-YYYY-MM-DD.md` (to skip already-flagged structural issues)
- `~/.mikai/wiki/log.md` (for prior dream deltas, to avoid re-proposing the same merges)

## Outputs

- **Merge proposals** → `~/.mikai/wiki/concept-inbox.md` under `## dream-consolidate proposals YYYY-MM-DD`
- **Re-synthesized concept pages** → direct rewrite of `concepts/<slug>.md` (only for pages meeting the re-render trigger below, and only `authored: llm` or `authored: partial` pages — never `authored: hand`)
- **Retirements** (post human approval) → move loser to `concepts/_retired/<slug>.md` with `superseded_by:` frontmatter, transfer citations to canonical
- **Delta log** → append to `~/.mikai/wiki/log.md`

## The four sub-passes

Modeled on Anthropic Dreams' public 4-phase pattern (`Orient → Gather Signal → Consolidate → Prune & Index`, per claudefa.st docs):

### Phase A — Orient (cheap, no LLM)

Read all concept pages. Compute a lightweight fingerprint per page:
- Frontmatter fields (slug, title, aliases, tags, salience, best_goal)
- TL;DR text (first 300 chars)
- Notes prose (first 500 chars)
- Source-citation count and unique-date count

Build a candidate list for downstream phases. Skip pages tagged `authored: hand` in full (only citations may accrete).

### Phase B — Gather Signal (dedup detection)

**Two-phase distillation per `boostedcore` gist:**
- **Cheap prefilter:** for each page pair, compute lexical similarity on TL;DR + title + aliases (Jaccard on tokens, or simple embedding cosine if we've built the embedding index). Return pairs with similarity ≥ 0.15.
- **LLM verification:** for each candidate pair, one LLM call: *"Do these two concept pages capture the same underlying idea? Return {same: bool, canonical_slug: str, aliases_to_absorb: [str], why: str, tension: bool}"*. `tension: true` means they overlap but disagree — do NOT propose merge, propose a `## Tensions` section addition to both.

**Threshold-banded action per `boostedcore` gist:**
- Prefilter similarity < 0.15 → skip (unrelated)
- 0.15 ≤ similarity < 0.30 AND LLM says same → flag for human review in inbox
- similarity ≥ 0.30 AND LLM says same → strong merge candidate (still needs human approval, but pre-highlighted)
- LLM says `tension: true` → tension proposal (both pages update, neither retires)

### Phase C — Consolidate (proposals, not writes)

For each strong merge candidate:
- LLM drafts the merged synthesis: canonical page's new TL;DR + Notes + Aliases + Sources (union of both pages' citations)
- Writes proposal to `concept-inbox.md`:
  ```markdown
  ## dream-consolidate proposal — 2026-08-11
  ### merge: [[faith-and-spirituality]] ← absorbs [[faith-and-meaning]]
  **Distance:** 0.09 (LLM verified: same)
  **Reason:** Both pages evidence Brian's Christian devotional writing 2013-2018; separate slugs are artifacts of open-vocab classifier variance.
  **Proposed canonical TL;DR:** ...
  **Aliases to add:** [faith-and-meaning, faith-and-scripture-reflections]
  **Citations union:** 18 → 34
  **APPROVE / REJECT** (edit this file to append your call)
  ```

For each re-synthesis candidate (see trigger below):
- LLM regenerates TL;DR + Notes from the accumulated Sources
- Writes directly to `concepts/<slug>.md` (this is a re-render, not a mutation of meaning)
- Preserves `authored: hand` fenced blocks if any

For each tension pair:
- LLM proposes a `## Tensions` addition to both pages
- Writes proposal to inbox (human approves the exact prose)

### Phase D — Prune & Index (post human approval only)

Human edits `concept-inbox.md` marking `APPROVE` on individual proposals. A separate `dream_apply.py` reads approved proposals and executes:
- Move loser to `concepts/_retired/<slug>.md` with `superseded_by: <canonical>` frontmatter
- Update canonical page with new synthesis + aliases + citations
- Update `concepts/index.md`
- Append delta to `log.md`

Rejected proposals stay in the inbox with `REJECT` marker so the next Dream pass doesn't re-propose them.

---

## Triggers

**Merge scan (Phase A + B):** weekly. Full pairwise scan is O(N²) but cheap in Phase A; Phase B is LLM-per-candidate, bounded by threshold.

**Re-synthesis:** per-page trigger. Concept page enters re-render queue when EITHER:
- `touch_count` grew by ≥ 5 since last `last_rerender` frontmatter timestamp, OR
- ≥ 2 new distinct source dates since last render, OR
- Human manually queues via `dream --resynthesize <slug>`

`touch_count: 1` pages **never enter re-render** — they render only as stubs (per stub-quality rules from earlier research).

**Tension detection:** runs whenever merge scan runs.

---

## What Dream MUST NOT do

- Never rewrites `authored: hand` pages
- Never executes a merge without human approval
- Never deletes a page (retirement moves to `_retired/`, doesn't delete)
- Never invents claims not present in the merged sources
- Never resolves a values-tension into one canonical position
- Never operates on the raw `wiki.md` (that was the graph-era design, superseded)

---

## Reference implementations + prior art

**MIKAI internal:**
- `docs/DREAM_WIKI_RUNTIME.md` — original graph-based dream (superseded for concept layer, still valid framing)
- `docs/research/dreaming-comparison-2026-06.md` — Anthropic Dreaming vs MIKAI comparison
- `docs/research/consolidation-approaches-2026-07.md` — approach research
- Memory: `dual-memory-consolidation-problem.md` — design conversation from June 2026

**External:**
- `boostedcore` gist — two-phase distillation + threshold-banded merge (the closest existing spec)
- `rohitg00` LLM Wiki v2 — supersession-with-lineage pattern (MIKAI adopts this)
- `penfieldlabs` — typed edges for first-class contradictions (validates surface-tensions posture)
- `kytmanov/obsidian-llm-wiki-local` — conservative posture: humans approve merges
- Park et al. 2023 (Generative Agents) — additive reflection without collapse (MIKAI's philosophical precedent)
- Anthropic Dreams (public, `claudefa.st/blog/guide/mechanics/auto-dream`) — 4-phase pattern
- Vectorize Hindsight blog — 4 levers (Importance/Merge/Decay/Eviction), 3 contradiction policies

**What MIKAI diverges on:** surface-tensions is minority position. Almost every production system resolves contradictions. MIKAI's moat lives here (tensions become first-class content the LLM can reason over) but should be defended explicitly against the alternative.

---

## Cross-references

- `docs/LINT_PASS.md` — structural hygiene runs before Dream
- `~/.mikai/wiki/SCHEMA.md` — governance rules for concept pages
- `docs/DREAM_WIKI_RUNTIME.md` — original graph-era dream design (superseded for concept layer)
- `infra/graphiti/dream.py` — legacy graph-reading dream (stopped since 2026-08-11; will move to `infra/graphiti/legacy/dream_graph.py`)
- `infra/graphiti/dream_bootstrap.py` — currently computes L4 salience; will be renamed `infra/graphiti/salience_pass.py`
- `infra/graphiti/dream_lint.py` — currently does structural lint checks; will be renamed `infra/graphiti/lint_pass.py`

## Rename map (executed as part of this build)

| Old path | New path | Reason |
|---|---|---|
| `infra/graphiti/dream_lint.py` | `infra/graphiti/lint_pass.py` | Was mis-prefixed `dream_`; it's lint work |
| `infra/graphiti/dream_bootstrap.py` | `infra/graphiti/salience_pass.py` | Was mis-prefixed `dream_`; it's salience/L4 work |
| `infra/graphiti/dream.py` | `infra/graphiti/legacy/dream_graph.py` | Legacy graph-era dream; graph deprecated |
| (new) | `infra/graphiti/dream_pass.py` | The actual concept-level Dream Pass |
| (new) | `infra/graphiti/dream_apply.py` | Post-human-approval executor for merges |

All launchd plists (`com.mikai.dream`, `com.mikai.dream-nightly`, `com.mikai.dream-weekly`) need corresponding rewrites to invoke the new script names.
