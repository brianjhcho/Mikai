"""Source-conditional extraction parameter router.

Maps a source_description string to the entity_types dict for that source,
and provides the shared edge_types / edge_type_map / custom_extraction_instructions
that apply to every source.

Usage at add_episode() call sites::

    from sidecar.extraction.router import extraction_params_for

    params = extraction_params_for(source_description)
    result = await graphiti.add_episode(
        ...
        **params,
    )

The returned dict is safe to unpack directly into add_episode() — it only
contains keys that add_episode() accepts.

Source routing rules (order matches expected call-site labels):
  "apple-notes"          → apple_note ENTITY_TYPES
  "claude-code"          → claude_thread ENTITY_TYPES
  "gmail"                → gmail_message ENTITY_TYPES
  "mcp-gmail-import"     → gmail_message ENTITY_TYPES
  "whatsapp-day"         → whatsapp_day ENTITY_TYPES
  "whatsapp-daily"       → whatsapp_day ENTITY_TYPES
  anything else          → claude_thread ENTITY_TYPES (+ logged warning)

All sources share EDGE_TYPES, EDGE_TYPE_MAP, and the negative-example
custom_extraction_instructions assembled in prompt_negatives.py.
"""

import logging
import os
from typing import Any

from sidecar.extraction import EDGE_TYPE_MAP, EDGE_TYPES, ENTITY_TYPES_BY_SOURCE
from sidecar.extraction.prompt_negatives import get_custom_extraction_instructions

logger = logging.getLogger("mikai-graphiti")

# Canonical mapping from source_description prefix/exact values to the
# ENTITY_TYPES_BY_SOURCE key.  All comparisons are lower-cased.
_SOURCE_TO_KEY: dict[str, str] = {
    "apple-notes": "apple_note",
    "apple_notes": "apple_note",
    "claude-code": "claude_thread",
    "claude_code": "claude_thread",
    "claude-conversation": "claude_thread",
    "gmail": "gmail_message",
    "mcp-gmail-import": "gmail_message",
    "gmail-import": "gmail_message",
    "whatsapp-day": "whatsapp_day",
    "whatsapp-daily": "whatsapp_day",
    "whatsapp_day": "whatsapp_day",
    "whatsapp_daily": "whatsapp_day",
}

_DEFAULT_KEY = "claude_thread"

_CUSTOM_INSTRUCTIONS = get_custom_extraction_instructions()


def _resolve_key(source_description: str) -> str:
    """Return the ENTITY_TYPES_BY_SOURCE key for source_description.

    Strips leading/trailing whitespace and lowercases before lookup.
    Falls back to ``_DEFAULT_KEY`` with a warning if no match is found.
    """
    normalized = (source_description or "").strip().lower()
    if normalized in _SOURCE_TO_KEY:
        return _SOURCE_TO_KEY[normalized]

    # Prefix match: "apple-notes::My Note Title" → "apple_note"
    for prefix, key in _SOURCE_TO_KEY.items():
        if normalized.startswith(prefix):
            return key

    logger.warning(
        "extraction_router: unrecognised source_description=%r — "
        "falling back to claude_thread entity types",
        source_description,
    )
    return _DEFAULT_KEY


def extraction_params_for(source_description: str) -> dict[str, Any]:
    """Return the add_episode() typed-extraction kwargs for source_description.

    The returned dict contains exactly:
      entity_types                  — source-conditional Pydantic type dict
      edge_types                    — shared epistemic edge types
      edge_type_map                 — shared (src_type, tgt_type) → [edge_names]
      custom_extraction_instructions — negative-example prompt augmentation

    All keys are accepted by graphiti_core.Graphiti.add_episode() ≥ 0.7.

    Default is graphiti-core NATIVE extraction (returns {} — no custom kwargs).
    The Stage 6 typed extraction (custom entity_types + epistemic edge_types) is
    incompatible with graphiti-core 0.28.2's attribute persistence: 0.28.2 writes
    custom node/edge attributes as nested Neo4j Maps, which Neo4j rejects with
    `Property values can only be of primitive types`. Native extraction carries
    only primitive fields (name, summary, fact) and matches the freeform-graph
    L4 direction. Set MIKAI_TYPED_EXTRACTION=1 to revive Stage 6 (requires a
    graphiti-core version that persists custom attributes correctly).
    """
    if os.environ.get("MIKAI_TYPED_EXTRACTION", "").strip().lower() not in (
        "1", "true", "yes", "on"
    ):
        return {}
    key = _resolve_key(source_description)
    entity_types = ENTITY_TYPES_BY_SOURCE[key]
    return {
        "entity_types": entity_types,
        "edge_types": EDGE_TYPES,
        "edge_type_map": EDGE_TYPE_MAP,
        "custom_extraction_instructions": _CUSTOM_INSTRUCTIONS,
    }
