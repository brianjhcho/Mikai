"""mikai_ask — free text in, substrate-grounded answer out.

The read path where an arbitrary question is answered *through* the
substrate instead of around it (docs/COCKPIT_INPUT_FEATURE.md §4).
One command: retrieve — FTS5 top-k over the wiki, entity-slug matches
against brain/entities/, active-thread frontmatter, BRAIN.md priorities
head, PROFILE.md — compose one prompt, call mikai_llm.chat(tier=
"interactive"), print the answer, log a mode="ask" row to
progress.jsonl (seed corpus for §3.iii's proposal pass and §5's
probe-miss evidence).

Out of scope, per the design doc: acting on the answer (mikai_exec),
ambient capture, silent profile learning. The cockpit textarea comes
only after ~2 weeks of CLI use (§5).
"""
