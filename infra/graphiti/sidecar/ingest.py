"""
Pure-Python ingestion helpers: parsers, sensitivity filters, checkpoint state.

No graphiti-core or network dependencies, so these functions are fast and easy
to unit-test. Shared between mcp_ingest.py (cloud sources) and the script-level
importers (Apple Notes dump, Claude threads, Perplexity threads).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("mikai-graphiti-ingest")


# ── Sensitivity filter ───────────────────────────────────────────────────────

SKIP_PATTERNS = ["api key", "password", "secret", "credential", "token"]


def is_sensitive_name(name: str) -> bool:
    """True if the name likely labels a secrets-bearing record."""
    lower = name.lower()
    return any(p in lower for p in SKIP_PATTERNS)


# ── Apple Notes dump parser ───────────────────────────────────────────────────
#
# The AppleScript dump format (from scripts/read_notes.applescript):
#   ===NOTE_START===
#   NAME:<note title>
#   DATE:<iso date>
#   <body lines...>
#   ===NOTE_END===


def parse_notes_dump(
    path_or_text: str | Path,
    *,
    min_body_chars: int = 50,
    max_body_chars: int | None = None,
) -> list[dict]:
    """Parse the AppleScript note dump into a list of note dicts.

    Accepts a filesystem path or a raw text blob. Drops sensitive and too-short
    notes silently. If `max_body_chars` is set, body is truncated to that
    length.

    Each returned dict has keys: name, date, body.
    """
    text = _read_text(path_or_text)
    notes: list[dict] = []
    current: dict | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if line == "===NOTE_START===":
            current = {"name": "", "date": "", "body_lines": []}
        elif line == "===NOTE_END===" and current is not None:
            body = "\n".join(current["body_lines"]).strip()
            name = current["name"]
            if len(body) > min_body_chars and not is_sensitive_name(name):
                notes.append({
                    "name": name,
                    "date": current["date"],
                    "body": body[:max_body_chars] if max_body_chars else body,
                })
            current = None
        elif current is not None:
            if line.startswith("NAME:") and not current["name"]:
                current["name"] = line[5:]
            elif line.startswith("DATE:") and not current["date"]:
                current["date"] = line[5:]
            else:
                current["body_lines"].append(line)

    return notes


# ── Direct osascript batch parser ─────────────────────────────────────────────
#
# Some importers skip the dump file and read notes directly via osascript with
# a delimited single-line format. See scripts/import_apple_notes.py.

NOTE_SEPARATOR = "---NOTE_SEPARATOR---"
FIELD_SEPARATOR = "---FIELD_SEP---"


def parse_osascript_notes_output(
    raw: str,
    *,
    min_body_chars: int = 50,
) -> list[dict]:
    """Parse the delimited osascript output from import_apple_notes.read_apple_notes.

    Each note is separated by NOTE_SEPARATOR. Fields within a note are
    separated by FIELD_SEPARATOR in order: name, body, date.
    """
    notes: list[dict] = []
    for entry in raw.split(NOTE_SEPARATOR):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(FIELD_SEPARATOR)
        if len(parts) < 3:
            continue
        name = parts[0].strip()
        body = parts[1].strip()
        date = parts[2].strip()
        if len(body) <= min_body_chars:
            continue
        if is_sensitive_name(name):
            continue
        notes.append({"name": name, "body": body, "date": date})
    return notes


# ── Claude thread turn parser ─────────────────────────────────────────────────


def parse_claude_turns(raw_content: str) -> list[dict]:
    """Split a Claude thread dump into a list of {role, content} turns.

    The dump uses inline prefixes:
      [User]: <text>
      [Assistant]: <text>
    A turn may span multiple lines; lines without a prefix belong to the
    current turn.
    """
    turns: list[dict] = []
    current_role: str | None = None
    current_lines: list[str] = []

    for line in raw_content.split("\n"):
        if line.startswith("[User]:"):
            if current_role:
                turns.append({
                    "role": current_role,
                    "content": "\n".join(current_lines).strip(),
                })
            current_role = "user"
            current_lines = [line[7:].strip()]
        elif line.startswith("[Assistant]:"):
            if current_role:
                turns.append({
                    "role": current_role,
                    "content": "\n".join(current_lines).strip(),
                })
            current_role = "assistant"
            current_lines = [line[12:].strip()]
        else:
            current_lines.append(line)

    if current_role:
        turns.append({
            "role": current_role,
            "content": "\n".join(current_lines).strip(),
        })

    return turns


# ── Perplexity thread step extractor ──────────────────────────────────────────


def _trim_to_first_json_array(raw: str) -> str:
    """If `raw` contains concatenated JSON arrays, return just the first.

    Walks the bracket depth from the start and stops at the first balanced
    close. Returns the original string if no top-level array is found.
    """
    depth = 0
    for i, c in enumerate(raw):
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
        if depth == 0 and i > 0:
            return raw[: i + 1]
    return raw


def parse_perplexity_query_and_answer(raw_content: str) -> tuple[str | None, str | None]:
    """Extract (query, answer) from a Perplexity raw thread blob.

    Handles the `[Assistant]:` prefix, concatenated JSON arrays, and
    double-encoded answer payloads (the FINAL step's `content.answer` is
    sometimes itself a JSON string).
    """
    raw = raw_content
    if raw.startswith("[Assistant]:"):
        raw = raw[len("[Assistant]:"):].strip()

    try:
        if raw.startswith("["):
            trimmed = _trim_to_first_json_array(raw)
            steps = json.loads(trimmed)
        else:
            steps = [json.loads(raw)]
    except (json.JSONDecodeError, TypeError):
        return None, None

    user_query: str | None = None
    answer: str | None = None

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_type = step.get("step_type", "")
        content = step.get("content", {})
        if step_type == "INITIAL_QUERY" and isinstance(content, dict):
            user_query = content.get("query", "") or None
        elif step_type == "FINAL" and isinstance(content, dict):
            answer_raw = content.get("answer", "")
            try:
                answer_obj = json.loads(answer_raw)
                answer = (
                    answer_obj.get("answer", answer_raw)
                    if isinstance(answer_obj, dict)
                    else answer_raw
                )
            except (json.JSONDecodeError, TypeError):
                answer = answer_raw

    return user_query, answer


# ── Checkpoint state for MCP ingestion ────────────────────────────────────────


def load_state(path: str | Path) -> dict[str, str]:
    """Load last-sync timestamps keyed by source name.

    Returns {} if the file doesn't exist or is unreadable. Doesn't raise —
    callers treat "no state" as "first run", which is what an unreadable
    file also means to them.
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with p.open() as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Could not read sync state from {p}: {e}")
        return {}


def save_state(state: dict[str, str], path: str | Path) -> None:
    """Persist last-sync timestamps to disk.

    Creates the parent directory if needed. Swallows write errors with a
    warning — a checkpoint that fails to save will just be re-tried on the
    next poll cycle.
    """
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as fh:
            json.dump(state, fh, indent=2)
    except OSError as e:
        logger.warning(f"Could not write sync state to {p}: {e}")


def interpolate_tool_args(
    tool_args: dict, last_sync: str | None
) -> dict:
    """Replace ${LAST_SYNC} placeholders with an actual ISO timestamp.

    Falls back to "now" when last_sync is None so that first-run queries
    using ${LAST_SYNC} don't return the entire corpus.
    """
    last_sync_val = last_sync or datetime.now(tz=timezone.utc).isoformat()
    result: dict = {}
    for k, v in tool_args.items():
        if isinstance(v, str):
            result[k] = v.replace("${LAST_SYNC}", last_sync_val)
        else:
            result[k] = v
    return result


# ── Internal ──────────────────────────────────────────────────────────────────


def _read_text(path_or_text: str | Path) -> str:
    """Accept either a path or a raw text blob.

    Heuristic: treat the argument as a path if it's a Path instance, or a
    short str that points to an existing file; otherwise treat it as raw text.
    """
    if isinstance(path_or_text, Path):
        return path_or_text.read_text(errors="replace")
    # For strings: short enough to plausibly be a path, and file exists
    if "\n" not in path_or_text and len(path_or_text) < 512:
        try:
            p = Path(path_or_text)
            if p.exists() and p.is_file():
                return p.read_text(errors="replace")
        except OSError:
            pass
    return path_or_text
