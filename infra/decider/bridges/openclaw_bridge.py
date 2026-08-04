"""OpenClaw bridge — MIKAI ↔ OpenClaw actuation & messaging ingestion.

Per docs/COMPARISON.md, MIKAI consumes OpenClaw's capability rather than
rebuild it:

  OpenClaw handles:
  - 100+ app integrations (WhatsApp, Signal, Discord, Slack, iMessage,
    Telegram, Gmail, Notion, Linear, Google Drive, …)
  - Browser automation (fill forms, extract data, autonomous web actions)
  - File operations (moves, renames, tags, custom scripts)
  - Multi-model backend (Claude / GPT / Gemini / local Ollama)
  - Modular plugin system

MIKAI's role is orthogonal:
  - Decides WHAT to surface (Surface Engine, née FIGS)
  - Decides WHEN + IF to fire (Sumimasen intervention-timing gate)
  - Requires approval per mutation (D-055 tap-approve pattern)
  - Owns the audit trail (notification_events, calendar_proposals)

The bridge has two directions:

1. **OpenClaw → MIKAI**  (OpenClaw ingests external content into MIKAI)
   MCP tool exposed by MIKAI's sidecar:
       tool_name: mikai.ingest_from_openclaw
       params:
         content: str
         source_description: str
             # e.g. "openclaw-imessage", "openclaw-signal", "openclaw-slack-#eng"
         reference_time: ISO-8601 UTC
         plugin_id: str        # which OpenClaw plugin ingested this
         source_uri: str | None  # deep link back to the original (for citations)
       returns:
         episode_uuid: str

   Wiring: each OpenClaw messaging plugin (Signal, WhatsApp, iMessage) is
   configured to POST new messages to this MCP endpoint. MIKAI's L3
   substrate now has the messaging surfaces MIKAI's native ingestion
   never covered.

2. **MIKAI → OpenClaw**  (MIKAI proposes actuation via OpenClaw)
   MCP tools consumed FROM OpenClaw (OpenClaw exposes them):

     tool_name: openclaw.file.propose_move
       params:
         src: absolute path
         dst: absolute path
         rationale: str        # for the approval card body
       returns:
         proposal_id: str
         needs_approval: True  # OpenClaw MUST NOT execute without MIKAI's confirm

     tool_name: openclaw.file.apply_move
       params:
         proposal_id: str
         approved: bool
       returns:
         status: "applied" | "rejected" | "expired"
         apply_error: str | None

     tool_name: openclaw.email.propose_draft
       params:
         to: str
         subject: str
         body: str
         context_bundle: str   # what to remind the user of when they read the draft
       returns:
         proposal_id: str
         needs_approval: True

     tool_name: openclaw.email.apply_send
       params:
         proposal_id: str
         approved: bool
       returns:
         status: str

     tool_name: openclaw.browser.fetch
       params:
         url: str
         extract: "text" | "structured"
       returns:
         content: str

   Wiring: Sumimasen decides a candidate should route to a Facilitator or
   Spark surface, calls the appropriate propose_* tool. OpenClaw returns a
   proposal_id. MIKAI dispatches an ntfy card with tap-to-approve routes
   that call apply_* back through the same MCP surface.

## Consent model — the critical property

OpenClaw's actuation MUST be gated by MIKAI's approval loop. The bridge
enforces this by SEPARATING propose_ from apply_ in the tool surface:

  - propose_ tools MUST NOT execute the mutation. They stage and return
    a proposal_id.
  - apply_ tools MUST refuse when approved=False, and MUST verify the
    proposal_id came from a propose_ call that MIKAI observed.
  - MIKAI's tap-endpoint routes at /approve/{proposal_id} +
    /reject/{proposal_id} (D-055 pattern) call the apply_ tools.

An OpenClaw plugin that bypasses this and mutates directly is a bug and
must be treated as such — the whole consumer-product trust story
depends on this invariant. MIKAI must never expose a raw "openclaw.file.
move_now" tool without approval semantics.

## Status

DRAFT (2026-07-17). Interfaces sketched; no live wiring. To activate:

1. Install OpenClaw (self-hosted, LLM backend via API key or local Ollama).
2. Configure OpenClaw's messaging plugins (Signal, WhatsApp, iMessage) to
   POST to MIKAI's ingest_from_openclaw endpoint.
3. Add MIKAI's sidecar MCP surface to consume the propose_/apply_ tools
   from OpenClaw's exposed MCP.
4. Extend the tap-endpoint routes to include /approve-openclaw/{id}
   and /reject-openclaw/{id} that call apply_ with the appropriate
   argument.
5. Add ~/.mikai/openclaw.json config with base URL + auth token.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


# ── Types the bridge speaks ──────────────────────────────────────────────────


@dataclass
class OpenClawIngestRequest:
    """Payload OpenClaw sends when relaying an external message into MIKAI."""

    content: str
    source_description: str
    reference_time: datetime
    plugin_id: str  # "openclaw-signal", "openclaw-imessage", etc.
    source_uri: str | None = None  # deep link to the original (for citations)
    # Contact metadata when applicable (message sender, group name, etc.)
    contact: dict = field(default_factory=dict)


@dataclass
class OpenClawIngestResponse:
    episode_uuid: str
    duplicate_of: str | None = None


@dataclass
class OpenClawProposal:
    """What OpenClaw returns from a propose_* call."""

    proposal_id: str
    action_type: str  # "file.move" | "file.rename" | "file.tag" | "email.draft" | ...
    summary: str  # human-readable "what will happen if approved"
    payload: dict  # the specific args the apply_* call will re-use
    needs_approval: bool = True


@dataclass
class OpenClawApplyResult:
    status: str  # "applied" | "rejected" | "expired"
    proposal_id: str
    executed_at: datetime | None = None
    apply_error: str | None = None


# ── Ingest — OpenClaw → MIKAI ────────────────────────────────────────────────


async def ingest_from_openclaw(
    req: OpenClawIngestRequest,
) -> OpenClawIngestResponse:
    """Write an OpenClaw-relayed message into MIKAI's L3 substrate.

    MCP tool: mikai.ingest_from_openclaw. Wired at the sidecar's MCP surface.
    Same shape as hermes_bridge.ingest_from_hermes — both use the port's
    ingest_episode() primitive.
    """
    # DRAFT — actual implementation deferred. Sketch:
    #
    #   from sidecar.l3 import Episode, make_backend
    #   backend = await make_backend()
    #   episode = Episode(
    #       content=req.content,
    #       source_description=req.source_description or f"openclaw-{req.plugin_id}",
    #       reference_time=req.reference_time,
    #   )
    #   result = await backend.ingest_episode(episode)
    #   return OpenClawIngestResponse(episode_uuid=result.episode_uuid)
    raise NotImplementedError(
        "openclaw_bridge.ingest_from_openclaw: draft only. Wire when OpenClaw "
        "plugins are configured to POST to MIKAI's MCP surface."
    )


# ── Actuation — MIKAI → OpenClaw ─────────────────────────────────────────────


async def propose_file_move(
    src: str, dst: str, rationale: str
) -> OpenClawProposal:
    """Ask OpenClaw to STAGE a file move (does not execute). Returns a
    proposal_id that MIKAI's tap-endpoint /approve/{id} route will use
    when the user consents.

    Wiring: MCP call to openclaw.file.propose_move on the OpenClaw daemon.
    """
    raise NotImplementedError(
        "openclaw_bridge.propose_file_move: draft only. Wire when "
        "~/.mikai/openclaw.json is provisioned with base URL + token."
    )


async def apply_file_move(
    proposal_id: str, approved: bool
) -> OpenClawApplyResult:
    """Execute (or reject) a staged file move. Called by the tap-endpoint
    route when the user approves. MUST refuse when approved=False."""
    raise NotImplementedError(
        "openclaw_bridge.apply_file_move: draft only. Wire together with "
        "propose_file_move and the /approve-openclaw/{id} tap route."
    )


async def propose_email_draft(
    to: str, subject: str, body: str, context_bundle: str
) -> OpenClawProposal:
    """Ask OpenClaw to STAGE an email draft. Returns a proposal_id."""
    raise NotImplementedError(
        "openclaw_bridge.propose_email_draft: draft only."
    )


async def apply_email_send(
    proposal_id: str, approved: bool
) -> OpenClawApplyResult:
    """Execute (or reject) a staged email draft."""
    raise NotImplementedError(
        "openclaw_bridge.apply_email_send: draft only."
    )


async def fetch_browser(
    url: str, extract: str = "text"
) -> str:
    """Read-only browser fetch. No approval required (non-mutating)."""
    raise NotImplementedError(
        "openclaw_bridge.fetch_browser: draft only."
    )


# ── Configuration shape ──────────────────────────────────────────────────────

CONFIG_TEMPLATE = {
    "base_url": "http://127.0.0.1:8400",  # OpenClaw daemon default
    "token": "<paste OpenClaw bearer token here>",
    "enabled_plugins": [
        # Ingestion plugins that will POST to MIKAI's ingest_from_openclaw:
        "signal",
        "imessage",
        "whatsapp",
        # Actuation plugins MIKAI can call propose_*/apply_* against:
        "file-ops",
        "gmail-drafts",
        "browser",
    ],
    "approval_endpoint": "http://192.168.88.228:8210/approve-openclaw",
    "reject_endpoint": "http://192.168.88.228:8210/reject-openclaw",
    "llm_backend": "deepseek",  # or "anthropic" or "ollama-local"
}


# ── Safety invariants (for future test harness) ──────────────────────────────

SAFETY_INVARIANTS = [
    "propose_* tools MUST return needs_approval=True and MUST NOT execute",
    "apply_* tools MUST refuse when approved=False",
    "apply_* tools MUST verify proposal_id was returned by a MIKAI-observed propose_",
    "No raw '_now'-suffixed tools may exist that bypass the approval loop",
    "Every apply_* call MUST write a row to notification_events with the outcome",
    "The consumer never sees an OpenClaw API key — MIKAI proxies auth",
]
