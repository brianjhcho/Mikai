# MIKAI — The AI That Knows What You're Stuck On

MIKAI is a local-first intent intelligence engine. It ingests your notes, conversations, emails, and messages, builds a structured knowledge graph with typed reasoning relationships, and exposes it to Claude Desktop via MCP. The result: every AI conversation knows what you're working through, what tensions you're holding, and where your thinking has stalled.

No other tool does this today.

---

## What MIKAI Does

Most AI memory tools store what you said. MIKAI infers what you mean.

When you ask Claude "what tensions am I holding about my company?", MIKAI retrieves not a list of documents but a *reasoning map* — concepts connected by typed edges like `contradicts`, `unresolved_tension`, and `partially_answers`. Claude sees the structure of your thinking, not just the content.

**8 MCP tools available to Claude:**

| Tool | What it does |
|------|-------------|
| `get_brief` | ~400-token context snapshot injected at conversation start |
| `search_knowledge` | Semantic search over 25K+ condensed passages |
| `search_graph` | Graph traversal — seed nodes + 1-hop edge expansion |
| `get_tensions` | Your top unresolved tensions, ranked by connectivity |
| `get_stalled` | Desires and projects that have gone quiet |
| `mark_resolved` | Tell the system something is done |
| `add_note` | Save an insight from the current conversation |
| `get_status` | Knowledge base health check |

---

## Getting Started (5 minutes)

### Prerequisites

- macOS
- [Node.js](https://nodejs.org/) v20+
- [Claude Desktop](https://claude.ai/download) with MCP enabled
- [Anthropic API key](https://console.anthropic.com/) (you already have this if you use Claude Desktop)

### Step 1: Install and set up

```bash
npx @chobus/mikai init
```

This creates a local database, downloads the embedding model (~130MB, one-time), and prints the Claude Desktop config to copy-paste. No cloud accounts needed — everything runs on your machine.

### Step 2: Sync your notes

```bash
npx @chobus/mikai sync
```

Ingests your Apple Notes automatically. Or drop any `.md`, `.txt`, or `.json` files into `~/.mikai/import/`.

### Step 3: Build the graph

```bash
npx @chobus/mikai build
```

Extracts your intent graph (concepts, tensions, decisions, questions) + searchable segments + stall scores. Uses Claude Haiku (~$0.01 per note).

### Step 4: Connect Claude Desktop

Copy the config JSON that `init` printed into `~/Library/Application Support/Claude/claude_desktop_config.json`. Restart Claude Desktop.

### Step 5: Try it

Open Claude Desktop and ask:

- "What tensions am I holding?"
- "What have I been thinking about [topic]?"
- "What's stalled in my projects?"
- "What contradicts my beliefs about [topic]?"

If Claude surfaces something you recognize as accurate and non-obvious — something you didn't expect it to know — that's the "holy shit" moment.

---

## Source Connectors

| Source | Command | What it ingests |
|--------|---------|----------------|
| Apple Notes | `npm run sync:notes` | All notes via osascript |
| Local files | `npm run sync:local` | Markdown, Claude exports, Perplexity threads from `sources/local-files/export/` |
| iMessage | `npm run sync:imessage` | Outgoing messages + action-verb incoming (requires Full Disk Access) |
| Gmail | `npm run sync:gmail` | Action-verb filtered emails (requires Gmail OAuth — see `sources/gmail/` for setup) |
| Claude exports | `npm run watch-claude` | Auto-ingest when you drop Claude JSON exports |
| Perplexity | `npx tsx scripts/perplexity-playwright.ts` | Bulk export via headless browser |

### Automatic sync

The `init` wizard offers to install a launchd scheduler that syncs + builds every 30 minutes automatically. Or run the full pipeline manually:

```bash
npx @chobus/mikai sync && npx @chobus/mikai build
```

---

## Architecture

```
You write/think/clip/email/message
        │
        ▼
   Source Connectors          ← Ingest raw content (zero LLM)
        │
        ▼
   Track A: Claude Haiku      ← Extract reasoning map from authored content
   Track B: Rule Engine        ← Detect action patterns from behavioral traces
   Track C: Smart Split        ← Structural segmentation (zero LLM)
        │
        ▼
   Local SQLite + sqlite-vec   ← Everything on your machine
   ├── sources (raw content)
   ├── nodes (concepts, tensions, decisions, questions)
   ├── edges (supports, contradicts, unresolved_tension, ...)
   └── segments (condensed passages for fast search)
        │
        ▼
   MCP Server (8 tools)       ← Claude Desktop queries your graph
```

**Local-first by default.** No cloud database, no third-party storage. Your data stays on your machine. Embeddings run locally via Nomic nomic-embed-text-v1.5 (768-dim). The only API call is Claude Haiku for graph extraction.

### The Epistemic Edge Vocabulary

MIKAI's edges aren't just "related to." They're typed reasoning relationships:

| Edge | Priority | Meaning |
|------|----------|---------|
| `unresolved_tension` | Highest | You're actively holding two beliefs in conflict |
| `contradicts` | High | Two nodes structurally conflict |
| `depends_on` | Medium | A can't be resolved without B |
| `partially_answers` | Medium | A addresses part of B |
| `supports` | Low | A provides evidence for B |
| `extends` | Lowest | A builds on B |

Tensions and contradictions surface first because that's where synthesis is most valuable. See [docs/EPISTEMIC_EDGE_VOCABULARY.md](docs/EPISTEMIC_EDGE_VOCABULARY.md) for the full specification.

---

## Commands

### Quick start (local-first)

```bash
npx @chobus/mikai init             # Set up database + model + config
npx @chobus/mikai sync             # Sync Apple Notes + import folder
npx @chobus/mikai build            # Extract graph + segments + score
npx @chobus/mikai status           # Knowledge base stats
npx @chobus/mikai serve            # Start MCP server (stdio)
```

### Advanced (developers / Supabase users)

```bash
npm run sync:notes              # Apple Notes (direct osascript)
npm run sync:local              # Local markdown/JSON/HTML files
npm run sync:imessage           # iMessage (requires Full Disk Access)
npm run sync:gmail              # Gmail (requires OAuth setup)
npm run build-graph             # Build knowledge graph (Track A + B)
npm run build-segments          # Build searchable segments (Track C)
npm run run-rule-engine         # Score stall probability
npm run build-graph -- --dry-run          # Preview without API calls
npm run build-graph -- --rebuild          # Re-extract everything
```

---

## Project Structure

```
mikai/
├── surfaces/mcp/server.ts       ← MCP server (the product)
├── engine/
│   ├── graph/                   ← Extraction pipeline
│   ├── inference/               ← Stall detection rule engine
│   ├── ingestion/               ← Content preprocessing
│   ├── scheduler/               ← Automated sync
│   └── eval/                    ← Quality evaluation
├── sources/                     ← Data source connectors
├── scripts/                     ← Utilities
├── lib/                         ← Shared modules
├── infra/supabase/              ← Schema migrations
└── docs/                        ← Specifications
```

---

## How It's Different

| | Traditional AI Memory | MIKAI |
|---|---|---|
| **Stores** | What you said | What you said + what you did |
| **Retrieves** | Similar content | Reasoning structure |
| **Surfaces** | Past conversations | Unresolved tensions |
| **Optimizes for** | Recall accuracy | Action — did you act on what was surfaced? |
| **Edge types** | None or flat | 6 typed reasoning relationships |

See [docs/INTENT_INTELLIGENCE_MANIFESTO.md](docs/INTENT_INTELLIGENCE_MANIFESTO.md) for the full thesis.

---

## Contributing

MIKAI is early. If you're interested in intent intelligence — as a user, researcher, or contributor — open an issue or reach out.

## License

MIT
