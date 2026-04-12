# Graphiti Best Practices Review

*Reviewed: 2026-04-11*
*Reviewed by: Claude Opus (analysis), Brian Cho (direction)*
*Subject: graphiti-core (by Zep) as MIKAI's L3 knowledge graph dependency*
*Context: MIKAI operates a 6,990-entity, 8,056-edge graph imported from 1,102 Apple Notes episodes with 87 partial Claude thread turns*

---

## Why this review exists

MIKAI adopted graphiti-core as the L3 knowledge graph backbone. When you build on an open-source dependency at this depth — it stores your data, calls LLMs on your behalf, manages your graph schema — you inherit not just their code, but their engineering culture. Their bugs become your bugs. Their scaling assumptions become your constraints. Their API stability determines how much rework each upgrade costs.

This review grades graphiti-core against eight industry best practices for framework design, with specific findings from MIKAI's real-world usage.

---

## Grading Summary

| Dimension | Grade | Impact on MIKAI |
|---|---|---|
| API surface clarity | B- | Minor friction, workaroundable |
| Error handling | C+ | High — context overflow hit in production |
| Scaling behavior | D+ | Critical — required manual site-packages patch |
| Separation of concerns | B+ | Low — plugin system works well |
| Testing | B- | Medium — undiscovered edge cases likely |
| Configuration | C | Medium — hardcoded values force patching |
| Documentation | B- | Medium — MIKAI wrote the best scaling docs |
| Community & maintenance | B | Low near-term risk |

**Overall: B-/C+**

---

## Detailed Findings

### 1. API Surface Clarity — B-

**What good looks like:** A small number of public methods with clear names, typed inputs and outputs, and minimal surprise. Pydantic models or dataclasses for all inputs and outputs, not raw dicts.

**Graphiti findings:**

The public API is reasonably small: `add_episode()`, `add_episode_bulk()`, `search()`, `search_()`, `build_indices_and_constraints()`, `close()`. That's good.

Problems:
- `search()` vs `search_()` — confusing naming. One returns edges, the other returns a `SearchResults` object with separate `.nodes`, `.edges`, `.communities` fields. The underscore convention doesn't communicate the difference.
- `add_episode()` returns a result object with `.episode`, `.nodes`, `.edges` that are all optional (can be None). The caller has to null-check everything. A well-designed return type would guarantee non-None on success and raise on failure.
- `RawEpisode` dataclass for bulk import has different fields from `add_episode()` keyword arguments. If you learn one API, the mental model doesn't transfer.

### 2. Error Handling — C+

**What good looks like:** Typed exceptions for expected failures (auth errors, connection drops, rate limits, constraint violations). Clear error messages that tell you what went wrong and how to fix it. Graceful degradation for transient failures. Never swallowing exceptions silently.

**Graphiti findings:**

This is where MIKAI got burned hardest. The context window overflow at 4,500 entities didn't raise a meaningful error — it generated a prompt exceeding DeepSeek's context window, which threw a generic OpenAI API error. Graphiti's `_resolve_with_llm` didn't check prompt size before sending. There's no concept of "this graph is too large for the configured LLM" as a known failure mode.

More generally, graphiti-core uses bare `except Exception` blocks in several places. When something goes wrong during resolution, you get a logged warning and the episode partially processes. There's no transaction boundary — if extraction succeeds but resolution fails halfway, the graph ends up with some edges but not others, and no way to retry just the failed part.

For a framework designed to be called thousands of times sequentially (one `add_episode()` per message turn), this is a significant gap.

### 3. Scaling Behavior — D+

**What good looks like:** Either the framework handles scale gracefully (bounded memory, bounded prompt sizes, pagination), or it documents its scaling limits explicitly. A developer should never discover a scaling cliff by hitting it in production.

**Graphiti findings:**

This is Graphiti's weakest area:

- `_resolve_with_llm` spreads `**candidate.attributes` unboundedly. After 4,500+ entities, this produces a 2.3M-token prompt against a 131K-token limit. The fix (cap candidates at 50, strip attributes) was developed by MIKAI, not Graphiti.
- `indexes.existing_nodes` contains ALL candidates from hybrid search, not just unresolved ones. Entities handled by deterministic Tier 1/2 still bloat the LLM's candidate list.
- No documentation warns about this. The scaling section of Graphiti's README shows a cost-decreasing curve accurate only for the chat-ingestion use case they designed for.
- `add_episode_bulk` is described in MIKAI's testing as "for bootstrapping small graphs only," but Graphiti's docs don't say this.

Undocumented scaling cliffs are one of the most costly gaps a framework can have: by the time you discover them, you've already built your architecture around the framework's promises.

### 4. Separation of Concerns — B+

**What good looks like:** The framework separates storage (Neo4j), LLM calls (extraction, resolution), embedding, and search into independent, replaceable layers.

**Graphiti findings:**

This is Graphiti's strongest area:

- LLM client is pluggable via `OpenAIGenericClient` subclass (MIKAI uses `DeepSeekClient`)
- Embedder is pluggable via `VoyageAIEmbedder` and config
- Cross-encoder/reranker is pluggable (MIKAI uses `PassthroughReranker`)
- Storage is Neo4j — not pluggable, but the coupling is clean

Why not an A: the LLM client interface leaks implementation details. MIKAI's `DeepSeekClient` overrides `_generate_response` (a private method, note the underscore) because the base class assumes OpenAI's `json_schema` response format. A well-designed plugin interface wouldn't force overriding private methods for provider compatibility.

### 5. Testing — B-

**What good looks like:** Unit tests for core logic, integration tests against a real Neo4j, CI on every PR. Coverage high enough for confident refactoring.

**Graphiti findings:**

Graphiti has a test suite and CI covering the happy path for add_episode, search, and resolution. But the gaps are telling:

- No test for large graphs (the scaling cliff would've been caught by importing 5,000+ entities)
- No test for prompt size limits
- Resolution quality tests are sparse
- The test Neo4j instance is ephemeral and small (doesn't exercise real-world data volumes)

### 6. Configuration — C

**What good looks like:** Sensible defaults that work for the 80% case, with every tunable knob documented and accessible without modifying source code.

**Graphiti findings:**

The `node_operations.py` problem is a configuration gap: there's no configurable cap on candidate count or attribute inclusion. The values are hardcoded in the implementation. MIKAI's patch works but is fragile — any `pip install --upgrade graphiti-core` overwrites it.

Search recipe configuration (`COMBINED_HYBRID_SEARCH_RRF`, etc.) is well-designed — pre-built config objects. The LLM and resolution layers should have the same pattern but don't.

### 7. Documentation — B-

**What good looks like:** API reference, getting-started guide, architecture overview, scaling guide, migration guide, example code.

**Graphiti findings:**

Decent README with code examples and quick-start guide. Architecture explained at a high level. But:

- No scaling guide. MIKAI's `docs/GRAPHITI_INTEGRATION.md` is the best scaling documentation for Graphiti that exists — written by MIKAI, not Graphiti.
- No migration guide between versions
- Search recipe system is barely documented
- `add_episode_bulk` behavior (skips edge invalidation) is in a code comment, not docs

### 8. Community & Maintenance — B

**What good looks like:** Regular releases, responsive issue tracker, clear contribution guidelines, breaking changes communicated with migration paths.

**Graphiti findings:**

Actively maintained by Zep (a real company). Regular updates. Active issue tracker. Accepts contributions. Still early-stage (v0.5.x) which means API stability isn't guaranteed. Building on a moving target is a calculated risk.

---

## Implications for MIKAI

### 1. The patch is load-bearing and fragile

The `node_operations.py` fix (cap candidates at 50, strip attributes) is the only thing preventing context overflow at scale. Every `pip install --upgrade graphiti-core` overwrites it.

**Mitigation:** `scripts/apply_graphiti_patch.py` — a reproducible patch script that re-applies the fix after any upgrade. Run it after every pip install.

**Long-term fix:** Upstream PR proposing configurable `max_resolution_candidates`. See `docs/UPSTREAM_PR_DRAFT.md`. If rejected or ignored for 30+ days, fork graphiti-core.

### 2. The sidecar is half-Graphiti, half-raw-Neo4j

Graphiti's value to MIKAI is the **write path** (ingestion, extraction, resolution, community detection). The **read path** (search, traversal, analytics) covers maybe 30% of what MIKAI needs. The remaining 70% is raw Cypher in the sidecar endpoints.

This ratio will shift further toward raw Neo4j as MIKAI grows. That's the correct architecture: use Graphiti for what it's good at, extend with raw Neo4j for what it doesn't cover.

### 3. Error handling must not trust Graphiti

Every call to `graphiti.search()` and `graphiti.add_episode()` should be wrapped in try/except with specific handling for timeout, connection, and LLM errors. Graphiti's internal error handling is insufficient for production use.

### 4. Fork trigger checklist

Fork `graphiti-core` into `mikai-graphiti-core` if any of these become true:

- [ ] Need to change Graphiti's Neo4j schema (node labels, edge properties, index definitions)
- [ ] Need to modify the entity resolution algorithm (not just the candidate cap)
- [ ] Have patched 3+ files in graphiti-core
- [ ] Upstream PR rejected or sits open 30+ days without response
- [ ] A graphiti-core upgrade breaks the patch AND contains features MIKAI needs

Until then, the current approach (use as dependency, patch one file, extend via raw Cypher) is optimal.

---

## Bottom line

Graphiti is the right choice for MIKAI's L3 given the constraints: you need a graph with temporal edges, entity resolution, and community detection without building a PhD-level system from scratch. But treat it as an 80% solution that you'll need to patch, extend, and eventually contribute back to — not a black box to trust blindly.

The sidecar is your divergence layer. It absorbs the boundary between Graphiti and raw Neo4j. Everything outside the sidecar (MCP server, L4 engine, ingestion automation) never needs to know which backend path each query uses.
