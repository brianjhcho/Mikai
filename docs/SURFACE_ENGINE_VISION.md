# SUMIMASEN — Vision

> **What this file is:** The load-bearing statement of what SUMIMASEN is, why it exists, and what it will not be. Anchors the other SUMIMASEN docs (`LOSS_FUNCTION`, `SURFACE_DECISION`, `CARD_TYPES`).
> **Written:** 2026-07-04 as consolidation across the 2026-06 strategic research thread (`docs/research/strategic-research-2026-06.md`) and the 2026-07 design conversation.
> **Status:** V1 vision, subject to refinement as implementation surfaces failure modes.

---

## 1. One-sentence definition

**SUMIMASEN is a continuation feed for a single user's own captured intent, rendered as prepared-execution cards that push each of the user's active threads forward by one atomic step.**

## 2. What each phrase carries

**Continuation feed** — not a notification, not a chat, not a to-do list. An ambient surface the user glances at, showing where they left off across N active threads. Feed is pull-primary; push is escalation for the small subset of items that clear a high urgency + confidence bar.

**Single user's own captured intent** — the substrate is what the user themselves demonstrated interest in through their behavior: browser tabs, notes, Claude threads, calendar, messages, wiki. Not external content curation (Google Discover, Apple News). Not other people's content (Instagram, TikTok, Twitter feeds). Their own trail.

**Prepared-execution cards** — each item in the feed is not a link or a reminder; it is the next action, already prepared. Draft written. Comparison built. Form filled. Re-entry state restored. The user's tap approves or edits; it does not initiate.

**Push each active thread forward by one atomic step** — the operational discipline. A thread earns a card in a given cycle only if SUMIMASEN can prepare at least one atomic advancement toward it. Threads that can't be advanced this cycle stay silent.

## 3. Why this exists — the notification lineage

The pre-existing history of software-to-user surfaces runs through six categories:

- **L1** — Interpersonal message (WhatsApp, iMessage): sender identified, verbatim content, reply CTA. **Not SUMIMASEN.**
- **L2** — Transactional (bank alert, delivery update, calendar reminder from a real event): institution identified, data point, single CTA. **Not SUMIMASEN.**
- **L3** — App-content notification (news, social, promotional): brand identified, content teaser, "open app" CTA.
- **L4** — Aggregated system reflection (Screen Time weekly, wellness summary): OS identified, behavioral observation, diffuse action.
- **L5** — Contextual reminder (IFTTT, Shortcuts, location-based): user's rules identified, trigger fired, user-defined action.
- **L6** — AI recommendation from behavioral signal (Siri Suggestions, Google Now, Apple Intelligence Priority): system identified, predicted useful info, opaque action.

**SUMIMASEN sits at L3–L6 as delivery, with a payload that is state-aware synthesis from a personal wiki.** Everything from L3 through L6 is system-authored — SUMIMASEN's operating range. Below L3 is other people's messages (WhatsApp) and other institutions' transactions (banks); those existing stacks handle themselves.

The 2020s frontier the field is stumbling toward is **LLM-mediated continuation feeds** — surfaces that show your own captured intent, synthesized by an LLM, delivered in an ambient way. Nothing ships this well today. Chrome Journeys (Google, 2022) and Windows Timeline (Microsoft, 2017–20) captured activity but didn't synthesize it. Rewind and Limitless capture but require search — you have to know what you're looking for. ChatGPT and Claude memory retain but stay chat-bound — you have to open the chat. Notion and Obsidian have backlinks but require you to be in the graph. **SUMIMASEN targets the gap where none of them go.**

## 4. Lineage — the 2016 concept browser

The original idea (Brian, 2016): a "concept browser" that would read your browsing history, extract the concepts/products/information you were looking at, apply a density or cluster function to identify what mattered, and either bring the user through the journey or synthesize the content into a page.

That vision partially shipped a decade later, but in pieces that don't compose:

- Chrome Journeys shipped the cluster function.
- Rewind → Limitless shipped the capture layer.
- ChatGPT/Claude memory shipped the synthesis primitive.
- Notion/Obsidian shipped the graph.

SUMIMASEN composes these — capture, cluster, synthesis, state-awareness, delivery — into one surface. The 2016 vision is technically executable in 2026 in ways it wasn't a decade ago.

## 5. Prepared execution — the load-bearing design principle

The single design commitment that distinguishes SUMIMASEN from every prior attempt: **cards are the next action pre-loaded, not the next reminder.**

- Chrome Journeys shows you what tabs you had open — you have to figure out what to do with them. SUMIMASEN shows you the drafted email that answers the ocean-farm follow-up; one tap sends.
- Rewind lets you search for what you did last Tuesday — you have to know what you're looking for. SUMIMASEN says "you narrowed to four diamond stones for the proposal ring; here's the side-by-side, pick one"; the comparison is built.
- Notion has backlinks — you have to be inside Notion to see them. SUMIMASEN says "you were exploring rooftop proposal venues but haven't visited any; here's your Claude thread and the three shortlisted venues"; the re-entry state is restored.

**The card IS the digital path, ready to walk.** Not a signpost pointing at where you should look next.

Consequence for build discipline: **any card type that cannot be prepared with the current substrate + tools is not shipped.** Better to have fewer card types working well than many card types half-working.

## 6. Two visions — pick one for v1

**Vision A — continuation feed over the user's own trail.** Small substrate (tabs, notes, Claude threads, wiki, calendar, messages). Nobody else has this substrate at this depth for this user. Feed shows re-entry to the user's own prior state. Ships in weeks; defensible because the substrate is unique.

**Vision B — everything-in-one-place aggregator.** Large substrate (Vision A + Instagram/TikTok/Twitter/RSS/news). Delivers the "one place for all my inputs" intuition. Hits the closed-ecosystem constraint; competes against Instagram/TikTok on their own turf.

**v1 = Vision A.** Vision B is a Phase 3 extension after Vision A earns the right. Explicitly out of scope for v1: aggregating closed-ecosystem content, curating external news/RSS feeds, replacing existing social-media consumption.

## 7. Success criteria for v1

SUMIMASEN's v1 succeeds if:

- The continuation feed is checkable in an ambient surface (Calendar entry, web dashboard, or new tab) — no push required for daily use.
- Cards are the prepared next action for at least 3 of the 5 card types (see `SUMIMASEN_CARD_TYPES.md`).
- Continuation rate (feed item → user action within N minutes) exceeds 30% for top-ranked cards.
- The first 20 cards Brian sees across the first two weeks produce zero identity-failure dismisses ("this isn't me / not my priority anymore").
- The one-notch discipline holds: SUMIMASEN never surfaces a card that doesn't prepare at least one atomic step.

## 8. Non-goals (v1)

- **Not a push-notification improvement.** SUMIMASEN's push surface (ntfy + osascript) is escalation only, not primary.
- **Not a chat UI.** No conversational interface. Cards are cards.
- **Not a to-do list.** Cards are re-entry points, not tasks-to-complete. Todoist, Things, Notion tasks fill that need if the user wants it.
- **Not external content curation.** Instagram/TikTok/Twitter/news/RSS excluded from v1's feed substrate.
- **Not multi-user.** Single-user, Brian's own trail.
- **Not action execution without confirmation.** Every action-taking card requires a user tap. SUMIMASEN prepares; the user commits.

## 9. Relationship to other SUMIMASEN docs

- `SUMIMASEN_LOSS_FUNCTION.md` — how ranking + `surface_priority` + PPP metrics work. The mathematical spec.
- `SUMIMASEN_SURFACE_DECISION.md` — which surfaces v1 ships (ntfy, Calendar, osascript, terminal-notifier, CLI). The operational spec.
- `SUMIMASEN_CARD_TYPES.md` — the five card types, their preparation pipelines, and their failure modes. The implementation spec.
- `DIMENSIONS.md` — the life-ontology feeding SUMIMASEN's dimension routing.
- `USER_NEEDS_REGISTRY.md` — hand-authored needs that seed the `## Now` threads.
- `MEMORY_ARCHITECTURE.md` — the wiki + graph substrate SUMIMASEN reads from.
- `DREAM_WIKI_RUNTIME.md` — how the wiki gets built nightly.

## 10. Cross-references outside SUMIMASEN

- `docs/FOUNDATIONS.md §3` — L4 research bridge (intervention timing, five papers, task-boundary principle).
- `docs/research/strategic-research-2026-06.md` — the personal-memory landscape and Jensen control-layer framing that positions SUMIMASEN.
- `docs/OPEN.md` — O-043 (core noun), O-044 (noticer/executor), O-045 (vertical/horizontal), O-046 (user), O-047 (moat). O-043 is answered by this doc; the others remain open.
- `docs/VISION.md` — the noonchi positioning; SUMIMASEN is the operational realization.
