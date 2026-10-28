# Actions and purchases — making MIKAI act, safely

*Draft · 2026-10-24 · Not built beyond the current default (Level A). Each level above A needs Brian's approval and a CHANGE_LEDGER entry first.*

## The tension

Brian wants MIKAI to work like Instinct: skills, actions and purchases. The
trust positioning (`docs/TRUST_POSITIONING.md`) currently says "MIKAI never
books or buys", and acting on people's accounts is exactly where Instinct got
burned (data kept after disconnect, prompt injection followed, unsolicited
shopping, a silent outage mid-task). The plan below adds capability in levels,
so each step can be judged on its own and the trust story survives.

## The levels

| Level | What MIKAI does | Money moves? | Risk | Status |
|---|---|---|---|---|
| **0. Skills, no money** | Research, drafts, reminders, calendar events (via the D-055 approve-tap), web browsing, summaries | No | Low | Hermes has a skills system and browser tools; the browser toolset was skipped at install and needs enabling |
| **A. Ready-to-buy** | Finds the item, texts Brian a checkout link with price and store; Brian pays himself | Brian pays | Very low | **Default** |
| **B. Dedicated virtual card** | Pays with a separate card that has a hard limit, only after Brian replies "yes" to a message showing item, price and store | Yes, capped | Medium | Not built |
| **C. Stored logins** | Signs into Brian's Amazon, airline and other accounts with saved passwords, like Instinct | Yes | High | **Not recommended** |

### Why not Level C

- Holding passwords contradicts the trust positioning and is Instinct's main
  liability.
- Amazon actively blocks AI shopping agents (it blocked Meta's Muse in
  September 2026), and other merchants can do the same at any time.
- Prompt injection: an email can plant instructions; with stored logins the
  damage is real purchases or account changes.

### Level B in Canada

Brian is in BC. Privacy.com — the best-known per-merchant virtual-card service —
is US-only. Canadian options found (October 2026):

| Service | Virtual card | Limits | Merchant locking |
|---|---|---|---|
| **KOHO** | Yes | $4,000 per transaction max (Core); load limits | Not stated by the provider |
| **Wise** | Yes | Configurable spending limits; $17,500/day online max | Not stated by the provider |
| **Neo** | Yes | High limits | Not stated |
| **Your bank's virtual card** | Some banks | Bank-set | Rare |

None clearly offers Privacy.com-style per-merchant locking in Canada. Practical
Level B in Canada: a **separate prepaid or low-limit card** (e.g. a KOHO or
Wise card loaded with only what MIKAI may spend this month), with MIKAI's own
caps and allowlist enforced in software. Verify each provider's current
features before choosing.

## Guardrails required for Level B (and anything above Level 0)

| Guardrail | What it means |
|---|---|
| **Confirmation every time** | No money moves without Brian replying "yes" to a message that names the item, price, store and card. No standing approvals. |
| **Caps** | Per purchase, per day and per month, enforced in MIKAI's code, plus the card's own limit as a backstop. |
| **Merchant allowlist** | MIKAI may only pay merchants Brian has approved in advance. |
| **Audit log** | Every proposed and completed action logged (what, why, which evidence, who approved, result), alongside the notification log. |
| **Prompt-injection defence** | Content from emails, messages and web pages is treated as untrusted data, never as instructions. A purchase can't be triggered by text found in a source — only by Brian's own message. Re-run the TechCrunch-style test (a planted instruction in an email) before Level B goes live. |
| **Kill switch** | One message ("stop") or one command disables all actions instantly; the card can also be frozen in its app. |
| **No silent failures** | If an action fails or is half-done, Brian is told immediately. |

## Build order

1. **Level 0:** enable a curated skill set in Hermes (web search, browser,
   reminders, calendar via the approve-tap), and trim the rest — this also
   cuts the ~62K-token cost per turn.
2. **Level A:** a "find and link" skill that returns checkout links with price
   and store.
3. **Guardrails:** audit log, injection handling, kill switch — built before
   any card exists.
4. **Level B:** choose and load a card, add caps and allowlist, run the
   injection test, then a first capped purchase with Brian watching.
5. **Update the trust doc**: "MIKAI never buys" becomes "MIKAI buys only what
   you approve, one message at a time, from a capped card."

## Open decisions (Brian)

1. **Go beyond Level A?** If yes, which card (KOHO, Wise, or a bank virtual
   card) and what monthly limit.
2. **Which skills first** for Level 0 (e.g. research, reminders, calendar,
   restaurant/travel lookup).
3. **Merchant allowlist** to start with.

## Sources

- [Virtual cards in Canada: 2026 provider index](https://revault.ca/virtual-cards-canada)
- [Best virtual credit cards in Canada 2026](https://www.savvynewcanadians.com/best-virtual-credit-cards-canada/)
- [KOHO: best virtual card provider in Canada](https://www.koho.ca/learn/best-virtual-card-provider-in-canada/)
- [Privacy.com alternatives (Privacy.com is US-only)](https://ramp.com/blog/privacy-dot-com-alternatives)
- Instinct failures and Amazon blocking: see `docs/COMPARISON.md` and `docs/TRUST_POSITIONING.md`
