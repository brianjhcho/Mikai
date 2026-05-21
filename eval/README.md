# eval/ — Stage-6 L3 typed-extraction eval harness

Precision/recall eval for Graphiti's typed entity and edge extraction.
Measures against a hand-labeled gold set (Brian's labels); does **not** replace
the intrinsic node-quality harness in `scripts/eval_mikai.py` (those measure
1–5 answer quality; this measures extraction precision/recall).

## Run sequence

```
# 1. Seed candidates from the live graph (requires Neo4j running)
python eval/seed_candidates.py

# 2. Label candidates (Brian only — keyboard-first CLI, y/n/s/q)
python eval/label.py

# 3. Run the eval (offline — no sidecar needed unless --latency)
python eval/run_l3_eval.py

# Optional: include latency probes (requires sidecar at localhost:8100)
python eval/run_l3_eval.py --latency
```

Scorecard is written to `docs/evals/stage6-YYYY-MM-DD.md`.
Exit code 0 = all metrics pass; 1 = one or more blocking metrics fail.

## Files

| File | Purpose |
|---|---|
| `schemas.py` | Pydantic models for JSONL records (`EntityCandidate`, `EdgeCandidate`) |
| `seed_candidates.py` | Stratified sampler — queries Neo4j, writes JSONL with `is_valid=null` |
| `label.py` | Keyboard-first labeling CLI (y/n/s/q, resumable) |
| `run_l3_eval.py` | Metric computation + scorecard writer |
| `labeled_entities.jsonl` | 200 entity candidates (seeded + labeled; gitignored until labeled) |
| `labeled_edges.jsonl` | 200 edge candidates (seeded + labeled; gitignored until labeled) |

## Acceptance criteria

From `docs/STAGE-6-TYPED-EXTRACTION-BRIEF.md`:

| Metric | Threshold |
|---|---|
| entity_precision | ≥ 0.85 |
| entity_recall | ≥ 0.75 |
| edge_precision | ≥ 0.80 |
| edge_recall | ≥ 0.65 |
| noise_rate | ≤ 0.10 |
| ingestion_latency_p95_ms | ≤ 8000 |
| query_latency_p95_ms | ≤ 500 |

## Labeling guide

The labeling CLI shows the entity/edge and its **source excerpt** prominently.

For **entities**:
- `y` if the entity type is appropriate and the name/summary is accurate.
- `n` if it is mis-typed, garbage, or hallucinated.

For **edges**:
- `y` if the relationship type fits the semantic connection and the fact is accurate.
- `n` if the edge type is wrong or the fact is garbled.

Use `s` to skip anything uncertain; run `python eval/label.py` again to come back.
Sessions are resumable — quitting mid-session never loses labeled records.

## Env vars for seeding

```
NEO4J_URI      bolt://localhost:7687
NEO4J_USER     neo4j
NEO4J_PASSWORD <password>
```

Place in `.env` at repo root or export before running `seed_candidates.py`.

## Tests

```
cd infra/graphiti && .venv/bin/python -m pytest tests/test_eval_harness.py -v
```
