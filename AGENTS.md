<!-- Generated: 2026-03-27 | Updated: 2026-03-27 -->

# MIKAI

## Purpose
Task-state awareness engine ("noonchi") that knows where you are in your thinking across apps and tells you what to do next. Extracts a knowledge graph from Apple Notes, Gmail, iMessage, and local files, then detects threads, classifies their reasoning state, and infers next steps.

## Architecture Layers
| Layer | Purpose | LLM Usage |
|-------|---------|-----------|
| L3 — Knowledge Graph | Extraction, segmentation, stall scoring | Claude Haiku (extraction only) |
| L4 — Task-State Awareness | Thread detection, state classification, next-step inference | Claude Haiku (inference only) |

## Key Files
| File | Description |
|------|-------------|
| `package.json` | @chobus/mikai v0.3.0 — npm package manifest |
| `CLAUDE.md` | Development context and build instructions |
| `.env.local` | API keys (Anthropic, Voyage, Supabase) — DO NOT COMMIT |
| `tsconfig.json` | TypeScript configuration |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `engine/` | Core processing pipeline (see `engine/AGENTS.md`) |
| `lib/` | Storage backends and embeddings (see `lib/AGENTS.md`) |
| `surfaces/` | Product surfaces — MCP server (see `surfaces/AGENTS.md`) |
| `sources/` | Data connectors — zero-LLM ingest (see `sources/AGENTS.md`) |
| `scripts/` | Utility scripts for watching/cleanup |
| `docs/` | Architecture docs, decisions, open questions |
| `private/` | Strategy docs — identity, roadmap, competitive analysis |
| `bin/` | CLI entrypoint (`mikai.ts`) |

## For AI Agents

### Working In This Directory
- Use `.env.local` for API keys — never hardcode secrets
- The project has TWO storage paths: Supabase (cloud) and SQLite (local, `~/.mikai/mikai.db`)
- Set `MIKAI_LOCAL=1` to use the local SQLite path
- All engine scripts use the same env-loading pattern: read `.env.local` line-by-line

### Testing Requirements
- `npm test` runs the full eval suite
- `npm run test:quick` for fast validation
- `npm run eval:stall` for stall detection accuracy

### Pipeline
```
sync (zero LLM) → build-graph (Haiku) → build-segments (zero LLM) → run-rule-engine (zero LLM) → run-l4-pipeline (detect → classify → infer)
```

## Dependencies

### External
- `@anthropic-ai/sdk` — Claude API for extraction and inference
- `@modelcontextprotocol/sdk` — MCP server framework
- `better-sqlite3` + `sqlite-vec` — Local storage with vector search
- `@supabase/supabase-js` — Cloud storage (optional)
- `voyageai` — Voyage AI embeddings (optional, cloud path)
