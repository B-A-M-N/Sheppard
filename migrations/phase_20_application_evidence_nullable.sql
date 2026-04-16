-- Phase 20: Application Evidence optional bindings
-- Sheppard v1.4.1-phase20
--
-- Restores the intended optional-link contract for application evidence.
-- Any row may bind an authority record, an atom, a bundle, or any combination,
-- but at least one binding must be present.

ALTER TABLE application.application_evidence
    ALTER COLUMN authority_record_id DROP NOT NULL;

ALTER TABLE application.application_evidence
    ALTER COLUMN atom_id DROP NOT NULL;

ALTER TABLE application.application_evidence
    ALTER COLUMN bundle_id DROP NOT NULL;

ALTER TABLE application.application_evidence
    DROP CONSTRAINT IF EXISTS application_evidence_nonempty_binding;

ALTER TABLE application.application_evidence
    ADD CONSTRAINT application_evidence_nonempty_binding
    CHECK (authority_record_id IS NOT NULL OR atom_id IS NOT NULL OR bundle_id IS NOT NULL);

COMMENT ON TABLE application.application_evidence IS
    'Evidence bindings for application queries. Authority, atom, and bundle references are optional individually but at least one must be present.';
