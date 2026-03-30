# Context Assembly Audit: TCR Compliance for Phase 10 PLAN-02

## Overview

This document maps the Truth Contract Requirements (TCRs) 5, 6, and 7 to the implemented code changes. It verifies that the retrieval integration adheres to the strict truth-grounded contract defined in PHASE-10-CONTEXT.md.

## TCR 5: Indexing Delay → Fallback

**Requirement:** When atoms are missing due to async indexing (or any reason), the system must not fall back to model priors; it must explicitly refuse with "I cannot answer based on available knowledge."

**Implementation:**

- `SystemManager.chat()` (in `src/core/system.py`) now checks whether the retrieved `context_block` is empty after stripping whitespace.
- If empty, the method yields the exact refusal message and returns immediately, bypassing the LLM call.

```python
# In system.py chat()
if not context_block.strip():
    yield "I cannot answer based on available knowledge."
    return
```

**Location:** `src/core/system.py` lines ~240-243 (after latest edit).

**Verification:** Manual testing confirms that when no atoms match the query, the refusal is shown.

---

## TCR 6: No Confidence Filtering

**Requirement:** Retrieval must return all relevant atoms regardless of confidence score; no hard threshold exclusion.

**Implementation:**

- `V3Retriever.retrieve()` (in `src/research/reasoning/v3_retriever.py`) calls `self.adapter.chroma.query()` with the user's query and returns all results provided by Chroma without applying any confidence cutoff.
- The query uses `limit=query.max_results` which is a top-K limit, not a confidence threshold.
- `build_context_block()` includes all items in the context without filtering.

**Location:** `src/research/reasoning/v3_retriever.py`, lines 51-81 (retrieve method). No code removes items based on relevance_score or trust_score.

**Verification:** Code inspection confirms absence of any `WHERE confidence > X` clauses.

---

## TCR 7: Contradictions Preserved

**Requirement:** Contradictory atoms must not be hidden, deduped, or silently merged. Both (or all) relevant perspectives must appear in the retrieved context. The synthesis layer must acknowledge disagreements if sources conflict.

**Implementation:**

- The `V3Retriever.retrieve()` method populates `ctx.contradictions` list (currently sourced from potential future conflict detection). Even if contradictions are not explicitly labeled, evidence items that conflict are both present in `ctx.evidence`.
- `build_context_block()` outputs the `contradictions` section (if any) separately, ensuring visibility.
- The system prompt (see `_build_system_prompt` in `src/core/system.py`) explicitly instructs: "If sources contradict each other, you must acknowledge the disagreement rather than presenting a single definitive answer."

**Locations:**
- Contradiction population: `src/research/reasoning/v3_retriever.py` (retrieve method – contrasts with evidence, but currently not auto-detecting; however, any atoms marked as contradictions elsewhere would appear).
- Conflict acknowledgment instruction: `src/core/system.py`, `_build_system_prompt`.
- Context formatting: `build_context_block()` includes both evidence and contradictions sections.

**Verification:** Manual inspection of context blocks shows all returned items; the prompt constrains the LLM.

---

## Additional Compliance

### Mandatory Retrieval & Sequential Citations

- All chat queries go through `SystemManager.chat()` → `V3Retriever.retrieve()` → Chroma query (no bypass).
- `build_context_block()` assigns sequential citation keys `[A001]`, `[A002]`, ... per query, overriding any stored keys. The keys are referenced in the context block and the system prompt requires inline citation using `[A###]`.

### Grounding Prompt

The system prompt embedded in `SystemManager._build_system_prompt()` matches the truth contract exactly:

```
You are a grounded research assistant.
- Use ONLY the retrieved knowledge to answer. Do not use your general training.
- Every claim must be directly supported by at least one of the provided sources.
- Cite claims inline using the [A###] keys from the knowledge section. Every declarative claim must have a citation.
- If the knowledge does not contain sufficient information to answer, say "I cannot answer based on available knowledge."
- Do not make assumptions or inferences beyond what the sources explicitly state.
- If sources contradict each other, you must acknowledge the disagreement rather than presenting a single definitive answer.
```

### Validation Before Yield

- `ChatApp.process_input()` now collects the full LLM response, then uses `ChatResponseValidator` to verify the presence of at least one citation and other coherence checks before any content is yielded to the user.
- If validation fails, the response is replaced with the refusal message.
- The explicit refusal is not subjected to validation, allowing it to pass.

---

## Test Coverage

While automated unit tests for these specific TCRs are not present in the repository, the following manual verification steps were performed:

1. **Fallback behavior:** Simulated a query with no matching atoms (e.g., gibberish) and confirmed the refusal message is returned.
2. **Citation presence:** Inspected the context block for a known query; verified that each bullet point includes a sequential `[A###]` key.
3. **No confidence filtering:** Reviewed `V3Retriever.retrieve()` to ensure no `WHERE confidence > ...` logic.
4. **Contradiction handling:** Confirmed that both evidence and contradictions sections are rendered and that the system prompt covers acknowledgment.
5. **Regression:** Ran a few sample queries that should produce answers; verified responses contain citations and remain grounded.

---

## Files Modified

- `src/research/reasoning/v3_retriever.py`
- `src/core/system.py`
- `src/llm/validators.py`
- `src/core/chat.py`

These changes implement the truth contract without weakening any existing invariants.
