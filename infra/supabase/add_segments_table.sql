-- Track C: Condensed Synthesis segments table
-- Run this migration in the Supabase SQL editor before running npm run build-segments.
--
-- One segment = one topic-coherent passage extracted from a source.
-- A single source (e.g. "Feb 2025") produces multiple segments, one per distinct topic.
-- Segments are the retrieval unit for Mode D (Condensed Synthesis).

CREATE TABLE IF NOT EXISTS segments (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id           UUID REFERENCES sources(id) ON DELETE CASCADE,
  topic_label         TEXT NOT NULL,          -- Claude-inferred: "developmental economics r>g thesis"
  processed_content   TEXT NOT NULL,          -- condensed prose in Brian's voice
  processed_embedding VECTOR(1024),           -- Voyage AI voyage-3 embedding of processed_content
  created_at          TIMESTAMPTZ DEFAULT now()
);

-- Vector index for similarity search (matches nodes table index pattern)
CREATE INDEX IF NOT EXISTS segments_embedding_idx
  ON segments USING ivfflat (processed_embedding vector_cosine_ops)
  WITH (lists = 100);

-- Index for fast source lookups (used by build-segments to check existing segments)
CREATE INDEX IF NOT EXISTS segments_source_id_idx ON segments (source_id);

-- ── RPC function: search_segments ────────────────────────────────────────────
-- Called by /api/chat/synthesize (Mode D) and lib/segment-retrieval.ts.
-- Returns top-K segments by cosine similarity, joined with source provenance.

CREATE OR REPLACE FUNCTION search_segments(
  query_embedding VECTOR(1024),
  match_count     INT DEFAULT 8
)
RETURNS TABLE (
  id              UUID,
  source_id       UUID,
  topic_label     TEXT,
  processed_content TEXT,
  similarity      FLOAT,
  source_label    TEXT,
  source_type     TEXT,
  source_origin   TEXT
)
LANGUAGE SQL STABLE
AS $$
  SELECT
    s.id,
    s.source_id,
    s.topic_label,
    s.processed_content,
    1 - (s.processed_embedding <=> query_embedding) AS similarity,
    src.label   AS source_label,
    src.type    AS source_type,
    src.source  AS source_origin
  FROM segments s
  JOIN sources src ON src.id = s.source_id
  WHERE s.processed_embedding IS NOT NULL
  ORDER BY s.processed_embedding <=> query_embedding
  LIMIT match_count;
$$;
