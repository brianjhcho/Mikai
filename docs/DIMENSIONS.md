# MIKAI — Life Dimensions

> **What this file is:** Brian's personal ontology. Nine top-level life dimensions,
> each with concrete goals and evidence concepts. FIGS reads this to organize
> surfacing by dimension rather than by flat entity density.
>
> **Why this exists:** the density lens surfaces high-mention concepts, but
> without an ontology those collapse into framework/tooling noise. The dimensions
> are the schema that turns raw evidence into meaningful surfacing.
>
> **How to maintain:** hand-edit. Add goals, retire done ones, promote concepts
> into goals as they crystallize, expand the noise list as new noise appears.
>
> **Pattern:** each `## N. Dimension` section has (a) `goals:` — concrete things
> being worked toward, (b) `concepts:` — evidence entities that route into this
> dimension, and (c) `notes:` — freeform framing.

---

## 1. AI Career / MIKAI Build

goals:
- Decide founder-track (MIKAI-as-startup) vs employee-track (AI job search) — state=exploring, urgency=high
- Ship MIKAI to a usable prototype — state=acting

concepts (mostly framework noise absorbed here — DO NOT surface as notifications unless a decision point arises):
- MIKAI, FIGS, Assistant, Claude Code, Perplexity, Neo4j, Graphiti, OpenAI, Anthropic, DeepSeek, Gemini, LLM, Ollama, Docker, sync.py, bot.py, dream.py, mikai_decide.py, HICCUP, Hermes, Sumimasen, Noonchi, openclaw, sidecar, launchd, MCP, iPhone, iMessage, Telegram, Instagram, Facebook, Google, Apple, Microsoft, GitHub, ChatGPT, Slack, Notion, n8n, Mem.ai, main, Cursor, Pinecone, Voyage, WhatsApp, Signal, Discord

notes:
This dimension is the meta-project. Brian is in it every day; he does not need
FIGS to remind him. Only surface if a concrete decision point crystallizes
(founder-vs-employee commitment, ship-milestone, funding move, tool-choice
gate). Framework noise here is deliberately captured so the rest of the
system knows to route it away from notification surface.

---

## 2. Where to Live

goals:
- Decide next long-term city / base — state=exploring, urgency=medium
- Reactivate BC residency (also under Health: MSP) — state=blocked (in-flight elsewhere)

concepts:
- Vancouver (current), Austin, Singapore, Seoul, Korea, Argentina, Buenos Aires,
  Nairobi (overlaps with Business Opportunities), BC

notes:
Cross-cuts with Business Opportunities (Nairobi appears both as "should I live
there" and "is there a venture here"). Germaine's preferences bind this
dimension to the relationship dimension.

---

## 3. Business Opportunities

goals:
- Identify + evaluate ventures worth pursuing — state=exploring
- Automate trading (parallel path — see also dimension 8) — state=exploring

concepts:
- Ocean farming, 3D ocean farming, kelp, food technology, freeze drying,
  Kenya coffee, Kenya, Nairobi, Vancouver food scene, ring industry
  (Whiteflash, Brilliant Earth), agritecture

notes:
The unifying frame is "ventures worth Brian's time, given his skills and
where he wants to live." Ocean farming, Kenya coffee, and food-tech are
long-running research threads; ring industry is a spike from the proposal
thread. Cross-references: Where to Live (Nairobi), Relationship (ring
industry via Germaine).

---

## 4. Relationship with Germaine

goals:
- Propose (ring + venue) — state=in_flight, urgency=high — registry: `proposal-ring-and-venue`
- Life planning (long-horizon: shared city, family, timing) — state=exploring

concepts:
- Germaine, Atacama, Ladakh, engagement ring, Whiteflash, Brilliant Earth,
  James Allen, proposal, venue, Skyscanner, Airbnb

notes:
This is the sharpest active life thread — venue picking is the current
cycle-breaker. Cross-references: Business Opportunities (ring industry
came in via this thread), Where to Live (Germaine's preferences).

---

## 5. Family Obligations

goals:
- Get Mom a Scotia credit card — state=on_hold, urgency=medium — registry: `mom-scotia-credit-card`

concepts:
- Mom, Scotia, Scotia online banking, joint applicant, credit card

notes:
Low frequency but load-bearing. On hold for reasons Brian has not surfaced
back to himself; FIGS should ask "still on hold?" rather than nag.

---

## 6. Health / Body

goals:
- Reactivate MSP — state=blocked, urgency=high — registry: `msp-reactivation-bc`
- Dry-eye investigation + smoking cessation — state=acting, urgency=medium
- Rib-flare / lower-back pain resolution via yoga alignment — state=acting
- Cat weight management — state=acting, urgency=low

concepts:
- MSP, BC, ServiceBC, dry eye, meibomian gland, lipid layer, tear film,
  smoking, rib flare, basketball, back pain, deadlift, yoga, ATG split
  squat, KB lunge, ab wheel, anterior pelvic tilt, cat, lentigo, RER

notes:
Weighted yoga is the primary interventional program; dry eye is diagnostic
+ investigation; MSP is administrative but time-sensitive (health-coverage
gap risk). The rib-flare mechanism (identified 2026-06) is the load-bearing
insight for the whole body program.

---

## 7. Craft / Hobbies

goals:
- Monstera pillar climbing project — state=acting
- Alocasia care (Dark Star) — state=decided→acting
- Full home plant collection survey + light optimization — state=acting

concepts:
- Monstera, Alocasia, Dark Star, Calathea ornata, Ctenanthe Grey Star,
  Ficus Burgundy, cryptomeria, olive tree, bonsai, west-facing pillar,
  diagonal spiral pattern, tennis, basketball

notes:
Sculptural/architectural plants are the through-line — Brian consistently
picks single-stem forms, wants elegance over biological reality. Tension
already surfaced in wiki. Low-urgency but joy-adjacent — surface at cadence
that respects rest of life.

---

## 8. Financial / Trading

goals:
- Automate trading (or trade suggestions) — state=exploring — registry: `automate-trading`
- Resolve crypto/Kenyan-driver situation — state=acting→stalled

concepts:
- IBKR, Alpaca, PayPal, trading strategy, earnings drift, sector momentum,
  Polygon, Yahoo Finance, TradingView, QuantConnect, crypto, Kenyan driver
  (Robby Musundi), $2 test transfer, $55 transfer, small-test ratchet

notes:
Automate-trading is stuck at "define one strategy class" — infra doesn't
help without strategy. Crypto/Kenya is a live tension (trust vs evidence)
and belongs in ## Tensions of the wiki as well.

---

## 9. Recurring Themes (Self-Messages)

Not goals — recurring wisdom Brian tells himself, month over month. FIGS
does not usually surface these as notifications (they're not actionable);
the wiki's `## Who` should reflect them as stable-trait self-model.

exemplars (from June 2026 notes):
- "Life is composed of the journey — not commencing after you've figured
  it out."
- "Spirit is free but needs to be more resolute — unapologetic, not
  asking permission."

notes:
Look for these as high-signal short-form entries repeated across months of
Apple Notes. They shape HOW Brian approaches every goal above; the wiki
Who section should quote them. FIGS may occasionally surface one as a
morning-tick philosophical anchor, but not more than once a week.

---

## Per-Dimension Destination Templates

FIGS reads these when composing `next_step_url` on each notification. Each
template pairs a **type of pickup** with the **canonical URL** or app deep-link
that transports Brian to the doing. When a notification's pickup matches a
template, use the URL; when nothing matches, set `next_step_url: null`.

**Dim 2 · Where to Live**
- `flight search` → `https://www.google.com/flights?q=<from>+to+<city>`
- `city housing browse` → Vancouver `https://www.rew.ca`, Austin `https://www.har.com`, Singapore `https://www.propertyguru.com.sg`, Nairobi `https://www.buyrentkenya.com`, Argentina `https://www.zonaprop.com.ar`
- `airbnb scout` → `https://www.airbnb.com/s/<city>`

**Dim 3 · Business Opportunities**
- `ocean farming grant / partner outreach` → `https://www.bcsrif.ca` (BC Salmon Restoration & Innovation Fund) or `mailto:info@ulvaseafarms.com`
- `Kenya coffee exchange` → `https://www.nairobicoffeeexchange.co.ke`
- `Vancouver commercial real estate` → `https://www.bcassessment.ca` (Int'l Village lookup) or `mailto:leasing@crystalmall.ca`
- `venture research` → `https://www.perplexity.ai/search?q=<query>`

**Dim 4 · Relationship with Germaine**
- `ring quote` → Whiteflash `https://www.whiteflash.com/loose-diamonds/`, Brilliant Earth `https://www.brilliantearth.com/loose-diamonds`, James Allen `https://www.jamesallen.com/loose-diamonds`
- `flight to Atacama` → `https://www.google.com/flights?q=YVR+to+CJC` (Calama)
- `flight to Ladakh` → `https://www.google.com/flights?q=YVR+to+IXL` (Leh)
- `venue lodging` → `https://www.airbnb.com/s/atacama` or `https://www.airbnb.com/s/ladakh`
- `Germaine shared calendar` → `https://calendar.google.com/calendar/u/0/r?tab=mc`

**Dim 5 · Family Obligations**
- `Scotia banking (joint applicant / card)` → `https://www.scotiaonline.scotiabank.com`
- `Scotia iOS app` → `scotia://` (iPhone) or `https://apps.apple.com/ca/app/scotiabank/id382597895`

**Dim 6 · Health / Body**
- `MSP reactivation` → `https://my.gov.bc.ca/msp/application` (Health Insurance BC portal)
- `ServiceBC (BC address docs, licence lookup)` → `https://www.gov.bc.ca/servicebc`
- `ICBC (BC driver's licence)` → `https://onlinebusiness.icbc.com/dbc`
- `dry eye / optometrist appointment` → `mailto:office@<optometrist>` or the optometrist's booking URL
- `yoga program tracker` → local file / Apple Notes deep link

**Dim 7 · Craft / Hobbies**
- `plant research` → `https://www.perplexity.ai/search?q=<species>+care`
- `Home Depot / plant supplies` → `https://www.homedepot.ca`
- `Vancouver plant nurseries` → `https://www.figaros.ca` (or local specialty)

**Dim 8 · Financial / Trading**
- `IBKR client portal` → `https://www.interactivebrokers.com/portal`
- `Alpaca (paper trading)` → `https://app.alpaca.markets/paper/dashboard/overview`
- `TradingView` → `https://www.tradingview.com/chart/`
- `strategy backtesting (QuantConnect)` → `https://www.quantconnect.com/lean/docs`
- `PayPal decline / transaction review` → `https://www.paypal.com/myaccount/activity`
- `Robby message decline draft` → `mailto:draft` with pre-composed decline body

**Dim 9 · Recurring Themes**
- Usually NULL — themes are for reflection, not action. Optionally: Apple Notes deep-link to the source note where the theme was first captured.

**Dim 1 · AI Career / MIKAI Build**
- Normally NULL — background work, Brian is in it every day.
- If a founder-vs-employee decision point crystallizes: `mailto:draft` to write the memo, or `https://linkedin.com/jobs/search/?keywords=AI+founding+engineer` for the employee side.

**Fallback URL schemes** (when no template matches):
- Draft email → `mailto:` (with `?subject=…&body=…` for pre-filled content)
- Apple Calendar → `x-apple-calshow://` or `webcal://`
- Apple Notes deep-link → `notes://showNote?identifier=<uuid>` or search `notes://showFolder?identifier=<name>`
- Phone call → `tel:+1...`
- iOS Shortcuts (custom automation) → `shortcuts://run-shortcut?name=<name>`

---

## How FIGS uses this file

At every tick, the FIGS decider reads this file and:

1. Uses the dimensions as bins. When ranking candidates for surfacing, aim
   for spectrum coverage — the 2-5 slate should span at least 3 different
   dimensions, not stack 5 items from one dimension.
2. Uses the noise list under Dimension 1 as a filter. If a candidate's
   entity name appears there and it doesn't map to a concrete decision
   point (founder/employee, ship milestone, funding move), it is background
   context, not notification-worthy.
3. Uses the goals list as the strong-signal set. A candidate that
   corresponds to a listed goal-with-state (in_flight, blocked, stalled)
   is a first-class surfacing candidate.
4. Uses Recurring Themes as an occasional wiki-anchor, not as
   notifications.
