# PHASE 11 VERIFICATION

**Report Generation Audit**
**Date:** 2026-03-29
**Auditor:** Claude Code

---

## Report Provenance Checklist

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Reports built only from stored atoms | **FAIL** | Uses `HybridRetriever`, not `V3Retriever` (assembler.py:37) |
| Regeneration possible from Postgres only | **FAIL** | `atom_ids_used` not stored; no deterministic traceability |
| Citations link to source metadata | **PARTIAL** | Citation keys used but may originate from wrong retriever; no validation |
| Report tied to mission_id | **FAIL** | No `mission_id` throughout synthesis pipeline |
| Evidence carry-through verified | **FAIL** | No `atom_ids_used` list; invalidator absent; word count pressure |

**Overall Verdict:** ❌ **FAIL**

---

## Evidence

### Code References

#### Violation 1: Wrong Retriever

**File:** `src/research/reasoning/assembler.py:17, 37, 105`

```python
from src.retrieval.retriever import HybridRetriever, RetrievalQuery

class EvidenceAssembler:
    def __init__(self, ollama: OllamaClient, memory: MemoryManager, retriever: HybridRetriever, adapter=None):
        self.retriever = retriever

    async def build_evidence_packet(...):
        retrieved_context = await self.retriever.retrieve(q)  # ← HybridRetriever
```

**Issue:** Locked Decision #1 requires V3Retriever **only**. `HybridRetriever` is injected and used.

---

#### Violation 2: Minimum Word Count

**File:** `src/research/archivist/synth_adapter.py:68`

```python
prompt = f"""
...
MINIMUM 1000 WORDS.
"""
```

**Issue:** Locked Decision #4 explicitly forbids word count minimums (hallucination pressure).

---

#### Violation 3: No atom_ids_used Storage

**File:** `src/research/reasoning/synthesis_service.py:69-75`

```python
await self.adapter.store_synthesis_section({
    "artifact_id": artifact_id,
    "section_name": section.title,
    "section_order": section.order,
    "inline_text": prose
    # MISSING: "atom_ids_used": [...]
})
```

**Issue:** Locked Decision #5 requires storing atom IDs per section for provenance. Not implemented; DB likely lacks column.

---

#### Violation 4: Missing mission_id

**Across all synthesis files:**

- `synthesis_service.py:26` — `async def generate_master_brief(self, topic_id: str)`
- `assembler.py:92` — `async def build_evidence_packet(self, topic_id: str, ...)`
- No occurrence of `mission_id` in any of the three main files.

**Issue:** Locked Decision #6 — mission_id is canonical; all queries must filter by mission_id. Not done.

---

#### Violation 5: Transformation-Only Not Enforced

**File:** `src/research/archivist/synth_adapter.py:16-29` (prompt)

```text
[SYSTEM: SENIOR RESEARCH ANALYST]
...
2. NO HALLUCINATION: Do NOT use your internal training data for specific metrics, dates, or detailed facts unless they are present in the snippets.
...
```

The prompt is **inconsistent**:
- Line 22 says "ONLY cite facts... that appear explicitly in the provided EVIDENCE BRIEF"
- But it does **not** forbid combining or inferring across atoms
- Does **not** require citation per sentence
- Does **not** state "if a claim is not directly supported by a citation, do not write it"

**Result:** LLM can legally (per prompt) produce prose that:
- Paraphrases multiple atoms without citing any (e.g., "Several sources indicate that...")
- Makes inferences like "Therefore, X is likely" even if atoms are factual

**Hard fail:** Report content may include **new claims** not present in any atom.

---

#### Violation 6: No Determinism

**File:** `src/research/archivist/synth_adapter.py:72-77`

```python
resp = await self.ollama.complete(
    task=TaskType.SYNTHESIS,
    prompt=prompt,
    system_prompt=SCHOLARLY_ARCHIVIST_PROMPT,
    max_tokens=3000
    # No temperature=0, no seed
)
```

**Issue:** Without fixed seed/temperature=0, identical prompt + atoms can produce different prose across runs. This breaks "regeneration possible" requirement because even with same atoms, output may drift.

---

## Lineage Breaks

| Break Point | Description | Impact |
|-------------|-------------|--------|
| Retrieval source | Uses HybridRetriever instead of V3Retriever | Atoms may not be from canonical knowledge store; cannot verify they are `knowledge_atoms` |
| Atom ID capture | `atom_ids_used` not extracted and stored | Cannot prove which specific atoms supported which claims |
| Mission scope | No `mission_id` binding | Reports cannot be scoped to a mission; cross-mission contamination possible |
| Inference allowance | Prompt permits uncited synthesis | Sentences may introduce new facts not in any atom |
| Non-determinism | No sampling control | Regeneration may produce different content, failing reproducibility |

---

## Compliance Matrix

| Locked Decision | Compliant? | Notes |
|-----------------|------------|-------|
| 1. V3Retriever ONLY | ✗ | Uses HybridRetriever |
| 2. Binary refusal for insufficient evidence | ✗ | Code calls Archivist even with empty `packet.atoms`; only shows warning |
| 3. Citation format [A###] | ✓ (syntax) | Mechanism exists, but may cite wrong sources |
| 4. Remove word count minimum | ✗ | "MINIMUM 1000 WORDS" present |
| 5. Store atom_ids_used for regeneration | ✗ | Not stored |
| 6. mission_id canonical | ✗ | Not used anywhere |
| 7. Contradictions explicitly stated | Partially | Contradictions packaged; Archivist prompt includes them; but retrieval depends on "contradictions" role |
| 8. LLM-structured reports allowed (but only organize) | N/A | Not relevant to core failure |
| 9. Report = pure transformation (zero inference) | ✗ | Prompt does not forbid inference; allows uncited claims |

---

## Hard Fail Condition Check

| Condition | Triggered? |
|-----------|------------|
| Reports are detached from lineage | ✅ YES — `atom_ids_used` not stored; no mapping |
| Reports depend on fresh browsing | ✅ NO — no web queries in synthesis code |
| Reports synthesized from vague summaries rather than atoms | ✅ YES — word count pressure + no per-sentence citation rule enables vague/hallucinated content |

**Two of three hard fail conditions are met.**

---

## Synthesis Service Activation Status

**Per context:** `SynthesisService` is disabled (`self.synthesis_service = None` in SystemManager).

**Interpretation for audit:**
- The code is **inactive** and likely **untested** in production
- The audit examines **intended behavior** if enabled
- Inactive status **increases risk** because integration issues are not observed
- **Does not excuse failures** — the implementation should comply before activation

---

## Final Verdict Reasoning

### Why NOT PARTIAL?

A `PARTIAL` verdict would indicate some dimensions pass while others fail. However, **the core mandatory requirements** (Locked Decisions 1, 5, 6) are all violated, and **hard fail conditions** are triggered. Additionally, the **transformation-only** principle (Decision 9) is not enforced.

### Why NOT PASS?

PASS requires: "reports are 100% derived from stored atoms and can be regenerated from Postgres alone."

Current state:
- ❌ Not derived from stored atoms (uses wrong retriever)
- ❌ Cannot be regenerated from Postgres (no atom list stored; no determinism)
- ❌ Not bound to mission
- ❌ Not pure transformation (inference allowed)

---

## Remediation Roadmap (Recommendations)

These are **not implemented** in Phase 11 — presented for Phase 12 or later.

1. **Replace HybridRetriever with V3Retriever** in `EvidenceAssembler`
2. **Remove "MINIMUM 1000 WORDS"** from `synth_adapter.py` prompt
3. **Add atom_ids_used field** to `EvidencePacket` and store in DB
4. **Propagate mission_id** through all synthesis functions
5. **Add explicit "no inference" constraint** to Archivist prompt:
   > "Every claim must be directly cited. Do not combine, infer, or paraphrase multiple sources without explicit citation for each claim."
6. **Add post-generation validator** to ensure all sentences have citations and all cited keys are in the evidence packet
7. **Set temperature=0 and fixed seed** in `ollama.complete()` call
8. **Update DB schema** for `synthesis_sections` to include `atom_ids_used` (JSON/array column)
9. **Update `SynthesisService`** to skip writing sections with `len(packet.atoms) < MIN_FOR_SECTION` (e.g., 3) rather than writing with warning
10. **Write unit tests** for transformation-only behavior (inject test atoms, verify output only contains cited facts)

---

## Sign-Off

**Phase 11 Status:** ❌ **FAIL**

Reports would **not** meet truth contract requirements if synthesis were enabled today.

The pipeline introduces multiple integrity risks:

- Wrong retriever (Hybrid instead of V3)
- No provenance capture
- No mission isolation
- Hallucination pressure
- Inference allowed

**Next step:** Do not enable synthesis service. Plan a remediation phase to implement all 10 recommendations above before re-audit.
