"""
MIKAI Ingestion Daemon — sync.py

Watches three sources and ingests new content into the Graphiti knowledge graph:
  1. Apple Notes  — via osascript, hash-diff to detect changes
  2. Claude Code  — JSONL session files, tail-parsed by byte offset
  3. Drop folder  — ~/.mikai/imports/ JSON/markdown files

Usage:
    python sync.py          # daemon mode (watchdog + debounce)
    python sync.py --once   # single pass, exit when done

State is checkpointed in ~/.mikai/sync_state.json so restarts never re-ingest.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.llm_client.config import LLMConfig, ModelSize, DEFAULT_MAX_TOKENS
from graphiti_core.llm_client.client import Message
from graphiti_core.embedder.voyage import VoyageAIEmbedder, VoyageAIEmbedderConfig
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.nodes import EpisodeType

logger = logging.getLogger("mikai-sync")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

# ── Paths ────────────────────────────────────────────────────────────────────

MIKAI_DIR = Path.home() / ".mikai"
IMPORTS_DIR = MIKAI_DIR / "imports"
PROCESSED_DIR = MIKAI_DIR / "imports" / "processed"
STATE_FILE = MIKAI_DIR / "sync_state.json"

NOTES_WATCH_PATH = (
    Path.home()
    / "Library"
    / "Group Containers"
    / "group.com.apple.notes"
)
CLAUDE_WATCH_PATH = Path.home() / ".claude" / "projects"

DEBOUNCE_SECONDS = 5
RETRY_SECONDS = 30
EPISODE_DELAY_SECONDS = 2
GROUP_ID = "mikai-default"


# ── Graphiti client classes (same as sidecar/mcp_server.py) ─────────────────


class DeepSeekClient(OpenAIGenericClient):
    """DeepSeek-compatible client using json_object mode instead of json_schema."""

    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, Any]:
        from openai.types.chat import ChatCompletionMessageParam

        openai_messages: list[ChatCompletionMessageParam] = []
        for m in messages:
            m.content = self._clean_input(m.content)
            if m.role == "user":
                openai_messages.append({"role": "user", "content": m.content})
            elif m.role == "system":
                openai_messages.append({"role": "system", "content": m.content})

        if response_model is not None:
            schema = response_model.model_json_schema()
            schema_instruction = (
                f"\n\nYou MUST respond with valid JSON matching this exact schema:\n"
                f"```json\n{json.dumps(schema, indent=2)}\n```\n"
                f"Respond ONLY with the JSON object, no other text."
            )
            injected = False
            for i, msg in enumerate(openai_messages):
                if msg["role"] == "system":
                    openai_messages[i] = {
                        "role": "system",
                        "content": str(msg["content"]) + schema_instruction,
                    }
                    injected = True
                    break
            if not injected:
                openai_messages.insert(
                    0, {"role": "system", "content": schema_instruction}
                )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
            )
            result = response.choices[0].message.content or "{}"
            return json.loads(result)
        except Exception as e:
            logger.error(f"DeepSeek error: {e}")
            raise


class PassthroughReranker(CrossEncoderClient):
    """No-op reranker — avoids OpenAI dependency."""

    async def rank(
        self, query: str, passages: list[str]
    ) -> list[tuple[str, float]]:
        return [(p, 1.0 - i * 0.01) for i, p in enumerate(passages)]


# ── Graphiti initialization ──────────────────────────────────────────────────


async def init_graphiti() -> Graphiti:
    """Initialize the Graphiti client with Neo4j + DeepSeek + Voyage AI."""
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "mikai-local-dev")

    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    voyage_key = os.environ.get("VOYAGE_API_KEY")

    if not deepseek_key:
        raise RuntimeError("DEEPSEEK_API_KEY required")
    if not voyage_key:
        raise RuntimeError("VOYAGE_API_KEY required")

    logger.info(f"Connecting to Neo4j at {neo4j_uri}")

    llm_client = DeepSeekClient(
        config=LLMConfig(
            api_key=deepseek_key,
            model="deepseek-chat",
            small_model="deepseek-chat",
            base_url="https://api.deepseek.com",
        ),
        max_tokens=8192,
    )

    embedder = VoyageAIEmbedder(
        config=VoyageAIEmbedderConfig(
            api_key=voyage_key,
            model="voyage-3",
        )
    )

    g = Graphiti(
        neo4j_uri,
        neo4j_user,
        neo4j_password,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=PassthroughReranker(),
    )

    await g.build_indices_and_constraints()
    logger.info("Graphiti initialized")
    return g


# ── Checkpoint state ─────────────────────────────────────────────────────────


def load_state() -> dict:
    """Load checkpoint state from disk, or return empty defaults."""
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open() as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not read state file: {e}; starting fresh")
    return {
        "apple_notes": {"hashes": {}},
        "claude_code": {"offsets": {}},
        "drop_folder": {"processed": []},
    }


def save_state(state: dict) -> None:
    """Persist checkpoint state to disk."""
    MIKAI_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(state, f, indent=2)
    tmp.replace(STATE_FILE)


# ── Ingestion helper ─────────────────────────────────────────────────────────


async def ingest(
    g: Graphiti,
    content: str,
    source_description: str,
    reference_time: datetime,
    label: str = "",
) -> None:
    """Call graphiti.add_episode() with logging. Errors are caught and logged."""
    preview = content[:80].replace("\n", " ")
    logger.info(f"[{source_description}] ingesting: {preview!r}")
    try:
        result = await g.add_episode(
            name=source_description,
            episode_body=content,
            source=EpisodeType.text,
            source_description=source_description,
            reference_time=reference_time,
            group_id=GROUP_ID,
        )
        nodes = len(result.nodes) if result and result.nodes else 0
        edges = len(result.edges) if result and result.edges else 0
        logger.info(
            f"[{source_description}] done — {nodes} entities, {edges} edges"
            + (f" | {label}" if label else "")
        )
    except Exception as e:
        logger.error(f"[{source_description}] add_episode failed: {e}")


# ── Source: Apple Notes ──────────────────────────────────────────────────────

APPLE_SCRIPT = """\
set output to ""
tell application "Notes"
    repeat with n in every note
        set t to name of n
        set b to plain text of n
        set output to output & t & "\x00" & b & "\x01"
    end repeat
end tell
return output
"""


def fetch_apple_notes() -> list[tuple[str, str]] | None:
    """
    Run osascript to fetch all notes as (title, body) pairs.
    Returns None if osascript fails (app not running, permission denied, etc.).
    """
    try:
        proc = subprocess.run(
            ["osascript", "-e", APPLE_SCRIPT],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            logger.warning(
                f"Apple Notes osascript failed (rc={proc.returncode}): "
                f"{proc.stderr.strip()}"
            )
            return None
        raw = proc.stdout.strip()
        if not raw:
            return []
        notes = []
        for chunk in raw.split("\x01"):
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = chunk.split("\x00", 1)
            title = parts[0].strip() if parts else ""
            body = parts[1].strip() if len(parts) > 1 else ""
            notes.append((title, body))
        return notes
    except subprocess.TimeoutExpired:
        logger.warning("Apple Notes osascript timed out")
        return None
    except Exception as e:
        logger.warning(f"Apple Notes fetch error: {e}")
        return None


def note_hash(title: str, body: str) -> str:
    return hashlib.sha256(f"{title}\x00{body}".encode()).hexdigest()


async def sync_apple_notes(g: Graphiti, state: dict) -> int:
    """Sync changed Apple Notes. Returns count of new episodes ingested."""
    notes = fetch_apple_notes()
    if notes is None:
        return 0

    note_state = state.setdefault("apple_notes", {"hashes": {}})
    stored_hashes: dict[str, str] = note_state.setdefault("hashes", {})
    count = 0

    for title, body in notes:
        h = note_hash(title, body)
        key = hashlib.sha256(title.encode()).hexdigest()
        if stored_hashes.get(key) == h:
            continue  # unchanged
        content = f"# {title}\n\n{body}" if title else body
        if not content.strip():
            continue
        await ingest(
            g,
            content=content,
            source_description="apple-notes",
            reference_time=datetime.now(),
            label=title[:60],
        )
        stored_hashes[key] = h
        count += 1
        if count > 1:
            await asyncio.sleep(EPISODE_DELAY_SECONDS)

    save_state(state)
    if count:
        logger.info(f"Apple Notes: {count} note(s) ingested")
    return count


# ── Source: Claude Code JSONL ────────────────────────────────────────────────


def find_jsonl_files(base: Path) -> list[Path]:
    """Recursively find all .jsonl files under base."""
    if not base.exists():
        return []
    return list(base.rglob("*.jsonl"))


def tail_jsonl(path: Path, offset: int) -> tuple[list[dict], int]:
    """
    Read new lines from a JSONL file starting at byte offset.
    Returns (new_records, new_offset).
    """
    try:
        size = path.stat().st_size
        if size <= offset:
            return [], offset
        records = []
        with path.open("rb") as f:
            f.seek(offset)
            for raw_line in f:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            new_offset = f.tell()
        return records, new_offset
    except Exception as e:
        logger.warning(f"Could not read {path}: {e}")
        return [], offset


def extract_turns(records: list[dict]) -> list[dict]:
    """Extract user/assistant turns from JSONL records."""
    turns = []
    for rec in records:
        msg_type = rec.get("type", "")
        if msg_type not in ("human", "assistant"):
            continue
        content = rec.get("content", "")
        if isinstance(content, list):
            # content can be a list of content blocks
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        for item in block.get("content", []):
                            if isinstance(item, dict) and item.get("type") == "text":
                                parts.append(item.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            content = "\n".join(p for p in parts if p)
        if not isinstance(content, str):
            content = str(content)
        content = content.strip()
        if content:
            turns.append({"type": msg_type, "content": content, "ts": rec.get("timestamp")})
    return turns


async def sync_claude_code(g: Graphiti, state: dict) -> int:
    """Sync new turns from Claude Code JSONL session files."""
    code_state = state.setdefault("claude_code", {"offsets": {}})
    offsets: dict[str, int] = code_state.setdefault("offsets", {})

    files = find_jsonl_files(CLAUDE_WATCH_PATH)
    count = 0

    for path in files:
        key = str(path)
        offset = offsets.get(key, 0)
        records, new_offset = tail_jsonl(path, offset)
        if not records:
            offsets[key] = new_offset
            continue

        turns = extract_turns(records)
        for turn in turns:
            role = turn["type"]
            content = turn["content"]
            ts_raw = turn.get("ts")
            try:
                ref_time = datetime.fromisoformat(ts_raw) if ts_raw else datetime.now()
            except (ValueError, TypeError):
                ref_time = datetime.now()

            label = f"{role} | {path.name}"
            await ingest(
                g,
                content=f"[{role}] {content}",
                source_description="claude-code",
                reference_time=ref_time,
                label=label,
            )
            count += 1
            await asyncio.sleep(EPISODE_DELAY_SECONDS)

        offsets[key] = new_offset

    save_state(state)
    if count:
        logger.info(f"Claude Code: {count} turn(s) ingested")
    return count


# ── Source: Drop folder ──────────────────────────────────────────────────────


async def sync_drop_folder(g: Graphiti, state: dict) -> int:
    """Ingest new files from ~/.mikai/imports/, move to processed/."""
    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    folder_state = state.setdefault("drop_folder", {"processed": []})
    processed: list[str] = folder_state.setdefault("processed", [])
    count = 0

    candidates = sorted(
        p for p in IMPORTS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".json", ".md", ".markdown")
    )

    for path in candidates:
        name = path.name
        if name in processed:
            continue

        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Drop folder: could not read {path}: {e}")
            continue

        if path.suffix.lower() == ".json":
            try:
                data = json.loads(raw)
                content = data.get("content") or data.get("text") or json.dumps(data, indent=2)
            except json.JSONDecodeError:
                content = raw
        else:
            content = raw

        content = content.strip()
        if not content:
            logger.warning(f"Drop folder: {name} is empty, skipping")
            processed.append(name)
            save_state(state)
            continue

        await ingest(
            g,
            content=content,
            source_description="manual-import",
            reference_time=datetime.now(),
            label=name,
        )
        count += 1

        # Move to processed/
        dest = PROCESSED_DIR / name
        if dest.exists():
            stem = path.stem
            suffix = path.suffix
            dest = PROCESSED_DIR / f"{stem}_{int(time.time())}{suffix}"
        try:
            shutil.move(str(path), str(dest))
            logger.info(f"Drop folder: moved {name} -> processed/")
        except Exception as e:
            logger.warning(f"Drop folder: could not move {name}: {e}")

        processed.append(name)
        save_state(state)

        if count > 1:
            await asyncio.sleep(EPISODE_DELAY_SECONDS)

    if count:
        logger.info(f"Drop folder: {count} file(s) ingested")
    return count


# ── Full sync pass ────────────────────────────────────────────────────────────


async def run_sync_pass(g: Graphiti, state: dict) -> None:
    """Run a single full sync across all three sources."""
    logger.info("--- sync pass starting ---")
    n = await sync_apple_notes(g, state)
    c = await sync_claude_code(g, state)
    d = await sync_drop_folder(g, state)
    total = n + c + d
    logger.info(f"--- sync pass done: {total} episode(s) ingested ---")


# ── Daemon mode (watchdog) ────────────────────────────────────────────────────


def start_daemon(g: Graphiti, state: dict, loop: asyncio.AbstractEventLoop) -> None:
    """Start watchdog observers for all three watch paths."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        logger.error(
            "watchdog is not installed. Run: pip install 'watchdog>=4.0'"
        )
        sys.exit(1)

    # Shared debounce: map source_key -> last_trigger_time
    _last_trigger: dict[str, float] = {}
    _pending: dict[str, asyncio.Handle] = {}

    def schedule_sync(source_key: str) -> None:
        """Debounce: schedule a sync DEBOUNCE_SECONDS after the last event."""
        now = time.monotonic()
        _last_trigger[source_key] = now

        existing = _pending.get(source_key)
        if existing is not None:
            existing.cancel()

        handle = loop.call_later(
            DEBOUNCE_SECONDS,
            lambda k=source_key: asyncio.ensure_future(
                _debounced_sync(k, state, g), loop=loop
            ),
        )
        _pending[source_key] = handle

    async def _debounced_sync(source_key: str, state: dict, g: Graphiti) -> None:
        _pending.pop(source_key, None)
        logger.info(f"Debounced sync triggered for: {source_key}")
        try:
            if source_key == "apple_notes":
                await sync_apple_notes(g, state)
            elif source_key == "claude_code":
                await sync_claude_code(g, state)
            elif source_key == "drop_folder":
                await sync_drop_folder(g, state)
        except Exception as e:
            logger.error(f"Sync error for {source_key}: {e}")

    class NotesHandler(FileSystemEventHandler):
        def on_any_event(self, event):
            schedule_sync("apple_notes")

    class ClaudeHandler(FileSystemEventHandler):
        def on_any_event(self, event):
            if hasattr(event, "src_path") and event.src_path.endswith(".jsonl"):
                schedule_sync("claude_code")

    class DropHandler(FileSystemEventHandler):
        def on_created(self, event):
            schedule_sync("drop_folder")

        def on_moved(self, event):
            schedule_sync("drop_folder")

    observer = Observer()

    if NOTES_WATCH_PATH.exists():
        observer.schedule(NotesHandler(), str(NOTES_WATCH_PATH), recursive=True)
        logger.info(f"Watching Apple Notes: {NOTES_WATCH_PATH}")
    else:
        logger.warning(f"Apple Notes path not found, skipping watch: {NOTES_WATCH_PATH}")

    if CLAUDE_WATCH_PATH.exists():
        observer.schedule(ClaudeHandler(), str(CLAUDE_WATCH_PATH), recursive=True)
        logger.info(f"Watching Claude Code: {CLAUDE_WATCH_PATH}")
    else:
        logger.warning(f"Claude Code path not found, skipping watch: {CLAUDE_WATCH_PATH}")

    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    observer.schedule(DropHandler(), str(IMPORTS_DIR), recursive=False)
    logger.info(f"Watching drop folder: {IMPORTS_DIR}")

    observer.start()
    logger.info("Daemon running. Press Ctrl+C to stop.")
    return observer


# ── Entry point ───────────────────────────────────────────────────────────────


async def main_async(once: bool) -> None:
    # Ensure directories exist
    MIKAI_DIR.mkdir(parents=True, exist_ok=True)
    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize Graphiti with retry logic
    g: Graphiti | None = None
    while g is None:
        try:
            g = await init_graphiti()
        except Exception as e:
            if once:
                logger.error(f"Cannot connect to Graphiti/Neo4j: {e}")
                sys.exit(1)
            else:
                logger.error(
                    f"Cannot connect to Graphiti/Neo4j: {e}. "
                    f"Retrying in {RETRY_SECONDS}s..."
                )
                await asyncio.sleep(RETRY_SECONDS)

    state = load_state()

    try:
        if once:
            await run_sync_pass(g, state)
        else:
            # Initial pass on startup
            await run_sync_pass(g, state)

            # Start watchdog observers
            loop = asyncio.get_event_loop()
            observer = start_daemon(g, state, loop)

            try:
                while True:
                    await asyncio.sleep(1)
            except (KeyboardInterrupt, asyncio.CancelledError):
                logger.info("Shutting down...")
                observer.stop()
                observer.join()
    finally:
        await g.close()
        logger.info("Graphiti connection closed")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MIKAI ingestion daemon — sync Apple Notes, Claude Code sessions, and drop folder into Graphiti"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Single sync pass then exit (default: run as daemon)",
    )
    args = parser.parse_args()
    asyncio.run(main_async(once=args.once))


if __name__ == "__main__":
    main()
