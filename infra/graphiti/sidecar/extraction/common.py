"""
Shared entity types used across all extraction sources.

These classes MUST be imported (not redefined) in each source-specific module
so that Graphiti's entity resolution merges the same real-world entity regardless
of which source episode introduced it.  For example, "Martin" extracted from a
Claude thread and "Martin" extracted from a Gmail message will resolve to the
same graph node because both episodes used the same `Person` class.
"""

from pydantic import BaseModel, Field


class Person(BaseModel):
    """A human being referenced or involved in the content."""

    summary: str = Field(description="Brief description of who this person is and their role.")


class Place(BaseModel):
    """A physical or virtual location (city, building, URL, region)."""

    summary: str = Field(description="Brief description of this place and its relevance.")


class Project(BaseModel):
    """A named initiative, product, or body of work being tracked."""

    summary: str = Field(description="Brief description of the project's goal or current state.")


class Concept(BaseModel):
    """An abstract idea, framework, technique, or domain term worth tracking."""

    summary: str = Field(description="One-sentence explanation of what this concept means here.")
