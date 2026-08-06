# Dream Bootstrap

`infra/graphiti/dream_bootstrap.py` is the one-shot replacement for the frozen
`dream.py` (which read Graphiti/Neo4j). It reads the Karpathy wiki directly —
`~/.mikai/wiki/wiki.md` (27MB, 8,049 sections spanning 2013 → 2026) via the
byte-offset `wiki.index` — and produces the two derived files the future
nightly/weekly dream jobs will keep fresh incrementally:

- **`wiki-narrative.md`** (Pass A) — first-person recent-activity summary.
  Windowed read over the last N days (default 30), chunked by month and split
  under ~150K chars per chunk, one `mikai_llm.chat(tier="interactive")` call
  per chunk (~5-6 calls for 30 days).
- **`wiki-ontology.md`** (Pass B) — canonical entity list over the FULL
  corpus. Map-reduce: sections are ordered by source stream, batched
  (≤300 sections / ≤150K chars), each batch mapped to a JSON entity list
  ({name, type, mentions, sources, confidence} per `docs/ENTITY_MODEL.md` —
  person/org/thing/place only, kebab-case, singular, first-name people), then
  reduced by merging on name: mentions summed, sources unioned, confidence
  averaged, type taken from the max-confidence occurrence. Entities with avg
  confidence < 0.5, or seen in one batch with < 3 mentions, are dropped.
  Entities whose name never appears verbatim in wiki.md are kept but flagged
  ⚠ as possibly inferred.

**Scale trick:** the raw corpus is 27MB, so naive 150KB batching would cost
~190 LLM calls. Both passes instead *excerpt* each section — header line plus
the first ~500 bytes of body — sized so a batch fits the char budget. Entity
names and thread signals concentrate in headers and openings, so this keeps
the whole bootstrap at ~37 calls. Guards: 1 call / 2s rate limit, `--max-calls`
hard cap (default 50), per-call try/except (a failed batch logs and the pass
continues), per-batch JSONL checkpoint (`--resume` skips completed batches),
`--dry-run` prints call estimates without calling or writing. Prior outputs
are backed up as `<file>.bak-bootstrap-<ts>`. The hand-curated
`wiki-ontology-v1.md` is never touched.

**What nightly/weekly should do differently:** this script regenerates from
scratch. `dream_nightly` should rebuild only the narrative, windowed to the
last few days plus the previous narrative as prior context (1-2 calls).
`dream_weekly` should *diff* rather than rebuild the ontology: extract
entities only from sections newer than the last run's high-water mark
(store `header_ts` watermark next to the checkpoint), merge into the existing
table, and decay entities not seen in N weeks — never re-scan 8K sections.
Both should reuse the excerpt/batch/merge helpers here rather than reinvent.
