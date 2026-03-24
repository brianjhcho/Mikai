# Epistemic Edge Vocabulary Specification v1.0

**Subtitle:** A framework for modeling reasoning relationships in AI memory systems

**Date:** March 2026

**Status:** Open specification — contributions welcome

**License:** Open for adoption and extension by other memory systems

---

## Section 1: Motivation

Flat fact storage — whether key-value databases, vector stores, or vector-only retrieval — is fundamentally insufficient for modeling how humans think. These systems can record atomic facts but cannot represent the structure of reasoning itself.

Consider the difference between two statements:
- "User prefers Python." (a fact)
- "User is deciding between Python and Rust — wrote positively about Rust's memory safety last week but chose Python for a prototype yesterday, suggesting the decision is unresolved." (a reasoning structure)

A vector-only system might retrieve both statements when asked about language preferences, but it cannot distinguish between a settled belief and an active contradiction the user is holding. It cannot surface the tension. It cannot tell you what the user is actually thinking about — only what facts are in the store.

The epistemic edge vocabulary solves this by adding typed relationships that capture not just what someone believes, but *how they believe it*: whether they are conflicted, whether they are investigating, whether one belief is becoming invalidated by new evidence. These relationships are what make a graph legible to both humans and AI during synthesis.

This matters because the highest-value signal in personal knowledge work is often not where thinking is settled — it is where it is unresolved. An AI that papers over tensions produces worse output than one that surfaces them and asks clarifying questions.

---

## Section 2: Node Types

| Type | Definition | When to Use | When NOT to Use | Examples |
|------|-----------|------------|-----------------|----------|
| **concept** | A belief, idea, or mental model the person holds | Use when extracting a working hypothesis, a recurring principle, or a general idea the person has developed | Do NOT use for temporary fragments or fleeting thoughts with one mention only | "Passive capture is the moat, not a convenience feature" / "Self-model is constructed in real-time from available evidence, not discovered" / "Epistemic edge typing is more valuable than passive data accumulation" |
| **question** | An open question the person is actively investigating | Use when the source explicitly shows the person probing, testing, or trying to resolve something | Do NOT use for rhetorical questions or questions already answered elsewhere in the corpus | "Does the extraction prompt generalize beyond my writing style?" / "What is the minimum corpus threshold for meaningful inference?" / "How should the graph handle beliefs the person no longer holds?" |
| **decision** | A resolved choice with reasoning attached | Use when the source shows the person concluding something after deliberation, with a clear reasoning chain | Do NOT use for assumptions, hypotheses, or choices that later evidence contradicts | "Use Supabase only — no separate vector DB" / "MCP is the sole product surface in Phase 1" / "Optimize for action (dismiss rate <30%) rather than engagement" |
| **tension** | An active contradiction the person is holding without resolution | Use when the source explicitly contains two incompatible beliefs or goals that the person is actively managing together | Do NOT use for resolved contradictions (those become two separate nodes linked by contradicts) or for simple disagreements with external sources | "Engine-first vs distribution-first — when does the surface decision become blocking?" / "Trust over engagement is the right optimization target, but monetization strategy is undefined" / "Personal utility vs scalable business are in structural tension" |
| **project** | An ongoing initiative or goal | Use when extracting something the person is actively building toward, with evidence of repeated action or refinement | Do NOT use for ideas the person mentioned once or aspirational goals with no demonstrated commitment | "Build MIKAI's MCP server for Claude Desktop" / "Develop the three-layer memory architecture (interface → infrastructure → intention-behavior gap detection)" / "Establish evaluation methodology for memory extraction quality" |

### Node Type Misclassifications: Common Pitfalls

**concept vs question:** "I wonder if passive capture is the moat" appears in a section that goes on to thoroughly explain why it isn't. This is not a question — the person has concluded something. Extract as a concept. A true question is "Does my extraction prompt generalize beyond my writing?" where the person hasn't yet worked through the answer.

**decision vs concept:** "I've decided X" feels like a decision, but if the decision is theoretical (not yet acted on) and the reasoning is incomplete, it may be a concept. A true decision has reasoning trace and typically appears at the end of deliberation. "I'll use Supabase only" after weighing Graphiti, Neo4j, and Postgres is a decision. "Supabase seems good" in early exploration is a concept.

**tension vs two separate nodes linked by contradicts:** A tension node means the person is actively holding both beliefs at once, managing the conflict. Example: "Engine matters most, but distribution is also critical — can't do one without the other." This is unresolved and active. If instead the source shows "I used to think distribution first, but now I believe engine-first is right," this is not a tension — it is two nodes (old belief, new belief) linked by a contradicts edge with a valid_from/expired_at timestamp.

**project vs decision:** "I've decided to build MIKAI's MCP server" is a decision. "I'm building MIKAI's MCP server — integrated with Claude Desktop, 8 tools, handling Track C synthesis" is a project. The distinction: projects have ongoing refinement and evidence of repeated action. Decisions are moments of commitment. A decision can spawn a project.

---

## Section 3: Edge Types

All edges carry a required `note` TEXT field (free-form plain language) that explains the specific relationship. The note is what makes edges legible to both humans and AI during synthesis. Examples: "Node A (design decision for Supabase) assumes Node B (single-player optimization) — if B changes, A must be revisited" or "User held A (Python is best) until new evidence (Rust's memory safety), now actively comparing both — unresolved_tension."

| Edge Type | Priority | Definition | Crucial Distinction | Directionality | Example |
|-----------|----------|-----------|---------------------|-----------------|---------|
| **unresolved_tension** | 0 (highest) | Internal conflict the person is actively holding — both beliefs are simultaneously active, no clear resolution path | vs **contradicts:** unresolved_tension is internal holding (two nodes both active), contradicts is structural conflict (one may supersede the other). Tensions are about psychology; contradicts are about logic. | Bidirectional — if A and B are in tension, the relationship is symmetric | User believes "engine work is critical" AND "distribution is critical" simultaneously. Both are lived as active principles. Edge note: "User recognizes both are essential but unclear which constraint is blocking." |
| **contradicts** | 1 | Structural contradiction between two nodes — one may supersede the other, or they represent different time periods | vs **unresolved_tension:** contradicts is structural (logically incompatible); unresolved_tension is psychological (both held active). A contradicts relationship may resolve into depends_on or supports. | Directional — from old/challenged belief to new/challenging belief. Can be tagged with valid_from and expired_at | User believed "Python best for prototypes" (old node, expired_at=date), contradicts new belief "Rust for memory safety" (new node, valid_from=date). Edge note: "New evidence from safety-critical prototype triggered belief update." |
| **depends_on** | 2 | Node A cannot be resolved without Node B | vs **partially_answers:** depends_on means B is a prerequisite; partially_answers means B addresses part of A but doesn't resolve it | Directional — from dependent (A) to prerequisite (B). One-way causal chain | Decision "Use Supabase only" depends_on resolved question "Will Neo4j scale to 100k nodes?" Until the question is resolved (or answered satisfactorily), the decision remains contingent. |
| **partially_answers** | 3 | Node A addresses part of Node B but doesn't fully resolve it | vs **depends_on:** partially_answers is partial resolution; depends_on is a blocker | Directional — from answering (A) to questioned (B) | Concept "Temporal edges with valid_from/expired_at capture belief revision" partially_answers question "How do we track when beliefs change?" It's an answer but not complete — doesn't address how to populate those timestamps. |
| **supports** | 4 | Node A provides evidence or reasoning for Node B | vs **extends:** supports is evidential (A justifies B); extends is developmental (A builds on B). | Directional — from evidence (A) to supported (B) | Concept "Recurrence signal is stronger than single-mention signal" supports decision "Weight multi-source evidence higher than single-source." Edge note: "Two mentions across different sources indicates pattern, not noise." |
| **extends** | 5 (lowest) | Node A builds on Node B without contradiction | vs **supports:** extends is structural building (A develops B further); supports is evidential (A justifies B). | Directional — from extending (A) to extended (B) | Concept "Epistemic edge typing" extends concept "Graph-based knowledge representation." Edge note: "Adds relationship semantics to standard graph model." |

### Edge Priority Ordering Rationale

The priority ordering is not arbitrary. When synthesizing from a person-graph, the system retrieves a subgraph seeded by vector similarity, then expands via edges in priority order. Edges are returned in this sequence:

1. **unresolved_tension (0):** Highest priority because unresolved thinking is the signal. If you want to know what someone is actually thinking about, ask about their tensions. A person holding a contradiction actively is doing something cognitively interesting.

2. **contradicts (1):** Next priority because contradiction indicates change. When someone updates a belief, the old and new nodes are both informative — the edge between them tells you the trajectory of thought.

3. **depends_on (2):** Dependencies show the structure of reasoning — what needs to be settled before this can be settled.

4. **partially_answers (3):** Partial answers are less valuable than full answers but more valuable than supportive evidence (which can be abundant and less selective).

5. **supports (4):** Supporting evidence is valuable but abundant. Too much support edge retrieval produces unfocused results.

6. **extends (5):** Extends is the weakest relationship — it builds on something but adds minimal new signal. Lowest priority in retrieval.

This ordering implements a hypothesis: **in synthesis, the most valuable signal is where thinking is unresolved, not where it is settled.** An AI fed a subgraph biased toward tensions, contradictions, and dependencies will ask better questions and surface more actionable insights than one fed a subgraph dominated by supportive evidence.

---

## Section 4: The Extraction Quality Standard

Extraction quality is measured by whether the output reveals the structure of reasoning, not by how many facts are captured.

A good extraction from a personal reflection should produce:

- **At least 2 tension or question nodes out of 5–7 total.** If every node is a concept or decision, extraction has drifted to summarization. The person's document showed thinking being worked through; the graph should reflect that work.

- **Content fields in first-person.** "I've concluded that passive capture alone isn't enough" not "The author believes passive capture alone isn't enough." The graph models *this person's* reasoning, not a disembodied summary.

- **Every edge has a note field explaining the relationship.** "contradicts" with no note is useless. The note should make the relationship intelligible to a non-technical reader: "Used to believe X because Y, now believe Z because new evidence W contradicted Y."

- **Revision events are captured.** When a source shows belief updating ("I thought X, but now realize Y because of Z"), extract this as two nodes (old, new) linked by contradicts with a note. This is the highest-signal content in any personal corpus.

**Anti-pattern:** Dense passages of reasoning extracted as a single concept node. A 400-word reflection on leadership failure should produce at least 3 nodes (old self-model, new self-model, supporting evidence concept) linked by edges showing the revision sequence.

---

## Section 5: Implementation Notes

### Schema

**nodes table**
```sql
id UUID PRIMARY KEY
label TEXT                -- node label/summary
content TEXT              -- full reasoning text
node_type TEXT            -- concept | question | decision | tension | project
embedding VECTOR(1024)    -- from Voyage AI
confidence FLOAT          -- 0.0–1.0, starts at 0.5, updated by recurrence and contradiction
source_id UUID            -- which source this was extracted from
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

**edges table**
```sql
from_node_id UUID REFERENCES nodes(id)
to_node_id UUID REFERENCES nodes(id)
relationship TEXT         -- unresolved_tension | contradicts | depends_on | partially_answers | supports | extends
note TEXT                 -- REQUIRED for unresolved_tension and contradicts; strongly recommended for others
weight FLOAT              -- priority ordering: 0–5 (automatically set by relationship type)
valid_from TIMESTAMPTZ    -- when this edge became true (for contradicts edges showing belief revision)
expired_at TIMESTAMPTZ    -- when this edge stopped being true (for superseded beliefs)
created_at TIMESTAMPTZ
```

**Retrieval algorithm (from ARCH-015)**

1. Take a query, embed it, search for top-5 vector-similar nodes
2. For each seed node, expand via one-hop edges in priority order
3. Return up to 15 nodes total, sorted by edge priority
4. Inject into context with note fields for explanation

This ordering ensures synthesis receives a subgraph biased toward unresolved thinking.

### Contradiction Detection (Tier 1 Evaluation, Phase 4A)

When new content is ingested, run a zero-LLM check:

1. Embed new segment
2. Find similar graph nodes (cosine similarity > 0.75)
3. Check for negation/opposition signals in text: "not", "wrong", "actually", "changed my mind", "I used to think"
4. If detected → flag for Tier 2 conflict resolution (one Haiku call to determine if it's a revision or a held tension)

This is free (Supabase query + text heuristic, no LLM).

### Recurrence Detection (Tier 1 Evaluation, Phase 4A)

When new content is ingested, run a zero-LLM check:

1. Embed new segment
2. Query segments table for similar content (cosine similarity > 0.85) from DIFFERENT sources
3. If found from 3+ sources across 2+ weeks → flag as recurring pattern
4. When threshold met → trigger Tier 2 promotion (one Haiku call to generate node label and classify type)

This is free (Supabase query only, no LLM).

### Model-Agnostic Design

The vocabulary is model-agnostic. It works with:
- Claude (native context windows, MCP integration)
- ChatGPT (via API)
- Cursor (MCP support)
- Any LLM with graph traversal capability

The specification defines the *structure* of reasoning relationships, not how a specific model consumes them. Different models may weight edges differently in their retrieval logic; the vocabulary supports that variation.

---

## Section 6: Example Graph Fragment

Here is a realistic graph extracted from a personal reflection on memory architecture:

**Nodes:**

```
Node A: concept
label: "Passive capture is not sufficient"
content: "I've concluded that accumulating raw data passively — notes, messages, emails —
           is not enough. The system must evaluate and classify content by epistemic type
           (fragment vs ideation vs processed reflection)."
confidence: 0.85
source: reflection-2026-03-22

Node B: concept
label: "Processed reflections carry highest signal"
content: "A 400-word reflection showing belief revision (evidence → new model → action)
         is orders of magnitude more informative than 100 fragment saves on the same topic."
confidence: 0.9
source: reflection-2026-03-22

Node C: tension
label: "Engine-first vs distribution-first"
content: "Engine work is critical for quality. Distribution is critical for reach.
         The product has neither if constraints conflict. Unclear which is blocking."
confidence: 0.7
source: decision-log-2026-03-20

Node D: decision
label: "Supabase only, no separate vector DB"
confidence: 0.95
source: architecture-2026-03-15

Node E: question
label: "Does epistemic edge typing generalize beyond my corpus?"
content: "Built for personal knowledge work. Will it work for other users who don't
         write extensively? Will tension surfacing be valuable to someone with fewer
         processed reflections?"
confidence: 0.4
source: open-questions-2026-03-21

Node F: project
label: "Build MIKAI MCP server"
confidence: 0.95
source: build-log-2026-03-19
```

**Edges:**

```
A → B: supports
note: "Passive capture is insufficient because processed reflections (Node B)
       should have higher weight. Node A explains why differentiation matters;
       Node B shows what to differentiate."

B → D: supports
note: "High-signal processed reflections must be stored and retrieved efficiently.
       Node D (Supabase-only) enables this by simplifying the stack. Node B
       justifies the architectural choice."

C ← → B: unresolved_tension
note: "Engine quality (realized through careful extraction, Node B) and distribution
      reach (constraint from Node C) are both essential. Unclear which constraint
      is blocking; held as active tension without resolution."

D → E: partially_answers
note: "Node D (Supabase architecture) is partially an answer to Node E
      (generalization question). Supabase can scale to other users, but the
      extraction prompt was tuned on Brian's corpus — doesn't fully answer
      generalization yet."

F → D: depends_on
note: "MCP server implementation (Node F) depends on settled architecture
      (Node D). Can't build the server until the storage layer is committed."

A → F: supports
note: "Epistemic edge typing (derived from Node A's insight about content
      differentiation) powers the MCP tools. Node A provides the conceptual
      foundation for Node F's feature set."
```

This fragment shows:
- Tensions surfaced explicitly (C), not papered over
- Revision signals captured (edges with temporal metadata)
- Supporting reasoning chains visible (A → B → D)
- Open questions preserved (E), not resolved prematurely
- Project grounded in conceptual work (A → F)

---

## Section 7: For Other Systems Adopting This Vocabulary

The epistemic edge vocabulary is designed for adoption. If you are building a memory system:

1. **Copy the node types and edge types as-is.** They are semantically precise and cover the reasoning relationships that matter.

2. **Implement edge priority ordering in your retrieval logic.** The ordering (unresolved_tension → contradicts → depends_on → partially_answers → supports → extends) is not arbitrary; it's a hypothesis about which relationships carry the most signal. Test this on your user base.

3. **Require note fields for unresolved_tension and contradicts edges.** These are the highest-priority relationships and need explanation. For lower-priority edges, notes are strongly recommended but can be auto-generated.

4. **Add temporal columns (valid_from, expired_at) to your edges table.** This is the minimal schema change needed to track belief revision without losing history.

5. **Run Tier 1 checks (recurrence and contradiction detection) without LLM calls.** These checks are free (vector similarity + heuristics). They feed higher-tier decisions and reduce LLM cost significantly.

6. **Bias your synthesis prompts toward tensions.** If you instruct your LLM to "surface and clarify tensions rather than paper over them," you will get better reasoning outputs from identical data.

If you adopt or extend this vocabulary, please document what worked and what didn't. The memory infrastructure space is young; evidence about what reasoning relationships matter will improve all systems.

---

**Version History**

- **v1.0 (March 2026):** Initial specification. Defines 5 node types, 6 edge types, priority ordering, extraction quality standard, and implementation notes. Open for adoption.

**Contributing**

This is an open specification. If you are using it, implementing it, or extending it, please share:
- Edge types you've added and why
- Node types you've removed or renamed
- Retrieval algorithms that worked better than edge priority ordering
- Evaluation methodologies for extraction quality

Contact: inquiries welcome at MIKAI's public channels.
