# Instinct-like actions — verification (2026-10-27)

Test errand (public site, no login): *"Find showtimes for a movie this Friday
evening at the Cineplex closest to downtown Vancouver, pick two seats, and stop
at the confirmation summary. Do not pay."* Run as one-shot turns with the same
toolsets iMessage uses: `hermes -z "<errand>" -t browser,web,mikai`.

## Results

| Run | Setup | Outcome | Cost |
|---|---|---|---|
| 1 | `-t browser,web` | **Fail.** No browser tool. MIKAI tools not loaded. Stopped to ask "which movie?" | 20.5K tokens, 3 calls |
| 2 | Fix 1 + Fix 2 + `-t browser,web,mikai` | **Pass up to the CAPTCHA.** Drove Cineplex in the MIKAI Chrome, found real Friday Oct 30 showtimes at Scotiabank Theatre, defaulted to a movie, logged a thread, stopped at Cineplex's hCaptcha without trying to bypass it. Nothing held or paid. | 2.6M tokens (2.47M cached reads), 38 calls |
| 3 | + Fix 3 | **Same result,** about a third of the cost. | 0.91M tokens (0.84M cached), 21 calls |

## Fixes made

1. **Browser tool was missing.** Hermes's default "Browser Use" mode exposes a
   single `browser_exec` tool that only appears when the `terminal` toolset is
   on (it runs Python). Terminal stays off for safety, so no browser existed.
   Set `browser.backend: "off"` → Hermes's built-in `browser_*` tools, which
   attach to the MIKAI Chrome over CDP (`browser.cdp_url`) with no extra binary.
2. **Stopped instead of acting.** SOUL.md now says missing details are not a
   reason to stop: pick a sensible default, carry the errand to the
   confirmation step, name the choices in the summary.
3. **Cost.** `agent.max_turns: 40` (was 500), `browser.snapshot_threshold: 8000`
   (was 15000), and a SOUL rule to look things up with web search and use the
   browser only for clicking/typing.
4. **Duplicate threads.** Each run created its own thread. SOUL now says check
   `mikai_threads_list` and update the matching thread before creating one. The
   test duplicate was moved to `~/.mikai/brain/threads/.history/`.

Backups: `~/.hermes/config.yaml.bak-pre-actions-test`,
`~/.hermes/SOUL.md.bak-pre-actions-test`, `~/.hermes/SOUL.md.bak-pre-dedupe`.

## What works

- Browsing real sites in the dedicated MIKAI Chrome (`~/.mikai/browser-profile`, CDP on 127.0.0.1:9222).
- Finding real availability and prices, choosing defaults, explaining choices.
- Stopping before payment, and stopping at bot checks instead of fighting them.
- Logging the errand as a MIKAI thread with state `acting` and the blocker as `next_step`.

## What doesn't (yet)

- **CAPTCHAs / bot checks** (Cineplex uses hCaptcha + Imperva). Hermes won't
  bypass them. Signing in to the site in the MIKAI Chrome usually reduces them;
  otherwise Brian clears the check once, then says "go".
- **Anything behind a login** until Brian signs in to that site in the MIKAI Chrome.
- **Cost is still high per errand** (~0.9M tokens, mostly cached reads). Fine
  for a few errands a day on the subscription; not for heavy use.
- **The "yes before paying" gate is an instruction, not code.** Watch the first
  few real purchases.
- **Thread dates use UTC**, so an evening errand in Vancouver can be stamped tomorrow.
- **Not yet exercised over iMessage itself** — tested via `hermes -z` with the
  iMessage toolsets; the live gateway has the same config and was restarted.

## Five errands to text MIKAI

1. "Find a table for 2 at a Japanese place near Kitsilano Saturday 7pm and hold it once I say yes."
2. "Check me in to my next flight and send me the boarding pass." *(needs the airline login in the MIKAI Chrome)*
3. "What subscriptions am I paying for? Find any I haven't used in 3 months." *(needs Gmail login)*
4. "Get two tickets for Street Fighter Friday 6:35 at Scotiabank Theatre." *(sign in to Cineplex first)*
5. "Remind me Sunday at 6pm to prep the week, and put a 30-minute block on my calendar for it."
