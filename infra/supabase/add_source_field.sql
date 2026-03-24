-- Migration: add source origin field and ingest counts to sources table
ALTER TABLE sources
  ADD COLUMN IF NOT EXISTS source TEXT,           -- 'apple-notes' | 'claude-thread' | 'perplexity' | 'browser' | etc.
  ADD COLUMN IF NOT EXISTS chunk_count INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS node_count INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS edge_count INT DEFAULT 0;
