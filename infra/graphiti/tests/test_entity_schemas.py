"""
Tests for source-conditional Pydantic entity_types schemas (Stage 6, Stream A).

Assertions:
- Each source module exports ENTITY_TYPES: dict[str, type[BaseModel]].
- Shared connector types (Person, Place, Project, Concept) are present where
  applicable to each source.
- Entity count is between 5 and 15 per source.
- All entity type values are BaseModel subclasses.
- Shared connector types across sources are the SAME class objects (imported
  from common), ensuring Graphiti's resolution merges cross-source entities.
"""

import importlib

import pytest
from pydantic import BaseModel

# ── helpers ──────────────────────────────────────────────────────────────────

SOURCES = [
    "sidecar.extraction.claude_thread",
    "sidecar.extraction.apple_note",
    "sidecar.extraction.gmail_message",
    "sidecar.extraction.whatsapp_day",
]

SHARED_CONNECTORS = ["Person", "Place", "Project", "Concept"]

# All four sources include all four shared connector types.
SOURCE_CONNECTORS: dict[str, list[str]] = {
    "sidecar.extraction.claude_thread": ["Person", "Place", "Project", "Concept"],
    "sidecar.extraction.apple_note": ["Person", "Place", "Project", "Concept"],
    "sidecar.extraction.gmail_message": ["Person", "Place", "Project", "Concept"],
    "sidecar.extraction.whatsapp_day": ["Person", "Place", "Project", "Concept"],
}


def load_entity_types(module_path: str) -> dict[str, type[BaseModel]]:
    mod = importlib.import_module(module_path)
    assert hasattr(mod, "ENTITY_TYPES"), f"{module_path} must export ENTITY_TYPES"
    return mod.ENTITY_TYPES  # type: ignore[return-value]


# ── parametrised tests ────────────────────────────────────────────────────────

@pytest.mark.parametrize("module_path", SOURCES)
def test_entity_types_exported(module_path: str) -> None:
    et = load_entity_types(module_path)
    assert isinstance(et, dict), "ENTITY_TYPES must be a dict"


@pytest.mark.parametrize("module_path", SOURCES)
def test_entity_types_count(module_path: str) -> None:
    et = load_entity_types(module_path)
    count = len(et)
    assert 5 <= count <= 15, (
        f"{module_path} has {count} entity types; expected 5–15"
    )


@pytest.mark.parametrize("module_path", SOURCES)
def test_all_values_are_basemodel_subclasses(module_path: str) -> None:
    et = load_entity_types(module_path)
    for type_name, cls in et.items():
        assert isinstance(cls, type) and issubclass(cls, BaseModel), (
            f"{module_path}.ENTITY_TYPES['{type_name}'] is not a BaseModel subclass"
        )


@pytest.mark.parametrize("module_path", SOURCES)
def test_shared_connectors_present(module_path: str) -> None:
    et = load_entity_types(module_path)
    required = SOURCE_CONNECTORS[module_path]
    for connector in required:
        assert connector in et, (
            f"{module_path} is missing shared connector '{connector}'"
        )


def test_shared_connectors_are_identical_classes() -> None:
    """Person/Place/Project/Concept must be the SAME class object across all sources."""
    from sidecar.extraction.common import (
        Concept,
        Person,
        Place,
        Project,
    )

    canonical = {"Person": Person, "Place": Place, "Project": Project, "Concept": Concept}

    for module_path in SOURCES:
        et = load_entity_types(module_path)
        for connector, canonical_cls in canonical.items():
            if connector in et:
                assert et[connector] is canonical_cls, (
                    f"{module_path}.ENTITY_TYPES['{connector}'] is not the same "
                    f"class as common.{connector} — Graphiti resolution will fail "
                    f"to merge cross-source entities"
                )


def test_no_reserved_field_names() -> None:
    """Entity type models must not define fields that collide with EntityNode fields."""
    reserved = {"uuid", "name", "group_id", "created_at"}
    for module_path in SOURCES:
        et = load_entity_types(module_path)
        for type_name, cls in et.items():
            fields = set(cls.model_fields.keys())
            collisions = fields & reserved
            assert not collisions, (
                f"{module_path}.{type_name} defines reserved field(s): {collisions}"
            )
