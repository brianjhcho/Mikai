# MIKAI — Scope Boundaries & Comparison to Adjacent Tools

> Living document. Update when adjacent tools ship new capabilities or MIKAI's
> own scope shifts. Cross-reference from `docs/VISION.md`, `docs/ARCHITECTURE.md`,
> `docs/DECISIONS.md`.
>
> Initial version: 2026-07-17 · After the OpenClaw vs Hermes comparison and
> Brian's decision to keep MIKAI as a consumer-product bet.

## The question this doc answers

Given that Hermes Agent (Nous Research) and OpenClaw already exist and cover
much of what MIKAI is trying to build, **why keep building MIKAI?**

## The answer

**MIKAI is a consumer product bet. Not a prosumer tool. Not a developer
framework.**

Hermes and OpenClaw are excellent. Both are OSS. Both are self-hostable. Both
are extensible. Both require the user to:

- Understand what layers do what
- Wire multiple tools together (Hermes for CLI + memory, OpenClaw for messaging
  + files, plus API keys for each)
- Debug when integrations break
- Read documentation to install
- Maintain their own instance

Consumers do not do this. The market gap MIKAI addresses is not "capability" —
it is **packaging**.

## What MIKAI does not try to build (adjacent tools cover it)

### Hermes Agent covers

- Cross-session memory with autonomous skill creation (`MEMORY.md`, `USER.md`)
- CLI agent surface + always-on daemon (`hermes gateway`)
- Messaging integrations: Telegram, Discord, Slack, WhatsApp, Signal, Email
- File R/W and terminal shell execution
- Multi-LLM routing (300+ backends via Nous Portal / OpenRouter / Anthropic /
  OpenAI / custom)
- Honcho dialectic user modeling
- FTS5 session search + LLM summarization

### OpenClaw covers

- 100+ app integrations
- Browser automation (fill forms, extract data)
- File operations (moves, tags, custom scripts)
- Autonomous web actions
- Multi-model backend (Claude / GPT / Gemini / local Ollama)
- Modular plugin system
- Self-host on Mac mini / Windows / Linux / $5 VPS

**MIKAI should consume these tools' capabilities (via MCP, event bridges, or
ingestion adapters) rather than duplicate them.** Duplicating them was the
mistake in earlier builds.

## What MIKAI uniquely builds

### 1. Declarative life-tier ontology

Hermes's memory is *implicit and agent-curated*. OpenClaw has no explicit
memory model. MIKAI's substrate is a **declared** 9-dimension life ontology
with a top-4 life-tier configuration overlay. This is auditable, editable, and
product-shaped in a way agent-grown memory is not. See
`docs/DIMENSIONS.md` for the ontology and `~/.mikai/life-tier.yaml` (to be
built) for the top-4 overlay.

### 2. Sumimasen intervention-timing gate

Neither Hermes nor OpenClaw addresses "when to fire" with any depth. MIKAI's
Sumimasen layer is JITAI-shaped (Nahum-Shani 2018 framework, Horvitz
decision-theoretic mediator, receptivity-conditioned delivery gate) — genuinely
differentiated research applied as product code. Research report:
https://claude.ai/code/artifact/153fe8e5-3837-470b-95ec-37bdd3c8a0e1

### 3. Consent-required approval loop for every mutation

Motion auto-schedules without consent → measurable user friction ("tug of
war"). MIKAI's D-055 pattern — tap-to-approve every calendar write, every file
move, every email draft — is the safety story that lets a consumer product
touch personal data at all. This is the trust moat.

### 4. Packaged consumer UX

**The differentiating value.** Everything the developer versions of these
tools give you, but:

- Installs like an app, not a bash script
- No API keys visible to the user
- No CLI to memorize
- Errors do not leak infrastructure detail (no "Docker socket not found," no
  "Neo4j connection refused")
- Trust story is simple: approve per action, silence is default
- Updates auto-apply
- One-click sign in

## Feature matrix

| Capability | Hermes Agent | OpenClaw | Claude Code | **MIKAI (target)** |
|---|---|---|---|---|
| Cross-session memory | Yes | No | No | Yes (via life-tier + wiki) |
| Declarative ontology | No | No | No | **Yes** |
| Skill creation | Yes | Via plugins | Via skills | Consumed via Hermes |
| Messaging integrations | 6 platforms | 100+ | No | **Consumed via OpenClaw** |
| Browser control | Read (Firecrawl) | Act (native) | No | **Consumed via OpenClaw** |
| File operations | Shell only | Yes (rich) | Yes | **Consumed via OpenClaw** |
| Terminal / CLI | Yes | Yes | Yes | No — consumer GUI only |
| Intervention-timing gate | No | No | No | **Yes (Sumimasen)** |
| Approval loop per mutation | No | No | No | **Yes (D-055)** |
| Consumer packaging | No | No | No | **Yes** |
| Self-hosted OSS | Yes | Yes | No | Cloud + optional local |
| Wiring required | Yes | Yes | Yes | **No — packaged** |

## Positioning claim in one sentence

MIKAI is what you get when you take Hermes's memory model, OpenClaw's
actuation reach, and JITAI's intervention-timing science — and wrap them in a
consumer product that non-technical users can install, trust, and use without
ever seeing an API key.

## What this means for the build

- **Do not** rebuild what Hermes covers well. Consume via MCP.
- **Do not** rebuild what OpenClaw covers well. Consume via MCP.
- **Do build**: life-tier config, Sumimasen, approval-loop patterns, consumer
  install / UX, trust story.
- The **wiring between MIKAI and its adopted infrastructure** (Hermes +
  OpenClaw) is itself part of the product — the consumer never sees it.

## Cross-references

- `docs/VISION.md` — product vision and noonchi framing
- `docs/ARCHITECTURE.md` — port-adapter model that allows MIKAI to consume
  Hermes / OpenClaw as backends
- `docs/DECISIONS.md` — architectural decisions
  - D-053: FIGS as LLM-only decider
  - D-054: FIGS feedback loop (notif_id, tap redirect, dismissal inference)
  - D-055: Calendar planner with iCloud CalDAV + approval loop
- Sumimasen research artifact:
  https://claude.ai/code/artifact/153fe8e5-3837-470b-95ec-37bdd3c8a0e1
- Architecture + product read artifact:
  https://claude.ai/code/artifact/c03417de-085b-4997-9753-d55c0ebeecb5

## Revision history

- **2026-07-17** — Initial version. Following the OpenClaw vs Hermes
  comparison and Brian's decision to keep MIKAI as a consumer-product bet, not
  a rebuild of infrastructure Hermes and OpenClaw already ship. The insight:
  most consumers cannot wire agentic tools together; MIKAI's differentiation
  is packaging + Sumimasen + declarative ontology + consent-required approval.
