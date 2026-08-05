# Surface Engine — Notification Surface Decision

> **What this file is:** Survey of candidate notification surfaces, the V1 choice, and the path to V2. Anchored in Brian's stated constraints: "I am a power user of Claude, but I can't just type in terminal commands of 'what should I deal with today.' Function surface first, optimize as we go."
>
> **Decision date:** 2026-06-28
> **V1 surfaces (operational):** ntfy.sh → iPhone (already shipped) + macOS Calendar.app daily brief (this session) + macOS osascript notification (existing fallback)
> **V2 candidates:** browser extension (Dia, Chrome MV3) OR lightweight web client

---

## 1. The Steve Jobs frame

Brian invoked the iPhone metaphor: collect all life needs in one place with AI managing them. The single-surface goal is real but a single-surface V1 is premature — Brian has different attention modes in different contexts (mobile vs laptop, focused work vs ambient). The right framing is *cohesive multi-surface, single brain* — Surface Engine makes one decision, dispatches to whichever surface fits the moment.

A useful constraint: any V1 surface must be **already-running** for Brian. He's not going to install a new app just to receive Surface Engine notifications. He IS already running:

- iPhone (ntfy app subscribed, verified working)
- macOS Calendar.app
- Claude Code in terminal (already integrated as MCP client)
- Gmail (already integrated as adapter)
- ntfy.sh client on Mac (optional)

Adding to this stack: zero. Removing from it: not yet.

---

## 2. Surface survey

For each surface: latency, interactivity, persistence, batching, infra cost, fit, Steve-Jobs metaphor fit, Surface Engine impl path.

### 2.1 ntfy.sh (status: V0 SHIPPED)

| Property | Value |
|---|---|
| Latency | <2s globally |
| Interactivity | Limited — tap opens body, no inline buttons reaching Surface Engine without a webhook handler |
| Persistence | iOS Notification Center retains them; ntfy app keeps history |
| Batching | Per-event, no built-in digest |
| Infra cost | Free (ntfy.sh) or self-hosted; $0 |
| Fit | Brian uses it; iPhone subscribed and verified |
| Jobs-metaphor fit | Partial — appears in iOS Notification Center alongside everything else, which IS the Jobs vision |
| Surface Engine impl | `dispatch_via_ntfy(title, body, priority)` already in `mikai_decide.py` |

**Verdict for V1:** Keep. Primary mobile surface. Brian sees these whether or not he's at his laptop.

**Known limitation:** No click-tracking back to Surface Engine. The CLI workaround (`mikai mark-acted`) is the V1 closer-of-loop.

### 2.2 macOS Calendar.app daily brief (status: SHIPPING THIS SESSION)

| Property | Value |
|---|---|
| Latency | Whenever Brian opens Calendar, ~daily |
| Interactivity | Tapping the event reveals the body — that IS the brief |
| Persistence | Maximum. Events sit on the day they were written, browsable for weeks |
| Batching | Native — one event per day, body contains top-3 surfaces |
| Infra cost | Free (osascript writes to local Calendar.app) |
| Fit | Brian already uses Calendar for work scheduling. Adding a daily MIKAI brief event makes Calendar a glanceable status dashboard. |
| Jobs-metaphor fit | High — Calendar is one of Brian's most-glanced surfaces. The brief lives there alongside meetings. |
| Surface Engine impl | `dispatch_calendar.py` writes the event via osascript at the start of each day. Body = the top-3 from Surface Engine' candidate slate. |

**Verdict for V1:** Ship. This is the surface Brian asked for ("calendar or web browser client"). Calendar is the lower-cost V1 because it requires no new infrastructure.

**Cadence:** Once daily at 7am local. Event time 7am-7:30am. Title: "MIKAI: today's brief — {top need}". Body: 3 candidates, each one line + the next_step from the registry.

### 2.3 macOS Notification Center (osascript `display notification`)

| Property | Value |
|---|---|
| Latency | <500ms |
| Interactivity | Tap to dismiss only. No inline buttons. |
| Persistence | macOS Notification Center holds until cleared |
| Batching | Per-event |
| Infra cost | $0 |
| Fit | Brian's already on the laptop; reaches him without switching context |
| Jobs-metaphor fit | Yes — this IS the macOS native equivalent of iOS Notification Center |
| Surface Engine impl | Trivial: `osascript -e 'display notification "..." with title "..."'` |

**Verdict for V1:** Yes, as a parallel dispatch alongside ntfy. If Brian's at his desk, this is more glanceable than checking iPhone.

**Limitation:** Same as ntfy — no click-tracking. Use the CLI to close the loop.

### 2.4 terminal-notifier (with action buttons)

| Property | Value |
|---|---|
| Latency | <500ms |
| Interactivity | Yes — `-actions "Acted,Dismiss,Snooze"` returns the response |
| Persistence | macOS Notification Center |
| Batching | Per-event |
| Infra cost | `brew install terminal-notifier` (one-time) |
| Fit | Best macOS interactivity available without a Swift app |
| Jobs-metaphor fit | Yes |
| Surface Engine impl | `subprocess.run(["terminal-notifier", "-title", t, "-message", b, "-actions", "..."])` returns Brian's choice → write straight to log |

**Verdict for V1:** Wire up but graceful fall-through to osascript if not installed. Brian's machine doesn't have it yet (as of this session). Prompt him once to install; Surface Engine works without it.

### 2.5 Pushover (paid, native iOS click-tracking)

| Property | Value |
|---|---|
| Latency | <2s |
| Interactivity | Native action buttons; click-tracking via webhook |
| Persistence | Pushover app |
| Batching | Per-event |
| Infra cost | $5 one-time per platform (iOS/macOS each) |
| Fit | Best mobile interactivity without going full APNs |
| Jobs-metaphor fit | Yes — sits in iOS Notification Center |
| Surface Engine impl | Replace `dispatch_via_ntfy()` with `dispatch_via_pushover()` — same shape, different HTTP endpoint and auth |

**Verdict for V1:** Defer. If ntfy fatigue surfaces and Brian needs click-tracking, this is the next move. $5 + 30 minutes to integrate.

### 2.6 Browser extension (Dia / Chrome MV3)

| Property | Value |
|---|---|
| Latency | <1s on focus |
| Interactivity | Maximum — full HTML/JS UI, can show the top-3 in a side panel |
| Persistence | Pinned tab or extension popup |
| Batching | Native — show full slate |
| Infra cost | ~3 days to build MV3 extension + 1 day to package |
| Fit | Brian's browser is open ~all his working hours |
| Jobs-metaphor fit | Highest — this IS the "executive assistant in one place" surface |
| Surface Engine impl | Extension polls `mikai_decide.py --json --show-slate` every N minutes; rich UI in popup. |

**Verdict for V1:** Defer. This is the V2 target — Brian explicitly mentioned "browser client" as a leading candidate. The trigger to build it: V1 surfaces (ntfy + Calendar + macOS notification) drive a stable productivity > 0.3 but Brian wants richer interaction (e.g., snooze / reschedule from the surface itself).

### 2.7 Telegram bot

| Property | Value |
|---|---|
| Latency | <1s |
| Interactivity | Inline keyboard buttons (Acted/Dismiss/Snooze) reach Surface Engine via webhook |
| Persistence | Chat history |
| Batching | Per-event or batched (Surface Engine controls) |
| Infra cost | Free; ~1 day to set up bot + webhook handler |
| Fit | Depends — Brian uses Telegram? Per his stated channels (iMessage/WhatsApp/Claude/email), Telegram is not primary |
| Jobs-metaphor fit | Partial — yet another inbox |
| Surface Engine impl | python-telegram-bot library + a small webhook server (already have Pattern B infra) |

**Verdict for V1:** Skip. Not a surface Brian uses daily. Reconsider if Telegram becomes a primary channel.

### 2.8 Email digest (Gmail send)

| Property | Value |
|---|---|
| Latency | <1m |
| Interactivity | Click-through to body |
| Persistence | Email is the most persistent surface there is |
| Batching | Natural — once daily/weekly |
| Infra cost | $0 — Gmail adapter is already an outbound capability |
| Fit | Brian's already using Gmail as an inbound adapter |
| Jobs-metaphor fit | Low — adds to an already-noisy inbox |
| Surface Engine impl | SMTP via the existing Gmail adapter, swapped from read to send |

**Verdict for V1:** Skip. Email is high-noise; Surface Engine' job is to reduce, not add. V3 candidate if Brian wants a weekly digest.

### 2.9 Raycast extension

| Property | Value |
|---|---|
| Latency | <500ms on hotkey |
| Interactivity | Full Raycast UI; native Mac feel |
| Persistence | None — appears on hotkey |
| Batching | Native — show full slate |
| Infra cost | ~2 days to build (Brian has Raycast?) |
| Fit | Yes for power users; depends on whether Brian uses Raycast |
| Jobs-metaphor fit | Medium — pull surface, not push |
| Surface Engine impl | Raycast Node extension calling `mikai_decide.py --json --show-slate` |

**Verdict for V1:** Skip unless Brian uses Raycast actively. The pull-on-hotkey behavior is good but doesn't replace a push surface.

### 2.10 Menubar app

| Property | Value |
|---|---|
| Latency | <1s |
| Interactivity | Click-through to dropdown |
| Persistence | Always visible in menubar |
| Batching | Natural — show top-N in dropdown |
| Infra cost | ~3 days to build Swift menubar app |
| Fit | macOS-only |
| Jobs-metaphor fit | High — single ambient surface |
| Surface Engine impl | Swift menubar app polling `mikai_decide.py --json --show-slate` |

**Verdict for V1:** Skip. Same end state as browser extension, more Mac-specific. Browser extension is more portable.

---

## 3. The V1 decision

**Surfaces shipping in V1:**

1. **ntfy.sh → iPhone (primary mobile)** — already shipped, verified
2. **macOS Calendar.app daily brief (primary persistent surface)** — `dispatch_calendar.py` writes a 7am daily event with the top-3 candidates from Surface Engine' slate
3. **macOS osascript notification (immediate-attention secondary)** — when Surface Engine fires a notification, also pop a macOS native one for low-friction Brian-at-desk awareness
4. **terminal-notifier upgrade path** — if installed, use it for action buttons; otherwise gracefully fall back to osascript
5. **CLI for response capture** — `mikai mark-acted`, `mikai mark-dismissed`, `mikai snooze` close the feedback loop until a richer surface lands

These four surfaces share one Surface Engine brain. The decision of what to surface happens once per tick; dispatch fans out.

**Surfaces NOT in V1:**

- Pushover (paid, not yet warranted; trivial to add when needed)
- Browser extension (the V2 target)
- Telegram (not Brian's daily channel)
- Email digest (would add to inbox noise)
- Raycast (depends on usage)
- Menubar app (subsumed by browser extension in V2)

---

## 4. V1 → V2 transition criteria

**Brian opens a browser extension or web client when ALL of:**

1. V1 has been running 14+ days with ≥20 dispatches
2. `mikai metrics` shows productivity ≥ 0.3 and dismiss_rate ≤ 0.30 (per PPP threshold)
3. Brian reports wanting richer interaction (snooze-from-surface, full-slate view, candidate-level mute) that the current surfaces don't provide
4. There's at least one specific surface deficiency that V2 would close (e.g., "the daily Calendar brief is too static — I want to be able to mark items done from within the surface")

If 1+2 hold but 3+4 don't, Brian doesn't need V2. The V1 surface is sufficient.

---

## 5. The Steve Jobs frame, revisited

Jobs collected the camera, iPod, and phone into one device because the user's *attention is one*. Surface Engine collects all of Brian's life needs into *one decision* — the same brain decides what to surface across iPhone, Calendar, Mac notification, and (later) browser extension.

The brain is `mikai_decide.py` reading the User Needs Registry + Dream wiki + adapters. The surfaces are dumb dispatchers. This separation is the Jobs unification — the user experience is "MIKAI knows what I care about and surfaces it where I'll see it." The actual delivery channel is implementation detail Surface Engine chooses based on context.

**V1 ships the brain plus the four surfaces.** V2 will replace surface-multiplexing with a single rich surface (browser extension) once V1 demonstrates the brain works.

---

## 6. Concrete dispatch summary

| Channel | When Surface Engine uses it | Code path |
|---|---|---|
| ntfy.sh | Every send decision | `dispatch_via_ntfy()` in `mikai_decide.py` |
| Calendar.app daily | Once daily at first tick after 6am local | `dispatch_calendar.py` |
| macOS notification | Every send decision | New: `dispatch_via_osascript()` |
| terminal-notifier | If installed, instead of osascript | New: `dispatch_via_terminal_notifier()` |
| CLI (mikai mark-*) | Brian invokes after seeing/responding | New: `mikai_cli.py` |

---

## 7. The first 24 hours

After this session ships:

1. Brian runs `mikai metrics` — sees baseline (likely all zeros).
2. Next Surface Engine tick: receives an ntfy notification AND a macOS notification AND a Calendar event for tomorrow.
3. Brian reads the Calendar event tomorrow morning; sees the top-3 brief.
4. Brian either runs `mikai mark-acted <id>` or lets it sit; Surface Engine observes via `acted_within_24h` backfill.
5. After 7 days: `mikai metrics` is meaningful. Brian + Surface Engine together evaluate whether V2 is warranted.
