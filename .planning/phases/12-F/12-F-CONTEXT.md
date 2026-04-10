# Phase 12-F — Context: Verification, Quality Gates, and Longform Enforcement

## Position in Stack

**12-F = Enforcement** — prevents the richer synthesis stack from degrading into polished nonsense.

Hard gates ensuring every sentence is grounded, every arithmetic claim is recomputed, every contradiction obligation satisfied, every section meets minimum evidence thresholds. Deterministic regeneration under same packet.

**Master Invariant:** The writer never invents intelligence; it renders intelligence already mechanically assembled upstream.

---

## Current State

**Existing validator** (`src/retrieval/validator.py`): per-section grounding check (lexical overlap, number consistency, entity matching). Extended in 12-B to verify derived numeric claims. But the validator operates at sentence level only — it doesn't enforce:
- Section-level minimum evidence thresholds
- Contradiction obligations (did section address required conflicts?)
- Expansion bounds (did elaboration stay within evidence budget?)
- Whole-report structural coherence
- Deterministic regeneration guarantees

---

## What 12-F Must Add

### Longform Verification Gates

| Gate | What It Checks | Failure Action |
|------|----------------|----------------|
| **Sentence Grounding** | Every declarative sentence mapped to atoms and/or validated derived claims | Reject sentence, mark for repair |
| **Derived Recomputation** | Every numerical/comparative claim recomputed and verified | Reject entire section if derived mismatch found |
| **Contradiction Obligation** | If SectionPlan.requires_contradiction=True, report must address conflict | Add missing contradiction section or mark report incomplete |
| **Section Evidence Threshold** | Section has ≥ N atoms and/or M derived claims | Replace section with [INSUFFICIENT EVIDENCE] placeholder |
| **No Uncited Abstraction** | Comparative/analytical claims without citations | Reject |
| **No Expansion Beyond Budget** | Expanded text references material outside SectionPlan.allowed scope | Trim back to scope |
| **Deterministic Regeneration** | Same packet → same output (LLM temperature=0, seed fixed) | Verify seed and temperature settings |

### Quality Gates

Additional quality metrics tracked (not enforced):
- Citation density (citations per 100 words)
- Unsupported sentence rate (target < 0.1%)
- Contradiction coverage rate (target > 90%)
- Derivation correctness rate (target 100%)
- Duplication rate (target < 5%)

### Failure Class Test Harness

Each of the six phases (12-A through 12-F) has a failure class that it prevents. The 12-F test harness injects failures and verifies the appropriate gate catches them:

| Failure Class | Expected Catch by Phase |
|---------------|------------------------|
| Report factual but dumb | 12-A (derived claims provide insight) |
| Lists facts but no analysis | 12-B (comparative reasoning primitives) |
| Weak internal structure | 12-C (evidence graph connects related facts) |
| Structurally incoherent | 12-D (planner enforces topology) |
| Too short/shallow/uneven | 12-E (staged composition ensures completeness) |
| Eloquence without grounding | 12-F (verification catches drift) |

### Files That Will Change

| File | Change |
|------|--------|
| `src/research/reasoning/longform_verifier.py` | NEW — LongformVerifier class with all gates |
| `src/research/reasoning/synthesis_service_v2.py` | Integrate LongformVerifier into pipeline (called between Pass 4 and final output) |
| `tests/research/reasoning/test_longform_verification.py` | NEW — gate tests, failure class tests |
| `.planning/phases/12-F/LONGFORM_VERIFICATION_SPEC.md` | NEW — spec |
| `.planning/phases/12-F/QUALITY_GATES.md` | NEW — quality metrics, thresholds |
| `.planning/phases/12-F/FAILURE_CLASS_HARNESS.md` | NEW — failure injection tests |
