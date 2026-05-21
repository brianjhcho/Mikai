"""GraphitiAdapter — L3Backend implementation backed by graphiti-core + Neo4j.

Wraps the previously-direct graphiti / Cypher calls behind the L3Backend
port (ARCH-024). The composition root (`sidecar/main.py` lifespan) reads
MIKAI_L3_BACKEND and instantiates this adapter when value == "graphiti"
(default).

Graphiti-specific concerns kept inside this module:
  - graphiti-core imports (Graphiti, EpisodeType, search recipes)
  - Cypher templates and raw driver session usage
  - Extraction-schema routing (entity_types / edge_types / edge_type_map
    via sidecar.extraction.router)
  - DeepSeek/Voyage cost shaping via the rate-limit token buckets

Nothing in this module is exported to product code — they go through
the L3Backend ABC.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.graphiti import RawEpisode
from graphiti_core.nodes import EpisodeType
from graphiti_core.search.search_config_recipes import (
    COMBINED_HYBRID_SEARCH_RRF,
)

from sidecar.client import run_cypher as _run_cypher_on
from sidecar.extraction.router import extraction_params_for as _extraction_params_for
from sidecar.l3.port import (
    L3Backend,
    Community,
    Edge,
    Episode,
    GraphStats,
    HistoryResult,
    IngestResult,
    Node,
    SearchQuery,
    SourceEpisode,
    Subgraph,
)
from sidecar.rate_limit import bucket_for

logger = logging.getLogger("mikai-graphiti")


def _parse_dt(v: Any) -> datetime | None:
    """Graphiti returns datetimes as Neo4j DateTime or ISO strings — normalize."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None


def _edge_from_graphiti(e, *, score: float | None = None) -> Edge:
    """Translate a graphiti-core EntityEdge into the port's Edge."""
    return Edge(
        uuid=str(e.uuid),
        source_uuid=str(getattr(e, "source_node_uuid", "") or ""),
        target_uuid=str(getattr(e, "target_node_uuid", "") or ""),
        source_name=getattr(e, "source_node_name", None),
        target_name=getattr(e, "target_node_name", None),
        name=getattr(e, "name", None) or "RELATES_TO",
        fact=getattr(e, "fact", None),
        valid_at=_parse_dt(getattr(e, "valid_at", None)),
        invalid_at=_parse_dt(getattr(e, "invalid_at", None)),
        expired_at=_parse_dt(getattr(e, "expired_at", None)),
        created_at=_parse_dt(getattr(e, "created_at", None)),
        episodes=[str(ep) for ep in (getattr(e, "episodes", None) or [])],
        confidence=getattr(e, "confidence", None),
        score=score,
    )


def _node_from_row(row: dict) -> Node:
    """Translate a Cypher row (uuid/name/labels/summary/created_at) into Node."""
    return Node(
        uuid=str(row.get("uuid") or ""),
        name=row.get("name") or "",
        labels=[lbl for lbl in (row.get("labels") or []) if lbl != "Entity"],
        summary=row.get("summary"),
        created_at=_parse_dt(row.get("created_at")),
    )


class GraphitiAdapter(L3Backend):
    """L3Backend backed by graphiti-core + Neo4j (the production runtime)."""

    def __init__(self, graphiti: Graphiti):
        self._g = graphiti
        self._closed = False

    @property
    def graphiti(self) -> Graphiti:
        """Escape hatch for migration. Product code should NOT use this —
        anything reaching for it is a port-extraction TODO."""
        return self._g

    # ── Write ────────────────────────────────────────────────────────────────

    async def ingest_episode(self, episode: Episode) -> IngestResult:
        # Per Stage 6 (D-049): extraction params are derived from
        # source_description here, inside the adapter — product code stays
        # schema-agnostic per ARCH-024.
        params = _extraction_params_for(episode.source_description)
        # Rate-limit DeepSeek (extraction LLM) and Voyage (embeddings).
        await bucket_for("deepseek").acquire()
        await bucket_for("voyage").acquire()
        result = await self._g.add_episode(
            name=episode.name or episode.source_description,
            episode_body=episode.content,
            source=EpisodeType.text,
            source_description=episode.source_description,
            reference_time=episode.reference_time,
            group_id=episode.group_id,
            **params,
        )
        return IngestResult(
            episode_uuid=str(result.episode.uuid) if result and result.episode else "",
            entities_extracted=len(result.nodes) if result and result.nodes else 0,
            edges_extracted=len(result.edges) if result and result.edges else 0,
        )

    async def ingest_episode_bulk(self, episodes: list[Episode]) -> IngestResult:
        """Bulk ingest — exposed beyond the abstract port because the production
        REST endpoint /episode/bulk takes the batch path. Future adapters may
        override; default implementations can loop one-at-a-time."""
        raw_episodes = [
            RawEpisode(
                name=ep.name or ep.source_description,
                content=ep.content,
                source=EpisodeType.text,
                source_description=ep.source_description,
                reference_time=ep.reference_time,
            )
            for ep in episodes
        ]
        group_id = episodes[0].group_id if episodes else "mikai-default"
        result = await self._g.add_episode_bulk(
            bulk_episodes=raw_episodes, group_id=group_id,
        )
        return IngestResult(
            episode_uuid="(bulk)",
            entities_extracted=len(result.nodes) if result and result.nodes else 0,
            edges_extracted=len(result.edges) if result and result.edges else 0,
        )

    # ── Read — edges ─────────────────────────────────────────────────────────

    async def search(self, query: SearchQuery) -> list[Edge]:
        edges = await self._g.search(
            query=query.text,
            group_ids=query.group_ids,
            num_results=query.num_results,
        )
        # Graphiti's search assigns scores via RRF; preserve if present.
        return [
            _edge_from_graphiti(e, score=getattr(e, "score", None))
            for e in edges or []
        ]

    async def history(
        self, query: SearchQuery, as_of: datetime | None = None
    ) -> HistoryResult:
        # Over-fetch so the bitemporal post-filter has material to work with.
        edges = await self._g.search(
            query=query.text,
            group_ids=query.group_ids,
            num_results=query.num_results * 3,
        )
        current: list[Edge] = []
        superseded: list[Edge] = []
        for e in edges or []:
            valid_at = _parse_dt(getattr(e, "valid_at", None))
            invalid_at = _parse_dt(getattr(e, "invalid_at", None))
            wrapped = _edge_from_graphiti(e)
            if as_of is not None:
                is_valid = (
                    (valid_at is None or valid_at <= as_of)
                    and (invalid_at is None or invalid_at > as_of)
                )
                if is_valid:
                    current.append(wrapped)
                elif (
                    invalid_at is not None
                    and (valid_at is None or valid_at <= as_of)
                ):
                    superseded.append(wrapped)
            else:
                (current if invalid_at is None else superseded).append(wrapped)
        return HistoryResult(
            current=current[: query.num_results],
            superseded=superseded[: query.num_results],
        )

    async def edges_between(
        self,
        node_uuids: list[str],
        *,
        as_of: datetime | None = None,
        include_invalidated: bool = False,
    ) -> list[Edge]:
        if not node_uuids:
            return []
        rows = await _run_cypher_on(self._g, """
            MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
            WHERE a.uuid IN $uuids AND b.uuid IN $uuids
                AND ($include_invalidated OR r.invalid_at IS NULL)
                AND (
                    $as_of IS NULL
                    OR (
                        r.valid_at <= datetime($as_of)
                        AND (r.invalid_at IS NULL OR r.invalid_at > datetime($as_of))
                    )
                )
            RETURN
                r.uuid AS uuid,
                a.uuid AS source_uuid,
                b.uuid AS target_uuid,
                a.name AS source_name,
                b.name AS target_name,
                r.name AS name,
                r.fact AS fact,
                r.valid_at AS valid_at,
                r.invalid_at AS invalid_at,
                r.expired_at AS expired_at,
                r.created_at AS created_at,
                r.episodes AS episodes,
                r.confidence AS confidence
        """,
            uuids=node_uuids,
            include_invalidated=include_invalidated,
            as_of=as_of.isoformat() if as_of else None,
        )
        return [
            Edge(
                uuid=str(r.get("uuid") or ""),
                source_uuid=str(r.get("source_uuid") or ""),
                target_uuid=str(r.get("target_uuid") or ""),
                source_name=r.get("source_name"),
                target_name=r.get("target_name"),
                name=r.get("name") or "RELATES_TO",
                fact=r.get("fact"),
                valid_at=_parse_dt(r.get("valid_at")),
                invalid_at=_parse_dt(r.get("invalid_at")),
                expired_at=_parse_dt(r.get("expired_at")),
                created_at=_parse_dt(r.get("created_at")),
                episodes=[str(ep) for ep in (r.get("episodes") or [])],
                confidence=r.get("confidence"),
            )
            for r in rows
        ]

    # ── Read — nodes ─────────────────────────────────────────────────────────

    async def search_nodes(self, query: SearchQuery) -> list[Node]:
        try:
            from graphiti_core.search.search_config_recipes import (
                NODE_HYBRID_SEARCH_RRF,
            )
            config = NODE_HYBRID_SEARCH_RRF
        except ImportError:
            config = COMBINED_HYBRID_SEARCH_RRF
        results = await self._g.search_(
            query=query.text, config=config, group_ids=query.group_ids,
        )
        nodes = (results.nodes or []) if results else []
        return [
            Node(
                uuid=str(n.uuid),
                name=getattr(n, "name", "") or "",
                labels=list(getattr(n, "labels", []) or []),
                summary=getattr(n, "summary", None),
                created_at=_parse_dt(getattr(n, "created_at", None)),
            )
            for n in nodes[: query.num_results]
        ]

    async def get_node(self, uuid: str) -> Node | None:
        rows = await _run_cypher_on(self._g, """
            MATCH (n:Entity {uuid: $uuid})
            RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels,
                   n.summary AS summary, n.created_at AS created_at
        """, uuid=uuid)
        return _node_from_row(rows[0]) if rows else None

    async def expand(
        self,
        uuid: str,
        *,
        max_edges: int = 20,
        include_invalidated: bool = False,
    ) -> Subgraph:
        rows = await _run_cypher_on(self._g, """
            MATCH (center:Entity {uuid: $uuid})
            OPTIONAL MATCH (center)-[r:RELATES_TO]-(neighbor:Entity)
            WHERE ($include_invalidated OR r.expired_at IS NULL)
            WITH center, r, neighbor
            LIMIT $max_edges
            RETURN
                center.uuid AS center_uuid, center.name AS center_name,
                labels(center) AS center_labels, center.summary AS center_summary,
                center.created_at AS center_created_at,
                neighbor.uuid AS neighbor_uuid, neighbor.name AS neighbor_name,
                labels(neighbor) AS neighbor_labels,
                neighbor.summary AS neighbor_summary,
                neighbor.created_at AS neighbor_created_at,
                r.uuid AS edge_uuid,
                startNode(r).uuid AS source_uuid, endNode(r).uuid AS target_uuid,
                startNode(r).name AS source_name, endNode(r).name AS target_name,
                r.name AS edge_name, r.fact AS fact,
                r.valid_at AS valid_at, r.invalid_at AS invalid_at,
                r.expired_at AS expired_at, r.created_at AS edge_created_at,
                r.episodes AS episodes, r.confidence AS confidence
        """, uuid=uuid, max_edges=max_edges,
            include_invalidated=include_invalidated)
        if not rows:
            raise KeyError(f"Node {uuid} not found")
        first = rows[0]
        center = Node(
            uuid=first.get("center_uuid") or uuid,
            name=first.get("center_name") or "",
            labels=[
                lbl for lbl in (first.get("center_labels") or []) if lbl != "Entity"
            ],
            summary=first.get("center_summary"),
            created_at=_parse_dt(first.get("center_created_at")),
        )
        nodes_by_uuid: dict[str, Node] = {}
        edges: list[Edge] = []
        for r in rows:
            if not r.get("neighbor_uuid"):
                continue
            nuid = r["neighbor_uuid"]
            if nuid not in nodes_by_uuid:
                nodes_by_uuid[nuid] = Node(
                    uuid=nuid,
                    name=r.get("neighbor_name") or "",
                    labels=[
                        lbl for lbl in (r.get("neighbor_labels") or [])
                        if lbl != "Entity"
                    ],
                    summary=r.get("neighbor_summary"),
                    created_at=_parse_dt(r.get("neighbor_created_at")),
                )
            if r.get("edge_uuid"):
                edges.append(Edge(
                    uuid=str(r["edge_uuid"]),
                    source_uuid=str(r.get("source_uuid") or ""),
                    target_uuid=str(r.get("target_uuid") or ""),
                    source_name=r.get("source_name"),
                    target_name=r.get("target_name"),
                    name=r.get("edge_name") or "RELATES_TO",
                    fact=r.get("fact"),
                    valid_at=_parse_dt(r.get("valid_at")),
                    invalid_at=_parse_dt(r.get("invalid_at")),
                    expired_at=_parse_dt(r.get("expired_at")),
                    created_at=_parse_dt(r.get("edge_created_at")),
                    episodes=[str(ep) for ep in (r.get("episodes") or [])],
                    confidence=r.get("confidence"),
                ))
        return Subgraph(
            center=center,
            nodes=list(nodes_by_uuid.values()),
            edges=edges,
        )

    # ── Read — raw episodes ──────────────────────────────────────────────────

    async def get_source(
        self, query: str, num_results: int = 5
    ) -> list[SourceEpisode]:
        if not query.strip():
            return []
        # graphiti's existing fulltext index over Episodic content.
        driver = getattr(self._g.driver, "driver", self._g.driver)
        rows: list[dict] = []
        async with driver.session() as session:
            # phrase → quoted phrase → OR-split fallback
            for lucene_q in (query, f'"{query}"', query.replace(" ", " OR ")):
                result = await session.run(
                    """
                    CALL db.index.fulltext.queryNodes("episode_content", $q)
                    YIELD node, score
                    RETURN
                        node.uuid AS uuid,
                        node.content AS content,
                        node.source AS source,
                        node.source_description AS source_description,
                        node.valid_at AS reference_time,
                        score
                    ORDER BY score DESC
                    LIMIT $limit
                    """,
                    q=lucene_q,
                    limit=num_results,
                )
                rows = [record.data() async for record in result]
                if rows:
                    break
        return [
            SourceEpisode(
                uuid=str(r.get("uuid") or ""),
                content=(r.get("content") or "").strip(),
                source=str(r.get("source") or ""),
                source_description=str(r.get("source_description") or ""),
                valid_at=_parse_dt(r.get("reference_time")),
                score=r.get("score"),
            )
            for r in rows
        ]

    # ── Read — global ────────────────────────────────────────────────────────

    async def stats(self) -> GraphStats:
        rows = await _run_cypher_on(self._g, """
            CALL { MATCH (n:Entity) RETURN count(n) AS entity_count }
            CALL { MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS edge_count }
            CALL { MATCH (e:Episodic) RETURN count(e) AS episode_count }
            CALL { MATCH (c:Community) RETURN count(c) AS community_count }
            CALL {
                MATCH (n:Entity) WHERE NOT (n)-[:RELATES_TO]-()
                RETURN count(n) AS orphan_count
            }
            RETURN entity_count, edge_count, episode_count,
                   community_count, orphan_count
        """)
        if not rows:
            return GraphStats(0, 0, 0, 0, 0)
        r = rows[0]
        return GraphStats(
            entities=int(r.get("entity_count", 0)),
            edges=int(r.get("edge_count", 0)),
            episodes=int(r.get("episode_count", 0)),
            communities=int(r.get("community_count", 0)),
            orphans=int(r.get("orphan_count", 0)),
        )

    async def communities(self) -> list[Community]:
        try:
            results = await self._g.search_(
                query="", config=COMBINED_HYBRID_SEARCH_RRF
            )
            return [
                Community(uuid=str(c.uuid), name=c.name, summary=c.summary)
                for c in (results.communities or [])
            ]
        except Exception as exc:
            logger.warning("communities() failed: %s", exc)
            return []

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def close(self) -> None:
        if self._closed:
            return
        await self._g.close()
        self._closed = True
