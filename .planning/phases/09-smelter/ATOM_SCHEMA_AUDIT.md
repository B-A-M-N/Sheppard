# Phase 09 Audit: Atom Schema

**Date:** 2026-03-29
**Auditor:** Phase 09 Execution
**Scope:** KnowledgeAtom schema definition, evidence binding, type system

---

## Schema Definition

The KnowledgeAtom model is defined in `src/research/domain_schema.py` (lines 233-283). It is a Pydantic BaseModel.

### Full Fields Table

| Field | Type | Required? | Description |
|-------|------|-----------|-------------|
| atom_id | str | yes (constructor) | Unique identifier (UUID5) |
| topic_id | str | yes | Topic identifier |
| authority_record_id | Optional[str] | no | Linked authority record (nullable) |
| domain_profile_id | str | yes | Domain profile identifier |
| atom_type | str | yes | Type label (free string) |
| title | str | yes | Short title (first 50 chars of content) |
| statement | str | yes | Full factual statement |
| summary | Optional[str] | no | Summary (defaults to content) |
| confidence | float | yes (default 0.7) | Confidence score |
| importance | float | yes (default 0.5) | Importance score |
| novelty | float | yes (default 0.5) | Novelty score |
| stability | str | yes (default "medium") | Stability rating |
| scope | AtomScope | no (default empty) | Applicability scope |
| qualifiers | AtomQualifiers | no (default empty) | Caveats, counterpoints |
| lineage | AtomLineage | yes | Provenance (mission_id, extraction_mode) |
| metadata | Dict[str, Any] | no (default {}) | Additional metadata |

**Note:** The Pydantic model does not mark any fields as `Field(...)` required except those passed to constructor. Fields like `scope`, `qualifiers`, `metadata` have default factories.

---

## Evidence Binding

**Current implementation:**
- Evidence is stored in a **separate table** via `store_atom_with_evidence(atom_row, evidence_rows)`.
- Evidence rows contain: `source_id`, `evidence_strength` (0.9), `supports_statement` (True).
- The atom itself does **not** store `source_chunk_id` directly; the linkage is through the relational evidence table.
- Evidence record is created atomically with the atom.

**Is evidence mandatory?** The extraction pipeline always passes at least one evidence row linking back to the source. The adapter `store_atom_with_evidence` is expected to enforce at least one evidence link. However, the KnowledgeAtom model itself has no required evidence field; it is possible to create an atom without evidence at the model level, but the storage pathway includes it.

**Status:** `VERIFIED` — Evidence linkage exists in storage pathway, though not embedded in atom.

---

## Type System

**Atom types** are free strings. The extraction prompt (`src/utils/json_validator.py`, lines 295-312) instructs the model to produce types: `claim|evidence|event|procedure|contradiction`.

The KnowledgeAtom model does not enforce an enum. Any string is accepted.

Downstream code may rely on these five types; no other types are produced by current extraction.

**Status:** `PARTIAL` — Types are constrained by extraction but not enforced at schema level. No risk of arbitrary types unless modified downstream.

---

## Validation Rules

**Extraction-time validation:**
- `extract_technical_atoms` uses a JSON schema requiring: `atoms` array, each atom requires `type`, `content`, `confidence`.
- `content` has `minLength: 10`.
- After LLM response, `JSONValidator.validate_and_fix_json` checks required fields and basic types (string, array, number).
- If validation fails, up to 2 repair attempts are made.

**Storage-time validation:**
- The KnowledgeAtom Pydantic model performs type coercion but does not raise on missing optional fields due to defaults.
- No explicit validation gate before `store_atom_with_evidence`; if the atom object is constructed, it is stored.

**Status:** `VERIFIED` — Validation occurs at extraction; storage accepts what extraction produces. Two-layer validation not present.

---

## Schema Violations / Gaps

- No enforced enum for `atom_type`.
- `source_chunk_id` not directly on atom; relies on separate evidence table (acceptable if that table is always joined).
- `statement` and `summary` can be identical; no consistency check.
- `importance`, `novelty`, `confidence` ranges not constrained by schema (0.0–1.0 expected but not enforced).

---

## Conclusion

The schema is **mostly strict** but allows flexibility in type and scores. Evidence binding is externalized, which is acceptable if the evidence table is always present. No critical schema gaps that would allow malformed atoms to be stored.
