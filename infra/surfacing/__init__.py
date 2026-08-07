"""Surfacing — text-first view of what L4 is currently surfacing.

The cockpit is the visual side view; this is the diagnostic ledger:
one page that answers "what is MIKAI's L4 layer surfacing right now,
and what is it staying silent about?"

Reads existing state files only (dashboard.json for scored threads +
attention head, delivery_events.jsonl for the Sumimasen ledger,
progress.jsonl for surface-engine ticks, thread markdown for state
transitions). Writes ~/.mikai/brain/surfacing.html and nothing else.
"""

from .collect import collect_view
from .render import render_html

__all__ = ["collect_view", "render_html"]
