#!/usr/bin/env python3
"""
eval/seed_candidates.py — Stratified candidate seeder for Stage-6 eval.

Queries the live Neo4j graph and writes:
  eval/labeled_entities.jsonl  (target: 200 rows, stratified by entity type)
  eval/labeled_edges.jsonl     (target: 200 rows, stratified by edge type)

All rows are written with is_valid=null so Brian's labeling tool can fill them in.

Requires:
  NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD env vars (or .env file at repo root).

Usage:
  python eval/seed_candidates.py
  python eval/seed_candidates.py --entities-target 200 --edges-target 200
  python eval/seed_candidates.py --dry-run         # print stats, write nothing
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Allow running from repo root without installing anything
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "infra" / "graphiti"))

from eval.schemas import (
    KNOWN_EDGE_TYPES,
    KNOWN_ENTITY_TYPES,
    EdgeCandidate,
    EntityCandidate,
    SourceTag,
)

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_ENTITIES_TARGET = 200
DEFAULT_EDGES_TARGET = 200

# Excerpt max chars shown to labeler (keep it readable, not a wall of text)
EXCERPT_MAX_CHARS = 600

# Source-tag detection heuristics based on episode group_id prefix / name
_SOURCE_PREFIXES: dict[str, SourceTag] = {
    "claude": "claude_thread",
    "note": "apple_note",
    "gmail": "gmail_message",
    "mail": "gmail_message",
    "whatsapp": "whatsapp_day",
    "wa_": "whatsapp_day",
}


def _infer_source_tag(group_id: str) -> SourceTag:
    low = (group_id or "").lower()
    for prefix, tag in _SOURCE_PREFIXES.items():
        if prefix in low:
            return tag
    return "unknown"


def _truncate(text: str, max_chars: int = EXCERPT_MAX_CHARS) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + " …"


# ── Neo4j helpers ─────────────────────────────────────────────────────────────


def _get_driver():
    """Return a neo4j.GraphDatabase driver using env vars."""
    try:
        from neo4j import GraphDatabase
    except ImportError:
        sys.exit(
            "neo4j package not found. "
            "Run: pip install neo4j  (or use the venv at infra/graphiti/.venv)"
        )

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")
    return GraphDatabase.driver(uri, auth=(user, password))


# ── Entity sampling ───────────────────────────────────────────────────────────


def _fetch_entity_counts(driver) -> dict[str, int]:
    """Return {entity_type: count} for all entity types present in the graph."""
    query = """
    MATCH (n:Entity)
    WHERE n.name IS NOT NULL
    RETURN n.name_embedding_label AS label, count(*) AS cnt
    ORDER BY cnt DESC
    """
    # Graphiti stores the Pydantic class name in `name_embedding_label` on entity nodes.
    # Fall back to scanning labels if that property isn't present.
    counts: dict[str, int] = {}
    with driver.session() as session:
        result = session.run(query)
        for record in result:
            label = record.get("label") or "unknown"
            counts[label] = record.get("cnt", 0)
    if not counts:
        # Fallback: count by Neo4j labels (Graphiti adds the type as a label too)
        fallback = """
        MATCH (n:Entity)
        UNWIND labels(n) AS lbl
        WHERE lbl <> 'Entity'
        RETURN lbl, count(*) AS cnt
        ORDER BY cnt DESC
        """
        with driver.session() as session:
            result = session.run(fallback)
            for record in result:
                counts[record["lbl"]] = record["cnt"]
    return counts


def _sample_entities(driver, target: int) -> list[EntityCandidate]:
    """
    Stratified sample of entity candidates.

    Each type gets a quota proportional to its share of the graph, with a
    minimum of 1 per type that has at least 1 node. Total capped at `target`.
    """
    counts = _fetch_entity_counts(driver)
    if not counts:
        print("WARNING: no entity counts returned from Neo4j. Graph may be empty.")
        return []

    total_nodes = sum(counts.values())
    quotas: dict[str, int] = {}
    for etype, cnt in counts.items():
        quota = max(1, round(cnt / total_nodes * target))
        quotas[etype] = quota

    # Trim to target
    total_quota = sum(quotas.values())
    if total_quota > target:
        # Scale down proportionally
        scale = target / total_quota
        quotas = {k: max(1, round(v * scale)) for k, v in quotas.items()}

    candidates: list[EntityCandidate] = []
    for etype, quota in quotas.items():
        rows = _fetch_entities_for_type(driver, etype, quota)
        candidates.extend(rows)

    return candidates[:target]


def _fetch_entities_for_type(driver, etype: str, limit: int) -> list[EntityCandidate]:
    """Fetch up to `limit` entity nodes of a given type with their episode excerpts."""
    # Graphiti entity nodes have: uuid, name, summary, group_id
    # Episodes linked via (ep:Episodic)-[:MENTIONS]->(n:Entity)
    query = """
    MATCH (n:Entity)
    WHERE (n.name_embedding_label = $etype OR $etype IN labels(n))
      AND n.name IS NOT NULL
    WITH n
    ORDER BY rand()
    LIMIT $limit
    OPTIONAL MATCH (ep:Episodic)-[:MENTIONS]->(n)
    WITH n, ep
    ORDER BY ep.created_at DESC
    WITH n, collect(ep)[0] AS latest_ep
    RETURN
      n.uuid          AS node_uuid,
      n.name          AS name,
      n.summary       AS summary,
      n.group_id      AS group_id,
      latest_ep.uuid  AS episode_uuid,
      latest_ep.content AS episode_content
    LIMIT $limit
    """
    rows: list[EntityCandidate] = []
    with driver.session() as session:
        result = session.run(query, etype=etype, limit=limit)
        for record in result:
            rows.append(
                EntityCandidate(
                    node_uuid=str(record.get("node_uuid") or ""),
                    entity_type=etype,
                    name=str(record.get("name") or ""),
                    summary=str(record.get("summary") or ""),
                    source_excerpt=_truncate(
                        str(record.get("episode_content") or "")
                    ),
                    source_tag=_infer_source_tag(
                        str(record.get("group_id") or "")
                    ),
                    episode_uuid=str(record.get("episode_uuid") or ""),
                    is_valid=None,
                )
            )
    return rows


# ── Edge sampling ─────────────────────────────────────────────────────────────


def _fetch_edge_counts(driver) -> dict[str, int]:
    """Return {edge_type: count} for relationship types present in the graph."""
    query = """
    MATCH ()-[r]->()
    RETURN type(r) AS rel_type, count(*) AS cnt
    ORDER BY cnt DESC
    """
    counts: dict[str, int] = {}
    with driver.session() as session:
        result = session.run(query)
        for record in result:
            counts[record["rel_type"]] = record["cnt"]
    return counts


def _sample_edges(driver, target: int) -> list[EdgeCandidate]:
    """Stratified sample of edge candidates across relationship types."""
    counts = _fetch_edge_counts(driver)
    if not counts:
        print("WARNING: no edge counts returned from Neo4j.")
        return []

    total_edges = sum(counts.values())
    quotas: dict[str, int] = {}
    for etype, cnt in counts.items():
        quota = max(1, round(cnt / total_edges * target))
        quotas[etype] = quota

    total_quota = sum(quotas.values())
    if total_quota > target:
        scale = target / total_quota
        quotas = {k: max(1, round(v * scale)) for k, v in quotas.items()}

    candidates: list[EdgeCandidate] = []
    for etype, quota in quotas.items():
        rows = _fetch_edges_for_type(driver, etype, quota)
        candidates.extend(rows)

    return candidates[:target]


def _fetch_edges_for_type(driver, etype: str, limit: int) -> list[EdgeCandidate]:
    """Fetch up to `limit` edges of a given type with endpoints and episode excerpt."""
    query = f"""
    MATCH (src:Entity)-[r:{etype}]->(tgt:Entity)
    WHERE src.name IS NOT NULL AND tgt.name IS NOT NULL
    WITH src, r, tgt
    ORDER BY rand()
    LIMIT $limit
    OPTIONAL MATCH (ep:Episodic)-[:MENTIONS]->(src)
    WITH src, r, tgt, ep
    ORDER BY ep.created_at DESC
    WITH src, r, tgt, collect(ep)[0] AS latest_ep
    RETURN
      r.uuid          AS edge_uuid,
      type(r)         AS edge_type,
      src.name        AS source_name,
      src.name_embedding_label AS source_type,
      tgt.name        AS target_name,
      tgt.name_embedding_label AS target_type,
      r.fact          AS fact,
      r.weight        AS confidence,
      src.group_id    AS group_id,
      latest_ep.uuid  AS episode_uuid,
      latest_ep.content AS episode_content
    LIMIT $limit
    """
    rows: list[EdgeCandidate] = []
    with driver.session() as session:
        result = session.run(query, limit=limit)
        for record in result:
            rows.append(
                EdgeCandidate(
                    edge_uuid=str(record.get("edge_uuid") or ""),
                    edge_type=str(record.get("edge_type") or etype),
                    source_name=str(record.get("source_name") or ""),
                    source_type=str(record.get("source_type") or "Entity"),
                    target_name=str(record.get("target_name") or ""),
                    target_type=str(record.get("target_type") or "Entity"),
                    fact=str(record.get("fact") or ""),
                    confidence=float(record.get("confidence") or 1.0),
                    source_excerpt=_truncate(
                        str(record.get("episode_content") or "")
                    ),
                    source_tag=_infer_source_tag(
                        str(record.get("group_id") or "")
                    ),
                    episode_uuid=str(record.get("episode_uuid") or ""),
                    is_valid=None,
                )
            )
    return rows


# ── Writer ────────────────────────────────────────────────────────────────────


def _append_jsonl(path: Path, records: list) -> None:
    """Append records as JSONL to path (creates file if absent)."""
    with path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(rec.model_dump_json() + "\n")


def _write_jsonl(path: Path, records: list) -> None:
    """Overwrite path with records as JSONL."""
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(rec.model_dump_json() + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed Stage-6 eval candidates from the live Neo4j graph."
    )
    parser.add_argument(
        "--entities-target",
        type=int,
        default=DEFAULT_ENTITIES_TARGET,
        metavar="N",
        help=f"Target entity candidates (default: {DEFAULT_ENTITIES_TARGET})",
    )
    parser.add_argument(
        "--edges-target",
        type=int,
        default=DEFAULT_EDGES_TARGET,
        metavar="N",
        help=f"Target edge candidates (default: {DEFAULT_EDGES_TARGET})",
    )
    parser.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "eval"),
        metavar="DIR",
        help="Directory to write JSONL files (default: eval/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts only; write nothing.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    entities_path = out_dir / "labeled_entities.jsonl"
    edges_path = out_dir / "labeled_edges.jsonl"

    # Load .env if present
    dotenv_path = REPO_ROOT / ".env"
    if dotenv_path.exists():
        for line in dotenv_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    print("Connecting to Neo4j…")
    driver = _get_driver()

    print(f"Sampling {args.entities_target} entity candidates (stratified)…")
    entity_candidates = _sample_entities(driver, args.entities_target)
    print(f"  → {len(entity_candidates)} entity candidates")

    print(f"Sampling {args.edges_target} edge candidates (stratified)…")
    edge_candidates = _sample_edges(driver, args.edges_target)
    print(f"  → {len(edge_candidates)} edge candidates")

    driver.close()

    # Entity type breakdown
    from collections import Counter

    etype_counts = Counter(c.entity_type for c in entity_candidates)
    print("\nEntity type breakdown:")
    for etype, cnt in sorted(etype_counts.items(), key=lambda x: -x[1]):
        print(f"  {etype:30s} {cnt}")

    edge_type_counts = Counter(c.edge_type for c in edge_candidates)
    print("\nEdge type breakdown:")
    for etype, cnt in sorted(edge_type_counts.items(), key=lambda x: -x[1]):
        print(f"  {etype:30s} {cnt}")

    if args.dry_run:
        print("\n[dry-run] Nothing written.")
        return 0

    # Skip already-seeded rows (resumable: don't re-seed if file exists)
    if entities_path.exists():
        existing_uuids = set()
        for line in entities_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    existing_uuids.add(json.loads(line)["node_uuid"])
                except (json.JSONDecodeError, KeyError):
                    pass
        entity_candidates = [
            c for c in entity_candidates if c.node_uuid not in existing_uuids
        ]
        print(f"\n{len(entity_candidates)} new entity rows to append (deduped).")
    else:
        print(f"\nWriting {len(entity_candidates)} entity rows.")

    if edges_path.exists():
        existing_uuids = set()
        for line in edges_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    existing_uuids.add(json.loads(line)["edge_uuid"])
                except (json.JSONDecodeError, KeyError):
                    pass
        edge_candidates = [
            c for c in edge_candidates if c.edge_uuid not in existing_uuids
        ]
        print(f"{len(edge_candidates)} new edge rows to append (deduped).")
    else:
        print(f"Writing {len(edge_candidates)} edge rows.")

    _append_jsonl(entities_path, entity_candidates)
    _append_jsonl(edges_path, edge_candidates)

    print(f"\nWrote: {entities_path}")
    print(f"Wrote: {edges_path}")
    print("\nNext: run  python eval/label.py  to label candidates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
