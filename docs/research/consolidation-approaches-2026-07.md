# Node consolidation approaches — research note

*Written 2026-07-02, driven by the "why doesn't ocean farming surface?"
investigation. Companion to `MEMORY_ARCHITECTURE.md` PART I / PART J.
This doc is the deep-dive reasoning; the parts are the design decisions.*

---

## 1. The problem, in one paragraph

MIKAI's graph accumulates duplicate entity nodes over time — the same
real-world concept represented as `ocean farming`, `Ocean farming`,
`3D ocean farming`, `Ocean farming bots` across five separate nodes,
because Graphiti's inline entity resolution (D-042, capped at 50
candidates) is good for same-thread merges but decays across time and
sources. The cost: RELATES_TO paths that *should* bridge current-week
Claude threads back to older Perplexity research get trapped inside
islands. The dream's Echoes traversal cannot cross bridges that don't
exist. Consolidation is the maintenance discipline that closes these
gaps — and this note works through *how* to do it well.

---

## 2. Organic bridging — the mechanism this is trying to preserve

Entity resolution is not merely a cleanup task. It's the **structural
mechanism by which knowledge graphs compound value with each new source.**
Every merge creates a hub. Every hub creates connective tissue. Every
new document ingested near an existing hub strengthens that hub's
neighborhood. The graph "wires itself" over time.

The direct analogy: **Hebbian learning.** *Cells that fire together
wire together.* At the graph level: entities that co-occur across
documents accumulate edge weight through the shared node they merge
into. The graph is running gradient descent on an implicit loss
function — minimize distance between semantically similar concepts,
maximize distance between distinct ones — that nobody explicitly
designed. Entity resolution is the training step.

This is why PKM tools (Roam, Obsidian, Logseq) "come alive" after
months of use. It's not the tool improving. It's the graph converging.
Consolidation is what lets that convergence happen in an automated
graph rather than requiring the user to hand-canonicalize every mention.

---

## 3. Precedents — how mature systems handle this

Six categories worth studying, ordered by relevance to MIKAI:

### 3.1 Palantir Foundry / Gotham (MDM discipline)

**Key insight**: entity resolution is its own discipline. Master Data
Management. Golden records. Deterministic keys for common cases,
probabilistic matching for the rest, human-in-loop for uncertain,
undo/audit built-in.

Palantir's operators use structured **confidence bands** (high /
medium / low), a **canonical ontology** applied at ingest, and a
**review queue** for the medium-confidence cases. Every merge is
logged and reversible.

This is the elegant long-term target for MIKAI. Its cost: consolidation
becomes a full pipeline with its own state, its own operators, its own
recovery — not a bolt-on to synthesis. That's expensive to build; the
question is *when* MIKAI reaches the point that the investment pays off.

Deferred to future iteration; see `MEMORY_ARCHITECTURE.md` PART I.8 for
the migration path.

### 3.2 Google Knowledge Graph / Wikidata (canonical IDs)

**Key insight**: prefer deferring to authoritative external identifiers
over solving resolution from scratch. Every Google KG entity has a MID
(Machine ID); every Wikidata entity has a Q-ID. New content resolves
to these; the resolution problem shrinks to "does this entity exist in
the canonical registry?"

Freebase (Google's 2010 acquisition) had to solve the exact resolution
problem MIKAI is facing. Google threw a full engineering team at it.
Then they got the leverage of Wikipedia's editors deciding what counts
as canonical.

**Relevance to MIKAI**: use Wikidata Q-IDs as an *auxiliary* signal for
public entities (companies, cities, well-known concepts). Rejected as
*primary* mechanism because most of MIKAI's entities are private —
friends, personal projects, half-formed ideas — with no Wikidata
anchor. Combine with local resolution rather than replace.

### 3.3 Zettelkasten (Luhmann, 1950s) — the intellectual origin

**Key insight**: value emerges from connections between notes, not
from the notes themselves. Every slip references others by ID. A
well-referenced concept becomes a hub connecting many slips.

Niklas Luhmann accumulated ~90,000 slips over decades. The connective
tissue was the actual value. He didn't have automated resolution — he
did it by hand as part of his reading practice. Modern automated
resolution is the industrial version of what Luhmann did artisanally.

**Relevance to MIKAI**: the target UX is that "MIKAI hands Brian a
Luhmann-scale slip-box that maintains itself." Consolidation is a
prerequisite for that.

### 3.4 Roam Research / Obsidian / Logseq (user-driven)

**Key insight**: put the resolution burden on the human. The
`[[wiki-link]]` name IS the canonical form. Different spellings =
different nodes. Aliases as first-class means one page responds to
multiple names.

Elegant in its minimalism. Only works when the user is actively
curating. Fails at scale — you don't want Brian manually merging
"Ocean farming" and "3D ocean farming" every week.

**Relevance to MIKAI**: the *review queue* pattern (see PART I.4.5)
is Roam's aliasing done as batch. Uncertain merges land in a section
of the wiki; Brian resolves them during his weekly read. Combines
Palantir's confidence-band discipline with Roam's user-checkpoint
minimalism.

### 3.5 Anchor Modeling / Data Vault (structural prevention)

**Key insight**: prevention is more elegant than cure. Design the
ingestion so duplicates can't be created in the first place. Enforce
a business key at ingestion; the key determines the anchor;
duplicates are structurally impossible.

**Relevance to MIKAI**: apply at ingest via better extraction prompts.
"Always lowercase; strip articles; use singular form." Reduces the
downstream consolidation surface without solving it.

Combine with I.4's cluster detection rather than replace. Prevention
handles new duplicates; consolidation handles the legacy backlog.

### 3.6 Neo4j GDS (community detection algorithms)

**Key insight**: use graph structure itself — density, connectivity,
embedding neighborhoods — to detect likely duplicates. Weakly
Connected Components. Louvain community detection. Node similarity
via Jaccard or cosine.

**Direct precedent for PART I.4.** Cluster detection over pairwise
comparison. The LLM (or a human) verifies clusters, not pairs.

Impact: turns O(n²) pairwise LLM calls into O(cluster_count) — for
1,694 clusters averaging 3 nodes each, that's 1,694 calls vs 5,082
pairwise. Plus the LLM sees the full cluster context, giving better
decisions than a series of transitively-inconsistent pairwise votes.

---

## 4. The elegance debate — V1 vs V2 for MIKAI

Two implementations of consolidation with different cost / elegance
profiles.

### V1 — LLM-verified cluster consolidation (currently shipped)

Implemented in `infra/graphiti/consolidation.py` on `feat-dream-echoes`
(commit `f5f9ff0`). Every cluster verified by an LLM call. ~$1.20 per
nightly run at DeepSeek pricing. Converges over ~30 nights.

**Where V1 wins**:
- Correctness — LLM catches proper-noun collisions ("Sam Altman" vs
  "Sam") that a pure-rules approach would miss
- Explanatory — every merge has a natural-language reason logged
- Robust to ambiguous cases (medium-similarity bands)

**Where V1 is unsatisfying**:
- Depends on cloud LLM. If DeepSeek is down or the balance is out (as
  happened 2026-07-01), the whole nightly pass fails
- The LLM cost is not zero. At scale (100K+ entity graph, weekly
  reingestions), the arithmetic gets meaningful
- Feels like the LLM is doing work rules could do — for identical
  normalized names with cosine > 0.95, there is no ambiguity to
  resolve

### V2 — Rule-first, LLM-optional (current design intent)

Not yet coded. Design:

- **Auto-merge**: same normalized name AND cosine > 0.92 → merge, no
  LLM. Handles ~80% of the 1,694 backlog clusters at zero cost.
- **Short-name guardrail**: names < 5 chars ("Sam", "AI", "MSP")
  stay in the review queue even at high similarity. Prevents
  catastrophic proper-noun collisions.
- **Review queue**: 0.75 < cosine < 0.92, or high-similarity clusters
  gated by the short-name guardrail. Lands in wiki
  `## Pending consolidations`; the user resolves during weekly read.
- **LLM verification** (optional, `--llm-verify` flag): for the medium
  band, or for confirming clusters above the guardrail. Bounded at
  ~20 calls per run = ~$0.05.

**V2 total cost**: $0 default. ~$0.05/night with LLM enabled. Effectively
free.

**V2 risk**: ~5% false-merge rate on ambiguous names. Mitigated by
- the short-name guardrail
- the `merged_from` attribute on canonical nodes that enables an unmerge
  utility (currently unbuilt but straightforward)
- the review queue for the medium band

**V2 wins on**: elegance, cost, no cloud dependency, faster nightly
runs (no network latency in the hot path). Aligns with rule-first as
articulated in `MEMORY_ARCHITECTURE.md` J.4.

### The bet

Personal knowledge graphs at MIKAI's scale (< 1M entities) can tolerate
occasional bad merges if unmerge is cheap. The LLM verification was a
**precaution against a risk that isn't actually costly** — a wrong merge
is one broken bridge, easily fixed on the next dream when the log shows
it. LLM cost buys 5% risk reduction on a low-cost failure mode. Bad
trade at MIKAI's scale.

**V2 is the current design intent.** V1 is shipped as a proof-of-mechanism
and remains available for the medium band as `--llm-verify`. Migration
to V2 as default: pending a follow-up implementation pass.

---

## 5. Model economics — the four call classes

MIKAI's LLM calls decompose into four classes with distinct
frequency / volume / quality / cost profiles. See PART J for the
formal table. This section captures the reasoning behind why the
distinction matters.

### 5.1 Interactive query (user asks MIKAI in Claude)

Volume: ad-hoc, 0–20/day. Quality bar: high (Brian sees the reasoning).
Rate limits: whatever Brian's Claude subscription gives him.

**Chosen backend**: Claude Max via MCP tool (D-040). Zero marginal
cost — already paid. The 2026-04-20 MCP eval validated this pattern
(3-2-1 vs baseline).

Constraint: same rate limit as Brian's own chat. If a background job
saturates that pool, interactive queries starve. This is the reason
FIGS and consolidation cannot use `claude -p` for high-volume batch.

### 5.2 Real-time decision (FIGS tick)

Volume: 3 scheduled ticks/day, ~3–5 LLM calls each = ~10–15/day total.
Quality bar: high (single user-facing output).

**Chosen backend**: Claude via `claude -p` (Max first-party OAuth). Same
subscription pool as interactive, but bounded volume keeps it well
within limits.

### 5.3 Background synthesis (dream, echoes, consolidation V1)

Volume: ~5 calls/night baseline, +60 for consolidation. Quality bar:
medium (structured JSON output; no reasoning ceiling needed).

**Current backend**: DeepSeek V3 at $0.27/M input. Serviceable.

**Upgrade path**: Gemini 2.0 Flash Lite at $0.038/M input — **7×
cheaper** at equivalent JSON extraction quality. Swap is a `base_url`
edit at the sidecar's LLM client. See O-054.

**Ultimate target**: local LLM (Qwen 2.5 32B via Ollama). Zero cost.
Blocked by 8 GB RAM on current hardware; deferred until a 32 GB+
M-series machine.

### 5.4 High-volume extraction (per-episode Graphiti)

Volume: 100s/day when new content flows. Quality bar: low-medium
(structured JSON).

Same backend allocation as 5.3. Unify with synthesis in the LlmBackend
protocol so per-run routing is a config edit, not a code change.

### The design principle

**LLM choice is a policy layer, swappable at the sidecar boundary.**
Product code should never mention "DeepSeek" or "Claude" — those live
in the policy layer. This is the 12-factor version of Palantir's
"resolution is its own discipline": *model choice is its own discipline*.

Ships as O-054 (see PART J.5).

---

## 6. Hardware — what changes with a memory upgrade

Current 8 GB Mac blocks local LLM. Docker Desktop + Neo4j + graphiti
sidecar + macOS baseline already consume ~5–6 GB. Loading even a 3B
model on top pushes into constant swap → hammers SSD, kills battery,
slows the whole machine.

At **32 GB (M-series)**:
- Qwen 2.5 32B Q4 quantized: fits comfortably at ~24 GB during inference
- Or 14B if 32B feels tight alongside other apps
- All synthesis + extraction + consolidation LLM cost → **zero**
- Removes the cloud dependency for background work entirely
- Interactive queries still use Claude Max (it's better and free-via-subscription)

At **64 GB+**:
- 70B models fit; quality approaches GPT-4 tier
- Multiple concurrent models possible (specialized extractor + verifier)

The MIKAI architecture is designed to make this upgrade a config change,
not a rewrite. See PART J's LlmBackend protocol.

---

## 7. Ocean farming as the empirical test case

The concrete case that drove this investigation:

- 5 substantive Perplexity threads on 3D ocean farming exist on disk
- 4 of 5 landed in graph on ingest
- 1 dropped in the 2026-07-01 DeepSeek balance-out (63-saga cleanup gap)
- Extraction was inconsistent across the 4 that landed — 2 of 4 initially
  missed the `3D ocean farming` entity
- Manual MENTIONS attach via Cypher + targeted reingest of the missing
  saga brought perplexity mentions of `3D ocean farming` from 3 → 5

**Total ocean-farming coverage across the graph** (post-fix):

| Source | Entity | Mentions |
|---|---|---|
| apple-notes | `Ocean farming` | 26 |
| claude-code | `ocean farming` | 18 |
| perplexity | `3D ocean farming` | 5 |
| mikai-default | `Ocean farming bots` | 3 |
| claude-code (meta) | various | 6 |

**58 episodes across 4 source classes.** Consolidation V2 would collapse
these into a single canonical `ocean farming` node with ~58 mentions
and edges spanning years of Brian's research + capture + strategy. That
would give the Echoes pass a strong bridge from any current-week Claude
anchor back to the older Perplexity research — which was the original
"why doesn't ocean farming surface?" question that started this whole
investigation.

The empirical test: after consolidation lands, does an unprompted
Claude conversation about (say) food technology or Kenya cause the
next dream's Echoes to surface ocean farming? If yes, the whole pipeline
— ingest + extract + consolidate + echo — works end-to-end. If no,
diagnose which stage's assumption was wrong and iterate.

---

## 8. Open questions surfaced

- **O-053** — Consolidation as PART B phase 5 (ratified in PART I.7)
- **O-054** — LlmBackend protocol (see PART J.5)
- **Unnumbered** — V2 rule-first consolidation as default: needs
  implementation + migration plan for the V1 code currently shipped
- **Unnumbered** — Unmerge utility: cheap Cypher utility that undoes a
  merge by re-splitting on `merged_from` attribute. Prerequisite for
  V2's "accept 5% false-merge risk" bet
- **Unnumbered** — Prevention layer: extraction-prompt updates that
  reduce duplicate-creation rate at ingest. Combines with V2 rather
  than replaces
