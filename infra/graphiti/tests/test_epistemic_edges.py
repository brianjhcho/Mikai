"""
Tests for epistemic edge types and edge_type_map (Stage 6, Stream B).

Assertions:
- EDGE_TYPES contains all 6 required edge type names.
- Every edge type is a BaseModel subclass with a `confidence` float field.
- EDGE_TYPE_MAP keys are 2-tuples of strings.
- Every string value in EDGE_TYPE_MAP appears as a key in EDGE_TYPES.
- No EDGE_TYPE_MAP value list is empty.
"""

import pytest
from pydantic import BaseModel

from sidecar.extraction.edge_type_map import EDGE_TYPE_MAP
from sidecar.extraction.epistemic_edges import EDGE_TYPES

REQUIRED_EDGE_TYPES = {
    "CONTRADICTS",
    "SUPPORTS",
    "DEPENDS_ON",
    "PARTIALLY_ANSWERS",
    "UNRESOLVED_TENSION",
    "EXTENDS",
}


def test_all_required_edge_types_present() -> None:
    assert REQUIRED_EDGE_TYPES.issubset(set(EDGE_TYPES.keys())), (
        f"Missing edge types: {REQUIRED_EDGE_TYPES - set(EDGE_TYPES.keys())}"
    )


def test_edge_types_count() -> None:
    assert len(EDGE_TYPES) == 6, f"Expected 6 edge types, got {len(EDGE_TYPES)}"


@pytest.mark.parametrize("edge_name", list(REQUIRED_EDGE_TYPES))
def test_edge_type_is_basemodel_subclass(edge_name: str) -> None:
    cls = EDGE_TYPES[edge_name]
    assert isinstance(cls, type) and issubclass(cls, BaseModel), (
        f"EDGE_TYPES['{edge_name}'] is not a BaseModel subclass"
    )


@pytest.mark.parametrize("edge_name", list(REQUIRED_EDGE_TYPES))
def test_edge_type_has_confidence_float(edge_name: str) -> None:
    cls = EDGE_TYPES[edge_name]
    fields = cls.model_fields
    assert "confidence" in fields, (
        f"EDGE_TYPES['{edge_name}'] is missing required 'confidence' field"
    )
    # Verify annotation resolves to float (handles Optional[float] too)
    annotation = fields["confidence"].annotation
    origin = getattr(annotation, "__origin__", None)
    if origin is not None:
        # e.g. Optional[float] → Union[float, None]
        args = annotation.__args__
        assert float in args, (
            f"EDGE_TYPES['{edge_name}'].confidence annotation {annotation} does not include float"
        )
    else:
        assert annotation is float, (
            f"EDGE_TYPES['{edge_name}'].confidence must be float, got {annotation}"
        )


def test_edge_type_map_keys_are_string_tuples() -> None:
    for key in EDGE_TYPE_MAP:
        assert isinstance(key, tuple) and len(key) == 2, (
            f"EDGE_TYPE_MAP key {key!r} is not a 2-tuple"
        )
        assert isinstance(key[0], str) and isinstance(key[1], str), (
            f"EDGE_TYPE_MAP key {key!r} elements must both be strings"
        )


def test_edge_type_map_values_are_nonempty_lists() -> None:
    for key, val in EDGE_TYPE_MAP.items():
        assert isinstance(val, list) and len(val) > 0, (
            f"EDGE_TYPE_MAP[{key!r}] must be a non-empty list, got {val!r}"
        )


def test_edge_type_map_values_reference_valid_edge_types() -> None:
    valid_names = set(EDGE_TYPES.keys())
    for key, val in EDGE_TYPE_MAP.items():
        for edge_name in val:
            assert isinstance(edge_name, str), (
                f"EDGE_TYPE_MAP[{key!r}] contains non-string value {edge_name!r}"
            )
            assert edge_name in valid_names, (
                f"EDGE_TYPE_MAP[{key!r}] references unknown edge type '{edge_name}'. "
                f"Valid: {sorted(valid_names)}"
            )
