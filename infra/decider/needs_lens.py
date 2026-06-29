"""
needs_lens.py — parse docs/USER_NEEDS_REGISTRY.md into structured candidates.

This is the HIGHEST-PRIORITY lens for FIGS. Brian explicitly curated this
file — every item here represents a load-bearing life need MIKAI should
treat as a candidate for surfacing. Outranks the Dream-generated wiki.

Schema per item (see USER_NEEDS_REGISTRY.md):
  slug, title, state, urgency, domain, last_movement, next_step,
  connects_to, blockers, notes
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Resolve registry path. The file lives in docs/ at the repo root.
DEFAULT_REGISTRY = Path(__file__).resolve().parent.parent.parent / "docs" / "USER_NEEDS_REGISTRY.md"


STATE_WEIGHTS = {
    "in_flight": 0.95,
    "acting": 1.00,         # alias from wiki vocabulary
    "stalled": 0.95,
    "blocked": 0.90,
    "decided": 0.70,
    "on_hold": 0.50,
    "exploring": 0.40,
    "unknown": 0.30,
    "done": 0.00,
}


URGENCY_WEIGHTS = {
    "critical": 1.00,
    "high": 0.85,
    "medium": 0.60,
    "low": 0.35,
}


@dataclass
class UserNeed:
    """One curated user need parsed from the registry."""
    slug: str
    title: str
    state: str
    urgency: str
    domain: str
    last_movement: str
    next_step: str
    connects_to: list[str] = field(default_factory=list)
    blockers: str = ""
    notes: str = ""

    @property
    def is_done(self) -> bool:
        return self.state.lower() == "done"


@dataclass
class ParsedRegistry:
    needs: list[UserNeed]
    available: bool = True
    error: str | None = None
    registry_path: str = ""


# ── Parsing helpers ─────────────────────────────────────────────────────


def _split_into_yaml_blocks(text: str) -> list[str]:
    """Find every fenced YAML block in the markdown."""
    pattern = re.compile(r"```yaml\s*\n(.*?)\n```", re.DOTALL)
    return [m.group(1) for m in pattern.finditer(text)]


def _parse_simple_yaml(block: str) -> dict:
    """Hand-roll a parser for the subset of YAML used in the registry.

    Supports:
      key: value           (single-line scalar)
      key: |               (multi-line block scalar, indented)
        line 1
        line 2
      key:                 (list)
        - item 1
        - item 2

    Does NOT support nested mappings — registry doesn't need them.
    """
    out: dict = {}
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue

        m = re.match(r"^(\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)$", line)
        if not m:
            i += 1
            continue
        indent, key, value = m.group(1), m.group(2), m.group(3).strip()

        if value == "|":
            # Multi-line block scalar — gather following indented lines
            block_lines = []
            i += 1
            base_indent: str | None = None
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    block_lines.append("")
                    i += 1
                    continue
                if base_indent is None:
                    bi_m = re.match(r"^(\s+)", nxt)
                    if not bi_m:
                        break
                    base_indent = bi_m.group(1)
                if nxt.startswith(base_indent):
                    block_lines.append(nxt[len(base_indent):])
                    i += 1
                else:
                    break
            out[key] = "\n".join(block_lines).rstrip()
            continue

        if value == "":
            # List — gather following "- " lines at deeper indent
            items: list[str] = []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    i += 1
                    continue
                lm = re.match(r"^(\s*)-\s+(.+)$", nxt)
                if lm and len(lm.group(1)) > len(indent):
                    items.append(lm.group(2).strip())
                    i += 1
                else:
                    break
            out[key] = items
            continue

        # Single-line scalar — strip optional surrounding quotes
        val = value
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        out[key] = val
        i += 1
    return out


def parse_registry(path: Path = DEFAULT_REGISTRY) -> ParsedRegistry:
    """Load and parse the registry. Never raises — returns ParsedRegistry
    with available=False on error."""
    if not path.exists():
        return ParsedRegistry(
            needs=[],
            available=False,
            error=f"USER_NEEDS_REGISTRY.md not found at {path}",
            registry_path=str(path),
        )

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return ParsedRegistry(
            needs=[],
            available=False,
            error=f"read failed: {e}",
            registry_path=str(path),
        )

    needs: list[UserNeed] = []
    for block in _split_into_yaml_blocks(text):
        try:
            data = _parse_simple_yaml(block)
        except Exception:
            continue
        if not data.get("slug"):
            continue
        need = UserNeed(
            slug=str(data.get("slug", "")).strip(),
            title=str(data.get("title", "")).strip(),
            state=str(data.get("state", "unknown")).strip().lower(),
            urgency=str(data.get("urgency", "medium")).strip().lower(),
            domain=str(data.get("domain", "other")).strip().lower(),
            last_movement=str(data.get("last_movement", "")).strip(),
            next_step=str(data.get("next_step", "")).strip(),
            connects_to=data.get("connects_to", []) or [],
            blockers=str(data.get("blockers", "")).strip(),
            notes=str(data.get("notes", "")).strip(),
        )
        needs.append(need)

    return ParsedRegistry(
        needs=needs,
        available=True,
        registry_path=str(path),
    )


# ── Scoring ─────────────────────────────────────────────────────────────


def _tension_pressure_for_need(need: UserNeed) -> float:
    """Per FIGS_LOSS_FUNCTION.md §1.2 — needs default to 0.7; a blocker
    counts as a tension and bumps to 0.9."""
    if need.blockers and need.blockers.lower() not in ("none", "n/a", ""):
        return 0.9
    return 0.7


def score_need(need: UserNeed) -> float:
    """Compute the (state × tension × urgency × detail) wiki-derived
    components of surface_priority. delivery_value and delivery_cost are
    judged by the LLM at prompt time.

    Returned score range: 0..1
    """
    if need.is_done:
        return 0.0
    state_w = STATE_WEIGHTS.get(need.state, STATE_WEIGHTS["unknown"])
    urgency_w = URGENCY_WEIGHTS.get(need.urgency, URGENCY_WEIGHTS["medium"])
    tension_w = _tension_pressure_for_need(need)
    # Detail proxy — a need with a real next_step is more actionable
    detail_w = min(1.0, len(need.next_step) / 80.0) if need.next_step else 0.3
    raw = state_w * urgency_w * tension_w * detail_w
    # The four factors are each 0..1; product is naturally 0..1
    return min(1.0, raw)


def ranked_needs(registry: ParsedRegistry) -> list[tuple[float, UserNeed]]:
    """Return all live (non-done) needs ranked by score descending."""
    scored = [(score_need(n), n) for n in registry.needs if not n.is_done]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


# ── Standalone diagnostic ───────────────────────────────────────────────


if __name__ == "__main__":
    import json
    import sys
    reg = parse_registry()
    print(f"registry_path: {reg.registry_path}")
    print(f"available: {reg.available}")
    if reg.error:
        print(f"error: {reg.error}")
    print(f"needs: {len(reg.needs)}")
    print()
    print("=== Ranked needs (live only) ===")
    for score, need in ranked_needs(reg):
        print(f"  {score:.2f} [{need.state:<10}/{need.urgency:<8}/{need.domain:<12}] {need.title}")
        if need.next_step:
            print(f"        next: {need.next_step[:120]}")
        print()
