-- Migration: Add exhausted_modes_json to mission.mission_nodes
-- Phase: 07.1 Critical Repairs
-- Issue: MissionNode.to_pg_row() includes exhausted_modes_json but column does not exist in schema
-- Impact: Frontier checkpoint crashes when attempting to INSERT/UPDATE mission_nodes
-- Date: 2026-03-28

-- Add the column with safe defaults
-- JSONB type matches the serialization pattern used for other JSON fields
-- NOT NULL with empty array default ensures existing rows get valid data
ALTER TABLE mission.mission_nodes
ADD COLUMN IF NOT EXISTS exhausted_modes_json JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Optional: Add an index if queries will filter on exhausted_modes (not required for current usage)
-- CREATE INDEX idx_mission_nodes_exhausted_modes ON mission.mission_nodes USING gin (exhausted_modes_json);

COMMIT;
