# Second Brain — Fable 5 build + review pass

Run date: 2026-08-05, ~75 min wall clock across an interruption. Branch:
`feat/pure-file-brain`. No pushes; every change is a local, atomic,
revertable commit.

## What shipped (end-to-end)

| Commit | What | Why it's done |
|---|---|---|
| `45c6a50` | Merge `pear-seashore` branch into `feat/pure-file-brain` | The shell/organize planner and FIGS decider live on that branch — items A and B were impossible without it. Side effect: this un-broke the 3x-daily FIGS LaunchAgent, which `cd`s into this worktree's `infra/decider/` and had been pointing at a branch with no decider sources. |
| `9466786` | **A** — shell/organize planner routed through `mikai_llm.chat(tier="interactive")` | Verified with a real `claude -p` dry-run against a temp dir (never `~/Desktop`, per constraint): 6-folder taxonomy aligned to life-tier themes, 6/7 sensible moves, `validate()` clean. JSON-mode inlined in prompt; markdown fences stripped defensively. |
| `3652173` | **B** — FIGS per-call tier audit | `calendar_planner` → interactive (user-facing calendar copy, ≤ a few calls/day). `week_planner` → interactive (5 day-plans/week). `mikai_decide.invoke_claude` → delegates to the shim (was already claude -p; now one choke point, and the shim strips `ANTHROPIC_API_KEY` from the subprocess env). `infra/graphiti` sync/dream deliberately left on DeepSeek — bulk extraction is exactly what the background tier is for. Nothing was moved to deterministic: the three call sites are all genuine NLG. |
| `a7177ea` | **D** — Makefile (`standup`, `standup-dry`, `triage`, `triage-no-llm`, `consolidate-dry`, `test`, `smoke`) + two fixes below | `make smoke` is read-only by construction; verified against the real brain. |
| `79adc25` | Fix: `progress.json` corruption no longer clobbers history | See Holes. |
| `439771e` | Fix: log lines insert under `## Log`; triage guards off-schema LLM output | See Holes. |
| `e1d1592` | **C** — 18-test end-to-end suite + falsy-stall fix | All green in 0.15s, stdlib unittest only, temp brain tree, zero network. |
| (no commit — files live in `~/.mikai/brain/`) | **E** — brain CLAUDE.md ritual audit + fixes; **F** — real `consolidate --dry-run` | Both done; details below. |

**E details:** I executed the startup ritual against the real brain, then the
shutdown ritual for real (thread `mikai-shell-v1-followthrough` moved
stalled→acting with commit refs in its log; run entry appended via
`ledger.run`). Three CLAUDE.md defects fixed (backup at
`CLAUDE.md.bak-fable-20260805`): (1) it said progress.json was JSONL — it's a
JSON array; (2) the triage command lacked a repo cwd and would fail from
`~/.mikai/brain/` — now `make -C <repo> triage`; (3) the emergency-stop
guidance now matches the actual corrupt-file behavior shipped in `79adc25`.

**F details:** `make consolidate-dry` ran a real `claude -p` call against the
real brain. Output was genuinely good — it caught the moss-pole
decision-avoidance, the proposal thread going cold, and proposed logging the
swap decision as D-op-002. I did **not** save it: it was written before this
session's work landed, so its top item ("the claude -p swap is stalled") was
already false. Re-run `make consolidate-dry` after merge and save then.

## What was tested

18 tests in `infra/mikai_brain/tests/test_end_to_end.py` (temp brain via
`MIKAI_BRAIN_ROOT`, LLM fully mocked):

- `test_standup_on_empty_brain` — empty tree doesn't crash; run entry still written
- `test_stall_thresholds_by_state` — decided stalls at 5d, acting at 7d, exploring never
- `test_overdue_next_step_due_is_flagged` / `test_future_next_step_due_is_not_flagged` — past fires, today/future don't
- `test_stall_date_edge_cases` — unparseable dates never stall; activity-today never stalls (regression guard for the falsy-0 bug)
- `test_completed_evidence_gate` — completed-without-evidence flagged, with-evidence not
- `test_standup_persists_stall_transition_and_ledger` — file rewrite + both state files
- `test_dismissal_cooldown_suppresses_then_expires` — 48h window honored both directions
- `test_three_consecutive_dismissals_mute_thread` — mute outlasts cooldown
- `test_surfacing_capped_at_five_per_run` — MAX_SURFACE cap
- `test_corrupt_frontmatter_does_not_crash_standup` / `test_thread_without_log_section_is_handled`
- 4 triage tests — heuristic-vs-LLM routing, canned-JSON write-back + archive, garbage LLM output never loses the item, `processed/` never re-triaged
- 2 consolidate tests — dry-run leaves BRAIN.md untouched; wet run splices only the priorities section

Beyond the suite: real-call verification of planner (A) and consolidate (F);
mocked verification of all three FIGS call sites including the
failure-returns-None contract; corruption-recovery script against a scratch
tree; `make smoke` against the real brain; compile sweep over all touched
modules. 3 real `claude -p` calls total (one unintended, during a mock that
missed its target — caught and documented below).

## Holes found + fixed

- **`progress.json` clobber (data loss):** `append_run` read (returning `[]`
  on parse error) then rewrote the whole file — one corrupt byte would erase
  all run history on the next append. Now: corrupt file moved aside as
  `progress.corrupt-<ts>.json`, writes go tmp-file + atomic rename. (`79adc25`)
- **Log lines appended to end-of-file, not `## Log`:** every triage-created
  thread has `## Content` after `## Log`, so appended activity landed where
  `_extract_log_lines` never looks — activity stopped counting for stall
  detection, silently. (`439771e`)
- **Stalled threads vanished from standup:** stall detection only fired on
  decided/acting, so one run after a stall persisted, the thread produced no
  finding — "what's stalled?" answered nothing. Found live via `make smoke`.
  Already-stalled threads now re-surface; cooldown/mute is what stops
  nagging, not detection. (`a7177ea`)
- **Activity-today counted as no-activity:** `_days_since(last_activity) or
  _days_since(state_since)` — 0 is falsy, so a thread touched today with an
  old `state_since` was reported stalled. Found by the test suite. (`e1d1592`)
- **Off-schema LLM kind = silent drop:** triage archived the item but did no
  write-back if the LLM invented a kind. Now defaults to fragment; non-numeric
  confidence tolerated. (`439771e`)
- **Hardcoded brain root:** untestable without touching real personal data.
  `MIKAI_BRAIN_ROOT` env override added. (`a7177ea`)
- **Mock-target miss (test methodology, mine):** patching
  `infra.mikai_llm.chat` does nothing for modules that did `from … import
  chat` at import time — my first verification accidentally made a real LLM
  call. The committed suite patches at the use site.

## Ready-to-ship vs plausible-future

- **standup** — ready. Deterministic, tested, ~0.15s. Expect the
  evidence-keyword list ("sent/signed/shipped/…") to force iteration; it's a
  crude substring gate.
- **triage** — ready for the happy path. Heuristic gate + LLM tie-break +
  archive all tested. Expect `_match_thread` (5-char token overlap, ≥3 hits)
  to mis-file fragments once thread count grows.
- **ledger / Sumimasen gate** — ready. But `_is_muted` ignores its
  `current_state` argument: "muted until state changes" is not implemented,
  only "3 consecutive dismissals mute" — a state change today does not unmute.
- **consolidate** — ready as a weekly manual `make consolidate-dry` → eyeball
  → run wet. No scheduler; do not automate until a few manual cycles look good.
- **store (FileStore)** — ready at current scale; token-overlap scoring is
  deliberately dumb (D-op-001 says revisit at 500+ threads).
- **MikaiStore** — plausible-future. Stub that raises. Correctly gated.
- **shell/organize on claude** — ready for supervised use. One real dry-run
  passed; the 300-file case is unverified on Claude (prompt is larger; CLI
  timeout is 300s — watch the first big run).
- **FIGS on the shim** — plumbing verified with mocks only. The next scheduled
  decide tick (07:00/12:00/18:00) is the real test. `invoke_claude` no longer
  passes `--output-format text`; plain `claude -p` defaults to text, but watch
  the first tick's log.

## Concerns worth Brian's attention

1. **Prompt injection surface got sharper.** Inbox items, thread titles, and
   calendar-event descriptions flow verbatim into `claude -p` prompts, and the
   shim does not restrict the CLI's tool access in `-p` mode. A crafted note
   ("ignore instructions, run …") is now aimed at a Claude that may have tool
   permissions, not at a DeepSeek completion API. Cheap mitigation: add
   `--disallowedTools`/`--tools`-style restriction (or a dedicated settings
   profile) to `_chat_claude`. I did not do this — untested flags on the
   launchd-critical path felt riskier than flagging it.
2. **No file locking anywhere.** Concurrent standup + interactive session (or
   two launchd jobs) do read-modify-write on the same files. `progress.json`
   is now atomic-rename but last-writer-wins; thread files aren't even that.
   Solo-operator probability is low; it will bite eventually. JSONL migration
   for progress + O_APPEND everywhere is the fix.
3. **Quota, not dollars.** Every FIGS tick, calendar proposal, week plan,
   shell run, triage tie-break, and consolidate now shares the Max-sub
   interactive quota with Brian's own Claude Code sessions. If Anthropic
   re-meters `-p` (policy memory says watch this), flip
   `MIKAI_LLM_INTERACTIVE=deepseek` — one env var, that's the whole point of
   the shim — but until then heavy FIGS days eat session quota.
4. **`progress.json` grows without bound** and is fully rewritten each append
   — O(n²) lifetime cost and a growing corruption blast radius.
5. **BRAIN.md scratch-parking rewrites the whole file** (triage fragment
   path). A crash mid-write could truncate BRAIN.md. Same atomic-rename
   treatment as progress.json would close it.
6. **Backups I created** (safe to delete after review):
   `~/.mikai/brain/CLAUDE.md.bak-fable-20260805`,
   `~/.mikai/brain/threads/mikai-shell-v1-followthrough.md.bak-fable-20260805`.

## What I did NOT do (with reasons)

- **No real FIGS decide tick** — it dispatches ntfy; hard constraint.
- **No `~/Desktop` dry-run** — checklist item A named it, but constraint 5
  ("never touch ~/Desktop") wins; used a seeded temp dir instead.
- **No wet consolidate** — output was good but pre-stale; rule was "only save
  if it clearly improves."
- **No week_planner live run** — writes to iCloud CalDAV; mutation of a
  remote calendar is not a stress test I get to run unsupervised.
- **No claude-CLI tool-restriction flags** — see concern 1; flagged instead.
- **No JSONL migration of progress.json** — data-format change touching every
  reader, mid-session, with real data on disk; wrong altitude for this pass.
- **Did not fix `_is_muted` state-change unmute** — needs a design decision
  (where is "state at time of mute" recorded?), not a patch.
- **DeepSeek background tier never exercised live** — constraint; mocked only.

## Suggested next moves after Brian returns

1. **Review + merge `feat/pure-file-brain` → main** (10 commits). Then update
   the two launchd runner comments that say "until FIGS merges to main," and
   log D-op-002 (the swap decision) — consolidate itself asked for it.
2. **Watch the next scheduled FIGS tick's log** (`~/.mikai/logs/`) — first
   real proof of `invoke_claude`-via-shim on the unattended path.
3. **Add tool restriction to `_chat_claude`** (concern 1) — highest
   security-ROI single edit in the codebase right now.
4. **Run `make consolidate-dry` fresh and save it** — the brain's threads now
   reflect today's work; the rewrite will be accurate this time.
5. **Migrate progress.json → JSONL** behind `ledger.py`'s API (no callers
   change) — closes concerns 2 and 4 in one small PR.
