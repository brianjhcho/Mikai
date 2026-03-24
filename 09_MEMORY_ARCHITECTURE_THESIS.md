# MIKAI Memory Architecture Thesis
**Date:** March 2026
**Status:** Active — strategic reference for all architecture decisions
**Supersedes:** Informal positioning in CLAUDE.md and competitive strategy docs

---

## The Honest Competitive Position

### What Is NOT a Moat

| Claimed Differentiator | Why It's Not Defensible |
|---|---|
| "Infers what you want" | Mem0 + one prompt + one schema change gets 80% of the way there |
| Epistemic edge vocabulary | Any competitor can add `supports`/`contradicts` edge types in a migration |
| Tension surfacing | One new query + one UI feature |
| Source-type-aware extraction | Pipeline engineering, replicable in 1-2 weeks |
| Behavioral data accumulation | Every memory system creates switching costs |
| Three-track extraction | Architectural pattern, not proprietary |

The memory infrastructure space is commoditizing. Six+ serious competitors shipped in 12 months. The architecture is converging on vector + graph + temporal as standard. Features that feel novel today will be table stakes in 6 months.

### What IS Defensible: The Intention-Behavior Gap

No competitor cross-references **stated intentions** (from notes, conversations, reflections) against **actual behavior** (from email, messages, calendar, transactions) to detect where intentions have stalled and why.

```
Track A: What Brian THINKS  →  "I've decided to build in East Africa"
Track B: What Brian DID     →  No flight booked. No visa. No contacts.
THE GAP:                    →  Intention stalling for 3 weeks. Why?
```

Mem0 stores what Brian SAID. Hindsight recalls what Brian SAID. Supermemory extracts what Brian SAID. None compare what was said to what was done.

### The Optimization Target Defense

**Most memory systems will optimize for engagement** — more tool usage, more queries, more premium features. This is the default incentive structure for SaaS.

**MIKAI optimizes for action** — the system succeeds when the user ACTS on a surfaced intention, not when they USE the tool more. The dismiss rate metric (Phase 4: <30% after 20 interactions) is a structural product gate that forces this optimization.

Over time, engagement-optimized and action-optimized systems diverge because the training signal is different:
- Engagement-trained: learns to surface things that make you browse
- Action-trained: learns to surface things that make you act

This produces fundamentally different products from identical starting architecture.

---

## Memory Architecture: Short-Term → Evaluation → Long-Term → Inference

### The Two-Phase Memory Model

Every sophisticated memory system (biological and artificial) has two phases:

**Phase 1: Short-Term Memory (capture + hold)**
- Everything comes in: notes, conversations, behavioral signals
- Stored quickly, cheaply, with minimal processing
- Available for immediate recall but not yet evaluated for importance
- Analogous to: hippocampal encoding in neuroscience, Letta's "recall memory", MIKAI's Track C segments

**Phase 2: Long-Term Memory (evaluate + commit)**
- An evaluation pass determines what's worth keeping
- Content is classified: fragment vs structured ideation vs processed reflection (07_EPISTEMIC_DESIGN.md)
- Relationships are established: supports, contradicts, unresolved_tension
- Beliefs are tracked over time: what changed, when, why
- Analogous to: cortical consolidation in neuroscience, Letta's "core memory", MIKAI's Track A graph nodes

**The Evaluation Bridge:**
The transition from short-term to long-term is the most critical operation. This is where:
- Fragments get filtered (most are noise)
- Recurring patterns get promoted (a fragment that appears 5x becomes a belief)
- Contradictions get detected (new information vs existing graph)
- Temporal validity gets set (when did this become true? is the old belief now expired?)

### How Competitors Handle This

| System | Short-Term | Evaluation | Long-Term | Intent Synthesis |
|---|---|---|---|---|
| **Mem0** | Conversation buffer + rolling summary | LLM-based ADD/UPDATE/DELETE/NOOP resolver | Vector store + Neo4j graph | None |
| **Zep/Graphiti** | Episode subgraph (raw input, non-lossy) | Entity extraction + conflict detection + temporal invalidation | Semantic entity subgraph + community subgraph | None |
| **Hindsight** | Retain pipeline (fact extraction + temporal tagging) | Confidence scoring + opinion evolution | Four memory networks (World/Experience/Observation/Opinion) | Reflect operation (synthesis across memories with disposition params) |
| **Letta** | Message buffer (FIFO + recursive summarization) | Agent self-decides via inner monologue | Core memory blocks + archival memory | Implicit (agent reasons about what to remember) |
| **Supermemory** | Auto-extraction from conversations | Contradiction handling + active forgetting | User profiles + knowledge base | "Right context at right time" (proprietary) |
| **MIKAI (current)** | Track C segments (zero-LLM structural split) | **Missing** — no evaluation bridge | Track A graph nodes (LLM extraction) | get_tensions + get_stalled (partial) |

### The Gap: MIKAI's Missing Evaluation Bridge

MIKAI currently has:
- **Short-term:** Track C segments (25,749 segments, cheap, instant)
- **Long-term:** Track A graph nodes (2,246 nodes, LLM-extracted, expensive)

But the transition between them is a **manual full-corpus extraction pass** (`build-graph`). There is no:
- Automatic promotion of recurring segments to graph nodes
- Contradiction detection between new segments and existing nodes
- Temporal invalidation of superseded beliefs
- Confidence scoring that evolves as evidence accumulates
- Fragment-to-pattern-to-belief progression described in 07_EPISTEMIC_DESIGN.md

### What Each Competitor's Evaluation Bridge Looks Like

**Mem0's Approach (LLM-based resolver):**
```
New input → LLM extracts candidate facts
         → Retrieve top-10 similar existing memories
         → LLM decides: ADD / UPDATE / DELETE / NOOP
         → Write to stores
```
- Cost: 2 LLM calls per input
- Quality: decent for factual conflicts, poor for epistemic conflicts
- Strength: simple, proven
- Weakness: expensive at scale, non-deterministic

**Graphiti's Approach (temporal + entity resolution):**
```
New episode → LLM extracts entities + relationships
           → Entity resolution (exact match → fuzzy → LLM)
           → Contradiction detection vs existing edges
           → Conflicting edges get temporal invalidation (valid_until = now)
           → Community detection updates cluster summaries
```
- Cost: 6-10 LLM calls per episode
- Quality: best temporal reasoning, preserves full history
- Strength: never deletes, only invalidates — full audit trail
- Weakness: very expensive, requires Neo4j

**Hindsight's Approach (confidence evolution):**
```
New input → Retain: extract facts + temporal tags + entity resolution
         → Store across 4 memory networks
         → Opinion network: update confidence scores when evidence arrives
         → Reflect: synthesize across memories on demand
```
- Cost: 2-3 LLM calls + embedding
- Quality: highest benchmark scores (91.4% LongMemEval)
- Strength: confidence scores make belief evolution trackable
- Weakness: reflect() adds per-query cost

**Letta's Approach (agent self-management):**
```
New message → Agent's inner monologue: "Is this worth remembering?"
           → If yes: memory_replace / memory_insert (core memory)
           → If archival: archival_memory_insert
           → Agent manages its own context window
```
- Cost: 1 LLM call (part of normal agent reasoning)
- Quality: depends entirely on model judgment
- Strength: most adaptive, naturally handles nuance
- Weakness: inconsistent, model can miss important info

### What MIKAI's Evaluation Bridge Should Look Like

**Proposed: Tiered evaluation with zero-LLM for most content, LLM for high-value transitions**

```
New source ingested (e.g., Apple Note, Claude thread)
    │
    ▼
[TIER 0: Immediate — zero cost]
    Structural split (smart-split.js) → segments
    Embed segments → searchable immediately
    This is what exists today.
    │
    ▼
[TIER 1: Background evaluation — low cost]
    Run on next scheduled sync (every 30 min):

    a) RECURRENCE CHECK: Do any new segments have high embedding
       similarity (>0.85) to existing segments from DIFFERENT sources?
       If yes → this is a recurring pattern, flag for promotion.
       Cost: Supabase query only (free).

    b) CONTRADICTION CHECK: Do any new segments have high similarity
       to existing graph nodes but OPPOSITE sentiment/stance?
       Cost: Supabase query + simple heuristic (free).
       Flag for LLM conflict resolution if detected.

    c) STALL CHECK: Does the new content mention something that
       was flagged as stalled? If yes → update stall status.
       Cost: Track B rule engine (free).
    │
    ▼
[TIER 2: Promotion — moderate cost]
    Triggered by Tier 1 flags:

    a) RECURRING PATTERN → BELIEF: If a concept appears across 3+
       sources over 2+ weeks, promote to a graph node with high
       confidence. One Haiku call to generate the node label and
       classify its type (concept/decision/tension/question).
       Cost: ~$0.002 per promotion.

    b) CONTRADICTION → RESOLUTION: If Tier 1 flagged a contradiction,
       one Haiku call to determine: is this a genuine belief revision
       (old belief superseded) or a held tension (both beliefs active)?
       If revision → set expired_at on old edge, create new edge.
       If tension → create unresolved_tension edge.
       Cost: ~$0.002 per conflict.

    c) STALL RESOLUTION: If new content resolves a stalled item,
       automatically call mark_resolved.
       Cost: free (Supabase update).
    │
    ▼
[TIER 3: Intent synthesis — on demand]
    Triggered by user query or proactive schedule:

    Cross-reference Track A (beliefs/intentions) vs Track B (behavior):
    - What has the user said they want to do?
    - What have they actually done?
    - Where is the gap?

    This is the intention-behavior gap detection.
    Currently partially implemented (get_stalled).
    Full implementation requires Phase 4 (proactive surfacing).
```

### Implementation Timeline

| Tier | What | When | Cost/source | Already built? |
|---|---|---|---|---|
| **Tier 0** | Structural split + embed | **Now** | $0.0001 | Yes — smart-split.js + build-segments |
| **Tier 1** | Recurrence/contradiction/stall checks | **Phase 3.5** | $0 (Supabase queries) | No — needs recurrence checker |
| **Tier 2** | Pattern promotion + conflict resolution | **Phase 4** | $0.002/promotion | No — needs promotion pipeline |
| **Tier 3** | Intention-behavior gap detection | **Phase 4-5** | $0.01/synthesis | Partial — get_stalled exists |

### Adaptability Assessment

**Can MIKAI adopt this now?**
- Tier 0: Already done. Zero-LLM segmentation is live.
- Tier 1: Yes, implementable now. Recurrence checking is a Supabase embedding similarity query. Contradiction checking uses the same query + a simple polarity heuristic. Both are free (no LLM calls). **Recommend building in next sprint.**
- Tier 2: Deferred to Phase 4. Requires temporal edge columns (P1-3 in architecture gaps) and a basic Update Resolver. The Haiku calls are cheap but the logic is complex.
- Tier 3: Deferred to Phase 4-5. Requires proactive surfacing (WhatsApp or Cowork) to generate dismiss/act training signals.

**Can MIKAI adopt Graphiti's bitemporal model?**
Yes, partially. Add `valid_from` and `expired_at` to edges table (1 hour schema migration). Full bitemporal (4 timestamps) is overkill — two timestamps capture 90% of the value. Population happens at Tier 2 when contradictions are resolved.

**Can MIKAI adopt Hindsight's confidence scoring?**
Yes. Add a `confidence` float column to nodes table. Starts at 0.5 for new nodes. Incremented when supporting evidence arrives (Tier 1 recurrence check). Decremented when contradicting evidence arrives. This is a simple update, not a new architecture.

**Can MIKAI adopt Letta's agent self-management?**
Partially — through the `add_note` and `mark_resolved` MCP tools. Claude (the agent) can now write to the knowledge base. But full Letta-style management (agent decides what to retain/forget on every message) is too expensive per D-026 (LLM reserved for 3 roles only). The hybrid approach (structural ingestion + targeted agent writes) is the right balance.

---

## The Three-Layer Architecture (Revised)

```
LAYER 3: INTENTION-BEHAVIOR GAP DETECTION (the real moat)
═══════════════════════════════════════════════════════════
  Not "what does this person want?" (Mem0 can answer that)
  But "where is this person stuck, and why?"

  Cross-reference Track A (stated intentions from authored content)
  vs Track B (actual behavior from email, messages, calendar)

  Optimize for ACTION (dismiss rate < 30%)
  Training signal: user acts or dismisses surfaced intentions

  No competitor is building this because:
  1. Requires multi-source data (authored + behavioral)
  2. Requires cross-track inference
  3. Optimization target (action) is structurally opposed to engagement
  4. The evaluation methodology doesn't exist yet (MIKAI must create it)

LAYER 2: MEMORY INFRASTRUCTURE (commodity — adopt best patterns)
═══════════════════════════════════════════════════════════
  Short-term: Zero-LLM structural segmentation (Tier 0) — BUILT
  Evaluation: Recurrence + contradiction + stall checks (Tier 1) — NEXT
  Long-term: Graph with temporal edges + confidence scores (Tier 2) — PLANNED

  Retrieval: Vector + BM25 + graph traversal (adopt from Hindsight)
  Conflict resolution: Temporal invalidation (adopt from Graphiti)
  Active forgetting: Confidence decay (adopt from Supermemory)

LAYER 1: MEMORY INTERFACE (commodity — MCP standard)
═══════════════════════════════════════════════════════════
  8 MCP tools (6 read + 2 write)
  JSONL export for portability
  Model-agnostic (Claude, ChatGPT, Cursor, any MCP client)
```

---

## Standing Strategic Questions

**Q: What happens when Claude's native memory gets good enough?**
If Claude can natively track belief revision and surface stalled intentions, Layer 3 becomes redundant. The defense: MIKAI's cross-source data (Apple Notes + Gmail + iMessage + Perplexity) gives it information Claude's native memory doesn't have. Claude's memory only knows what you told Claude. MIKAI knows what you told everyone.

**Q: What happens when Mem0 adds desire inference?**
They'll optimize for engagement (more API calls = more revenue). MIKAI optimizes for action. Different training signals → different products over time. But this is a philosophical defense, not a technological one. If Mem0 genuinely adopts action-optimization, MIKAI's moat narrows significantly.

**Q: What happens when Apple builds this into the OS?**
Apple has the data (Notes, Calendar, Messages, Mail, Safari). Apple has the privacy story. Apple has the distribution. If Apple Intelligence evolves into an intention-behavior gap detector, MIKAI's position becomes extremely difficult. The defense: Apple will optimize for the median user, not for the power user who writes 2,000+ notes and wants epistemic reasoning. MIKAI's depth on personal knowledge work is a niche Apple won't serve.

**Q: Is the moat just "Brian's personal tool"?**
Possibly. A tool perfectly tuned to one person is a product of one, not a business. The business question is: does the intention-behavior gap detection generalize? Phase 4 (5 beta users) tests this. If other users find the tension surfacing and stall detection valuable, MIKAI has a business. If only Brian finds it useful, MIKAI is a personal utility.

---

---

## Future Phase Design (Detailed)

### Phase 4: Evaluation Bridge + Infrastructure

The critical missing piece: the transition from short-term segments to long-term graph nodes.

**4A: Tier 1 Evaluation Checks (zero LLM cost)**

Run after every sync cycle (every 30 min):

- **Recurrence detector:** For each new segment, query segments table for embedding similarity > 0.85 from DIFFERENT sources. If found → flag as recurring pattern, increment counter. When count reaches 3+ sources across 2+ weeks → trigger Tier 2 promotion. Cost: Supabase vector query only.

- **Contradiction detector:** For each new segment, find similar graph nodes. Check for negation/opposition signals ("not", "wrong", "actually", "changed my mind", "I used to think"). If detected → flag for Tier 2 conflict resolution. Cost: Supabase query + text heuristic.

- **Stall resolver:** Check if new content mentions entities/topics from stalled nodes. If found → auto-reduce stall_probability or call mark_resolved. Cost: Supabase query only.

**4B: Infrastructure Upgrades**

- BM25 keyword search: Add `to_tsvector` column to segments table. Run vector + full-text in parallel, merge via RRF. Catches "rent" vs "lease" synonym failures. (P1-1 from architecture gaps)
- Temporal edges: Add `valid_from`, `expired_at` columns. Populated by Tier 2 conflict resolution. (P1-3)
- Confidence scoring: Add `confidence` float to nodes. Starts 0.5, incremented by recurrence, decremented by contradiction. (Adopted from Hindsight)
- Epistemic edge scoring: Boost retrieval relevance for nodes reached via `contradicts`/`unresolved_tension` edges. (P1-4)

**4C: Proactive Surfacing**

Start with the cheapest delivery surfaces:
- **Cowork tasks:** Claude Desktop background tasks running get_tensions/get_stalled periodically. Already possible — zero build.
- **Email digest:** Daily/weekly summary of stalled items and active tensions. Simple script that queries Supabase + sends via Gmail API. Low build effort.
- **WhatsApp (later):** n8n + WhatsApp Business API for immediate desires only. High build effort, defer until Cowork validates the surfacing model.

**4D: Feedback Loop Schema**

Add `surfacing_log` table:
```sql
CREATE TABLE surfacing_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  node_id UUID REFERENCES nodes(id),
  surfaced_at TIMESTAMPTZ DEFAULT now(),
  surfaced_via TEXT, -- 'cowork', 'email', 'whatsapp', 'mcp'
  outcome TEXT, -- 'acted', 'dismissed', 'ignored'
  outcome_at TIMESTAMPTZ
);
```

This generates the dismiss/act training signal that makes desire inference learnable.

### Phase 5: Desire Classification + Trajectory

**5A: Desire Level Classification**

Add `desire_level TEXT` to nodes table: `immediate` / `instrumental` / `terminal`.

Classification rules:
- **Immediate:** Track B behavioral traces with time-bound action verbs. Short time horizon, resolves or decays. "Book the restaurant", "buy the jacket."
- **Instrumental:** Recurring patterns promoted from Tier 2 that persist over months. Active investigation, accumulates evidence. "Understand Kenya coffee market", "research East African real estate."
- **Terminal:** Never extracted directly. Inferred from trajectory of instrumental desires in Phase 5C.

**5B: Trajectory Modeling**

Track how instrumental desires evolve over time:
- **Acceleration:** more sources, more specific queries, shorter intervals between mentions → desire is active and deepening
- **Plateau:** steady mentions but no new evidence → desire may be stuck
- **Decay:** fewer mentions, longer gaps → desire may have been resolved or abandoned

Implementation: query segments by topic similarity across time windows. Plot mention frequency and specificity. This is a Supabase aggregation, no LLM needed.

**5C: Terminal Desire Inference**

The hardest and most valuable operation:
- Gather all active instrumental desires
- One Claude synthesis pass: "What direction do these collectively point?"
- "Brian is researching Kenya coffee, Kenya real estate, Nairobi tech ecosystem, African agritech. These all point toward: building a business presence in East Africa."
- The terminal desire was never stated. It's inferred from trajectory.

This requires: rich instrumental desire data (Phase 5A-B), confidence in trajectory modeling, and a synthesis prompt tuned for desire-level reasoning.

### Phase 6: Multi-Surface Delivery

Different desire levels → different delivery surfaces:

| Desire Level | Urgency | Best Surface | Example |
|---|---|---|---|
| Immediate | High (time-bound) | WhatsApp / push notification | "You mentioned booking the restaurant — here's a draft" |
| Instrumental | Medium (weekly review) | Cowork / email digest | "Your Kenya research has plateaued — 3 new sources but no action in 2 weeks" |
| Terminal | Low (deep conversation) | Claude Desktop | "Your instrumental desires point toward building in East Africa — is that what you actually want?" |

The dismiss rate gate (<30%) applies to ALL surfaces. Each surface tracks outcomes in the `surfacing_log`.

### Phase 7: Multi-User + Memory Passport

If Phase 5 validation shows the system generalizes:
- Add `user_id UUID` to sources, nodes, edges, segments (P1-5, should be done earlier)
- Row Level Security policies on all tables
- MCP server accepts user context
- JSONL export for graph portability
- "Memory passport": same graph, any LLM consumer (Claude, ChatGPT, Cursor)

The validation question: does intention-behavior gap detection work for users who don't write like Brian? (O-025)

### Phase Dependency Map

```
Phase 3.5 (Trust Barrier)
  └──→ Phase 4A (Tier 1 Evaluation) ← zero cost, next to build
        ├──→ Phase 4B (BM25 + temporal edges)
        ├──→ Phase 4C (Cowork proactive surfacing)
        └──→ Phase 4D (Feedback loop schema)
              └──→ Phase 5A (Desire classification)
                    ├──→ Phase 5B (Trajectory modeling)
                    └──→ Phase 5C (Terminal desire inference)
                          └──→ Phase 6 (Multi-surface delivery)
                                └──→ Phase 7 (Multi-user)
```

Critical path: 3.5 → 4A → 4D → 5A → 5C. Everything else is parallel work.

---

*This document should be read alongside 08_ARCHITECTURE_GAPS.md (what's broken) and 07_EPISTEMIC_DESIGN.md (the philosophical foundations). Review before each phase gate.*
