# Phase 10 Context: Retrieval & Interactive Agent Integration

## Purpose

This document defines the truth-grounded retrieval contract for Phase 10. All downstream agents (researcher, planner, implementer) must adhere to these rules when designing, building, and verifying the retrieval integration layer.

**Phase 10 Goal:** Verify that all interactive responses are grounded in stored atoms with clear, auditable provenance. The system must be **truth-bound**, not merely functional.

---

## 0. Deterministic Enforcement Rules (Non-Negotiable)

The following rules must be implemented as **hard constraints** with no discretionary interpretation:

| Rule | Check | Violation = Hard Failure |
|------|-------|------------------------|
| **Grounded answers only** | Every factual claim maps to a retrieved atom OR is a trivial rephrasing of such | Answer rejected or flagged |
| **No inference** | No claims requiring gap-filling, combination, or extrapolation beyond atom content | System prompt must forbid; LLM must not produce |
| **Binary coverage** | All material claims have at least one supporting citation; if any lack support → refusal | Must trigger fallback |
| **Explicit refusal** | When coverage fails, response is exactly `I cannot answer based on available knowledge.` | Any other response invalid |
| **Citation per claim** | Every declarative claim has at least one `[A###]` citation | LLM must not emit uncited claims |
| **Sequential citations** | Citations are `[A001]`, `[A002]`, ... per query, assigned by retrieval layer | Format deviation invalid |
| **Mandatory retrieval** | All responses originate from `query()` → retrieval context → LLM | No direct LLM paths |
| **No hard filtering** | Retrieval returns all relevant atoms regardless of confidence | No `WHERE confidence > X` |
| **Contradictions preserved** | Conflicting atoms both appear in context if relevant | Not deduped, merged, or biased |
| **Contradictions synthesized** | Response acknowledges disagreement if sources conflict | Silent unilateral synthesis invalid |
| **Eventual consistency** | Queries see only ChromaDB-indexed atoms | Dual-read forbidden in Phase 10 |
| **Indexing delay = no knowledge** | Missing atoms due to async indexing trigger fallback | Not a reason to use model priors |

These are **mechanically verifiable** attributes of the implementation. No ambiguity.

---

## 1. Grounding Definition (Strict)

**Rule:** All answers must be fully derivable from retrieved atoms.

**Derivability definition:**
- A claim is valid if it is:
  - **directly stated** in one or more retrieved atoms
  - OR a **trivial transformation** (rephrasing, aggregation, syntactic variation) that does not introduce new information or implications
- **Forbidden:** claims that require:
  - inference beyond the explicit content of atoms
  - filling gaps using model knowledge
  - combining atoms to produce new conclusions not explicitly supported
  - extrapolation or generalization

**No hybrid blending:** The system may not supplement retrieved atoms with general model knowledge and present it as a specific answer.

**Burden of proof:** The response generation logic must ensure that every factual assertion in the output is traceable to at least one retrieved atom and stays within the evidence envelope. Ambiguous or borderline claims must be omitted or qualified with uncertainty.

**Implementation implication:** The system prompt and response generation logic must encode these constraints such that the LLM cannot produce non-derivable claims even if it "wants to."

---

## 2. Fallback Behavior (Explicit Refusal)

**Rule:** When no sufficient atoms are retrieved, the system must refuse to answer with a standard message.

**Coverage criterion (binary, deterministic):**
- A response is **allowed** only if **all material claims** in the response are supported by at least one retrieved atom
- Material claim = any assertion that would affect the user's understanding or decision-making
- If **any** material claim lacks direct atom support → the response is **not allowed** → trigger fallback

**Fallback message format:** `I cannot answer based on available knowledge.`

**Trigger conditions:**
- The retrieved context is empty (no atoms found)
- The retrieved atoms do not collectively provide sufficient support for all material claims needed to answer the query
- **Concurrency edge case:** Atoms are missing from ChromaDB due to indexing delay are treated as "no knowledge available" and trigger fallback (no partial answer based on partial visibility)

**Routing:** The refusal itself routes through retrieval (i.e., retrieval runs first, then refusal logic triggers on empty/insufficient result).

**No pass-through to model's own knowledge** under any circumstances.

**Implementation implication:** The chat endpoint must check if the retrieved context fails the coverage criterion, and short-circuit with the refusal message. This is not a "soft fallback" — it's a hard stop. The coverage check must be deterministic and cannot use heuristics like "maybe good enough."

---

## 3. Citation Format (Sequential [A###])

**Rule:** Every claim in the response must be accompanied by at least one citation key in the format `[A001]`, `[A002]`, etc.

- Citation keys are assigned **during context block construction** (retrieval layer)
- They are **sequential per query** starting at `[A001]` for each user message
- The keys map 1:1 to `RetrievedItem` entries in the context
- **Every declarative claim must have at least one [A###] citation.** Uncited statements are not allowed.

**Generation enforcement:** The LLM must not produce any factual assertion that is not immediately followed by a citation. The system prompt must state: "Every claim must cite at least one source using the [A###] keys provided in the knowledge section. If you cannot cite a claim, do not include it."

**Implementation implication:**
- `build_context_block()` must generate sequential citation keys and ensure each `RetrievedItem` has a `citation_key` in its metadata
- The citation keys must appear both in the context block and be instructing the model to use them inline
- The system prompt must include a hard constraint: "No uncited claims."

---

## 4. Routing (Mandatory Retrieval)

**Rule:** **All** responses must pass through the atom retrieval pipeline.

- This includes:
  - Refusals (still run retrieval to determine emptiness)
  - Meta-responses about system capabilities
  - Casual conversational turns
  - Any user message that receives a response

**No bypass paths** of any kind:
- No "direct model" mode (i.e., calling LLM without retrieval context)
- No special-case handlers that skip `V3Retriever`
- No "memory-only" fallback (V2 MemoryManager is deprecated and must not be used)
- **No direct LLM answering path exists or may be introduced outside the retrieval-gated flow**

**Implementation implication:** The entire chat endpoint must be gated by `system_manager.query()` first; no early returns that skip retrieval. There must be **zero** code paths that invoke the LLM without first constructing a retrieval context, even for refusal or meta messages. This is a hard architectural constraint.

---

## 5. Concurrency Model (Eventual Consistency)

**Rule:** Queries operate on **indexed atoms only**.

- The retrieval layer queries ChromaDB exclusively
- There is an inherent window between Postgres commit and ChromaDB indexing completion during which a newly stored atom is **not visible to queries**
- This is an **explicit, documented limitation** of the Phase 10 architecture
- **Do NOT introduce dual-read (Postgres+Chroma) in Phase 10** to close this gap

**Indexing delay fallback:** Absence of atoms due to indexing delay is treated as "no knowledge available" and triggers the explicit refusal fallback (Section 2). The system must **not** attempt to answer based on prior knowledge or speculation during the delay window.

**Implementation implication:** The system design accepts that immediate availability of freshly condensed atoms is not guaranteed. Monitoring indexing lag may be added later as an ops concern, but not part of the truth contract. The fallback behavior remains consistent regardless of why atoms are missing.

---

## 6. Quality Handling (No Hard Filtering)

**Rule:** Retrieval must return **all relevant atoms**, regardless of confidence score.

- **Allowed:** ranking/reordering by quality metrics (if a re-ranker exists)
- **Forbidden:** excluding atoms based on a confidence threshold
- Rationale: confidence is a heuristic; truth verification occurs at synthesis/answer time, not retrieval exclusion
- Even low-confidence atoms that are semantically relevant must be included; the LLM can choose to trust or disregard them

**Implementation implication:** The `V3Retriever.retrieve()` method must not apply any `WHERE confidence > X` filters. It should return the full result set from the vector search (with optional re-ranking, but no removal).

---

## 7. Contradiction Handling (Returned, Not Resolved)

**Rule:** Contradictory atoms must **not be hidden, deduped, or silently merged**.

- If two atoms express conflicting facts and both are relevant to the query, both must appear in the retrieved context
- The retrieval layer does **not** attempt contradiction detection or resolution
- The system must not bias toward one over the other in the context construction (no "preferred" side selection)

**Synthesis constraint:** When contradictory atoms are present, the response generation layer **must not** synthesize a single definitive claim that favors one side without explicitly acknowledging the contradiction. If the query warrants an answer that addresses the conflict, the answer must include a statement reflecting that the sources disagree.

**Example (acceptable):** "Sources differ on this point. [A001] says X, while [A002] says Y."

**Example (unacceptable):** Quietly using one source and ignoring the other to produce a seemingly definitive answer.

- **Optional:** The context block may include a note like `[Note: Contradictory information present in sources]` (nice-to-have, not required)

**Implementation implication:** No additional logic in `V3Retriever` to collapse conflicts. The evidence items are presented as-is. The `contradiction` flag in the atom metadata can be ignored by retrieval; it's there for later analytics. The LLM system prompt must include the synthesis constraint.

---

## 8. Grounding Enforcement at Response Generation

**System Prompt Requirements:**

```
You are a grounded research assistant.

- Use ONLY the retrieved knowledge to answer. Do not use your general training.
- Every claim must be directly supported by at least one of the provided sources.
- Cite claims inline using the [A###] keys from the knowledge section. Every declarative claim must have a citation.
- If the knowledge does not contain sufficient information to answer, say "I cannot answer based on available knowledge."
- Do not make assumptions or inferences beyond what the sources explicitly state.
- If sources contradict each other, you must acknowledge the disagreement rather than presenting a single definitive answer.
```

**Key constraints encoded:**
- No inference: no filling gaps, no combining atoms to create new conclusions, no extrapolation
- Trivial transformations only: rephrasing/summarization that preserves exact meaning is permitted; any claim that adds information is forbidden
- Binary coverage: If you cannot cite a material claim, omit it; if omission makes the answer incomplete, refuse to answer
- Contradiction handling: When multiple sources conflict, explicitly reflect that conflict in your response

**Implementation:** The `system.py` prompt template (`get_system_prompt`) must incorporate these constraints exactly. No softening language. The prompt must be structured such that the LLM understands it **cannot** answer if it cannot cite or if contradictions would force it to choose sides.

---

## 9. Validation & Verification Criteria

For a Phase 10 implementation to pass verification, it must demonstrate:

1. **Traceability:** Every assertion in a sampled response can be mapped to a specific `[A###]` citation that corresponds to a stored atom
2. **Refusal correctness:** Queries with no relevant atoms produce the exact refusal message and do not hallucinate
3. **No bypass:** No code paths that skip `query()` for interactive messages
4. **Completeness:** Contradictory and low-confidence atoms are not filtered out before reaching the LLM
5. **Conformance:** System prompt matches Section 8 verbatim (semantic equivalent acceptable)

**Test method:** Generate responses on edge-case prompts; inspect atom retrieval, context block, and final output; verify all claims are cited and drawn from the retrieved set.

---

## 10. Out of Scope for Phase 10 (Do Not Implement)

- Advanced reranking algorithms
- Citation UI/formatting (plain text [A###] is sufficient)
- Ranking by authority or trust
- Query understanding enhancements
- Performance optimization
- Real-time dual-read consistency fixes
- Contradiction resolution
- Confidence-based filtering

**Focus: Truth path correctness only.** These optimization/resolution concerns belong to later phases (11+).

---

## Summary

Phase 10 defines the **truth contract**:

> The system answers only from what it has stored, cites everything, refuses when unknown, and preserves all evidence regardless of quality or conflicts.

Everything else (ranking, synthesis quality, performance) builds on top of this foundation.
