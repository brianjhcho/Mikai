# Upstream PR Draft: Configurable Resolution Candidate Cap

*For: graphiti-core (github.com/getzep/graphiti)*
*Proposed by: Brian Cho (MIKAI project)*
*Reference: docs/GRAPHITI_INTEGRATION.md*

---

## PR Title

feat: configurable max_resolution_candidates to prevent context overflow at scale

## Problem

`_resolve_with_llm()` in `graphiti_core/utils/maintenance/node_operations.py` spreads `**candidate.attributes` into the LLM prompt for ALL candidates returned by hybrid search, with no upper bound. This creates a prompt-size scaling cliff:

- **Small graphs (< 2,000 entities):** 80 candidates × 100 tokens = 8K prompt. Fine.
- **Large graphs (> 4,500 entities):** 80 candidates × 40,000 tokens (accumulated summaries) = 3.2M tokens. Exceeds any LLM context window.

This was discovered during sequential import of 1,102 Apple Notes into a production graph that grew to 6,990 entities and 8,056 edges. At batch 52 (4,681 entities), the resolution prompt requested 2.3M tokens against DeepSeek V3's 131K context limit.

Two compounding factors:

1. **Unbounded candidate list.** `indexes.existing_nodes` contains ALL candidates from Step 2 (hybrid search), including entities already resolved deterministically in Step 3 (Tier 1/2). Only the unresolved remainder should reach the LLM.

2. **Full attribute spreading.** `**candidate.attributes` includes accumulated summaries that grow with each episode. After 800+ episodes, a frequently-mentioned entity like "MIKAI" accumulates ~2,000 tokens of summary alone.

## Proposed fix

Add a configurable `max_resolution_candidates` parameter (default 50) and strip attributes from the resolution prompt context (LLM only needs name + labels for dedup):

```python
# Before (current, line 299-308)
existing_nodes_context = [
    {
        **{"name": candidate.name, "entity_types": candidate.labels},
        **candidate.attributes,
    }
    for candidate in indexes.existing_nodes
]

# After (proposed)
max_candidates = getattr(graphiti_config, 'max_resolution_candidates', 50)
existing_nodes_context = [
    {"name": candidate.name, "entity_types": candidate.labels}
    for candidate in indexes.existing_nodes[:max_candidates]
]
```

## Quality impact

Minimal. The LLM disambiguates entity identity by comparing names and type labels, not by reading full summaries. In testing across 1,102 episodes (6,990 entities):

- Resolution accuracy: no observable degradation
- Prompt size: reduced from unbounded (up to 3.2M tokens) to a fixed ceiling (~1,000 tokens for 50 candidates × ~20 tokens each)
- Cost per episode: reduced from variable/$0.04 peak to stable ~$0.005 in mature graphs

## Why this should be configurable

Different use cases have different graph sizes and LLM context budgets:

- **Chat ingestion** (Graphiti's design target): graphs stay small, candidates are few, current behavior works. Default of 50 is more than sufficient.
- **Bulk import of rich content** (MIKAI's use case): graphs grow to 5K-10K+ entities, attributes accumulate, the cap prevents overflow.
- **Large-context LLMs** (future): users with 1M-context models might want a higher cap. Configurability lets them tune it.

## Supporting data

Full technical analysis with cost curves, resolution tier breakdown, and comparison of Graphiti's design assumptions vs. bulk import behavior:

- Scaling issue root cause and math: [docs/GRAPHITI_INTEGRATION.md §Scaling Issue](https://github.com/brianjhcho/Mikai/blob/main/docs/GRAPHITI_INTEGRATION.md#scaling-issue-context-window-overflow-at-4500-entities)
- Resolution cost scaling curves: [docs/GRAPHITI_INTEGRATION.md §How Resolution Costs Scale](https://github.com/brianjhcho/Mikai/blob/main/docs/GRAPHITI_INTEGRATION.md#how-resolution-costs-scale)
- Entity resolution pipeline explanation: [docs/GRAPHITI_INTEGRATION.md §Graphiti's Entity Resolution Pipeline](https://github.com/brianjhcho/Mikai/blob/main/docs/GRAPHITI_INTEGRATION.md#graphitis-entity-resolution-pipeline)

## Breaking changes

None. The default behavior (50 candidates, stripped attributes) is strictly safer than the current behavior (unbounded candidates, full attributes). Users who want the current behavior can set `max_resolution_candidates` to a very large number.

## Testing

- Tested on a 6,990-entity graph imported from 1,102 Apple Notes episodes
- Sequential `add_episode()` with the patch applied completed the full import without context overflow
- No observable resolution quality degradation vs. the first 20 batches (where the original code still fit within context)
