"""
extraction — source-conditional Pydantic schemas for L3 typed extraction.

Public re-exports used by add_episode() call sites:

    from extraction import (
        ENTITY_TYPES_BY_SOURCE,
        EDGE_TYPES,
        EDGE_TYPE_MAP,
    )

`ENTITY_TYPES_BY_SOURCE` maps the source_type string (matching the values used
in sync.py / mcp_tools.py) to the per-source entity_types dict.
"""

from .apple_note import ENTITY_TYPES as _APPLE_NOTE_ENTITY_TYPES
from .claude_thread import ENTITY_TYPES as _CLAUDE_THREAD_ENTITY_TYPES
from .common import Concept, Person, Place, Project
from .edge_type_map import EDGE_TYPE_MAP
from .epistemic_edges import EDGE_TYPES
from .gmail_message import ENTITY_TYPES as _GMAIL_MESSAGE_ENTITY_TYPES
from .whatsapp_day import ENTITY_TYPES as _WHATSAPP_DAY_ENTITY_TYPES

ENTITY_TYPES_BY_SOURCE: dict[str, dict[str, type]] = {
    "claude_thread": _CLAUDE_THREAD_ENTITY_TYPES,
    "apple_note": _APPLE_NOTE_ENTITY_TYPES,
    "gmail_message": _GMAIL_MESSAGE_ENTITY_TYPES,
    "whatsapp_day": _WHATSAPP_DAY_ENTITY_TYPES,
}

__all__ = [
    "ENTITY_TYPES_BY_SOURCE",
    "EDGE_TYPES",
    "EDGE_TYPE_MAP",
    "Person",
    "Place",
    "Project",
    "Concept",
]
