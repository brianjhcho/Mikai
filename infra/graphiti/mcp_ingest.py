"""
MIKAI MCP Ingestion Daemon — Phase 2 cloud-source ingestion.

Makes MIKAI an MCP CLIENT that connects to external MCP servers (Gmail,
Calendar, Drive) and feeds their data into the Graphiti knowledge graph.

Usage:
    python mcp_ingest.py          # continuous polling on each source's schedule
    python mcp_ingest.py --once   # single pass across all sources, then exit

Config: ~/.mikai/mcp_sources.yaml
State:  ~/.mikai/mcp_sync_state.json

NOTE: The MCP client API used here (mcp.client.stdio / mcp.client.session)
matches the mcp>=1.0 SDK. If the installed SDK version differs, the import
paths or context-manager signatures may need adjustment. The code documents
these touch-points with inline comments.
"""

import argparse
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import yaml  # pyyaml>=6.0

# Bring the sidecar package onto sys.path regardless of how this script is run.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType

# MCP client imports — exact paths depend on installed mcp SDK version.
# mcp>=1.0 ships these under mcp.client.*
try:
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp.client.session import ClientSession
except ImportError as _e:  # pragma: no cover
    raise ImportError(
        "MCP client libraries not found. Ensure mcp>=1.0 is installed.\n"
        f"Original error: {_e}"
    )

from sidecar.client import init_graphiti as _init_graphiti_client
from sidecar.ingest import (
    interpolate_tool_args,
    load_state as _load_state_at,
    save_state as _save_state_at,
)
from sidecar.rate_limit import bucket_for

logger = logging.getLogger("mikai-mcp-ingest")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# ── Paths ────────────────────────────────────────────────────────────────────

MIKAI_DIR = Path.home() / ".mikai"
CONFIG_PATH = MIKAI_DIR / "mcp_sources.yaml"
STATE_PATH = MIKAI_DIR / "mcp_sync_state.json"


# ── Graphiti initialization ──────────────────────────────────────────────────


async def init_graphiti() -> Graphiti:
    """Thin wrapper — delegates to the shared factory."""
    return await _init_graphiti_client()


# ── Checkpoint state ─────────────────────────────────────────────────────────


def load_state() -> dict[str, str]:
    """Load last-sync timestamps keyed by source name."""
    return _load_state_at(STATE_PATH)


def save_state(state: dict[str, str]) -> None:
    """Persist last-sync timestamps to disk."""
    _save_state_at(state, STATE_PATH)


# ── Config loading ────────────────────────────────────────────────────────────


TEMPLATE_CONFIG = """\
# MIKAI MCP source configuration
# Copy this file to ~/.mikai/mcp_sources.yaml and enable the sources you want.
# Each source spawns an MCP server subprocess via stdio.
#
# IMPORTANT: You must set up auth credentials for each source before enabling.
# Refer to each MCP server's README for environment variable requirements.

sources:

  # gmail:
  #   command: "npx"
  #   args: ["-y", "@anthropic-ai/gmail-mcp"]
  #   # Environment variables passed to the MCP server process.
  #   # Add your OAuth credentials here or set them in your shell environment.
  #   env: {}
  #   tool: "search_emails"
  #   tool_args:
  #     query: "newer_than:1d"
  #   schedule_minutes: 30
  #   group_id: "gmail"
  #   source_description: "gmail"

  # google_calendar:
  #   command: "npx"
  #   args: ["-y", "@anthropic-ai/google-calendar-mcp"]
  #   env: {}
  #   tool: "list_events"
  #   tool_args:
  #     time_min: "${LAST_SYNC}"
  #   schedule_minutes: 60
  #   group_id: "calendar"
  #   source_description: "google-calendar"

  # google_drive:
  #   command: "npx"
  #   args: ["-y", "@anthropic-ai/google-drive-mcp"]
  #   env: {}
  #   tool: "search_files"
  #   tool_args:
  #     query: "modifiedTime > '${LAST_SYNC}'"
  #   schedule_minutes: 60
  #   group_id: "drive"
  #   source_description: "google-drive"
"""


def load_config() -> dict:
    """Load mcp_sources.yaml. Create a template and exit if it doesn't exist."""
    if not CONFIG_PATH.exists():
        MIKAI_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(TEMPLATE_CONFIG)
        print(
            f"\nNo config found. A template has been created at:\n  {CONFIG_PATH}\n\n"
            "Edit that file to enable MCP sources (Gmail, Calendar, Drive),\n"
            "then re-run mcp_ingest.py.\n"
        )
        sys.exit(0)

    with CONFIG_PATH.open() as fh:
        cfg = yaml.safe_load(fh)

    if not cfg or not cfg.get("sources"):
        logger.warning(f"No sources defined in {CONFIG_PATH}. Nothing to do.")
        return {"sources": {}}

    return cfg


# ── MCP client poll ───────────────────────────────────────────────────────────


def _extract_text(content_item) -> str | None:
    """
    Extract plain text from a single MCP content item.

    The mcp SDK returns content items with a .type attribute. We handle the
    common 'text' type. Other types (image, resource) are skipped.
    """
    item_type = getattr(content_item, "type", None)
    if item_type == "text":
        return getattr(content_item, "text", None)
    # For structured content that may have a dict-like representation
    if isinstance(content_item, dict):
        if content_item.get("type") == "text":
            return content_item.get("text")
    return None


# ── Injectable collaborators (for tests) ──────────────────────────────────────
#
# poll_source() takes its external dependencies as keyword-only parameters.
# Production wiring uses the defaults below; tests pass in-memory fakes.


@asynccontextmanager
async def _default_stdio_session(command: str, args: list, env: dict):
    """Production session factory: stdio subprocess → MCP ClientSession."""
    server_params = StdioServerParameters(command=command, args=args, env=env)
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def poll_source(
    source_name: str,
    source_cfg: dict,
    graphiti: Graphiti,
    state: dict[str, str],
    *,
    session_factory=_default_stdio_session,
    now=_utc_now,
    state_path: Path = STATE_PATH,
    sleep=asyncio.sleep,
) -> None:
    """
    Connect to one MCP server, call its configured tool, and ingest results.

    Collaborators (`session_factory`, `now`, `state_path`, `sleep`) are
    injectable so the poll loop can be exercised without a subprocess,
    network, or wall-clock delay. Production callers rely on the defaults.
    """
    command = source_cfg.get("command", "npx")
    args = source_cfg.get("args", [])
    env_overrides: dict[str, str] = source_cfg.get("env") or {}
    tool_name = source_cfg.get("tool", "")
    tool_args_template: dict = source_cfg.get("tool_args") or {}
    group_id = source_cfg.get("group_id", source_name)
    source_description = source_cfg.get("source_description", source_name)

    if not tool_name:
        logger.warning(f"[{source_name}] No tool configured, skipping.")
        return

    last_sync = state.get(source_name)
    tool_args = interpolate_tool_args(tool_args_template, last_sync)

    # Merge caller's env overrides on top of the current process environment.
    merged_env = {**os.environ, **env_overrides}

    logger.info(
        f"[{source_name}] Polling via {command} {args} "
        f"| tool={tool_name} | last_sync={last_sync or 'never'}"
    )

    try:
        async with session_factory(command, args, merged_env) as session:
            result = await session.call_tool(tool_name, tool_args)
    except Exception as e:
        logger.error(
            f"[{source_name}] MCP server failed to start or tool call failed: {e}"
        )
        return

    # result.content is a list of content items (TextContent, ImageContent, etc.)
    content_items = getattr(result, "content", []) or []
    items_found = len(content_items)
    items_ingested = 0
    poll_time = now().isoformat()

    logger.info(f"[{source_name}] Items found: {items_found}")

    for item in content_items:
        text = _extract_text(item)
        if not text or not text.strip():
            continue

        await bucket_for("deepseek").acquire()
        await bucket_for("voyage").acquire()
        try:
            await graphiti.add_episode(
                name=f"{source_name}-{poll_time}",
                episode_body=text,
                source=EpisodeType.text,
                source_description=source_description,
                reference_time=now(),
                group_id=group_id,
            )
            items_ingested += 1
            logger.info(
                f"[{source_name}] Ingested item {items_ingested}/{items_found}"
            )
        except Exception as e:
            logger.error(f"[{source_name}] add_episode failed: {e}")

        # 2-second delay between add_episode calls to avoid overwhelming Neo4j.
        await sleep(2)

    # Update checkpoint to the poll time (even if 0 items — avoids re-fetching
    # the same empty window on next poll).
    state[source_name] = poll_time
    _save_state_at(state, state_path)

    logger.info(
        f"[{source_name}] Done. found={items_found} ingested={items_ingested} "
        f"checkpoint={poll_time}"
    )


# ── Scheduler ─────────────────────────────────────────────────────────────────


async def run_once(graphiti: Graphiti, sources: dict) -> None:
    """Poll every configured source once and exit."""
    state = load_state()
    for source_name, source_cfg in sources.items():
        await poll_source(source_name, source_cfg, graphiti, state)
    logger.info("--once pass complete.")


async def run_continuous(graphiti: Graphiti, sources: dict) -> None:
    """
    Run each source on its configured schedule_minutes interval, forever.

    Each source runs in its own asyncio task with its own sleep cycle so a
    slow source doesn't block the others.
    """
    state = load_state()

    async def source_loop(source_name: str, source_cfg: dict) -> None:
        interval_minutes = int(source_cfg.get("schedule_minutes", 30))
        interval_seconds = interval_minutes * 60
        while True:
            await poll_source(source_name, source_cfg, graphiti, state)
            logger.info(
                f"[{source_name}] Next poll in {interval_minutes} minutes."
            )
            await asyncio.sleep(interval_seconds)

    tasks = [
        asyncio.create_task(source_loop(name, cfg))
        for name, cfg in sources.items()
    ]

    logger.info(
        f"Continuous polling started for {len(tasks)} source(s). "
        "Press Ctrl-C to stop."
    )
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for t in tasks:
            t.cancel()
        logger.info("Polling cancelled.")


# ── Main ──────────────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="MIKAI MCP ingestion daemon — feeds cloud sources into Graphiti."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single poll pass across all sources, then exit.",
    )
    args = parser.parse_args()

    cfg = load_config()
    sources: dict = cfg.get("sources") or {}

    if not sources:
        logger.info("No enabled sources in config. Exiting.")
        return

    logger.info(
        f"Initializing Graphiti... (sources: {', '.join(sources.keys())})"
    )
    graphiti = await init_graphiti()

    try:
        if args.once:
            await run_once(graphiti, sources)
        else:
            await run_continuous(graphiti, sources)
    finally:
        await graphiti.close()
        logger.info("Graphiti connection closed.")


if __name__ == "__main__":
    asyncio.run(main())
