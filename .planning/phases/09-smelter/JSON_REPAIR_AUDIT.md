# Phase 09 Audit: JSON Repair

**Date:** 2026-03-29

---

## Repair Component

`JSONValidator.validate_and_fix_json` in `src/utils/json_validator.py` (lines 22-112).

## Strategy

1. Try to parse initial response; extract JSON via `_extract_json`.
2. If parse/validation fails:
   - If no JSON at all: prompt LLM to reformat the text into valid JSON.
   - If JSON present but invalid: prompt LLM to correct the JSON to match the schema.
3. Up to 2 repair attempts (`max_attempts=2`).
4. If all attempts fail: `_create_fallback_response` fills required fields with placeholder values (e.g., `"Fallback type"`, `["Fallback item"]`).

## Safety Concerns

- **LLM-based repair** can rephrase content while fixing structure. The prompt asks to "fix this JSON" — the model may change wording to ensure syntactic correctness.
- No content fingerprinting: original content not compared to repaired content; semantic drift not detected.
- Fallback response is syntactically valid but semantically generic; caller filters atoms containing "Fallback".

## Interim Rule Applied

- Syntax-only repair is presumed acceptable; meaning-changing repair is unsafe unless bounded.
- **Assessment:** The current repair approach **does not guarantee** syntax-only; it allows content alteration. This is a **potential meaning mutation** risk.

## Classification

`REQUIRES INTERPRETATION` — Does the plan's "JSON repair safe (does not mutate meaning)" tolerate LLM rephrasing? If not, this is a `FAIL`. If fallback filtering is deemed sufficient mitigation, then `PARTIAL`.

---
