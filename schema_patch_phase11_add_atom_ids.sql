-- ============================================================
-- Phase 11.1 — Add atom_ids_used to synthesis_sections
--
-- Adds a top-level, machine-readable column to track which
-- knowledge atoms were used in each section for provenance
-- and regeneration lineage.
-- ============================================================

ALTER TABLE authority.synthesis_sections
  ADD COLUMN IF NOT EXISTS atom_ids_used JSONB;

-- Index for fast lookup by atom (reverse provenance)
-- GIN index works for JSONB containment queries
CREATE INDEX IF NOT EXISTS idx_synthesis_sections_atom_ids_used
  ON authority.synthesis_sections USING GIN (atom_ids_used);
