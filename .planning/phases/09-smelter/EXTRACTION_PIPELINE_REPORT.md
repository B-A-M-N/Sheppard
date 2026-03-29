# Phase 09 Audit: Extraction Pipeline

**Date:** 2026-03-29
**Auditor:** Phase 09 Execution
**Scope:** Extraction prompts, parsing flow, JSON repair strategy, deduplication logic

---

## Extraction Prompt

**Location:** `src/utils/json_validator.py`, function `extract_technical_atoms`, lines 295-312.

**Prompt content:**
```
Analyze this technical document about "{topic}".
Extract a list of Knowledge Atoms (standalone technical facts, claims, or procedures).

Output ONLY a valid JSON object matching this schema:
{
  "atoms": [
    {
      "type": "claim|evidence|event|procedure|contradiction",
      "content": "the precise technical statement",
      "confidence": 0.9
    }
  ]
}

DOCUMENT CONTENT:
{text[:4000]}
```

- Temperature: 0.2 (low for precision)
- Model: invoked via `llm_client.chat` (Ollama)
- Text truncated to 4000 chars (first 4k of source)

---

## Parser Algorithm

**Entry:** `extract_technical_atoms` (async)
1. Send prompt to LLM; stream response into `response_content`.
2. Create `JSONValidator` with `max_attempts=2`.
3. Call `validator.validate_and_fix_json(llm_client, response_content, schema)`.
4. Validator either returns valid JSON or falls back to minimal schema-compliant dict.
5. Extract `atoms` array; filter out any atom where `content` contains "Fallback".
6. Return list of atom dicts (each with `type`, `content`, `confidence`).

**Downstream conversion:** In `src/research/condensation/pipeline.py` (lines 81-117):
- Each atom dict becomes a `KnowledgeAtom` object.
- `atom_id` computed as: `uuid5(NAMESPACE_URL, f"{mission_id}:{source_id}:{content[:200]}")`
- `importance` boosted if `type == "contradiction"`.
- Stored via `store_atom_with_evidence(atom_row, evidence_rows)` with evidence linking to `source_id`.

---

## JSON Repair Strategy

**Component:** `JSONValidator` class in `src/utils/json_validator.py`, method `validate_and_fix_json`.

**Repair flow:**
1. Try direct parse of extracted JSON from response (`_extract_json`).
2. If parse fails or schema validation fails:
   - If `current_json is None` (completely unparsable): prompt LLM to reformat the text into valid JSON.
   - If JSON exists but invalid: prompt LLM to correct the JSON to match the schema.
3. Up to `max_attempts` (2) repair attempts.
4. If all fail: return `_create_fallback_response(schema)` which fills required fields with placeholder values (e.g., `"Fallback type"`).
5. Caller filters out any atom with "Fallback" in content.

**Repair characteristics:**
- Uses LLM to generate corrected JSON; can rephrase content if needed to satisfy schema.
- The repair prompt asks to "fix this JSON" — may alter wording if model deems necessary.
- No checksums or content fingerprinting to ensure semantic preservation across repair.
- Fallback response is syntactically valid but semantically generic; filtered by caller.

**Safety assessment:** Syntax-only repair is **not guaranteed**. The LLM could rephrase content while fixing structure. However, fallback filtering removes obviously placeholder atoms. The repair is presumptively **meaning-changing** unless proven otherwise.

**Status:** `REQUIRES INTERPRETATION` — Could alter atom content during repair; must decide if this violates "JSON repair safe (does not mutate meaning)". If strict preservation is required, this likely `FAIL`. If syntactic validity with fallback is acceptable, then `PARTIAL`.

---

## Deduplication Logic

**Location:** `src/research/condensation/pipeline.py`, lines 86-88.

**Mechanism:**
- Atom ID is deterministic **per source**: `uuid5(NAMESPACE_URL, f"{mission_id}:{source_id}:{content[:200]}")`.
- If the same atom content appears in **multiple sources**, different `source_id` values produce different atom_ids → **not deduplicated globally**.
- No cross-source deduplication implemented; method `consolidate_atoms` is a stub (line 154-156).
- Storage: Each atom is stored independently; duplicate content across sources creates multiple atom records.

**Determinism:** Within a single source, identical content yields same atom_id (content[:200] hash). However, if the same source is processed twice (rare), same atom_id would be reused (idempotent per source).

**Global deduplication:** Absent.

**Status:** `PARTIAL` — Deduplication is deterministic per source but not global. Does this violate "deduplication deterministic"? Possibly `REQUIRES INTERPRETATION` if the requirement means "same content always yields same atom regardless of source." The current implementation minimizes per-source duplicates but allows cross-source redundancy.

---

## Evidence Binding Details

Evidence is attached via `store_atom_with_evidence(atom_row, evidence_rows)` with:
```python
evidence_rows = [{
    "source_id": source_id,
    "evidence_strength": 0.9,
    "supports_statement": True
}]
```
Evidence linkage is explicit and mandatory in the extraction pipeline (always one evidence row per atom, referencing the originating source). The evidence table likely stores chunk-level references; `source_id` alone is coarse but sufficient for provenance at source level.

**Status:** `VERIFIED` — Evidence binding is explicit and enforced by pipeline code.

---

## Invalid Extraction Rejection

**Failure modes:**
- LLM returns non-JSON or malformed JSON → JSONValidator attempts repair.
- Repair fails after 2 attempts → fallback response with "Fallback" placeholders.
- Caller filters out fallback atoms → returns empty list if none valid.
- Pipeline catches exceptions at source level; marks source status `error`.

**Rejection behavior:** Invalid outputs are **not stored**. They are either repaired or discarded. No soft acceptance.

**Status:** `VERIFIED` — Hard rejection with clear error handling; source marked as error.

---

## Summary of Findings

| Area | Status | Notes |
|------|--------|-------|
| Prompt strategy | VERIFIED | Clear instructions, limited types, low temperature |
| Parser flow | VERIFIED | JSONValidator with repair loop; fallback filtering |
| JSON repair safety | REQUIRES INTERPRETATION | LLM may rephrase content during repair |
| Deduplication | PARTIAL | Per-source deterministic; global dedupe pending |
| Evidence binding | VERIFIED | Mandatory evidence row per atom |
| Invalid rejection | VERIFIED | Hard reject; source marked error |

---
