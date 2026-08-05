"""MIKAI brain — pure file-based task-state substrate (S3 stratum).

Threads, decisions, entities, and inbox live as plain markdown under
`~/.mikai/brain/`. Deterministic scanners run over them; one LLM call
per week rewrites BRAIN.md; one LLM call per ambiguous inbox item.

The graph (Graphiti / Neo4j) is not required for anything in this
package. It sits alongside as an optional richer retrieval surface
via BrainStore adapters (see store.py).
"""

from pathlib import Path

BRAIN_ROOT = Path.home() / ".mikai" / "brain"

THREADS_DIR = BRAIN_ROOT / "threads"
DECISIONS_LOG = BRAIN_ROOT / "decisions" / "LOG.md"
ENTITIES_DIR = BRAIN_ROOT / "entities"
INBOX_DIR = BRAIN_ROOT / "inbox"
INBOX_PROCESSED = INBOX_DIR / "processed"
STATE_DIR = BRAIN_ROOT / "state"

BRAIN_MD = BRAIN_ROOT / "BRAIN.md"
PROGRESS_LOG = STATE_DIR / "progress.json"
DELIVERY_LOG = STATE_DIR / "delivery_events.jsonl"
