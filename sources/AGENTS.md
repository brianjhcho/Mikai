<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-27 | Updated: 2026-04-02 -->

# Sources — Data Connectors

## Purpose
Zero-LLM ingestion from user's apps. Each subdirectory handles one data source. Two output paths exist: legacy (Supabase) and current (Graphiti).

## Data Flow

### Production Path (Graphiti — current)
```
Apple Notes → osascript (read_notes.applescript) → /tmp dump → import_from_dump.py → Graphiti sidecar → Neo4j
Perplexity  → local-files/export/ → import script → Graphiti sidecar → Neo4j
Claude      → local-files/export/ → import script → Graphiti sidecar → Neo4j
```

### npm Package Path (SQLite — legacy)
```
Sources → sync-direct.js → ingest-direct.ts → Supabase (legacy) / SQLite
```

**Note:** The sync scripts in this directory write to **Supabase** via `ingest-direct.ts`. For Graphiti import, use the scripts in `infra/graphiti/scripts/` which read directly from Apple Notes and send to the Graphiti sidecar.

## Subdirectories
| Directory | Purpose | Graphiti Path |
|-----------|---------|--------------|
| `apple-notes/` | Apple Notes via osascript | Use `infra/graphiti/scripts/read_notes.applescript` + `import_from_dump.py` |
| `local-files/` | Markdown, Claude exports, Perplexity transcripts | Import via `migrate_sqlite_to_graphiti.py --source-type perplexity` |
| `gmail/` | Gmail via Google API with OAuth2 | **Skipped** for Graphiti (per user decision) |
| `imessage/` | iMessage via direct SQLite access | Low priority |

## For AI Agents

### Working In This Directory
- ALL connectors are zero-LLM — they only extract and store raw content
- **For Graphiti imports:** Do NOT use these sync scripts. Use `infra/graphiti/scripts/` instead.
- **For SQLite/npm path:** Each sync script reads from source → deduplicates by content_hash → inserts into sources table
- The `ingest-direct.ts` writes to Supabase (legacy) — this is the SQLite/npm path, not the Graphiti path

### Sync Commands (SQLite/npm path only)
```bash
npm run sync:notes      # Apple Notes
npm run sync:local      # Local files (Perplexity, Claude exports)
npm run sync:gmail      # Gmail
npm run sync:imessage   # iMessage
npm run sync:all        # All sources
```

### Graphiti Import Commands (production)
```bash
cd infra/graphiti
osascript scripts/read_notes.applescript 2>/tmp/mikai_notes_raw.txt   # Read notes
source .venv/bin/activate
python scripts/import_from_dump.py --delay 8                           # Import to Graphiti
```

## Dependencies

### Internal
- `engine/ingestion/ingest-direct.ts` — Supabase ingestion (legacy)
- `engine/ingestion/preprocess.ts` — Content cleaning per source type

### External
- Gmail requires OAuth2 setup (`~/.mikai/gmail-credentials.json`)
- iMessage requires Full Disk Access permission on macOS
- Apple Notes requires Notes.app running

<!-- MANUAL: The Supabase sync path will be maintained for the npm package. Graphiti path is production-only. -->
