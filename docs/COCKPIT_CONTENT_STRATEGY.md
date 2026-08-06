# Cockpit content strategy — survey, stress-test, ranked recommendations

*2026-08-06 · Fable 5. Inputs: `COCKPIT_STRUCTURE_RESEARCH.md`, `COCKPIT_ORGANIZATION_TRADEOFF.md`, `COCKPIT_INPUT_FEATURE.md`, `HARNESS_ARCHITECTURE.md` — settled, not reopened. Under test: Brian's intuition — "show the most important things in my life, where the progress is; clickable → detail panel" — against a substrate (8,049 sections, 375 entities, ask) invisible in the cockpit.*

## 1. What primary views actually show — categories the first survey missed

Sixteen products fetched; the *decision* each made:

1. **Sunsama** — today's tasks and meetings merged into one column; the human declares importance each morning via a planning ritual. [sunsama.com](https://www.sunsama.com/)
2. **Motion** — the calendar as decision surface: AI tells you "the best task to work on at any moment." One answer, not a list. [usemotion.com](https://www.usemotion.com/)
3. **Reclaim.ai** — time *recovered*: defended focus hours, meeting load — deltas, not inventories. [reclaim.ai](https://reclaim.ai/)
4. **Amie** — calendar + todos unified; AI reshuffles when plans change. [amie.so](https://www.amie.so/)
5. **Superhuman** — "respond faster to what matters most" + follow-ups that would otherwise drop: triage plus decay-watch. [superhuman.com](https://superhuman.com/)
6. **Streaks** — up to 24 habits but one metric: consecutive days. Continuity-at-risk is the signal. [streaksapp.com](https://streaksapp.com/)
7. **RescueTime** — where your time actually went; activity visibility as the product. [rescuetime.com](https://www.rescuetime.com/)
8. **Mesh** (Clay; clay.earth now 301s to me.sh) — filterable feed of relationship events: reconnect prompts, birthdays, life updates. [me.sh](https://me.sh/)
9. **Dex** — keep-in-touch reminders first; timeline second. Time-since-last-touch is the primary signal. [getdex.com](https://getdex.com/)
10. **Things 3** — Today: today's tasks + calendar events + "This Evening," nothing else; badges and clutter deliberately absent. [culturedcode.com](https://culturedcode.com/things/features/)
11. **OmniFocus** — Forecast: due items interleaved with calendar events on a day axis. [omnigroup.com](https://support.omnigroup.com/documentation/omnifocus/mac/2.12/en/forecast/)
12. **Todoist** — Today/Upcoming; "see only what you need, when you need it." [todoist.com](https://www.todoist.com/)
13. **Granola** — the meeting note itself is the workspace; actions and next steps inline, corpus invisible. [granola.ai](https://www.granola.ai/)
14. **Limitless** (Rewind's successor; rewind.ai redirects elsewhere, limitless.ai homepage 500'd — help docs used) — the day as chronological topic blocks, plus "Ask about anything you've said or heard" as a persistent bottom input. [help.limitless.ai](https://help.limitless.ai/en/articles/10546658-interacting-with-the-pendant-search-ask-ai-summaries)
15. **Fibery** — no default view at all: twelve view types, the "architect" user assembles their own. [fibery.com](https://fibery.com/)
16. **Stoic** — one reflective prompt at a time; morning/evening check-in. Radical fewness as register. [getstoic.com](https://www.getstoic.com/)

*Couldn't verify:* Monica, Habitica, Day One (pages uninformative); Vimcal, Fyi, Timing, Sessions, Way of Life, Journey, Linear-as-personal not fetched.

## 2. The pattern

Four convergences:

- **Today, not the archive.** Nearly every primary view is indexed to *now* — Sunsama, Motion, Amie, Things, OmniFocus, Todoist, Limitless, Stoic. Nobody leads with their corpus.
- **Next action, approaching singular.** The strongest compress toward one answer: Motion's "best task right now," Stoic's one prompt, Superhuman's "what matters most."
- **Decay is a first-class signal.** The whole personal-CRM category (Dex, Mesh, Monica's pitch) leads with *what you've neglected*; Superhuman's follow-ups and Streaks' about-to-break streaks are the same signal in other clothes.
- **Substrate is invisible; it shows up as answer quality.** Limitless — MIKAI's closest structural cousin — surfaces a day summary and an ask box, never "n hours recorded." RescueTime, which *does* lead with activity inventory, is the category's churn cautionary tale.

Shared framework: **primary view = attention trigger; detail = context on demand.** Brian's "clickable → detail panel" is exactly this. The contested half is what triggers attention.

## 3. Five attacks

**Attack 1 — who defines "important"?** *Steelman:* someone must rank, and MIKAI's thesis is that the substrate can. *Counter:* no surveyed product infers importance from scratch. All split the job — humans *declare* the set (Sunsama's ritual, Motion's deadlines), machines *rank within it* by urgency and decay. Silent LLM reordering of a life is unaccountable, and MIKAI's consent moat (`HARNESS_ARCHITECTURE` §1) already rejects it. **Verdict: modified.** The hubs and threads Brian created *are* the declaration; MIKAI ranks within them by state and staleness. Anything it wants to *add* to the set is an `inbox/` proposal, never a silent insertion.

**Attack 2 — what is "progress"?** *Steelman:* movement is legible and motivating. *Counter:* log entries are activity; RescueTime proves activity visibility changes nothing. In MIKAI's own schema, progress is **state transitions toward resolution** and the reduction of open loops — Reclaim's insight that deltas beat inventories. **Verdict: modified.** "Where the progress is" must mean "where state changed," never "where the log grew." Render transitions, not volume.

**Attack 3 — important but not progressing.** *Steelman:* a progress view naturally spotlights movement. *Counter:* taken literally, "show me where the progress is" would *hide* the 17-day-stalled proposal thread — the most attention-worthy object in the sky. An entire category (personal CRM) exists because decay, not progress, is the primary signal; `COCKPIT_STRUCTURE_RESEARCH` §2.2 already made stall a first-class regression. **Verdict: rejected as phrased.** Correct formulation: show **where attention is owed** — "state just changed" (momentum to ride) ∪ "state should have changed and didn't" (decay to arrest). The one place Brian's wording is plainly wrong.

**Attack 4 — serendipity from the substrate.** *Steelman:* Mesh ships exactly this — ambient life-update feeds — and users value it; 8,049 sections earning zero pixels feels wasteful. *Counter:* a signal feed is the dashboard register `COCKPIT_ORGANIZATION_TRADEOFF` §4 closed against, and mention-frequency surfacing is the ambient-presence noise `ENTITY_MODEL` rejected. The substrate's designed outlets exist: **ask** (depth felt as answer quality — the Limitless pattern) and **entity edges** (cross-life patterns as structure, not feed). If "Black Forest Labs × 4 this week" clears a threshold, it's a `consolidate` proposal into `inbox/`, not a cockpit ticker. **Verdict: rejected for the primary view.** Serendipity routes through edges, ask, and triage — channels that already exist.

**Attack 5 — attention economics.** *Steelman of the attack:* Cowan's ~4-item working memory says 4 hubs × 5 threads = 20 competing nodes; Motion and Stoic go to *one*. *Counter:* the arithmetic treats the portrait as a list. A constellation is read as a gestalt — dim nodes are scenery, not items; the cost is per *salient* node. **Verdict: modified.** Keep the full sky; enforce a **salience budget** — at most 3–4 nodes visually loud (pulsing, warm, bright) at any render. "Most important things" is not radical fewness of objects but of *emphasis*.

**Net:** Brian is right about clickable-portrait-with-detail and that fewness matters. He is wrong that progress is the beacon — attention-owed is — and importance must stay human-declared, machine-ranked.

## 4. What the cockpit should surface

**Always visible — the attention head.** One line, top of sky: the thread MIKAI would interrupt about if allowed — Sumimasen's top candidate, rendered passively. `PROPOSAL — stalled 17d — next: venue shortlist`. The cockpit answering "what is today for."

**The 3–5 beneath:**
1. The constellation — hubs + threads, state styling, salience budget (≤4 loud).
2. Staleness as decay — stalled threads age visibly (dimming + day count); resolved threads leave the sky (`COCKPIT_STRUCTURE_RESEARCH` §2.3).
3. A delta strip — ≤3 state transitions since last open (Attack 2's survivor).
4. The ask input (§5).
5. Entity edges on hover — the approved serendipity channel.

**Deferred to hover/detail:** next-step, trajectory strip, linked decisions, entangled-with rows, full log, provenance.

**Never shown:** substrate counts (8,049 sections / 375 entities is vanity — Limitless hides its equivalent), ingestion health (the plate's register), activity volume, capability inventory (rising-KPI telos already rejected), any unbounded feed.

**Score against `COCKPIT_ORGANIZATION_TRADEOFF` §4:** in-register. Topic view only; attention head and delta strip are *state*, not metrics; no toggles, charts, or function anatomy. The one deliberate drift — an input on a read-only portrait — was pre-approved by `COCKPIT_INPUT_FEATURE` §5 ("quiet input, portrait register intact"), whose CLI-first trigger the parallel wiring work has met.

## 5. Where ask lives

**Bottom bar.** Persistent, quiet, placeholder-text register — the Limitless pattern ("Ask about anything you've said or heard"), chosen by the shipped product whose substrate most resembles MIKAI's. Top bar reads as search chrome; overlay/modal reads as interruption and hides the portrait exactly when the answer should be seen against it. Bottom-of-workspace reads as *addressing the portrait*.

Interaction: the answer opens in the existing left detail panel — prose, the map-plus-reading-pane discipline of `COCKPIT_STRUCTURE_RESEARCH` §2.1 — not a chat transcript; no conversation UI accretes. Threads and entities the answer cites glow while it is open — the `COCKPIT_ORGANIZATION_TRADEOFF` §5 move: substrate legible through behavior. The 24 hours of depth is *felt* as grounded answers and glowing provenance, without one substrate statistic on screen.

## 6. Ranked build items

1. **Attention head + salience budget** in the T2 generator/renderer — rank by attention-owed (transition recency ∪ stall age), cap loud nodes at 4. Makes the portrait answer the 7am question.
2. **Delta strip** — diff thread states against last-open snapshot; render ≤3 transitions. Closes Attack 2.
3. **Ask, visually integrated** — bottom bar, detail-panel answers, cited-node glow. (Plumbing is the parallel Fable's; this is the portrait-side contract.)
4. **Entity edges** — already specced (`COCKPIT_STRUCTURE_RESEARCH` §3, ~one day); the channel that keeps Attack 4's rejection honest.
5. **Thread mortality styling** — staleness dimming, archival exit, no rising counts.

Frame: not customer-release — the cockpit becoming the product experience the substrate already earned.
