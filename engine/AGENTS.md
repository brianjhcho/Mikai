<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-27 | Updated: 2026-03-27 -->

# engine

## Purpose
Core processing pipeline — from raw content to actionable thread intelligence. Contains the graph builder (L3), rule engine (L3), and the full L4 task-state awareness stack.

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `graph/` | L3 knowledge graph construction — Track A (Claude), Track B (rules), Track C (segments) |
| `inference/` | L3 stall probability scoring via rule engine |
| `ingestion/` | Content preprocessing and direct ingestion |
| `l3/` | **L3 Graphiti-inspired upgrades** — bitemporal edges, BM25 fulltext, hybrid search with RRF (see `l3/AGENTS.md`) |
| `l4/` | **L4 task-state awareness** — thread detection, state classification, next-step inference (see `l4/AGENTS.md`) |
| `scheduler/` | macOS launchd integration for automated 30-min sync |
| `eval/` | Evaluation and test suites |

## For AI Agents

### Working In This Directory
- Engine scripts are standalone CLI entrypoints — each loads its own env
- L3 pipeline: `build-graph.js` → `build-segments.js` → `run-rule-engine.js`
- L4 pipeline: `l4/run-l4-pipeline.ts` (detect → classify → infer)
- Graph scripts use `.js` extension (plain JS), L4 uses `.ts` (TypeScript)

### Testing Requirements
- `npm run eval` for node quality evaluation
- `npm run eval:stall` for stall detection accuracy
- `npm run test` for full test suite
