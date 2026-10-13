# Branch manifest — `feat/brain-hands-hermes`

> Every session on this branch reads this manifest first. It names the
> constitution, the goal, the current phase and the branch-scoped do-not list.

## Constitution

- **`docs/VISION.md` §0** — the goal and the three-test filter for decisions.
- **The Oct 11, 2026 market position decision, Option C** — MIKAI competes as
  the task-state and salience layer, not as a general assistant. It ships
  through one narrow surface of its own (to collect act/dismiss labels) and
  exposes the same state over MCP so any executor can read it. Summarised in
  `docs/COMPARISON.md` ("Positioning: MIKAI is the brain, the assistant is the
  hands").

## Branch goal

A dogfood loop for one user (Brian): **MIKAI is the brain, Hermes is the
hands.**

- MIKAI decides what matters and when (thread files in
  `~/.mikai/brain/threads/`, the wiki, the Surface Engine decider).
- Hermes Agent carries the conversation over iMessage and runs scheduled jobs,
  on Brian's Claude subscription via the `claude-subscription-directsdk`
  plugin.
- ntfy push stays as the salience-surfacing channel.
- Every surfaced item and every reply is logged so the dismiss rate can be
  measured (gate: under 30% after 20 surfaced items).

Branched from `feat/pure-file-brain` on 2026-10-13 (inherits `mikai-wiki-v1`).

## Work streams (2026-10-13)

1. Surface Engine reads thread files + wiki instead of Neo4j (`infra/decider/`).
2. Task-state tools in the MCP server (`infra/mikai-mcp/`).
3. Hermes installed and wired to MIKAI (`infra/hermes/`).
4. Dismiss-rate measurement (`eval/`).
5. Trust positioning (`docs/TRUST_POSITIONING.md`).
6. Docs corrected before any pitch (`docs/VISION.md` §2, `docs/COMPARISON.md`).

## Do not (branch-scoped)

- **Do not take credential-based actions.** No booking, buying or signing in to
  the user's accounts with saved passwords. MIKAI reads and surfaces; the user
  or an assistant acts. Any calendar or file write goes through the D-055
  approval loop.
- **Do not add paid API keys.** Inference runs on Brian's Claude subscription
  (`claude -p`, the Hermes subscription plugin) or local models. Note:
  `.env.local` currently contains an `ANTHROPIC_API_KEY`; nothing on this
  branch should start depending on it.
- **Do not write to the production vault** (`~/.mikai/wiki/`). Read-only is
  fine; writes go to `~/.mikai/wiki-mikai-parallel-test/` or `~/.mikai/brain/`.
- **Do not land a mechanism without a CHANGE_LEDGER entry.** Draft the entry,
  get it approved, then land the mechanism.
- **Do not make trust claims outside the "true today" column** of
  `docs/TRUST_POSITIONING.md`.
- **Do not message anyone but Brian.** Hermes's iMessage gateway must be
  restricted to Brian's own number; no sends to contacts.
- **Do not sell or describe MIKAI as "powered by your Claude subscription"**
  through a third-party harness — Anthropic does not permit routing users'
  plan credentials. The product route for other users is MCP inside their own
  Claude app.

## Related docs

- `docs/VISION.md` §0, §2
- `docs/COMPARISON.md`
- `docs/TRUST_POSITIONING.md`
- `docs/DECISIONS.md` — D-053, D-054, D-055
- `docs/CHANGE_LEDGER.md`
