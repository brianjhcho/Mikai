"""Kenya-coffee benchmark — integration test (Task #8, Stream G).

Ingests 4 synthetic episodes across all source types and asserts that:
  1. A shared "Martin" Person node is touched by ≥3 of the 4 episodes.
  2. A shared "Kenya coffee" Project node exists in the graph.
  3. At least one epistemic edge exists whose fact expresses an unresolved
     tension or partial answer (open question / concern / conflict language).

Marked @pytest.mark.integration — excluded from the default pytest run by
the ``addopts = -m "not integration"`` setting in pytest.ini.

Run explicitly::

    cd infra/graphiti
    .venv/bin/python -m pytest tests/test_kenya_coffee_benchmark.py -m integration -v

Requirements:
  - Graphiti sidecar running at http://localhost:8100
  - Neo4j and the sidecar's LLM/embedding services reachable
  - Uses group_id="stage6-trace-test" to isolate from the live corpus.

If the sidecar is unreachable the entire module is skipped, not failed.

Design note on epistemic edge detection
-----------------------------------------
Graphiti's extraction LLM picks its own relationship name strings even when
``edge_types`` is supplied — the Pydantic model validates the edge *properties*
(e.g. ``confidence``), not the name label.  Asserting exact label matches
(``UNRESOLVED_TENSION``, ``PARTIALLY_ANSWERS``) is therefore brittle.  Instead
we assert on *fact content*: an edge whose fact contains tension/question
language is the semantic equivalent the brief requires.  If a future version of
graphiti-core stamps our schema labels onto the relationship name, this test
will still pass (the fact will still contain the relevant language).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest

# ── Marks ─────────────────────────────────────────────────────────────────────

pytestmark = pytest.mark.integration

# ── Constants ─────────────────────────────────────────────────────────────────

SIDECAR_URL = "http://localhost:8100"
GROUP_ID = "stage6-trace-test"
TIMEOUT_INGEST = 90   # seconds; extraction + embedding can be slow
TIMEOUT_QUERY = 30    # seconds

# Keywords whose presence in an edge fact signals epistemic tension or partial
# answers — the semantic content the UNRESOLVED_TENSION / PARTIALLY_ANSWERS
# edge types are meant to capture.
_EPISTEMIC_KEYWORDS = {
    "tension", "conflict", "question", "unresolved", "open question",
    "not sure", "unclear", "concern", "disagree", "contradicts",
    "partial", "partially", "over-extract", "over-extraction",
}

# ── Synthetic episodes ────────────────────────────────────────────────────────
#
# Four episodes designed to share "Martin" (Person) and "Kenya coffee" (Project)
# across all four source types.  The epistemic tension is between:
#   - Claude thread: Martin says Kenya AA light roast at 94°C is definitive.
#   - Apple note: author questions whether 94°C causes over-extraction on filter.
# This creates an UNRESOLVED_TENSION or PARTIALLY_ANSWERS edge opportunity.

_EPISODES = [
    {
        "source_description": "claude-code",
        "name": "claude-code::benchmark-session::assistant",
        "content": (
            "Martin and I spent the afternoon dialling in the Kenya AA coffee on the V60. "
            "He's convinced that a light roast at 94°C with a 1:15 ratio is the definitive "
            "filter profile for this origin. We documented the recipe in the Kenya coffee "
            "project wiki. Martin said he's tried darker roasts but finds they lose the "
            "bright acidity that makes Kenyan beans distinctive. The next step is to source "
            "a washed Kenyan single-origin from a different region to compare."
        ),
    },
    {
        "source_description": "apple-notes",
        "name": "apple-notes::kenya-coffee-question",
        "content": (
            "Been thinking about the Kenya coffee project. Martin's light-roast recommendation "
            "makes sense for espresso, but I'm not sure it holds for filter — the longer "
            "contact time might over-extract at 94°C. Need to ask him whether he's tested "
            "lower temperatures. There's an open question here about whether the 'bright acidity' "
            "goal conflicts with what a filter drinker actually wants. This tension hasn't been "
            "resolved yet."
        ),
    },
    {
        "source_description": "gmail",
        "name": "gmail::kenya-coffee-supplier-thread",
        "content": (
            "Email from Martin re: Kenya coffee sourcing update. He confirmed the new batch "
            "from Kirinyaga county has landed — washed process, 1800m elevation. He's planning "
            "a tasting session next Tuesday at the roastery and wants us both there. "
            "The Kenya coffee project is moving into its next phase: blind comparison of "
            "three different roast levels. Martin will provide the roasted samples; "
            "I'm responsible for bringing the brewing equipment."
        ),
    },
    {
        "source_description": "whatsapp-day",
        "name": "whatsapp-day::2026-05-20",
        "content": (
            "Martin messaged this morning — the Kenya coffee tasting is confirmed for Tuesday "
            "at 10am. He's roasted three profiles: light, medium, and medium-dark. "
            "Quick chat about whether to include a cold brew in the Kenya coffee comparison; "
            "we decided to keep it to hot filter methods for now. "
            "Martin seems excited about the Kirinyaga batch."
        ),
    },
]

# ── Helpers ───────────────────────────────────────────────────────────────────


def _sidecar_available() -> bool:
    """Return True if the sidecar responds to /health within 3 seconds."""
    try:
        resp = httpx.get(f"{SIDECAR_URL}/health", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def _fact_is_epistemic(fact: str) -> bool:
    """Return True if the edge fact contains tension/question language."""
    if not fact:
        return False
    lower = fact.lower()
    return any(kw in lower for kw in _EPISTEMIC_KEYWORDS)


async def _ingest_episode(client: httpx.AsyncClient, ep: dict) -> dict:
    """POST a single episode to /episode and return the JSON response."""
    payload = {
        "content": ep["content"],
        "source_description": ep["source_description"],
        "episode_type": "text",
        "reference_time": datetime.now(tz=timezone.utc).isoformat(),
        "group_id": GROUP_ID,
    }
    resp = await client.post(
        f"{SIDECAR_URL}/episode",
        json=payload,
        timeout=TIMEOUT_INGEST,
    )
    resp.raise_for_status()
    return resp.json()


async def _search_nodes(
    client: httpx.AsyncClient, query: str, num_results: int = 20
) -> list[dict]:
    resp = await client.post(
        f"{SIDECAR_URL}/nodes/search",
        json={"query": query, "num_results": num_results, "group_ids": [GROUP_ID]},
        timeout=TIMEOUT_QUERY,
    )
    resp.raise_for_status()
    return resp.json()


async def _search_edges(
    client: httpx.AsyncClient, query: str, num_results: int = 50
) -> list[dict]:
    resp = await client.post(
        f"{SIDECAR_URL}/search",
        json={"query": query, "num_results": num_results, "group_ids": [GROUP_ID]},
        timeout=TIMEOUT_QUERY,
    )
    resp.raise_for_status()
    return resp.json()


async def _expand_node(
    client: httpx.AsyncClient, uuid: str, max_edges: int = 50
) -> dict:
    resp = await client.post(
        f"{SIDECAR_URL}/nodes/{uuid}/expand",
        json={"max_edges": max_edges, "include_invalidated": False},
        timeout=TIMEOUT_QUERY,
    )
    resp.raise_for_status()
    return resp.json()


# ── Skip guard ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def require_sidecar():
    """Skip all tests in this module if the sidecar is unreachable."""
    if not _sidecar_available():
        pytest.skip(
            "Sidecar not running at http://localhost:8100 — "
            "skipping Kenya-coffee benchmark.\n"
            "Start with: cd infra/graphiti/sidecar && uvicorn main:app --port 8100"
        )


# ── Main benchmark test ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kenya_coffee_cross_source_benchmark():
    """Ingest 4 synthetic episodes and assert shared typed entities + epistemic edges.

    Assertions:
      A. "Martin" Person node exists and is touched by ≥3 episodes.
      B. "Kenya coffee" Project node exists in the graph.
      C. ≥1 edge whose fact expresses an unresolved tension or partial answer.
    """
    async with httpx.AsyncClient() as client:

        # ── Phase 1: ingest all four episodes ─────────────────────────────────
        for ep in _EPISODES:
            result = await _ingest_episode(client, ep)
            assert result.get("status") == "ok", (
                f"Ingest failed for {ep['source_description']!r}: {result}"
            )

        # Let the graph settle (async community detection, index refresh).
        await asyncio.sleep(2.0)

        # ── Phase 2: find the "Martin" Person node ────────────────────────────
        martin_nodes = await _search_nodes(client, "Martin coffee Kenya")
        martin_node = next(
            (n for n in martin_nodes if "martin" in n.get("name", "").lower()),
            None,
        )
        assert martin_node is not None, (
            "Expected a 'Martin' Person node in the graph after ingestion. "
            f"Found nodes: {[n.get('name') for n in martin_nodes]}"
        )

        # ── Phase 3: Martin touched by ≥3 episodes ────────────────────────────
        martin_uuid = martin_node["uuid"]
        expand = await _expand_node(client, martin_uuid)
        martin_edges = expand.get("edges", [])

        # Each edge carries an `episodes` list of episode UUIDs.
        episode_uuids_via_martin: set[str] = set()
        for edge in martin_edges:
            for ep_uuid in edge.get("episodes", []):
                episode_uuids_via_martin.add(str(ep_uuid))

        assert len(episode_uuids_via_martin) >= 3, (
            f"Expected Martin node to be referenced by ≥3 episodes; "
            f"found {len(episode_uuids_via_martin)}: {episode_uuids_via_martin}"
        )

        # ── Phase 4: "Kenya coffee" Project node ─────────────────────────────
        project_nodes = await _search_nodes(client, "Kenya coffee project")
        kenya_project = next(
            (
                n for n in project_nodes
                if "kenya" in n.get("name", "").lower()
                and (
                    "coffee" in n.get("name", "").lower()
                    or "coffee" in (n.get("summary") or "").lower()
                    or "project" in (n.get("summary") or "").lower()
                )
            ),
            None,
        )
        assert kenya_project is not None, (
            "Expected a 'Kenya coffee' Project node in the graph. "
            f"Found: {[n.get('name') for n in project_nodes]}"
        )

        # ── Phase 5: ≥1 epistemic edge (tension / open question content) ──────
        # Search edges related to the tension domain from the apple-note episode.
        tension_edges = await _search_edges(
            client,
            "Kenya coffee roast light filter over-extraction open question tension",
        )

        epistemic_hit = next(
            (e for e in tension_edges if _fact_is_epistemic(e.get("fact", ""))),
            None,
        )

        assert epistemic_hit is not None, (
            "Expected ≥1 edge whose fact expresses an unresolved tension or open "
            "question about the Kenya coffee project (tension / question / concern "
            "language in the fact text). "
            f"Facts found: {[e.get('fact', '')[:80] for e in tension_edges[:10]]}"
        )

        # The edge must have a non-empty fact string.
        assert epistemic_hit.get("fact"), (
            f"Epistemic edge {epistemic_hit.get('uuid')} has no fact text."
        )
