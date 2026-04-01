# Phase 12-B — Context: Dual Validator Extension

## Purpose

Extend the existing citation validator (`src/retrieval/validator.py`) to verify derived claims in addition to direct source claims. This enables the system to accept statements like "Company A exceeded B by 25% [A001, A002]" without breaking the truth contract.

---

## Prerequisites

- Phase 12-A: Derived Claim Engine must be complete (engine.py, DerivedClaim dataclass, derivation rules)
- The validator extension depends on `compute_delta`, `compute_percent_change`, `compute_rank` being importable

---

## Current Validator State

**Location:** `src/retrieval/validator.py` (171 lines)

**Current behavior** (`validate_response_grounding`):
1. Extract citations `[A###]` from response text
2. Split into alternating text/citation segments
3. For uncited text: error "Uncited claim"
4. For cited text:
   - Lexical overlap ≥2 content words
   - All numbers in claim must appear in atom
   - All capitalized entities must appear in atom
5. Returns `{is_valid: bool, errors: list, details: list}`

**Problem for derived claims:**
- "A exceeded B by 25% [A001, A002]" cites TWO atoms
- Current numeric check: "25%" must appear in A001 OR A002 → will FAIL
- Need to detect multi-atom numeric claims and recompute from source atoms

---

## Extension Design

**New check after existing numeric consistency:**
```python
# If segment cites 2+ atoms AND contains numeric relationship:
# 1. Extract numbers from sentence ("25" from "A exceeded B by 25%")
# 2. Extract relationship type (increase/decrease/rank)
# 3. Extract cited atom IDs ([A001], [A002])
# 4. Call appropriate derivation function:
#    expected_value = compute_percent_change(atom_a, atom_b)
# 5. Compare: abs(claimed_value - expected_value) <= tolerance
# 6. FAIL if mismatch
```

**Tolerance:** `1e-9` for floating point, exact match for integers

**Detection heuristics:**
- Sentence contains ≥2 citations AND a number
- Sentence contains comparative language: "higher/lower", "increased/decreased", "by X%", "exceeds", "less than", "more than", "ranked"

---

## Files That Will Change

| File | Change |
|------|--------|
| `src/retrieval/validator.py` | Extend `validate_response_grounding` with derived claim check |
| `tests/retrieval/test_validator.py` | NEW or extend existing: test derived claim validation |
| `.planning/phases/12-B/DUAL_VALIDATOR_REPORT.md` | NEW — validator extension specification |

---

## Key Integration Constraints

1. No existing validation logic weakened
2. Lexical overlap check still runs (unchanged)
3. Entity consistency check still runs (unchanged)
4. Derived check is ADDITIONAL, not replacement
5. If derived check fails → validation FAILS
6. If derived check not applicable (single citation) → skip derived check, use existing path

---

## Test Requirements

- Correct derived claim → PASS
- Incorrect derived claim → FAIL
- Single-citation statements → existing path unchanged
- Existing test suite passes (no regression)
