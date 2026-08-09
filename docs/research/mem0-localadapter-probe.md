# mem0 as an `L3Backend` candidate — probe findings

**Date:** 2026-07-30
**Probed:** `github.com/mem0ai/mem0` @ `760dca6` (2026-07-30), shallow clone (depth 50) at `~/.mikai/probes/mem0`
**License:** Apache-2.0 (Graphiti is MIT — both permissive, no blocker)
**Question:** Can mem0 be adopted under the `L3Backend` port (ARCH-024 / D-050) as an alternative to building `LocalAdapter` from scratch, in the same way Cognee and Mnemosyne are being considered?

**Verdict: No. Reject as an adapter candidate.** Not because of quality — because mem0 is no longer a graph, and the port is a graph port.

---

## The disqualifying finding

**mem0 v3 removed graph-store support from the open-source package entirely.**

From `docs/migration/oss-v2-to-v3.mdx` in the repo:

| Change | Old | New | Migration |
|---|---|---|---|
| Graph memory | `enable_graph` + `graph_store` in config | Removed | Graph store support has been removed entirely |
| Default graph config | Neo4j default config applied | No default graph config | Graph store config is no longer used |

Corroborated in the code, not just the docs:

- No `mem0/graphs/` module. No `graph_memory.py`.
- `grep -n -i "graph" mem0/memory/main.py` → **zero hits** across 3,787 lines.
- `pyproject.toml` has no graph extra and no Neo4j / Memgraph / Kùzu dependency.
- Checked-out code is confirmed v3-state (`mem0/configs/base.py:54` carries `custom_instructions`, the v3 rename of `custom_fact_extraction_prompt`).

Graph memory still exists in mem0's **hosted platform** (`docs/platform/features/graph-memory.mdx`), behind their API. That is not adoptable under the port — it is a managed cloud service, which contradicts both the LocalAdapter goal (ARCH-025, on-device) and the port's "no infrastructure nouns" rule.

### How mem0 frames it, and why the framing is misleading for our purposes

Fairness requires quoting their own words. From `docs/changelog/sdk.mdx` (PR #4805):

> **External Graph Store Removed (OSS):** `mem0/memory/graph_memory.py`, `memgraph_memory.py`, `kuzu_memory.py`, `apache_age_memory.py`, and `mem0/graphs/` (Neo4j / Memgraph / Kuzu / Apache AGE / Neptune drivers) deleted, **about 4,000 lines**. […] **Graph memory now runs natively as built-in entity linking.**

So mem0 does not describe this as "we dropped graphs" — they describe entity linking as the *successor* to the graph store. That claim does not survive contact with the schema: entity linking stores `linked_memory_ids[]` per entity and no entity→entity relation of any kind (see below). It is a co-occurrence index for retrieval boosting, not a graph. The capability was replaced with something cheaper that serves their retrieval benchmark, not with a lighter graph.

### The stated rationale — it was a benchmark-driven trade

From `docs/migration/oss-v2-to-v3.mdx`, the v3 redesign was:

- **Extraction:** single-pass **ADD-only** — one LLM call, no UPDATE/DELETE pass
- **Retrieval:** multi-signal hybrid — semantic + BM25 keyword + entity matching
- **Result:** **LoCoMo 71.4 → 91.6 (+20)** and **LongMemEval 67.8 → 93.4 (+26)**, with **extraction latency roughly halved**

Both benchmarks are conversational-recall QA over long dialogue histories. They reward *"given a question, retrieve the right fact stated somewhere in the chat log."* On that task a graph is largely overhead — you pay entity resolution and edge extraction per episode to answer questions that similarity + keyword + entity boost already answer. mem0 measured that, and cut the graph.

This is a legitimate result for their market and should not be read as a refutation of the graph approach in general. It is a statement about *which* job needs edges. See "Why this matters beyond the scorecard" below.

## What mem0 OSS actually is now

A **flat fact store over a vector index**, plus a second vector collection used for search boosting:

1. **Memories** — LLM-distilled fact *strings* in a vector store (Qdrant default; ~25 backends supported). Scoped by `user_id` / `agent_id` / `run_id` filters. `search()` returns ranked strings, not triples.
2. **Entity store** (`main.py:534-704`) — a *second vector collection* in the same backend. Each row is `{data, entity_type, linked_memory_ids[], user_id}`. Entities are extracted with **spaCy NER** (`mem0/utils/entity_extraction.py`, 772 lines — NER labels + proper-noun / quoted / topic-phrase / identifier heuristics), not by an LLM.

   The critical detail: **entities link only to memory IDs, never to each other.** There is no `(source_entity, relation, target_entity)` record anywhere in the schema. The entity store exists to compute relevance boosts (`_compute_entity_boosts`, `main.py:1703`), not to be traversed.
3. **History** (`mem0/memory/storage.py:102`) — a SQLite audit table: `(id, memory_id, old_memory, new_memory, event, created_at, updated_at, is_deleted, actor_id, role)`. This is a per-memory changelog, not bitemporal validity.

## Port fit — the 11 primitives

Scored against `infra/graphiti/sidecar/l3/port.py`.

| Primitive | mem0 OSS v3 | Fit |
|---|---|---|
| `ingest_episode` | `Memory.add()` → LLM distillation → fact strings | ⚠️ Partial — `IngestResult.edges_extracted` has nothing to report |
| `ingest_episode_bulk` | No native batch; port's default loop works | ⚠️ Partial — loses shared-context extraction |
| `search` → `list[Edge]` | Returns fact strings; no `source_uuid` / `target_uuid` / `fact` triple | ❌ **Fails** — nothing to build an `Edge` from |
| `search_nodes` → `list[Node]` | Entity-store vector search | ✅ Closest clean fit |
| `get_node(uuid)` | Entity fetch by vector id | ✅ Works |
| `expand(uuid)` → `Subgraph` | Reachable only as entity → `linked_memory_ids` → memories → co-occurring entities. Co-occurrence, not a hop. `Subgraph.edges` would always be `[]` | ❌ **Fails** |
| `edges_between(node_uuids)` | No edges exist | ❌ **Fails** |
| `history(query, as_of)` → current/superseded | Keyed by `memory_id`, not a query; no `as_of`; no `valid_at` / `invalid_at` / `expired_at` | ❌ **Fails** |
| `get_source` | mem0 stores *distilled* facts, not raw episode prose; a `messages` table exists but isn't a search surface | ⚠️ Partial |
| `stats` | Countable from the vector store | ✅ Works |
| `communities` | No community detection | ❌ **Fails** |
| `close` | `Memory.close()` exists | ✅ Works |

**4 clean / 3 partial / 5 hard fails.** The failures are not gaps to fill — they are all the same missing thing: edges.

## Why this matters beyond the scorecard

D-041 fixes the port as *graph primitives only*, with L4 built on top. MIKAI's L4 thesis depends on edge semantics the port already types for: `CONTRADICTS`, `UNRESOLVED_TENSION`, `DEPENDS_ON`, plus bitemporal invalidation (`valid_at` / `invalid_at` / `expired_at`) to detect the exploring → decided → acting → stalled transitions. mem0 v3 has no representation for any of it. An adapter would have to *synthesize* a graph on top of a vector store — which is building `LocalAdapter` from scratch, with mem0 as dead weight in the middle.

Second-order note: `docs/research/l3-extraction-survey.md` credits mem0's ADD/UPDATE/DELETE/NOOP resolver as prior art we deliberately declined to copy. In v3 that's moot — the migration doc records `add()` events narrowing to **`ADD` only**. The thing we studied mem0 for no longer exists in it either.

## What's still worth taking

Nothing new. The one borrowing already landed: negative-example few-shot augmentation in the extraction prompt (`extraction/prompt_negatives.py`, per `l3-extraction-survey.md`). mem0's spaCy-NER entity layer is *cheaper* than LLM extraction and could inform a fast pre-filter, but it produces untyped mention strings — strictly weaker than Stage 6's source-conditional Pydantic schemas.

## Consequences

- **O-037** ("when should the memory layer be replaced with open source?") — mem0 is now removable from the candidate set. Candidates remaining: **Cognee** and **Mnemosyne**, both of which retain real graph layers. Mnemosyne in particular (SQLite + `sqlite-vec`, temporal KG with time-aware fact invalidation) is the structural match mem0 turned out not to be.
- **ARCH-025 / LocalAdapter** — unaffected. Still deferred pending its three triggers.
- Recommend the next probe be **Mnemosyne**, since it's the only candidate whose bitemporal model maps onto `history()` / `edges_between()` without invention.

## Caveats on this probe

- Clone is `--depth 50`, so `git log` cannot date the graph-store removal or show the deleted files. The *current-state* findings above are all verified directly against the checked-out tree; the removal timeline is taken from mem0's own migration doc.
- `pyproject.toml` still reads `version = "2.0.14"` while the tree carries v3 code and v3 migration docs. The repo appears mid-release; this doesn't change any finding (the graph module is absent either way) but means "v3" here refers to the documented change set, not a published tag.
- This is a static read of the source. No mem0 instance was installed or run — unnecessary, since the disqualifying finding is structural absence, not behavior.
