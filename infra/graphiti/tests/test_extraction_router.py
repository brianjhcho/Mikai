"""Tests for sidecar/extraction/router.py.

The router maps source_description strings to per-source entity_types dicts
and injects the shared edge_types / edge_type_map / custom_extraction_instructions.
Tests cover all documented source labels, prefix matching, the fallback path,
and the shape of the returned dict.

No Graphiti connectivity required — all assertions are on Python objects.
"""

from __future__ import annotations

import logging

import pytest

from sidecar.extraction import EDGE_TYPE_MAP, EDGE_TYPES, ENTITY_TYPES_BY_SOURCE
from sidecar.extraction.router import extraction_params_for, _resolve_key


# ── _resolve_key ──────────────────────────────────────────────────────────────


class TestResolveKey:
    @pytest.mark.parametrize("desc,expected_key", [
        # Exact matches
        ("apple-notes",         "apple_note"),
        ("apple_notes",         "apple_note"),
        ("claude-code",         "claude_thread"),
        ("claude_code",         "claude_thread"),
        ("claude-conversation", "claude_thread"),
        ("gmail",               "gmail_message"),
        ("mcp-gmail-import",    "gmail_message"),
        ("gmail-import",        "gmail_message"),
        ("whatsapp-day",        "whatsapp_day"),
        ("whatsapp-daily",      "whatsapp_day"),
        ("whatsapp_day",        "whatsapp_day"),
        ("whatsapp_daily",      "whatsapp_day"),
        # Case-insensitive
        ("Apple-Notes",         "apple_note"),
        ("CLAUDE-CODE",         "claude_thread"),
        ("Gmail",               "gmail_message"),
        ("WhatsApp-Day",        "whatsapp_day"),
    ])
    def test_exact_and_case_insensitive(self, desc, expected_key):
        assert _resolve_key(desc) == expected_key

    @pytest.mark.parametrize("desc,expected_key", [
        # Prefix match — call sites use "source::detail" style names
        ("apple-notes::My Note Title", "apple_note"),
        ("claude-code::session.jsonl::user", "claude_thread"),
        ("gmail::thread-id-xyz", "gmail_message"),
        ("whatsapp-day::2026-05-21", "whatsapp_day"),
    ])
    def test_prefix_match(self, desc, expected_key):
        assert _resolve_key(desc) == expected_key

    def test_unknown_source_falls_back_to_claude_thread(self, caplog):
        with caplog.at_level(logging.WARNING, logger="mikai-graphiti"):
            key = _resolve_key("unknown-source-xyz")
        assert key == "claude_thread"
        assert "unrecognised source_description" in caplog.text

    def test_empty_string_falls_back_to_claude_thread(self, caplog):
        with caplog.at_level(logging.WARNING, logger="mikai-graphiti"):
            key = _resolve_key("")
        assert key == "claude_thread"

    def test_none_like_empty_string_handled(self):
        # None is coerced to empty string inside _resolve_key
        key = _resolve_key(None)  # type: ignore[arg-type]
        assert key == "claude_thread"

    def test_whitespace_stripped(self):
        assert _resolve_key("  apple-notes  ") == "apple_note"


# ── extraction_params_for ─────────────────────────────────────────────────────


class TestExtractionParamsFor:
    def _required_keys(self):
        return {"entity_types", "edge_types", "edge_type_map",
                "custom_extraction_instructions"}

    def test_returns_all_required_keys(self):
        params = extraction_params_for("apple-notes")
        assert self._required_keys() <= set(params.keys())

    def test_entity_types_matches_source(self):
        params = extraction_params_for("apple-notes")
        assert params["entity_types"] is ENTITY_TYPES_BY_SOURCE["apple_note"]

        params = extraction_params_for("claude-code")
        assert params["entity_types"] is ENTITY_TYPES_BY_SOURCE["claude_thread"]

        params = extraction_params_for("gmail")
        assert params["entity_types"] is ENTITY_TYPES_BY_SOURCE["gmail_message"]

        params = extraction_params_for("whatsapp-day")
        assert params["entity_types"] is ENTITY_TYPES_BY_SOURCE["whatsapp_day"]

    def test_edge_types_is_shared(self):
        p1 = extraction_params_for("apple-notes")
        p2 = extraction_params_for("gmail")
        assert p1["edge_types"] is EDGE_TYPES
        assert p2["edge_types"] is EDGE_TYPES

    def test_edge_type_map_is_shared(self):
        p1 = extraction_params_for("claude-code")
        p2 = extraction_params_for("whatsapp-day")
        assert p1["edge_type_map"] is EDGE_TYPE_MAP
        assert p2["edge_type_map"] is EDGE_TYPE_MAP

    def test_custom_instructions_is_a_non_empty_string(self):
        params = extraction_params_for("apple-notes")
        instructions = params["custom_extraction_instructions"]
        assert isinstance(instructions, str)
        assert len(instructions) > 0

    def test_custom_instructions_contains_negative_example_header(self):
        params = extraction_params_for("claude-code")
        assert "Do NOT extract" in params["custom_extraction_instructions"]

    def test_entity_types_dict_values_are_pydantic_models(self):
        from pydantic import BaseModel
        params = extraction_params_for("apple-notes")
        for name, cls in params["entity_types"].items():
            assert issubclass(cls, BaseModel), (
                f"entity_types[{name!r}] is not a Pydantic BaseModel subclass"
            )

    def test_entity_types_includes_shared_connectors(self):
        """Person/Place/Project/Concept must appear in every source's dict."""
        shared = {"Person", "Place", "Project", "Concept"}
        for desc in ("apple-notes", "claude-code", "gmail", "whatsapp-day"):
            params = extraction_params_for(desc)
            missing = shared - set(params["entity_types"].keys())
            assert not missing, (
                f"{desc!r} entity_types missing shared connector types: {missing}"
            )

    def test_params_safe_to_unpack_into_add_episode_kwargs(self):
        """The dict should only contain keys accepted by add_episode()."""
        accepted_kwargs = {
            "entity_types", "edge_types", "edge_type_map",
            "custom_extraction_instructions",
        }
        params = extraction_params_for("gmail")
        extra = set(params.keys()) - accepted_kwargs
        assert not extra, f"Unexpected keys in extraction params: {extra}"
