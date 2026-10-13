# MIKAI — Scope Boundaries & Comparison to Adjacent Tools

> Living document. Update when adjacent tools ship new capabilities or MIKAI's
> own scope shifts. Cross-reference from `docs/VISION.md`, `docs/ARCHITECTURE.md`,
> `docs/DECISIONS.md`.
>
> Initial version: 2026-07-17 · After the OpenClaw vs Hermes comparison and
> Brian's decision to keep MIKAI as a consumer-product bet.
> Last updated: 2026-10-13 (personal-agent launches + Hermes refresh).

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

### Hermes Agent covers (refreshed 2026-10-13)

- Cross-session memory with autonomous skill creation (`MEMORY.md`, `USER.md`)
- **Memory-provider plugins**: one external provider active at a time alongside
  built-in memory (Honcho, Mem0, Supermemory, Hindsight, RetainDB, ByteRover,
  OpenViking, Holographic). Hooks: inject provider context into the system
  prompt, prefetch before each turn, sync turns after each response, extract
  memories at session end. ([docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers))
- **MCP client**: any MCP server over stdio or HTTP, per-server tool filtering,
  sampling support. ([docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/overview))
- **Multi-platform gateway, 20+ platforms**: Telegram, Discord, Slack,
  WhatsApp, iMessage, Signal, Matrix, Teams, Email and more
- Terminal, native desktop app, IDE surfaces; six terminal backends; isolated
  profiles; cron scheduling with multi-platform delivery
- Multi-LLM routing (Nous Portal / OpenRouter / Anthropic / OpenAI / custom)
- **`claude-subscription-directsdk` plugin** (added 2026-09-20, updated
  2026-10-13): runs Hermes through the official `claude` CLI so turns bill
  against the Claude subscription's Agent SDK allowance, no API key.
  ([docs](https://hermes-agent.nousresearch.com/docs/plugins/claude-subscription-directsdk))
  Policy status is contested — see "Anthropic subscription constraint" below.
- FTS5 session search + LLM summarization

**What Hermes does not do:** track where each of a user's threads stands, or
judge whether an interruption is worth sending. Same empty band as the
commercial personal agents below.

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

### Commercial personal agents (launched Aug–Sep 2026)

All three execute tasks. None tracks where each of a person's threads stands
or publishes how often its proactive messages are acted on vs. dismissed.

| | **Instinct** (Spear Street Technology) | **Muse** (Meta) | **Dots** (OpenAI) |
|---|---|---|---|
| Focus | Personal logistics: travel, groceries, appointments, cancelling subscriptions | Everyday personal errands | Professional work: research, proposals, fixing software |
| Interface | Text (iMessage / WhatsApp), phone calls, Mac app, web workspace | Own app + WhatsApp | Inside ChatGPT; Slack, Teams |
| How it acts | Signs into the user's own accounts with their credentials; books with the user's airline end to end; has its own agent email addresses | Per-user cloud VM; asks approval for critical actions | Professional delegation in OpenAI's tools |
| Proactivity | High: checks in to flights, reminds about cancellations, follows up dropped conversations | Some | Some |
| Data stance | Training on by default (opt-out); indexed data kept after disconnect unless deletion requested | Memory downloadable by the user | Personal accounts opt-in training |
| Access | Invite-only beta, no public pricing; $350M raised | Free tier, Meta distribution | Paid ChatGPT tiers |

**Instinct's documented gaps** (the openings MIKAI targets — full contrast in
`docs/TRUST_POSITIONING.md`):

- **No per-task status.** A heavy user: "my chat has a bunch of diff, unrelated
  stuff, and it's hard for me to quickly figure out the 'status' of each
  thing." ([eesel](https://www.eesel.ai/blog/instinct-ai-review)) Note: it also
  has a Mac app and web workspace, so this is a reported pain point, not
  proof that no status view exists.
- **Silent failure.** On 2026-09-22 it stopped replying mid-task, messages
  showing as read, no status page, no statement.
  ([Yahoo Finance](https://finance.yahoo.com/technology/ai/articles/hello-frozen-users-viral-ai-161755806.html))
- **Data trust.** Data retained after disconnect, inbox stored in plain text,
  followed a planted prompt injection.
  ([TechCrunch](https://techcrunch.com/2026/08/24/instincts-powerful-ai-assistant-is-raising-privacy-and-security-concerns/))
- **Interruption quality.** Unrequested shopping suggestions.
  ([BigGo](https://finance.biggo.com/news/4bb6e195-cb18-455f-baef-9914f298018e))

Sources for the table: [Kilo](https://blog.kilo.ai/p/dots-instinct-and-muse-the-same-category),
[Notis](https://www.notis.ai/compare/instinct-vs-meta-muse-vs-openai-dots/),
[Skift](https://skift.com/2026/09/04/a-viral-ai-bot-just-showed-travel-what-frictionless-actually-means/),
[TechCrunch on Instinct email](https://techcrunch.com/2026/09/09/viral-ai-assistant-instinct-now-has-its-own-email-address/).

## Positioning: MIKAI is the brain, the assistant is the hands

Per the Oct 11 market position brief (Option C): MIKAI does not compete as a
general assistant. It owns task-state (where each thread stands) and salience
(whether surfacing it is worth an interruption), and plugs into executors that
already exist.

| Phase | Hands (execution + channel) | Brain (MIKAI) |
|---|---|---|
| Dogfood (Brian) | Hermes Agent: iMessage conversation, cron | MIKAI over MCP (`mikai-wiki-v1`) + Surface Engine deciding interruptions, ntfy push kept for salience surfacing |
| First users | The user's own Claude app (Desktop / Code) | MIKAI as an MCP server exposing task-state tools |
| Power users | Hermes with the user's own keys | A MIKAI memory-provider plugin or MCP server |

**Borrowed from Instinct:** texting as the interface, proactive follow-up on
dropped threads, a separate agent identity (own email) instead of the user's
credentials. **Not borrowed:** acting through the user's saved passwords.

### Anthropic subscription constraint

- **Personal use:** `claude -p` and the Agent SDK still bill against the
  user's subscription. Anthropic announced a separate agentic credit for
  2026-06-15, then paused it on 2026-06-16; nothing changed.
  ([Digital Applied](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026))
- **Products:** Anthropic does not permit third-party developers to "offer
  Claude.ai login or to route requests through Free, Pro, or Max plan
  credentials on behalf of their users." Some guides treat even personal use
  of Hermes's subscription plugin as disallowed.
  ([vincentvandeth.nl](https://vincentvandeth.nl/blog/hermes-agent-claude-subscription-oauth),
  [OpenClaw Launch](https://openclawlaunch.com/guides/hermes-claude-subscription))
- **Consequence:** the legitimate distribution route is MCP inside the user's
  own Claude app — their subscription pays for inference through Anthropic's
  own client. MIKAI must not sell "powered by your Claude subscription"
  through a third-party harness.

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

Updated 2026-10-13. "Partial" means a related capability without the full
thing (e.g. following up dropped conversations without per-thread state).

| Capability | Hermes Agent | OpenClaw | Instinct | Muse | Dots | Claude Code | **MIKAI (target)** |
|---|---|---|---|---|---|---|---|
| Cross-session memory | Yes (+ plug-in providers) | No | Yes | Yes (downloadable) | Yes | Via CLAUDE.md / memory | Yes (wiki + thread files) |
| Declarative ontology | No | No | No | No | No | No | **Yes** |
| Messaging integrations | 20+ platforms incl. iMessage | 100+ app integrations | iMessage, WhatsApp, phone | Own app, WhatsApp | ChatGPT, Slack, Teams | No | **Consumed via Hermes** |
| Acts on the user's accounts | Via tools | Yes (browser) | Yes (user credentials) | Yes (cloud VM, approvals) | Yes (work tools) | Files / shell | **No — by design** |
| Per-thread task-state | No | No | Partial (follow-ups, no state view) | No | No | No | **Yes** |
| Interruption gate (salience) | No | No | No (unsolicited suggestions reported) | Approval gate only | No | No | **Yes (Sumimasen)** |
| Published dismiss rate | No | No | No | No | No | No | **Planned** |
| Approval loop per mutation | No | No | No | For critical actions | Partial | Permission prompts | **Yes (D-055)** |
| Self-hosted OSS | Yes | Yes | No | No | No | No | Local files; optional cloud |
| Runs on a Claude subscription | Contested plugin | Blocked | No (own models) | No | No | Yes (first-party) | **Via MCP in the user's Claude** |

## Positioning claim in one sentence

MIKAI is the brain other assistants lack: it knows where each of your threads
stands and only interrupts when it matters — and it plugs into the hands you
already use (Hermes, your Claude app) instead of holding your passwords.

*(Previous version, 2026-07-17: "MIKAI is what you get when you take Hermes's
memory model, OpenClaw's actuation reach, and JITAI's intervention-timing
science — and wrap them in a consumer product…" Superseded by the Oct 11
Option C decision: MIKAI no longer aims to package actuation itself.)*

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

- **2026-10-13** — Added Instinct, Muse and Dots; refreshed Hermes (20+
  platforms incl. iMessage, memory-provider plugins, MCP client,
  `claude-subscription-directsdk`); rewrote the feature matrix; added the
  "MIKAI brain / assistant hands" positioning from the Oct 11 market brief
  (Option C) and the Anthropic subscription constraint. Trust contrast moved
  to `docs/TRUST_POSITIONING.md`.
- **2026-07-17** — Initial version. Following the OpenClaw vs Hermes
  comparison and Brian's decision to keep MIKAI as a consumer-product bet, not
  a rebuild of infrastructure Hermes and OpenClaw already ship. The insight:
  most consumers cannot wire agentic tools together; MIKAI's differentiation
  is packaging + Sumimasen + declarative ontology + consent-required approval.
