<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-27 | Updated: 2026-03-27 -->

# sources

## Purpose
Data connectors — zero-LLM ingestion from user's apps. Each subdirectory handles one data source.

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `apple-notes/` | Apple Notes via osascript (two variants: sync.js + sync-direct.js) |
| `gmail/` | Gmail via Google API with OAuth2 |
| `imessage/` | iMessage via direct SQLite access to chat.db |
| `local-files/` | Markdown, Claude exports, Perplexity transcripts |

## For AI Agents

### Working In This Directory
- ALL connectors are zero-LLM — they only extract and store raw content
- Each has a standalone `sync.js` that can be run independently
- Output goes to the `sources` table in the database
- The graph builder and segmenter run AFTER sync to extract structure

### Common Patterns
- Each sync script: read from source → deduplicate by content_hash → insert into sources table
- Gmail requires OAuth setup (credentials in `~/.mikai/`)
- iMessage requires Full Disk Access permission on macOS
