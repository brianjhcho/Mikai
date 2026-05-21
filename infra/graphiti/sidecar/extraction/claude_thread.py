"""
Entity types for Claude conversation threads.

Claude threads contain rich technical context: code, tool invocations, decisions,
questions, errors, and references to files or external sources.  This schema
captures the full breadth of that content while keeping shared connector types
(Person, Place, Project, Concept) identical to other sources so Graphiti's
entity resolution merges cross-source references correctly.
"""

from pydantic import BaseModel, Field

from .common import Concept, Person, Place, Project


class Tool(BaseModel):
    """A software tool, CLI, or service invoked or discussed in the conversation."""

    summary: str = Field(description="What this tool does and how it was used in this context.")


class Library(BaseModel):
    """A software library, framework, or SDK referenced or used."""

    summary: str = Field(description="What this library provides and why it is relevant here.")


class Decision(BaseModel):
    """A design or implementation choice that was reached during the conversation."""

    summary: str = Field(description="What was decided and the key rationale behind it.")


class Question(BaseModel):
    """An open question or unresolved problem surfaced during the conversation."""

    summary: str = Field(description="The question as stated, and any context about why it matters.")


class FilePath(BaseModel):
    """A file or directory path referenced in the conversation."""

    summary: str = Field(description="What this file/directory is and why it was mentioned.")


class Command(BaseModel):
    """A shell command, script invocation, or terminal operation discussed or executed."""

    summary: str = Field(description="What this command does and the outcome or intent.")


class ErrorMessage(BaseModel):
    """A specific error, exception, or failure output referenced in the conversation."""

    summary: str = Field(description="The error text or type and what caused or resolved it.")


class Source(BaseModel):
    """An external reference, URL, documentation page, or citation brought into the thread."""

    summary: str = Field(description="What this source is and what it contributed to the discussion.")


# Canonical dict consumed by add_episode(entity_types=...).
# Keys are the string labels Graphiti stamps on nodes in Neo4j.
ENTITY_TYPES: dict[str, type[BaseModel]] = {
    "Person": Person,
    "Place": Place,
    "Project": Project,
    "Concept": Concept,
    "Tool": Tool,
    "Library": Library,
    "Decision": Decision,
    "Question": Question,
    "FilePath": FilePath,
    "Command": Command,
    "ErrorMessage": ErrorMessage,
    "Source": Source,
}
