# MIKAI Strategic & Product Insights

**Last updated:** 2026-05-11
**Purpose:** Standing reference for product, strategy, and architecture decisions. Intended for upload into the MIKAI Claude Project to provide continuity across conversations.
**Companion docs:** `PHILOSOPHICAL_LINEAGE.md` (Bush → Weiser → 2026 intellectual lineage), `CURRENT_STACK.md` (Graphiti-only post-cleanup state), `CLAUDE.md` (build-task contract).

---

## TL;DR

MIKAI is a **specialized vertical consumer-utility product** for cross-source personal task-state awareness, ambient delivery, and action-not-engagement. Closest historical analog: Photoshop or Quicken (specialized vertical) — not Microsoft or Apple (general assistant). The proposed moat is *depth of personalization compounding over time*, which is novel in the consumer-utility category and therefore both the largest opportunity and the largest risk.

The honest base rate: consumer-utility apps facing platform bundling historically die, get acquired, or pivot to enterprise. Survival as an independent consumer product requires either (a) network effects, (b) regulatory/professional complexity moat, or (c) Discord-style vertical-segment community. MIKAI does not yet have any of these and must build at least one.

Probability estimates from the strategic analysis:
- ~60% MIKAI survives as a vertical specialist for a defined segment, conditional on active defense
- ~25% gets squeezed between OS + Copilot + open-source
- ~15% category-defines before incumbents commit

The single thing to watch: Apple opening Apple Intelligence to third-party cloud sources (probable timeframe: WWDC 2027). If they do, the cross-source moat narrows to non-Apple platforms. If they don't, the specialized-vertical thesis has real runway.

---

## 1. Threat landscape — the OS-absorbs-the-assistant stress test

Five scenarios that would kill MIKAI's specialized-vertical thesis, with probability estimates:

### Scenario A — Apple opens the walled garden (25%)
Apple Intelligence adds connected accounts for ChatGPT, Claude, Gemini, Notion. App Intents extends to web reading history. On-device processing preserves the privacy story.
- **Why possible:** Apple already permits a ChatGPT extension for Siri; Google's Gemini pressure could force expansion.
- **Why unlikely:** "Privacy" is Apple's brand moat; ingesting third-party cloud data, even locally, is the kind of move Apple legal blocks.
- **If it happens:** MIKAI's cross-source moat collapses on iOS/Mac. Desktop/Linux/Windows/Android users remain — narrower market.

### Scenario B — Microsoft Copilot+ eats "work" (30%)
Copilot already sees Office/Outlook/Teams/SharePoint. Add GitHub, Slack, Zoom. For professional knowledge workers, Copilot covers 80% of the workweek.
- **Why highest probability:** Already shipping, enterprise distribution in hand, marginal work to extend within walled garden is small.
- **MIKAI's opening:** Copilot stops at the professional boundary. Doesn't cross into WhatsApp, Substack, iMessage, personal email, personal notes, reading history.
- **If it happens:** MIKAI cannot win "help me finish work emails." Can still win "help me finish the Kenya coffee project, which spans work-Slack, personal-WhatsApp, Claude-research, and Apple-Notes."

### Scenario C — ChatGPT/Anthropic bolt on memory + sources (20%)
ChatGPT Pulse is already a weak version. Strengthen memory, add source imports (Gmail export, Notion OAuth), add cross-conversation state tracking, ship daily briefings.
- **Why possible:** OpenAI is openly pursuing ambient (Operator, Computer Use). Pulse was the first move. User base and model quality already exist.
- **Why not the full category:** Cross-source personal ingestion is a distraction from model scaling. They lack a non-chat surface. Pulse is a briefing, not calm tech.
- **If it happens:** MIKAI pushed up the specialization curve. The generic "ambient agent with memory" tier gets absorbed; MIKAI survives only with depth features Pulse can't match.

### Scenario D — Open-source stack becomes plug-and-play (15%)
Graphiti + LangGraph + open ambient layer becomes a Docker-compose away. Technical users self-host. MIKAI becomes a hosted wrapper competing on convenience.
- **Why real:** Graphiti, A-MEM, LangMem, Letta — all open. Happening at the L3 layer.
- **Why slower than it sounds:** Self-hosting always-on personal ingestion is painful for normies. Most self-hosting projects cap at small technical audiences.
- **If it happens:** MIKAI's positioning shifts from category-defining to convenience-tier. See GitHub (hosted Git), Supabase (hosted Postgres) — still a real business.

### Scenario E — Ambient surfaces stay locked (30%)
Apple never lets a third-party AI truly live on the lock screen or persistent iOS widget. Android dominated by Samsung/Google defaults. Calm-tech surfaces remain platform-owned.
- **Why structural:** MIKAI's commitment to calm tech needs surfaces; surfaces are owned by platforms. Raycast on Mac is the one exception.
- **Mitigation:** Own surfaces MIKAI can win — Raycast, browser extensions (Chrome/Arc/Dia), iOS Shortcuts + App Intents + widgets (limited but real), desktop companion app, MCP-in-Claude. Accept that iOS lock screen is not MIKAI's to own.

### Three defense conditions
The specialized-vertical thesis is not wishful thinking, but it requires active defense:
1. **Don't drift into general assistant features.** Every feature that isn't cross-source-depth invites OS competition.
2. **Own surfaces the platforms won't or can't.** Desktop (Raycast, menubar, browser extension) is defensible. Mobile lock screen is not.
3. **Keep the user segment well-defined and narrow.** "Everyone" is wishful. "Indie operators with ≥5 sources and a cross-source workflow" is defensible.

---

## 2. The depth thesis — what the moat looks like in features

Seven dimensions of feature investment. Each is something Apple Intelligence + Copilot cannot do, and that compounds with use.

### D1 — Depth of cross-source synthesis
Not "ingest more sources" (breadth). "Reconstruct single threads across sources with temporal ordering" (depth).
Example: Martin mentioned the Kenya harvest timeline in WhatsApp on March 3. User replied in Claude on March 5 asking for specific cultivar names. Martin emailed the answer on March 7 from his farm address. User drafted a follow-up in Apple Notes on March 10 but didn't send it. *That thread is stalled at the Notes draft, 14 days old.*

### D2 — Depth of state model
Not "todo/done" (breadth). A full state vocabulary with transitions as first-class data.
States: `exploring → decided → acting → stalled → (waiting-on-other | waiting-on-info | waiting-on-approval | waiting-on-self) → resumed → completed → dropped → pivoted`. The transitions between states are themselves data — a user who moves quickly from `exploring` to `dropped` has a different signature than one who hits `stalled` repeatedly before `acting`.

### D3 — Depth of personal modeling
Not "generic stall detection" (breadth). User-specific behavioral modeling.
Examples: "You tend to drop threads requiring coordination across 3+ people. This thread just hit 4." / "You typically reply to Martin within 5 days; this is day 12." / "You defer big decisions to Sunday morning. This is Tuesday 2pm — surfacing this is wrong timing."

This is Engelbart's C-level — the system models how *you specifically* work and improves your meta-process over time.

### D4 — Depth of next-step inference
Not "you have a stalled thread" (notification spam). Pre-composed next-step drafts grounded in the thread history, in your voice.

### D5 — Depth of opportune-moment detection (Sumimasen layer)
Not "push notifications on a schedule" (breadth). Context-aware surfacing tied to user attention state.
- User opens WhatsApp Martin conversation → surface Kenya thread context inside WhatsApp.
- User starts a Claude message about coffee → inject thread context as Claude system prompt, invisible to user.
- User closes last calendar block of the day → surface "threads that went stale today."
- User in deep-focus (camera/calendar/active-app signals) → say nothing.

Timing accounts for 40% of intervention-acceptance variance (arXiv:2602.00880). Depth here is knowing when *not* to surface.

### D6 — Depth of temporal modeling
Not "timestamps" (breadth). Bitemporal reasoning over contradictions and cadence.
- "On March 3 you said Kenya was on hold. On April 5 you told Martin it was back on. Which is current?"
- "Your typical cadence for Martin threads is 5 days. Current gap: 14 days. Confidence stalled vs. paused: 72%."
- "The quarterly review pattern hits the 3rd Friday every quarter. Next: 11 days. You haven't started prep."

Graphiti's bitemporal edges give this structurally. No OS-level assistant reasons in two time dimensions.

### D7 — Compounding corpus value
Not "works out of the box" (breadth). Monotonically increasing value over years.
- Month 1: baseline. MIKAI ≈ ChatGPT with memory.
- Month 6: state model has learned transition patterns. Drafts sound like you.
- Year 1: 10K+ episodes. Cross-source threads reconstructed with high precision. Proactive patterns emerge.
- Year 3: MIKAI is a model of how you think that nobody else has. Switching cost prohibitive.

This is the Photoshop/Quicken moat — cumulative user investment becomes the lock-in. Apple Intelligence users get no equivalent compounding because Apple resets with every iPhone they replace.

### The acid test
A candidate feature passes as "depth" if all five hold:
1. Only makes sense for a user with cross-source personal data at scale.
2. Compounds — each use makes future uses better.
3. Apple Intelligence won't build it (privacy/data-boundary reasons).
4. Copilot won't build it (consumer-source / cross-personal reasons).
5. A power user would notice its absence; a median user wouldn't notice its presence.

Fail 2+ → it's breadth, not depth. Kill it.

### What depth is NOT
- Chat features (users already have 10 chat surfaces)
- Generic productivity UI (calendar views, task lists) — Apple Intelligence will eat
- Horizontal AI features (summarize, draft, translate) — foundation labs win
- Social/sharing features — consumer expansion, not vertical depth
- More sources before deeper sources — adding Notion when Claude/Gmail/WhatsApp aren't deeply modeled is breadth-drift

### Tier sequencing
- **Tier 1 (ships the thesis):** D1 + D2 + D4. Minimum demo.
- **Tier 2 (builds the moat):** D3 + D6. Need corpus to work; Tier-2 by definition.
- **Tier 3 (realizes Weiser):** D5. Requires surfaces.
- **Infrastructure (always-on):** D7. Ingestion + graph maintenance + patch-resistant Graphiti.

---

## 3. The product

### ICP — indie operator
Solo founders, consultants, independent researchers, fund principals at micro-funds. Traits that matter:
- Work and personal are commingled because they *are* their work. Cross-source-personal isn't a privacy concern; it's the actual problem.
- AI is core to their thinking (Claude/ChatGPT are heavy-use tools, not add-ons).
- Naturally have ≥5 sources — partners in WhatsApp, clients in email, contractors in Slack, research in Claude, notes in Apple Notes/Obsidian.
- Real measurable pain — dropped threads cost money or relationships.
- Willingness to pay $30–60/mo (expensable through their LLC).
- Early-tech-adopting; reachable via content, not enterprise sales.

**Why not alternatives:**
- *In-house knowledge workers:* IT-restricted source access; Copilot/Glean encroaching; distribution is enterprise-sales-shaped (MIKAI cannot run).
- *Investors/PMs:* Too few; too consultative; cold-outreach distribution.
- *Heavy AI users in general:* Too broad; no ingestion-permission story.

ICP is dogfood-shaped (you are the user). Risk: dogfood-trap. Mitigation: cohort of 5–10 indie operators outside immediate network providing feedback from week 1.

### Three demos at increasing depth

**Demo A — "What's stalled?" query (pull mode, MCP-in-Claude)**
User asks MIKAI in Claude. MIKAI returns 3 threads with cross-source reconstruction, state classification, pre-drafted next steps. Requires D1 + D2 + D4 + thin D6.
- Surface: MCP-in-Claude (already direction D-039)
- Shippable on existing Graphiti + sidecar + MCP stack
- **Role: the demo that earns attention**

**Demo B — Sunday weekly review (push mode, email or Claude artifact)**
9pm Sunday: structured review of the week's drift. "Threads that moved. Threads that stalled. Decisions logged but not announced. Draft replies for the 3 most urgent."
- Same machinery as Demo A but on a cadence, not a query
- Calm-tech-aligned: comes to user on user's schedule, not the reverse
- Indie operators lack the structural weekly review a manager would otherwise provide — MIKAI provides it
- **Role: the product that earns retention**

**Demo C — Contextual injection (ambient mode, surface-dependent)**
User opens WhatsApp Martin conversation → Raycast/extension/iOS share sheet overlay surfaces thread state. Requires D5 + surface infra.
- Highest demo impact, highest build cost
- 18+ months out
- **Role: the moat that defends against ChatGPT Pulse v2 + Apple Intelligence v2**

### Product staging implications
- Tier 1 isn't the product, it's the demo.
- The product is Tier 1 *delivered on a Tier-2 cadence*.
- The premium tier ($60+/mo) is Tier 3 — just-in-time injection on reachable surfaces.

### Surfaces (in priority order)
1. MCP-in-Claude (Demo A)
2. Email or Claude artifact (Demo B)
3. Raycast (Mac, narrow but defensible)
4. Browser extension (Chrome/Arc/Dia)
5. iOS Shortcuts/widgets (limited but real)
6. Mac companion app (for device-side ingestion)

Explicitly out of scope: iOS lock screen, Apple Intelligence integration. Per stress-test Scenario E, these are platform-owned and not winnable.

---

## 4. Tensions to name explicitly

Surface these so they don't blunder into feature decisions.

- **Pull-vs-push.** MCP-in-Claude is pull; calm tech is push. Default: every pull-mode feature must have a push-mode counterpart on the roadmap, or it's not aligned with the thesis.
- **Cold-start vs. compounding moat.** D7 compounding is the moat but month-1 users get little compounding. Mitigation: D1 cross-source synthesis provides novelty value with zero personalization.
- **Sources-you-have vs. sources-you-control.** Claude, Gmail, Notion: easy. WhatsApp, iMessage: hard. First ship can only span the accessible set. Acceptable because the accessible set includes Claude (most-used by ICP).
- **Personalization vs. demo-ability.** D3 is the deepest moat but invisible to strangers. The demo can't rely on it; the product (Sunday review) can — by week 4, personalization shows up in voice and pattern recognition.
- **Indie-operator vs. dogfood trap.** Building for yourself can converge on bespoke. Mitigation: external cohort of 5–10 indie operators from day 1.

---

## 5. Historical pattern — consumer-utility apps vs. platform bundling

35 years of evidence across cycles. Consumer productivity tools facing platform incumbents (Microsoft, Apple, Google, OpenAI/Anthropic) sort into four outcomes.

### Outcome 1: Killed by bundling
Netscape/Mosaic (IE), RealNetworks (WMP + iTunes), Lotus 1-2-3 / WordPerfect / Borland (Office + Visual Studio), Winamp (iTunes + streaming), Evernote (Notion + OS notes), AOL (free web). The standalone tool was *good enough* but not deeply specialized. The free-and-bundled alternative was an acceptable substitute even when objectively worse.

### Outcome 2: Survived by going enterprise
Dropbox ($2.5B ARR, ~70% business), 1Password ($620M ARR, majority business), Slack ($1.5B ARR → Salesforce $27B), Notion (~$500M ARR), Linear, Calendly. Consumer surface as marketing channel; enterprise contract as revenue.

### Outcome 3: Survived through depth in a specialized vertical
- Adobe Photoshop — professional photography moat + .psd lingua franca + Creative Cloud bundle + brand-as-identity
- Intuit (Quicken/QuickBooks/TurboTax) — tax code complexity + CPA distribution + regulatory moat
- Discord — explicitly for gamers and communities, vertical-segment positioning
- Figma — clearly best-in-class + design-team network effects

Shared profile: professional or sub-cultural segment with real depth requirements; "good enough" actually isn't; network effect (file format, community, collaboration) compounds moat.

### Outcome 4: Survived as content network, not utility
Netflix, Spotify, YouTube. Content network effects, not utility — different category.

### Key 2025-2026 data points
- **Grammarly acquired Superhuman** (mid-2025). Direction matters: Grammarly had enterprise distribution at ~$700M ARR; Superhuman was capped at ~$50M ARR after 11 years and $120M raised. Grammarly absorbed Superhuman to add agent + email capability. *Modal exit for polished consumer-prosumer tools in this cycle.*
- Loom → Atlassian (Oct 2023, $975M)
- Coda → Grammarly (late 2024)
- Granola, Mem, Reflect, Tana, Roam — all PKM/notes prosumer; all capped at niche scale or wound down
- Pattern: consumer-prosumer productivity tools reach $20–80M ARR then get acquired or stall. None have crossed $200M ARR as pure consumer-prosumer subscription.

### The MIKAI implication
MIKAI is consumer-utility facing platform incumbents. It has:
- No content network effect (data is private)
- No professional certification ecosystem
- No shared-file-format network effect
- No regulatory complexity moat

Its proposed moat is *depth-of-personalization-compounding* — a moat type with **zero historical precedent in consumer-utility**. Closest analogs (Photoshop, Quicken) are *professional* tools with shared file formats / tax-code complexity, not personal compounding-corpus tools.

This is the critical assessment to sit with. The compounding-personal-corpus thesis is a *candidate* moat. It may be the first of a new kind. It may not survive contact with platform bundling. Treat as hypothesis, not settled answer.

---

## 6. Where OpenAI/Anthropic sit relative to MIKAI

Foundation labs are not where MIKAI dies — they're where MIKAI gets *price-squeezed and feature-shadowed*.

- **ChatGPT Pulse + Memory + connectors** — weak version of Demo A. Strengthening every quarter. Likely covers ~70% of Demo A by Q4 2026.
- **Claude Projects + Memory + MCP** — Anthropic's analogous track. Less aggressive on ambient, similar trajectory.
- **Operator / Computer Use** — moving toward action, not just memory. In 18 months will likely close stalled threads.

Foundation labs structurally cannot do three things MIKAI's thesis depends on:
1. **Cross-source ingestion across consumer-data silos** (WhatsApp, iMessage, personal Gmail). Wrong shape of company.
2. **Single-user identity-aware personalization that survives across model versions and devices.** They can do session-level memory; cannot do "model of how Brian works since 2026."
3. **Calm-tech delivery surfaces** (briefings, ambient widgets). Their distribution is chat; chat is not calm.

But three differentiators are not enough alone. ChatGPT memory + Gmail/Calendar connectors + a daily review prompt covers 70% of Demo B for $20/mo. MIKAI must be visibly, expensively better than that for $30–60/mo. Bar rises every quarter.

**The real threat is Apple/Microsoft, not the labs.** Mosaic didn't lose to a better browser; it lost to IE bundled with Windows. MIKAI's analog is Apple Intelligence with cross-account connectors (Scenario A) or Microsoft Copilot+ extending past work (Scenario B). These are the bundling-kill scenarios.

---

## 7. Paths forward, ranked by historical viability

**Path 1 — Prosumer subscription + acquired exit (Superhuman pattern). ~45% likely.**
Build the best version of Demo A/B/C for indie operators. Reach $5–30M ARR over 3–5 years. Exit to Anthropic, OpenAI, Notion, Atlassian, or Grammarly. $50M–$500M exit depending on timing. **Modal honest outcome.** No shame in planning for it. Superhuman, Loom, Coda all took this path.

**Path 2 — Vertical specialist + Discord-style segment moat. ~20% likely.**
Treat "indie operator" the way Discord treated "gamer." Don't broaden. Build community + identity + lore around the segment. MIKAI becomes the cultural tool of independent operators, not just a productivity utility. Requires brand-building, not just product-building. Hardest path; highest ceiling without enterprise pivot. Outcome: $50–500M ARR independent business.

**Path 3 — Infrastructure / protocol play (Supabase/Vercel pattern). ~15% likely.**
Open-source cross-source memory layer + state model. Become the standard ambient-agent personal layer others build on. Monetize hosted version. Adjacent to Zep+Graphiti at lower layer. Different company than "MIKAI the consumer product" — different team, different go-to-market. Outcome: $50–500M ARR infrastructure business.

**Path 4 — Independent consumer utility at scale. ~5% likely.**
Reach millions of paying users on consumer pricing. No historical precedent in this category for personal-utility apps. Treat as upside, not plan.

**Path 5 — Enterprise pivot (Dropbox/Notion pattern). ~15% likely if chosen.**
Sell "MIKAI for Teams" — cross-source thread-state awareness for small consultancies, family offices, VC partnerships, design studios. Per-seat pricing. Enterprise sales. *Not* the indie-operator product; abandons the calm-tech consumer thesis. Most historically reliable revenue path. Outcome: $20–200M ARR enterprise business, lower-multiple valuation.

### The strategy that respects all paths
**Plan for Path 1 as baseline.** Build the product as if Path 2 is real (optimizing for Path 1 forecloses Path 2; optimizing for Path 2 keeps Path 1 open). Keep Path 3 optionality by releasing pieces of MIKAI as open standards (the state model vocabulary, the cross-source schema). Avoid Path 5 unless Path 2 visibly fails after 18–24 months — switching too early kills the consumer thesis.

### Concrete implications
1. **Demo A must ship within 6 months.** It's the proof-of-life event that determines whether Paths 1/2/3 are open. Slip past 12 months and ChatGPT Pulse v2 + Operator close the demo window.
2. **The Sunday-review product needs a community angle from day one.** Path 2 requires culture, not just product. Indie-operator newsletter, public weekly-review templates, conference visibility — not nice-to-haves, moat infrastructure.
3. **The protocol play deserves serious thought as you build.** If the state model is good enough to publish as an open vocabulary (the *concepts* — `exploring`, `decided`, `acting`, `stalled-on-self` — not the implementation), that's a strategic asset whether or not the protocol ever ships. Precedent: Markdown (Gruber), JSON (Crockford). Adobe didn't publish .psd until decades in.

---

## 8. Enterprise "where am I with X" architecture — what already exists

The capability MIKAI promises already ships in enterprise as a productized category. Knowing the architecture clarifies what to copy and what to skip.

### Canonical products (2026)
- **Glean** — enterprise search + reasoning across SaaS. ~$100/seat/yr. ~$250M+ ARR. ~150 connectors (Slack, Drive, Jira, Confluence, Salesforce, GitHub).
- **Microsoft Copilot for M365** — same over Microsoft Graph (Outlook, Teams, SharePoint, OneDrive, Loop, Planner). $30/seat/mo on M365.
- **Atlassian Rovo** — agent across Atlassian + ~50 third-party connectors.
- **Salesforce Agentforce** — sales-pipeline agent over Salesforce + connectors.
- **ServiceNow Now Assist** — IT workflow agent over ServiceNow workflow engine.

### The 8-layer enterprise architecture
1. **Source connectors (OAuth + API).** Per-source adapters via REST/GraphQL/webhooks. Each connector: 2–6 engineer-months + ongoing maintenance.
2. **Identity + permission graph.** Maps users → groups → source-level ACLs. Inherits from Okta/Azure AD/Google Workspace via SCIM. *Hardest part* — every query must enforce row-level security across sources.
3. **Indexing + storage (structured + unstructured).** Structured records → relational/columnar. Documents → chunked + embedded + vector-indexed. Both ACL-tagged.
4. **Knowledge graph.** Entities (people, projects, teams, tickets) + relationships. Glean built in-house. Microsoft Graph IS this layer. Atlassian's Teamwork Graph is the equivalent. *The layer that makes "where am I with X" answerable.*
5. **Query / retrieval (ACL-aware RAG).** Intent classification → permission filter → hybrid retrieval (vector + structured + graph) → ranked context.
6. **LLM synthesis + action.** Context + question → LLM → cited synthesis. Increasingly: agentic actions back to sources.
7. **Workflow + event triggers.** Subscribe to source events; trigger state transitions, notifications, agent runs.
8. **Audit + compliance.** Per-query logging, SOC 2 trail, data residency, customer-managed keys.

**Total cost to build properly: $40–80M engineering.** Glean raised $200M+; Microsoft has hundreds of engineers on Graph + Copilot.

### What enterprise products actually deliver today
Ask Glean: *"Where am I with the Q3 launch?"* Get back:
> The Q3 launch tracker (Jira EPIC-4823) is 60% complete, 12 of 20 tickets done. Most recent activity: Sarah Chen moved INFRA-441 to "In Review" 2 hours ago. Launch readiness doc last updated by Mike Park yesterday. Three tickets blocked, all waiting on the security review thread in #sec-review (last message 3 days ago). Slack discussion suggests team is targeting Aug 15 but formal Jira date is Aug 8.

This is functionally MIKAI's Demo A output. The capability exists. It ships. Companies pay $100/seat/yr. IT sets up connectors.

---

## 9. Why no consumer Glean exists

Three structural barriers, all binding, all real.

### Barrier 1: Source API access for personal data (PRIMARY)

| Source | Personal API? | Notes |
|---|---|---|
| Gmail / Calendar / Drive personal | Yes, OAuth | Solid |
| Notion personal | Yes, OAuth | Solid |
| Slack community | Limited | Workspace-scoped |
| Claude / ChatGPT conversations | Export only | Manual upload workflow |
| iMessage | **No API** | EventKit on Mac only; iOS effectively no |
| SMS (iOS) | **No API** | Apple blocks |
| WhatsApp personal | **No API** | Business API exists; personal doesn't |
| Telegram personal | Bot API only | Personal account: no |
| Signal | **No API** | Deliberately |
| Instagram / FB Messenger DMs | **No API** | Meta blocks |
| Apple Notes | iCloud-locked | AppleScript on Mac as workaround |
| Apple Calendar / Reminders / Mail | EventKit on-device only | Mac/iOS app required |
| Substack / personal blogs | RSS | Limited |
| Browser history | OS-specific | No standard |

**Platform-locked sources deliberately don't expose APIs.** Not a coverage gap — a strategy. Apple/Meta know that third-party aggregation of personal messaging would let products compete with the platform's own AI ambitions.

Enterprise doesn't have this problem because enterprise SaaS *wants* to be aggregated (connecting to Glean makes Jira more valuable). Personal messaging is the opposite (Apple makes iMessage more valuable to Apple by NOT publishing the API).

**Net: enterprise has ~150 reliable connectors available. Consumer has ~8–12 that work well + 5–10 via export upload + most high-signal personal sources locked behind platforms that won't open.** Not solvable by paying more — APIs don't exist.

### Barrier 2: Willingness to pay + unit economics

Enterprise: $100–1,200/seat/yr. Consumer: $60–600/yr. 2–20× price gap.

Per-source integration cost is roughly fixed (~$300K to build + ~$30K/yr to maintain a quality connector). At $720/yr ARPU, MIKAI needs **500 paying users per connector** to break even on engineering for that connector. Across 20 connectors: 10K paying users just for engineering breakeven. Glean breaks even at ~30 large enterprise customers.

This is why "indie operators" rather than "everyone" is the right ICP — need 5–10× ARPU to amortize connector costs.

### Barrier 3: Trust + distribution

Enterprise: IT delegates trust via security review, SOC 2, BAA. Adoption mandated. One decision-maker per thousands of seats.

Consumer: every user is their own procurement department. Each user must individually trust a startup with their entire personal information graph. No IT to delegate to.

Compounding: consumer aggregators have well-known platform-risk pattern. Path, Klout, IFTTT-Twitter, Hiya, dozens died when Facebook/Twitter/Instagram cut API access. Every potential customer online >5 years has seen this happen.

### Which barrier is most binding
**Permissions/APIs is the hard ceiling.** No amount of money or trust gets you live iMessage ingestion on iOS. Platform policy, not market failure.

ARPU is the soft ceiling. Solvable by charging $60–120/mo for the right segment.

Trust is the slow gate. Solvable by time + brand + privacy posture.

The single biggest hinder is Barrier 1. Foundation labs partially route around it (OpenAI now ingests Gmail/Calendar/Drive at platform level) — but even they don't get iMessage or WhatsApp personal. Apple Intelligence is the only entity that *can* ingest iMessage cleanly because it's the platform itself. The structural endgame: **only the platform owner can build the deepest version of the consumer L4 product on their own platform.** Mosaic-IE pattern.

---

## 10. MIKAI architecture — what to copy from enterprise, what to skip

Don't copy enterprise architecture. The enterprise stack is shaped by problems MIKAI doesn't have (multi-tenant ACLs, SAML/SCIM, audit/compliance, hundreds of connectors).

### MIKAI consumer architecture

**L1 — Source ingestion, three flavors:**
- *Live OAuth connectors* for sources that allow it: Gmail, Calendar, Drive, Notion, Slack-personal, browser-history-via-extension. ~8–12 sources.
- *Device-side ingestion* via OS APIs: EventKit for Apple Calendar/Reminders, AppleScript/MessageKit on Mac for Notes and iMessage, FileProvider for iCloud-Drive. Requires Mac companion app.
- *Bring-your-own-export uploads* for sources without APIs: WhatsApp chat exports, ChatGPT/Claude data exports, Substack archives. Periodic re-upload; user-driven friction acceptable for highest-signal data.

Realistic coverage: ~60–70% of an indie operator's task-state surface.

**L2 — Skip the permission graph.** Single-tenant per user. No ACL propagation engine. Save 30–50% of enterprise engineering.

**L3 — Storage = Graphiti + Neo4j (already decided per ARCH-019).** Bitemporal knowledge graph IS the enterprise "knowledge graph layer" but better. Glean built theirs in 2020 before Graphiti existed; MIKAI starts with Graphiti for free.

**L4 — State model + thread reconstruction.** *The layer enterprise doesn't have well.* Glean answers "where is the Q3 plan?" but doesn't classify state as `exploring|decided|acting|stalled|drift-to-drop`. **The state model is the MIKAI-specific contribution.** Thin layer over Graphiti queries.

**L5 — Synthesis + action via commodity LLM.** Claude or DeepSeek (already in sidecar). Cite sources. Draft replies.

**L6 — Surfaces:** MCP-in-Claude (Demo A), email/Claude-artifact briefing (Demo B), Raycast/extension/Mac-app (Demo C).

### Skipped enterprise layers
- Audit/compliance/SOC 2 — defer until enterprise pivot
- Multi-tenant infrastructure
- SAML/SCIM identity
- Per-source row-level ACL
- 100+ connector ambition (target 8–12 well)

### Cost comparison
- Enterprise stack: $40–80M engineering
- MIKAI consumer stack: $3–8M engineering

Achievable for a small team if scoped this way.

### Defensible position
MIKAI structurally cannot match Apple Intelligence's coverage of iMessage + Apple Notes on iOS specifically — that's platform-own moat. MIKAI's defensible position is:
- **On Mac:** comparable coverage to Apple Intelligence via device-side EventKit/AppleScript ingestion, PLUS the cross-platform sources Apple won't touch (Claude, ChatGPT, Gmail-not-iCloud, Notion).
- **On iOS:** weaker — can't ingest iMessage live. Relies on Mac-side sync + opt-in exports.
- **Cross-platform:** stronger than Apple/Microsoft because Apple won't cross to MS-stack and MS won't cross to personal.

The product that wins this lane isn't "consumer Glean." It's **the cross-platform memory the platform owners structurally won't build.** Real lane, narrower than enterprise, right architecture reflects narrowness rather than fighting it.

---

## 11. Roadmap implications

Existing `CLAUDE.md` roadmap order: (1) L4 redesign → (2) MCP product surface → (3) ingestion pipeline → (4) eval tooling.

**This order is wrong if the product framing above is accepted.** Correct order: **(3) → (1) → (2) → (4)**.

- Ingestion first: without it, no demo can run.
- One source first (Claude conversations — already accessible, permission baked in, ICP's most-used source), then L4 against that single-source corpus, then add a second source.
- Multi-source ingestion in parallel is a trap: delays demo until everything works.
- MCP comes after L4 has real data to operate on.
- Eval comes after MCP so it can measure the actual product surface.

### What needs to be true to ship Demo A in 6 months
1. Claude-conversations ingestion → Graphiti via `/episode` endpoint, automated.
2. State model L4 over Graphiti — minimum viable vocabulary (`exploring`, `decided`, `acting`, `stalled`).
3. MCP server exposing "what's stalled?" / "where am I with X?" tools, wrapping Graphiti `/search` + L4 state classification.
4. Manual eval on 10–20 known threads from user's own corpus.

### What needs to be true to ship Demo B (Sunday review)
5. Second source ingested (Gmail or Notion).
6. Cron-driven weekly briefing generator producing a Claude artifact (or sending an email).
7. Pre-draft-reply generation for top 3 surfaced threads.
8. Cohort of 5–10 indie operators outside the dogfood circle providing feedback.

---

## 12. Open questions and the next concrete decisions

Settled (within this strategic frame):
- ICP = indie operator
- Product staging = Demo A → Demo B → Demo C
- L3 = Graphiti (per ARCH-019)
- First surface = MCP-in-Claude
- Roadmap order = ingestion → L4 → MCP → eval
- First source to ingest = Claude conversations

Open:
1. **Pressure-test the ICP.** Is "indie operator" right, or is there a sharper sub-segment (solo investors managing portfolio comms, research-heavy consultants with retainer clients, indie fund GPs) that gives MIKAI better economics and tighter distribution?
2. **Concretize Demo A against current graph state.** What threads does MIKAI actually surface for a real user on a Sunday evening with the 6,990-entity graph as it stands? Converts theory to reality-check.
3. **Open-vocabulary state model.** Should the state vocabulary (`exploring|decided|acting|stalled|...`) be published as an open standard early, or held private until traction? Precedent-mixed; strategic option per Path 3.
4. **Community/brand layer for Path 2.** What does the "indie operator newsletter" / "public weekly review template" look like? When does it ship relative to product?
5. **Patch-resistance for Graphiti.** The in-place patch at `node_operations.py:299` is fragile. If `legitimate vertical specialist` is the play, this needs to be upstreamed or forked properly before scaling corpus.

---

## 13. The honest critical assessment

The consumer-utility-app graveyard is real. The compounding-personal-corpus moat has zero historical precedent in this category. The deepest personal sources are platform-locked by design. ARPU economics make connector-heavy architectures structurally hard. Trust takes years to build.

What makes the bet not hopeless:
- Indie-operator segment genuinely underserved + willing to pay.
- Cross-source personal data position structurally hostile to platform aggregation (Apple won't, Microsoft can't reach personal).
- Foundation labs are converging on chat-with-memory; none committed to calm-tech delivery as primary surface. Open lane.
- Graphiti + compounding corpus is a real technical differentiator that takes 2–3 years to replicate from scratch.

What makes the bet hard:
- Pure-consumer-utility independent businesses are historically rare.
- "Indie operators willing to pay $30–60/mo for ambient memory" might be 50K–200K people globally. $20–140M ARR ceiling.
- Apple opening Apple Intelligence to third-party cloud sources at WWDC 2027 (low but real probability) collapses cross-source moat on iOS/Mac.
- ChatGPT memory + connectors will reach ~70% feature coverage by Q4 2026 at $20/mo. MIKAI must be visibly worth premium.

### The legitimate way forward
Plan for Path 1 (prosumer + acquired exit) as baseline. Build as if Path 2 (Discord-style vertical specialist) is real — optimizing for Path 1 forecloses Path 2 but optimizing for Path 2 keeps Path 1 open. Keep Path 3 (protocol play) optionality by publishing pieces of MIKAI as open standards. Defer Path 5 (enterprise pivot) until Path 2 visibly fails after 18–24 months.

This is the same answer historically successful consumer-prosumer companies converge on: optimize for the best independent-product outcome, structure for acquisition optionality, keep one foot in the infrastructure conversation, defer the enterprise decision until the consumer story has been given a real test.

The legitimate way forward exists. It is narrow. The historical analogs that succeeded all required (a) sharp segment focus, (b) cultural/community work beyond product, (c) protocol-level thinking, (d) acceptance that exit-via-acquisition is a respectable outcome.

---

## Appendix A — Research papers to anchor the work

External evidence supporting MIKAI's design choices (cite in product narrative and investor materials):
- TME (Temporal Memory Evaluation) — bitemporal reasoning benchmarks
- ProAgentBench — proactive agent evaluation
- Sensible Agent — opportune-moment intervention timing
- ProAgent — proactive task-completion architectures
- "Sensing What Surveys Miss" — passive personal-data signal value
- GAM (Generative Agent Memory) — long-horizon agent memory architectures
- A-MEM — agentic memory layer (open-source reference)

(Note: confirm citation completeness against current literature before external publication.)

## Appendix B — Settled architectural decisions (reference)

| Decision | What was decided |
|---|---|
| ARCH-019 | Graphiti + Neo4j is the sole L3 backend |
| ARCH-020 | Ingestion targets Graphiti directly via sidecar `/episode` endpoint |
| ARCH-021 | No dual-backend abstraction. Code calls sidecar HTTP API directly |
| ARCH-023 | Hybrid ingestion architecture (Pattern 2 + Pattern 3) |
| D-039 | MCP is the intended product surface direction |
| O-042 | Closed 2026-06-04 in favor of Pattern B (laptop-as-home-server) |

## Appendix C — Surfaces priority (with platform-risk notes)

| Surface | Priority | Platform risk | Notes |
|---|---|---|---|
| MCP-in-Claude | 1 | Low (Anthropic-owned protocol) | Demo A target |
| Email | 2 | None (open protocol) | Demo B option |
| Claude artifact | 2 | Low | Demo B option |
| Raycast (Mac) | 3 | Low (independent company) | Power-user moat |
| Browser extension (Chrome/Arc/Dia) | 4 | Medium (Google could change manifest rules) | Cross-source overlay |
| iOS Shortcuts / Widgets | 5 | Medium (Apple controls) | Limited but real |
| Mac companion app | 5 | Low | For device-side ingestion |
| **iOS lock screen** | **Skip** | **Too high** | Platform-owned |
| **Apple Intelligence integration** | **Skip** | **Too high** | Platform-owned |
