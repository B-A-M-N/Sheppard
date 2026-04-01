# Dual Validator Extension Report (Phase 12-B)

## Overview

Extended `src/retrieval/validator.py` to verify derived (multi-atom numeric) claims in addition to direct source claims. This enables the system to accept statements like "Company A exceeded B by 25% [A001, A002]" when correct, and FAIL when the derived value is wrong.

## Problem

The original validator checked:
1. Every citation exists in retrieved items
2. Lexical overlap ≥ 2 content words between claim and atom
3. All numbers in claim must appear in atom
4. All capitalized entities must appear in atom

**Issue**: "A exceeded B by 3 [A] [B]" with A=10, B=7 → validator FAILED because "3" doesn't appear in either atom. The derived value (10-7=3) is correct but neither atom contains "3".

## Solution

### New Checks Added

**Segment merging**: Parse response to collect all `[A] [B]` citations per text block instead of attaching only the first citation to the text.

**Derived claim detection**: When text block has:
- ≥2 citations AND
- ≥1 numeric value AND  
- Comparative language ("exceeds", "increased by X%", "difference of", "higher/lower", "decreased")

Then **recompute** the expected derived value from cited atoms and verify.

**Derived verification algorithm**:
1. Extract all numbers from sentence
2. Filter out numbers already present in any cited atom → remaining = claimed derived value
3. Extract first number from atom A and atom B
4. If "exceeds/difference/higher/lower" detected → expected = A - B
5. If "percent/%" detected → expected = ((B - A) / A) * 100
6. Compare: abs(claimed - expected) > 1e-9 → FAIL

**Entity fallback**: If an entity from the claim isn't in the extracted entity list, check case-insensitive presence anywhere in the raw atom text. This prevents false negatives from entity extraction edge cases.

## Files Modified

- `src/retrieval/validator.py`:
  - Added `COMPARATIVE_PATTERNS` constant list
  - Added `_is_comparative_claim()` helper
  - Added `_verify_derived_claim()` function
  - Added `_is_delta_pattern()` helper
  - Modified main `validate_response_grounding()` segment loop to detect and verify derived claims
  - Fixed entity extraction fallback for raw text check
  - Fixed segment merging for multi-citation text blocks

## Acceptance

- ✅ 9/9 new tests pass
- ✅ 50/50 existing tests pass (no regression)
- ✅ Correct derived claims → PASS
- ✅ Incorrect derived claims → FAIL
- ✅ Single-citation statements unchanged
- ✅ Non-comparative multi-citation statements skip derived check
- ✅ Kill test: incorrect percentage caught
