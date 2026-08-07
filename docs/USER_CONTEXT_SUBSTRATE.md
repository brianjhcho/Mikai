# User-context substrate — deconstruction and rebuild from literature

*2026-08-06 · Fable 5. Brian's charge: Claude cited two-file systems (Karpathy, Hermes) and minimal-taxonomy doctrine (Matuschak, Kepano), then proposed an eight-section `USER_MODEL.md` — Values, Obsessions, Themes, Aphorisms, Ideas, Expertise, Preferences, Unresolved. Where is the literature for eight? Answer below: there isn't any. Inputs: `USER_MODEL_RESEARCH.md`, `HARNESS_ARCHITECTURE.md` §1, `RETRIEVAL_STACK.md`, `COCKPIT_CONTENT_STRATEGY.md`, `ENTITY_MODEL.md`, live `~/.mikai/brain/USER_MODEL.md`, plus the primary sources re-fetched this pass.*

## 1. Deconstruction — where the eight sections came from

Traced one by one, honestly:

- **Preferences** — grounded. Hermes' `USER.md` is exactly this: "identity, preferences, communication style, workflow habits," 1,375-char cap ([Hermes memory docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)). The one section with a direct shipped precedent.
- **Values** — half-grounded. `USER_MODEL_RESEARCH.md:91-95` imports the Big Five *stable-trait vs. situational* split, which licenses a durable **slot**. No surveyed system ships a section named Values; the header is Claude's coinage on a borrowed axis.
- **Themes** — internal, not literature. It restates MIKAI's own hydrator `themes` field ("a degenerate interest graph," `USER_MODEL_RESEARCH.md:102-104`) and half-duplicates the hubs-and-threads declaration `COCKPIT_CONTENT_STRATEGY.md` §3 already treats as canonical.
- **Unresolved** — internal. Open-loop tracking is MIKAI's product thesis (`VISION.md` §2 — the capability table says *nobody* ships it), so no external citation exists by construction. Justified by the moat, not the literature — and it shadows thread state.
- **Obsessions, Aphorisms, Ideas, Expertise** — fabrication. Nothing in the 15-tool cockpit survey, the Hermes docs, the Karpathy gist, or `USER_MODEL_RESEARCH.md` proposes any of them. Expertise directly violates Hermes' exclusion list ("re-discoverable facts" don't belong in memory). Aphorisms and Ideas are wiki content wearing a model costume — the earlier artifact-file version of this proposal was rightly rejected.

Note the drift compounds in bytes too: the research doc prescribed ~2 KB (`USER_MODEL_RESEARCH.md:111`); the shipped code quietly doubled it (`infra/mikai_brain/user_model.py:58`, `MARKDOWN_BYTE_CAP = 4000`). Two sections were grounded; the other six, and half the budget, were invented in the same gesture that cited minimalists.

## 2. What the literature actually converges on

**Bounded prose beats schema.** Karpathy's wiki is `index.md` + `log.md` + a schema doc — and *no user-model sections at all*; pages emerge from ingestion ([gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)). Hermes' two files have **no prescribed sections** — entries separated by `§`, structure free ([docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)). ChatGPT memory is a flat list of strings ([Embrace The Red](https://embracethered.com/blog/posts/2025/chatgpt-how-does-chat-history-memory-preferences-work/)). Claude Projects is human-curated files, no schema. mem.ai declares no shape at all — embedding adjacency ([mem.ai](https://get.mem.ai/blog/organize-your-notes-with-ai-using-collections)). Matuschak: no genre folders, structure emerges from links ([notes.andymatuschak.org](https://notes.andymatuschak.org/)); Kepano: file-over-app, minimal taxonomy (`ENTITY_MODEL.md` §2, §6).

**The one recurring split is durable-vs-rotating.** Hermes: `USER.md` (who the user is) vs. `MEMORY.md` (what's currently true of the environment). Karpathy: `index.md` (stable navigation) vs. `log.md` (chronology). Big Five: trait vs. state. That split is load-bearing. Nothing else recurs.

**Byte caps with error-on-overflow** are Hermes' contribution alone — 1,375 and 2,200 chars, writes that exceed the cap *error* rather than truncate (`HARNESS_ARCHITECTURE.md` §1). Everyone else converges on the softer form: small enough to inject whole.

**Compiled, not retrieved** is Karpathy's contribution: downstream reads a distilled artifact, not raw chunks. Already adopted — `USER_MODEL.md` as the compiled index of Brian is correct.

**What each rejected:** ChatGPT's any-turn writes are a proven injection attack surface ([Embrace The Red](https://embracethered.com/blog/posts/2024/chatgpt-hacking-memories/)) — rejected by MIKAI's dream-weekly-only writes. mem.ai's undeclared vector persona — rejected; nothing consumes it and one user can't be population-modeled. Hermes' silent self-edits — rejected for the consent moat (`COMPARISON.md`; `HARNESS_ARCHITECTURE.md` §1 lesson 2).

**Against MIKAI's constraints:** single-user kills recommender patterns; two consumers ask exactly two questions — *how should I answer Brian* (mikai_ask) and *what deserves attention* (Attention Engine) — which is the durable/rotating split wearing product clothes; and the wiki, threads, and entities already exist, so anything restatable from them is noise here.

## 3. Reconstruction from simple

**Position: one machine-compiled file, two sections, 2 KB.** MIKAI already has the two-file pattern: `PROFILE.md` is the hand-curated file (the Claude-Projects layer), `USER_MODEL.md` the compiled one (the Karpathy layer). The wiki is the corpus beneath both. No new files.

1. **Files: one** (`USER_MODEL.md`; `PROFILE.md` stands, unchanged). Hermes precedent: the user profile is a single file; MIKAI's analog of `MEMORY.md` is the wiki itself.
2. **Sections: two.** **Durable** — values + interaction preferences merged (Hermes `USER.md` content, verbatim category). **Current** — active themes + open loops merged (the rotating slot; MIKAI's own thesis carries the open-loop half). Every other header rejected: no source, or restatable from the substrate.
3. **Cap: 2,048 bytes, error on overflow.** Hermes' 1,375-char `USER.md` proves the register works; revert the unexplained 4,000.
4. **Cadence: dream-weekly rewrite, one reviewable diff per week** (`USER_MODEL_RESEARCH.md` lesson 5). Never ask-time writes — the ChatGPT attack surface. Git history of `~/.mikai/brain` is the `log.md` analog.
5. **Consumers:** mikai_ask injects the whole file after `PROFILE.md` (`infra/mikai_ask/core.py:284` ordering stands — 2 KB needs no retrieval). Attention Engine reads **Current** for alignment ranking; mention counts stay a tiebreaker only (lesson 4).
6. **Not in this substrate:** episodic facts → wiki; task state and next steps → threads/`BRAIN.md`; person/thing facts → `entities/`; decisions → `docs/DECISIONS.md`; quotes, ideas, expertise → wiki (re-discoverable; Hermes exclusion list); provenance → the weekly diff and compile log, not the injected file — audit is a channel, not a section.

**Migration.** KEEP: all four sections' *content*; the mikai_ask injection point; the hydrator alignment read; the weekly cadence. MERGE: Values + Preferences → **Durable**; Themes + Unresolved → **Current** — on the next dream-weekly rewrite. REMOVE: **Source signals** from the injected file (emit into the compile log / weekly diff instead — it is audit trail spending context bytes); the never-shipped Obsessions/Aphorisms/Ideas/Expertise, permanently; the 4,000-byte cap, back to 2,048. Nothing to ADD. We over-engineered by taxonomy; the fix is deletion.
