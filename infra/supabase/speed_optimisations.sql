-- Migration: speed optimisations — content hash, indexes, scoring function
-- Safe to re-run (uses IF NOT EXISTS / CREATE OR REPLACE)
-- Apply via Supabase SQL editor or psql

-- ── 1. content_hash on sources ────────────────────────────────────────────────
-- SHA-256 of raw_content, set at ingest time.
-- build-graph --rebuild skips sources where hash matches last extraction,
-- eliminating unnecessary Claude API calls on daily runs.

ALTER TABLE sources ADD COLUMN IF NOT EXISTS content_hash TEXT;


-- ── 2. Indexes on nodes ───────────────────────────────────────────────────────

-- getTopStalledNodes() — partial index covers only rows the query touches
CREATE INDEX IF NOT EXISTS idx_nodes_stall_probability
  ON nodes (stall_probability DESC)
  WHERE stall_probability > 0.5;

-- DELETE FROM nodes WHERE source_id = ? (rebuild delete step)
CREATE INDEX IF NOT EXISTS idx_nodes_source_id ON nodes (source_id);

-- --track A/B filter in run-rule-engine
CREATE INDEX IF NOT EXISTS idx_nodes_track ON nodes (track);


-- ── 3. compute_stall_probability() Postgres function ─────────────────────────
-- Mirrors scoreNode() in engine/inference/rule-engine.ts exactly.
-- Allows the rule engine to update all nodes in a single SQL statement
-- instead of fetching all rows to JS and issuing one UPDATE per node.
--
-- Inputs match the feature columns on the nodes table.
-- days_since_created is passed in as a FLOAT (computed from created_at by caller).

CREATE OR REPLACE FUNCTION compute_stall_probability(
  p_occurrence_count    INT,
  p_days_since_created  FLOAT,
  p_has_action_verb     BOOLEAN,
  p_query_hit_count     INT,
  p_confidence_weight   FLOAT,
  p_resolved_at         TIMESTAMPTZ,
  p_track               TEXT
) RETURNS FLOAT AS $$
DECLARE
  v_score FLOAT;
BEGIN
  -- High-confidence stall rule (mirrors rule-engine.ts line 49-56)
  IF p_occurrence_count >= 2
     AND p_days_since_created > 14
     AND p_has_action_verb = TRUE
     AND p_resolved_at IS NULL
  THEN
    RETURN 0.8;
  END IF;

  -- Weighted signal combination (mirrors rule-engine.ts line 59-68)
  v_score := (
    CASE WHEN p_has_action_verb THEN 0.3 ELSE 0.0 END
    + LEAST(p_occurrence_count::FLOAT / 5.0, 1.0) * 0.3
    + CASE WHEN p_days_since_created > 7 THEN 0.2 ELSE 0.0 END
    + CASE WHEN p_query_hit_count > 0 THEN 0.1 ELSE 0.0 END
  ) * COALESCE(p_confidence_weight, 0.5);

  -- Track B baseline floor (mirrors run-rule-engine.js line 129-132)
  IF p_track = 'B' THEN
    v_score := GREATEST(
      v_score,
      CASE WHEN p_has_action_verb THEN 0.6 ELSE 0.0 END
    );
  END IF;

  RETURN LEAST(v_score, 1.0);
END;
$$ LANGUAGE plpgsql IMMUTABLE;


-- ── 4. score_all_nodes() convenience function ─────────────────────────────────
-- Replaces the JS loop in run-rule-engine.js with a single RPC call.
-- Returns the count of rows updated.
--
-- Usage from JS: await supabase.rpc('score_all_nodes')
-- Usage from SQL: SELECT score_all_nodes();

CREATE OR REPLACE FUNCTION score_all_nodes() RETURNS INT AS $$
DECLARE
  v_updated INT;
BEGIN
  UPDATE nodes
  SET stall_probability = compute_stall_probability(
    COALESCE(occurrence_count, 1),
    EXTRACT(EPOCH FROM (NOW() - created_at)) / 86400.0,
    COALESCE(has_action_verb, FALSE),
    COALESCE(query_hit_count, 0),
    COALESCE(confidence_weight, 0.5),
    resolved_at,
    track
  )
  WHERE id IS NOT NULL;

  GET DIAGNOSTICS v_updated = ROW_COUNT;
  RETURN v_updated;
END;
$$ LANGUAGE plpgsql;
