# MIKAI Architecture Gaps & Risk Triggers
**Assessed: March 2026**
**Status: Active — review before each phase gate**

---

## Summary

MIKAI's MCP tool surface is coherent for single-user Phase 1 but has 7 structural gaps that will compound at scale. Two are P0 (blocking beta), five are P1 (competitive disadvantage within 3 months). The epistemic edge vocabulary — the claimed competitive moat — is stored but barely queried.

---

## P0: Must Fix Before Beta

### Gap 1: No Write Path from MCP Tools
All 6 MCP tools are read-only. Claude cannot:
- Record new information from conversation
- Mark a tension as resolved
- Note that a stalled item was actioned
- Correct an inaccurate extraction

The graph only updates through the batch sync pipeline. If Claude surfaces a stalled desire the user already resolved, and can't record that resolution, trust degrades.

**Risk trigger:** User says "I booked that restaurant" → Claude re-surfaces it as stalled next session.
**Minimum fix:** `mark_resolved(node_id)` and `add_note(content)` write tools. Deterministic, cheap, no LLM needed.
**Effort:** 1-2 days.

### Gap 2: Documentation Claims vs Reality
`MIKAI_Architecture_Memory_Comparison.md` Section 7 checklist marks these as complete:

| Claimed Complete | Actual Status |
|---|---|
| BM25 keyword retrieval | **Not implemented.** Zero full-text search code in codebase. |
| Five-operation Update Resolver | **Not implemented.** No resolver code exists. |
| Four-timestamp edges (valid_from, valid_to, etc.) | **Not implemented.** Schema has only `created_at`. |
| Async summarization | **Not implemented.** |

All downstream planning that assumes these exist is operating on false premises.
**Fix:** Correct the comparison doc. Move claimed items to "planned" status.
**Effort:** 2 hours.

---

## P1: Fix Within 3 Months

### Gap 3: Pure Vector Retrieval — No Keyword or Temporal Fusion
`search_knowledge` and `search_graph` use only Voyage AI embedding similarity. No BM25/full-text search. No temporal filtering. No cross-encoder reranking.

Estimated retrieval quality: 50-60% on LongMemEval (vs Hindsight's 91.4%).

**Concrete failure mode:** Query "rent costs" fails if segments use "lease" instead of "rent." BM25 catches partial term overlap that embeddings miss.
**Fix:** Add Supabase `to_tsvector` full-text search as parallel retrieval path. Run vector + full-text, merge results.
**Effort:** 2-3 days.

### Gap 4: No Conflict Resolution
`build-graph` writes nodes without checking for duplicates or contradictions against existing nodes. No dedup logic, no embedding-similarity check before insert.

**Risk trigger:** 30-minute sync frequency re-processes unchanged sources, creating duplicate nodes.
**Fix:** Before node insertion, check embedding similarity against existing nodes from same source. Similarity > 0.92 → skip (NOOP).
**Effort:** 3-5 days.

### Gap 5: No Temporal Validity on Edges or Nodes
Schema has only `created_at`. Cannot answer "what did I believe about X in January?" Cannot expire superseded beliefs. Cannot track belief revision.

The epistemic design doc (07_EPISTEMIC_DESIGN.md) explicitly requires distinguishing episodic from semantic memory. The schema cannot express this.

**Fix:** Add `valid_from TIMESTAMPTZ` and `expired_at TIMESTAMPTZ` columns to edges table. Cheap to add now, expensive to retrofit later.
**Effort:** 1 hour (schema) + 1 day (extraction prompt update).

### Gap 6: Epistemic Edge Vocabulary Under-Leveraged
Edge types (supports, contradicts, unresolved_tension, partially_answers, depends_on, extends) are stored but only used for **sort ordering** in `search_graph`. They do not:
- Influence retrieval scoring (a `contradicts` edge should boost relevance more than `supports`)
- Trigger automatic tension detection when a query touches an unresolved edge
- Track belief revision chains
- Get used by `search_knowledge` at all

The claimed competitive moat is an asset that is barely read.

**Fix:** In `search_graph`, boost nodes reached via `contradicts` or `unresolved_tension` edges. In `search_knowledge`, cross-reference with graph edges when segments match near a tension.
**Effort:** 1 day.

### Gap 7: Single-Tenant Schema
No `user_id` column on sources, nodes, edges, or segments. All RPCs search the full database.

**Risk trigger:** Second user.
**Fix:** Add nullable `user_id UUID` column to all four tables now. Default to constant for current single user. Prevents the most expensive possible future migration.
**Effort:** Half day.

---

## P2: Defer 6+ Months

| Gap | When Needed | Effort |
|---|---|---|
| Server-side synthesis (reflect operation) | Phase 4 (WhatsApp/Siri need pre-synthesized output) | 1-2 weeks |
| RRF score fusion across retrieval strategies | After BM25 is implemented | 1 week |
| Cross-encoder reranking | Marginal quality lift, adds latency | 3-5 days |
| Migrate IVFFlat → HNSW index | Before 50K segments | 1 hour |

---

## P3: Architectural Awareness

| Item | Notes |
|---|---|
| Multi-hop graph traversal (spreading activation) | ARCH-015 caps at 1 hop + 15 nodes. Revisit when graph > 10K nodes. |
| Confidence decay on unqueried nodes | `query_hit_count` column exists but is never incremented by MCP tools. Latent feature. |
| REFRAME operation | Requires working Update Resolver first (Gap 4). Do not build standalone. |

---

## Competitive Position (Honest)

| Capability | MIKAI | Mem0 | Hindsight | Verdict |
|---|---|---|---|---|
| Epistemic edges | **Unique** — no competitor has typed reasoning relationships | Factual only (lives_in, prefers) | Confidence-scored opinions | MIKAI advantage (if leveraged — Gap 6) |
| Tension surfacing | **Unique** — `get_tensions` is a novel inference tool | None | None | MIKAI advantage |
| Stall detection | **Unique** — `get_stalled` via rule engine | None | None | MIKAI advantage |
| L1 context brief | **Unique** — `get_brief` auto-injects context | None | None | MIKAI advantage |
| Retrieval quality | Pure vector, 1-hop graph | Vector + optional graph | 4-strategy + RRF + reranker | MIKAI disadvantage (Gap 3) |
| Write path | **None** | Full CRUD | retain() | MIKAI critical gap (Gap 1) |
| Temporal reasoning | created_at only | None | Temporal retrieval channel | MIKAI disadvantage (Gap 5) |
| Conflict resolution | **None** | ADD/UPDATE/DELETE/NOOP | Confidence evolution | MIKAI disadvantage (Gap 4) |

---

*Review this document before each phase gate. Update gap status as items are resolved.*
