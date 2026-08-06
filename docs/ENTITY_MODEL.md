# MIKAI Entity Model

Convention for `~/.mikai/brain/entities/`. Entities are what threads share; cross-thread
"entangled with" edges in the cockpit are drawn only when two threads list the same entity.

## 1. Definition

An **entity** is a specific, recurring **person, org, thing, or place** that exists
independently of any one thread: `bethany`, `monstera`, a jeweler, the loft. Never an
abstract concept, state, or judgment — "important", "wip", "urgent" are not entities.

Contrast with the two other axes threads already have:

- **`department`** (body, love, domestic, ai_work) — coarse routing, one per thread.
- **Tags** (if ever added) — flat descriptive keywords, cheap, no identity.
- **Entities** — have identity and accumulate facts. Tana's test applies: tag a node
  only if "**is a**" holds ("Marisha *is a* person"). If the candidate is a description
  rather than a thing, it's a tag, not an entity.

## 2. Naming rules

- **kebab-case slug = filename** (`moss-pole.md` → entity `moss-pole`). Kepano's
  file-over-app convention: the file *is* the entity; plain markdown, no app-side registry.
- **Singular** (`chair`, not `chairs`) — Tana supertag convention (`#person`, `#meeting`).
- **No prefixes** (`bethany`, not `person-bethany` or `@bethany`). Type lives in
  frontmatter, not the name — Anytype's Object model: type is a property of the object.
- **People: first name only** (`bethany`), promote to `first-last` only on collision.
  Zep/Graphiti resolves duplicates by matching candidates against existing entities;
  file-first MIKAI does the same manually — shortest unambiguous name wins.

## 3. Entity file schema

Exemplar: `~/.mikai/brain/entities/bethany.md`.

```yaml
---
name: bethany            # = slug = filename
type: person             # person | org | thing | place
status: active           # active | dormant
owner_thread: proposal-timing   # thread that "owns" it most; optional
---
```

Body: one paragraph of **first-person facts** worth remembering across sessions —
preferences, constraints, history. Not a biography. Threads point at entities via
`entities: [...]` frontmatter (Kepano's links-in-properties pattern); entity files
never list threads back — one direction, no sync problem.

## 4. When to promote a name to an entity

Promote when it **appears in ≥ 2 threads, or clearly will** (named in
`life-tier.json` filters, or the concrete subject of an active thread). Otherwise
leave it as prose. Under-promotion is cheap to fix; over-promotion creates hub
entities that edge every thread to every thread — noise, the Roam hairball.

## 5. Prior art

| Tool | Entity handling |
|---|---|
| **Tana** | Typed supertags + fields; "is a" test; singular names; no graph view — views over structure. |
| **Anytype** | Everything is an Object with a Type; Sets = live queries over objects. |
| **Obsidian (Kepano)** | Entity = a note; membership via wikilinks in frontmatter properties; tags stay flat. |
| **Zep/Graphiti** | LLM entity extraction + resolution against existing nodes; typed via Pydantic models; bitemporal facts. |
| **Notion** | Entities = database rows with typed properties; relations link databases. |
| **Roam/Logseq** | Any `[[page]]` is an entity — zero friction, hub-noise hairball; the cautionary case. |
