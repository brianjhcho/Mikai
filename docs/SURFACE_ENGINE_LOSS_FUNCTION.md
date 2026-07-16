# Surface Engine — Loss Function and Surface-Priority Metric

> **What this file is:** The formal definition of how Surface Engine decides what to surface, how it measures whether its surfacing was useful, and how it improves over time. Grounded in five research papers on intervention timing and proactive AI assistance (see `docs/research/l4-papers.md`).
>
> **Audience:** Surface Engine implementation code, the Claude prompt in `mikai_decide.py`, and Brian when he wants to understand or tune Surface Engine' behaviour.
>
> **Status:** V1 (operational). Numeric calibration deferred — the LLM-as-judge implementation of `delivery_value` and `delivery_cost` is the V1 stand-in for the learned-utility model that the literature implies but cannot be trained until 100+ logged interactions exist.

---

## 1. The surface-priority metric

Per candidate (a user need from the registry, or a wiki ## Now thread, or a raw graph thread), Surface Engine computes:

```
surface_priority = state_weight × tension_pressure × delivery_value × delivery_cost⁻¹
```

All four factors are 0..1.

### 1.1 `state_weight` — what the candidate's life-state implies about action-readiness

Source: MIKAI's own state model (see `FOUNDATIONS.md §3`), informed by ProMemAssist's recency-decay framing (UIST 2025, arXiv:2507.21378).

| State | Weight | Interpretation |
|---|---|---|
| `acting` | 1.00 | In motion; a nudge can compound progress |
| `stalled` | 0.95 | Was acting, dropped — the highest-value surface MIKAI exists for |
| `in_flight` | 0.95 | User-need-registry equivalent of `acting` |
| `blocked` | 0.90 | Wants to move but missing inputs — surface the blocker |
| `decided` | 0.70 | Choice made, scheduling is the open step |
| `on_hold` | 0.50 | Deliberately paused — surface as check-in, not nag |
| `exploring` | 0.40 | Pre-decision; surface open questions, not actions |
| `unknown` | 0.30 | Default for unparsable state |
| `done` | 0.00 | Closed — kept for learning, never surfaced |

### 1.2 `tension_pressure` — does the candidate sit in an active contradiction?

Source: MIKAI's epistemic edge vocabulary (`docs/EPISTEMIC_EDGE_VOCABULARY.md`); priority-0 signal per the Dream rule #1 ("Surface tensions, don't resolve them").

```
tension_pressure = min(1.0, 0.6 + 0.2 × num_tensions_referencing_thread)
```

- A thread in zero tensions: `tension_pressure = 0.6` (still meaningful — has its own weight)
- A thread referenced by one tension: `0.8`
- A thread referenced by two or more tensions: `1.0`

For user-need-registry entries, `tension_pressure` defaults to `0.7` unless the `blockers` field is non-empty, in which case `0.9` (a blocker IS a tension).

### 1.3 `delivery_value` — would surfacing this CHANGE what Brian does today?

Source: Inner Thoughts (CHI 2025, arXiv:2501.00383) "evaluation stage" — the question is not "is this true?" but "is this worth speaking?" plus the OmniActions (CHI 2024, arXiv:2405.03901) finding that recommendation value tracks with the user's action-readiness.

In V1, **this factor is judged by the LLM** in the prompt because the literature is clear that calibrated `delivery_value` requires a learned model over many interactions, and Surface Engine doesn't have those yet. The LLM is given explicit guidance:

| Signal | Effect on `delivery_value` |
|---|---|
| No new evidence in last 24h on this candidate | DOWN — repeating known info |
| Fresh raw event (calendar in 24h, message, email) tied to this candidate | UP — actionable trigger |
| Brian already surfaced this in last 48h | DOWN HARD — don't repeat |
| Recent `acted` response to similar candidate | UP — pattern of action validates |
| Recent `dismissed` response to similar candidate | DOWN HARD — don't repeat dismissed patterns |
| Brian is in active build-momentum on this thread | DOWN — he doesn't need a reminder |
| Candidate is a stalled thread with no follow-through | UP — the canonical MIKAI use case |

Numeric range: 0.0 — 1.0. In V2 (after ~100 logged interactions), this factor becomes a learned function over the historical act-rate per candidate-similarity-bucket.

### 1.4 `delivery_cost⁻¹` — what's the cost of being wrong?

Source: ProMemAssist's intervention timing gate (UIST 2025) and PPP's productivity/proactivity/personalization joint optimization (CMU Nov 2025, arXiv:2511.02208). PPP showed that optimizing productivity ALONE hurts proactivity and personalization — must optimize jointly.

`delivery_cost` is computed from:

| Component | Definition | V1 stand-in |
|---|---|---|
| Time-of-day cost | Workday hours = higher; late night = higher | LLM-judged from clock in prompt |
| Recent-dismiss cost | Last N dismisses raise the bar | LLM reads last 15 decisions from SQLite |
| Notification fatigue | More notifications today = higher bar | LLM reads total count today from SQLite |
| Interruption level cost | `timeSensitive` > `active` > `passive` | Hard rule: `timeSensitive` requires `delivery_value ≥ 0.9` |

`delivery_cost⁻¹` = 1 / (1 + cost). Range: ~0.3 (workday, fatigued) to ~1.0 (evening, no recent dismisses).

---

## 2. User-response signals — the four-channel feedback loop

When Surface Engine dispatches a notification, the user can respond in four distinguishable ways. Mapping borrows from PPP's reward function and Inner Thoughts' "participation" stage.

| Signal | Captured how | Maps to |
|---|---|---|
| `ACTED` | (a) ntfy click → opens MIKAI URL handler that posts back; (b) within 24h Brian opens the linked external surface (e.g., Scotia app) and Surface Engine sees evidence in the graph; (c) manual `mikai mark-acted <log_id>` CLI | Productivity: +1; Calibration: positive class |
| `DISMISSED` | ntfy swipe-clear OR `mikai mark-dismissed <log_id>` CLI | Productivity: −1; Personalization: increments dismiss count for this candidate-category |
| `IGNORED` | No response within 24h of dispatch, AND no graph evidence of acting | Productivity: −0.3; Personalization: weak signal — Brian saw it and didn't engage |
| `SNOOZED` | `mikai snooze <log_id> <days>` CLI; or the LLM detects a dismiss-then-later-acted pattern | Productivity: 0; Personalization: positive long-tail signal |

**V1 instrumentation gap.** ntfy.sh's iOS app does NOT report click/dismiss back to the publisher. Brian sees the notification but Surface Engine sees no response unless Brian uses the CLI. V1 ships with the CLI; V2 should consider native iOS (APNs) or Pushover with click-tracking webhooks. See `SURFACE_ENGINE_DECISION.md`.

---

## 3. The loss function (per tick)

The LLM doesn't see this directly — it's the framework for evaluating Surface Engine' decisions over time. Computed daily over the SQLite log:

```
L(t) = α·dismiss_rate(t) + β·ignore_rate(t) − γ·act_rate(t) − δ·time_to_act⁻¹(t)
```

Where:
- `dismiss_rate(t)` = dismisses in last 7 days / total dispatches in last 7 days
- `ignore_rate(t)` = ignored (no response within 24h) / total dispatches
- `act_rate(t)` = acts within 24h / total dispatches
- `time_to_act` = median seconds from dispatch → ACTED for dispatches that were acted on
- α=1.0, β=0.5, γ=2.0, δ=0.1 (initial weights; tunable)

Lower L is better. Negative L = Surface Engine is net-helpful.

**Target operating ranges**, per PPP's empirical finding (CMU Nov 2025) that dismiss rate ≤30% after 20 interactions is the threshold below which proactive systems sustain trust:

| Metric | Target after 20 dispatches | Target after 100 dispatches |
|---|---|---|
| `dismiss_rate` | ≤ 0.30 | ≤ 0.20 |
| `ignore_rate` | ≤ 0.40 | ≤ 0.30 |
| `act_rate` | ≥ 0.30 | ≥ 0.40 |
| Median `time_to_act` | ≤ 6 hours | ≤ 3 hours |

If after 20 dispatches `dismiss_rate > 0.30`, the operational policy is: lower the Surface Engine dispatch threshold, NOT increase notification volume. The literature is consistent — surfacing more does not improve action rates, it just trains the user to ignore.

---

## 4. The four PPP-adapted metrics

PPP (CMU Nov 2025, arXiv:2511.02208) ran a joint-optimization training loop on three signals (productivity, proactivity, personalization). Surface Engine adapts these for single-user MIKAI plus adds calibration as a fourth quality metric.

### 4.1 Productivity — "did Brian act on what I surfaced?"

```
productivity = acts_within_24h / total_dispatches
```

The most direct measure of whether Surface Engine is useful at all. A productivity of 0 = Surface Engine is just noise.

### 4.2 Proactivity — "was the surface unsolicited and useful?"

```
proactivity = (acts_within_24h on proactive surfaces) / total_proactive_surfaces
```

A proactive surface is one fired by Surface Engine' tick logic (vs. one fired by Brian explicitly asking "what should I deal with today?"). Reactive surfaces are easier to make valuable — they answer a direct question. Proactivity isolates whether Surface Engine' *unprompted* judgment is good.

### 4.3 Personalization — "is dismiss rate trending below the PPP threshold?"

```
personalization_score = max(0, 1 - dismiss_rate_over_last_20 / 0.30)
```

Target: 1.0 (zero dismisses) or close. Below 0 (more than 30% dismissed) is the PPP-paper red line.

### 4.4 Calibration — "is Surface Engine' stated confidence aligned with actual act rate?"

For each dispatch, Surface Engine' decision JSON includes a confidence (implicit in the choice to send + the body language used). We bin dispatches by confidence (low / medium / high) and check whether higher confidence empirically delivers higher act rate.

A simple Brier-score-like metric:

```
calibration_error = mean over all dispatches of (surface_engine_confidence_normalized - actually_acted ? 1 : 0)²
```

Lower is better. Calibration error = 0 means Surface Engine' confidence is perfectly aligned with action probability.

---

## 5. Per-thread / per-need learning

Source: PPP's "UserVille" persona-conditioning + Inner Thoughts' continuous reasoning loop.

**V1 implementation:** Surface Engine does NOT train a model. Instead, the last 15 decisions are read from SQLite and injected into the Claude prompt verbatim. Claude reads them and adjusts its judgment per-candidate-category:

```
BRIAN'S RECENT NOTIFICATIONS AND HIS RESPONSES (newest first):
  2026-06-28 09:00 SENT "Denver proposal spots — still open?" → ACTED (took 4h)
  2026-06-27 18:00 SENT "MSP residence proof status?" → DISMISSED (took 2 minutes)
  2026-06-27 11:00 SILENT (acting threads have momentum)
  ...
```

This is the simplest possible learning loop — the LLM reads its own track record. When dispatch count exceeds ~100, we can graduate to:

**V2:** A small XGBoost-style ranker over the candidate's features (slug, state, urgency, last_movement age, time-of-day, recent-dismiss-rate-for-similar-category) → predicted act probability. Used as an input to the LLM, not a replacement.

---

## 6. The four-stage decision pipeline (Inner Thoughts mapping)

Inner Thoughts (CHI 2025, arXiv:2501.00383) defines a 5-stage loop. Surface Engine implements it as:

| Inner Thoughts stage | Surface Engine implementation |
|---|---|
| 1. Trigger | Scheduled tick (cron / `mikai-decide`) OR user-requested via CLI |
| 2. Retrieval | Read needs registry + wiki + graph recency-lens + adapters (iMessage/Calendar/Gmail) |
| 3. Thought Formation | Build the prompt, ask Claude to rank candidates and produce a decision |
| 4. Evaluation (the critical stage) | Claude applies the 4-factor `surface_priority` formula + the recent-decisions log; decides send vs silent |
| 5. Participation | Dispatch via ntfy.sh (V1) OR via Calendar.app daily brief (V1.5) OR via macOS Notification Center (V2) |

The **Evaluation** stage is where Inner Thoughts says proactive systems usually fail — they generate plausible candidates but don't gate them well. Surface Engine' V1 gate is the explicit "default to silence for noise; only surface stalled or trigger-aligned candidates" prompt instruction. This is a soft gate; the loss-function metrics measure whether the gate is well-calibrated.

---

## 7. Schema additions for V1

V0's `notification_log` already has `user_response` and `response_at`. V1 adds:

```sql
ALTER TABLE notification_log ADD COLUMN time_to_response_seconds INTEGER;
ALTER TABLE notification_log ADD COLUMN candidate_source TEXT;  -- 'needs_registry' | 'wiki' | 'graph_recency' | 'adapter_imessage' | ...
ALTER TABLE notification_log ADD COLUMN candidate_slug TEXT;    -- 'mom-scotia-credit-card', 'mikai_task_state_awareness_20', etc.
ALTER TABLE notification_log ADD COLUMN figs_confidence REAL;   -- the priority Claude assigned, 0..1
ALTER TABLE notification_log ADD COLUMN acted_within_24h INTEGER; -- 0/1, populated by a daily backfill job
```

`time_to_response_seconds` populated automatically when the CLI captures a response. `acted_within_24h` is a derived field updated by a small backfill that runs at the start of each tick (looks at all dispatches >24h old without a populated value, checks if a response came in or graph evidence emerged).

---

## 8. The CLI for response capture (V1 workaround for iOS click-tracking gap)

```
mikai mark-acted <log_id>           # mark the most recent or specified dispatch as ACTED
mikai mark-dismissed <log_id>       # mark as DISMISSED
mikai snooze <log_id> <days>        # mark as SNOOZED for N days
mikai status                        # show last 20 dispatches + their response state
mikai metrics                       # print productivity, proactivity, personalization, calibration
```

When Brian sees a Surface Engine notification and acts on it, he runs `mikai mark-acted` to close the loop. This is friction; V2 replaces it with native iOS click-tracking (Pushover or APNs) or with a Calendar.app integration where the act of opening the linked event itself signals ACTED.

---

## 9. The V2 path — when does Surface Engine need real machine learning?

Not until both are true:

1. Dispatch count ≥ 100
2. Dismiss rate over last 20 has stalled at > 0.30 despite prompt-level tuning attempts

At that point, the LLM-as-judge is provably insufficient and a small ranker (XGBoost over the per-candidate feature vector) becomes warranted. Per the predictive-layer-spec exploration (now archived as research input — see `docs/research/strategic-insights-2026-05.md`), this is the natural V2 evolution but is not warranted at V1 single-user scale.

---

## 10. What this file commits Surface Engine to

1. Surface candidates only when `surface_priority ≥ 0.5` AND `delivery_value ≥ 0.5` simultaneously
2. Never repeat a candidate in cooldown (2h default; longer for dismissed candidates)
3. Log every decision (sent OR silent) with the four-factor breakdown for later eval
4. Provide the CLI surface for response capture until a richer signal path lands
5. Re-evaluate weights and thresholds when `notification_log` reaches 50 rows and again at 100

These commitments are testable against `mikai metrics` output. If they regress, the loss function says so quantitatively, not qualitatively.

---

## References

- ProMemAssist (UIST 2025) — `docs/research/l4-papers.md` §Paper 1; arXiv:2507.21378
- OmniActions (CHI 2024) — `docs/research/l4-papers.md` §Paper 2; arXiv:2405.03901
- Inner Thoughts (CHI 2025) — `docs/research/l4-papers.md` §Paper 3; arXiv:2501.00383
- PPP / UserVille (CMU Nov 2025) — `docs/research/l4-papers.md` §Paper 4; arXiv:2511.02208
- MEMTRACK (Patronus AI NeurIPS 2025) — `docs/research/l4-papers.md` §Paper 5; arXiv:2510.01353
- Anthropic's harness pattern — `docs/research/l4-papers.md` §Anthropic; anthropic.com/engineering/effective-harnesses-for-long-running-agents
- MIKAI epistemic edge vocabulary — `docs/EPISTEMIC_EDGE_VOCABULARY.md` (state hierarchy)
- MIKAI Dream/Wiki runtime — `docs/DREAM_WIKI_RUNTIME.md` (where ## Now state assignments come from)
