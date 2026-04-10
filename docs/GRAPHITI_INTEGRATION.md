# Graphiti Integration — Architecture Insights & Scaling Lessons

**Last updated:** 2026-04-08

---

## Overview

MIKAI uses Graphiti (open source, by Zep) as its L3 knowledge graph backend. Graphiti runs on Neo4j with DeepSeek V3 for entity extraction/resolution and Voyage AI for embeddings.

**Current graph state (2026-04-08):**
- 1,158 episodes (1,102 Apple Notes complete, 87 Claude thread turns partial)
- 6,990 entities
- 8,056 edges
- 1,233 orphan entities (17.6%, no edges)

---

## Graphiti's Entity Resolution Pipeline

When a new episode is imported via `add_episode()`, Graphiti runs a 4-step resolution pipeline:

### Step 1: Entity Extraction (LLM)
DeepSeek extracts entity mentions from the episode text. A typical note produces 5-15 entities.

### Step 2: Candidate Collection (Hybrid Search)
For EACH extracted entity, Graphiti runs a hybrid search (vector kNN + BM25 fulltext) against the existing graph to find potential duplicates. Returns top 10 candidates per entity.

```
N extracted entities × 10 candidates each = up to N×10 candidate nodes
After deduplication of overlapping candidates: 50-400 unique candidates
```

### Step 3: Deterministic Resolution (No LLM, FREE)

**Tier 1 — Exact string match:** Normalizes names and matches exactly. "MIKAI" == "MIKAI". O(1) per entity.

**Tier 2 — Fuzzy match (LSH/MinHash):** Creates character n-gram shingles and matches by similarity. "Mika" ≈ "MIKAI". O(1) per entity.

In a mature graph, Tier 1/2 resolves 70-90% of entities without any LLM call.

### Step 4: LLM Disambiguation ($$, only for unresolved)

Remaining unresolved entities are sent to the LLM with the candidate list. The LLM decides if "coffee ERP system" is the same entity as "Coffee ERP".

---

## Scaling Issue: Context Window Overflow at ~4,500+ Entities

### What happened

At batch 52 of the Apple Notes import (4,681 entities in graph), the LLM resolution prompt exceeded DeepSeek's 131K context window — requesting 2.3M+ tokens.

### Root cause (in Graphiti's `_resolve_with_llm`, `node_operations.py` line 299-308)

```python
existing_nodes_context = [
    {
        **{"name": candidate.name, "entity_types": candidate.labels},
        **candidate.attributes,    # ← THE PROBLEM
    }
    for candidate in indexes.existing_nodes   # ← ALL candidates, not filtered
]
```

**Two problems compound:**

**Problem 1:** `indexes.existing_nodes` contains ALL candidates collected in Step 2 — not just candidates relevant to the unresolved entities from Step 4. Entities already resolved in Step 3 still have their candidates in the list.

**Problem 2:** `**candidate.attributes` spreads all accumulated data into the prompt. After 800+ episodes, entity summaries grow large. An entity like "MIKAI" mentioned in 50+ notes accumulates ~2,000 tokens of summary.

**The math:**
- Small graph (batch 1-20): 80 candidates × 100 tokens = 8K tokens → fits
- Large graph (batch 52+): 80 candidates × 40,000 tokens average = 3.2M tokens → overflow

### Why Graphiti doesn't catch this

Graphiti was designed for incremental chat ingestion where:
- Each message adds 2-3 entities (not 10-15 from rich notes)
- Candidate search returns 20-30 total (not 200-400)
- Attributes are small (graph is young)
- Prompt stays under 10K tokens

Bulk import of rich content at scale is an undocumented edge case.

### The patch (applied to venv site-packages)

```python
# MIKAI patch in node_operations.py line 299
capped_candidates = indexes.existing_nodes[:50]  # cap candidates
existing_nodes_context = [
    {'name': candidate.name, 'entity_types': candidate.labels}  # strip attributes
    for candidate in capped_candidates
]
```

Two changes:
1. **Cap at 50 candidates** (was unbounded)
2. **Strip attributes** — LLM only needs name + labels for dedup, not full summaries

Prompt size: 50 × ~20 tokens = 1,000 tokens. Fixed permanently regardless of graph size.

**Quality tradeoff:** Minimal. LLM disambiguates by name similarity, not by reading summaries.

---

## How Resolution Costs Scale

### Graphiti's intended use: cost DECREASES over time

```
Cost per episode
    ↑
$0.04 ┤  ●●
      │    ●●
$0.02 ┤      ●●●
      │         ●●●●●
$0.01 ┤              ●●●●●●●●●●●●●●●●●●●●
      │                                    ●●●●●●●
$0.005┤                                            ●●●●●●●●●●●
      └─────────────────────────────────────────────────────────→
      Episode 1                  Episode 500              Episode 900
      (all new)                (70% known)            (90% known)
```

As the graph matures, the same entities recur. Tier 1/2 resolves them for free. LLM is only called for genuinely new, ambiguous entities.

### Graphiti's design vs bulk import

| Graphiti's design | Bulk import of years of notes |
|---|---|
| 1 message at a time, same domain | 900 notes across years, diverse topics |
| Same entities keep recurring | Every note introduces many new entities |
| Graph reaches steady state quickly | Graph never reaches steady state during import |
| Tier 1/2 resolves 90%+ | Tier 1/2 resolves maybe 30% (everything is new) |
| ~2 LLM calls per episode (mature graph) | ~15 LLM calls per episode (constant novelty) |

### Chronological import = natural maturation

Importing notes oldest-first simulates natural use:
1. 2014 notes: "Brian", "writing", "philosophy" → all NEW, but graph is small → cheap
2. 2016 notes: "Brian" (Tier 1 match, FREE), "business ideas" (NEW) → cheaper
3. 2020 notes: Most personal entities exist → Tier 1/2 handles 70% → cheap
4. 2025 notes: 90% of entities in graph → mostly FREE resolution → very cheap

### Post-import steady state

After the full import, ongoing daily use is cheap:
- ~10 new episodes/day (new notes, conversations)
- 90%+ entities already in graph → Tier 1/2
- ~$0.005 per episode → $0.05/day → $1.50/month

---

## Entity Resolution: What It Catches and What It Misses

### How candidates are found

Hybrid search (vector + BM25) over entity `name` AND `summary`:

| Entity in graph | Name match? | Summary contains query? | Found as candidate? |
|---|---|---|---|
| "MIKAI" | Yes (vector + BM25) | Yes | **Yes** |
| "MIKA AI" | Yes | Yes | **Yes** |
| "MIKA/REMY TECH" | Yes | Yes | **Yes** |
| "REMY" | No (different name) | Maybe (if summary mentions MIKA) | **Only via BM25 on summary** |
| "Let's talk" | No | Probably not | **No** |
| "noonchi" | No | Probably yes (summary links to MIKAI) | **Maybe via BM25** |

### Entity resolution vs edge extraction vs graph traversal

| Mechanism | Question it answers | How it works |
|---|---|---|
| **Entity resolution** | "Is this NEW entity the SAME as an existing one?" | Name similarity (vector + fuzzy + LLM) |
| **Edge extraction** | "What RELATIONSHIP does this entity have to others?" | LLM reads episode content, extracts relationships |
| **Graph traversal** | "What's connected to this entity?" | Follow existing edges (BFS, shortest path) |

**REMY connects to MIKAI through edges** (shared concepts like "AI"), not through entity resolution (they're different entities). The graph found 15 paths between them.

**"Let's Talk" is an orphan** — no edges, no path to MIKAI. The conceptual connection (both are about understanding people through data) was never stated explicitly in a note.

### Implicit vs explicit knowledge

Graphiti captures **explicitly stated relationships**. If a note says "REMY became MIKAI", it's an edge. If the evolution happened gradually across 50 notes without ever stating the connection directly, the graph doesn't know.

**Community detection** solves implicit connections: if "Let's Talk" and MIKAI share common neighbors or similar summaries, label propagation clusters them together even without a direct edge.

---

## Graph Quality Metrics (2026-04-08)

### Connectivity distribution

| Connectivity | Entities | % |
|---|---|---|
| 0 edges (orphan) | 1,233 | 17.6% |
| 1-2 edges | 4,239 | 60.6% |
| 3-5 edges | 936 | 13.4% |
| 6-10 edges | 359 | 5.1% |
| 11+ edges (hubs) | 223 | 3.2% |

### Hub entities (most connected)

International Villages (50), Germaine (39), MIKAI (33+), Brian (30), AI (26), Kareem (22), Bounce (18)

### Orphan categories

1. **Noise fragments** — "A bee", "2327 storage number" → prune
2. **Substantive but isolated** — "Let's Talk", "Alexander technique" → need community detection
3. **Duplicates** — two "Adwords" entries → need dedup pass

---

## Import Status

| Source | Episodes | Status | Method |
|---|---|---|---|
| Apple Notes | 1,102 | **Complete** | `add_episode()` sequential |
| Claude threads | 87/649 | Partial (ran out of DeepSeek credits) | `add_episode()` turn-by-turn with saga |
| Perplexity | 0/583 | Not started | `add_episode()` query+answer with saga |

### Costs incurred

| Phase | Method | Episodes | Estimated cost |
|---|---|---|---|
| Apple Notes (bulk batches) | `add_episode_bulk` × 10 | ~500 | ~$8 |
| Apple Notes (sequential) | `add_episode` | ~600 | ~$5 |
| Claude threads (partial) | `add_episode` | 87 | ~$1 |
| Comparison tests | Various | ~20 | ~$0.50 |
| **Total spent** | | | **~$14.50** |

### Remaining cost estimate

With mature graph (6,990 entities, 80%+ Tier 1/2 resolution):
- Claude threads: 562 remaining × ~$0.008 = **~$4.50**
- Perplexity: 583 × ~$0.006 = **~$3.50**
- **Total remaining: ~$8**

---

## Technical Setup

### Stack

| Component | Technology |
|---|---|
| Graph database | Neo4j 5.26 (Docker) |
| Knowledge graph framework | graphiti-core (Python, open source) |
| LLM (extraction + resolution) | DeepSeek V3 via OpenAI-compatible API |
| Embeddings | Voyage AI voyage-3 (1024-dim) + Nomic v1.5 (768-dim, local) |
| Sidecar API | FastAPI (Python, Docker) |
| MCP server | TypeScript (queries via sidecar HTTP or SQLite directly) |

### Key files

| File | Purpose |
|---|---|
| `infra/graphiti/docker-compose.yml` | Neo4j + sidecar containers |
| `infra/graphiti/sidecar/main.py` | FastAPI sidecar with DeepSeekClient |
| `infra/graphiti/scripts/import_sequential.py` | Sequential import (notes, claude, perplexity) |
| `infra/graphiti/scripts/bulk_import.py` | Batch import (Apple Notes, deprecated for large graphs) |
| `infra/graphiti/scripts/add_nomic_embeddings.py` | Post-hoc Nomic embedding addition |
| `infra/graphiti/scripts/compare_quick.py` | Voyage vs Nomic embedding comparison |

### Patches applied

| Patch | File | What it does |
|---|---|---|
| Attribute stripping + candidate cap | `node_operations.py` (venv site-packages) | Prevents context overflow at scale |
| DeepSeekClient | `sidecar/main.py` | Uses `json_object` mode instead of `json_schema` |
| PassthroughReranker | `sidecar/main.py` | Avoids OpenAI dependency for cross-encoder |

---

## Embedding Comparison: Voyage vs Nomic

Tested on 3 dense content pieces (journal, perplexity thread, claude thread):

| Dimension | Voyage | Nomic |
|---|---|---|
| Entity count | 30 | 30 (same) |
| Entity overlap | 83% shared | |
| Search precision | Better top-1 ranking | More specific but generic ranking |
| Granularity | Merges more aggressively | Preserves more distinct entities |
| Edge density on threads | 97 edges/20 turns | 124 edges/18 turns |
| User intent preservation | Generic edges | Granular ("HAS_THREADS_ABOUT industry/entrepreneurship/market research") |
| Speed | ~500ms/embed (API) | ~5ms/embed (local) |
| Cost | $0.06/MTok | $0 |

**Conclusion:** Nomic better for knowledge graph granularity and import speed. Voyage better for search ranking. Both embeddings stored on all entities (dual embedding).

---

## Next Steps

1. **Run community detection** — connect orphan entities through implicit relationships
2. **Resume Claude thread import** (562 remaining, ~$4.50)
3. **Import Perplexity** (583 episodes, ~$3.50)
4. **Prune noise orphans** — remove fragments that add no graph value
5. **Re-run Nomic embeddings** on new entities after import completes
6. **Wire MCP server to Graphiti** — L3Backend interface connecting TypeScript MCP to Neo4j

---

*For strategic context, see `CLAUDE.md` (architectural constraints) and `private/strategy/02_EXECUTION_STRATEGY.md` (V3 Graphiti adoption). For MCP tool design, see `docs/ARCHITECTURE.md`.*
