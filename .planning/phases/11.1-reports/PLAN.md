# PHASE 11.1 — REPORT PIPELINE HARDENING

## Mission

Hardening the report generation pipeline to comply with V3 truth contract by enforcing transformation-only behavior, provenance tracking, mission isolation, and deterministic regeneration.

---

## GSD Workflow

- Discuss: Truth contract enforcement mechanisms
- Plan: Implement each invariant with verification gates
- Execute: Atomic commits per invariant
- Verify: Re-run Phase 11 audit

---

## Prompt for Agent

```
You are executing Phase 11.1 for Sheppard V3: Report Pipeline Hardening.

Mission:
Resolve all 7 blocking failures identified in Phase 11 audit to achieve truth-compliant report generation.

Objectives:
1. Replace HybridRetriever with V3Retriever
2. Add atom_ids_used provenance storage (DB + code)
3. Propagate mission_id through entire synthesis call chain
4. Remove word count minimum and tighten Archivist prompt
5. Enforce per-sentence citation and no-inference rule
6. Implement grounding validator (post-generation)
7. Enforce deterministic sampling (temperature=0, fixed seed)
8. Fix insufficient evidence handling (binary refusal)

Required method:
- Make atomic, testable changes to synthesis pipeline
- Update DB schema for synthesis_sections (add atom_ids_used column)
- Write unit tests for each invariant
- Ensure no regression on existing functionality

Deliverables (write to .planning/gauntlet_phases/phase11.1_reports/):
- INVARIANT_IMPLEMENTATION.md (per-invariant changes)
- DB_SCHEMA_MIGRATION.md
- UNIT_TESTS.md
- VERIFICATION_REPORT.md (re-audit results)

Mandatory checks (must pass before completion):
- V3Retriever wireup confirmed (no HybridRetriever imports)
- atom_ids_used stored for every section
- All queries filter by mission_id
- Archivist prompt forbids inference and requires per-sentence citation
- Validator rejects outputs with uncited sentences or citation mismatch
- Temperature=0 and seed fixed in ollama.complete()
- Sections with insufficient evidence are skipped, not written

Hard fail conditions:
- Any HybridRetriever reference remains
- atom_ids_used not persisted
- mission_id not used in any query
- Validator absent or bypassed
- Word count minimum reintroduced
- Temperature not zero
- Insufficient evidence still produces prose

Completion bar:
PASS only when all 7 Phase 11 failures are resolved and re-audit confirms compliance.
```

---

## Tasks

| ID | Task | Status | Owner | Dependencies |
|----|------|--------|-------|--------------|
| 11.1-01 | Replace HybridRetriever with V3Retriever in EvidenceAssembler | ⏳ Pending | Claude | — |
| 11.1-02 | Capture atom_ids, fix adapter call (use store_synthesis_sections), and store citations | ⏳ Pending | Claude | — |
| 11.1-03 | Propagate mission_id through entire synthesis call chain | ⏳ Pending | Claude | — |
| 11.1-04 | Remove "MINIMUM 1000 WORDS" and tighten Archivist prompt | ⏳ Pending | Claude | — |
| 11.1-05 | Add explicit "no inference" and "per-sentence citation" constraints | ⏳ Pending | Claude | 11.1-04 |
| 11.1-06 | Implement grounding validator (citation presence + support check) | ⏳ Pending | Claude | 11.1-02, 11.1-05 |
| 11.1-07 | Enforce deterministic sampling (temperature=0, fixed seed) | ⏳ Pending | Claude | — |
| 11.1-08 | Fix insufficient evidence handling: skip sections with < MIN_EVIDENCE | ⏳ Pending | Claude | 11.1-06 |
| 11.1-09 | Write unit tests for transformation-only invariants | ⏳ Pending | Claude | 11.1-06, 11.1-08 |
| 11.1-10 | Re-run Phase 11 audit and verify PASS | ⏳ Pending | Claude | All above |

---

## Deliverables

- **INVARIANT_IMPLEMENTATION.md** — detailed change log per invariant
- **DATA_PROVENANCE_STORAGE.md** — how `synthesis_citations` is populated (no schema change needed)
- **UNIT_TESTS.md** — test suite showing each invariant enforced
- **VERIFICATION_REPORT.md** — re-audit results (Phase 11 rerun)

---

## Dependencies

**Upstream:**
- Phase 10 (Atom Store & Query) — V3Retriever must be functional
- Phase 11 (audit report) — provides failure catalog and evidence

**Schema changes required:**
- `synthesis_sections` table: add `atom_ids_used` column (TEXT[] or JSONB)
- May need to add `mission_id` column if not already present (verify against domain schema)

**Code touch points:**
- `src/research/reasoning/assembler.py` — retriever, packet, mission_id
- `src/research/archivist/synth_adapter.py` — prompt, validator, sampling
- `src/research/reasoning/synthesis_service.py` — orchestration, DB calls, evidence threshold
- `src/research/reasoning/v3_retriever.py` — ensure it's the right interface
- `src/memory/manager.py` or adapter — DB schema extension

---

## Acceptance Criteria (Invariants)

### Invariant 1: Retrieval Compliance
- No `HybridRetriever` imports or usage in synthesis code paths
- `EvidenceAssembler` receives `V3Retriever` instance
- All evidence from `knowledge.knowledge_atoms` via Chroma

### Invariant 2: Provenance
- `EvidencePacket` includes `atom_ids_used: List[str]` (ordered by citation appearance)
- After section storage, call `store_synthesis_citations()` to insert rows into `authority.synthesis_citations` linking `artifact_id`, `section_name`, and `atom_id`
- No schema change required — `synthesis_citations` table already exists
- Verification: query `synthesis_citations` to reconstruct which atoms supported each section

### Invariant 3: Mission Isolation
- `generate_master_brief(mission_id, topic_id)` signature (or mission_id derived from topic)
- All DB queries include `WHERE mission_id = $1`
- All artifacts include `mission_id` foreign key

### Invariant 4: Transformation-Only
- Archivist prompt includes: "Every claim must be directly cited. Do not combine, infer, or paraphrase multiple sources without explicit citation for each claim."
- No word count minimum anywhere in synthesis prompts
- Validator runs post-generation and rejects uncited sentences

### Invariant 5: Citation Integrity
- Grounding validator checks:
  - Every sentence contains at least one `[A###]` citation
  - Every cited key exists in the evidence packet
  - Clause-level checks for numeric/entity consistency (e.g., if sentence says "300°C", cited atom must contain that value)
- Validator raises error on any violation; output rejected

### Invariant 6: Determinism
- `ollama.complete()` called with `temperature=0.0`
- Fixed `seed` parameter (if supported by model backend)
- Evidence packet atom order sorted by `citation_key` to guarantee consistent ordering
- Prompt includes no random elements

### Invariant 7: Insufficient Evidence Fallback
- `SynthesisService` checks `len(packet.atoms) < MIN_EVIDENCE` (configurable, default 3)
- If insufficient: **skip** writing section entirely
- Insert: `## [Section Title]\n\n[INSUFFICIENT EVIDENCE FOR SECTION]\n`
- Do **not** call `archivist.write_section()` when evidence insufficient

### Invariant 8: Contradiction Surface
- Contradictions retrieved when relevant (as currently designed)
- Archivist explicitly states conflicts in prose with citations
- No silent resolution

---

## Expected Wave Structure

### Wave 1 — Structural Rewiring
- 11.1-01 (V3Retriever)
- 11.1-03 (mission_id)

### Wave 2 — Data Integrity
- 11.1-02 (provenance storage)
- 11.1-06 (validator)

### Wave 3 — Behavioral Constraints
- 11.1-04 (remove word count)
- 11.1-05 (prompt tightening)
- 11.1-08 (fallback rule)

### Wave 4 — Determinism + Verification
- 11.1-07 (sampling)
- 11.1-09 (tests)
- 11.1-10 (re-audit)

---

## Verification Template

```markdown
# Phase 11.1 Verification

## Invariant Check

- [ ] 1. Retrieval: V3Retriever only (no Hybrid)
- [ ] 2. Provenance: atom_ids_used stored
- [ ] 3. Mission: all queries filter by mission_id
- [ ] 4. Transformation: no inference, per-sentence citation
- [ ] 5. Validator: present and enforced
- [ ] 6. Determinism: temperature=0, fixed seed
- [ ] 7. Fallback: insufficient evidence → section refusal

## Phase 11 Re-Audit

- [ ] All 7 Phase 11 failures resolved
- [ ] No new regressions introduced
- [ ] Unit tests green

## Verdict

**Status:** PASS / FAIL

## Notes

(any open gaps or justification)
```

---

## Completion Criteria

PASS when:
- All 7 Phase 11 blocking failures are fixed
- Re-audit (Phase 11 style) confirms compliance on all locked decisions
- Unit tests prove each invariant
- No HybridRetriever remnants
- DB schema updated and migrations documented

---

**Ready for execution.** This phase will close the truth contract gaps and enable safe synthesis activation.
