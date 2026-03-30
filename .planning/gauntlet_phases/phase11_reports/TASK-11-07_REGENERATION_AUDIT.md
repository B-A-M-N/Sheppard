# PHASE 11 — REPORT GENERATION AUDIT
## Task 11-07: Regeneration Capability Audit

**Auditor:** Claude Code
**Date:** 2026-03-29

---

## Audit Question

Can reports be regenerated from Postgres alone with deterministic output?

---

## Required Conditions for PASS

1. **Fixed sampling parameters** — temperature=0, fixed seed (if supported)
2. **Stored atom list** — `atom_ids_used` preserved for each section
3. **Deterministic prompt** — no random elements, consistent ordering
4. **Same model** — model version locked
5. **No external dependencies** — all inputs from Postgres/Chroma only

---

## Current Implementation Assessment

### 1. Sampling Control

**File:** `src/research/archivist/synth_adapter.py:72-77`

```python
resp = await self.ollama.complete(
    task=TaskType.SYNTHESIS,
    prompt=prompt,
    system_prompt=SCHOLARLY_ARCHIVIST_PROMPT,
    max_tokens=3000
    # No temperature, no seed
)
```

**Status:** ✗ **No determinism guarantee**
- Default Ollama temperature likely > 0
- No seed fixed
- Identical input → potentially different output across runs

**Impact:** Regeneration may produce different prose, failing reproducibility test.

---

### 2. Atom List Storage

**Status:** ✗ **Not stored** (see REPORT_INPUT_PROVENANCE.md)
- `atom_ids_used` field absent from `EvidencePacket`
- Not passed to `store_synthesis_section()`
- No way to know which atoms were used for which claims

**Impact:** Cannot validate that regenerated report uses same evidence set.

---

### 3. Prompt Determinism

The prompt includes:
- Section title and objective (deterministic)
- Evidence brief (order depends on `packet.atoms` iteration)
- Previous context (rolling context varies only by prior sections)

**Potential non-determinism:**
- `packet.atoms` order not explicitly sorted — depends on retriever order
- `previous_context[-2000:]` slice uses negative indexing, consistent but cuts context

**Assessment:** Prompt structure is deterministic, but evidence order may vary if retriever returns non-deterministic order.

---

### 4. Model Version Locking

**Not examined in this audit.** Assumption: model is fixed in configuration.

---

### 5. No External Dependencies

**Violation:** Uses `HybridRetriever` (which may query additional sources beyond V3 atoms)
**Violation:** No `mission_id` binding (could pull from wrong topic scope)

Even if determinism were perfect, the **input source** is not pure.

---

## Regeneration Test Feasibility

Given current code, regeneration would require:

1. Re-enable `SynthesisService` (currently disabled)
2. Provide same `topic_id` (but not mission-scoped)
3. Ensure `HybridRetriever` returns identical results (unlikely without fixed seed in retriever too)
4. Accept that output may differ due to LLM sampling
5. Accept that atom list is unknown, so cannot verify same atoms used

**Conclusion:** Regeneration is **not feasible** in any provable sense.

---

## Verdict

| Requirement | Pass? | Evidence |
|-------------|-------|----------|
| Fixed sampling parameters | ✗ | No temperature/seed in `ollama.complete()` |
| Stored atom list | ✗ | `atom_ids_used` not captured or stored |
| Deterministic prompt | ⚠️ | Structure OK, but evidence order unspecified |
| Model version locked | ? | Not verified |
| Pure V3 inputs | ✗ | Uses `HybridRetriever` |

**Overall:** ❌ **FAIL**

---

## Evidence Reference

- `src/research/archivist/synth_adapter.py:72-77` — missing sampling control
- `src/research/reasoning/synthesis_service.py:69-75` — no atom list stored
- `src/research/reasoning/assembler.py:105` — non-deterministic retriever order possible

---

**Task 11-07 complete.** Ready for final deliverables compilation (11-08) and verification production (11-09).
