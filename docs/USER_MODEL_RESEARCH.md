# User Modeling Research — for MIKAI's dreaming layer

_Written 2026-08-06 before adding `mikai_brain/user_model.py`. Frames the
question: **how should MIKAI build "a real model of Brian" from the
substrate?** Not from mention frequency, but from what the substrate
means as a whole. This doc reviews prior art (LLM-era + pre-LLM) and
extracts 5 concrete design lessons for a single-user personal system._

## Motivation — why the frequency filter is wrong

Today `hydrator.py` (and the planned latent-thread detector) rank
substrate candidates by mention count with a `min_mentions >= 5`
threshold (once floated to 30). That treats "importance" as
"repetition", which:

- surfaces framework/tooling noise ("claude-md", "python") that has high
  mention count but zero life-signal;
- buries dormant-but-load-bearing threads (dry-eye ophthalmology
  research, plant care, the China proposal) that are heavily-weighted
  in Brian's attention but only show up in a handful of sections;
- can't distinguish *what he cares about* from *what happens to be
  loud in the substrate this week*.

Brian's real ask is that the dreaming loop **build a real model of him
as a person** — his values, his open loops, the way he prefers to work —
and use that model to gate what surfaces.

## Prior art, LLM-era

### Nous Research — Hermes Agent `USER.md` (2026)
Hermes keeps three memory kinds under `~/.hermes/`: episodic (SQLite
FTS5 of conversations), semantic (`MEMORY.md` + `USER.md`, curated), and
procedural (auto-generated skill files). `USER.md` is a bounded,
LLM-editable file of user facts and preferences that gets injected into
every session. Key design: **the LLM edits its own memory with typed
ops** rather than rewriting the file blindly, which stops runaway
growth and lets a diff be reviewed. First release Feb 25 2026; still
shipping (v0.18.2, July 7 2026). [1][2]

### OpenAI — ChatGPT Saved Memories (Feb 2024)
Saved memories are opaque short strings sitting in a "Model Set
Context" section of the system prompt. They're injected into every
chat until deleted. Two lessons: (a) even short structured memories
change model behavior noticeably; (b) prompt injection can *write* to
this store from untrusted content — real vulnerability
class ("remember that…" attacks land at 100% ASR). [3][4]

### Anthropic — Claude memory / Projects
Project files sit above every message like a lightweight `USER.md`.
Not personalized per-user; the human curates.

### Character.AI, Replika — three-layer memory
Layer 1 character definition, Layer 2 user persona ("who the user
is"), Layer 3 rolling conversation. Layer 2 is a bounded fact sheet;
some systems also do post-conversation summarization into a vector
store. Long-term-memory persona files that "mirror the user" are the
Replika direction. [5]

### Karpathy — LLM Wiki (Apr 2026)
Not about user modeling directly, but the meta-lesson applies:
**knowledge is compiled, not retrieved**. The wiki is written to and
maintained over time by the LLM, so downstream queries read a
distilled artifact instead of retrieving raw chunks. Applying that to
user modeling: a `USER_MODEL.md` rebuilt periodically from the whole
substrate is the compiled artifact; every ask reads *that*, not raw
sections. [6]

### Rewind / Limitless
Screen + audio captured continuously; a persistent user
representation emerges implicitly from embeddings. Different bet — no
declared, human-legible user model, just retrieval over everything.

### Mem.ai
Note capture with implicit clustering; the user model is
embedding-space adjacency, not a declared shape.

## Prior art, pre-LLM

### Collaborative filtering (Netflix, Spotify)
Users as latent vectors learned from behavior. Depends on population
data — irrelevant for a single-user system (no crowd to filter
against). Lesson kept: **behavior beats stated preference**; look at
what Brian did (which threads he answered, which drafts he shipped),
not what he claims to want. [7]

### Product/design personas (IDEO)
Hand-authored one-page composite users. Analogous to `PROFILE.md`
today. Weakness: static; doesn't update as the person changes.

### Big Five personality
Five dimensions from behavioral traces. Useful as *shape*, not as
targets — MIKAI shouldn't try to score Brian on Openness. But the
"stable trait vs situational preference" split is useful: some
`USER_MODEL.md` entries are near-permanent (values), others rotate
(current themes, unresolved loops).

### Bayesian preference elicitation
Ask the user informative questions to narrow uncertainty. Elegant but
over-engineered here — MIKAI already has abundant passive signal.
Reserve for a later pass. [8]

### Interest graphs (Pinterest, Facebook)
Explicit topic membership edges. MIKAI's `themes` field is a
degenerate interest graph — a flat list of topic labels.

## Five lessons distilled for MIKAI

1. **Compile a bounded, human-legible `USER_MODEL.md`** — Karpathy +
   Hermes. Rebuild periodically; injectable in every downstream call.
   Byte-cap it (~2 KB) so it can't silently balloon; overflow errors,
   doesn't truncate.
2. **Split near-permanent from rotating** — Big Five's stable-vs-
   situational split. Values and preferences drift slowly; themes and
   unresolved loops rotate. One dataclass, distinct fields.
3. **Behavior beats stated preference** — collaborative filtering. Weight
   what Brian did (threads with logged decisions, entities he
   promoted) above what he said. `source_signals` records provenance
   so promotions are auditable.
4. **Ranker consults the model, not the mention count** — the
   frequency filter is a floor, not a signal. Downstream (latent
   threads, hydrator) score candidates by *alignment with themes* and
   only fall back to counts as a tiebreaker.
5. **Weekly, not nightly, and never surprise-inject** — Hermes writes
   `USER.md` inline; ChatGPT surprise-writes on any turn (attack
   surface). MIKAI rebuilds `USER_MODEL.md` weekly on the same
   `dream-weekly` cron, so drift is one-diff-per-week and reviewable.

## What we're deliberately not building

- No embedding-space user vector — nothing consumes it, and one user
  can't be recommender-modeled from population data.
- No Big Five scoring — over-engineered, wrong altitude.
- No active preference elicitation — enough passive signal exists.
- No auto-write from ask-time context — that's the ChatGPT-memory
  attack surface. Writes happen only from `dream-weekly`.

## References

1. [Hermes Agent: Self-Hosted AI That Never Forgets You (2026)](https://www.aibuilderclub.com/blog/hermes-nous-research-self-improving-agent)
2. [Hermes Agent: The Practitioner's Reference (2026)](https://blakecrosley.com/guides/hermes)
3. [How ChatGPT Remembers You — Embrace The Red](https://embracethered.com/blog/posts/2025/chatgpt-how-does-chat-history-memory-preferences-work/)
4. [ChatGPT: Hacking Memories with Prompt Injection — Embrace The Red](https://embracethered.com/blog/posts/2024/chatgpt-hacking-memories/)
5. [Character.AI Memory: How It Works and How to Make It Stick](https://konshus.ai/character-ai-memory-guide)
6. [Karpathy's LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
7. [Netflix recommendation architecture deep dive](https://dzone.com/articles/a-deep-dive-into-recommendation-algorithms-with-ne)
8. [Bayesian Preference Elicitation with Language Models (arXiv 2403.05534)](https://arxiv.org/abs/2403.05534)
