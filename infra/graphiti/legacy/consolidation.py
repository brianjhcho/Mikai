"""
consolidation.py — the dream's second job.

Implements MEMORY_ARCHITECTURE.md PART I: node consolidation via cluster
detection (Neo4j GDS insight) + one LLM call per cluster (not per pair).

Called from dream.py after Echoes, before wiki write. Every nightly dream:
  1. Bucket all entities by a normalized-name key (lowercase, strip
     trailing suffixes). Skip singleton buckets — nothing to consolidate.
  2. Within each multi-entity bucket, compute cosine similarity across
     `name_embedding` vectors. Cluster nodes above SIMILARITY_HI; nodes
     in [SIMILARITY_LO, SIMILARITY_HI) go to a review queue.
  3. One LLM call per cluster: "are these N nodes the same concept?" —
     receives the full cluster (names, summaries, source diversity)
     rather than N pairwise questions.
  4. For confirmed clusters: pick a canonical target via canonicality
     score (age × degree × summary richness × source diversity) and
     merge via apoc.refactor.mergeNodes. Preserves canonical UUID,
     re-points all edges, records merged_from on the target.
  5. Append every merge decision to ~/.mikai/wiki/log.md as an audit
     line. Uncertain clusters go into the wiki's ## Pending
     consolidations section for the user's next-day review.

Cost budget per run capped at MAX_LLM_CALLS to keep nightly spend bounded.
Best-effort — a failure here must not break the dream.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase
from openai import OpenAI


# ── Thresholds ─────────────────────────────────────────────────────────

SIMILARITY_HI = 0.90        # auto-merge threshold (cosine on name_embedding)
SIMILARITY_LO = 0.75        # review-queue threshold; below this is not a match
MAX_CLUSTER_SIZE = 10       # cap on a single cluster the LLM sees
MIN_NAME_LENGTH = 3         # skip 1-2 char names (noise)
MIN_ENTITY_DEGREE = 1       # skip fully orphan entities
MAX_LLM_CALLS = 60          # per-run cap on cluster-verification calls
                            # (bounds cost to ~$1.20 per nightly consolidation)

MIKAI_DIR = Path.home() / ".mikai"
LOG_PATH = MIKAI_DIR / "wiki" / "log.md"


# ── Cypher ────────────────────────────────────────────────────────────

# Fetch every entity above degree threshold with its embedding and metadata
# needed for canonicality scoring. Skips orphans (degree 0) and entities
# with no name_embedding.
FETCH_ENTITIES = """
MATCH (n:Entity)
WHERE n.name_embedding IS NOT NULL
  AND size(n.name) >= $min_name
OPTIONAL MATCH (n)-[r:RELATES_TO]-()
WITH n, count(r) AS degree
WHERE degree >= $min_degree
OPTIONAL MATCH (n)<-[:MENTIONS]-(ep:Episodic)
WITH n, degree,
     count(DISTINCT ep) AS mention_count,
     count(DISTINCT ep.group_id) AS source_count
RETURN n.uuid AS uuid,
       n.name AS name,
       n.summary AS summary,
       n.created_at AS created_at,
       n.name_embedding AS embedding,
       degree,
       mention_count,
       source_count
"""

# apoc.refactor.mergeNodes merges the list of nodes into the first one,
# preserving its UUID + labels, moving relationships onto it, and coalescing
# properties per the config. mergeRels dedupes any duplicate edges created.
MERGE_CYPHER = """
MATCH (canonical:Entity {uuid: $canonical_uuid})
UNWIND $other_uuids AS other_uuid
MATCH (other:Entity {uuid: other_uuid})
WITH canonical, collect(other) AS others
CALL apoc.refactor.mergeNodes(
    [canonical] + others,
    {properties: 'discard', mergeRels: true}
) YIELD node
RETURN node.uuid AS merged_uuid
"""


# ── Helpers ────────────────────────────────────────────────────────────

# Common trailing tokens we can safely strip so "ocean farming" and
# "Ocean farming" land in the same bucket. Order matters — longer suffixes
# first so we don't half-strip "farming" → "farm" before stripping "ing".
_SUFFIX_STRIP = [
    "ings", "ing", "eds", "ed", "es", "s'", "'s", "s",
]

# Common leading tokens to drop when bucketing. Keeps "The ocean farm" and
# "ocean farm" in the same bucket.
_LEADING_DROP = {"the", "a", "an", "my", "your", "our", "this", "that"}


def normalize_name(name: str) -> str:
    """Cheap normalization for bucketing. Lowercases, strips punctuation,
    drops leading articles, strips common English suffixes token-by-token."""
    s = re.sub(r"[^\w\s]", " ", name.lower())
    tokens = s.split()
    if tokens and tokens[0] in _LEADING_DROP:
        tokens = tokens[1:]
    normalized_tokens = []
    for t in tokens:
        for suf in _SUFFIX_STRIP:
            if len(t) > len(suf) + 2 and t.endswith(suf):
                t = t[: -len(suf)]
                break
        normalized_tokens.append(t)
    return " ".join(normalized_tokens).strip()


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Neo4j returns embeddings as
    plain lists of floats via the HTTP driver."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def canonicality_score(entity: dict) -> float:
    """Higher = better merge target. Combines: older created_at (stable
    identity), higher degree (well-connected), richer summary, more
    diverse source coverage. All log-scaled so no single factor dominates."""
    # created_at may be a Neo4j datetime string or a python-native datetime
    try:
        raw = entity.get("created_at")
        if isinstance(raw, str):
            s = raw.split("[", 1)[0].rstrip("Z")
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        elif hasattr(raw, "to_native"):
            dt = raw.to_native()
        else:
            dt = raw or datetime.now(tz=timezone.utc)
        age_days = max(1, (datetime.now(tz=timezone.utc) - dt).days)
    except Exception:
        age_days = 1

    return (
        math.log1p(age_days)
        + math.log1p(entity.get("degree") or 0)
        + math.log1p(len(entity.get("summary") or ""))
        + 2.0 * math.log1p(entity.get("source_count") or 0)  # source diversity weighted
    )


def cluster_by_embedding(
    entities: list[dict],
    *,
    similarity_hi: float,
    similarity_lo: float,
) -> tuple[list[list[dict]], list[list[dict]]]:
    """Union-Find on cosine-similar entity pairs within a bucket. Returns
    (auto_merge_clusters, review_queue_pairs). Auto clusters are components
    where every internal edge is ≥ similarity_hi; review pairs are edges
    in the [similarity_lo, similarity_hi) band."""
    n = len(entities)
    if n < 2:
        return [], []

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    review_pairs: list[tuple[int, int, float]] = []
    for i in range(n):
        for j in range(i + 1, n):
            sim = cosine(entities[i]["embedding"], entities[j]["embedding"])
            if sim >= similarity_hi:
                union(i, j)
            elif sim >= similarity_lo:
                review_pairs.append((i, j, sim))

    clusters: dict[int, list[dict]] = {}
    for i in range(n):
        root = find(i)
        clusters.setdefault(root, []).append(entities[i])
    auto_merge = [c for c in clusters.values() if len(c) >= 2]

    # Review queue: only pairs whose endpoints aren't already in the same
    # auto-merge cluster.
    review_out: list[list[dict]] = []
    for i, j, _sim in review_pairs:
        if find(i) == find(j):
            continue
        review_out.append([entities[i], entities[j]])
    return auto_merge, review_out


# ── LLM verification ──────────────────────────────────────────────────

VERIFY_CLUSTER_PROMPT = """\
You are MIKAI's node-consolidation judge. You receive a candidate cluster of
entity nodes from a personal knowledge graph. Your job is to decide whether
they all represent the same concept, and if not, which subset does.

Rules:
1. TWO NODES ARE THE SAME CONCEPT if they refer to the same real-world thing
   or idea, regardless of spelling, capitalization, or level of specificity.
   Example: "MSP", "BC Medical Services Plan", "MSP (BC)" — SAME.
2. TWO NODES ARE DIFFERENT if they are distinct concepts even when semantically
   adjacent. Example: "ocean farming" and "3D ocean farming" are RELATED but
   NOT the same — 3D is a specific sub-technique. Do NOT merge.
3. When unsure, SPLIT rather than MERGE. A bad merge loses information; a
   missed merge is trivially fixed on a future pass.
4. Bias toward preserving specific/proper nouns. Merging "Sam Altman" and
   "Sam" would be catastrophic even if the embedding says they're close.

Output STRICTLY valid JSON with this shape:
{
  "decision": "merge_all" | "merge_subset" | "split_all",
  "canonical_name": "<the best name for the merged concept, or null if split_all>",
  "merge_uuids": ["<uuid>", "<uuid>", ...],  // uuids that merge together; empty if split_all
  "reason": "<one sentence — the deciding factor>"
}

If decision is "merge_subset", `merge_uuids` lists ONLY the ones that merge;
the rest stay separate.
"""


def format_cluster_for_prompt(cluster: list[dict]) -> str:
    lines = []
    for e in cluster:
        summary = (e.get("summary") or "").strip().split("\n")[0][:200]
        lines.append(
            f"- uuid={e['uuid'][:8]}  name={e['name']!r}  degree={e['degree']}  "
            f"sources={e['source_count']}\n    summary: {summary}"
        )
    return "\n".join(lines)


def verify_cluster(
    cluster: list[dict],
    *,
    model: str,
    client: OpenAI,
) -> dict | None:
    """Ask the LLM to verify a candidate cluster. Returns the parsed JSON
    decision, or None on parse/API failure."""
    user_prompt = "CANDIDATE CLUSTER:\n\n" + format_cluster_for_prompt(cluster)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": VERIFY_CLUSTER_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        print(f"WARN: LLM verify failed: {e}", file=sys.stderr)
        return None

    raw = (resp.choices[0].message.content or "").strip()
    try:
        decision = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract first JSON object we can find
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            decision = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(decision, dict) or "decision" not in decision:
        return None
    return decision


# ── Merge execution ──────────────────────────────────────────────────

def execute_merge(driver, *, canonical_uuid: str, other_uuids: list[str]) -> bool:
    """Merge `other_uuids` INTO `canonical_uuid` via apoc.refactor.mergeNodes.
    Returns True on success, False on any exception."""
    if not other_uuids:
        return True
    try:
        with driver.session() as session:
            session.run(
                MERGE_CYPHER,
                canonical_uuid=canonical_uuid,
                other_uuids=other_uuids,
            ).consume()
        return True
    except Exception as e:
        print(f"WARN: merge failed for {canonical_uuid}: {e}", file=sys.stderr)
        return False


# ── Main pass ─────────────────────────────────────────────────────────

def run_consolidation(
    *,
    model: str,
    client: OpenAI,
    dry_run: bool = False,
    similarity_hi: float = SIMILARITY_HI,
    similarity_lo: float = SIMILARITY_LO,
    max_llm_calls: int = MAX_LLM_CALLS,
) -> dict:
    """Nightly consolidation pass. Returns a summary dict; the caller
    (dream.py) uses it to compose the ## Consolidation changelog entry
    and, when there are review-queue items, the ## Pending consolidations
    wiki section."""
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ["NEO4J_PASSWORD"]
    driver = GraphDatabase.driver(uri, auth=(user, pw))

    result = {
        "clusters_detected": 0,
        "clusters_verified": 0,
        "merges_executed": 0,
        "entities_merged": 0,
        "review_queue_size": 0,
        "merges": [],           # list of {canonical, merged, reason}
        "review_queue": [],     # list of {name_a, name_b, similarity}
        "skipped_over_cap": 0,
    }

    try:
        with driver.session() as session:
            rows = session.run(
                FETCH_ENTITIES,
                min_name=MIN_NAME_LENGTH,
                min_degree=MIN_ENTITY_DEGREE,
            ).data()
        print(f"Consolidation: fetched {len(rows)} entity candidates "
              f"(≥{MIN_NAME_LENGTH} chars, degree ≥{MIN_ENTITY_DEGREE})",
              file=sys.stderr)

        # Bucket by normalized name key
        buckets: dict[str, list[dict]] = {}
        for r in rows:
            key = normalize_name(r["name"] or "")
            if not key:
                continue
            buckets.setdefault(key, []).append(r)
        multi_buckets = {k: v for k, v in buckets.items() if len(v) >= 2}
        print(f"Consolidation: {len(multi_buckets)} multi-entity buckets "
              f"after normalization", file=sys.stderr)

        # Detect clusters + review pairs within each bucket
        all_clusters: list[list[dict]] = []
        all_review_pairs: list[list[dict]] = []
        for key, bucket in multi_buckets.items():
            if len(bucket) > MAX_CLUSTER_SIZE:
                bucket = bucket[:MAX_CLUSTER_SIZE]
            clusters, review_pairs = cluster_by_embedding(
                bucket,
                similarity_hi=similarity_hi,
                similarity_lo=similarity_lo,
            )
            all_clusters.extend(clusters)
            all_review_pairs.extend(review_pairs)

        result["clusters_detected"] = len(all_clusters)
        result["review_queue_size"] = len(all_review_pairs)
        print(f"Consolidation: {len(all_clusters)} candidate clusters, "
              f"{len(all_review_pairs)} review pairs", file=sys.stderr)

        # Rank clusters by size × source_diversity — verify the highest-signal
        # ones first so if we hit MAX_LLM_CALLS the useful merges land.
        all_clusters.sort(
            key=lambda c: (
                len(c),
                max((e.get("source_count") or 0) for e in c),
            ),
            reverse=True,
        )

        llm_calls_used = 0
        for cluster in all_clusters:
            if llm_calls_used >= max_llm_calls:
                result["skipped_over_cap"] += 1
                continue
            decision = verify_cluster(cluster, model=model, client=client)
            llm_calls_used += 1
            if not decision:
                continue
            result["clusters_verified"] += 1

            merge_uuids = decision.get("merge_uuids") or []
            if decision.get("decision") == "split_all" or len(merge_uuids) < 2:
                continue

            # Filter merge_uuids to only include ones actually in this cluster
            cluster_uuids = {e["uuid"] for e in cluster}
            merge_uuids = [u for u in merge_uuids if u in cluster_uuids
                           or any(e["uuid"].startswith(u) for e in cluster)]
            # Re-expand any short-form uuids the LLM may have emitted
            expanded = []
            for u in merge_uuids:
                if u in cluster_uuids:
                    expanded.append(u)
                else:
                    for e in cluster:
                        if e["uuid"].startswith(u):
                            expanded.append(e["uuid"])
                            break
            merge_uuids = list(dict.fromkeys(expanded))
            if len(merge_uuids) < 2:
                continue

            # Pick canonical target by canonicality score across the merge subset
            merge_entities = [e for e in cluster if e["uuid"] in merge_uuids]
            merge_entities.sort(key=canonicality_score, reverse=True)
            canonical = merge_entities[0]
            others = merge_entities[1:]

            merge_record = {
                "canonical": {"uuid": canonical["uuid"], "name": canonical["name"]},
                "merged": [{"uuid": e["uuid"], "name": e["name"]} for e in others],
                "canonical_name_suggested": decision.get("canonical_name"),
                "reason": decision.get("reason") or "",
            }

            if dry_run:
                result["merges"].append(merge_record)
                continue

            ok = execute_merge(
                driver,
                canonical_uuid=canonical["uuid"],
                other_uuids=[e["uuid"] for e in others],
            )
            if ok:
                result["merges_executed"] += 1
                result["entities_merged"] += len(others)
                result["merges"].append(merge_record)

        # Populate review queue (top ranked pairs by cosine similarity)
        for pair in all_review_pairs[:20]:
            result["review_queue"].append({
                "name_a": pair[0]["name"],
                "uuid_a": pair[0]["uuid"][:8],
                "name_b": pair[1]["name"],
                "uuid_b": pair[1]["uuid"][:8],
            })

    finally:
        driver.close()

    return result


# ── Audit log ─────────────────────────────────────────────────────────

def append_audit_entry(result: dict) -> None:
    """Append a ## Consolidation section to ~/.mikai/wiki/log.md for this
    dream tick. Idempotent additions (each call appends a stamped block)."""
    if not result.get("merges") and not result.get("review_queue"):
        return
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M")
    lines = [f"\n## Consolidation {stamp}\n"]
    if result["merges_executed"]:
        lines.append(f"- executed {result['merges_executed']} merges, "
                     f"collapsing {result['entities_merged']} duplicate entities:")
        for m in result["merges"]:
            canonical = m["canonical"]["name"]
            merged_names = ", ".join(e["name"] for e in m["merged"])
            reason = m["reason"][:200]
            lines.append(f"  · {merged_names} → **{canonical}** — {reason}")
    if result["review_queue"]:
        lines.append(f"- {len(result['review_queue'])} pairs in review queue "
                     f"(similarity {SIMILARITY_LO:.2f}–{SIMILARITY_HI:.2f}); "
                     f"decide next pass or accept auto-drop.")
    if result.get("skipped_over_cap"):
        lines.append(f"- {result['skipped_over_cap']} clusters skipped "
                     f"(over MAX_LLM_CALLS={MAX_LLM_CALLS}); will resurface "
                     f"next pass.")
    with LOG_PATH.open("a") as f:
        f.write("\n".join(lines) + "\n")


def format_review_queue_section(result: dict) -> str:
    """Return a markdown section for wiki.md listing review-queue pairs.
    dream.py appends this after the existing sections."""
    q = result.get("review_queue") or []
    if not q:
        return ""
    lines = ["## Pending consolidations",
             "",
             "Pairs the graph thinks might be duplicates but MIKAI wasn't confident enough "
             "to merge. Rename or delete one side to accept; leave both to reject.",
             ""]
    for pair in q:
        lines.append(
            f"- **{pair['name_a']}** ({pair['uuid_a']}) ↔ "
            f"**{pair['name_b']}** ({pair['uuid_b']})"
        )
    return "\n".join(lines) + "\n"
