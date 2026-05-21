"""Tests for extraction prompt negatives."""

import sys
from pathlib import Path

# Add sidecar to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sidecar.extraction.prompt_negatives import (
    EXTRACTION_NEGATIVES,
    NegativeExample,
    format_negatives_for_prompt,
    get_custom_extraction_instructions,
)


def test_extraction_negatives_exists():
    """EXTRACTION_NEGATIVES constant is defined."""
    assert EXTRACTION_NEGATIVES is not None
    assert isinstance(EXTRACTION_NEGATIVES, list)


def test_extraction_negatives_has_minimum_entries():
    """EXTRACTION_NEGATIVES has at least 8 entries."""
    assert len(EXTRACTION_NEGATIVES) >= 8, f"Expected ≥8 negatives, got {len(EXTRACTION_NEGATIVES)}"


def test_each_negative_has_required_fields():
    """Each negative example has 'text' and 'because' fields."""
    for i, neg in enumerate(EXTRACTION_NEGATIVES):
        assert isinstance(neg, dict), f"Negative {i} is not a dict: {type(neg)}"
        assert "text" in neg, f"Negative {i} missing 'text' field: {neg}"
        assert "because" in neg, f"Negative {i} missing 'because' field: {neg}"
        assert isinstance(neg["text"], str), f"Negative {i} 'text' is not a string: {neg['text']}"
        assert isinstance(
            neg["because"], str
        ), f"Negative {i} 'because' is not a string: {neg['because']}"
        assert len(neg["text"]) > 0, f"Negative {i} 'text' is empty"
        assert len(neg["because"]) > 0, f"Negative {i} 'because' is empty"


def test_negative_examples_are_typed():
    """Each negative conforms to NegativeExample TypedDict."""
    for i, neg in enumerate(EXTRACTION_NEGATIVES):
        # Check the TypedDict structure
        try:
            # This would be the actual validation if we could cast,
            # but we verify field presence above.
            assert "text" in neg and "because" in neg
        except KeyError as e:
            raise AssertionError(f"Negative {i} missing required key: {e}")


def test_format_negatives_produces_markdown():
    """format_negatives_for_prompt() produces valid markdown."""
    output = format_negatives_for_prompt()
    assert isinstance(output, str)
    assert len(output) > 0
    # Should contain a header
    assert "# Do NOT extract these" in output
    # Should contain all negative examples as bullet points
    for neg in EXTRACTION_NEGATIVES:
        assert neg["text"] in output, f"Negative text '{neg['text']}' missing from output"
        assert neg["because"] in output, f"Negative 'because' for '{neg['text']}' missing from output"


def test_custom_extraction_instructions_includes_negatives():
    """get_custom_extraction_instructions() includes all negatives."""
    instructions = get_custom_extraction_instructions()
    assert isinstance(instructions, str)
    assert len(instructions) > 0
    # Should contain negatives
    for neg in EXTRACTION_NEGATIVES:
        assert (
            neg["text"] in instructions
        ), f"Negative text '{neg['text']}' missing from instructions"


def test_negatives_would_appear_in_prompt():
    """Verify negatives are formatted in a way that would appear in prompts."""
    instructions = get_custom_extraction_instructions()
    # Check for markdown list markers and emphasis
    assert "**" in instructions, "Negative examples not formatted with markdown emphasis"
    assert "-" in instructions, "Negative examples not formatted as markdown list items"
    # Check that the "because" explanations are present
    assert "—" in instructions or "—" in instructions, "Separator between text and reason missing"


if __name__ == "__main__":
    # Run basic checks if executed directly
    test_extraction_negatives_exists()
    test_extraction_negatives_has_minimum_entries()
    test_each_negative_has_required_fields()
    test_negative_examples_are_typed()
    test_format_negatives_produces_markdown()
    test_custom_extraction_instructions_includes_negatives()
    test_negatives_would_appear_in_prompt()
    print("All tests passed!")
