-- Phase 17: Consolidation — Golden Atom columns
-- Sheppard v1.3.0-phase17
--
-- Adds consolidation columns to knowledge.knowledge_atoms:
-- - is_golden: True for Golden Atoms merged from similar atoms
-- - is_obsolete: True for atoms superseded by consolidation or contradiction resolution
-- - obsolete_reason: Why the atom was marked obsolete
-- - golden_atom_id: References the Golden Atom that superseded this atom
-- - source_ids: All source_ids contributing to this atom (merged for Golden Atoms)

ALTER TABLE knowledge.knowledge_atoms
    ADD COLUMN IF NOT EXISTS is_golden BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE knowledge.knowledge_atoms
    ADD COLUMN IF NOT EXISTS is_obsolete BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE knowledge.knowledge_atoms
    ADD COLUMN IF NOT EXISTS obsolete_reason TEXT;

ALTER TABLE knowledge.knowledge_atoms
    ADD COLUMN IF NOT EXISTS golden_atom_id TEXT
    REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE SET NULL;

ALTER TABLE knowledge.knowledge_atoms
    ADD COLUMN IF NOT EXISTS source_ids TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN knowledge.knowledge_atoms.is_golden IS
    'True for Golden Atoms — merged from multiple similar atoms with combined source_ids.';
COMMENT ON COLUMN knowledge.knowledge_atoms.is_obsolete IS
    'True for atoms superseded by a Golden Atom or resolved as the weaker contradiction claim.';
COMMENT ON COLUMN knowledge.knowledge_atoms.obsolete_reason IS
    'Why this atom was marked obsolete: "consolidated_into_golden", "contradiction_resolved", etc.';
COMMENT ON COLUMN knowledge.knowledge_atoms.golden_atom_id IS
    'References the Golden Atom that superseded this atom (NULL for active/golden atoms).';
COMMENT ON COLUMN knowledge.knowledge_atoms.source_ids IS
    'All source_ids contributing to this atom. For Golden Atoms, merged from cluster members.';

-- Verification
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='knowledge' AND table_name='knowledge_atoms' AND column_name='is_golden') THEN
        RAISE EXCEPTION 'Phase 17 migration failed: is_golden column not created';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='knowledge' AND table_name='knowledge_atoms' AND column_name='is_obsolete') THEN
        RAISE EXCEPTION 'Phase 17 migration failed: is_obsolete column not created';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='knowledge' AND table_name='knowledge_atoms' AND column_name='obsolete_reason') THEN
        RAISE EXCEPTION 'Phase 17 migration failed: obsolete_reason column not created';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='knowledge' AND table_name='knowledge_atoms' AND column_name='golden_atom_id') THEN
        RAISE EXCEPTION 'Phase 17 migration failed: golden_atom_id column not created';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='knowledge' AND table_name='knowledge_atoms' AND column_name='source_ids') THEN
        RAISE EXCEPTION 'Phase 17 migration failed: source_ids column not created';
    END IF;
    RAISE NOTICE 'Phase 17 migration verified: all columns created successfully';
END $$;

-- Migration complete.
