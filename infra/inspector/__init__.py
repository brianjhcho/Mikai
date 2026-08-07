"""Inspector — diagnostic surface for MIKAI (builder's view).

Companion to the cockpit. The cockpit is the operator's morning
surface (act on it). The Inspector is the builder's diagnostic surface
(understand what MIKAI is noticing before deciding whether to surface
it via other channels).

Contract:
  * Reads only. Never mutates thread / brain state.
  * Consumes wiki.md, USER_MODEL.md, entities/, state/*.jsonl.
  * Emits ~/.mikai/brain/inspector.html + state/tensions.json.
  * Streaming answers piggyback on the existing /ask/stream endpoint.
"""

from __future__ import annotations

from pathlib import Path

from infra.mikai_brain import BRAIN_ROOT, STATE_DIR

WIKI_DIR = Path.home() / ".mikai" / "wiki"
WIKI_MD = WIKI_DIR / "wiki.md"
CONSOLE_DIR = Path.home() / ".mikai" / "console"
CONSOLE_TENSIONS_JSON = CONSOLE_DIR / "tensions.json"
INSPECTOR_HTML = BRAIN_ROOT / "inspector.html"
TENSIONS_JSON = STATE_DIR / "tensions.json"

__all__ = [
    "BRAIN_ROOT",
    "STATE_DIR",
    "WIKI_DIR",
    "WIKI_MD",
    "CONSOLE_DIR",
    "CONSOLE_TENSIONS_JSON",
    "INSPECTOR_HTML",
    "TENSIONS_JSON",
]
