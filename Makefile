# MIKAI Second Brain — operator shortcuts.
# All targets run from the repo root against ~/.mikai/brain/ unless
# MIKAI_BRAIN_ROOT is exported to point elsewhere.

PY := python3

.PHONY: standup standup-dry triage triage-no-llm consolidate-dry test smoke cockpit

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

test:
	$(PY) -m unittest discover -s infra/mikai_brain/tests -t . -v

# Second Brain constellation view: writes state/dashboard.json + cockpit.html.
cockpit:
	$(PY) -m infra.cockpit.main

# Read-only health check: no state writes, no LLM calls, no file moves.
smoke:
	$(PY) -m infra.mikai_brain.standup --dry-run
	$(PY) -c "import sys; sys.path.insert(0, '.'); \
	from infra.mikai_brain.store import make_store; \
	hits = make_store().recall('proposal'); \
	print('smoke: store.recall ok —', len(hits), 'hit(s)'); \
	from infra.mikai_brain import ledger; \
	print('smoke: ledger ok —', len(ledger.read_events()), 'delivery event(s),', len(ledger.read_runs()), 'run(s)')"
