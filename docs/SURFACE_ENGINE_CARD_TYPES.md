# SUMIMASEN — Card Types (implementation spec)

> **What this file is:** The operational spec for the five card types SUMIMASEN ships in v1. Written to be executable — file paths, data models, function names, acceptance criteria.
> **Written:** 2026-07-04
> **Status:** V1 spec. Card types are additive; new types are appended, not shuffled.

---

## 1. Overview — the five types

Every card in the SUMIMASEN feed is one of five types. Type is determined by the card generator based on the thread's state × available signals × preparability.

- **Respond** — external input requires action; the response is drafted. *Canonical:* "Ocean Farm Co. emailed — draft ready to send."
- **Decide** — multiple options gathered; comparison built; user picks. *Canonical:* "4 diamond stones shortlisted — pick one."
- **Continue** — user was working, went idle, no external forcing function; re-entry state restored. *Canonical:* "Proposal spot search — pick up where you left off (3 tabs, Claude thread)."
- **Complete** — external event closes a step; single confirmation advances the thread. *Canonical:* "Ring shipped from Whiteflash — confirm delivery address."
- **Reflect** — ambient surface of a tension or pattern; no CTA. *Canonical:* "Vancouver-vs-Nairobi tension — held 6 weeks in `## Wants`."

Continue is the load-bearing card type. It's the 2016 concept-browser realized. Every other card type is Continue with a specific trigger overlay + a stronger CTA.

## 2. Common substrate — data model

Every card has the same underlying record shape:

```python
@dataclass
class SumimasenCard:
    id: str                        # UUID
    thread_id: str                 # ref to wiki ## Now or ## Tensions
    thread_name: str               # human-readable
    dimension: str                 # from DIMENSIONS.md (one of 9)
    card_type: Literal[
        "respond", "decide", "continue", "complete", "reflect"
    ]
    trigger: str                   # what fired this card now
    state: str                     # thread state at time of card
    last_left_off: str             # LLM-generated narrative
    prepared_action: PreparedAction | None  # None for Reflect
    ctas: list[CTA]                # ordered by primary
    evidence: list[EvidenceRef]    # links to source material
    surface_priority: float        # from SUMIMASEN_LOSS_FUNCTION
    generated_at: datetime

@dataclass
class PreparedAction:
    kind: Literal["draft", "comparison", "restoration", "confirmation"]
    payload: dict                  # kind-specific
    reversibility: Literal["safe", "committing"]
    confidence: float              # 0..1
    audit: list[str]               # trace of what the LLM used to prepare

@dataclass
class CTA:
    label: str                     # button text
    action_type: Literal[
        "send", "edit", "dismiss", "correct_thread",
        "compare", "restore", "confirm", "acknowledge",
    ]
    payload: dict

@dataclass
class EvidenceRef:
    source_type: Literal[
        "email", "note", "claude_thread", "tab_set",
        "calendar_event", "graph_node",
    ]
    source_id: str
    excerpt: str | None
```

**Storage:** SQLite table `sumimasen_cards` at `~/.mikai/sumimasen.db`. Follows the L4-state-persistence pattern from `docs/research/l4-port-gap-2026-06.md §4` — keeps SUMIMASEN metadata out of Neo4j.

## 3. Per-card-type spec

### 3.1 Respond

**Purpose.** External communication (email, message) arrived that requires the user's action; the response is drafted.

**Trigger conditions.** All must hold:
- Inbound email/message ingested into the graph.
- Sender is linked to an active `## Now` thread (via graph or DIMENSIONS).
- Message content parses to a "requires response" signal (LLM classification).
- No response has been sent within the current session.

**Substrate required.** Inbound email/message (Gmail adapter, iMessage capture); prior correspondence history (graph query); wiki `## Now` context for the thread; any `## Tensions` that gate this response.

**Preparation pipeline.**
1. Extract the ask from the inbound message (LLM).
2. Query graph for prior correspondence + wiki context.
3. Check for unresolved `## Tensions` blocking the response.
4. If a blocking tension is found → downgrade to Continue card with the tension surfaced.
5. Otherwise → draft the response via LLM + skill template.

**CTA shape.**
- `[Send]` — commits the drafted response via `gmail.send` tool.
- `[Edit]` — opens the draft in the user's editor.
- `[Not now]` — dismisses this cycle; thread remains in feed pool.
- `[Wrong thread]` — writes correction back to graph (identity-failure recovery channel).

**Confidence gating.**
- High: "clear intent, sufficient context." → default state, draft shown.
- Medium: "intent clear but context ambiguous." → card shows draft with the uncertainty highlighted inline ("I'm assuming X — correct?").
- Low: "intent unclear." → do not prepare; downgrade to Continue with the raw email surfaced.

**Failure modes.**
- Draft factually wrong → user hits Edit; audit trail preserved for calibration.
- Well-formed but tone-mismatched → user hits Edit; calibration captured.
- Wrong thread → user hits `[Wrong thread]`; graph correction fires.

**Skills invoked (v1).** `skills/draft_business_reply.md`, `skills/draft_personal_reply.md`, `skills/decline_politely.md`.

### 3.2 Decide

**Purpose.** Multiple options gathered across sessions; user picks.

**Trigger conditions.**
- Thread state is `evaluating` (per `FOUNDATIONS.md §3` state machine).
- Options count is stable across 24+ hours — user has stopped gathering.
- Comparison criteria are extractable from thread context.

**Substrate required.** The options (from tabs, notes, Claude threads); extracted criteria (LLM: "what dimensions is the user comparing on?"); optional external metadata (prices, availability).

**Preparation pipeline.**
1. Enumerate options from the thread (LLM extracts from notes/tabs/Claude conversation).
2. Extract the comparison criteria the user has been using (LLM).
3. For each option, gather criterion values. If external data is missing → v1 falls back to LLM knowledge or leaves gaps flagged; v2 spins up an agent for scraping.
4. Build the comparison table.
5. Optionally surface a soft recommendation with explicit confidence.

**CTA shape.**
- `[Compare]` — opens the built comparison view (side-by-side).
- `[Pick <option>]` — one CTA per option; commits selection and offers next-step draft (e.g., "email jeweler about this stone" → chains to a Respond card).
- `[Not now]` — dismisses this cycle.
- `[Add more options]` — reopens the search; downgrades this card to Continue.

**Confidence gating.**
- High: criteria clear + all option data available → default.
- Medium: criteria clear but one or more options missing data → partial comparison with gaps highlighted.
- Low: criteria unclear → do not prepare Decide; surface as Continue.

**Failure modes.**
- Options mismatched → user hits Add more options.
- Wrong criteria → user edits and reselects.

**Skills invoked (v1).** `skills/build_comparison.md`, `skills/extract_criteria.md`.

**V2 extension.** Agent spinup for gathering missing option data (e.g., scrape product pages via Claude Computer Use).

### 3.3 Continue

**Purpose.** User was working, went idle. No external forcing function. Re-entry state restored.

**Trigger conditions.**
- Thread state is `acting` or `exploring`.
- N days since last activity (N calibrated per dimension — 3 for high-priority, 14 for low).
- No external signal has arrived to reactivate.

**Substrate required.** Last-known thread state (wiki `## Now`); last-open tabs (if browser-extension capture is available — v2); last edited note snippets; last Claude thread reference.

**Preparation pipeline.**
1. Query wiki for the thread's last-known state.
2. Query graph for the last N episodes referencing this thread's entities.
3. Build the "last-left-off" narrative (LLM synthesis).
4. Prepare the restoration payload: which tabs to reopen, which notes to surface, which Claude thread to link.

**CTA shape.**
- `[Continue in Claude]` — deep-links back to the thread.
- `[Reopen tabs]` — restores the last-known tab set. **v2:** requires browser extension. **v1:** graceful skip.
- `[Show notes]` — opens the last-edited notes.
- `[Not now]` — dismisses; thread stays in feed pool.
- `[Done — resolved elsewhere]` — writes back to wiki: `state=completed`.

**Confidence gating.**
- High: last-left-off is unambiguous → default.
- Medium: multiple possible re-entry points → offer choice.
- Low: no coherent last-left-off (thread has drifted) → do not surface Continue; wait for external signal.

**Failure modes.**
- User already resolved offline → hits Done; state=completed writes back.
- User has moved on → hits Not now repeatedly; SUMIMASEN's calibration lowers this thread's frequency.

**Skills invoked (v1).** `skills/build_reentry_narrative.md`.

### 3.4 Complete

**Purpose.** An external event closes a pending step; a single confirmation advances the thread.

**Trigger conditions.**
- External signal detected that maps to a thread's pending step. Examples:
  - Email arrives with "order shipped" language on a thread with a `pending: shipping` step
  - Calendar event ends that corresponds to a `pending: meeting` step
  - Message received that satisfies a `pending: reply` step
- Confidence in the mapping is high.

**Substrate required.** The external signal event; the thread's pending steps (from wiki `## Now`).

**Preparation pipeline.**
1. Match external signal to pending step (LLM).
2. Prepare the confirmation payload — what state transition writes to the wiki?
3. Optionally prepare the next step (e.g., "shipped → next step is arrival tracking").

**CTA shape.**
- `[Confirm — mark as X]` — writes state transition to wiki.
- `[Confirm + next step]` — confirms + prepares the next Continue or Complete card.
- `[Not this step]` — user rejects the mapping; audit for calibration.
- `[Dismiss]`.

**Confidence gating.**
- High: unambiguous match → default.
- Medium: multiple possible pending steps → offer choice.
- Low: no clear match → do not prepare Complete; surface as Continue.

**Failure modes.**
- Wrong step matched → user rejects; calibration.
- Step doesn't actually exist (system hallucinated) → user rejects; audit.

**Skills invoked (v1).** `skills/match_event_to_step.md`, `skills/prepare_state_transition.md`.

### 3.5 Reflect

**Purpose.** Ambient surface of a tension or pattern; no CTA.

**Trigger conditions.**
- Thread is in `## Tensions` and has been held for T weeks.
- No recent resolution attempt (no state change, no relevant episodes).
- User has not seen a Reflect card for this tension within the cooldown window.

**Substrate required.** The tension entry from `## Tensions`; optional recent frames that reinforced or contradicted it.

**Preparation pipeline.**
1. Extract the tension text from `## Tensions`.
2. Surface its recency (how long held).
3. Optionally name any recent frames that pressed on it.

**CTA shape.**
- `[Acknowledge]` — soft dismiss, logged as seen.
- `[Dismiss]` — hard dismiss, longer cooldown.

**No commitment actions.** Reflect never fires push. Never escalates.

**Confidence gating.** Any confidence level acceptable — Reflect is the low-stakes card type.

**Failure modes.** User finds it intrusive → hits Dismiss; longer cooldown next time.

**Skills invoked (v1).** `skills/surface_tension.md`.

**This is the calm-technology card type.** Trains the user that SUMIMASEN doesn't always demand action.

## 4. Card generation pipeline

Run per SUMIMASEN cycle (default: every 4 hours; also on-demand via CLI):

1. Load current wiki (`## Who`, `## Now`, `## Tensions`, `## Wants`).
2. Load `DIMENSIONS.md`.
3. Load `USER_NEEDS_REGISTRY.md`.
4. Load recent external signals (last N hours): email, calendar, messages.
5. For each `## Now` thread + each `## Tensions` entry:
   1. Determine candidate card type(s) via state × trigger table.
   2. For each candidate:
      1. Check preparability (do we have the tools + substrate?).
      2. Attempt preparation (LLM + skill invocation).
      3. Compute confidence.
      4. If confidence < threshold → skip.
      5. Compute `surface_priority` via `SUMIMASEN_LOSS_FUNCTION`.
   3. Keep the highest-priority preparable card for this thread.
6. Rank all prepared cards by `surface_priority`.
7. **Filter by one-notch discipline** (must prepare at least one atomic step; Reflect is the sole exception).
8. Deduplicate by dimension (max 2 cards per dimension per cycle).
9. Cap to top N (default N=10 for feed; top 3 for Calendar brief; top 1 for push escalation).
10. Emit cards to the appropriate surface(s).
11. Log full audit trail to `~/.mikai/sumimasen/audit.jsonl`.

## 5. Confidence × reversibility matrix

Determines default posture:

- **High confidence + Safe reversibility** (draft, comparison, restoration) → prepare + present in card; user commits with tap.
- **High confidence + Committing reversibility** (send, book, submit) → prepare + present as draft-with-commit-CTA; user commits with explicit tap. Never auto-execute in v1.
- **Medium confidence + Safe** → prepare with highlighted uncertainty; card shows the ambiguity inline.
- **Medium confidence + Committing** → downgrade to a lower card type (Respond → Continue).
- **Low confidence, any reversibility** → do not prepare; surface as Continue with context only, or skip entirely.

## 6. Preparation infrastructure

Three layers:

**(a) MCP tool discovery.** SUMIMASEN's card generator enumerates available MCP tools at cycle start. Tools required for v1: `gmail.send`, `gmail.draft`, `calendar.create_event`, `notes.append`, `browser.open_tabs`. Each card type declares its required tools; if a tool is missing, that card type is unavailable for the current cycle. Discovery happens via standard MCP `list_tools` on connected servers.

**(b) Skills catalog.** Directory: `infra/decider/skills/`. Each skill is a markdown file with a prompt template + a description of when to invoke. Skills for v1 (9 files):

- `skills/draft_business_reply.md`
- `skills/draft_personal_reply.md`
- `skills/decline_politely.md`
- `skills/build_comparison.md`
- `skills/extract_criteria.md`
- `skills/build_reentry_narrative.md`
- `skills/match_event_to_step.md`
- `skills/prepare_state_transition.md`
- `skills/surface_tension.md`

Skill files follow the Anthropic Skills / Hermes Skills convention: a system-prompt-shaped markdown that gets injected into the LLM call for that specific preparation step.

**(c) Agent spinup.** Deferred to v2. When a card type needs multi-step external work (e.g., scraping product pages for Decide), SUMIMASEN would spin up a Claude Agent SDK harness and await results. v1 falls back to LLM knowledge or leaves gaps flagged in the card.

## 7. The one-notch discipline

Enforced as a filter in step 7 of the pipeline. A card without a `prepared_action` (except Reflect) is dropped from this cycle's feed. Dropped threads get logged in the audit trail with reason ("no prepared next step found — thread `X`, tried all card types, low confidence on all") — the calibration signal that lets SUMIMASEN measure "why we can't help thread X."

Dropped threads still exist in the wiki. They re-enter the feed when either (a) a new external signal fires (email arrives, calendar event lands, note is edited) or (b) confidence grows because the substrate has more context.

## 8. Success metrics per card type

Additive to `SUMIMASEN_LOSS_FUNCTION`'s PPP metrics:

- **Respond:** send-rate (drafted → sent) target ≥60%; edit-rate ≤30%; wrong-thread rate ≤5%.
- **Decide:** pick-rate target ≥40%; add-more-options rate ≤20%.
- **Continue:** re-entry rate (tap Continue → actual work session started) target ≥30%; done-resolved-elsewhere rate ≤15%.
- **Complete:** confirm-rate target ≥70%; not-this-step rate ≤10%.
- **Reflect:** acknowledge-rate target ≥30%; hard-dismiss rate ≤20%.

## 9. What v1 ships

- All 5 card types with LLM-only preparation (no agent spinup).
- Feed surface: Calendar brief (already exists via `dispatch_calendar.py`) + a new web dashboard at `localhost:8100/feed`.
- Push escalation: reuses existing ntfy + osascript dispatch from `SUMIMASEN_SURFACE_DECISION.md`.
- Storage: `~/.mikai/sumimasen.db` (SQLite) for cards; `~/.mikai/sumimasen/audit.jsonl` for the audit trail.
- Skills: 9 markdown files as above.
- CLI: `sumimasen mark-acted <id>`, `sumimasen mark-dismissed <id>`, `sumimasen show-feed`, `sumimasen dry-run`.
- Metrics: nightly summary appended to wiki `log.md`.

## 10. What v1 does NOT ship

- Agent spinup for complex card preparation (deferred to v2).
- Browser tab capture (deferred to v2 — requires browser extension).
- Multi-modal cards (video, audio).
- Vision B: external content aggregation (RSS, news, closed-ecosystem content).
- Multi-user support.
- Auto-execute without confirmation for any action-taking card.

## 11. Testing and acceptance criteria

**Per card type — integration tests validate:**
- Preparation happens deterministically given the same substrate + signals.
- Confidence gating drops low-confidence cards before they reach the feed.
- Failure modes (wrong thread, wrong step) route to correction channels.
- Audit trail is complete for every dispatched card.

**End-to-end acceptance for v1:**
- SUMIMASEN runs a full cycle in <30 seconds against the current wiki + graph.
- The feed contains 5–10 cards per cycle in a real Brian-scale substrate.
- Each card in the feed either (a) has a `prepared_action` or (b) is a Reflect card.
- No card in the feed lacks evidence.
- All cards' audit trails are queryable via SQLite.

## 12. Implementation sequencing (recommended)

To ship v1 without over-scoping:

1. **Continue card first** — it's the load-bearing type and has the fewest external dependencies (no MCP tools required beyond wiki + graph read). Ship, calibrate, verify one-notch discipline holds.
2. **Reflect second** — trivial to implement, zero action risk. Trains the user that SUMIMASEN can be quiet.
3. **Respond third** — requires MCP outbound (Gmail send). Highest-value use case (the ocean-farming example).
4. **Complete fourth** — requires signal-matching. Depends on ingestion already extracting email/calendar boundaries.
5. **Decide fifth** — most complex preparation. Delay until the other four are calibrated.

Each card type has independent acceptance criteria (§8, §11). Ship one, calibrate, ship the next.

---

**Cross-references:**
- `SUMIMASEN_VISION.md` — the load-bearing vision.
- `SUMIMASEN_LOSS_FUNCTION.md` — the `surface_priority` + PPP metrics.
- `SUMIMASEN_SURFACE_DECISION.md` — where cards are delivered.
- `DIMENSIONS.md` — the life ontology.
- `USER_NEEDS_REGISTRY.md` — hand-authored need entries.
- `MEMORY_ARCHITECTURE.md` — the wiki + graph substrate.
- `DREAM_WIKI_RUNTIME.md` — how the wiki gets built.
- `docs/research/l4-port-gap-2026-06.md` — the L4 → port audit that informs the storage layer.
