# MIKAI Semantic Matching Audit

**Date:** 2026-09-13
**Scope:** Every layer of MIKAI's semantic matching stack, marked PROVEN / EXPERIMENTAL / EXPERIMENTAL-BUT-CONSTRAINED, with references and risks.
**Purpose:** Distinguish where we're standing on validated methodology vs where we're making creative bets that need explicit tracking.

## Verdict summary

- **PROVEN**: 3 layers (embedding model, similarity metric at current scale, retire+rewrite)
- **EXPERIMENTAL-BUT-CONSTRAINED**: 2 layers (LLM adjudication, embedding proxy shape)
- **EXPERIMENTAL**: 2 layers (threshold tiers, mention extraction wiring)
- **Biggest risk**: threshold tiers are picked without calibration against a labeled benchmark; false-positive rate at 0.85 tier-2 was empirically ~30% on our test.
- **Recommended fix priority**: (1) parser variants for mention extraction (blocks the whole gate); (2) threshold calibration against a small labeled pair set (~100 pairs); (3) revisit embedding-proxy shape if gate keeps missing real synonyms.

---

## Layer-by-layer

| # | Layer | Choice | Verdict | Reference |
|---|---|---|---|---|
| 1 | Embedding model | Ollama `nomic-embed-text` v1 (768-dim, 8k context, local, subscription-safe) | **PROVEN (constrained)** | Nomic 2024 tech report; MTEB benchmark |
| 2 | Similarity metric | Brute-force numpy cosine on pre-normalized vectors, N≈1200 | **PROVEN** | Standard IR; FAISS Flat index rationale |
| 3 | Embedding proxy | Title + first paragraph of each existing page as canonical rep | **EXPERIMENTAL-BUT-CONSTRAINED** | BLINK uses full document; Wikipedia uses lead paragraph; no direct citation for our shape |
| 4 | Threshold tiers (ARCH-034) | 0.95 hard / 0.85-0.95 LLM-judge / <0.85 pass | **EXPERIMENTAL** | Picked from vibes + one empirical test showing 30% FP at 0.85 |
| 5 | LLM adjudication | `claude -p` pairwise MERGE/KEEP/HUB judgment on candidate pairs | **EXPERIMENTAL-BUT-CONSTRAINED** | Analogous to LLM-as-judge literature; nashsu's own `detectDuplicateGroups` uses same shape |
| 6 | Mention extraction | Parse nashsu stage-1 analysis output for `SLUG DECISION: GENUINELY NEW` lines | **EXPERIMENTAL** | Our creative wiring; BLINK/DITTO extract mentions differently |
| 7 | Retire-not-delete + xref rewrite | Retire stub with `retired_to:` frontmatter + `rewriteCrossReferences` | **PROVEN** | Wikipedia redirect model; nashsu native `rewriteCrossReferences` |

---

## Detailed notes per layer

### 1. Embedding model — nomic-embed-text v1 (PROVEN, constrained by policy)

**Choice**: Ollama-hosted `nomic-embed-text` v1. 768-dim, 8192 context, English-only, runs locally.

**Reference**: Nomic 2024 technical report (arXiv:2402.01613). On the MTEB (Massive Text Embedding Benchmark) short-context set, nomic-embed-text v1 outperforms OpenAI's `text-embedding-ada-002` and `text-embedding-3-small` on 2 of 3 benchmark categories. It's the first fully-open-source (weights + data + training code) English embedder to beat those OpenAI models. On long-context (LoCo benchmark), it beats jina-embeddings-v2 and matches Ada-002.

**Verdict**: PROVEN for the class it was picked from. Constrained because we can't use paid embedders (subscription-only policy — no Voyage-3, no OpenAI text-embedding-3-large, no Cohere embed-v3). Among free/local options, nomic is one of the strongest as of 2026-09.

**Risk**: nomic is optimized for English. Sources that contain German/Korean/Chinese text (Brian's journals often do) may embed with lower fidelity. Not fatal but a real quality tax.

### 2. Similarity metric — brute-force cosine at N=1200 (PROVEN)

**Choice**: `numpy` dot product on pre-normalized 768-dim vectors, symmetric N×N pair computation.

**Reference**: This is the standard IR baseline. FAISS's own docs describe Flat index (brute-force) as "perfect recall, scales poorly." The general threshold cited in vector-DB literature (SurrealDB blog, PyImageSearch FAISS guide, Yuma similarity-search post) is **~100,000 vectors** — below that, brute force is practical; above that, ANN (FAISS IVF, HNSW, IVFPQ) becomes necessary.

**Verdict**: PROVEN. At current N=1200, our brute-force computes 738,720 pair-cosines in ~50s on an M-series Mac. This scales linearly to about 10,000 vectors (~5-10 min) — well within acceptable batch cost. **Only becomes a problem past ~50,000 concepts.**

**Risk**: none at current scale. When vault approaches 10k concepts, transition to `sqlite-vec` or hnswlib. Not urgent.

### 3. Embedding proxy — title + first paragraph (EXPERIMENTAL-BUT-CONSTRAINED)

**Choice**: For each existing page, embed the string `<title>\n\n<first paragraph of body>`. This is the canonical representation cosined against fresh mentions.

**Reference**: No single system does exactly this.
- **BLINK** (Wu et al., EMNLP 2020) embeds full entity descriptions from Wikipedia — much longer than one paragraph.
- **Wikipedia dense retrieval** typically uses lead paragraph (first ~500 chars) as the mention-side.
- **mem0** (open-source memory system) embeds full memory summaries.
- **Nashsu's own dedup** embeds the concatenation of `## Overview + ## Notes` sections (~500-1500 chars per page).

Our title+first-paragraph is between Wikipedia's lead and mem0's summary. Not directly validated against any of these.

**Verdict**: EXPERIMENTAL. We picked a reasonable-looking proxy without benchmarking alternatives.

**Risk**: if the LLM-generated first paragraphs across our vault are stylistically homogeneous (same-shape topic sentences), they may all cluster near each other → false-positive rate high. Or if the first paragraph is too thin, we miss true synonyms whose distinguishing content lives in the body. **Symptom to watch for**: gate consistently returns cosine 0.75-0.85 across most mention-page pairs (indicates the proxy is compressing everything into a narrow band). Fix: swap to `## Overview + ## Notes` (nashsu's proven proxy) or add title-only as a second signal.

### 4. Threshold tiers — 0.95/0.85 cutoffs (EXPERIMENTAL)

**Choice**: cosine ≥ 0.95 → hard redirect (no LLM); 0.85 ≤ cosine < 0.95 → LLM adjudicates pairwise; cosine < 0.85 → pass through as novel.

**Reference**: Not calibrated against any labeled dataset. Two data points shaped the choice:
- Nashsu's `dedup-runner.ts` uses **0.68** prefilter threshold. Comment says "deliberately low to catch cross-language aliases." (D-067)
- Our own test 2026-09-11 (task #13, `test_write_time_gate.py` on 20 known-synonym-coining sources): 28.9% hit rate at 0.85 threshold, but **~30% of hits at 0.85-0.94 were false positives** (`enfj ↔ entj`, `hilton ↔ hyatt`, `extraverted-feeling ↔ extraverted-thinking`).

The 0.95 hard-gate + 0.85-0.95 adjudicate design is our attempt to keep the high-precision hits automatic and defer the boundary cases to the LLM. But the specific numbers are picked from the same empirical run, not validated across sources.

**Verdict**: EXPERIMENTAL. Directionally correct architecture (tiered thresholds are standard in blocking-then-matching, e.g., DeepBlocker → DITTO cascade) but the specific cutoffs are unverified.

**Risk**: too-low tier-1 → wrong-merges auto-applied (destructive). Too-high tier-1 → all real synonyms get punted to expensive LLM adjudication. Same for tier-2 boundary at 0.85 — real synonyms cluster at 0.846-0.884 per gate-integrator's report; a small shift can push a real synonym into silent Tier-3 passthrough.

**Fix priority (recommended)**: build a small labeled benchmark of 100 pairs (50 known-synonym, 50 known-distinct) drawn from the vault. Sweep threshold 0.75-0.98 in 0.02 steps, compute precision/recall at each. Pick the operating point where precision on tier-1 stays >0.95 and recall of tier-2-catchable pairs is >0.80. That's a ~30-min manual labeling task + auto sweep.

### 5. LLM adjudication — `claude -p` pairwise judge (EXPERIMENTAL-BUT-CONSTRAINED)

**Choice**: for each candidate pair with cosine in 0.85-0.95, send both page bodies to `claude -p --output-format json` with a MERGE/KEEP/HUB judge prompt (nashsu's `detectDuplicateGroups` structure).

**Reference**:
- Nashsu ships the exact prompt structure in `vendor/src/lib/dedup.ts`.
- LLM-as-judge for entity linking is an active research area — recent work (2024-2025) shows GPT-4-class models achieve F1 ≥ 0.85 on standard EL benchmarks (AIDA, ZESHEL) when given both mention context and candidate descriptions.
- R5 dedup verdicts on our own vault: 33 pairs judged, 0 PARSE_FAIL, 0 ERROR — verdict quality was manually verified as sensible.

**Verdict**: EXPERIMENTAL-BUT-CONSTRAINED. The method is proven in the literature (LLM-as-judge on entity pairs), and nashsu ships the same prompt shape. We're using it in the standard way. Constrained only by cost — each adjudication is a `claude -p` call at ~$0.05-0.10.

**Risk**: prompt drift — if the LLM output format changes between Sonnet versions, our JSON parser may break silently (already happened once when we saw German-language responses). Detectable via parse-fail counts; mitigated by our incremental verdicts JSON that persists progress.

### 6. Mention extraction — parsing SLUG DECISION lines (EXPERIMENTAL)

**Choice**: after stage-1 analysis returns, walk the freeform text for `### Name` or `**Name**` items in `## Key Entities` / `## Key Concepts` sections, extract the following `SLUG DECISION: GENUINELY NEW` marker as the closure signal, emit `ParsedSlugMention`.

**Reference**: **No reference implementation.** BLINK extracts mentions from NER models over source text. DITTO uses structured tabular inputs. Our design piggybacks on nashsu's own analysis prompt (which asks the LLM to self-mark GENUINELY NEW vs EXISTING slugs) and parses that structured markdown output.

**Verdict**: EXPERIMENTAL. This is the most creative part of the stack and the load-bearing one — if parsing misses mentions, the entire gate is inert.

**Risk**: **VERY HIGH**. Empirical evidence: on R1-v3 fresh ingest (2026-09-13), 46% of sources returned `passthrough=0`, meaning the parser found zero mentions. LLM output format varies across sources (bold headers vs H3 headers vs numbered lists; English vs auto-translated section names; SLUG DECISION as bare text vs `**SLUG DECISION**:` bold-wrapped). Each variant discovered required another regex patch.

**Mitigation options**:
1. **Force stricter LLM output** with `claude -p --json-schema` (D-062 — flagged for wiring but not yet complete). Would eliminate the parsing problem entirely.
2. **Language-agnostic + format-tolerant parser** — treat any H2/H3 header inside the analysis as a candidate mention header; match SLUG DECISION with more regex variants. Ongoing.
3. **Post-write dedup as fallback** — if the gate misses, the periodic dedup pass (D-057 lineage, currently implemented in `dedup_embed.py` + `apply_dedup.py`) catches it later. Already in place.

### 7. Retire-not-delete + xref rewrite (PROVEN)

**Choice**: When two pages merge, keep the loser as a stub with `retired_to: <winner>` frontmatter. Rewrite every inbound `[[loser-slug]]` link across the vault to `[[winner-slug]]` via nashsu's `rewriteCrossReferences`.

**Reference**: This is the **Wikipedia redirect model**, standard since 2001. Nashsu implements it natively in `vendor/src/lib/dedup.ts` (`rewriteCrossReferences` at line 456, `rewriteIndexMd` at line 534). We verified end-to-end Sep 3 (7 retire stubs, 80 broken inbound links fixed) and Sep 11 (15 retire stubs, 142 links fixed).

**Verdict**: PROVEN. Nothing about this layer is creative; we're using nashsu's native functions.

---

## Where we're being creative — explicit list

For the branch record, the parts of MIKAI's semantic matching stack that are NOT off-the-shelf and depend on our judgment:

1. **Embedding proxy shape** (title + first paragraph) — bet that this compression retains enough signal for synonym detection.
2. **Threshold tier cutoffs** (0.95 / 0.85) — picked from one empirical measurement, not calibrated against a labeled set.
3. **Mention extraction from freeform LLM markdown** — our wiring, not BLINK's or DITTO's mechanism.
4. **Piggy-backing on nashsu's stage-1 SLUG DECISION** — a design choice that saves an entire NER pass but couples us to nashsu's output format.

Everything else is either proven library work (embedding, cosine, LLM-judge prompt) or platform-forced (subscription-auth constraint on embedder + LLM choice).

---

## Sources

- Nomic Embed technical report: [arXiv:2402.01613](https://arxiv.org/pdf/2402.01613)
- MTEB benchmark: [arXiv:2210.07316](https://arxiv.org/pdf/2210.07316)
- BLINK repository + paper: [facebookresearch/BLINK](https://github.com/facebookresearch/BLINK), [Scalable Zero-shot Entity Linking with Dense Entity Retrieval (EMNLP 2020)](https://aclanthology.org/2020.emnlp-main.519/)
- FAISS Flat vs ANN threshold guidance: [Luminis: Similarity Search with FAISS](https://www.luminis.eu/blog/decoding-similarity-search-with-faiss-a-practical-approach/), [PyImageSearch: Vector Search with FAISS](https://pyimagesearch.com/2026/02/16/vector-search-with-faiss-approximate-nearest-neighbor-ann-explained/)
- Nashsu dedup module: `infra/nashsu/vendor/src/lib/dedup.ts`, `dedup_embedding.ts`, `dedup-runner.ts` (see D-067)
- Prior MIKAI decisions: ARCH-033, ARCH-034, D-057, D-063, D-067, D-068
