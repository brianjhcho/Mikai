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

## Getting Started (30 minutes)

### Prerequisites

- macOS (for Apple Notes and iMessage connectors)
- [Node.js](https://nodejs.org/) v20+
- A [Supabase](https://supabase.com/) project (free tier works)
- [Claude Desktop](https://claude.ai/download) with MCP enabled
- API keys: [Anthropic](https://console.anthropic.com/) + [Voyage AI](https://www.voyageai.com/)

### Step 1: Clone and install

```bash
git clone https://github.com/yourusername/mikai.git
cd mikai
npm install
```

### Step 2: Set up Supabase

Create a new Supabase project. Enable the `pgvector` extension:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Run the schema migrations in order:

```bash
# In the Supabase SQL editor, run each file:
infra/supabase/create_core_tables.sql
infra/supabase/add_source_field.sql
infra/supabase/add_edge_note.sql
infra/supabase/add_feature_store_columns.sql
infra/supabase/add_segments_table.sql
infra/supabase/add_extraction_logs.sql
infra/supabase/speed_optimisations.sql
```

### Step 3: Configure environment

```bash
cp .env.example .env.local
```

Edit `.env.local`:

```bash
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=pa-...
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
```

### Step 4: Ingest your first source

The fastest path — sync your Apple Notes:

```bash
npm run sync:notes
```

Or drop markdown files into `sources/local-files/export/markdown/` and run:

```bash
npm run sync:local
```

### Step 5: Build the graph

```bash
# Extract reasoning structure (uses Claude Haiku — ~$0.01 per note)
npm run build-graph

# Build searchable segments (uses Voyage AI embeddings — ~$0.001 per note)
npm run build-segments

# Score nodes for stall detection (free — rule engine, no API calls)
npm run run-rule-engine
```

### Step 6: Connect Claude Desktop

Add MIKAI to your Claude Desktop MCP config at `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mikai": {
      "command": "npx",
      "args": ["tsx", "/absolute/path/to/mikai/surfaces/mcp/server.ts"]
    }
  }
}
```

Restart Claude Desktop.

### Step 7: Try it

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

Install the daily scheduler (runs every 30 minutes via macOS launchd):

```bash
npm run scheduler:install
```

Or run the full pipeline manually:

```bash
npm run scheduler:run
```

---

## Architecture

```
You write/think/email/message
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
   Supabase (Postgres + pgvector)
   ├── sources (raw content)
   ├── nodes (concepts, tensions, decisions, questions)
   ├── edges (supports, contradicts, unresolved_tension, ...)
   └── segments (condensed passages for fast search)
        │
        ▼
   MCP Server (8 tools)       ← Claude Desktop queries your graph
```

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

## Pipeline Commands

```bash
# Ingest
npm run sync:notes              # Apple Notes (direct)
npm run sync:local              # Local markdown/JSON/HTML files
npm run sync:imessage           # iMessage
npm run sync:gmail              # Gmail

# Extract
npm run build-graph             # Build knowledge graph (Track A + B)
npm run build-segments          # Build searchable segments (Track C)
npm run run-rule-engine         # Score stall probability

# Evaluate
npm run eval                    # Interactive node quality eval
npm run eval:stall              # Stall detection quality eval
npm run test                    # Full test suite

# Run
npm run mcp                     # Start MCP server (stdio)
npm run scheduler:run           # Full pipeline (all syncs + extract)
```

### Useful flags

```bash
npm run build-graph -- --dry-run          # Preview without API calls
npm run build-graph -- --rebuild          # Re-extract everything
npm run build-graph -- --source-id <uuid> # Process one source
npm run sync:local -- --force             # Re-ingest all files
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
