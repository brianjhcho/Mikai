"""
apply_graphiti_patch.py — Reproducible patch for graphiti-core scaling fix.

Applies the candidate-cap + attribute-stripping patch to graphiti-core's
node_operations.py in whatever venv is active. Run this after every
`pip install --upgrade graphiti-core` to restore the fix.

The problem: graphiti-core's _resolve_with_llm() in node_operations.py
spreads **candidate.attributes into the LLM prompt for ALL candidates,
unboundedly. After ~4,500 entities with accumulated summaries, the prompt
exceeds any LLM context window (2.3M tokens requested vs 131K limit).

The fix: cap candidates at 50 and strip attributes (name + labels only).
Quality tradeoff is minimal — the LLM disambiguates by name similarity,
not by reading full summaries.

Full write-up: docs/ARCHITECTURE.md (raw research: docs/research/graphiti-review.md)

Usage:
    python scripts/apply_graphiti_patch.py
    python scripts/apply_graphiti_patch.py --check   # verify without modifying
    python scripts/apply_graphiti_patch.py --revert   # restore original

Exit codes:
    0 — patch applied (or already applied with --check)
    1 — patch needed (--check mode) or error
"""

import argparse
import importlib.util
import re
import shutil
import sys
from pathlib import Path

MAX_CANDIDATES = 50

# The original code pattern we're looking for (may vary slightly between versions)
ORIGINAL_PATTERN = re.compile(
    r'existing_nodes_context\s*=\s*\[\s*\{[^}]*\*\*candidate\.attributes[^]]*\]',
    re.DOTALL,
)

# Our replacement code
PATCHED_CODE = f"""existing_nodes_context = [
        {{
            **{{"name": candidate.name, "entity_types": candidate.labels}},
            # MIKAI patch: stripped attributes to prevent context overflow at scale.
            # See docs/ARCHITECTURE.md for full rationale.
        }}
        for candidate in indexes.existing_nodes[:{MAX_CANDIDATES}]  # MIKAI patch: capped
    ]"""

PATCH_MARKER = "# MIKAI patch:"


def find_node_operations() -> Path | None:
    """Find node_operations.py in the active graphiti-core installation."""
    spec = importlib.util.find_spec("graphiti_core")
    if spec is None or spec.origin is None:
        return None

    graphiti_root = Path(spec.origin).parent
    candidates = [
        graphiti_root / "utils" / "maintenance" / "node_operations.py",
        graphiti_root / "utils" / "node_operations.py",
        graphiti_root / "node_operations.py",
    ]

    for path in candidates:
        if path.exists():
            return path

    # Fallback: search recursively
    for path in graphiti_root.rglob("node_operations.py"):
        return path

    return None


def is_patched(content: str) -> bool:
    """Check if the file already has the MIKAI patch."""
    return PATCH_MARKER in content


def apply_patch(filepath: Path, dry_run: bool = False) -> bool:
    """Apply the candidate-cap patch. Returns True if changes were made."""
    content = filepath.read_text()

    if is_patched(content):
        print(f"Already patched: {filepath}")
        return False

    if not ORIGINAL_PATTERN.search(content):
        print(f"WARNING: Could not find the expected code pattern in {filepath}")
        print("The graphiti-core version may have changed the resolution code.")
        print("Manual inspection required.")
        return False

    if dry_run:
        print(f"Patch needed: {filepath}")
        return True

    # Backup original
    backup = filepath.with_suffix(".py.bak")
    shutil.copy2(filepath, backup)
    print(f"Backup saved: {backup}")

    # Apply patch
    patched = ORIGINAL_PATTERN.sub(PATCHED_CODE, content)
    filepath.write_text(patched)
    print(f"Patch applied: {filepath}")
    print(f"  - Candidates capped at {MAX_CANDIDATES}")
    print(f"  - Attributes stripped (name + labels only)")
    return True


def revert_patch(filepath: Path) -> bool:
    """Revert to the backup if it exists."""
    backup = filepath.with_suffix(".py.bak")
    if not backup.exists():
        print(f"No backup found at {backup}")
        return False

    shutil.copy2(backup, filepath)
    print(f"Reverted to backup: {filepath}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Apply MIKAI's scaling patch to graphiti-core"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if patch is needed without applying",
    )
    parser.add_argument(
        "--revert",
        action="store_true",
        help="Revert the patch using the .bak backup",
    )
    args = parser.parse_args()

    filepath = find_node_operations()
    if filepath is None:
        print("ERROR: graphiti-core not found in the current Python environment.")
        print("Make sure you've activated the correct venv:")
        print("  source infra/graphiti/.venv/bin/activate")
        sys.exit(1)

    print(f"Found node_operations.py: {filepath}")

    if args.revert:
        success = revert_patch(filepath)
        sys.exit(0 if success else 1)

    if args.check:
        content = filepath.read_text()
        if is_patched(content):
            print("Patch is applied.")
            sys.exit(0)
        else:
            print("Patch is NOT applied.")
            sys.exit(1)

    success = apply_patch(filepath)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
