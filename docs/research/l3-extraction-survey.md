# L3 Memory Architectures: Extraction Survey

This survey compares four production L3 (long-term memory layer) architectures to ground the decisions in D-049 (source-conditional Pydantic extraction, no second pass).

## Mem0

**Architecture:** Two-pass extraction with edit-resolution gate. Episode → (1) LLM extract facts, (2) LLM classify each fact as ADD (new), UPDATE (refine existing), DELETE (resolved), or NOOP (ignore). Each class triggers a different write path. Negatives are paired with positives in the extraction prompt ("capture meeting notes about Q2 budget, but NOT generic setup preamble").

**Benchmarks:** LOCOMO on short-horizon Q&A (F1=38.72 single-hop, J=67.13 BLEU). Designed for conversational agent memory in chatbot contexts.

**What we copy:** Negative-example few-shot pairing in the extraction prompt. Mem0's docs demonstrate that pairing one positive example ("this is a meeting decision") with one negative ("this is meeting preamble") cuts false-positive-dense noise by ~20% relative to positive-only prompts.

**What we don't copy:** The ADD/UPDATE/DELETE/NOOP second pass. Graphiti's native entity resolution + bitemporal invalidation (valid_from, expired_at) already handle dedup and contradiction semantically. Replicating Mem0's gate would add LLM cost and latency without manufacturer-supported benefit. Each class (ADD, UPDATE, DELETE) requires a separate LLM invocation; we get the same structural outcome (marked-resolved nodes, entity merging) from Graphiti's resolution + our confidence scoring.

**References:**
- [Mem0 architecture overview](https://docs.mem0.ai/platform/memory-types)
- [LOCOMO benchmark](https://arxiv.org/abs/2404.19057)

---

## Cognee

**Architecture:** Pydantic schema-validated extraction with optional OWL ontology layer. Episodes are parsed via Instructor (LLM output validation), producing strongly-typed nodes and edges. Optionally, an OWL (Web Ontology Language) classifier validates nodes against a domain ontology with 80% fuzzy matching — rejects nodes that don't fit the schema.

**What we copy:** Source-conditional Pydantic schemas for entity types. Cognee's lesson is that schemas should vary by source (email threads have different entity types than calendar events; Claude threads have different entities than browser history). This drives ARCH-024 / ARCH-025: each adapter defines source-specific schemas, not one global schema.

**What we don't copy:** OWL ontology validation layer. Pydantic validation is sufficient — if a node doesn't conform to our source-conditional `EmailThread.entity_types`, it fails validation at extraction time. We don't need a separate OWL layer to achieve "typed extraction." Pydantic is the manufacturer-supported equivalent.

**References:**
- [Cognee architecture](https://github.com/topoteretes/cognee)
- [Instructor for LLM-validated outputs](https://github.com/jxnl/instructor)

---

## Letta / MemGPT

**Architecture:** Self-editing memory blocks via tool calls. During agent runtime, the agent can call `save_to_memory(content)`, `update_memory(id, new_content)`, `delete_memory(id)`. These are deterministic tool invocations, not LLM classifications. The agent reasons about which memory to edit as part of its reasoning loop.

**What we copy:** Nothing for L3. Letta's self-editing is an L4 pattern (the reasoning layer that decides what to remember and when). L4 uses the same principle — write tools like `mark_resolved(node_id)` from conversation — but applied at the synthesis layer, not the extraction layer.

**Why it's not L3:** Self-editing requires a reasoning loop (agent decides to call the tool, then the tool executes). L3 extraction is deterministic — given an episode, produce typed nodes and edges. The two concerns are separate.

**References:**
- [Letta memory architecture](https://docs.letta.com/memory/agent-memory)

---

## Honcho

**Architecture:** Extract explicit claims + deductive conclusions separately. Explicit: LLM produces facts directly stated in the episode. Deductive: LLM reasons about implicit conclusions ("user asked about budget three times → likely budget is a priority"). Both are stored as nodes. Edges carry confidence scores reflecting the chain-of-reasoning depth — explicit facts score 1.0, single-step deductions 0.7, multi-step 0.4.

**What we copy:** Confidence scoring on edges. Honcho's model is that edge confidence reflects reasoning depth, not just semantic similarity. We adopt this: extraction produces `confidence: float` on every epistemic edge (CONTRADICTS, SUPPORTS, DEPENDS_ON, etc.), where confidence reflects the extraction model's certainty about the relationship.

**What we don't copy:** Explicit vs. deductive node split at extraction time. We do distinguish between them, but via source type (Track A = authored content where explicit/deductive is meaningful; Track B = behavioral traces where the pattern itself is the signal). We don't need a separate LLM pass to classify nodes as "this was explicit vs. deduced."

**References:**
- [Honcho architecture](https://github.com/plastic-labs/honcho)

---

## D-049 Synthesis

MIKAI's Stage 6 approach combines three proven patterns:

1. **From Mem0:** Negative-example few-shot augmentation in the extraction prompt. Paired POSITIVE + NEGATIVE examples cut extraction noise by ~20%.
2. **From Cognee:** Source-conditional Pydantic schemas. Entity types vary by source (Claude threads, Apple Notes, Gmail, WhatsApp) — not a global fixed taxonomy.
3. **From Honcho:** Confidence scoring on epistemic edges. Each edge carries confidence reflecting the extraction model's certainty.

We deliberately do NOT copy:
- Mem0's ADD/UPDATE/DELETE/NOOP second LLM pass (Graphiti's entity resolution + bitemporal invalidation already cover this semantically).
- Cognee's OWL ontology layer (Pydantic validation is sufficient).
- Letta's self-editing loop (that's L4 synthesis, not L3 extraction).

The result is deterministic typed extraction at inference time, with no second-pass cost, no post-hoc projection layer, and no LLM-based gate. Graphiti's native `add_episode(entity_types=, edge_types=, edge_type_map=)` parameters drive the typing directly.
