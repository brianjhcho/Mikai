# MIKAI — User Needs Registry

> **What this file is:** Brian-curated list of high-priority life needs MIKAI should track. **FIGS reads this file at every tick and treats every item here as a candidate for surfacing.** This is the highest-priority lens — it outranks the nightly Dream-generated `wiki.md` because Brian explicitly authored these.
>
> **Why this exists, not in `wiki.md`:** The Dream wiki reflects what's *in your recent conversations*. Many of Brian's load-bearing life needs don't show up in Claude.ai conversations at all (mom's Scotia card, MSP residency) — or they show up sparsely and get crowded out by product-build noise. This registry is the override.
>
> **How to maintain:** Edit by hand. Add a need when one becomes load-bearing. Mark `state: done` when closed (FIGS will stop surfacing). Don't delete done items for at least 30 days — they're useful for FIGS to learn "Brian acts on financial-admin needs within N days" patterns.

**Schema per item** (each `## N. Title` section below contains one `yaml` fenced block following this schema):

```
slug: short-id            # used by FIGS as the citation key
title: human-readable
state: in_flight | on_hold | blocked | exploring | decided | done
urgency: critical | high | medium | low
domain: financial | health | relationship | career | trading | other
last_movement: ISO date   # last time Brian made progress
next_step: one concrete sentence — "open the Scotia app and submit X form"
connects_to: list of external infrastructure (Scotia app, ServiceBC portal, IBKR API, etc.)
blockers: free text
notes: free text
```

The schema block above is illustrative only; the parser ignores it because it isn't fenced as `yaml`. The actual items follow.

---

## 1. Buy a proposal ring stone + book proposal vacation spot

```yaml
slug: proposal-ring-and-venue
title: Buy proposal ring stone + book vacation venue
state: in_flight
urgency: high
domain: relationship
last_movement: 2026-06-22
next_step: Decide stone shape and budget; ping Whiteflash or Brilliant Earth for one quote in that range. Separately, pick Atacama vs Ladakh and check flight calendars + lodging availability for the target window.
connects_to:
  - Whiteflash, Brilliant Earth, James Allen (online stone shops)
  - Skyscanner, Google Flights (vacation flights)
  - Airbnb, Booking.com (vacation lodging)
  - Calendar.app (block the trip window once chosen)
blockers: |
  Two-decision tangle — stone budget anchors the trip budget, but the trip
  window anchors how soon the stone needs to arrive. Picking the venue first
  (Atacama vs Ladakh) breaks the cycle because the trip window is the harder
  schedule constraint.
notes: |
  Earlier Denver/Red Rocks discussion is stale (Jun 22 thread). Atacama and
  Ladakh are now the leading candidates per the wiki ## Who section.
  Surface this every 3-4 days until either (a) the stone is ordered, or
  (b) the venue is booked, whichever comes first.
---
```

## 2. Get mom a Scotia credit card

```yaml
slug: mom-scotia-credit-card
title: Get mom a Scotia credit card (currently paused)
state: on_hold
urgency: medium
domain: financial
last_movement: 2026-05  # approximate — paused for reasons not in graph yet
next_step: Decide whether to resume now or wait for a specific trigger (e.g., a credit-balance threshold, a planned big purchase). If resuming, log into Scotia online banking and complete the joint-applicant flow.
connects_to:
  - Scotia online banking (initial application + ongoing servicing)
  - Mom's mailing address verification (likely a separate step)
blockers: |
  Unknown — Brian needs to surface the reason for the hold to himself.
  FIGS should ask him "is this still on hold for the same reason?" rather
  than nag for action.
notes: |
  This is an on_hold item, not a blocked one — the difference is that
  Brian chose to pause it. FIGS should remind less frequently (every
  ~10 days) and frame as "still on hold?" not "you should do this."
---
```

## 3. Reactivate MSP (BC Medical Services Plan)

```yaml
slug: msp-reactivation-bc
title: Reactivate MSP — need to prove BC residence
state: blocked
urgency: high
domain: health
last_movement: 2026-04  # approximate
next_step: Gather two BC residency proofs (BC driver's licence + utility bill OR lease + bank statement with BC address). Then submit via Health Insurance BC online portal or by mail.
connects_to:
  - Health Insurance BC online portal (msp.gov.bc.ca)
  - ICBC for BC driver's licence (if needed as proof)
  - Personal records — lease/utility bills/bank statements
blockers: |
  Don't have two BC-address documents handy. Brian needs to physically
  locate or request: (1) something dated within last 90 days showing
  current BC address, (2) a government-issued ID with BC address.
notes: |
  Health coverage gap is a hard time-sensitive risk — if Brian needs
  medical care while uncovered, the cost spikes. FIGS should escalate
  the urgency if more than 7 days pass without movement.
---
```

## 4. Find a job OR start a startup in AI

```yaml
slug: ai-career-move
title: Land an AI job OR start an AI-adjacent venture
state: exploring
urgency: high
domain: career
last_movement: 2026-06  # ongoing — MIKAI build is implicitly the startup track
next_step: Spend 90 minutes this week on the explicit "is MIKAI the startup?" decision. If no, write a one-page "what kind of AI role" memo and target 3 specific companies. If yes, write the one-page MIKAI pitch + name the 3 funding paths (bootstrap, angel, accelerator).
connects_to:
  - LinkedIn job search (filter: AI infra, AI product)
  - YC and other accelerator deadlines
  - Brian's existing network (no infrastructure to build — just outreach)
  - MIKAI's own product surface (this build IS the startup track if Brian chooses)
blockers: |
  This need straddles two life paths (employee vs founder) that have
  incompatible week-to-week routines. Until Brian explicitly picks one
  for the next 90 days, FIGS will surface this as an open-question
  prompt rather than an action prompt.
notes: |
  Open-question framing for FIGS: "career thread is unbranched — pick a
  90-day lane this week?" NOT "apply to N jobs today."
---
```

## 5. Automate trading account (or trade suggestions)

```yaml
slug: automate-trading
title: Automate trading account OR at least automate trade suggestions
state: exploring
urgency: medium
domain: trading
last_movement: 2026-05
next_step: Pick a depth — full execution (IBKR API or Alpaca) or suggestion-only (a daily candidate list pushed to FIGS itself). Suggestion-only is the smaller step. If suggestion-only, define one strategy class (e.g., earnings-drift, sector momentum) and the data source (e.g., Yahoo Finance, Polygon).
connects_to:
  - IBKR (Interactive Brokers) — primary trading account API
  - Alpaca — simpler API for paper/live automation
  - TradingView or QuantConnect (strategy backtesting)
  - Polygon / Yahoo Finance / IEX Cloud (price data)
blockers: |
  Strategy undefined. Automation is a means; without a defined strategy
  there's nothing to automate. FIGS should surface this as "define one
  strategy class before any infra work" not "set up the API."
notes: |
  The "suggestion-only" version is the small, MIKAI-compatible variant:
  one daily FIGS notification listing N candidate trades with reasoning,
  no execution. This composes cleanly with the existing notification
  surface. Full automation is V2.
---
```

---

## How FIGS uses this file

1. At every tick, the `needs_lens.py` parser reads this file and produces structured candidates with the per-item scoring fields.
2. These needs go into the FIGS prompt as the **highest-priority section** — above the Dream wiki — because Brian explicitly curated them.
3. FIGS applies the same `surface_priority = state_weight × urgency × delivery_value × delivery_cost⁻¹` formula (see `FIGS_LOSS_FUNCTION.md`).
4. Recently-surfaced needs are deprioritized via the SQLite log (e.g., if MSP was surfaced 2 days ago and Brian dismissed, don't repeat for 7 days; if he acted, mark `last_movement` forward and lower priority for 14 days).

---

## Status conventions

- `in_flight` — actively being worked on; surface if no recent movement
- `on_hold` — deliberately paused; surface as "still on hold?" check-ins, not action prompts
- `blocked` — wants to move but missing inputs; surface the specific blocker
- `exploring` — pre-decision; surface as open-question prompts, not action prompts
- `decided` — committed, awaiting execution; surface to drive scheduling
- `done` — closed; keep for 30 days as a learning signal, then archive

## Urgency conventions

- `critical` — material risk (financial, health, legal) if not addressed within days
- `high` — material risk within weeks
- `medium` — material if it slips a quarter
- `low` — Brian thinks about this; surface monthly at most

---

## Adding a new need

1. Append a new `## N. <Title>` section at the bottom of this file
2. Fill all fields in the YAML block
3. The next FIGS tick picks it up automatically — no code changes needed
