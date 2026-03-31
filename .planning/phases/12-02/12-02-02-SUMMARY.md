---
phase: 12-02
plan: 02
subsystem: research/reasoning
tags: [performance, concurrency, asyncio, evidence-assembly]
dependency_graph:
  requires: [12-02-01]
  provides: [concurrent-retrieval, assemble_all_sections]
  affects: [synthesis_service, assembler]
tech_stack:
  added: []
  patterns: [asyncio.gather with return_exceptions=True, index-preserving gather, two-phase retrieval+synthesis]
key_files:
  created:
    - tests/research/reasoning/test_concurrent_assembly.py (stubs filled in)
  modified:
    - src/research/reasoning/assembler.py
    - src/research/reasoning/synthesis_service.py
    - tests/research/reasoning/test_phase11_invariants.py
decisions:
  - "assemble_all_sections uses index-preserving (order, task) tuple pattern with asyncio.gather return_exceptions=True for error isolation"
  - "LLM synthesis loop kept sequential to preserve previous_context accumulation invariant"
  - "Truth contract lines in synthesis_service unchanged: validate_grounding=2, write_section=1, citation=15"
metrics:
  duration: ~10min
  completed: 2026-03-30
  tasks_completed: 2
  files_modified: 4
---

# Phase 12-02 Plan 02: Concurrent Assembly Implementation Summary

One-liner: Concurrent section retrieval via asyncio.gather in EvidenceAssembler with index-preserving error isolation, integrated into SynthesisService two-phase retrieval+synthesis pattern.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | TDD: assemble_all_sections + tests | 227b191 | assembler.py, test_concurrent_assembly.py |
| 2 | Integrate into SynthesisService | 4311249 | synthesis_service.py, test_phase11_invariants.py |

## What Was Built

**Task 1 (TDD):**
- Filled in 3 test stubs + 1 timing test in `test_concurrent_assembly.py`
- Verified RED: 3 FAILED (assemble_all_sections missing), 2 PASSED
- Added `assemble_all_sections` method to `EvidenceAssembler` with:
  - Index-preserving `(section.order, task)` tuple pattern
  - `asyncio.gather(..., return_exceptions=True)` for failure isolation
  - Empty EvidencePacket returned on per-section failure
  - `Dict[int, EvidencePacket]` return type keyed by section.order
- Verified GREEN: 13 tests pass

**Task 2 (Integration):**
- Replaced sequential `build_evidence_packet` loop in `generate_master_brief` with two-phase approach:
  - Phase A: `await self.assembler.assemble_all_sections(...)` — concurrent retrieval
  - Phase B: Sequential synthesis loop with `all_packets.get(section.order, ...)` lookup
- Fallback EvidencePacket if section missing from dict
- Truth contract preserved: `_validate_grounding`, `write_section`, `citation` counts unchanged
- Fixed invariant tests: added `assemble_all_sections = AsyncMock` to mock_assembler setups

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed broken invariant tests after refactor**
- **Found during:** Task 2 verification
- **Issue:** test_phase11_invariants.py tests mocked `build_evidence_packet` but synthesis_service now calls `assemble_all_sections` — causing TypeError on await
- **Fix:** Added `mock_assembler.assemble_all_sections = AsyncMock(return_value={1: mock_packet})` to both affected tests
- **Files modified:** tests/research/reasoning/test_phase11_invariants.py
- **Commit:** 4311249

## Known Stubs

None — all test stubs from Plan 01 have been filled in and pass.

## Self-Check: PASSED

- [x] `async def assemble_all_sections` exists in assembler.py
- [x] `asyncio.gather` with `return_exceptions=True` exists in assembler.py
- [x] `assemble_all_sections` called in synthesis_service.py
- [x] `build_evidence_packet` not called directly in synthesis_service.py
- [x] All 13 reasoning tests pass
- [x] Commits 227b191 and 4311249 exist
