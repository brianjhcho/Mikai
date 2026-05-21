# Stage 6 — L3 typed extraction (build brief)

> **Source:** Brian's session brief (2026-05-21), refined against research on
> Mem0 / Cognee / Letta / Honcho extraction architectures (see
> `docs/research/l3-extraction-survey.md`, to be written as part of this stage).
>
> **Branch:** `feat/stage-6-typed-extraction`. **Decision record:** D-049
> (to be written as the first artifact of this stage).
>
> **ARCH note:** The brief's reference to "ARCH-021 = no dual-backend
> abstraction" is stale — ARCH-021 was superseded by ARCH-024 (L3Backend
> port) and ARCH-025 (LocalAdapter as first-class alternate). Read the
> "no dual-backend abstraction" line as: **inside the Graphiti adapter**,
> there is exactly one L3 implementation. The port pattern across adapters
> stands.

## Goal

Improve L3 extraction quality from **3.10/5 → ≥4.3/5** and produce a
machine-readable typed graph that L4 can query directly — using Graphiti's
native typed-extraction API (`entity_types`, `edge_types`, `edge_type_map`).
No second LLM pass. No projection layer.

## Constraints

- Graphiti sidecar at `http://localhost:8100` is the L3 backend targeted by
  this work (ARCH-019, current default per ARCH-024).
- Typing happens at extraction time via `add_episode()` parameters only.
- No second post-extraction LLM pass; no separate "projection layer";
  no Mem0-style ADD/UPDATE/DELETE/NOOP gate. Graphiti's entity resolution +
  bitemporal invalidation are the manufacturer-supported equivalent.
- No new vector store, embedding service, or auxiliary backend.

## Build scope

1. **Source-conditional Pydantic entity types** under `infra/graphiti/sidecar/extraction/`:
   - `claude_thread.py`, `apple_note.py`, `gmail_message.py`, `whatsapp_day.py`
   - Each defines 5–15 entity types covering that source's domain.
2. **Shared epistemic edge types** — `extraction/epistemic_edges.py`:
   - `CONTRADICTS`, `SUPPORTS`, `DEPENDS_ON`, `PARTIALLY_ANSWERS`,
     `UNRESOLVED_TENSION`, `EXTENDS`
   - Every edge type carries `confidence: float`.
3. **Shared `edge_type_map`** declaring which edge types may connect which entity
   types (e.g. `Question → PARTIALLY_ANSWERS → Decision`).
4. **Negative few-shot examples** added to the extraction prompt path. Negatives
   sourced from the existing noise cluster: `"Hearty simple creative"`, `"folly"`,
   `"The MacNabs"`, `"2327 storage number"`, etc.
5. **Query-time recency-decay scoring overlay** — a single function applied at
   search time, not a service. Time-decays edge scores so freshly-`valid_at`
   facts outrank stale ones.
6. **Eval suite** — `eval/labeled_entities.jsonl` (200) + `eval/labeled_edges.jsonl`
   (200) + `eval/run_l3_eval.py` runner. Candidates seeded by the team from the
   current graph; **Brian labels the gold set** (work cannot be agentified).
7. **D-049 decision record** capturing the no-second-pass / source-conditional
   schema decision against the rejected alternatives (Mem0 gate, Cognee ontology).

## Acceptance criteria (executable)

```json
{
  "layer": "L3",
  "capability": "typed_extraction",
  "acceptance_criteria": {
    "entity_precision":  { "threshold": 0.85, "eval_set": "eval/labeled_entities.jsonl" },
    "entity_recall":     { "threshold": 0.75, "eval_set": "eval/labeled_entities.jsonl" },
    "edge_precision":    { "threshold": 0.80, "eval_set": "eval/labeled_edges.jsonl" },
    "edge_recall":       { "threshold": 0.65, "eval_set": "eval/labeled_edges.jsonl" },
    "noise_rate":        { "max": 0.10, "definition": "extracted entities that fail Pydantic validation OR are filtered post-hoc as garbage" },
    "ingestion_latency_p95_ms": { "max": 8000, "per": "episode" },
    "query_latency_p95_ms":     { "max": 500,  "per": "search" }
  },
  "eval_command": "python eval/run_l3_eval.py",
  "blocking": true
}
```

## Anti-patterns (do not do)

- **No** second post-extraction LLM gate (Graphiti's resolution + bitemporal
  invalidation already cover this).
- **No** projection layer that re-classifies freeform edges — constrain edges
  at extraction time via `edge_types`.
- **No** Cognee OWL ontology validator — Pydantic + `edge_type_map` is the
  manufacturer-supported equivalent.
- **No** new vector store or embedding service — Graphiti's existing retrieval
  is the search layer.
- **No** dual L3 backends "for safety" within this work.
- **Do not** describe the system as "local-first" (per CLAUDE.md constitution).

## Done definition

- Eval suite passes all blocking thresholds.
- Kenya-coffee benchmark trace: a Claude thread → Apple Note → Gmail →
  WhatsApp daily summary all land typed entities and typed edges in Graphiti,
  connected through shared Person/Place/Project nodes, with confidence on
  epistemic edges.
- L4 can query: `edges where type=UNRESOLVED_TENSION and confidence>0.6 and
  connected to any Project node` — and get a usable result set with no
  additional projection step.

## Work streams (parallelizable)

| Stream | Owner | Deps |
|---|---|---|
| A. Pydantic `entity_types` per source (4 files) | agent | — |
| B. `epistemic_edges.py` + `edge_type_map` | agent | — |
| C. Wire into `add_episode()` call sites (sync.py, mcp_tools.py, main.py) | agent | A, B |
| D. Negative-example prompt augmentation | agent | — |
| E. Query-time recency-decay scoring overlay | agent | — |
| F. Eval harness (`eval/run_l3_eval.py`) + JSONL format + candidate seeder | agent | A, B (schemas drive the format) |
| G. Kenya-coffee benchmark trace test | agent | C |
| H. D-049 decision record + research survey doc | agent | — |
| **L. Hand-label the 200+200 eval set** | **Brian** | F (needs the labeling tool) |
