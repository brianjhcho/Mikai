-- Enable pgvector extension (run once)
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column to knowledge_nodes if not exists
ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS embedding vector(1024);

-- Vector similarity search function
-- Used by /api/search to find the top K most similar nodes to a query embedding
CREATE OR REPLACE FUNCTION search_knowledge_nodes(
  query_embedding vector(1024),
  match_count int DEFAULT 5
)
RETURNS TABLE (
  id text,
  label text,
  description text,
  color text,
  note_count int,
  similarity float
)
LANGUAGE sql STABLE
AS $$
  SELECT
    kn.id,
    kn.label,
    kn.description,
    kn.color,
    kn.note_count,
    1 - (kn.embedding <=> query_embedding) AS similarity
  FROM knowledge_nodes kn
  WHERE kn.embedding IS NOT NULL
  ORDER BY kn.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- IVFFlat index for fast cosine similarity search
-- Run after embeddings have been populated
-- CREATE INDEX ON knowledge_nodes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
