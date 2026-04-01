---
phase: 12-B
plan: 01
type: tdd
depends_on:
  - 12-A  # derivation engine (compute_delta, compute_percent_change, compute_rank)
files_modified:
  - src/retrieval/validator.py
  - tests/retrieval/test_validator_derived.py
autonomous: true
requirements:
  - DERIV-04  # validator extension
  - DERIV-05  # determinism / kill tests (validator catch test)

must_haves:
  truths:
    - "validator detects multi-atom numeric claims (delta/percent/rank relationships)"
    - "validator recomputes derived value from cited atoms and compares to claimed value"
    - "validator FAILS if recomputed value differs from claimed value beyond tolerance"
    - "validator PASSES single-citation statements via existing path (no regression)"
    - "validator PASSES non-comparative multi-citation statements (skip derived check)"
    - "tolerance: 1e-9 for floating point, exact match for integers"
  artifacts:
    - path: "src/retrieval/validator.py"
      provides: "Extended validate_response_grounding with derived claim verification"
      exports:
        - validate_response_grounding  # existing function, now with derived check
    - path: "tests/retrieval/test_validator_derived.py"
      provides: "Tests for derived claim validation: correct, incorrect, single-citation, non-comparative, validator catch kill test"
      exports:
        - test_validator_correct_derived_delta
        - test_validator_correct_derived_percent
        - test_validator_incorrect_derived_delta
        - test_validator_incorrect_derived_percent
        - test_validator_single_citation_still_passes
        - test_validator_non_comparative_multi_citation
        - test_validator_kill_test_incorrect_percentage
  key_links:
    - from: "src/retrieval/validator.py"
      to: "src/research/derivation/engine.py"
      via: "from research.derivation.engine import compute_delta, compute_percent_change, verify_derived_claim"
      pattern: "from research\\.derivation\\.engine import"
---

<objective>
Extend validate_response_grounding() to verify derived (multi-atom numeric) claims. TDD approach: write tests first, then extend validator.

Purpose: Enable statements like "A exceeded B by 25% [A001, A002]" to pass validation when correct, and FAIL when incorrect.

Output:
- src/retrieval/validator.py — extended with derived claim check
- tests/retrieval/test_validator_derived.py — derived claim validation tests
- .planning/phases/12-B/DUAL_VALIDATOR_REPORT.md — specification doc
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/plan-phase.md
</execution_context>

<context>
@.planning/phases/12-B/12-B-CONTEXT.md
@.planning/phases/12-A/12-A-RESEARCH.md
@.planning/phases/12-A/12-A-CONTEXT.md
@.planning/phases/12-A/DERIVATION_VALIDATION.md

<interfaces>
**Current validator** (src/retrieval/validator.py):
```python
def validate_response_grounding(
    response_text: str,
    retrieved_items: List[RetrievedItem]
) -> Dict[str, Any]:
    # Returns: {'is_valid': bool, 'errors': list, 'details': list}
```

**Extension point**: After existing numeric consistency check (line ~152), add derived claim check BEFORE the `details.append({'claim': text, 'cited': cite, 'valid': True})` success line.

**Import from 12-A:**
```python
from research.derivation.engine import compute_delta, compute_percent_change, verify_derived_claim
```

**Derived claim detection heuristics:**
1. Segment cites ≥2 atoms (citation keys present)
2. Segment contains ≥1 numeric value
3. Segment contains comparative language: "higher", "lower", "exceeds", "increased by", "decreased", "by X%", "less than", "more than", "first", "second", "ranked", "top", "bottom"

**Validation algorithm for derived claims:**
1. Extract claimed number from sentence (first numeric value not in citation brackets)
2. Extract all cited atom IDs
3. Look up retrieved_items by citation_key
4. If 2 atoms found: compute expected delta/percent from atom contents
5. Compare claimed vs expected: abs(claimed - expected) > tolerance → FAIL
</interfaces>
</context>

<feature>
  <name>Dual Validator Extension</name>
  <files>
    src/retrieval/validator.py
    tests/retrieval/test_validator_derived.py
  </files>
  <behavior>
    RED phase — write tests first:

    1. test_validator_correct_derived_delta:
       "A exceeded B by 3 [A, B]" with A="10 units", B="7 units" → is_valid=True

    2. test_validator_correct_derived_percent:
       "B is 25% lower than A [A, B]" with A="100", B="75" → is_valid=True

    3. test_validator_incorrect_derived_delta:
       "A exceeds B by 50 [A, B]" with A="10", B="7" → is_valid=False (delta is 3, not 50)

    4. test_validator_incorrect_derived_percent:
       "B is 50% higher than A [A, B]" with A="100", B="75" → is_valid=False (should be -25%)

    5. test_validator_single_citation_still_passes:
       "A reported 10 units [A]" with atom containing "10" → existing path, passes

    6. test_validator_non_comparative_multi_citation:
       "A and B are both important [A, B]" → no numeric relationship detected, existing path

    7. test_validator_kill_test_incorrect_percentage:
       "B decreased 80% from A [A, B]" with A="100", B="75" → FAIL (should be 25% decrease, not 80%)

    GREEN: extend validate_response_grounding with derived claim detection + recomputation
    REFACTOR: extract helper functions (_detect_derived_claim, _extract_claimed_number, _recompute_from_atoms)
  </behavior>
</feature>

<implementation>
  RED → GREEN → REFACTOR:

  RED: Write test_validator_derived.py with 7 tests above.
  Run: confirm tests fail for right reasons (not ImportError)

  GREEN: In validator.py:
    1. Add import: from research.derivation.engine import compute_delta, compute_percent_change, _extract_numbers
    2. Add helper: _detect_derived_claim(text) -> Optional[str]  # returns rule type or None
    3. Add helper: _extract_claimed_number(text) -> Optional[float]
    4. Modify segment loop: if segment has ≥2 citations AND numeric content AND comparative language:
        a. Recompute expected value from cited atoms
        b. Compare: abs(claimed - expected) > tolerance → add error
    5. Keep ALL existing checks running (no removal)

  REFACTOR:
    - Extract _is_numeric_claim(text) helper
    - Extract _identify_relationship(text) helper
    - Remove debug prints
    - Ensure existing test suite passes unchanged
</implementation>

<verification>
  <automated>cd /home/bamn/Sheppard && python -m pytest tests/retrieval/test_validator_derived.py -v</automated>
  <automated>cd /home/bamn/Sheppard && python -m pytest tests/research/ -x -q</automated>
  <automated>python -c "from src.retrieval.validator import validate_response_grounding; print('Import OK')"</automated>
</verification>

<success_criteria>
- tests/retrieval/test_validator_derived.py exists with at least 7 test functions
- `python -m pytest tests/retrieval/test_validator_derived.py -v` exits 0, all green
- `python -m pytest tests/research/ -x -q` exits 0 (no regression)
- Correct derived claims PASS validation
- Incorrect derived claims FAIL validation
- Single-citation statements unchanged (existing path)
- Non-comparative multi-citation statements skip derived check (existing path)
- Tolerance: 1e-9 for floating point comparison
- Documentation artifact: DUAL_VALIDATOR_REPORT.md created
</success_criteria>

<output>
After completion, create `.planning/phases/12-B/12-B-SUMMARY.md`
</output>
