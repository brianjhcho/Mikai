"""
Entity types for WhatsApp daily digest summaries.

WhatsApp digests are informal, conversational, and time-anchored to a single day.
The schema focuses on the interpersonal and logistical entities that typically
surface: people, places, plans, events, and concerns.  Shared connector types
(Person, Place, Project, Concept) are imported from common so cross-source
entity resolution works correctly.
"""

from pydantic import BaseModel, Field

from .common import Concept, Person, Place, Project


class Plan(BaseModel):
    """An intention or arrangement discussed that has not yet happened."""

    summary: str = Field(description="What is planned, who is involved, and when if mentioned.")


class Event(BaseModel):
    """Something that happened or is happening on this day."""

    summary: str = Field(description="What occurred, who was involved, and any notable outcome.")


class Decision(BaseModel):
    """A choice reached or communicated in the conversation."""

    summary: str = Field(description="What was decided and by whom.")


class Concern(BaseModel):
    """A worry, risk, or problem raised in the conversation."""

    summary: str = Field(description="The concern as stated and any proposed response.")


class Question(BaseModel):
    """An open question surfaced in the conversation."""

    summary: str = Field(description="The question and any context about why it came up.")


# Canonical dict consumed by add_episode(entity_types=...).
ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "Person": Person,
    "Place": Place,
    "Project": Project,
    "Concept": Concept,
    "Plan": Plan,
    "Event": Event,
    "Decision": Decision,
    "Concern": Concern,
    "Question": Question,
}
