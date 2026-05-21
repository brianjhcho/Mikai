"""
Entity types for Gmail messages.

Email carries structured business context: people, organisations, scheduled meetings,
action items, and documents.  Shared connector types (Person, Place, Project, Concept)
are imported from common so cross-source entity resolution works correctly.
"""

from pydantic import BaseModel, Field

from .common import Concept, Person, Place, Project


class Organization(BaseModel):
    """A company, institution, team, or named group referenced in the email."""

    summary: str = Field(description="What this organisation is and how it relates to the conversation.")


class Meeting(BaseModel):
    """A scheduled or proposed meeting, call, or synchronous event."""

    summary: str = Field(description="The meeting's purpose, participants, and timing if mentioned.")


class Decision(BaseModel):
    """A choice or agreement reached or communicated via email."""

    summary: str = Field(description="What was decided and who was party to it.")


class ActionItem(BaseModel):
    """A concrete task or follow-up committed to in the email thread."""

    summary: str = Field(description="What needs to be done, by whom, and by when if specified.")


class Document(BaseModel):
    """An attachment, linked file, or named document referenced in the email."""

    summary: str = Field(description="What this document contains and why it was shared.")


class Source(BaseModel):
    """An external URL, article, or reference shared in the email."""

    summary: str = Field(description="What this source is and what it contributes to the thread.")


# Canonical dict consumed by add_episode(entity_types=...).
ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "Person": Person,
    "Place": Place,
    "Project": Project,
    "Concept": Concept,
    "Organization": Organization,
    "Meeting": Meeting,
    "Decision": Decision,
    "ActionItem": ActionItem,
    "Document": Document,
    "Source": Source,
}
