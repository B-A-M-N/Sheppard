# Sheppard V3 Hardening Gauntlet — GSD Phase Set

This directory contains 18 rigorous audit phases designed to transform Sheppard V3 from "mostly working" to **provably correct, governed, and production-grade**.

## Philosophy

- **No assumptions.** Every claim must be code-backed.
- **No skipping.** Phases build on each other.
- **No soft passes.** PASS/PARTIAL/FAIL with evidence.

## How to Execute

Each phase is a self-contained GSD unit:

1. **Read** the `PHASE-XX-PLAN.md` file
2. **Execute** via GSD workflow:
   - Use `/gsd:discuss-phase` to clarify any questions
   - Use `/gsd:plan-phase` to create execution plan
   - Use `/gsd:execute-phase` to perform the audit
   - Generate the required deliverables in the phase directory
3. **Verify** using the template in the plan
4. **Mark** the phase status (PASS/PARTIAL/FAIL) in `PHASE-XX-VERIFICATION.md`

## Phase List

| # | Phase | Directory | Deliverables |
|---|-------|-----------|--------------|
| 01 | Ground-Truth System Inventory | `phase01_inventory/` | SYSTEM_MAP.md, ENTRYPOINT_INVENTORY.md, ARCHITECTURE_TRACEABILITY.md |
| 02 | Runtime & Boot Path Validation | `phase02_boot/` | BOOT_SEQUENCE.md, CONFIG_REQUIREMENTS.md, STARTUP_FAILURE_MATRIX.md |
| 03 | Triad Memory Contract Audit | `phase03_triad/` | MEMORY_CONTRACT_AUDIT.md, STORAGE_WRITE_MATRIX.md, STORAGE_READ_MATRIX.md |
| 04 | Data Model & Lineage Integrity | `phase04_lineage/` | LINEAGE_MAP.md, ENTITY_RELATIONSHIP_AUDIT.md, ORPHAN_RISK_REPORT.md |
| 05 | `/learn` Pipeline Path Audit | `phase05_learn/` | LEARN_EXECUTION_TRACE.md, PIPELINE_STATE_MACHINE.md, QUEUE_HANDOFF_AUDIT.md |
| 06 | Discovery Engine Verification | `phase06_discovery/` | DISCOVERY_AUDIT.md, TAXONOMY_GENERATION_AUDIT.md, SEARCH_BEHAVIOR_REPORT.md |
| 07 | Distributed Queue & Worker Audit | `phase07_workers/` | WORKER_MODEL_AUDIT.md, QUEUE_SEMANTICS_REPORT.md, DUPLICATION_AND_LOCKING_AUDIT.md |
| 08 | Scraping / Content Normalization Audit | `phase08_scraping/` | CONTENT_INGEST_AUDIT.md, NORMALIZATION_SPEC_AS_IMPLEMENTED.md |
| 09 | Smelter / Atom Extraction Audit | `phase09_smelter/` | ATOM_SCHEMA_AUDIT.md, EXTRACTION_PIPELINE_REPORT.md |
| 10 | Retrieval & Interactive Agent Integration | `phase10_retrieval/` | QUERY_PATH_AUDIT.md, RETRIEVAL_GROUNDING_REPORT.md |
| 11 | Report Generation Audit | `phase11_reports/` | REPORT_PIPELINE_AUDIT.md, REPORT_INPUT_PROVENANCE.md |
| 12 | Async / Non-Blocking Execution Audit | `phase12_async/` | ASYNC_EXECUTION_MODEL.md, BLOCKING_RISK_REPORT.md |
| 13 | Failure Modes & Recovery Audit | `phase13_failures/` | FAILURE_MODE_CATALOG.md, RECOVERY_BEHAVIOR_AUDIT.md |
| 14 | Benchmark & Evaluation Contract Audit | `phase14_benchmark/` | BENCHMARK_AUDIT.md, SCORE_SEMANTICS_REPORT.md |
| 15 | Ambiguity Extraction & Correction Register | `phase15_ambiguities/` | AMBIGUITY_REGISTER.md, CONTRADICTION_LEDGER.md |
| 16 | Code Correction Plan | `phase16_correction/` | REMEDIATION_ROADMAP.md, FIX_PRIORITY_MATRIX.md |
| 17 | Enforcement & Governance Layer Spec | `phase17_governance/` | GOVERNANCE_SPEC.md, MISSION_STATE_MACHINE.md |
| 18 | Final Re-Verification Gauntlet | `phase18_final/` | FINAL_SYSTEM_AUDIT.md, PRODUCTION_READINESS_DECISION.md |

## Execution Order

**Sequential.** Phase N depends on outputs from phases 1..N-1. Do not skip.

## Dependencies

- Phases 01-05: Foundational system understanding
- Phases 06-09: Pipeline critique (depend on 05)
- Phases 10-12: Integration checks (depend on 09)
- Phases 13-14: Resilience & metrics (depend on 10-12)
- Phases 15-16: Synthesis (depend on all prior)
- Phase 17: Governance spec (depends on 16)
- Phase 18: Final judgment (depends on 17)

## Output Structure

Each phase directory will contain:

```
phaseXX_name/
├── PHASE-XX-PLAN.md          (this file - mission & prompt)
├── <required deliverables>   (filled during execution)
└── PHASE-XX-VERIFICATION.md  (verdict with evidence)
```

## Tracking Progress

Create a tracker in `.planning/gauntlet_phases/STATUS.md`:

```markdown
# Hardening Gauntlet Progress

| Phase | Status | Verdict | Notes |
|-------|--------|---------|-------|
| 01 | ⏳ | | |
| 02 | ⏳ | | |
| ... | | | |
| 18 | ⏳ | | |
```

## Hard Rules (Non-Negotiable)

- ✗ No "it should work"
- ✗ No skipping failed phases
- ✗ No merging phases
- ✗ No soft validation
- ✗ No hidden assumptions

## When a Phase Returns PARTIAL

- Document the gaps explicitly
- Do not proceed until gaps are understood
- Some partial phases may need rework after later fixes

## When a Phase Returns FAIL

- Stop and assess whether the system is salvageable
- Major architectural issues may require Phase 19 (rearchitecture)

## Support

Refer to the original megaprompt for detailed phase descriptions, hard fail conditions, and completion criteria.

---

**Begin with Phase 01.**
