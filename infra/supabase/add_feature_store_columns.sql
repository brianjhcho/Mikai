-- Migration: add feature store columns to nodes table
-- Safe to re-run (uses ADD COLUMN IF NOT EXISTS)

-- Number of times this node has appeared across sources (incremented on duplicate detection)
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS occurrence_count INT DEFAULT 1;

-- Number of times this node has been returned as a query result (used to weight recall quality)
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS query_hit_count INT DEFAULT 0;

-- Source-type reliability weight used during retrieval scoring (1.0 = highest confidence)
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS confidence_weight FLOAT DEFAULT 1.0;

-- Whether the node content contains an action verb (buy, book, schedule, etc.) indicating a stalled desire
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS has_action_verb BOOLEAN DEFAULT false;

-- Estimated probability that this node represents a stalled desire (NULL until classifier runs)
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS stall_probability FLOAT;
