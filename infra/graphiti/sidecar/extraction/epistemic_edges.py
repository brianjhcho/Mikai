"""
Shared epistemic edge vocabulary for L3 typed extraction.

These six edge types model the epistemic relationships between extracted entities
that L4 can query directly — e.g. "find all UNRESOLVED_TENSION edges connected
to any Project node with confidence > 0.6".  Every edge type carries a
`confidence` float (0.0–1.0) produced by the extraction LLM.

The constants EDGE_TYPES and EDGE_TYPE_MAP are consumed by the add_episode()
call sites in sync.py / mcp_tools.py to constrain extraction at ingest time.
"""

from pydantic import BaseModel, Field


class CONTRADICTS(BaseModel):
    """Fact A contradicts fact B — they cannot both be true."""

    confidence: float = Field(ge=0.0, le=1.0, description="Confidence that the contradiction holds (0–1).")
    explanation: str = Field(default="", description="Brief explanation of what specifically conflicts.")


class SUPPORTS(BaseModel):
    """Fact A provides evidence for or corroborates fact B."""

    confidence: float = Field(ge=0.0, le=1.0, description="Confidence that the support relationship holds (0–1).")
    explanation: str = Field(default="", description="Brief explanation of how A supports B.")


class DEPENDS_ON(BaseModel):
    """Entity/fact A is contingent on entity/fact B being true or completed."""

    confidence: float = Field(ge=0.0, le=1.0, description="Confidence that the dependency holds (0–1).")
    explanation: str = Field(default="", description="Brief explanation of the dependency relationship.")


class PARTIALLY_ANSWERS(BaseModel):
    """Entity/fact A provides a partial answer to question or concern B."""

    confidence: float = Field(ge=0.0, le=1.0, description="Confidence that A meaningfully addresses B (0–1).")
    explanation: str = Field(default="", description="Brief explanation of what part of B is answered.")


class UNRESOLVED_TENSION(BaseModel):
    """A and B sit in tension with each other and no resolution has been reached yet."""

    confidence: float = Field(ge=0.0, le=1.0, description="Confidence that the tension is real and unresolved (0–1).")
    explanation: str = Field(default="", description="Brief description of the nature of the tension.")


class EXTENDS(BaseModel):
    """Entity/fact A elaborates, expands, or refines entity/fact B."""

    confidence: float = Field(ge=0.0, le=1.0, description="Confidence that A meaningfully extends B (0–1).")
    explanation: str = Field(default="", description="Brief explanation of how A extends B.")


# Canonical dict consumed by add_episode(edge_types=...) — keys are the string
# names Graphiti uses to label edges in Neo4j.
EDGE_TYPES: dict[str, type[BaseModel]] = {
    "CONTRADICTS": CONTRADICTS,
    "SUPPORTS": SUPPORTS,
    "DEPENDS_ON": DEPENDS_ON,
    "PARTIALLY_ANSWERS": PARTIALLY_ANSWERS,
    "UNRESOLVED_TENSION": UNRESOLVED_TENSION,
    "EXTENDS": EXTENDS,
}
