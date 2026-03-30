-- ============================================================
-- Phase 11 Activation — Add mission_id to synthesis tables
--
-- This patch adds mission_id columns to synthesis artifacts
-- and sections to enforce mission isolation in the synthesis
-- pipeline.
-- ============================================================

-- Add mission_id to synthesis_artifacts
ALTER TABLE authority.synthesis_artifacts
  ADD COLUMN mission_id TEXT REFERENCES mission.research_missions(mission_id);

-- Add mission_id to synthesis_sections
ALTER TABLE authority.synthesis_sections
  ADD COLUMN mission_id TEXT REFERENCES mission.research_missions(mission_id);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_synthesis_artifacts_mission_id
  ON authority.synthesis_artifacts(mission_id);

CREATE INDEX IF NOT EXISTS idx_synthesis_sections_mission_id
  ON authority.synthesis_sections(mission_id);
