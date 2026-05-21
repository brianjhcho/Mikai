"""
Shared edge_type_map for L3 typed extraction.

EDGE_TYPE_MAP constrains which epistemic edge types may connect which entity type
pairs at extraction time.  Keys are (source_entity_type_name, target_entity_type_name)
tuples; values are lists of allowed edge type name strings that must appear in
EDGE_TYPES from epistemic_edges.py.

Design notes:
- Be deliberate, not exhaustive.  Fewer allowed pairings means the LLM is forced
  to be precise; a free-for-all produces noisy edges that degrade L4 queries.
- All 6 epistemic edge names are strings matching the keys in EDGE_TYPES.
- L4's primary query ("UNRESOLVED_TENSION edges on Project nodes") is satisfied
  by the (Project, Decision), (Project, Concept), and (Concept, Concept) rows.
"""

EDGE_TYPE_MAP: dict[tuple[str, str], list[str]] = {
    # Questions resolved (or partially) by decisions
    ("Question", "Decision"): ["PARTIALLY_ANSWERS"],
    ("Question", "Concept"): ["PARTIALLY_ANSWERS", "EXTENDS"],
    ("Question", "Idea"): ["PARTIALLY_ANSWERS"],

    # Decisions relating to other decisions
    ("Decision", "Decision"): ["CONTRADICTS", "SUPPORTS", "EXTENDS"],

    # Decisions depending on or extending projects / concepts
    ("Decision", "Project"): ["DEPENDS_ON"],
    ("Decision", "Concept"): ["DEPENDS_ON", "EXTENDS"],

    # Concepts relating to other concepts
    ("Concept", "Concept"): ["CONTRADICTS", "SUPPORTS", "EXTENDS", "UNRESOLVED_TENSION"],
    ("Concept", "Question"): ["UNRESOLVED_TENSION"],
    ("Concept", "Decision"): ["SUPPORTS", "CONTRADICTS"],

    # Projects depending on or in tension with decisions / concepts
    ("Project", "Decision"): ["DEPENDS_ON", "UNRESOLVED_TENSION"],
    ("Project", "Concept"): ["DEPENDS_ON", "UNRESOLVED_TENSION"],
    ("Project", "Project"): ["DEPENDS_ON", "EXTENDS"],

    # Action items and plans depending on decisions
    ("ActionItem", "Decision"): ["DEPENDS_ON"],
    ("ActionItem", "Project"): ["DEPENDS_ON"],
    ("Plan", "Decision"): ["DEPENDS_ON"],
    ("Plan", "Project"): ["DEPENDS_ON"],

    # Concerns surfacing tensions
    ("Concern", "Project"): ["UNRESOLVED_TENSION"],
    ("Concern", "Decision"): ["UNRESOLVED_TENSION", "CONTRADICTS"],
    ("Concern", "Concept"): ["UNRESOLVED_TENSION"],

    # Ideas extending or supporting concepts / decisions
    ("Idea", "Concept"): ["EXTENDS", "SUPPORTS", "CONTRADICTS"],
    ("Idea", "Decision"): ["SUPPORTS", "CONTRADICTS"],
    ("Idea", "Project"): ["EXTENDS"],

    # Tools / libraries depending on projects / concepts
    ("Tool", "Project"): ["DEPENDS_ON"],
    ("Library", "Project"): ["DEPENDS_ON"],
    ("Tool", "Concept"): ["EXTENDS"],
    ("Library", "Concept"): ["EXTENDS"],

    # Sources supporting decisions / concepts
    ("Source", "Decision"): ["SUPPORTS", "CONTRADICTS"],
    ("Source", "Concept"): ["SUPPORTS", "EXTENDS"],
    ("Document", "Decision"): ["SUPPORTS"],
    ("Document", "Project"): ["DEPENDS_ON"],
}
