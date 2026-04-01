# Phase 12-B: Dual Validator Extension - Research

**Researched:** 2026-04-01
**Domain:** Grounding Validation & Analytical Reasoning
**Confidence:** HIGH

## Summary

Phase 12-B focuses on extending the Sheppard "Truth Contract" from simple fact verification to **analytical verification**. This is achieved through the **Dual Validator** pattern, which verifies both the atomic premises (Direct Validation) and the logical/mathematical relationships between them (Derived Validation).

The current system has a "preview" implementation of derived claim verification for `delta` and `percent_change`. However, this logic is currently decoupled from the `DerivationEngine` and lacks support for more complex analytical operators like ranking, consensus detection, and tradeoff analysis. This phase will unify the validator with the derivation engine and implement a suite of deterministic "Analytical Operators" that provide the cognitive synthesis layer for v1.2.

**Primary recommendation:** Unify `src/retrieval/validator.py` with `src/research/derivation/engine.py` using a "Detect-Resolve-Compute-Compare" pipeline that treats the engine as the sole authority for derived truth.

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **LLM-Free Determinism:** All analytical operators and derivation rules must be deterministic, pure functions with zero LLM calls.
- **Master Invariant:** The writer (synthesis engine) never invents intelligence; it only renders intelligence already mechanically assembled upstream.
- **Dual Validator Role:** The validator extension serves as the "safety gate" to ensure derived claims written by the LLM are correct before the report is accepted.

### the agent's Discretion
- **Implementation of Operators:** The specific logic for `compare_contrast_bundle`, `consensus_divergence`, etc., is at the agent's discretion, provided it remains deterministic.
- **Heuristic Selection:** Heuristics for detecting "claimed values" vs "input values" in natural language can be refined based on performance.

### Deferred Ideas (OUT OF SCOPE)
- **Deep Semantic Inference:** Logical deductions requiring world knowledge or common sense reasoning (e.g., "A causes B") remain out of scope for deterministic validation.
- **Vague Quantitative Claims:** Statements like "significantly higher" without a numeric percentage or delta will skip derived validation and fall back to lexical overlap.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VAL-12B-01 | Unify validator with DerivationEngine | `engine.py` already contains verification helpers; `validator.py` needs to import and use them to avoid logic drift. |
| VAL-12B-02 | Multi-atom numeric support | Research shows LLMs often cite 3+ atoms for "ranking" or "averaging". Validator needs to handle list-based derivations. |
| ANALY-12B-01 | compare_contrast_bundle | Heuristic: group atoms by metadata entity, use lexical overlap to find shared metrics, classify as agreement/conflict. |
| ANALY-12B-02 | consensus_divergence | Heuristic: 3+ atoms with numeric values; if values are within a tolerance threshold, it's a "consensus". |
| ANALY-12B-03 | tradeoff_extraction | Heuristic: extract atoms with "pro/con" or "strength/weakness" tags from smelter metadata and build a matrix. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `re` | stdlib | Pattern detection | Highly efficient for detecting `[A001]` and comparative keywords. |
| `math` | stdlib | Numeric computation | Used for `delta`, `percent_change`, and `average`. |
| `src/research/derivation/engine.py` | 12-A-v1 | Derivation Rules | The canonical implementation of truth for derived facts. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `difflib` | stdlib | Lexical similarity | Useful for `compare_contrast_bundle` to find overlapping claims. |
| `statistics` | stdlib | Statistical functions | Use for `average`, `median`, and `variance` in consensus detection. |

## Architecture Patterns

### Pattern: Detect-Resolve-Compute-Compare (DRCC)
The validator should follow this pipeline for every text segment:
1. **Detect:** Does the segment cite 2+ atoms AND contain numbers AND comparative keywords?
2. **Resolve:** Map the citation keys (e.g., `[A001]`, `[A002]`) to the actual `RetrievedItem` objects.
3. **Compute:** Pass the atoms to `DerivationEngine.run()` to find all valid derived claims for that set.
4. **Compare:** Extract the "claimed value" from the text and see if it matches any of the `DerivedClaim` outputs within the specified tolerance.

### Pattern: Analytical Bundling
Analytical operators produce "Bundles" which are specialized `DerivedClaim` objects:
- **CompareBundle:** `{ "entity": "X", "agreements": [...], "conflicts": [...] }`
- **ConsensusBundle:** `{ "metric": "Y", "value": 100, "sources": ["[A1]", "[A2]", "[A3]"], "variance": 0.0 }`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Numeric Parsing | Custom split logic | `_extract_numbers` (existing) | Already handles commas, decimals, and edge cases consistently across the project. |
| Logic Verification | Inline math in validator | `DerivationEngine` | Prevents "double-entry bookkeeping" bugs where generation and validation logic diverge. |
| Entity Identification | LLM-based NER | Heuristic + Metadata | Maintains the "LLM-free" truth contract. Use metadata tags if available. |

## Common Pitfalls

### Pitfall 1: Permutation Explosion
**What goes wrong:** A claim cites `[A, B, C]`. The validator doesn't know if the LLM means `(A+B)/C` or `A-(B+C)`.
**How to avoid:** The `DerivationEngine` produces all *valid* derivations for a set. If the LLM makes a claim that matches *any* of the possible valid derivations, it is accepted. If it matches none, it fails.

### Pitfall 2: Ambiguous "Claimed Number"
**What goes wrong:** "Revenue grew from 100 [A] to 125 [B], a 25% increase." Text contains 100, 125, and 25.
**How to avoid:** Use a heuristic: The "claimed value" is the number in the text that is **not** present in any of the cited source atoms.

### Pitfall 3: Order Dependency
**What goes wrong:** `percent_change` depends on `(new - old) / old`. If citations are `[A, B]`, is A old and B new?
**How to avoid:** Use metadata (timestamps) if available. If not, check both permutations. If either matches, validation passes.

## Code Examples

### Unifying Validator with Engine
```python
# Proposed change in src/retrieval/validator.py
from research.derivation.engine import DerivationEngine, DerivationConfig

def _verify_derived_claim_v2(text, citations, item_map):
    items = [item_map[c] for c in citations if c in item_map]
    if len(items) < 2: return {'passed': True}
    
    # 1. Compute all possible derived claims for these atoms
    engine = DerivationEngine()
    possible_claims = engine.run(items)
    
    # 2. Extract claimed value from text
    claimed_val = _extract_claimed_value(text, items)
    
    # 3. Check for match
    for claim in possible_claims:
        if abs(claim.output - claimed_val) < 1e-9:
            return {'passed': True}
            
    return {'passed': False, 'errors': ["Derived claim mismatch"]}
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pytest.ini` |
| Quick run command | `pytest tests/retrieval/test_validator_derived.py` |
| Full suite command | `pytest tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VAL-12B-01 | Validator uses engine | integration | `pytest tests/retrieval/test_validator_derived.py` | ✅ |
| ANALY-12B-01| Compare/contrast bundle | unit | `pytest tests/research/reasoning/test_analytical_operators.py` | ❌ Wave 0 |
| ANALY-12B-02| Consensus verification | unit | `pytest tests/research/reasoning/test_analytical_operators.py` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `src/research/reasoning/analytical_operators.py` — Implementation of new operators.
- [ ] `tests/research/reasoning/test_analytical_operators.py` — Tests for bundle logic.
- [ ] Refactor `src/retrieval/validator.py` to remove duplicate logic.

## Sources

### Primary (HIGH confidence)
- `src/retrieval/validator.py` - Current implementation (preview).
- `src/research/derivation/engine.py` - Rule definitions.
- `12-B-CONTEXT.md` - Cognitive synthesis requirements.

### Secondary (MEDIUM confidence)
- "PaperAsk: A Benchmark for Reliability Evaluation of LLMs" (2025) - Definition of "derived claims".
- "VERIRAG" (2025) - Statistical audit methodology for RAG.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Internal modules are already defined.
- Architecture: HIGH - DRCC pattern is standard for programmatic fact-checking.
- Pitfalls: MEDIUM - Heuristics for "claimed value" can still be tricky in complex sentences.

**Research date:** 2026-04-01
**Valid until:** 2026-05-01
