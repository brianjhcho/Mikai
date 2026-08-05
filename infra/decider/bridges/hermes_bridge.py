"""Hermes Agent bridge — MIKAI ↔ Hermes memory & skill layer.

Per docs/COMPARISON.md, MIKAI consumes Hermes's capability rather than
rebuild it:

  Hermes handles:
  - Cross-session memory (MEMORY.md, USER.md)
  - FTS5 session search + LLM summarization
  - Autonomous skill creation from experience
  - Honcho dialectic user modeling
  - CLI agent surface (always-on daemon via `hermes gateway`)

MIKAI's role is orthogonal:
  - Declarative life-tier ontology + top-4 config (~/.mikai/life-tier.json)
  - Sumimasen intervention-timing gate
  - Consent-required approval loop (D-055 pattern)
  - Consumer packaging (the user never sees the wiring)

The bridge has two directions:

1. **Hermes → MIKAI**  (Hermes writes what it learned into MIKAI's substrate)
   MCP tool exposed by MIKAI's sidecar:
       tool_name: mikai.ingest_from_hermes
       params:
         content: str
         source_description: str  # e.g. "hermes-conversation", "hermes-skill"
         reference_time: ISO-8601 UTC
         session_id: str | None
         skill_id: str | None
       returns:
         episode_uuid: str

   Wiring: Hermes calls this after each turn (background thread) so MIKAI's
   L3 substrate gets what Hermes just learned. Uses MIKAI's L3Backend port,
   so the same call works against the graph or the wiki (WikiAdapter).

2. **MIKAI → Hermes**  (MIKAI asks Hermes for cross-session context on demand)
   MCP tool consumed FROM Hermes (Hermes exposes it):
       tool_name: hermes.search_memory
       params:
         query: str
         limit: int = 10
         scope: "user" | "session" | "all"
       returns:
         hits: list[{ text: str, source: str, ts: ISO-8601 }]

   Wiring: when Sumimasen's L4 reasoner has a gap ("what did the user do
   about this last month?"), it calls this to backfill from Hermes's
   FTS5-indexed session history. Complements MIKAI's wiki which only holds
   the LLM-synthesized narrative.

## Consent model

Hermes writes into MIKAI's substrate freely (append-only, non-destructive).
MIKAI reads from Hermes freely (read-only). Neither direction requires per-
call approval — this is memory-level interop, not user-facing actuation.

User-facing actuation (calendar writes, email drafts, notification fires)
STILL flows through MIKAI's D-055 tap-approve routes even if the target
data came from Hermes. This is the load-bearing safety property.

## Status

DRAFT (2026-07-17). Interfaces sketched; no live wiring. To activate:

1. Install Hermes Agent (self-hosted per its docs).
2. Add MIKAI's ingest_from_hermes tool to the sidecar's MCP surface.
3. Add MIKAI as a Hermes memory provider (via Hermes's plugin config
   pattern — see ~/.mikai/probes/mem0/docs/integrations/hermes.mdx for
   the Mem0 template; MIKAI would follow the same shape).
4. Add ~/.mikai/hermes.json config with the base URL / auth token.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


# ── Types the bridge speaks ──────────────────────────────────────────────────


@dataclass
class HermesIngestRequest:
    """Payload Hermes sends when writing into MIKAI's substrate."""

    content: str
    source_description: str
    reference_time: datetime
    session_id: str | None = None
    skill_id: str | None = None
    # Optional Hermes-side memory ID so MIKAI can cross-reference back.
    hermes_memory_id: str | None = None


@dataclass
class HermesIngestResponse:
    episode_uuid: str
    # True if this content was already in MIKAI's substrate (dedup).
    duplicate_of: str | None = None


@dataclass
class HermesSearchHit:
    text: str
    source: str  # "hermes-session:<id>" | "hermes-skill:<id>" | "hermes-user-model"
    ts: datetime
    score: float | None = None


# ── Ingest — Hermes → MIKAI ──────────────────────────────────────────────────


async def ingest_from_hermes(
    req: HermesIngestRequest,
) -> HermesIngestResponse:
    """Write Hermes's memory into MIKAI's L3 substrate via the port.

    This is the MCP tool implementation. Wiring: the sidecar's MCP surface
    registers this under `mikai.ingest_from_hermes`. Hermes's memory plugin
    calls it in a background thread after each conversation turn.
    """
    # DRAFT — actual implementation deferred. Sketch:
    #
    #   from sidecar.l3 import Episode, make_backend
    #   backend = await make_backend()
    #   episode = Episode(
    #       content=req.content,
    #       source_description=req.source_description or "hermes",
    #       reference_time=req.reference_time,
    #   )
    #   result = await backend.ingest_episode(episode)
    #   return HermesIngestResponse(episode_uuid=result.episode_uuid)
    raise NotImplementedError(
        "hermes_bridge.ingest_from_hermes: draft only. Wire when Hermes is "
        "installed and MIKAI's MCP surface is ready to accept it."
    )


# ── Query — MIKAI → Hermes ───────────────────────────────────────────────────


async def search_hermes_memory(
    query: str, limit: int = 10, scope: str = "all"
) -> list[HermesSearchHit]:
    """Ask Hermes for cross-session context. Consumed by Sumimasen's L4
    reasoner when the wiki has a gap.

    Wiring: HTTPS POST to `${HERMES_BASE}/mcp/tools/hermes.search_memory`
    with the JSON payload. Auth: bearer token from ~/.mikai/hermes.json.
    """
    # DRAFT — actual implementation deferred. Sketch:
    #
    #   import json, os
    #   from urllib import request as urlreq
    #   cfg = json.loads((Path.home() / ".mikai" / "hermes.json").read_text())
    #   payload = json.dumps({"query": query, "limit": limit, "scope": scope}).encode()
    #   req = urlreq.Request(
    #       f"{cfg['base_url']}/mcp/tools/hermes.search_memory",
    #       data=payload,
    #       method="POST",
    #       headers={
    #           "Authorization": f"Bearer {cfg['token']}",
    #           "Content-Type": "application/json",
    #       },
    #   )
    #   with urlreq.urlopen(req, timeout=10) as resp:
    #       data = json.loads(resp.read())
    #   return [HermesSearchHit(**hit) for hit in data.get("hits", [])]
    raise NotImplementedError(
        "hermes_bridge.search_hermes_memory: draft only. Wire when "
        "~/.mikai/hermes.json is provisioned with base URL + token."
    )


# ── Configuration shape ──────────────────────────────────────────────────────

CONFIG_TEMPLATE = {
    "base_url": "http://127.0.0.1:8300",  # Hermes daemon default
    "token": "<paste Hermes bearer token here>",
    "user_id": "brian",  # scopes memory reads
    "agent_id": "mikai",  # tags MIKAI's writes on the Hermes side
    "ingest_on_hermes_turn": True,  # Hermes calls MIKAI after each turn
    "read_when_wiki_gap": True,  # MIKAI calls Hermes when local substrate is thin
}
