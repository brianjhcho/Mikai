CREATE TABLE IF NOT EXISTS extraction_logs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id       UUID REFERENCES sources(id) ON DELETE SET NULL,
  operation       TEXT NOT NULL,  -- 'graph_extraction', 'segmentation', 'synthesis'
  model           TEXT NOT NULL,  -- 'claude-haiku-4-5-20251001', 'claude-sonnet-4-6'
  input_tokens    INT,
  output_tokens   INT,
  prompt_version  TEXT,           -- version string for tracking prompt changes
  duration_ms     INT,
  error           TEXT,           -- null on success, error message on failure
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX extraction_logs_created_at_idx ON extraction_logs (created_at);
CREATE INDEX extraction_logs_operation_idx ON extraction_logs (operation);
