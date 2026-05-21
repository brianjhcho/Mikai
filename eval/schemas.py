"""
eval/schemas.py — Pydantic models for the Stage-6 eval JSONL files.

Two JSONL formats:
  eval/labeled_entities.jsonl  — one EntityCandidate per line
  eval/labeled_edges.jsonl     — one EdgeCandidate per line

`is_valid` is always written as null by the candidate seeder.
Only Brian's labeling tool sets it to true/false.

Entity types listed in KNOWN_ENTITY_TYPES will be extended once worker-schemas
lands the source-conditional Pydantic files under
infra/graphiti/sidecar/extraction/. Until then this list covers the
common.py types plus the obvious domain types for MIKAI's four source
categories.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Known entity types (updated once extraction/ schemas land) ───────────────
#
# These match the class names Graphiti will store in the `label` field of
# entity nodes.  Keep in sync with extraction/common.py and the four
# source-specific modules once they exist.

KNOWN_ENTITY_TYPES: list[str] = [
    # common.py — shared across all sources
    "Person",
    "Place",
    "Project",
    "Concept",
    # claude_thread.py
    "Tool",
    "Library",
    "Decision",
    "Question",
    "FilePath",
    "Command",
    "ErrorMessage",
    "Source",
    # apple_note.py — note: Decision/Question/Event overlap with other sources;
    # Graphiti merges nodes by class identity so shared names must use shared classes.
    "Idea",
    "Event",
    # gmail_message.py
    "Organization",
    "Meeting",
    "ActionItem",
    "Document",
    # whatsapp_day.py
    "Plan",
    "Concern",
]

# ── Epistemic edge types (mirrors extraction/epistemic_edges.py) ──────────────

KNOWN_EDGE_TYPES: list[str] = [
    "CONTRADICTS",
    "SUPPORTS",
    "DEPENDS_ON",
    "PARTIALLY_ANSWERS",
    "UNRESOLVED_TENSION",
    "EXTENDS",
    # generic Graphiti-emitted relationship type (catch-all for non-epistemic edges)
    "RELATES_TO",
]

# ── Source tags ───────────────────────────────────────────────────────────────

SourceTag = Literal[
    "claude_thread",
    "apple_note",
    "gmail_message",
    "whatsapp_day",
    "unknown",
]


# ── Entity candidate record ───────────────────────────────────────────────────


class EntityCandidate(BaseModel):
    """One row in eval/labeled_entities.jsonl.

    Populated by eval/seed_candidates.py; labeled by eval/label.py.
    """

    # Graph identifiers
    node_uuid: str = Field(description="UUID of the entity node in Neo4j.")
    entity_type: str = Field(
        description="The Pydantic type label (e.g. 'Person', 'Decision')."
    )

    # Human-readable content shown during labeling
    name: str = Field(description="Display name of the extracted entity.")
    summary: str = Field(description="Summary field stored on the node.")
    source_excerpt: str = Field(
        description=(
            "The episode body text from which this entity was extracted. "
            "Shown verbatim to the labeler so they can judge correctness."
        )
    )
    source_tag: SourceTag = Field(
        default="unknown",
        description="Which ingestion source produced this episode.",
    )
    episode_uuid: str = Field(
        default="",
        description="UUID of the originating episode (for traceability).",
    )

    # Eval fields — seeder writes null; labeler writes true/false
    is_valid: bool | None = Field(
        default=None,
        description=(
            "True if the entity is correctly typed and factually accurate. "
            "False if it is garbage, mis-typed, or hallucinatory. "
            "Null means not yet labeled."
        ),
    )
    label_note: str = Field(
        default="",
        description="Optional free-text comment from the labeler.",
    )


# ── Edge candidate record ─────────────────────────────────────────────────────


class EdgeCandidate(BaseModel):
    """One row in eval/labeled_edges.jsonl.

    Populated by eval/seed_candidates.py; labeled by eval/label.py.
    """

    # Graph identifiers
    edge_uuid: str = Field(description="UUID of the edge in Neo4j.")
    edge_type: str = Field(
        description="The relationship label (e.g. 'CONTRADICTS', 'DEPENDS_ON')."
    )

    # Node endpoints shown during labeling
    source_name: str = Field(description="Display name of the head (source) entity.")
    source_type: str = Field(description="Entity type of the head node.")
    target_name: str = Field(description="Display name of the tail (target) entity.")
    target_type: str = Field(description="Entity type of the tail node.")

    # Edge payload
    fact: str = Field(
        description=(
            "The Graphiti-generated fact sentence describing this edge. "
            "Shown to the labeler as the primary judgment surface."
        )
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence score on the edge (0.0–1.0), if present.",
    )
    source_excerpt: str = Field(
        default="",
        description="Episode body excerpt that produced this edge.",
    )
    source_tag: SourceTag = Field(default="unknown")
    episode_uuid: str = Field(default="")

    # Eval fields
    is_valid: bool | None = Field(
        default=None,
        description=(
            "True if the edge type is correct and the fact is accurate. "
            "False if the relationship is wrong, the edge type is misapplied, "
            "or the fact is garbled. Null means not yet labeled."
        ),
    )
    label_note: str = Field(default="")


# ── Helpers ───────────────────────────────────────────────────────────────────


def load_entity_jsonl(path: str) -> list[EntityCandidate]:
    """Load all records from a labeled_entities.jsonl file."""
    import json
    from pathlib import Path

    records: list[EntityCandidate] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            records.append(EntityCandidate.model_validate(json.loads(line)))
    return records


def load_edge_jsonl(path: str) -> list[EdgeCandidate]:
    """Load all records from a labeled_edges.jsonl file."""
    import json
    from pathlib import Path

    records: list[EdgeCandidate] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            records.append(EdgeCandidate.model_validate(json.loads(line)))
    return records
