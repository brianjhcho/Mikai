# Onboarding plan — how a new person connects MIKAI

*Draft · 2026-10-24 · Not built. Approve the decisions at the bottom before any code.*

> **Status 2026-10-27:** a script-based onboarding path is built: `infra/onboarding/mikai-setup` (and `mikai-uninstall`), user steps in `docs/ONBOARDING_GUIDE.md`. It sets up the full Hermes + MIKAI stack on a tester's own Mac (their Claude subscription via the official CLI plugin, their own Photon iMessage line, MIKAI's Chrome, Full Disk Access for calendar and messages, optional Apple Notes import via a read-only AppleScript export). It is a terminal script, not the packaged Mac app this plan describes; the Mac app, the remote Claude connector and per-user cloud hosting are still unbuilt.

## The goal

A new user should get from "I heard about MIKAI" to "MIKAI texted me something
useful" in under 10 minutes, without seeing an API key, a terminal, or a
config file. Three things need connecting: **their Claude**, **their Apple
Calendar**, and **their Apple Notes**. Each has a different hard constraint.

## The three connections

| Connection | How it works | Constraint that shapes it |
|---|---|---|
| **Claude** | The user adds MIKAI as a **custom connector** inside their own Claude app (Settings → Connectors → "Add custom connector", paste MIKAI's URL, sign in). Claude then calls MIKAI's tools in their conversations. | Anthropic does not let a third party run a user's Claude subscription on their behalf. A connector inside the user's own Claude is the legitimate route, and their own plan pays for the inference. Available on Pro, Max, Team and Enterprise. |
| **Apple Calendar** | The MIKAI Mac app asks for **calendar permission** (the standard macOS prompt) and reads events locally through Apple's EventKit framework. | Preferred over iCloud CalDAV, which needs an app-specific password — that would mean MIKAI holds a password, which the trust doc says we should stop doing. |
| **Apple Notes** | The MIKAI Mac app reads notes **on the user's Mac** and sends new or changed notes to MIKAI. | Apple Notes has **no cloud API**. Notes can only be read on a Mac signed into the user's account. There is no web-only way to do this. |

### The Claude connector needs rebuilding

MIKAI already has a remote connector from Stage 5 (OAuth, verified on
2026-05-19), but:

- it is **down** — the claude.ai MIKAI connector returns a 502 from its
  Cloudflare endpoint, and
- it was built around the **deprecated Neo4j graph**, not the wiki or thread
  files.

What's needed: the `mikai-wiki-v1` MCP server (task-state and wiki tools,
already working locally) served over HTTPS with OAuth, one isolated data space
per user. Claude supports both authless and OAuth remote servers, including
dynamic client registration. This lives on the cloud server
(`docs/CLOUD_DEPLOYMENT_PLAN.md`).

## What the user sees

1. **Download the MIKAI Mac app** from the website and open it.
2. **Allow Calendar** when macOS asks.
3. **Allow Notes access.** (The exact mechanism — Automation permission for
   Notes vs. reading Notes' local store with Full Disk Access — is an open
   technical question; see below.)
4. **Add MIKAI to Claude.** The app shows a button that opens Claude's
   connector page with MIKAI's URL ready to paste, then the user signs in.
5. **Text MIKAI.** The app shows the user's MIKAI iMessage number; they save
   it and text "hi" once (required before MIKAI can message first).
6. **First value.** Within a day, MIKAI sends one useful item — a stalled
   thread with a next step — and the user can reply *done / snooze / not
   relevant*.

## What we build

| Piece | What it is | Notes |
|---|---|---|
| **MIKAI Mac app** | A small menu-bar app (Swift) that holds the permissions, reads Calendar and Notes locally, and uploads changes to the user's MIKAI space. | Needs an **Apple Developer Program** membership (US $99/year) so it can be signed and notarized; without it macOS warns users the app is unsafe. |
| **Remote MCP connector** | `mikai-wiki-v1` over HTTPS + OAuth, per-user. | Replaces the broken Stage 5 connector. |
| **Per-user iMessage line** | Each user needs an iMessage number to talk to. | See next section — this is a cost decision. |
| **Ingestion per user** | Notes and calendar events become sources in the user's own wiki; thread detection runs per user. | Thread detection from the wiki isn't automatic yet (only Brian's 7 hand-written threads exist). This is the product's real bottleneck for anyone but Brian. |

## Per-user iMessage lines

| Option | Cost | Trade-off |
|---|---|---|
| **Photon free tier** (what Brian uses now) | Free | Shared line pool; can't message a user first until they've texted the line; reliability so far: the stream drops every 20–30 min and reconnects. Fine for a few testers. |
| **Sendblue** | From about US $100/month per dedicated line (AI-agent plan, inbound-first); full outbound is enterprise pricing | Dedicated number per user is expensive at scale. |
| **Linq** | About US $250/line/month plus setup fees; sales call required | Used by OpenInstinct. |
| **No iMessage for testers** | Free | Testers use MIKAI only through their Claude connector plus ntfy pushes. |

For the first 3–5 testers, Photon's free tier (or connector-only) is enough.
A paid line per user only makes sense once the dismiss rate shows the
messages are worth it.

## Privacy and consent

- **Ask for each permission separately**, with one sentence on why (Calendar:
  "to see what you've committed to"; Notes: "to see what you've been thinking
  about").
- **Show what was read.** The Mac app lists what it synced and lets the user
  exclude folders or calendars.
- **Delete must mean delete** before anyone else's data is stored. Today it
  doesn't (see `docs/TRUST_POSITIONING.md`): archives, caches and logs keep
  copies. Building a real `forget` is a prerequisite for Phase 2 users.
- **Be honest about third parties**: their notes reach Anthropic (via their
  own Claude for connector use, or MIKAI's model provider for background
  work), and iMessage text passes through the iMessage provider's servers.

## Build order

1. **Remote connector for Brian** — `mikai-wiki-v1` over HTTPS + OAuth on the
   cloud server; Brian adds it to his own Claude. Proves the connector path.
2. **Mac app, Calendar only** — permission prompt, local read, upload. Easiest
   permission, fastest proof.
3. **Mac app, Notes** — settle the access method (open question 2), then sync.
4. **Forget / delete** — required before any second user.
5. **First 3–5 testers** — connector + Mac app + Photon free tier.
6. **Automatic thread detection** — so testers get threads without writing
   them by hand.

## Open decisions (Brian)

1. **Who are the first testers, and do they all have Macs?** Notes and
   Calendar reading require a Mac. iPhone-only users would get connector-only
   MIKAI.
2. **Notes access method.** Automation permission (asks once, reads through
   the Notes app, slower) vs. Full Disk Access (reads Notes' local database
   directly, faster, but a scarier permission and an undocumented format that
   can break on macOS updates). Recommendation: Automation first.
3. **iMessage for testers:** Photon free tier, connector-only, or pay for
   lines.
4. **Apple Developer account:** sign up now ($99/year) so the Mac app can be
   notarized.

## Sources

- [Claude: get started with custom connectors using remote MCP](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
- [Claude docs: add a connector that isn't in the directory](https://claude.com/docs/connectors/custom/remote-mcp)
- [Anthropic: building custom connectors via remote MCP servers](https://support.anthropic.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers)
- [Sendblue vs Linq comparison](https://www.sendblue.com/compare/sendblue-vs-linq)
- [iMessage API pricing comparison 2026](https://tuco.ai/blog/imessage-api-pricing-comparison-2026)
- Photon plugin README: `~/.hermes/hermes-agent/plugins/platforms/photon/README.md`
