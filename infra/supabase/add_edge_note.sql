-- Migration: add note column to edges table
-- Run in Supabase SQL editor before running build-graph.js
-- Stores the one-phrase explanation extracted by the new reasoning prompt.

ALTER TABLE edges ADD COLUMN IF NOT EXISTS note TEXT;
