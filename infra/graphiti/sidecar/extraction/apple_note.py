"""
Entity types for Apple Notes content.

Apple Notes are personal, reflective prose — the noisiest source in the graph.
This schema is deliberately conservative (6 types) to minimise garbage extraction.
Shared connector types (Person, Place, Project, Concept) are imported from common
so cross-source entity resolution works correctly.
"""

from pydantic import BaseModel, Field

from .common import Concept, Person, Place, Project


class Decision(BaseModel):
    """A choice or commitment the author recorded in their notes."""

    summary: str = Field(description="What was decided and any noted rationale.")


class Idea(BaseModel):
    """A nascent thought, hypothesis, or possibility the author is exploring."""

    summary: str = Field(description="The idea as captured and any initial reactions to it.")


class Question(BaseModel):
    """An open question the author is sitting with or wants to investigate."""

    summary: str = Field(description="The question and any context about its importance.")


class Event(BaseModel):
    """A specific dated or dateable happening referenced in the note."""

    summary: str = Field(description="What happened, when, and its significance.")


# Canonical dict consumed by add_episode(entity_types=...).
ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "Person": Person,
    "Place": Place,
    "Project": Project,
    "Concept": Concept,
    "Decision": Decision,
    "Idea": Idea,
    "Question": Question,
    "Event": Event,
}
