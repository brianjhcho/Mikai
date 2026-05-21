"""
MIKAI MCP Server — Python stdio server for Claude Desktop.

Exposes four L3-only tools backed by Graphiti + Neo4j:
  search     — Hybrid search (vec + BM25 + RRF) over the knowledge graph
  get_history — Bitemporal point-in-time query with current/superseded split
  add_note   — Save an insight as a Graphiti episode
  get_stats  — Graph quality snapshot (entity/edge/episode/community/orphan counts)

No L4 tools (tensions, threads, brief, next_steps) — those will be built
in a separate L4 engine branch once the product semantics are designed.

Runs in-process with graphiti-core: no HTTP hop to the FastAPI sidecar.
The sidecar remains available for debugging and future non-MCP surfaces.

Usage:
    python sidecar/mcp_server.py

Claude Desktop config (~/.claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "mikai": {
          "command": "/path/to/infra/graphiti/.venv/bin/python",
          "args": ["/path/to/infra/graphiti/sidecar/mcp_server.py"],
          "env": {
            "DEEPSEEK_API_KEY": "sk-...",
            "VOYAGE_API_KEY": "pa-...",
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_USER": "neo4j",
            "NEO4J_PASSWORD": "mikai-local-dev"
          }
        }
      }
    }
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# When Claude Desktop launches this script directly, `sidecar` isn't on the
# path. Add the parent dir so `from sidecar.client import ...` works both when
# run as a module and as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from sidecar.client import iso_or_empty as _iso
from sidecar.l3 import Episode, L3Backend, SearchQuery, make_backend

logger = logging.getLogger("mikai-mcp")
logging.basicConfig(level=logging.INFO)


# ── L3 backend initialization ────────────────────────────────────────────────

backend: L3Backend | None = None


# ── MCP Server ───────────────────────────────────────────────────────────────

server = Server("mikai")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search",
            description=(
                "Search MIKAI's knowledge graph. Returns facts (edges) "
                "connecting entities, ranked by relevance via hybrid "
                "search (vector + BM25 + reciprocal rank fusion)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for in the knowledge graph",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_history",
            description=(
                "Query how the knowledge graph looked at a specific point "
                "in time. Returns current facts and superseded (invalidated) "
                "facts separately, so you can see how beliefs have evolved."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for",
                    },
                    "as_of": {
                        "type": "string",
                        "description": (
                            "ISO datetime to query the graph state at "
                            "(e.g. '2026-03-15T00:00:00'). Omit for current state."
                        ),
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Max results per category (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="add_note",
            description=(
                "Save a note or insight into the knowledge graph as a new "
                "episode. Graphiti will extract entities and relationships "
                "automatically."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The text content to save",
                    },
                    "source_description": {
                        "type": "string",
                        "description": "Label for the source (default 'claude-conversation')",
                        "default": "claude-conversation",
                    },
                },
                "required": ["content"],
            },
        ),
        types.Tool(
            name="get_stats",
            description=(
                "Get a snapshot of the knowledge graph: how many entities, "
                "edges, episodes, communities, and orphan nodes exist."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent]:
    args = arguments or {}

    if name == "search":
        return await _tool_search(args)
    elif name == "get_history":
        return await _tool_get_history(args)
    elif name == "add_note":
        return await _tool_add_note(args)
    elif name == "get_stats":
        return await _tool_get_stats()
    else:
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


# ── Tool implementations ────────────────────────────────────────────────────


async def _tool_search(args: dict) -> list[types.TextContent]:
    if not backend:
        return [types.TextContent(type="text", text="L3 backend not initialized")]

    query = args.get("query", "")
    num_results = args.get("num_results", 10)

    edges = await backend.search(SearchQuery(text=query, num_results=num_results))

    if not edges:
        return [types.TextContent(type="text", text=f"No results for: {query}")]

    lines = [f"## Search results for: {query}\n"]
    for i, e in enumerate(edges, 1):
        src = e.source_name or "?"
        tgt = e.target_name or "?"
        fact = e.fact or "(no fact text)"
        valid = _iso(e.valid_at)
        lines.append(f"**{i}.** {src} → {tgt}")
        lines.append(f"   {fact}")
        if valid:
            lines.append(f"   _Valid since: {valid}_")
        if e.invalid_at:
            lines.append(f"   _Invalidated: {_iso(e.invalid_at)}_")
        lines.append("")

    return [types.TextContent(type="text", text="\n".join(lines))]


async def _tool_get_history(args: dict) -> list[types.TextContent]:
    if not backend:
        return [types.TextContent(type="text", text="L3 backend not initialized")]

    query = args.get("query", "")
    as_of_str = args.get("as_of")
    num_results = args.get("num_results", 10)
    as_of_dt = datetime.fromisoformat(as_of_str) if as_of_str else None

    history = await backend.history(
        SearchQuery(text=query, num_results=num_results), as_of=as_of_dt,
    )

    lines = []
    timestamp_label = f" (as of {as_of_str})" if as_of_str else ""

    if history.current[:num_results]:
        lines.append(f"## Current facts{timestamp_label}\n")
        for e in history.current[:num_results]:
            src = e.source_name or "?"
            tgt = e.target_name or "?"
            lines.append(f"- **{src} → {tgt}**: {e.fact or '(no fact)'}")

    if history.superseded[:num_results]:
        lines.append(f"\n## Superseded facts{timestamp_label}\n")
        for e in history.superseded[:num_results]:
            src = e.source_name or "?"
            tgt = e.target_name or "?"
            lines.append(
                f"- ~~{src} → {tgt}: {e.fact or '(no fact)'}~~ "
                f"_(invalidated {_iso(e.invalid_at)})_"
            )

    if not lines:
        lines.append(f"No facts found for: {query}")

    return [types.TextContent(type="text", text="\n".join(lines))]


async def _tool_add_note(args: dict) -> list[types.TextContent]:
    if not backend:
        return [types.TextContent(type="text", text="L3 backend not initialized")]

    content = args.get("content", "")
    source_desc = args.get("source_description", "claude-conversation")

    if not content.strip():
        return [types.TextContent(type="text", text="Empty note — nothing saved.")]

    result = await backend.ingest_episode(Episode(
        content=content,
        source_description=source_desc,
        reference_time=datetime.now(),
        group_id="mikai-default",
        name=source_desc,
    ))

    return [
        types.TextContent(
            type="text",
            text=(
                f"Saved to knowledge graph.\n"
                f"- Episode: {result.episode_uuid or '?'}\n"
                f"- Entities extracted: {result.entities_extracted}\n"
                f"- Relationships created: {result.edges_extracted}"
            ),
        )
    ]


async def _tool_get_stats() -> list[types.TextContent]:
    if not backend:
        return [
            types.TextContent(type="text", text="L3 backend not initialized")
        ]
    s = await backend.stats()
    orphan_pct = (
        f"{s.orphans / s.entities * 100:.1f}" if s.entities > 0 else "0"
    )
    return [
        types.TextContent(
            type="text",
            text=(
                f"## MIKAI Knowledge Graph\n\n"
                f"| Metric | Count |\n"
                f"|--------|-------|\n"
                f"| Entities | {s.entities:,} |\n"
                f"| Relationships | {s.edges:,} |\n"
                f"| Episodes | {s.episodes:,} |\n"
                f"| Communities | {s.communities:,} |\n"
                f"| Orphan entities | {s.orphans:,} ({orphan_pct}%) |"
            ),
        )
    ]


# ── Main ─────────────────────────────────────────────────────────────────────


async def main():
    global backend

    logger.info("MIKAI MCP server starting...")
    backend = await make_backend()

    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("MCP stdio transport ready")
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        if backend:
            await backend.close()
            logger.info("L3 backend closed")


if __name__ == "__main__":
    asyncio.run(main())
