#!/usr/bin/env python3
"""
Stage 4 — retrieval-groundedness rater for L3 queries (O-020).

Runs each query in QUERIES against the live graph via graphiti-core's
search API, prints the top-K results alongside their citation episode
text, and prompts the human reviewer for two scores:

  - relevance_at_k   0..K  count of results judged relevant to the query
  - groundedness     1-5   are the citations actually supported by the
                            episode text, or hallucinated fits?

Results append to docs/evals/queries-{YYYY-MM-DD}.md as a markdown table.
Re-running on the same day appends; never overwrites.

Mirrors the structure of scripts/eval_nodes.py — pure helpers split out
from the interactive shell, GraphProbe protocol so tests pass a fake.

Usage:
    python scripts/eval_queries.py
    python scripts/eval_queries.py --backend graphiti --top-k 10
    python scripts/eval_queries.py --backend local        # NotImplementedError
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "infra" / "graphiti"))

# Re-use the eval_nodes init path — single source of truth for client
# config (DeepSeek + Voyage + the patched-graphiti scaling clamp).
from eval_nodes import init_graphiti, run_cypher  # type: ignore  # noqa: E402

logger = logging.getLogger("mikai-eval-queries")
logging.basicConfig(level=logging.INFO, format="%(message)s")

EVALS_DIR = REPO_ROOT / "docs" / "evals"


# ── Starter query set ────────────────────────────────────────────────────────
#
# These probe areas the corpus is known to cover (Apple Notes monthly logs,
# Claude Code threads about MIKAI). Calibrate for your own graph by running
# `python scripts/eval_queries.py --print-queries` and editing the list.

QUERIES: list[str] = [
    "What have I been working on with MIKAI?",
    "Poker strategy notes",
    "Trading thesis 2024-2025",
    "Product ideas I've written down",
    "Jobs or roles I've considered",
    "Coffee preferences and rituals",
    "Tennis training and matches",
    "Reading list — books I want to read",
    "Travel plans or trips",
    "Apple Notes architecture",
]


# ── Domain types ─────────────────────────────────────────────────────────────


@dataclass
class SearchHit:
    """One result for one query — keep flat so render is mechanical."""
    rank: int
    fact: str
    source_node_name: str
    target_node_name: str
    valid_at: str | None
    episode_uuid: str | None
    episode_content: str | None


@dataclass
class QueryRun:
    query: str
    hits: list[SearchHit]


@dataclass
class QueryRating:
    run: QueryRun
    relevance_at_k: int   # 0..k, count of hits the human judged relevant
    groundedness: int     # 1..5, are citations supported by the cited text?
    note: str


# ── Backend abstraction ──────────────────────────────────────────────────────


class GraphProbe(Protocol):
    """Read-only graph access the eval needs. Production wraps a Graphiti
    client; tests pass a fake."""
    async def search(self, query: str, top_k: int) -> list[dict]: ...
    async def fetch_citation_episode(self, edge_uuid: str) -> dict | None: ...


class GraphitiProbe:
    """GraphProbe backed by a live graphiti-core / Neo4j connection."""

    def __init__(self, graphiti):
        self._g = graphiti

    async def search(self, query: str, top_k: int) -> list[dict]:
        # graphiti.search returns EntityEdge objects (the "fact" rows). Each
        # carries an episodes list pointing back to the source episodes that
        # caused the edge to be extracted — that's what gives us groundedness.
        edges = await self._g.search(query=query, num_results=top_k)
        out: list[dict] = []
        for i, edge in enumerate(edges, 1):
            out.append({
                "rank": i,
                "fact": getattr(edge, "fact", "") or "",
                "source_node_name": getattr(edge, "source_node_name", "") or "",
                "target_node_name": getattr(edge, "target_node_name", "") or "",
                "valid_at": (
                    getattr(edge, "valid_at", None).isoformat()
                    if getattr(edge, "valid_at", None) else None
                ),
                "episodes": list(getattr(edge, "episodes", []) or []),
            })
        return out

    async def fetch_citation_episode(self, episode_uuid: str) -> dict | None:
        rows = await run_cypher(
            self._g,
            """
            MATCH (e:Episodic {uuid: $uuid})
            RETURN e.uuid AS uuid,
                   e.name AS name,
                   e.content AS content,
                   coalesce(e.source_description, '') AS source_description
            LIMIT 1
            """,
            uuid=episode_uuid,
        )
        return rows[0] if rows else None


# ── Pure helpers (testable without a live driver) ────────────────────────────


def to_hit(row: dict, episode: dict | None) -> SearchHit:
    return SearchHit(
        rank=int(row["rank"]),
        fact=str(row.get("fact") or ""),
        source_node_name=str(row.get("source_node_name") or ""),
        target_node_name=str(row.get("target_node_name") or ""),
        valid_at=row.get("valid_at"),
        episode_uuid=str(episode["uuid"]) if episode else None,
        episode_content=str(episode["content"]) if episode else None,
    )


def format_query_card(
    run: QueryRun, *, max_episode_chars: int = 600,
) -> str:
    """Pretty-print a query + its top-K hits for the reviewer's terminal."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"Query:   {run.query}")
    lines.append(f"Hits:    {len(run.hits)}")
    lines.append("")
    if not run.hits:
        lines.append("(no results)")
        lines.append("=" * 72)
        return "\n".join(lines)

    for h in run.hits:
        edge = f"{h.source_node_name} → {h.target_node_name}"
        when = f" [{h.valid_at}]" if h.valid_at else ""
        lines.append(f"  #{h.rank}  {edge}{when}")
        lines.append(f"        {h.fact}")
        if h.episode_content:
            body = h.episode_content
            if len(body) > max_episode_chars:
                body = body[:max_episode_chars] + f"... [+{len(h.episode_content) - max_episode_chars} chars]"
            lines.append(f"        cite: {body}")
        else:
            lines.append("        cite: (no episode loaded)")
        lines.append("")
    lines.append("=" * 72)
    return "\n".join(lines)


def render_results_md(
    ratings: list[QueryRating], *, when: date, backend: str, top_k: int,
) -> str:
    """Render a markdown table fragment to append to the daily eval doc."""
    lines: list[str] = []
    lines.append(
        f"## Run — {when.isoformat()} ({backend}, queries={len(ratings)}, k={top_k})"
    )
    lines.append("")
    lines.append("| # | query | relevance@k | groundedness | hits | note |")
    lines.append("|---|---|---|---|---|---|")
    for i, r in enumerate(ratings, 1):
        q = (r.run.query or "").replace("|", "\\|")
        note = (r.note or "").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {i} | {q} | {r.relevance_at_k}/{top_k} | "
            f"{r.groundedness} | {len(r.run.hits)} | {note} |"
        )
    if ratings:
        rel = [r.relevance_at_k for r in ratings]
        gnd = [r.groundedness for r in ratings]
        lines.append("")
        lines.append(
            f"**Run mean:** relevance={sum(rel)/len(rel):.2f}/{top_k}, "
            f"groundedness={sum(gnd)/len(gnd):.2f}"
        )
    lines.append("")
    return "\n".join(lines)


def append_results_md(
    path: Path, body: str, *, when: date, backend: str,
) -> None:
    """Append a run section. If the file is new, prepend a doc header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        header = (
            f"# Query-retrieval eval — {when.isoformat()}\n\n"
            f"**Backend:** `{backend}`. Per O-020: relevance@k counts hits "
            f"a human judges relevant to the query (0..k); groundedness is "
            f"1-5 on whether each result's citation supports the claimed "
            f"fact.\n\n"
        )
        path.write_text(header, encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(body)


# ── Backend dispatch ─────────────────────────────────────────────────────────


async def open_graphiti_probe() -> tuple[GraphitiProbe, Callable[[], Awaitable[None]]]:
    g = await init_graphiti()

    async def _close() -> None:
        await g.close()

    return GraphitiProbe(g), _close


async def open_probe(backend: str) -> tuple[GraphProbe, Callable[[], Awaitable[None]]]:
    if backend == "graphiti":
        return await open_graphiti_probe()
    if backend == "local":
        raise NotImplementedError(
            "LocalAdapter (ARCH-025) is in design — Stage 6 will plug it in here."
        )
    raise ValueError(f"unknown backend: {backend}")


# ── Sample collection (testable) ─────────────────────────────────────────────


async def collect_runs(
    probe: GraphProbe, queries: list[str], top_k: int,
) -> list[QueryRun]:
    """Run every query through the probe; resolve each hit's citation."""
    runs: list[QueryRun] = []
    for q in queries:
        rows = await probe.search(q, top_k=top_k)
        hits: list[SearchHit] = []
        for row in rows:
            # Pick the first cited episode — gives reviewer enough context
            # without flooding the terminal with every overlapping citation.
            episodes = row.get("episodes") or []
            ep = await probe.fetch_citation_episode(str(episodes[0])) if episodes else None
            hits.append(to_hit(row, ep))
        runs.append(QueryRun(query=q, hits=hits))
    return runs


# ── Interactive prompt (not tested — needs a human) ──────────────────────────


def _prompt_int(label: str, lo: int, hi: int) -> int:
    while True:
        raw = input(f"  {label} ({lo}-{hi}, q to skip run): ").strip()
        if raw.lower() == "q":
            raise KeyboardInterrupt
        try:
            v = int(raw)
        except ValueError:
            print(f"  please enter an integer {lo}-{hi}")
            continue
        if lo <= v <= hi:
            return v
        print(f"  out of range; expected {lo}-{hi}")


def rate_interactively(runs: list[QueryRun], top_k: int) -> list[QueryRating]:
    ratings: list[QueryRating] = []
    for i, run in enumerate(runs, 1):
        print()
        print(f"[{i}/{len(runs)}]")
        print(format_query_card(run))
        if not run.hits:
            print("  (skipping — no hits to rate)")
            continue
        try:
            rel = _prompt_int("relevance @ k", 0, top_k)
            gnd = _prompt_int("groundedness", 1, 5)
        except KeyboardInterrupt:
            print("\nAborted; partial run will not be saved.")
            return []
        note = input("  note (optional, single line): ").strip()
        ratings.append(QueryRating(
            run=run, relevance_at_k=rel, groundedness=gnd, note=note,
        ))
    return ratings


# ── CLI ──────────────────────────────────────────────────────────────────────


async def _main_async(args: argparse.Namespace) -> int:
    if args.print_queries:
        for q in QUERIES:
            print(q)
        return 0

    probe, close = await open_probe(args.backend)
    try:
        runs = await collect_runs(probe, QUERIES, args.top_k)
    finally:
        await close()

    ratings = rate_interactively(runs, args.top_k)
    if not ratings:
        return 1

    body = render_results_md(
        ratings, when=date.today(), backend=args.backend, top_k=args.top_k,
    )
    out_path = EVALS_DIR / f"queries-{date.today().isoformat()}.md"
    append_results_md(out_path, body, when=date.today(), backend=args.backend)
    print(f"\nAppended {len(ratings)} rating(s) to {out_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rate L3 retrieval-groundedness on a fixed query set (O-020).",
    )
    parser.add_argument("--top-k", type=int, default=10,
                        help="Top results per query to rate (default 10).")
    parser.add_argument("--backend", choices=("graphiti", "local"),
                        default="graphiti",
                        help="L3 backend to evaluate (default graphiti).")
    parser.add_argument("--print-queries", action="store_true",
                        help="Print the built-in query set and exit.")
    args = parser.parse_args()
    sys.exit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
