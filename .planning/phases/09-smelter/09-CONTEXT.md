---
phase: 09
name: Smelter / Atom Extraction Audit
date: 2026-03-29
status: audit_complete
---

# Phase 09 Context — Smelter/Audit

## Mission
Audit the atom extraction path to verify schema correctness, parsing robustness, evidence integrity, deduplication determinism, and safe JSON repair. No code changes; inspection and reporting only.

## Prior Decisions (relevance)
- Phase 06: Discovery engine fixed (parent_node_id, deep mining, academic filtering, exhausted_modes persistence, queue backpressure)
- Phase 07: Orchestration contract validated (core invariants)
- Phase 08: Ingestion resilience hardened (retry classification, error logging, extract_text heuristics)

## Codebase Context (Audited)
The smelter layer implementation:
- `src/utils/json_validator.py` — JSONValidator (iterative LLM-based repair) + `extract_technical_atoms`
- `src/research/domain_schema.py` — KnowledgeAtom Pydantic model
- `src/research/condensation/pipeline.py` — DistillationPipeline orchestration

### Extraction flow
1. `extract_technical_atoms` calls LLM with prompt expecting JSON `{ "atoms": [{ "type", "content", "confidence" }] }`
2. JSONValidator validates against schema; if invalid, performs up to 2 repair attempts.
3. Validated atoms are converted to KnowledgeAtom objects.
4. Each atom is stored via `store_atom_with_evidence(atom_row, evidence_rows)` linking to source_id.
5. Atom ID = `uuid5(NAMESPACE_URL, f"{mission_id}:{source_id}:{content[:200]}")` — deterministic per source.

## Must-Have Truths (Audit Verdicts)

| Truth | Verdict | Notes |
|-------|---------|-------|
| Atoms standalone | VERIFIED | Self-contained; evidence external but present |
| Evidence binding mandatory | VERIFIED | Evidence row always provided in pipeline |
| Atom types consistent and enforced | PARTIAL | Extraction produces 5 types; schema free string; no enum |
| JSON repair does not mutate meaning | REQUIRES INTERPRETATION | LLM may rephrase during repair; no semantic guarantees |
| Deduplication deterministic | PARTIAL | Per-source deterministic; global dedupe absent |
| Invalid extraction outputs rejected | PARTIAL | Hard reject for invalid atoms, but source status `condensed` may be set even when zero atoms stored (soft acceptance bug) |

## Gray Areas (Deferred)

Per user instruction, these were not decided during audit. They are flagged in audit reports.

- Deduplication scope: global vs per-source
- Evidence linkage: direct chunk references vs separate table sufficient
- Type enforcement: enum vs flexible
- JSON repair safety: tolerance for meaning changes
- Validation layering: extraction-time vs storage-time

## Audit Deliverables

- `ATOM_SCHEMA_AUDIT.md` — schema fields, evidence, types, validation
- `EXTRACTION_PIPELINE_REPORT.md` — prompts, parser, repair strategy, deduplication (high-level)
- `DEDUPE_AUDIT.md` — deduplication mechanism and determinism assessment (detailed)
- `JSON_REPAIR_AUDIT.md` — repair component safety analysis
- `ATOM_VALIDATION_AND_REJECTION_RULES.md` — rejection conditions, observability, soft acceptance bug
- `PHASE-09-VERIFICATION.md` — overall verification with `PARTIAL` verdict

## Next Steps

- Review PARTIAL/REQUIRES INTERPRETATION items.
- Decide whether to fix issues in a gap closure phase or proceed to next milestone.
- If proceeding, archive Phase 09 after addressing soft acceptance bug (source status logic) as a high-priority fix.
