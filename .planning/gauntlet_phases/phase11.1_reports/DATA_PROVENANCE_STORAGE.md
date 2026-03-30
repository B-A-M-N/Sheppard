# Data Provenance: How synthesis_citations is Populated

**Phase 11.1 — Report Pipeline Hardening**

This document describes the mechanism by which the `atom_ids_used` are captured during synthesis and persisted into the `authority.synthesis_citations` table, enabling full regeneration of reports from the knowledge store.

---

## Overview

The truth contract requires that every section of a synthesized report be traceable to the exact knowledge atoms used. This lineage is stored via the existing `authority.synthesis_citations` table, which links synthesis artifacts and sections to the underlying `knowledge.knowledge_atoms`.

---

## Data Flow

1. **Evidence Assembly** (`EvidenceAssembler.build_evidence_packet`):
   - The retriever (V3Retriever) returns `RetrievedItem` objects whose metadata includes the `atom_id` of each knowledge atom.
   - While constructing the `EvidencePacket`, we now:
     - Extract `atom_id` from `item.metadata['atom_id']`.
     - Append it to `packet.atom_ids_used`.
   - The `packet.atoms` list contains the human-readable atom data (text, global_id, etc.) that will be fed to the LLM.

2. **Section Synthesis** (`SynthesisService.generate_master_brief`):
   - For each section in the plan, after calling `archivist.write_section` and validating grounding, we persist section content:
     ```python
     await self.adapter.store_synthesis_section({
         "artifact_id": artifact_id,
         "section_name": section.title,
         "section_order": section.order,
         "inline_text": prose,
         "mission_id": mission_id
     })
     ```
   - Then, if the section is real (not a placeholder) and `packet.atom_ids_used` is non-empty, we build citation records:
     ```python
     citations = [
         {
             "artifact_id": artifact_id,
             "section_name": section.title,
             "atom_id": atom_id,
             "metadata_json": {}
         }
         for atom_id in packet.atom_ids_used
     ]
     await self.adapter.store_synthesis_citations(citations)
     ```
   - The `store_synthesis_citations` method performs a bulk insert into `authority.synthesis_citations`.

3. **Database Schema**
   - The `authority.synthesis_citations` table already exists and requires no schema changes:
     ```sql
     CREATE TABLE authority.synthesis_citations (
         citation_id BIGSERIAL PRIMARY KEY,
         artifact_id TEXT NOT NULL REFERENCES authority.synthesis_artifacts(artifact_id) ON DELETE CASCADE,
         section_name TEXT,
         atom_id TEXT REFERENCES knowledge.knowledge_atoms(atom_id) ON DELETE SET NULL,
         source_id TEXT REFERENCES corpus.sources(source_id) ON DELETE SET NULL,
         citation_label TEXT,
         metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
     );
     ```
   - We insert one row per atom used in a section, linking the artifact, section, and atom.

---

## Provenance Guarantees

- **Completeness:** Every atom that contributed to a section's prose is recorded.
- **Atomicity:** Citations are stored transactionally with the section content (via the outer service transaction if the adapter uses one; recommended).
- **Queryability:** One can reconstruct which atoms supported which claims by joining `synthesis_citations` with `knowledge.knowledge_atoms`.
- **Regeneration:** Given an `artifact_id`, all used atoms can be fetched from the knowledge store solely via the `synthesis_citations` table.

---

## Example Query

To retrieve all atoms used in the "Methods" section of a given master brief:

```sql
SELECT ka.*
FROM authority.synthesis_citations sc
JOIN knowledge.knowledge_atoms ka ON sc.atom_id = ka.atom_id
WHERE sc.artifact_id = $1
  AND sc.section_name = 'Methods';
```

---

## Implementation References

- `src/research/reasoning/assembler.py` — population of `atom_ids_used` in `EvidencePacket`.
- `src/research/reasoning/synthesis_service.py` — invocation of `store_synthesis_citations`.
- `src/memory/storage_adapter.py` — `store_synthesis_citations` method (bulk insert).

---

## Validation

Unit tests (`test_phase11_invariants.py`) cover:
- `atom_ids_used` is non-empty when atoms are retrieved.
- `store_synthesis_citations` is called exactly once per synthesized section with the correct atom list.
- The citations table contains the expected rows after synthesis.
