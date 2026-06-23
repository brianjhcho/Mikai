# Strategic Research — 2026-06

> **Captured:** 2026-06-23 from a deep research thread on MIKAI's positioning, the personal-memory landscape, the intervention-timing lineage, and the strategic questions that gate L4 work.
> **Authoritative for:** the May–June 2026 snapshot of competitive landscape, the recommended rename of "Sumimasen" → "intervention timing," the task-boundary delivery principle, and the five strategic questions logged as O-043 through O-047 in `OPEN.md`.

This document is a snapshot, not a living spec. The structural decisions it surfaces belong in `DECISIONS.md` once made; the unresolved questions live in `OPEN.md`.

---

## 1. The personal-memory landscape (May–June 2026)

The space has converged on Jensen Huang's four-layer control plane — **tools, memory, permissions, audit.** Players split into holistic (vertically integrated) vs. parts (horizontally composed). MIKAI sits in the memory slot: strong on substrate (multi-year corpus, bitemporal, epistemic edges), weak on the other three layers.

### Holistic / vertically integrated

- **OpenAI** — ChatGPT + Tasks + Memory + GPTs + Operator. Tightest integrated consumer stack.
- **Anthropic** — Claude + MCP + Memory + Skills + Projects + Computer Use. Same direction, less productized.
- **Apple** — Apple Intelligence + Foundation Models + App Intents + Focus + Notification Summary. Strongest possible permissions layer because they own the OS.
- **Microsoft** — Copilot + Graph + Recall + Loop. Enterprise vertical bundle; Recall got crushed on privacy and is internally considered a failed implementation.
- **Hermes (Nous Research)** — Memory (Mnemosyne) + Skills + Crons + Soul + GEPA learning loop. 135K stars in three months. Open-source vertical bundle.
- **Google** — Gemini + Workspace + Astra + Agentspace. Fragmented but consolidating.

### Parts / horizontally composed (where MIKAI is most visibly competing)

| Layer | Players | Notes for MIKAI |
|---|---|---|
| Memory | Mem0, Letta/MemGPT, Zep, Cognee, Graphiti, Mnemosyne, Honcho | MIKAI's slot. **Cognee benchmarks better than Graphiti** on multi-hop reasoning and uses auto-generated ontologies (no hand-crafted vocabulary). **Mnemosyne** mirrors the LocalAdapter design (SQLite + sqlite-vec + temporal invalidation). |
| Tools | MCP (protocol), Composio, Toolhouse, LangChain catalogs | MIKAI has an MCP server with 5 tools — modest. |
| Orchestration | Temporal, Restate, Inngest, LangGraph | Not in MIKAI's scope today. |
| Permissions | OAuth 2.1 + DCR; Anthropic tool-use authorization | Least mature layer industry-wide. |
| Audit | LangSmith, Helicone, Langfuse, Arize Phoenix | Not in MIKAI's scope today. |

### Product-shape distinction (the verb, not the substrate)

- **Hermes / Manus / Devin / Letta** — *do things* (agents execute tasks). State machinery is for the agent's own work.
- **Apple Intelligence / Recall / Granola / Limitless** — *capture and recall* (passive observation, semantic search).
- **Linear AI / Asana AI / Notion AI** — *fill in declared task state* (workflow assistance).
- **MIKAI** — *infer user task state from cross-source passive observation* and surface next-steps. **Nobody else is shipping this.** Apple's Reduce Interruptions Focus is the closest production thing but operates inside Apple's notification stream, not over cross-source thread state.

### Hermes' L4-equivalent — what they ship under different names

Hermes solves the L4 problem for *itself*, not for the user as a whole human:

| MIKAI L4 stage | Hermes equivalent |
|---|---|
| Thread detection | Honcho representations + Mnemosyne episodic clustering |
| State classification | GEPA stage 2: Outcome Evaluation (did the task succeed?) |
| Intervention timing gate | Proactive check-ins (Issue #9645, in development) + cron triggers |
| Next-step inference | Skills + GEPA Skill Abstraction |
| Delivery | Cron scheduler + messaging integrations |

Hermes infers *agent next-action*; MIKAI infers *user next-action*. Same machinery shape, different target.

### Honcho ≠ Hermes (correction worth recording)

Honcho is a **Plastic Labs** project (`docs.honcho.dev`), not Nous. Hermes integrates it as an optional memory/profile layer. Dialectical user profiling and Theory-of-Mind representations belong to Honcho. Mnemosyne (BEAM tiering) is Hermes-aligned but separately developed. Three distinct things.

---

## 2. MIKAI's position in Jensen's four-layer control plane

| Layer | MIKAI's position | Maturity |
|---|---|---|
| Tools | MCP server, 5 tools (`search`, `get_source`, `get_history`, `get_stats`, `add_note`) | Modest |
| Memory | L3Backend port + Graphiti adapter; multi-year corpus; bitemporal; epistemic edges | **Strong — the differentiator** |
| Permissions | OAuth 2.1 + DCR for MCP access only; no fine-grained internal action authorization | Weak |
| Audit | Per-edge `note` field, `thread_transitions` table; no system-level audit for surfacings | Weak |

**Strategic implication:** a great memory layer without a control stack gets used by someone else's control plane, capturing memory-layer value but not relationship value. This is the load-bearing strategic risk in MIKAI's current shape.

---

## 3. Intervention timing — terminology, lineage, current state

### Terminology

The internal codename "Sumimasen" is fine internally but is **not a published term anywhere**. After 30 years of literature, these are the available terms:

| Term | Provenance | Use |
|---|---|---|
| **Intervention timing** | Current research (CHI 2025, arXiv:2601.10253) | **Recommended** for code, docs, external comms |
| Considerate computing | Horvitz, Scientific American 2005 | Whole-system framing |
| Receptivity-aware delivery | Modern ML research | Emphasizes user-state input |
| Attentive delivery | Vertegaal CACM 2003 | Attention-as-resource framing |
| Calm delivery | Weiser & Brown 1995 | Stay-in-background framing |

**Recommendation:** publish "intervention timing." Keep "Sumimasen" as an internal codename if it has emotional value.

### Lineage

The intellectual stack MIKAI's L4 sits on is older than LLMs:

- **1995** — Weiser & Brown, "Calm Technology" (Xerox PARC). Defined the aesthetic.
- **1993–98** — Horvitz, **Lumiere project** (Microsoft Research). Bayesian models reasoning about time-varying user goals from observed actions + queries + program state. **Five named problems identical to what MIKAI is solving today.** Shipped as Office Assistant (Clippy). Failed productization; the science was right.
- **2003** — Vertegaal, "Attentive User Interfaces" CACM special issue. "User attention as a limited resource" becomes the dominant frame.
- **2003** — Horvitz, "Attuning notification design to user goals and attention costs" (CACM). Cost-utility framework: deliver if `VOI > COI + trust_erosion`. **Still the decision function.**
- **2005** — Horvitz, "Considerate Computing" (Scientific American). Public-facing version of the program.
- **2005–08** — Iqbal & Bailey. Task structure as predictor of cost-of-interruption. **Key finding: interrupting at task boundaries vs. random → 30% faster recovery, half the errors, half the negative affect.**
- **2005** — Horvitz et al., BusyBody. Personalized cost-of-interruption models from passive signals.
- **2008** — Gloria Mark, "The Cost of Interrupted Work" (CHI). **23 min 15 sec to fully refocus** after an interruption. +32–37% stress.
- **2010s** — iOS DND (2012), Android Doze (2015), iOS Focus modes (2021).
- **2024** — Apple Intelligence Notification Summary (iOS 18). First mainstream LLM-driven notification gating.
- **2025** — iOS 18.4 Priority Notifications + Reduce Interruptions Focus. **First shipping production "delivery gate" at consumer scale.**
- **2025–26 research frontier** — ProMemAssist (UIST 2025), Inner Thoughts (CHI 2025), PPP/UserVille (CMU Nov 2025), MEMTRACK (NeurIPS 2025).
- **Jan 2026** — arXiv:2601.10253, "Developer Interaction Patterns with Proactive AI." 5-day field study, 229 interventions. **Replicates Iqbal/Bailey 2006 in the LLM era: post-commit suggestions accepted more readily than mid-task.**

### What's actually shipping

| Capability | Maturity | Best examples |
|---|---|---|
| User-declared rule-based gating | Mature | iOS Focus, Slack DND |
| System-level prioritization | Mature | Apple Priority Notifications, Reduce Interruptions Focus |
| Scheduled proactive (time-driven) | Mature | Hermes crons, ChatGPT Tasks, Reclaim.ai |
| **State-aware delivery from cross-source observation** | **Not shipping anywhere** | The gap MIKAI's L4 is positioned to fill |

---

## 4. Task-boundary detection — the load-bearing finding

Of everything in the literature, one result has the highest signal-to-cost ratio for product decisions:

**Iqbal & Bailey 2006 + arXiv:2601.10253 (Jan 2026):** interrupting at task boundaries reduces cost-of-interruption by ~30% and halves errors vs. random moments. Same finding, same magnitude, replicated 20 years apart, including in the LLM era.

**Recommendation:** if MIKAI's intervention-timing gate implements only one signal, it should be task-boundary detection. Boundaries detectable from existing MIKAI ingestion signals:

- Apple Notes save event
- Gmail outgoing send
- Claude Code session close (JSONL tail)
- Calendar meeting-end event
- Phone unlock after >5 min idle (Shortcuts can detect)
- App switch with no immediate re-engagement
- Long idle followed by deliberate action

The delivery layer doesn't need new sensors. It needs to use the existing event stream as a boundary detector, not just as content for extraction.

---

## 5. The five strategic questions (logged as O-043 through O-047)

These emerged from auditing the conversation. Each constrains the next. **Until answered, every feature decision is taste-based.**

1. **O-043** — What is MIKAI's core noun? (Inbox / context-bridge / control-layer / noonchi engine — pick one as load-bearing.)
2. **O-044** — Is MIKAI a noticer or an executor? (The Rubicon — changes L4 design, trust calibration, threat model.)
3. **O-045** — Vertical product or horizontal substrate? (Currently incoherent.)
4. **O-046** — Who is the user and how do they discover MIKAI?
5. **O-047** — What's the moat 18 months out when the substrate commoditizes?

Full text and resolution criteria in `OPEN.md`.

---

## 6. Things that were re-framed during this research

- **The "epistemic edge vocabulary" is not the moat.** It's an ontology choice. Cognee already produces typed knowledge graphs from heterogeneous corpus with **auto-generated** ontologies and benchmarks better than Graphiti. The hand-crafted vocabulary is interesting research, not durable advantage. (This corrects a claim in VISION.md §2 that was already partially walked back; this research confirms the walk-back.)
- **The substrate is replaceable; the product is not.** L3 substrate (Graphiti / Cognee / Mnemosyne / LocalAdapter) is buy-vs-build. The L4 inference loop and the surface(s) it serves are where the product lives.
- **Hermes is not the competitor for L4.** Hermes solves L4 for the agent's own work, not for the user's life. The actual competition for MIKAI's L4 is the next thing to ship in this space — likely from OpenAI / Apple / a Hermes RFC closing — within 12–18 months.

---

## 7. Cross-references

- `docs/research/l4-port-gap-2026-06.md` — concrete L4 + L3Backend porting audit
- `docs/FOUNDATIONS.md §3` — updated 2026-06-23 with intervention-timing terminology and task-boundary principle
- `docs/OPEN.md` — O-043 through O-047 logged as new strategic blockers
- `docs/VISION.md` — existing noonchi positioning (this research informs but doesn't yet supersede)
- Memory entries: `intervention-timing-term`, `cognee-mnemosyne-localadapter`, `strategic-noun-unresolved`, `worktree-coordination-pattern`
