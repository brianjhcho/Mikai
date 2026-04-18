"""MIKAI L3 MCP tools — FastMCP wrapper mounted inside the sidecar FastAPI app.

Exposes four L3-only tools backed by the same Graphiti singleton the REST
sidecar uses:
  search       — Hybrid search (vec + BM25 + RRF) over the knowledge graph
  get_history  — Bitemporal point-in-time query with current/superseded split
  add_note     — Save an insight as a Graphiti episode
  get_stats    — Graph quality snapshot (entity/edge/episode/community/orphan)

No L4 tools (tensions, threads, brief, next_steps) per D-041 — those land on
the feat/l4-engine branch once product semantics are settled.

The tools read Graphiti via a getter closure passed in at construction. This
avoids circular imports between main.py (owns the singleton) and this module.
"""

import logging
import time
from datetime import datetime
from typing import Callable, NamedTuple

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType

logger = logging.getLogger("mikai-graphiti")


class MCPBundle(NamedTuple):
    mcp: FastMCP
    tool_names: list[str]


def _iso(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        return v.isoformat()
    except AttributeError:
        return str(v)


def build_mcp(get_graphiti: Callable[[], Graphiti | None]) -> MCPBundle:
    """Construct a FastMCP app bound to the sidecar's Graphiti singleton.

    The returned instance exposes .streamable_http_app() for ASGI mount.
    streamable_http_path is set to "/" so mounting at "/mcp" yields the
    canonical endpoint at /mcp (not /mcp/mcp).
    """
    mcp = FastMCP("mikai")
    mcp.settings.streamable_http_path = "/"
    # DNS rebinding protection rejects Host headers it doesn't recognize.
    # Claude.ai and Claude mobile connect through Anthropic's cloud and hit us
    # via whatever public URL is fronting the sidecar (Tailscale Funnel,
    # Cloudflare Tunnel, etc.) — that Host value is not knowable at build time.
    # Turn off DNS rebinding protection; authentication (OAuth or bearer) is
    # the real security boundary for public exposure.
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    )

    @mcp.tool(
        description=(
            "Search MIKAI's knowledge graph. Returns facts (edges) connecting "
            "entities, ranked by relevance via hybrid search (vector + BM25 + "
            "reciprocal rank fusion)."
        )
    )
    async def search(query: str, num_results: int = 10) -> str:
        t0 = time.perf_counter()
        try:
            g = get_graphiti()
            if not g:
                return "Graphiti not initialized"

            edges = await g.search(query=query, num_results=num_results)
            if not edges:
                return f"No results for: {query}"

            lines = [f"## Search results for: {query}\n"]
            for i, e in enumerate(edges, 1):
                src = getattr(e, "source_node_name", None) or "?"
                tgt = getattr(e, "target_node_name", None) or "?"
                fact = e.fact or "(no fact text)"
                valid = _iso(e.valid_at)
                lines.append(f"**{i}.** {src} → {tgt}")
                lines.append(f"   {fact}")
                if valid:
                    lines.append(f"   _Valid since: {valid}_")
                if e.invalid_at:
                    lines.append(f"   _Invalidated: {_iso(e.invalid_at)}_")
                lines.append("")

            result = "\n".join(lines)
            logger.info("mcp_tool=search args=[query, num_results] duration_ms=%.1f status=ok", (time.perf_counter() - t0) * 1000)
            return result
        except Exception as exc:
            logger.info("mcp_tool=search args=[query, num_results] duration_ms=%.1f status=error error=%s(%s)", (time.perf_counter() - t0) * 1000, type(exc).__name__, exc)
            raise

    @mcp.tool(
        description=(
            "Query how the knowledge graph looked at a specific point in time. "
            "Returns current facts and superseded (invalidated) facts separately, "
            "so you can see how beliefs have evolved. Pass as_of as an ISO datetime "
            "(e.g. '2026-03-15T00:00:00') or omit for the current state."
        )
    )
    async def get_history(
        query: str, as_of: str | None = None, num_results: int = 10
    ) -> str:
        t0 = time.perf_counter()
        try:
            g = get_graphiti()
            if not g:
                return "Graphiti not initialized"

            edges = await g.search(query=query, num_results=num_results * 3)
            as_of_dt = datetime.fromisoformat(as_of) if as_of else None
            current: list = []
            superseded: list = []

            for e in edges:
                valid_at = e.valid_at
                invalid_at = e.invalid_at

                if as_of_dt is not None:
                    is_valid = (valid_at is None or valid_at <= as_of_dt) and (
                        invalid_at is None or invalid_at > as_of_dt
                    )
                    if is_valid:
                        current.append(e)
                    elif invalid_at is not None and (
                        valid_at is None or valid_at <= as_of_dt
                    ):
                        superseded.append(e)
                else:
                    (current if invalid_at is None else superseded).append(e)

            lines: list[str] = []
            timestamp_label = f" (as of {as_of})" if as_of else ""

            if current[:num_results]:
                lines.append(f"## Current facts{timestamp_label}\n")
                for e in current[:num_results]:
                    src = getattr(e, "source_node_name", None) or "?"
                    tgt = getattr(e, "target_node_name", None) or "?"
                    lines.append(f"- **{src} → {tgt}**: {e.fact or '(no fact)'}")

            if superseded[:num_results]:
                lines.append(f"\n## Superseded facts{timestamp_label}\n")
                for e in superseded[:num_results]:
                    src = getattr(e, "source_node_name", None) or "?"
                    tgt = getattr(e, "target_node_name", None) or "?"
                    lines.append(
                        f"- ~~{src} → {tgt}: {e.fact or '(no fact)'}~~ "
                        f"_(invalidated {_iso(e.invalid_at)})_"
                    )

            if not lines:
                lines.append(f"No facts found for: {query}")

            result = "\n".join(lines)
            logger.info("mcp_tool=get_history args=[query, as_of, num_results] duration_ms=%.1f status=ok", (time.perf_counter() - t0) * 1000)
            return result
        except Exception as exc:
            logger.info("mcp_tool=get_history args=[query, as_of, num_results] duration_ms=%.1f status=error error=%s(%s)", (time.perf_counter() - t0) * 1000, type(exc).__name__, exc)
            raise

    @mcp.tool(
        description=(
            "Save a note or insight into the knowledge graph as a new episode. "
            "Graphiti extracts entities and relationships automatically."
        )
    )
    async def add_note(
        content: str, source_description: str = "claude-conversation"
    ) -> str:
        t0 = time.perf_counter()
        try:
            g = get_graphiti()
            if not g:
                return "Graphiti not initialized"

            if not content.strip():
                return "Empty note — nothing saved."

            result = await g.add_episode(
                name=source_description,
                episode_body=content,
                source=EpisodeType.text,
                source_description=source_description,
                reference_time=datetime.now(),
                group_id="mikai-default",
            )

            episode_id = str(result.episode.uuid) if result and result.episode else "?"
            nodes = len(result.nodes) if result and result.nodes else 0
            edges = len(result.edges) if result and result.edges else 0

            output = (
                f"Saved to knowledge graph.\n"
                f"- Episode: {episode_id}\n"
                f"- Entities extracted: {nodes}\n"
                f"- Relationships created: {edges}"
            )
            logger.info("mcp_tool=add_note args=[content, source_description] duration_ms=%.1f status=ok", (time.perf_counter() - t0) * 1000)
            return output
        except Exception as exc:
            logger.info("mcp_tool=add_note args=[content, source_description] duration_ms=%.1f status=error error=%s(%s)", (time.perf_counter() - t0) * 1000, type(exc).__name__, exc)
            raise

    @mcp.tool(
        description=(
            "Get a snapshot of the knowledge graph: how many entities, edges, "
            "episodes, communities, and orphan nodes exist."
        )
    )
    async def get_stats() -> str:
        t0 = time.perf_counter()
        try:
            g = get_graphiti()
            if not g:
                return "Graphiti not initialized"

            driver = getattr(g.driver, "driver", g.driver)
            async with driver.session() as session:
                result = await session.run("""
                    CALL {
                        MATCH (n:Entity) RETURN count(n) AS entity_count
                    }
                    CALL {
                        MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS edge_count
                    }
                    CALL {
                        MATCH (e:Episodic) RETURN count(e) AS episode_count
                    }
                    CALL {
                        MATCH (c:Community) RETURN count(c) AS community_count
                    }
                    CALL {
                        MATCH (n:Entity)
                        WHERE NOT (n)-[:RELATES_TO]-()
                        RETURN count(n) AS orphan_count
                    }
                    RETURN entity_count, edge_count, episode_count, community_count, orphan_count
                """)
                rows = [record.data() async for record in result]

            if not rows:
                return "Could not fetch graph stats."

            r = rows[0]
            entities = r.get("entity_count", 0)
            edge_count = r.get("edge_count", 0)
            episodes = r.get("episode_count", 0)
            communities = r.get("community_count", 0)
            orphans = r.get("orphan_count", 0)
            orphan_pct = f"{orphans / entities * 100:.1f}" if entities > 0 else "0"

            output = (
                f"## MIKAI Knowledge Graph\n\n"
                f"| Metric | Count |\n"
                f"|--------|-------|\n"
                f"| Entities | {entities:,} |\n"
                f"| Relationships | {edge_count:,} |\n"
                f"| Episodes | {episodes:,} |\n"
                f"| Communities | {communities:,} |\n"
                f"| Orphan entities | {orphans:,} ({orphan_pct}%) |"
            )
            logger.info("mcp_tool=get_stats args=[] duration_ms=%.1f status=ok", (time.perf_counter() - t0) * 1000)
            return output
        except Exception as exc:
            logger.info("mcp_tool=get_stats args=[] duration_ms=%.1f status=error error=%s(%s)", (time.perf_counter() - t0) * 1000, type(exc).__name__, exc)
            raise

    return MCPBundle(mcp=mcp, tool_names=["search", "get_history", "add_note", "get_stats"])
