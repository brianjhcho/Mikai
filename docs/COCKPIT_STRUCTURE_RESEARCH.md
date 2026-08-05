# Cockpit structure research — presenting a personal Second Brain as HTML

*2026-08-05 · Research pass only, nothing built. Inputs: the anatomy plate (Plate I), the cosmology portrait, the live cockpit at `~/.mikai/brain/cockpit.html`, and the ecosystem survey below.*

## 1. Wider ecosystem

One line each: visual metaphor / interaction / what it privileges.

1. **Obsidian graph view** — force-directed hairball of all notes; the *local* graph (n-hop from current note, auto-updating in a sidebar) is the part people actually use; privileges link discovery over state. [thesweetsetup.com](https://thesweetsetup.com/the-power-of-obsidians-local-graph/)
2. **Roam Research graph overview** — spider network, "brick-like," near-zero interaction beyond zoom; widely judged decorative; privileges the *idea* of connection. [alvistor.com](https://alvistor.com/comparing-roamresearch-graph-view-with-logseq-obsidian-and-others/)
3. **Logseq graph** — same metaphor but filterable by tag and n-hop depth; privileges exploratory browsing. [alvistor.com](https://alvistor.com/comparing-roamresearch-graph-view-with-logseq-obsidian-and-others/)
4. **Andy Matuschak's notes** — no map at all: sliding stacked panes that preserve the reading trail; privileges the *path*, not the territory. [notes.andymatuschak.org](https://notes.andymatuschak.org/)
5. **Nick Milo LYT / Ideaverse** — hand-curated Home note + Maps of Content; explicit thesis that curated maps beat auto-generated graphs. [blog.linkingyourthinking.com](https://blog.linkingyourthinking.com/ideaverse-map)
6. **Tiago Forte PARA** — four folders on an actionability gradient (Projects→Areas→Resources→Archives); ships no visualization; privileges retrieval-by-actionability. [fortelabs.com](https://fortelabs.com/blog/para/)
7. **Tana** — a true typed graph (supertags + fields) that deliberately ships **no graph view**: the same substrate rendered as table, cards, calendar; privileges structured views over portraits. [tana.inc](https://tana.inc/classic/knowledge-graph), [tana.inc/views](https://tana.inc/views)
8. **Anytype** — everything-is-an-Object plus Sets (live queries over the graph) plus a graph view; privileges typed structure with query-defined slices. [doc.anytype.io](https://doc.anytype.io/anytype-docs/getting-started/sets)
9. **RemNote** — global knowledge graph wired to spaced repetition; privileges memorization, the graph is secondary. [help.remnote.com](https://help.remnote.com/en/articles/8771354-knowledge-graph)
10. **Reflect** — "Map" of backlinked notes, pitched for finding orphans; privileges frictionless capture over structure. [reflect.app](https://reflect.app/blog/rise-of-networked-note-taking)
11. **Mem** — no map at all; AI surfaces related notes contextually and auto-groups Collections; privileges ambient recall, zero user-facing structure. [get.mem.ai](https://get.mem.ai/blog/organize-your-notes-with-ai-using-collections)
12. **Kortex** — three-pane writing cockpit (sources left, canvas center, panels right); privileges output production, not state awareness. [kortex.co](https://www.kortex.co/)
13. **Karpathy's LLM Wiki** (Apr 2026) — agent-maintained markdown wiki with `index.md` + `log.md`; the memory artifact is *navigable and inspectable*; privileges legibility of what the machine knows. [gist (LLM Wiki v2)](https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2), [toolmesh.ai](https://www.toolmesh.ai/news/karpathy-llm-wiki-personal-knowledge-management)
14. **Claude live-artifact personal dashboards** (2026 wave) — persistent single-file HTML dashboards refreshed from connected services; the cockpit's closest cousins; privilege convenience aggregation, not state semantics. [chatprd.ai](https://www.chatprd.ai/how-i-ai/workflows/how-to-build-a-live-auto-updating-personal-dashboard-with-claude)
15. **Notion databases** — one database, many views (table/board/timeline); same "substrate ≠ view" convergence as Tana. *Cited from general knowledge; not fetched this pass.*

**Verification note.** Alassafi's "137 skills / 7 AI directors" screens could not be located by web search (Instagram-native, not indexed); everything below relies on Brian's structural description of them. **Blunt finding:** nothing surveyed renders *task state*. Every tool visualizes either notes-and-links or aggregated metrics. A state machine (exploring→decided→acting→stalled) drawn as a living portrait is something the current cockpit already does that none of these ship. The two recurring ecosystem lessons: global graphs decay into hairballs — scoped/local graphs survive; and mature tools converge on "one substrate, many views."

## 2. Personal vs. company display

**Transfers well:**

1. **Map + reading pane.** Radial hubs with a left detail panel on selection beats every surveyed graph-with-tooltips. Selection opens *prose*, not a popup. Already adopted; keep it.
2. **Fixed schema per node.** Alassafi's chip vocabulary (BREAKS INTO / WIRED INTO / BUILDS ON) works because every node answers the same questions. The personal analog — every thread answers *state / since when / next step / why surfaced* — is the right discipline and the cockpit's panel already approximates it. Formalize, don't improvise per thread.
3. **One payoff axis, legible at a glance.** The company map color-codes the autonomy ladder so the whole screen reads as "how far along is the org." The transferable move is *a single progressive axis encoded in node styling* — for MIKAI that axis is state (hollow→solid→pulsing→warm), already implemented.

**Doesn't transfer — needs a different affordance:**

1. **Departments as silos → dimensions that leak.** An org chart is *designed* so departments don't share internals. A life's dimensions share entities constantly — Bethany exists in Love and in the calendar; posture exists in Body and in AI Work sessions. Hub-and-spoke structurally forbids expressing this. The personal shape needs **cross-hub edges**, which the company shape cannot have without admitting its departments are fake.
2. **The autonomy ladder → the wrong telos.** HUMAN-LED→FULLY AUTONOMOUS is a payoff axis because a company *wants* to automate its processes. Nobody wants to automate proposing to Bethany. The personal axis is progression toward **resolution** (exploring→decided→acting→done), and critically it runs *both directions* — stalling is a first-class regression signal. The ladder has no slot for going backward; a personal display without stall semantics is lying.
3. **Skills as permanent inventory → threads are mortal.** "137 skills" is a count that only goes up; accumulation is the point. Threads end. A personal cockpit needs affordances for **closure and decay** — archive states, dimming with staleness, resolved threads leaving the sky — not an ever-growing capability tree. A rising thread count is a pathology signal, not a KPI.

## 3. Recommendation: cross-thread entity edges ("entangled with")

**The upgrade.** When two threads share an entity, draw the edge — but scoped, never global: edges render only on hover/selection (the Obsidian local-graph lesson), curved, labeled with the shared entity; the detail panel gains one row: **ENTANGLED WITH** — the personal answer to WIRED INTO, pointing at *other threads* rather than at tools.

```
     BODY                          AI WORK
   ● breathing ─┐              ┌─ ● shell-v1
                └── SURFACE ───┘
                    (MIKAI)
                   /        \
   LOVE  ◌ proposal-timing   ◌ calendar-sync  SIGNAL
           ╰╌╌╌╌╌ bethany ╌╌╌╌╌╯   ← appears on hover only
   ┌────────────────────────────┐
   │ PROPOSAL — TIMING · exploring · 36d       │
   │ NEXT  venue shortlist × her availability  │
   │ ENTANGLED WITH  calendar-sync (bethany)   │
   └────────────────────────────┘
```

**Cost, honestly.** The data already exists: thread frontmatter carries `entities:` (verified — `proposal-timing.md` has `entities: [bethany]`). The T2 generator adds ~10 lines to emit them into `dashboard.json`; the cockpit adds edge derivation + SVG curves + hover gating, ~100–150 lines. One focused day. The *real* cost is upstream hygiene: `entities/` holds one file today, and edge density is only as good as frontmatter discipline — one or two edges now, correct for a four-thread sky, compounding as the brain grows.

**Why it beats the alternatives.** The ladder duplicates the state axis MIKAI already encodes (§2.2). MAP/DASHBOARD/CHART toggles add chrome and drag toward exactly the productivity dashboard the cockpit must not become — Tana proves views are for work surfaces, not portraits. The heatmap strip and next-step leaderboard re-aggregate information already visible in node styling and panels. "Wired into" sources is provenance — audit, not structure. Cross-thread edges are the only option that adds *information currently invisible* — that two parts of your life hinge on the same thing — and the only one no surveyed tool can copy, because it requires an entity layer underneath. MIKAI has an L3; the cockpit should look like it.

## 4. Sources

- https://thesweetsetup.com/the-power-of-obsidians-local-graph/
- https://alvistor.com/comparing-roamresearch-graph-view-with-logseq-obsidian-and-others/
- https://notes.andymatuschak.org/
- https://blog.linkingyourthinking.com/ideaverse-map
- https://fortelabs.com/blog/para/
- https://tana.inc/classic/knowledge-graph · https://tana.inc/views
- https://doc.anytype.io/anytype-docs/getting-started/sets
- https://help.remnote.com/en/articles/8771354-knowledge-graph
- https://reflect.app/blog/rise-of-networked-note-taking
- https://get.mem.ai/blog/organize-your-notes-with-ai-using-collections
- https://www.kortex.co/
- https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2 · https://www.toolmesh.ai/news/karpathy-llm-wiki-personal-knowledge-management
- https://www.chatprd.ai/how-i-ai/workflows/how-to-build-a-live-auto-updating-personal-dashboard-with-claude
- Local evidence: `~/.mikai/brain/state/dashboard.json`, `~/.mikai/brain/threads/proposal-timing.md` (entities frontmatter), `~/.mikai/brain/cockpit.html`
- Not verifiable by search: Alassafi's Instagram screens (described secondhand); Notion database views (general knowledge).
