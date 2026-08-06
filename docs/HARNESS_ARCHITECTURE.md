# Harness architecture — Hermes learnings, global vs specific, ask↔exec composition

*2026-08-06 · Decision doc, nothing built. Inputs: `COCKPIT_INPUT_FEATURE.md` §3.iii, `COCKPIT_STRUCTURE_RESEARCH.md`, `COCKPIT_ORGANIZATION_TRADEOFF.md`, `infra/mikai_exec/core.py`, `infra/mikai_llm/__init__.py`, Hermes Agent sources below. Standing frame: score tradeoffs against "customer-release," not "working prototype."*

## 1. What Hermes actually ships, and what to take

Hermes Agent (Nous Research, released Feb 2026, MIT; TechCrunch reports [$1.5B valuation talks](https://techcrunch.com/2026/07/13/hermes-agent-maker-nous-research-in-talks-for-new-funding-at-1-5b-valuation/)) is the closest shipped comparable for the repeat-pattern learning that `COCKPIT_INPUT_FEATURE` §3.iii deferred. What it verifiably ships:

- **Bounded, curated memory.** Two files — `MEMORY.md` (2,200-char cap) and `USER.md` (1,375-char cap: preferences, communication style, workflow habits) — injected "as a frozen snapshot at session start." The agent edits them through a `memory` tool with three ops (`add` / `replace` / `remove`); over-budget writes **error** instead of silently truncating. Docs explicitly list what *not* to save: trivia, re-discoverable facts, raw dumps. ([memory docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory))
- **Skills as documents.** On-demand procedural markdown, progressive-disclosure loading, agentskills.io-compatible; the [repo](https://github.com/NousResearch/hermes-agent) claims "skill creation after complex tasks" and skills that "self-improve during use," plus command approval and a built-in cron. ([features overview](https://hermes-agent.nousresearch.com/docs/user-guide/features/overview))
- **Pluggable memory providers** (Mem0, Supermemory, Honcho, …) for heavier cross-session user modeling.

**Not verifiable:** the mechanics of the "background self-improvement review" — triggers, cadence, consent — are not specified anywhere in the docs; the features-overview page doesn't document autonomous skill creation at all. The claim lives in README/marketing copy and community reviews ([yuv.ai](https://yuv.ai/blog/hermes-agent)). Notably absent everywhere: statistical pattern mining. Hermes' "learning" is LLM-curated prose under hard byte budgets.

**Lessons for MIKAI:**

1. **Byte budgets beat retrieval cleverness for profiles.** `USER.md` works at 1,375 chars. `PROFILE.md` ≤ 1 page (§3.iv) is right — add a hard cap that errors on overflow, forcing the consolidation Hermes forces.
2. **Learning is curation ops, not ML.** `add`/`replace`/`remove` by a reviewing LLM is exactly the §3.iii proposal-pass shape — validation that v0-as-curation is how the one shipped comparable does it. One divergence to keep: Hermes writes its own memory silently; MIKAI routes proposals through `inbox/` + `triage`. That consent gate is the moat `COMPARISON.md` names — don't trade it for Hermes' autonomy.
3. **Repeats become documents.** A recurring procedure becomes a loadable doc, not a vector or a weight. MIKAI analog: the ask-log pass proposes `PROFILE.md` lines or per-thread playbooks.

**Verdict:** adaptable, not copyable. Same mechanism shape (bounded files + LLM curation + document promotion), different consent stance, different substrate — Hermes personalizes a general agent harness; MIKAI's brain *is* the product.

## 2. Global vs specific — the capability architecture

Categorization of everything live:

| Kind | Surfaces |
|---|---|
| **GLOBAL primitives** (every surface may use; no side-effects of their own) | `mikai_llm` (tier-routed LLM shim, tool-less by default) · `mikai_brain` (store/threads/ledger/triage — the state substrate) · retrieval (WikiFTS/WikiIndex per `RETRIEVAL_STACK`) · `mikai_shell.dialogs` (approval dialogs — misfiled under shell; it's a primitive) · the Sumimasen delivery-cost gate (intervention timing, per `GLOSSARY.md`) |
| **SPECIFIC surfaces** (own a channel and a scope) | `mikai_exec` (per-action-type `--allowedTools`) · `mikai_ask` (read path) · `mikai_shell` organizer (filesystem) · `mikai_cockpit`/`infra/cockpit` (render) · `calendar_planner` + `week_planner` (CalDAV) · `tap_endpoint` (HTTP :8210) · `sumimasen_watcher` + Surface Engine `mikai_decide` (ntfy) · `dream_*` + `hydrator` + `consolidate` (scheduled brain maintenance) · MCP server (external port) |

The test: a global primitive can be described without naming a channel; a specific surface cannot.

**Proposed shape: one registry file, `docs/CAPABILITIES.md`** — a block per surface with five fixed chips: **USES** (which global primitives), **CHANNEL** (the one side-effect scope it owns), **APPROVAL** (dialog / tap / none-read-only), **SCHEDULE** (invocation: CLI / LaunchAgent / on-demand), **WRITES-BACK** (ledger/thread trace). Against Alassafi's vocabulary: WIRED INTO → USES; BUILDS ON → the global-primitive column; WHAT IT REPLACES → dropped deliberately — capability inventory as a rising KPI is the company telos `COCKPIT_STRUCTURE_RESEARCH` §2.3 already rejected for a personal system. Registry file over per-module frontmatter because half the surfaces are LaunchAgents and contracts (approval rules, side-effect scopes) that no single `.py` owns; frontmatter would fragment the audit across two repos and `~/Library`. A cockpit chip renderer that reads the registry is possible later but deferred — the portrait register (`COCKPIT_ORGANIZATION_TRADEOFF` §4) stays closed.

**Example — `mikai_exec`:**

> **USES** mikai_llm(interactive) · mikai_brain.threads · ledger · dialogs
> **CHANNEL** per action_type: email→`mcp__claude_ai_Gmail` · calendar→`mcp__claude_ai_Google_Calendar` · drive→`mcp__claude_ai_Google_Drive` · note→`mcp__mem` · message→clipboard · shell→Bash+Read · code→Bash+Read+Edit · browse→unimplemented
> **APPROVAL** native dialog, Execute/Edit/Cancel — nothing runs without it
> **SCHEDULE** on-demand CLI
> **WRITES-BACK** `ledger.run(mode="exec")` + thread log line

**Honest note:** most of this matrix is internal-audit infrastructure and doesn't ship. The exception is the CHANNEL + APPROVAL columns — "what can this thing touch, and does it ask first" is precisely the privacy manifest a customer must be shown at onboarding. Build the registry once; two of five columns become customer-facing for free.

## 3. mikai_ask ↔ mikai_exec composition

Current split: `mikai_ask` composes context and answers through `mikai_llm` with `--tools ""` — it cannot act. `mikai_exec` acts, but takes a thread slug and an explicit `action_type`. Brian's ask — "make me a presentation" typed into MIKAI — falls between them.

**Pick: (a), intent detection as a *handoff proposal*, with (b)'s `--mode` kept as a manual override.** The ask pass stays tool-less; its output schema gains one field classifying whether the query maps to an `ACTION_POLICIES` key. If yes, `mikai_ask` prints the answer, then offers execution through the **same** `dialogs.confirm_three` gate `mikai_exec` uses, running the payload through `_run_claude_scoped` with that action type's whitelist. Never silent escalation: injected text in retrieved context can at worst *propose*, and the proposal is shown before anything runs — the exact invariant `mikai_exec`'s docstring already encodes.

**Reason:** it preserves the single free-text entry point (the customer-release bar — nobody learns a mode taxonomy, which kills (b)-alone), and keeps the entire tool surface behind one auditable approval choke point. (c) is the two-command workflow Brian explicitly rejected; (d) duplicates `mikai_ask` for no new capability.

**Cost:** `mikai_exec.execute()` needs a threadless path — ask-context substituting for `_thread_dump` — a real refactor, not glue; plus misclassification friction (answering when it should offer to act, and vice versa) and one extra approval tap on every action. Accept both.

## 4. Ranked next moves toward customer-release

1. **Credential onboarding.** `launchd.env` hand-edits, app-specific passwords, cookie decryption, FDA/TCC grants on a Homebrew python path — no customer survives day one of this. Largest single gap.
2. **Installer + doctor.** `install.sh` plus `HEALTH_CHECK.md`'s checks collapsed into one first-run command with legible failures.
3. **`CAPABILITIES.md` as privacy manifest** (§2) — the consent story, productized.

Retrieval is not on the list; the substrate is ahead of the packaging.

## Sources

- https://hermes-agent.nousresearch.com/docs/user-guide/features/memory · https://hermes-agent.nousresearch.com/docs/user-guide/features/overview · https://hermes-agent.nousresearch.com/docs/
- https://github.com/NousResearch/hermes-agent
- https://techcrunch.com/2026/07/13/hermes-agent-maker-nous-research-in-talks-for-new-funding-at-1-5b-valuation/
- https://yuv.ai/blog/hermes-agent (community review; claims exceed docs)
- Not verifiable: mechanics/consent of Hermes' "background self-improvement review" — undocumented as of 2026-08.
