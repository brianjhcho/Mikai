"""MIKAI L3 MCP tools — FastMCP wrapper mounted inside the sidecar FastAPI app.

Exposes five L3-only tools backed by the L3Backend port (ARCH-024):
  search       — Hybrid edge search (vec + BM25 + RRF), with recency decay
  get_history  — Bitemporal point-in-time query with current/superseded split
  add_note     — Save an insight as a new episode
  get_stats    — Graph quality snapshot (entity/edge/episode/community/orphan)
  get_source   — Raw source-episode prose for a query (D-045)

No L4 tools (tensions, threads, brief, next_steps) per D-041 — those land on
the feat/l4-engine branch once product semantics are settled.

The tools read the backend via a getter closure passed in at construction.
This avoids circular imports between main.py (owns the singleton) and this
module, and keeps mcp_tools agnostic to which adapter is plugged in
(Graphiti today, LocalAdapter eventually per ARCH-025).
"""

import logging
import time
from datetime import datetime
from typing import Callable, NamedTuple

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from sidecar.l3 import Episode, L3Backend, SearchQuery
from sidecar.recency import apply_recency_decay

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


def build_mcp(get_backend: Callable[[], L3Backend | None]) -> MCPBundle:
    """Construct a FastMCP app bound to the sidecar's L3Backend singleton.

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
            "reciprocal rank fusion). Pass recency_decay=false to disable "
            "time-based re-ranking and return Graphiti's raw ordering."
        )
    )
    async def search(
        query: str, num_results: int = 10, recency_decay: bool = True
    ) -> str:
        t0 = time.perf_counter()
        try:
            backend = get_backend()
            if not backend:
                return "L3 backend not initialized"

            edges = await backend.search(
                SearchQuery(text=query, num_results=num_results)
            )
            if recency_decay:
                edges = apply_recency_decay(edges, reference_time=datetime.now())
            logger.info(
                "mcp_tool=search query=%r num_results=%d results=%d duration_ms=%.1f status=ok",
                query, num_results, len(edges), (time.perf_counter() - t0) * 1000,
            )
            if not edges:
                return f"No results for: {query}"

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

            return "\n".join(lines)
        except Exception as exc:
            logger.info("mcp_tool=search query=%r duration_ms=%.1f status=error error=%s(%s)", query, (time.perf_counter() - t0) * 1000, type(exc).__name__, exc)
            raise

    @mcp.tool(
        description=(
            "Query how the knowledge graph looked at a specific point in time. "
            "Returns current facts and superseded (invalidated) facts separately, "
            "so you can see how beliefs have evolved. Pass as_of as an ISO datetime "
            "(e.g. '2026-03-15T00:00:00') or omit for the current state. "
            "Pass recency_decay=false to disable time-based re-ranking."
        )
    )
    async def get_history(
        query: str,
        as_of: str | None = None,
        num_results: int = 10,
        recency_decay: bool = True,
    ) -> str:
        t0 = time.perf_counter()
        try:
            backend = get_backend()
            if not backend:
                return "L3 backend not initialized"

            as_of_dt = datetime.fromisoformat(as_of) if as_of else None
            history = await backend.history(
                SearchQuery(text=query, num_results=num_results),
                as_of=as_of_dt,
            )
            if recency_decay:
                history_current = apply_recency_decay(
                    history.current, reference_time=datetime.now()
                )
                history_superseded = apply_recency_decay(
                    history.superseded, reference_time=datetime.now()
                )
            else:
                history_current = history.current
                history_superseded = history.superseded

            lines: list[str] = []
            timestamp_label = f" (as of {as_of})" if as_of else ""

            if history_current[:num_results]:
                lines.append(f"## Current facts{timestamp_label}\n")
                for e in history_current[:num_results]:
                    src = e.source_name or "?"
                    tgt = e.target_name or "?"
                    lines.append(f"- **{src} → {tgt}**: {e.fact or '(no fact)'}")

            if history_superseded[:num_results]:
                lines.append(f"\n## Superseded facts{timestamp_label}\n")
                for e in history_superseded[:num_results]:
                    src = e.source_name or "?"
                    tgt = e.target_name or "?"
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
            backend = get_backend()
            if not backend:
                return "L3 backend not initialized"

            if not content.strip():
                return "Empty note — nothing saved."

            result = await backend.ingest_episode(Episode(
                content=content,
                source_description=source_description,
                reference_time=datetime.now(),
                group_id="mikai-default",
                name=source_description,
            ))

            output = (
                f"Saved to knowledge graph.\n"
                f"- Episode: {result.episode_uuid or '?'}\n"
                f"- Entities extracted: {result.entities_extracted}\n"
                f"- Relationships created: {result.edges_extracted}"
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
            backend = get_backend()
            if not backend:
                return "L3 backend not initialized"

            s = await backend.stats()
            orphan_pct = (
                f"{s.orphans / s.entities * 100:.1f}" if s.entities > 0 else "0"
            )
            output = (
                f"## MIKAI Knowledge Graph\n\n"
                f"| Metric | Count |\n"
                f"|--------|-------|\n"
                f"| Entities | {s.entities:,} |\n"
                f"| Relationships | {s.edges:,} |\n"
                f"| Episodes | {s.episodes:,} |\n"
                f"| Communities | {s.communities:,} |\n"
                f"| Orphan entities | {s.orphans:,} ({orphan_pct}%) |"
            )
            logger.info("mcp_tool=get_stats args=[] duration_ms=%.1f status=ok", (time.perf_counter() - t0) * 1000)
            return output
        except Exception as exc:
            logger.info("mcp_tool=get_stats args=[] duration_ms=%.1f status=error error=%s(%s)", (time.perf_counter() - t0) * 1000, type(exc).__name__, exc)
            raise

    @mcp.tool(
        description=(
            "Retrieve the original source episode prose for a query. Returns "
            "the raw content of the top-K matching episodes (notes, "
            "conversations, excerpts) ranked by full-text relevance — not "
            "the LLM-summarized edge facts that `search` returns. Use this "
            "when the user asks 'what have I written about X' or wants to "
            "read their own words back rather than compressed claims. Each "
            "result includes the source label and reference time."
        )
    )
    async def get_source(query: str, num_results: int = 5) -> str:
        t0 = time.perf_counter()
        try:
            backend = get_backend()
            if not backend:
                return "L3 backend not initialized"

            if not query.strip():
                return "Empty query — nothing to retrieve."

            episodes = await backend.get_source(query, num_results=num_results)
            logger.info(
                "mcp_tool=get_source query=%r num_results=%d results=%d duration_ms=%.1f status=ok",
                query, num_results, len(episodes), (time.perf_counter() - t0) * 1000,
            )
            if not episodes:
                return f"No source episodes found for: {query}"

            lines = [f"## Source episodes for: {query}\n"]
            for i, ep in enumerate(episodes, 1):
                label = ep.source_description or ep.source or "episode"
                ref_time = _iso(ep.valid_at)
                content = (ep.content or "").strip()
                lines.append(f"### {i}. {label}")
                if ref_time:
                    lines.append(f"_{ref_time}_")
                lines.append("")
                lines.append(content if content else "_(empty content)_")
                lines.append("")

            return "\n".join(lines)
        except Exception as exc:
            logger.info("mcp_tool=get_source query=%r duration_ms=%.1f status=error error=%s(%s)", query, (time.perf_counter() - t0) * 1000, type(exc).__name__, exc)
            raise

    return MCPBundle(
        mcp=mcp,
        tool_names=["search", "get_history", "add_note", "get_stats", "get_source"],
    )
