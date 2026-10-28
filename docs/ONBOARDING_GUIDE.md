# Set up MIKAI on your Mac

*User guide · 2026-10-27 · for early testers. About 15 minutes.*

MIKAI is a personal assistant you text on iMessage. It remembers what you're
working on, runs errands on the web for you (bookings, purchases, check-ins,
cancellations) and checks in when something slips. It asks for your "yes"
before it spends money or messages anyone.

## What you need

| You need | Why |
|---|---|
| A Mac (macOS 13 or newer) that stays on most of the day | MIKAI runs on your Mac. When it sleeps, MIKAI can't answer. |
| An iPhone with iMessage | That's where you talk to MIKAI. |
| A **Claude Pro or Max** subscription, with Claude Code installed and logged in | MIKAI thinks with Claude, through your own plan. No API keys. |
| **Google Chrome** | MIKAI gets its own separate Chrome to run errands in. Your normal Chrome isn't touched. |
| Access to the MIKAI repository | The setup script lives in it. |

## Steps

1. **Install Claude Code and log in.** Install it from claude.com/claude-code, open
   Terminal, run `claude`, and log in with your Claude account. Type `/exit` when done.
2. **Get the MIKAI code.** In Terminal: `git clone <MIKAI repo URL> ~/MIKAI`
3. **Run setup**, with your first name and mobile number:
   ```
   ~/MIKAI/infra/onboarding/mikai-setup --user-name "Alex" --phone +16045551234
   ```
   It explains each step as it goes, and it's safe to run again if anything stops
   halfway. To see what it would do without changing anything, add `--dry-run`.
4. **Approve the iMessage sign-in.** A Photon page opens in your browser
   (Photon provides MIKAI's iMessage line). Approve it. Setup then prints
   **MIKAI's phone number**. Save it as a contact called "MIKAI".
5. **Text MIKAI "hi" once** from your iPhone. That allows MIKAI to message you first later.
6. **Give macOS permissions** (setup opens the right page):
   - **Full Disk Access** for the path setup shows you (it's on your clipboard).
     This lets MIKAI read, but never change, your calendar and recent iMessages,
     so it knows your schedule and notices conversations you dropped. Skip it
     and MIKAI still works without that context.
   - **Notes:** if you choose to import your notes, macOS asks whether Terminal may
     control Notes. Click OK. Nothing in Notes is changed.
7. **Sign in to sites in MIKAI's Chrome.** A separate Chrome window opens: that's
   MIKAI's. Sign in to Gmail, your calendar, and places you buy from (tickets,
   restaurants, airlines), with a card saved where you buy. MIKAI can only reach
   the sites you sign in to there.
8. **Text MIKAI something you need done**, like "Find two seats for a movie Friday
   night near me." It does the legwork, then texts you a summary and waits for
   "yes" before buying.

## What MIKAI can and can't do

| It will | It won't |
|---|---|
| Search, compare, fill in forms, book, buy, check you in, cancel subscriptions | Pay, book, cancel or message anyone without your "yes" to a summary first |
| Pay with cards already saved on a site | Ask for or type passwords or card numbers over iMessage |
| Add and move events on your own calendar | Send invites to other people without your "yes" |
| Read your calendar and recent texts (with Full Disk Access) | Change anything in Calendar, Messages or Notes |
| Track every errand as a thread you can ask about ("what's open?") | Use your normal Chrome or its logins |

## What leaves your Mac

| Goes to | What | Why |
|---|---|---|
| **Anthropic** (Claude) | Your messages to MIKAI, and the notes, calendar items or texts it reads to answer you | That's how MIKAI thinks. It uses your own Claude account's settings. |
| **Photon** | Your iMessage conversation with MIKAI | Photon runs the iMessage line. |
| **Websites MIKAI uses for you** | Whatever an errand needs (e.g. a booking form) | Same as if you browsed them yourself. |

Everything else (your threads, imported notes, MIKAI's Chrome logins) stays on
your Mac under `~/.mikai/`.

## Using your Claude quota

Every message to and from MIKAI uses your Claude plan, from the same pool as
your normal Claude use. A simple reply costs about as much as a short Claude
chat; errands with many browser steps cost more.

## Removing MIKAI

```
~/MIKAI/infra/onboarding/mikai-uninstall
```

It backs everything up to a file in your home folder first, removes MIKAI's
background service, Chrome profile (which signs MIKAI out of every site),
threads and notes, and restores your previous Hermes settings. Add
`--keep-data` to keep your threads and notes. To release MIKAI's phone number,
delete the "Hermes Agent" project at app.photon.codes.

## If something goes wrong

- **MIKAI doesn't reply:** is your Mac awake? Run `~/.local/bin/hermes gateway status`.
- **Setup stopped:** read the last red line, fix what it says, and run setup again.
  Finished steps are skipped.
- **MIKAI says it can't reach a site:** sign in to that site in MIKAI's Chrome.
