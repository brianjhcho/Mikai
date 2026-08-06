# MIKAI Second Brain — operator shortcuts.
# All targets run from the repo root against ~/.mikai/brain/ unless
# MIKAI_BRAIN_ROOT is exported to point elsewhere.

PY := python3

.PHONY: standup standup-dry triage triage-no-llm consolidate-dry consolidate consolidate-brain-md test test-writeback test-exec smoke cockpit install-consolidate-cron install-dream-crons act act-dry

standup:
	$(PY) -m infra.mikai_brain.standup

standup-dry:
	$(PY) -m infra.mikai_brain.standup --dry-run

triage:
	$(PY) -m infra.mikai_brain.triage

triage-no-llm:
	$(PY) -m infra.mikai_brain.triage --no-llm

# Real interactive-tier LLM call; prints the rewrite, never saves.
consolidate-dry:
	$(PY) -m infra.mikai_brain.consolidate --dry-run

# Weekly-consolidate manual invocation. Default target=inbox: writes to
# ~/.mikai/brain/inbox/proposed-priorities-<date>.md for triage to fold in.
consolidate:
	$(PY) -m infra.mikai_brain.consolidate

# Autonomous overwrite path — use only after you've calibrated trust from
# N weeks of accurate inbox proposals.
consolidate-brain-md:
	$(PY) -m infra.mikai_brain.consolidate --target=brain-md

test: test-writeback test-exec
	$(PY) -m unittest discover -s infra/mikai_brain/tests -t . -v

# SPEC §5.1 write-back tests for the action scenarios (shell organize,
# calendar planner, week planner). All I/O mocked; brain in a temp dir.
test-writeback:
	$(PY) -m unittest discover -s infra/mikai_shell/tests -t . -v

# Second Brain constellation view: runs standup first (deterministic
# heartbeat — writes state transitions, delivery events) then rebuilds
# dashboard.json + cockpit.html. Opening the cockpit IS the heartbeat.
cockpit:
	$(PY) -m infra.mikai_brain.standup --quiet
	$(PY) -m infra.cockpit.main

# Copy runner + plist into ~/Library/Application Support/mikai/launchd/
# and launchctl load. Idempotent: unloads first if already installed.
install-consolidate-cron:
	bash infra/decider/launchd/install-consolidate-cron.sh

# Dream crons: weekly ontology rebuild (Sun 06:00) + monthly wiki
# compaction (1st 05:00). See docs/DREAM_CRONS.md. Idempotent.
install-dream-crons:
	bash infra/decider/launchd/install-dream-crons.sh

# Executor-layer tests: LLM, dialogs, and subprocess spawns all mocked.
test-exec:
	$(PY) -m unittest discover -s infra/mikai_exec/tests -t . -v

# Act on a surfaced thread end-to-end: propose → approve dialog → execute
# through a scoped channel → write back. Example:
#   make act SLUG=proposal-timing TYPE=message
act:
	$(PY) -m infra.mikai_exec --slug=$(SLUG) --type=$(TYPE)

# Same, but stops after printing the proposal — no dialog, no execution,
# no state writes.
act-dry:
	$(PY) -m infra.mikai_exec --slug=$(SLUG) --type=$(TYPE) --dry-run

# Read-only health check: no state writes, no LLM calls, no file moves.
smoke:
	$(PY) -m infra.mikai_brain.standup --dry-run
	$(PY) -c "import sys; sys.path.insert(0, '.'); \
	from infra.mikai_brain.store import make_store; \
	hits = make_store().recall('proposal'); \
	print('smoke: store.recall ok —', len(hits), 'hit(s)'); \
	from infra.mikai_brain import ledger; \
	print('smoke: ledger ok —', len(ledger.read_events()), 'delivery event(s),', len(ledger.read_runs()), 'run(s)')"
