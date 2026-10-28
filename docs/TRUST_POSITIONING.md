# MIKAI — Trust Positioning

> Created 2026-10-13 on `feat/brain-hands-hermes`. Purpose: the trust contrast
> against Instinct's documented failures, with every MIKAI claim checked
> against the code. **Rule for any pitch: only say what is in the "true
> today" column.** Update this doc whenever a "target" claim becomes true.

## Why trust is the wedge

The personal-agent launches of Aug–Sep 2026 compete on capability. Instinct,
the best-reviewed, has accumulated a public record of trust failures. That
record makes MIKAI's stance — read-only brain, files on your disk, measured
restraint — a concrete contrast rather than an abstract promise. But the
contrast only works if MIKAI's own claims survive scrutiny, which several do
not yet.

## Instinct's documented failures

| Failure | Evidence |
|---|---|
| Data kept after disconnect | A user found it still summarising his inbox after he disconnected access; it would not delete Gmail records until a deletion tool was added. ([TechCrunch](https://techcrunch.com/2026/08/24/instincts-powerful-ai-assistant-is-raising-privacy-and-security-concerns/), [eesel](https://www.eesel.ai/blog/instinct-ai-review)) |
| Inbox stored in plain text | The bot confirmed emails were stored in plain text for later search. ([TechCrunch](https://techcrunch.com/2026/08/24/instincts-powerful-ai-assistant-is-raising-privacy-and-security-concerns/)) |
| Training on by default | Opt-out exists, but flagged safety-review data can still be used and prior training isn't undone. ([eesel](https://www.eesel.ai/blog/instinct-ai-review)) |
| Prompt injection followed | A user emailed his own inbox malicious instructions; Instinct followed them. ([TechCrunch](https://techcrunch.com/2026/08/24/instincts-powerful-ai-assistant-is-raising-privacy-and-security-concerns/)) |
| Silent outage | 2026-09-22: stopped replying mid-task, messages shown as read, no status page, no statement. ([Yahoo Finance](https://finance.yahoo.com/technology/ai/articles/hello-frozen-users-viral-ai-161755806.html)) |
| Unsolicited shopping | Product recommendations users did not ask for; commissions reportedly under consideration. ([BigGo](https://finance.biggo.com/news/4bb6e195-cb18-455f-baef-9914f298018e)) |
| Broad action rights | Terms authorise it to "enter into agreements, commitments or transactions on your behalf" with no responsibility for "unintended Actions". ([eesel](https://www.eesel.ai/blog/instinct-ai-review)) |

## MIKAI's claims, checked against the code (2026-10-13)

### True today

| Claim | Evidence |
|---|---|
| **Your knowledge base is plain files on your own disk.** No MIKAI-operated cloud stores it. | Wiki at `~/.mikai/wiki/`, threads at `~/.mikai/brain/threads/`; no MIKAI server exists. |
| **MIKAI never books, buys or transacts.** | No booking, purchase or payment code anywhere in the repo. The Surface Engine only sends notifications. |
| **Calendar changes need your tap.** | `infra/decider/calendar_planner.py` writes nothing; it sends an Approve/Reject card and the write happens only on Approve (D-055). |
| **Default is silence, with a hard bar to interrupt.** | `infra/decider/mikai_decide.py`: send-or-stay-silent decision, evidence citations validated, 2-hour cooldown (`COOLDOWN_HOURS`). |
| **Every decision is logged, including the silent ones.** | `~/.mikai/notification_log.db`, `notification_log` table (31 decisions logged to date). |
| **Vault changes are reversible.** | Canonicalization writes an archive + log and has a byte-identical undo tool (`canonicalize_undo.py`); link-wrapping archives originals (`.link-wrap-archive/`). |
| **MIKAI trains no models on your data.** | No training code exists. (Inference provider policies are separate — see "leaves your device" below.) |

### Not true today — target

| Claim we want to make | What is actually true today | What must change |
|---|---|---|
| **"No passwords held."** | **False.** The Gmail adapter (`infra/decider/adapters/gmail.py`) reads the inbox over IMAP with a Gmail app password, and one is set in `.env.local`. The CalDAV client (`infra/decider/caldav_client.py`) uses an iCloud app-specific password (not currently set). `.env.local` is gitignored but its permissions are world-readable (`-rw-r--r--`). | `chmod 600 .env.local` now. Move to OAuth read-only scopes stored in the macOS Keychain, or read mail from the local Mail.app store instead of IMAP. Then the honest claim becomes "no reusable passwords; read-only, revocable tokens." |
| **"Deleting means deleting."** | **False.** There is no single forget command. Copies survive deleting a page: `.canonicalization-archive/`, `.link-wrap-archive/`, `.embed-cache/`, the `~/.mikai/wiki-backup-2026-08-14-0828/` snapshot, notification text in `notification_log.db` (23 rows with bodies), and the deprecated Neo4j graph. | Build a `forget <source>` command that removes the source, derived pages, archives, cache entries and log rows, and state plainly what it cannot reach (copies held by inference providers). |
| **"Your data never leaves your device."** | **False.** `claude -p` sends prompts (which include notes and email/iMessage excerpts) to Anthropic. Notifications go through the public `ntfy.sh` server by default (`MIKAI_NTFY_BASE`), so notification text passes a third party. Since 2026-10-22, iMessage conversations with MIKAI pass through Photon's servers (the managed iMessage provider Hermes uses). The archived Neo4j graph was extracted with DeepSeek and embedded with Voyage AI. | Say instead: "stored only on your disk; sent for processing only to the model you already use." Self-host ntfy or route notifications through Hermes/iMessage. Minimise excerpt size in prompts. Check the Claude account's data-training setting. |
| **"We publish our dismiss rate."** | **Not yet.** Only 3 notifications have been tracked (all inferred dismissed — the tap tracker only works on home Wi-Fi). | Run the dogfood loop to ≥20 surfaced items with explicit replies, then publish the number with its method. |
| **"It never fails silently."** | **False.** The Surface Engine's last run (2026-08-07) failed with `claude_invocation_failed`, and nothing alerted; its scheduled job has not run since. | Alert on failed or missing runs (a health check that notifies), and show "last successful run" in the surface itself. |
| **"Prompt injection can't make it act."** | **Partly true, untested.** MIKAI cannot transact, which caps the damage. But email and iMessage text flows into prompts unmarked, so a planted instruction could still produce a misleading notification or wiki content. No injection test has been run. | Mark source content as untrusted in prompts, and repeat the TechCrunch test (a planted instruction in an email) and record the result here. |

## What we can say in a pitch today

- "MIKAI never books, buys or signs anything on your behalf. It tells you where
  things stand; you or your assistant act."
- "Your knowledge base is plain files on your own disk. You can open, edit or
  delete every page."
- "Calendar changes happen only after you tap Approve."
- "It stays silent by default, and every decision — including the silent
  ones — is logged so you can audit it."
- "Every change it makes to your knowledge base can be undone."

**Do not say yet:** "no passwords", "delete means delete", "never leaves your
device", "we publish our dismiss rate", "never fails silently".

## Cross-references

- `docs/COMPARISON.md` — sourced competitive landscape (Instinct, Muse, Dots, Hermes)
- `docs/VISION.md` §2 — the narrower moat claim (task-state + measured interruption quality)
- `docs/DECISIONS.md` — D-053 (Surface Engine), D-054 (feedback loop), D-055 (approval loop)
- `docs/branches/feat-brain-hands-hermes.md` — branch manifest
