"""
Negative examples for extraction prompt augmentation.

These examples are added to the `custom_extraction_instructions` parameter
of `add_episode()` calls to reduce false-positive noise in entity extraction.

Lesson from Mem0: pairing negative examples with positive examples in
the extraction prompt cuts false-positive-dense noise by ~20% relative
to positive-only prompts.
"""

from typing import TypedDict


class NegativeExample(TypedDict):
    """A single negative example with explanation."""
    text: str
    because: str


# Negative examples sourced from the existing noise cluster documented in
# docs/evals/baseline-2026-04-29.md and observed during initial extractions.
EXTRACTION_NEGATIVES: list[NegativeExample] = [
    {
        "text": "Hearty simple creative",
        "because": "fragment from creative-writing prose — not a named thing, just descriptive adjectives strung together",
    },
    {
        "text": "folly",
        "because": "title word in isolation — not an entity itself, only meaningful in context of its book source",
    },
    {
        "text": "The MacNabs",
        "because": "book reference inside a note — should be a Source type (the book), not a freestanding Concept",
    },
    {
        "text": "2327 storage number",
        "because": "numeric fragment with descriptive label — not an entity, part of a larger storage system reference",
    },
    {
        "text": "A bee",
        "because": "sentence-start indefinite article + noun, not a named entity — would only be an entity if it had a proper name",
    },
    {
        "text": "the thing",
        "because": "generic pronoun substitute — refers to something previously mentioned, not an entity of its own",
    },
    {
        "text": "stuff we talked about",
        "because": "meta-reference to previous conversation, not an extractable entity — too vague and contextual",
    },
    {
        "text": "whatever",
        "because": "colloquial filler word, not an entity — no semantic content worth capturing",
    },
    {
        "text": "this problem",
        "because": "unspecified noun phrase — lacks concrete specificity; the actual entity is the problem's name, not the phrase itself",
    },
    {
        "text": "good news",
        "because": "generic descriptor + noun — the entity is what the good news *is*, not the descriptor itself",
    },
]


def format_negatives_for_prompt() -> str:
    """Format negative examples as markdown for injection into extraction prompts.

    Returns a string that can be appended to custom_extraction_instructions.
    """
    lines = [
        "# Do NOT extract these (they are NOT entities):",
        "",
    ]
    for neg in EXTRACTION_NEGATIVES:
        lines.append(f"- **{neg['text']}** — {neg['because']}")
    lines.append("")
    return "\n".join(lines)


def get_custom_extraction_instructions() -> str:
    """Build the full custom extraction instructions including negatives.

    This is the string that should be passed as custom_extraction_instructions
    to every add_episode() call.
    """
    return format_negatives_for_prompt()
