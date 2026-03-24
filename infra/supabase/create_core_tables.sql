-- Core tables per ARCHITECTURE.md data model

CREATE TABLE IF NOT EXISTS sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type TEXT NOT NULL,           -- 'llm_thread' | 'note' | 'voice' | 'web_clip' | 'document'
  label TEXT,                   -- human-readable title
  raw_content TEXT NOT NULL,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID REFERENCES sources(id) ON DELETE CASCADE,
  content TEXT NOT NULL,        -- the concept/idea in plain text
  label TEXT NOT NULL,          -- short node label
  node_type TEXT NOT NULL,      -- 'concept' | 'project' | 'question' | 'decision' | 'tension'
  embedding VECTOR(1024),
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS edges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_node UUID REFERENCES nodes(id) ON DELETE CASCADE,
  to_node UUID REFERENCES nodes(id) ON DELETE CASCADE,
  relationship TEXT NOT NULL,   -- 'supports' | 'contradicts' | 'extends' | 'depends_on' | 'unresolved_tension' | 'partially_answers'
  note TEXT,                    -- one-phrase explanation of why this relationship exists
  weight FLOAT DEFAULT 1.0,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS briefs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT,
  content TEXT NOT NULL,
  source_node_ids UUID[],
  brief_type TEXT NOT NULL,     -- 'project' | 'daily' | 'domain' | 'manual'
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Vector similarity search over ingested nodes
CREATE OR REPLACE FUNCTION search_nodes(
  query_embedding vector(1024),
  match_count int DEFAULT 5
)
RETURNS TABLE (
  id uuid,
  label text,
  content text,
  node_type text,
  similarity float
)
LANGUAGE sql STABLE
AS $$
  SELECT
    n.id,
    n.label,
    n.content,
    n.node_type,
    1 - (n.embedding <=> query_embedding) AS similarity
  FROM nodes n
  WHERE n.embedding IS NOT NULL
  ORDER BY n.embedding <=> query_embedding
  LIMIT match_count;
$$;
