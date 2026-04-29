#!/usr/bin/env python3
"""
Stage 4 — extraction-quality rater for L3 nodes (O-020).

Picks N random EntityNodes, prints each node alongside the source episode
text that introduced it (Episodic-MENTIONS->Entity per graphiti-core), and
prompts the human reviewer for two ratings:

  - accuracy        1-5  does this node faithfully represent the source?
  - non_obviousness 1-5  did extraction add real signal vs. naive keyword index?

Results append to docs/evals/nodes-{YYYY-MM-DD}.md as a markdown table —
re-running on the same day appends new rows, never overwrites.

The data-fetching layer is split out into pure functions (`pick_nodes`,
`fetch_source_episode`, `format_node_card`, `append_results_md`) so the
interactive CLI shell stays a thin orchestrator. Tests mock the graph
driver and exercise the pure functions; the rating prompt itself is not
tested — it requires a live human.

Usage:
    python scripts/eval_nodes.py --n 10
    python scripts/eval_nodes.py --backend graphiti --n 5
    python scripts/eval_nodes.py --backend local        # raises NotImplementedError
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "infra" / "graphiti"))

# `sidecar/main.py` carries the canonical DeepSeekClient + PassthroughReranker
# wiring. We import them so this eval harness shares the same patched-graphiti
# stack the live sidecar uses; no second source of truth for client config.
from sidecar.main import DeepSeekClient, PassthroughReranker  # type: ignore

from graphiti_core import Graphiti
from graphiti_core.embedder.voyage import VoyageAIEmbedder, VoyageAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig

logger = logging.getLogger("mikai-eval-nodes")
logging.basicConfig(level=logging.INFO, format="%(message)s")

EVALS_DIR = REPO_ROOT / "docs" / "evals"


# ── Graphiti construction (mirrors sidecar/main.py) ──────────────────────────


def _require_env(var: str) -> str:
    import os
    val = os.environ.get(var)
    if not val:
        raise RuntimeError(f"{var} required")
    return val


async def init_graphiti() -> Graphiti:
    import os
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "mikai-local-dev")

    llm_client = DeepSeekClient(
        config=LLMConfig(
            api_key=_require_env("DEEPSEEK_API_KEY"),
            model="deepseek-chat",
            small_model="deepseek-chat",
            base_url="https://api.deepseek.com",
        ),
        max_tokens=8192,
    )
    embedder = VoyageAIEmbedder(config=VoyageAIEmbedderConfig(
        api_key=_require_env("VOYAGE_API_KEY"),
        model="voyage-3",
    ))
    g = Graphiti(
        neo4j_uri, neo4j_user, neo4j_password,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=PassthroughReranker(),
    )
    # Read-only eval — skip build_indices_and_constraints to keep this fast
    # and to make sure we never accidentally mutate schema during a rating run.
    return g


async def run_cypher(graphiti: Graphiti, query: str, **params) -> list[dict]:
    """Execute a raw Cypher query against Graphiti's underlying neo4j driver."""
    driver = getattr(graphiti.driver, "driver", graphiti.driver)
    async with driver.session() as session:
        result = await session.run(query, **params)
        return [record.data() async for record in result]


# ── Domain types ─────────────────────────────────────────────────────────────


@dataclass
class NodeSample:
    """A node + the source-episode text that introduced it. `episode_*` may
    be None when the node has no MENTIONS edge (orphan or community-only)."""
    uuid: str
    name: str
    labels: list[str]
    summary: str
    attributes: dict[str, Any]
    episode_uuid: str | None
    episode_name: str | None
    episode_content: str | None
    episode_source_description: str | None


@dataclass
class NodeRating:
    sample: NodeSample
    accuracy: int
    non_obviousness: int
    note: str


# ── Backend abstraction ──────────────────────────────────────────────────────


class GraphProbe(Protocol):
    """Read-only graph access — anything that can answer the two queries we
    need. Production wraps a Graphiti client; tests pass a fake."""
    async def total_entity_count(self) -> int: ...
    async def fetch_random_entities(self, n: int) -> list[dict]: ...
    async def fetch_source_episode(self, entity_uuid: str) -> dict | None: ...


class GraphitiProbe:
    """GraphProbe backed by a live graphiti-core / Neo4j connection."""

    def __init__(self, graphiti):
        self._g = graphiti

    async def total_entity_count(self) -> int:
        rows = await run_cypher(
            self._g,
            "MATCH (n:Entity) RETURN count(n) AS c",
        )
        return int(rows[0]["c"]) if rows else 0

    async def fetch_random_entities(self, n: int) -> list[dict]:
        # rand() per row + ORDER is fine at ~7K nodes; for larger graphs the
        # standard trick is reservoir sampling, but we don't need it yet.
        rows = await run_cypher(
            self._g,
            """
            MATCH (n:Entity)
            WITH n, rand() AS r
            ORDER BY r
            LIMIT $n
            RETURN n.uuid AS uuid,
                   n.name AS name,
                   labels(n) AS labels,
                   coalesce(n.summary, '') AS summary,
                   properties(n) AS props
            """,
            n=n,
        )
        return rows

    async def fetch_source_episode(self, entity_uuid: str) -> dict | None:
        # Earliest mentioning episode — gives the introduction context.
        # MENTIONS is the canonical Episodic→Entity edge in graphiti-core.
        rows = await run_cypher(
            self._g,
            """
            MATCH (e:Episodic)-[:MENTIONS]->(n:Entity {uuid: $uuid})
            RETURN e.uuid AS uuid,
                   e.name AS name,
                   e.content AS content,
                   coalesce(e.source_description, '') AS source_description,
                   e.valid_at AS valid_at
            ORDER BY e.valid_at ASC
            LIMIT 1
            """,
            uuid=entity_uuid,
        )
        return rows[0] if rows else None


# ── Pure helpers (testable without a live driver) ────────────────────────────


def pick_nodes(rows: list[dict], n: int, *, rng: random.Random | None = None) -> list[dict]:
    """If the driver returned more rows than asked for (defensive — Cypher
    LIMIT should already cap), trim deterministically when an rng is given."""
    if len(rows) <= n:
        return list(rows)
    rng = rng or random.Random()
    return rng.sample(rows, n)


def to_sample(node_row: dict, episode_row: dict | None) -> NodeSample:
    """Combine a node row + (optional) episode row into a single NodeSample."""
    props = dict(node_row.get("props") or {})
    # Strip the noisy / structural keys from the attributes view.
    for k in ("uuid", "name", "name_embedding", "summary", "group_id",
              "created_at", "labels"):
        props.pop(k, None)

    return NodeSample(
        uuid=str(node_row.get("uuid") or ""),
        name=str(node_row.get("name") or ""),
        labels=list(node_row.get("labels") or []),
        summary=str(node_row.get("summary") or ""),
        attributes=props,
        episode_uuid=str(episode_row["uuid"]) if episode_row else None,
        episode_name=str(episode_row["name"]) if episode_row else None,
        episode_content=str(episode_row["content"]) if episode_row else None,
        episode_source_description=(
            str(episode_row["source_description"]) if episode_row else None
        ),
    )


def format_node_card(sample: NodeSample, *, max_episode_chars: int = 1200) -> str:
    """Pretty-print a NodeSample for the reviewer's terminal. Trims long
    episode bodies — full content lives in the graph for re-fetch."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"Node:    {sample.name}")
    lines.append(f"UUID:    {sample.uuid}")
    lines.append(f"Labels:  {', '.join(sample.labels) or '(none)'}")
    if sample.summary:
        lines.append(f"Summary: {sample.summary}")
    if sample.attributes:
        kv = ", ".join(f"{k}={v!r}" for k, v in sample.attributes.items())
        lines.append(f"Attrs:   {kv}")
    lines.append("")
    if sample.episode_content is None:
        lines.append("Source episode: (none — orphan or community-only)")
    else:
        body = sample.episode_content
        if len(body) > max_episode_chars:
            body = body[:max_episode_chars] + f"\n... [+{len(sample.episode_content) - max_episode_chars} chars]"
        src = sample.episode_source_description or "(no source_description)"
        lines.append(f"Source episode [{src}] {sample.episode_name or ''}")
        lines.append("-" * 72)
        lines.append(body)
    lines.append("=" * 72)
    return "\n".join(lines)


def render_results_md(
    ratings: list[NodeRating], *, when: date, backend: str,
) -> str:
    """Render a markdown table fragment to append to the daily eval doc.

    Includes a fenced header per run so multiple runs on the same day stay
    readable as separate sections.
    """
    lines: list[str] = []
    lines.append(f"## Run — {when.isoformat()} ({backend}, n={len(ratings)})")
    lines.append("")
    lines.append("| # | node name | labels | accuracy | non-obviousness | note |")
    lines.append("|---|---|---|---|---|---|")
    for i, r in enumerate(ratings, 1):
        labels = ",".join(r.sample.labels) or "—"
        # Pipe characters in node names would break the table — escape them.
        name = (r.sample.name or "").replace("|", "\\|")
        note = (r.note or "").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {i} | {name} | {labels} | {r.accuracy} | {r.non_obviousness} | {note} |"
        )
    if ratings:
        acc = [r.accuracy for r in ratings]
        nob = [r.non_obviousness for r in ratings]
        lines.append("")
        lines.append(
            f"**Run mean:** accuracy={sum(acc)/len(acc):.2f}, "
            f"non-obviousness={sum(nob)/len(nob):.2f}"
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
            f"# Node-extraction eval — {when.isoformat()}\n\n"
            f"**Backend:** `{backend}`. Per O-020: 1-5 ratings on accuracy "
            f"(does the node faithfully represent the source?) and "
            f"non-obviousness (would a naive keyword index find this?).\n\n"
        )
        path.write_text(header, encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(body)


# ── Backend dispatch ─────────────────────────────────────────────────────────


async def open_graphiti_probe() -> tuple[GraphitiProbe, Callable[[], Awaitable[None]]]:
    g = await _init_graphiti_client()

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


async def collect_samples(probe: GraphProbe, n: int) -> list[NodeSample]:
    """Pull n random entities + their first source episode."""
    total = await probe.total_entity_count()
    if total == 0:
        logger.warning("Graph contains no Entity nodes — nothing to rate.")
        return []
    if n > total:
        logger.warning(
            "Requested n=%d exceeds graph size %d; using %d.", n, total, total,
        )
        n = total

    rows = await probe.fetch_random_entities(n)
    samples: list[NodeSample] = []
    for row in rows:
        episode = await probe.fetch_source_episode(str(row["uuid"]))
        samples.append(to_sample(row, episode))
    return samples


# ── Interactive prompt (not tested — needs a human) ──────────────────────────


def _prompt_int(label: str, lo: int = 1, hi: int = 5) -> int:
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


def rate_interactively(samples: list[NodeSample]) -> list[NodeRating]:
    ratings: list[NodeRating] = []
    for i, s in enumerate(samples, 1):
        print()
        print(f"[{i}/{len(samples)}]")
        print(format_node_card(s))
        try:
            acc = _prompt_int("accuracy")
            nob = _prompt_int("non-obviousness")
        except KeyboardInterrupt:
            print("\nAborted; partial run will not be saved.")
            return []
        note = input("  note (optional, single line): ").strip()
        ratings.append(NodeRating(
            sample=s, accuracy=acc, non_obviousness=nob, note=note,
        ))
    return ratings


# ── CLI ──────────────────────────────────────────────────────────────────────


async def _main_async(args: argparse.Namespace) -> int:
    probe, close = await open_probe(args.backend)
    try:
        samples = await collect_samples(probe, args.n)
    finally:
        await close()

    if not samples:
        return 1

    ratings = rate_interactively(samples)
    if not ratings:
        return 1

    body = render_results_md(ratings, when=date.today(), backend=args.backend)
    out_path = EVALS_DIR / f"nodes-{date.today().isoformat()}.md"
    append_results_md(out_path, body, when=date.today(), backend=args.backend)
    print(f"\nAppended {len(ratings)} rating(s) to {out_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rate L3 entity-extraction quality (O-020).",
    )
    parser.add_argument("--n", type=int, default=10,
                        help="Number of random entities to rate (default 10).")
    parser.add_argument("--backend", choices=("graphiti", "local"),
                        default="graphiti",
                        help="L3 backend to evaluate (default graphiti).")
    args = parser.parse_args()
    sys.exit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
