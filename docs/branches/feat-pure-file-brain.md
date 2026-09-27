# Branch manifest — `feat/pure-file-brain`

> **Purpose of this file:** every session on this branch reads this manifest FIRST. It names the branch's constitution, current phase, load-bearing decisions, and the do-not list scoped to this branch. Before making architectural changes on this branch, verify the change is consistent with the constitution below.

## Constitution

**`docs/CONSOLIDATION_ARCHITECTURE.md`** is the load-bearing doc. §5a specifies the Wikipedia-redirect canonicalization pipeline (alias-table → embedding kNN → LLM merge adjudication). §5b specifies the deterministic salience score S(c, t). §6 specifies Path 2 (exemplar-driven weight fitting).

Karpathy's crystallization principle (from Karpathy's llm-wiki README, adopted as `ARCH-035`): the wiki should crystallize into a small number of very dense, canonical pages that everything references. Compression is not the KPI; density × coverage × partition-correctness is.

## Branch goal

Replace MIKAI's L3 substrate from Neo4j/Graphiti to a Karpathy-style file-based wiki (`~/.mikai/wiki/`), driven by nashsu's ingest pipeline with MIKAI-specific extensions (canonicalization hook, alias frontmatter, comprehensive index sections, SLUG DISCIPLINE, semantic top-K neighbors). Test the architecture with a substantive corpus BEFORE adding new mechanisms.

## Current phase (2026-09-22)

- **Ingest stack**: nashsu vendored (v0.6.9) + parallel workers=6 + `pre_extract_topk.py` (semantic top-40 with aliases) + SLUG DISCIPLINE prompt + canonicalization hook (post-write). Working.
- **Consolidation completeness (6 criteria, measured on test vault `~/.mikai/wiki-mikai-parallel-test`):**
  - Partition correctness: ~90% (canonicalization catches 12% of proposed pages)
  - Coverage — MIKAI subject: 41% (was 31% pre-CANON-6 docs-as-sources ingest)
  - Density — words median: 630 (was 460)
  - Density — sources median: 2
  - Referential integrity: 72.46% (was 51.78% baseline before CANON-8 wrap-bare-mentions)
  - Orphan rate: untested
- **Retrieval interface**: `mikai-wiki-v1` MCP server built and tsc-clean at `infra/mikai-mcp/`. Headless (no Desktop dependency). Awaiting Claude Code config activation.
- **Parked mechanisms** (built but NOT applied — awaiting corpus-testing to justify): CANON-5 accretion (density enrichment via LLM). 

## Load-bearing decisions on this branch

Read the full text in `docs/DECISIONS.md`. Currently load-bearing:

| ID | What was decided |
|---|---|
| ARCH-032 | Vendored nashsu supersedes smoke_ingest_v2 |
| ARCH-033 | Semantic ≠ synonym matching; mention-level required |
| ARCH-034 | Two-tier write-time semantic gate (superseded by ARCH-036 canonicalization for page-level; O-050 for mention-level) |
| ARCH-035 | Karpathy crystallization principle + periodic dream pass |
| ARCH-036 | Canonicalization pipeline — Wikipedia-redirect model at ingest time |
| D-063 | Mechanism B (pre-extract semantic top-K) proven inert without link-at-birth |
| D-064 | enrichWithWikilinks removed (per Fable audit) — REPLACEMENT CLAIM DISPROVEN 2026-09-17 by CANON-7 measurement; CANON-8 deterministic wrapping is the correct replacement |
| D-065 | Ablation flags on CLI for factorial testing |
| D-066 | claude -p exit-1 root cause = 5-hour subscription cap, not concurrency |
| D-067 | Nashsu-native dedup wrapper landed |
| D-068 | Post-ingest dedup downgraded (canonicalization is the primary mechanism) |

## Do not (branch-scoped)

- **Do not diverge from the stated nashsu/karpathy architecture without measurement.** New mechanisms need a measured gap justification against the six consolidation criteria. Adding LLM calls needs a specific quality problem CANON-8-style deterministic fixes can't solve.
- **Do not write to production vault** (`~/.mikai/wiki/`). Everything runs against `~/.mikai/wiki-mikai-parallel-test` until an explicit production migration decision.
- **Do not commit to git without approval.** Especially: no force-pushes, no rewriting history.
- **Do not build new mechanisms on top of what's parked.** CANON-5 (accretion) and any similar density-enrichment work waits until corpus-testing measurement demands it.
- **Do not confuse "close to karpathy/nashsu" with "no MIKAI additions."** The constitution (§5a canonicalization + §5b salience) IS MIKAI-specific — it's the branch's stated architecture, not divergence.

## Active files (2026-09-22)

- `infra/nashsu/bridge/canonicalize.py` — three-tier resolution hook (built, live in ingest pipeline)
- `infra/nashsu/bridge/canonicalize_undo.py` — reversibility tool
- `infra/nashsu/bridge/wrap_bare_mentions.py` — CANON-8 deterministic wrap (applied)
- `infra/nashsu/bridge/accrete.py` — CANON-5 accretion mechanism (PARKED, do not apply without measurement)
- `infra/nashsu/bridge/build_aliases.py` — one-shot alias bootstrap
- `infra/nashsu/bridge/pre_extract_topk.py` — semantic top-K with aliases (live)
- `infra/nashsu/cli/ingest.ts` — CLI wrapper with canonicalization hook (live)
- `infra/mikai-mcp/**` — headless MCP server v1 (built, awaiting activation)

## Session workflow

1. **Read this manifest.**
2. Read the constitution: `docs/CONSOLIDATION_ARCHITECTURE.md`.
3. Read the current status: `docs/DECISIONS.md` (latest ARCH-036 + D-063 onward for branch-relevant).
4. Consult auto-memory: `[[pure-file-brain-constitution]]`, `[[pure-file-brain-test-before-diverge]]`.
5. Only then make architectural decisions.

## Related architecture docs

- `docs/CONSOLIDATION_ARCHITECTURE.md` — CONSTITUTION (§5a canonicalization, §5b salience, §6 Path 2)
- `docs/DREAM_PASS.md` — periodic dream pass design (Louvain + LLM adjudication)
- `docs/DREAM_RESEARCH_COMPARISON.md` — MIKAI dream approach vs Anthropic Managed Agents dreaming, GraphRAG, HippoRAG, RAPTOR, MemGPT, Mem0
- `docs/SEMANTIC_MATCHING_AUDIT.md` — proven vs experimental methods, layer-by-layer
- `docs/SEMANTIC_CLUSTERING_GAP.md` — the gap the consolidation architecture is closing
- `docs/INGESTION_PIPELINE_ANALYSIS_2026-08-14.md` — Fable's P1-P5 diagnostic frame
- `docs/ENTITY_MODEL.md` — file-first entities design
- `docs/MEMORY_ARCHITECTURE.md` — memory architecture deep-dive
- `docs/GLOSSARY.md` — named-concepts registry

## Related auto-memory

- `[[pure-file-brain-constitution]]` — the constitution as memory (McClelland 1995 grounding)
- `[[pure-file-brain-test-before-diverge]]` — 2026-09-17 directive: no new mechanisms until corpus-testing justifies
- `[[ingest-pipeline-2026-08-14]]` — Fable P1-P5 diagnostic + MAX_EXCERPT=4000 oversight
- `[[entity-model-2026-08]]` — file-first entities
- `[[mikai-consumer-product-bet]]` — 2026-07-17: consumer-product bet, moat = packaging + Sumimasen + declarative ontology
