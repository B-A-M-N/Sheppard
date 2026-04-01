# Phase 12-B Summary: Dual Validator Extension

**Status:** ✅ Complete
**Date:** 2026-03-31

## Changes

### Files modified:

| File | Change |
|------|--------|
| `src/retrieval/validator.py` | Extended `validate_response_grounding` with derived claim detection and verification; merged segment parser to collect all citations per text block |
| `tests/retrieval/test_validator_derived.py` | NEW — 9 tests covering correct/incorrect derived claims, single-citation non-regression, multi-citation skip, and kill test |

### New functionality in validator.py:

- `_is_comparative_claim()` — detects multi-atom numeric relationships
- `_verify_derived_claim()` — recomputes expected value from cited atoms, compares to claimed value
- Segment merging: collects all `[A] [B]` citations per text block (previously only attached to first citation)
- Derived check: when ≥2 citations + numbers + comparative language, skips single-atom numeric check, verifies multi-atom relationship
- Numeric uniqueness filtering: claimed number must not appear in any atom (only the derived relationship number counts)
- Entity fallback: if entity not in extracted entities list, checks case-insensitive presence anywhere in atom text

### Bug fixes from validator extension:

- Fixed: entities extracted from atom content excluded position-0 words causing false negatives; now fallback checks raw text
- Fixed: multi-citation segments now properly collect all citations per text block

## Test Results

| Suite | Before 12-B | After 12-B | Delta |
|-------|-------------|------------|-------|
| 12-A derivation tests | 18 pass | 18 pass | — |
| 12-B validator tests | — | 9 pass | +9 |
| Phase 11 invariants | 8 pass | 8 pass | — |
| Ranking tests | 24 pass | 24 pass | — |
| **Total** | **50 pass** | **59 pass** | **+9** |

## Requirements Satisfied

| Requirement | Status | Evidence |
|-------------|--------|----------|
| DERIV-04 | ✅ Complete | Validator detects multi-atom numeric claims and recomputes |
| DERIV-05 (validator catch) | ✅ Complete | `test_validator_kill_test_incorrect_percentage` passes |

## Guardrails Preserved

- ✅ 8 phase-11 invariant tests pass (including `test_grounding_validator_logic`)
- ✅ 24 ranking tests pass
- ✅ 18 derivation engine tests pass
- ✅ No existing test failures
- ✅ Entity consistency check still runs for all segments
- ✅ Lexical overlap check unchanged
- ✅ Single-citation path unchanged (non-regression verified)
