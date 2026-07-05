"""
concept_density_lens.py — surface high-density concepts across the WHOLE graph.

Motivation: FIGS currently reads recency-biased signals (last-7d wiki ##
Now, last-24h/7d/30d graph windows, live adapters). This misses concepts
that have substantial corpus presence but aren't currently active in the
last-week window — e.g., 3D ocean farming (58 mentions across 4 sources,
mostly dormant). Those are exactly the "long tail of your life" that
distinguishes MIKAI from a normal reminder tool.

This lens evaluates the ENTIRE graph, ranks entities by a density score,
and returns the top-N as candidates for FIGS to consider alongside its
existing lenses. The density signal is designed to catch:
  - Cross-source concepts (mentioned in ≥3 sources) — real life threads,
    not conversation artifacts
  - Rich-context concepts (many edges) — the graph has learned a lot
    about this concept
  - Concepts substantial enough to persist over time, not one-offs

Score formula (simple, tuneable):

  density = mentions * source_count * sqrt(1 + edges) / (1 + days_dormant^0.3)

Terms:
  mentions       — count of MENTIONS edges from Episodic → Entity
  source_count   — distinct group_id count across those episodes
  edges          — count of RELATES_TO edges (both directions)
  days_dormant   — days since last mention (0 if today)

The 0.3 exponent on dormancy softens the decay — a 90-day-dormant concept
is only ~3.6× less relevant than a today-touched one at the same
mentions/sources/edges. This lets deep-corpus concepts compete with
recent activity, which is the whole point of the lens.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime, timezone
from urllib import request as urlreq

NEO4J_HTTP_URL = os.environ.get("MIKAI_NEO4J_HTTP", "http://localhost:7474")
NEO4J_USER = os.environ.get("MIKAI_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("MIKAI_NEO4J_PASSWORD", "mikai-local-dev")

# Guardrails
MIN_MENTIONS = 3            # skip long-tail one-offs
MIN_SOURCES = 2             # cross-source signal is the anti-framework-noise gate;
                            # concepts threaded through life appear in multiple
                            # sources, framework/tooling noise mostly doesn't
MIN_EDGES = 1               # at least one relationship
MIN_NAME_CHARS = 3          # skip acronyms and single-token noise
DEFAULT_TOP_N = 15

# Entities we always want to skip — meta-concepts about MIKAI itself,
# framework noise, common English tokens that leaked through extraction.
NAME_BLOCKLIST = {
    "mikai", "figs", "graphiti", "claude", "claude-code", "claude.ai",
    "the user", "user", "brian", "brian cho", "briancho",
    "system", "thing", "things", "concept", "concepts",
    "python", "javascript", "typescript", "sql",  # tooling, not life topics
}

DENSITY_CYPHER = """
// Cross-group aggregation: Graphiti isolates entities per group_id, so
// the same concept exists as separate nodes across sources (e.g.
// '3D ocean farming' as uuid X in perplexity + uuid Y in claude-code).
// We aggregate across all variants sharing a lowercased name key.
MATCH (n:Entity)
WHERE size(n.name) >= $min_name
OPTIONAL MATCH (n)<-[m:MENTIONS]-(e:Episodic)
OPTIONAL MATCH (n)-[r:RELATES_TO]-()
WITH toLower(trim(n.name)) AS name_key,
     collect(DISTINCT n.name)[0] AS canonical_name,
     collect(DISTINCT coalesce(n.summary, ''))[0] AS summary,
     collect(DISTINCT n.uuid) AS variant_uuids,
     count(DISTINCT e) AS mentions,
     count(DISTINCT e.group_id) AS source_count,
     count(DISTINCT r) AS edges,
     max(e.valid_at) AS last_mention
WHERE mentions >= $min_mentions
  AND source_count >= $min_sources
  AND edges >= $min_edges
RETURN
    name_key,
    canonical_name AS name,
    substring(summary, 0, 300) AS summary,
    variant_uuids,
    size(variant_uuids) AS variant_count,
    mentions,
    source_count,
    edges,
    toString(last_mention) AS last_mention_iso
ORDER BY mentions * source_count DESC
LIMIT 200
"""


def _neo4j(cypher: str, params: dict | None = None) -> list[dict]:
    payload = json.dumps({
        "statements": [{"statement": cypher, "parameters": params or {}}],
    }).encode()
    auth = base64.b64encode(f"{NEO4J_USER}:{NEO4J_PASSWORD}".encode()).decode()
    req = urlreq.Request(
        f"{NEO4J_HTTP_URL}/db/neo4j/tx/commit",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}",
        },
        method="POST",
    )
    try:
        with urlreq.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"WARN: concept density query failed: {e}", file=sys.stderr)
        return []
    if data.get("errors"):
        print(f"WARN: neo4j errors: {data['errors']}", file=sys.stderr)
        return []
    results = data.get("results", [])
    if not results:
        return []
    cols = results[0].get("columns", [])
    return [dict(zip(cols, r["row"])) for r in results[0].get("data", [])]


def _days_dormant(iso_str: str | None, now: datetime) -> float:
    if not iso_str:
        return 999.0
    try:
        s = iso_str.split("[", 1)[0]
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = (now - dt).days
        return max(0.0, float(delta))
    except (ValueError, TypeError):
        return 999.0


def _score(row: dict, now: datetime) -> float:
    mentions = row.get("mentions", 0) or 0
    sources = row.get("source_count", 0) or 0
    edges = row.get("edges", 0) or 0
    dormant = _days_dormant(row.get("last_mention_iso"), now)
    # density = mentions * source_count * sqrt(1 + edges) / (1 + dormant^0.3)
    from math import sqrt
    return (
        mentions
        * sources
        * sqrt(1 + edges)
        / (1 + dormant ** 0.3)
    )


def concept_density_ranked(top_n: int = DEFAULT_TOP_N) -> list[dict]:
    """Return top-N high-density concepts across the entire graph, ranked.

    Each entry: {uuid, name, summary, mentions, source_count, edges,
    days_dormant, density_score}. Excludes MIKAI-internal noise via the
    NAME_BLOCKLIST.
    """
    rows = _neo4j(
        DENSITY_CYPHER,
        {
            "min_name": MIN_NAME_CHARS,
            "min_mentions": MIN_MENTIONS,
            "min_sources": MIN_SOURCES,
            "min_edges": MIN_EDGES,
        },
    )
    if not rows:
        return []

    now = datetime.now(timezone.utc)
    ranked: list[dict] = []
    for r in rows:
        name = (r.get("name") or "").strip()
        if not name or name.lower() in NAME_BLOCKLIST:
            continue
        ranked.append({
            "name_key": r.get("name_key"),
            "name": name,
            "summary": (r.get("summary") or "").strip(),
            "variant_uuids": r.get("variant_uuids") or [],
            "variant_count": r.get("variant_count", 0),
            "mentions": r.get("mentions", 0),
            "source_count": r.get("source_count", 0),
            "edges": r.get("edges", 0),
            "days_dormant": int(_days_dormant(r.get("last_mention_iso"), now)),
            "density_score": _score(r, now),
        })
    ranked.sort(key=lambda x: x["density_score"], reverse=True)
    return ranked[:top_n]


def format_for_prompt(ranked: list[dict]) -> str:
    """Format ranked concepts as a prompt section for mikai_decide.py.

    Consumed by FIGS as: "HIGH-DENSITY CORPUS CONCEPTS (whole-graph, not
    just this week)". Each row includes the source coverage and dormancy
    so the LLM can reason about whether to surface — high mentions +
    high sources + long dormancy = classic MIKAI wake-up case.
    """
    if not ranked:
        return "(concept density lens returned no candidates)"
    lines = []
    for i, c in enumerate(ranked, 1):
        summary = c["summary"][:180].replace("\n", " ")
        variant_note = (
            f" (across {c['variant_count']} entity variants)"
            if c.get("variant_count", 1) > 1 else ""
        )
        lines.append(
            f"{i:2}. [density={c['density_score']:.1f}] "
            f"{c['name']!r} — {c['mentions']} mentions across "
            f"{c['source_count']} source{'s' if c['source_count'] != 1 else ''}, "
            f"{c['edges']} edges, dormant {c['days_dormant']}d{variant_note}"
        )
        if summary:
            lines.append(f"     summary: {summary}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Standalone diagnostic: print the ranked slate.
    ranked = concept_density_ranked(top_n=25)
    print(f"Top {len(ranked)} concepts by whole-graph density:\n")
    print(format_for_prompt(ranked))
