# Cloud deployment plan

*Draft · 2026-10-24 · Not built. Approve the decisions at the bottom before provisioning anything.*

## Why move to a server

Today everything runs on Brian's MacBook Air. That causes three problems:

1. **MIKAI goes quiet when the Mac sleeps.** Hermes's iMessage listener and the
   Surface Engine only run while the Mac is awake. The Photon connection
   already drops every 20–30 minutes.
2. **Failures go unnoticed.** The Surface Engine failed on 2026-08-07 and
   nobody noticed for two months.
3. **Other people can't use it.** Nothing is reachable from outside the Mac.

## What moves and what stays

| Moves to the server | Stays on the user's Mac |
|---|---|
| Hermes gateway (the iMessage listener) | Reading **Apple Notes** — Apple offers no cloud API |
| Surface Engine schedules (7:00, 12:00, 18:00) | Reading **Apple Calendar** (via EventKit permission) |
| Remote MCP server with OAuth (the Claude connector) | Reading **iMessage history** (the Surface Engine's live-context adapter) |
| Each user's wiki and thread files | The MIKAI Mac app that does the reading and uploads changes |
| Notification and reply logs | |
| Backups and health alerts | |

The Mac app is the bridge: it reads locally and pushes changes up. Everything
that decides and messages runs in the cloud.

## The inference-cost decision

This is the business-model question the move forces.

| Who | How the model is paid for | Allowed? |
|---|---|---|
| **Brian, on his own server** | Brian's own Claude subscription through the official Claude CLI (as `claude -p` and the Hermes subscription plugin work today) | Yes — the official client on your own machine, for your own use. Every call draws on the same quota as his chat and Claude Code use, so background volume must stay low. |
| **Other users, via their Claude connector** | Their own Claude plan pays when they use MIKAI inside Claude | Yes — this is the legitimate product route. |
| **Other users, background work** (Surface Engine decisions, Hermes conversations) | MIKAI pays per use via an API key (priced into a subscription), or each user brings their own key | Yes, but it costs money. |
| **Other users' subscriptions run by MIKAI's server** | — | **No.** Anthropic does not permit third parties to route requests through users' Free/Pro/Max credentials. |

Note the branch do-not rule: no paid API keys. Phase 1 respects it. Phase 2
cannot, unless testers bring their own keys or use MIKAI connector-only.

## Phases

### Phase 1 — Brian only (about 1–2 days of work)

- One small server running Hermes gateway, the Surface Engine and the MCP
  server.
- Claude CLI on the server, logged into Brian's account.
- Brian's Mac pushes wiki, thread and context changes up (initially a sync
  script; later the Mac app).
- Daily encrypted backups of all MIKAI data.
- A health check that alerts Brian (ntfy or iMessage) when a scheduled run
  fails or doesn't happen.
- Secrets in a file readable only by the service account (never in git).

### Phase 2 — 3–5 testers

- **Isolation:** a separate data directory and process (or container) per user.
- **Sign-in:** OAuth for the Claude connector; a simple account for the Mac app.
- **Encryption at rest** for each user's data.
- **Delete means delete:** a `forget` command that removes a source and every
  derived copy (pages, archives, caches, logs). Prerequisite for storing anyone
  else's data.
- **Model billing:** API key with per-user usage caps, or bring-your-own-key.
- **iMessage lines:** Photon free tier for testers (see `docs/ONBOARDING_PLAN.md`).

### Phase 3 — public

- Mac app distribution (signed, notarized), pricing, privacy policy and terms,
  support, monitoring and incident process, data-residency choice.

## Provider options (prices checked October 2026, approximate)

| Option | What you get | Rough monthly cost | Fit |
|---|---|---|---|
| **Hetzner Cloud** (shared vCPU, e.g. CX23) | Plain Linux VM, 2 vCPU / 4 GB | About €4–5 before VAT and IPv4; Hetzner raised prices twice in 2026 | Cheapest, most control; you manage everything. EU/US regions. |
| **Fly.io** | Small always-on machines | About $6.70 for 1 GB RAM, $13.39 for 2 GB (RAM price rose to $6/GB on 2026-10-01) | Easy deploys, per-user machines are natural for Phase 2. |
| **Railway** | Managed app hosting | Hobby $5/month including $5 of usage | Simplest; less control over long-running processes and storage. |
| **Mac mini at home** (existing Pattern B, D-051) | Brian's own hardware | Hardware + electricity | Can also read iMessage/Notes directly, but not a path to other users. |

Recommendation for Phase 1: a 2–4 GB Linux VM (Hetzner or Fly). Hermes, the
Surface Engine and the MCP server are light; the Claude CLI and Node/Python
fit comfortably. Revisit for Phase 2 when per-user isolation matters.

## Risks

| Risk | Mitigation |
|---|---|
| Brian's quota drained by background calls on the server | Keep the Surface Engine at 3 runs/day; trim Hermes (about 62K tokens per turn today) before it's always-on. |
| Trust claim "stored only on your disk" stops being true | Update `docs/TRUST_POSITIONING.md`; the replacement claim ("your own encrypted space, delete means delete") must be built before it's said. |
| Anthropic policy changes again | Connector route is insulated (user's plan pays); keep a cheaper-model fallback for background jobs. |
| Single server failure | Daily backups, health alerts, documented restore. |
| Photon line reliability | Monitor reconnects; fall back to ntfy push for urgent items. |
| Server compromise exposes personal data | Minimal open ports, SSH keys only, automatic security updates, encrypted backups, per-user isolation from Phase 2. |

## Open decisions (Brian)

1. **Phase 1 provider:** Hetzner (cheapest) or Fly.io (easier, scales to
   per-user machines).
2. **Model billing for testers:** MIKAI pays via API (and sets a price),
   bring-your-own-key, or connector-only testers with no background jobs.
3. **Does iMessage-history reading stay?** On the server it can't read iMessage;
   either the Mac app uploads iMessage context or the Surface Engine drops that
   signal.
4. **Data region:** where user data lives (Canada, US or EU) once testers join.

## Sources

- [Hetzner CX22/CX23 pricing 2026](https://vpsfor.dev/posts/hetzner-cx22-pricing-2026/)
- [Fly.io pricing: what changed on 1 October 2026](https://dev.to/pavel-hostim/flyio-pricing-2026-what-changed-on-1-october-and-what-it-costs-in-europe-1pjl)
- [Railway pricing plans](https://docs.railway.com/pricing/plans)
- [Claude custom connectors (remote MCP)](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
- Anthropic subscription policy: see `docs/COMPARISON.md` and `docs/branches/feat-brain-hands-hermes.md`
