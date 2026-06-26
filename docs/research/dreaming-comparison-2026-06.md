# MIKAI vs Anthropic Dreaming — Side-by-Side

**Written:** 2026-06-22
**Companion to:** `docs/architecture_visual.html` (visual representation), `docs/SYSTEM_INVENTORY_2026-06.md` (system inventory)
**Status:** Working comparison; revisit when Dreaming exits research preview and becomes user-testable.

---

## Framing — same problem class, different scope and ownership

Anthropic's Dreaming and MIKAI's curator-led identity layer are both implementations of **scheduled async memory consolidation by an LLM that reviews past content and produces a curated downstream representation.** That mechanism is the same. The difference is what each one ingests, what each one writes, who controls the resulting representation, and whose downstream consumer reads it.

Dreaming addresses agent-self-improvement: an agent's past *sessions* get reviewed, patterns get extracted, and a curated memory store gets produced for *future sessions of that same agent or class of agent*. The optimization target is agent task performance over time. The data flow is intra-system — Anthropic's runtime feeds back into Anthropic's runtime, with the developer-as-operator in the loop optionally.

MIKAI's curator addresses user-knowledge-consolidation across surfaces: cross-source content (Apple Notes, Claude conversations, Perplexity, Gmail, iMessage) gets reviewed, recurring concepts get promoted to user-facing markdown files, and a curated identity representation gets produced for *any downstream agent or project the user points at it.* The optimization target is user reasoning continuity across disconnected thinking surfaces. The data flow is cross-system — heterogeneous sources feed into a user-owned representation that conditions whatever downstream agent the user chooses.

Brian's strategic claim — "user-knowledge-consolidation and agent-self-improvement are the same thing" — is true at the mechanism level (both = scheduled LLM curator over past content). It is not true at the scope level (different inputs, different outputs, different consumers). The two are best understood as **the same primitive applied to different layers of the stack**, each defensible against the other only on the scope they target.

This document maps the comparison across 12 axes, surfaces the overlap zones honestly, and ends with a risk analysis: what happens to MIKAI's wedge if Anthropic generalizes Dreaming to operate on user-side content.

---

## Authoritative facts about Dreaming (as of 2026-06-22)

From Anthropic's announcements + independent coverage:
- **Launch:** May 6, 2026, as a research preview.
- **Access:** API-only. Access requires a form request to Anthropic. Two beta headers required on every API call.
- **Models supported:** `claude-opus-4-7` and `claude-sonnet-4-6`.
- **Mechanism:** Asynchronous job in three phases. Input: existing memory store + up to 100 past session transcripts. Output: curated new memory store consisting of plain-text notes and structured "playbooks."
- **Target:** Claude Managed Agents specifically. Agent self-improvement is the framing.
- **User control:** Developers can set Dreaming to auto-update memory or to require review before changes land.
- **Storage opacity:** Output memory store is proprietary format inside Anthropic's runtime, not user-facing files.

These facts are what MIKAI is comparing against. Note all of them are about the agent-improvement layer, not the user-knowledge-consolidation layer.

---

## The 12-axis comparison

### Axis 1 — Target / scope

| | Dreaming | MIKAI |
|---|---|---|
| What gets consolidated | Past agent session transcripts (what the agent has been doing) | Cross-source user content (what the user has been thinking, writing, deciding across apps) |
| Optimization target | Agent task performance over time | User reasoning continuity across disconnected surfaces |
| Whose memory | Agent's memory (process-centric) | User's identity representation (data-owner-centric) |

**Overlap:** both consolidate past content into a more useful representation.
**Divergence:** *whose* content, and *whose* future use the representation serves.

### Axis 2 — Ingestion sources

| | Dreaming | MIKAI |
|---|---|---|
| Input source | Claude session transcripts only (up to 100 per dream job) | Cross-source: Apple Notes (osascript), Claude.ai conversations (live connector), Perplexity (browser-driven), Gmail (OAuth), iMessage (computer-use bridge), arbitrary markdown ingestion |
| Input format | Anthropic-internal session format | Heterogeneous source formats normalized via `SEGMENTATION_FRAMEWORK.md` adapters into canonical episodes |
| Cross-source synthesis | No — single agent class per dream | Yes — designed for it (cross-app thread detection in `detect-threads.ts`) |

**Overlap:** both ingest "history of what happened."
**Divergence:** Dreaming sees one surface (its own agent's sessions); MIKAI sees many surfaces (user's entire digital reasoning life).

### Axis 3 — Retrieval surface

| | Dreaming | MIKAI |
|---|---|---|
| Where output is read | Anthropic runtime injects memory into future agent sessions automatically | Downstream projects read identity files explicitly via retrieval recipes (per `docs/PROJECT_RECIPE.md`, deferred from current plan) |
| Read API | Implicit (memory store loaded into agent context) | Explicit (markdown files + Graphiti `/search`, `/get_source`, `/expand_node` per project recipe) |
| Who controls retrieval composition | Anthropic (memory store schema) | User (per-project YAML recipes; user authors what gets composed) |

**Overlap:** both produce a retrievable representation.
**Divergence:** Dreaming's retrieval is opaque/platform-controlled; MIKAI's is explicit/user-authored.

### Axis 4 — Write target

| | Dreaming | MIKAI |
|---|---|---|
| Output target | Proprietary memory store (notes + playbooks format) | User-facing markdown files under `~/mikai/identity/{core,taste,mentors,concerns,projects,history}/` |
| Format | Opaque to user (managed by Anthropic) | Markdown with YAML frontmatter, hand-readable, hand-editable |
| Portability | Tied to Anthropic's runtime | Filesystem — survives Anthropic going away, can be consumed by any LLM/agent |

**Overlap:** both produce structured output ready for downstream consumption.
**Divergence:** ownership and portability are inverted.

### Axis 5 — Citation model

| | Dreaming | MIKAI |
|---|---|---|
| Provenance | Internal (notes/playbooks may reference session IDs internally; user-facing transparency unclear from public docs) | Every write cites Graphiti episode UUIDs in the file's `cited_episodes:` frontmatter array |
| Audit trail | Anthropic-controlled | User-controlled in `history/` directory with daily changelogs and supersedence records |
| Verifiability by user | Limited — depends on what Anthropic surfaces | Full — every claim resolves to an episode body retrievable via `/get_source` |

**Overlap:** both have some notion of provenance.
**Divergence:** MIKAI's citation is first-class and verifiable; Dreaming's is implementation-internal.

### Axis 6 — Runtime / where it runs

| | Dreaming | MIKAI |
|---|---|---|
| Execution environment | Anthropic's managed cloud (asynchronous job inside their infrastructure) | User's laptop via Claude Code skill (Max-legitimate first-party OAuth, per the May 19 session thread) OR Anthropic-managed via Claude Code Routines |
| Always-on requirement | No — fires on Anthropic's job scheduler | No — Claude Code Routines schedule it; user laptop need not be on |
| Cost model | Burns Anthropic API tokens at preview pricing | Burns user's Max-plan first-party allowance (no overage if scheduled within Routines limits) |

**Overlap:** both run on-schedule, asynchronously, without user supervision.
**Divergence:** runtime ownership is Anthropic-side (Dreaming) vs user-controlled (MIKAI).

### Axis 7 — Scheduling

| | Dreaming | MIKAI |
|---|---|---|
| Trigger mechanism | Dream jobs invoked via API call (developer-initiated or scheduled by developer's external system) | Claude Code Routines (`cron_create`, `cron_list`, `cron_delete`) — Anthropic-native scheduling |
| Cadence | Developer-controlled, per-job | Daily (default), configurable via cron expression. Brian's stated cadence: every 24 hours. |
| User-facing schedule control | Through developer's interface | Direct via `claude /cron_create mikai-curator '0 6 * * *'` |

**Overlap:** both are scheduled, both async, both can run unattended.
**Divergence:** scheduling lives at different layers of the stack.

### Axis 8 — Access tier

| | Dreaming | MIKAI |
|---|---|---|
| Availability | Research preview only as of 2026-05-06. Access requires form request to Anthropic. Two beta headers required per API call. | Open — runs on user's existing Max plan + Claude Code. No special access required. |
| Pricing | Anthropic-internal preview pricing (token-based) | Within Max plan allowance |
| Geographic availability | API-gated; same access pattern as Anthropic's API | Wherever Claude Code + Max are available |

**Overlap:** both need a Claude account.
**Divergence:** Dreaming requires an active access invitation; MIKAI works today within standard Max.

### Axis 9 — User control

| | Dreaming | MIKAI |
|---|---|---|
| Auto vs reviewed updates | Developers can choose: auto-update OR review-before-land | Curator agent operates with operationalized brief: pinned sections immune, write-quota caps, decision-quorum for supersedes (per Section 4 of `.omc/plans/tier2-curator-identity-layer.md`) |
| Override mechanism | Developer review queue (per Anthropic docs) | `pinned_sections` frontmatter + weekly Brian review of recent supersedes + dismiss CLI (deferred to follow-up) |
| Destructive operations | Updates the memory store (additive curation; exact supersedence semantics unclear from public docs) | Never deletes. Supersedence moves files to `history/`. Every change citable, every change reversible. |

**Overlap:** both offer optional human-in-the-loop review.
**Divergence:** MIKAI's invariants (no delete, every write cited, pinned sections immune) are explicit; Dreaming's are not documented at the same level of detail.

### Axis 10 — Supersedence semantics

| | Dreaming | MIKAI |
|---|---|---|
| How old content is handled | "Remove stale entries" and "merge duplicates" per Anthropic's framing. Mechanism opaque. | Bitemporal — old content moves to `history/YYYY-MM-DD/superseded/`, never deleted. Edge invalidation (`invalid_at`) propagated through Graphiti. |
| Belief revision tracking | Implicit in the curated memory store | Explicit — supersedence quorum requires ≥2 supporting episodes for new, ≤1 for old in 60d, and an explicit-change verb signal ("I no longer think", "Actually", "I was wrong about") |
| Historical accessibility | Unclear what's queryable post-supersede | Full — `history/` is append-only, queryable, supports rollback |

**Overlap:** both handle stale entries.
**Divergence:** MIKAI exposes bitemporal semantics; Dreaming abstracts them away.

### Axis 11 — Cross-source support

| | Dreaming | MIKAI |
|---|---|---|
| Source diversity | Single source class (Claude agent sessions). Cross-agent dreams are not the design target. | Multi-source from day one. The 12,849-entity / 3,455-episode graph already spans Apple Notes, Claude conversations, Perplexity threads. Hibernation source = Computer Use for locked sources (iMessage, WhatsApp via browser-driven flow). |
| Cross-source thread detection | Not in scope | Core capability (`SEGMENTATION_FRAMEWORK.md` source-adaptive normalization, `detect-threads.ts` cross-source clustering — the proposed `mikai-thread-linker` skill builds on this) |
| Behavioral signal integration | No (Anthropic sees only session transcripts) | Designed for it — Spotify, Letterboxd, Pinterest are roadmapped extensions to fill taste domains the expressed-content corpus misses |

**Overlap:** essentially none — this is the cleanest divergence axis.
**Divergence:** cross-source is MIKAI's structural commitment; it's not Dreaming's problem to solve.

### Axis 12 — Distribution model

| | Dreaming | MIKAI |
|---|---|---|
| Who uses the output | Other agents in the same Anthropic Managed Agent runtime | Any downstream project the user authors (Village mentor, weekend planner, taste-furniture retrieval, deep-analyze meta-routine) — and any external LLM/agent that can read markdown files |
| Distribution surface | Anthropic's runtime → developer's agent products | User's filesystem → Claude Projects, OMC, Letta, Hermes, any MCP-capable client |
| Lock-in shape | Anthropic-platform — leaving means losing the curated memory | None — files are portable; user owns them; Graphiti substrate can be exported as JSONL |

**Overlap:** both serve downstream consumers.
**Divergence:** Dreaming's downstream consumer is bound to Anthropic's runtime; MIKAI's is platform-agnostic by design.

---

## Overlap zones — where Dreaming and MIKAI actually converge

Three substantive overlaps deserve honest naming:

**Overlap 1 — Scheduled async LLM-as-curator pattern.** Both architectures use the same fundamental primitive: an LLM that runs on a schedule, reviews past content, decides what to consolidate, and writes a curated downstream representation. This is not a coincidence — it's the right pattern for the problem class. Anyone solving any version of "long-running personal/agent memory" converges on this shape. MIKAI was running this pattern in design 11 weeks before Dreaming's research-preview announcement (see `MEMORY_ARCHITECTURE_THESIS.md` Tier 2 spec, March 2026). Dreaming validates the pattern.

**Overlap 2 — Plain-text notes + structured artifacts as output format.** Dreaming produces "plain-text notes and structured playbooks." MIKAI produces markdown files with YAML frontmatter (notes) and per-use-case retrieval recipes (the structured equivalent of playbooks). The choice of human-readable format is correct in both cases — LLMs read them, humans read them, and they survive runtime changes.

**Overlap 3 — Human-in-the-loop optional.** Both architectures permit either auto-update or review-before-land. Both acknowledge that fully autonomous curation is the goal but not always the safe default. MIKAI's review surface is `concerns/contradictions.md` + weekly manual sample audit. Dreaming's is the developer review queue.

These overlaps mean: if you squint at the diagrams, the shapes look similar. The diagrams in `docs/architecture_visual.html` make this visually explicit.

---

## Divergence zones — where the two architectures structurally cannot meet

Four divergences that no amount of feature parity can erase:

**Divergence 1 — Target audience of the curated representation.** Dreaming serves agents; MIKAI serves users (and the agents users point at it). Each will optimize toward its target. Dreaming will get better at agent procedural memory. MIKAI will get better at user identity continuity. These are different optimization targets and will produce different products even if mechanism converges.

**Divergence 2 — Source scope.** Dreaming reads sessions inside Anthropic. It can read MORE sessions over time but cannot reach into Apple Notes or Perplexity or your Substack reading. The platform structurally cannot — these are not its data. MIKAI's first-class commitment is cross-source. The divergence is permanent absent a strategic shift at Anthropic.

**Divergence 3 — Ownership of the output.** Dreaming's curated memory is inside Anthropic's runtime. If Anthropic changes pricing, deprecates Dreaming, or restricts access, the output goes with it. MIKAI's output is markdown files in the user's filesystem. The wedge here is ownership, not just format.

**Divergence 4 — Composability with non-Anthropic surfaces.** Dreaming's output is consumable by Anthropic-runtime agents. MIKAI's output is consumable by anything that can read a markdown file. The next agent ecosystem (Letta, Hermes, OMC, HICCUP, the curator/thread-linker/deep-analyze trio MIKAI itself ships) can read MIKAI's identity files natively. Dreaming will not interoperate with Letta or Hermes or any non-Anthropic agent runtime.

---

## What happens if Dreaming generalizes to user-side content

This is the platform-risk scenario the strategic doc named R8. With Dreaming shipped, the risk timeline has likely compressed from 12 months to 6.

Three plausible Anthropic moves to watch for:

### Scenario 1 — Dreaming for Claude Projects (most likely)

Anthropic extends Dreaming so that a Project's conversation history (not just an agent's sessions) becomes the input. Output is improvements to the Project's memory store, automatically. Users see "Project memory updated based on recent conversations."

**MIKAI impact:** moderate. The within-Claude-Projects auto-curation slice that MIKAI provides gets absorbed. But:
- Single-platform (Claude conversations only); cross-source remains MIKAI's lane
- Anthropic-runtime output; non-Claude consumers (other LLMs, OMC, Letta) still need files
- Retrieval recipe library (per-use-case prompt composition) is content/IP MIKAI authors; Anthropic likely ships a generic curator, not recipes

**Hedge:** ship α v1 within 6 months with cross-source ingestion as a visible product differentiator. Make the recipe library the moat.

### Scenario 2 — Dreaming for user memory broadly (less likely near-term, transformative if it happens)

Anthropic extends Dreaming so it can ingest user-uploaded data (Apple Notes export, Gmail OAuth, Notion connector) and curate a personal context layer accessible across Claude surfaces.

**MIKAI impact:** severe. This would be the direct Anthropic move into MIKAI's category. But:
- User-controlled file output is unlikely (Anthropic would build proprietary memory store)
- Non-Anthropic agent consumers remain MIKAI's lane
- Mentor authoring layer + per-use-case recipes remain authoring work Anthropic won't do

**Hedge:** position MIKAI explicitly as "cross-platform / file-based / mentor-authoring" relative to Anthropic's "Claude-native / runtime-based / generic-curator" version. Make the IP the recipe library and the mentor briefs, not the curator runtime.

### Scenario 3 — Dreaming for shared/team memory (orthogonal)

Anthropic extends Dreaming to consolidate memory across teams or organizations (the agent learns team conventions).

**MIKAI impact:** low. This is enterprise productivity territory — Glean's lane, not MIKAI's. Brian's stated direction is individual users, not teams.

### What to monitor

Concrete signals that Scenario 1 or 2 is imminent:
- Public docs for Dreaming start showing "user content" or "project context" as inputs alongside session transcripts
- Anthropic ships a "Dreaming for Projects" beta
- The Apple Notes Connector (currently passive read-on-demand) gains scheduled-ingestion capability
- Claude Projects gains "edit project files based on conversation history"

Monitoring cadence: weekly Anthropic blog scan, monthly check of Dreaming preview docs as they update. Brian to test Dreaming personally once access is granted.

---

## Conclusions

1. **Brian's strategic claim is right at the mechanism level.** Dreaming and MIKAI implement the same primitive (scheduled async LLM-as-curator). The pattern is correct because the problem is the same problem class.

2. **The claim is incomplete at the scope level.** Dreaming targets agent self-improvement inside Anthropic's runtime; MIKAI targets cross-source user-knowledge-consolidation across surfaces. These remain distinct products even though the mechanism is shared.

3. **Anthropic's release of Dreaming is platform-risk-validation, not platform-risk-realization.** Dreaming today does NOT do what MIKAI does. It validates that Anthropic is thinking in this direction. The strategic move is to ship MIKAI's wedge fast enough that when Anthropic generalizes (Scenarios 1 or 2 above), MIKAI's cross-source + file-based + mentor-authoring position is established and defensible.

4. **The MIKAI wedge, in one sentence:** *cross-source ingestion + user-owned markdown files + per-use-case retrieval recipes + mentor authoring layer.* Dreaming will probably take 12+ months to credibly cover any one of these; it will probably never cover all four simultaneously because Anthropic's business model doesn't pull it there.

5. **Recommended action:** treat Dreaming as a forcing function. Ship α v1 by Q3 2026, not Q4. Position MIKAI's docs and any future external messaging around the four defensible properties above, not around the curator pattern itself (which is now common ground).

---

## Cross-references

- Visual: `docs/architecture_visual.html`
- Inventory: `docs/SYSTEM_INVENTORY_2026-06.md`
- Strategic context: `docs/STRATEGIC_INSIGHTS_2026-05.md` (especially R8 risk)
- Build plan: `.omc/plans/tier2-curator-identity-layer.md`
- Mechanism precedent: `docs/MEMORY_ARCHITECTURE_THESIS.md` (Tier 0-3 spec, March 2026 — predates Dreaming)
