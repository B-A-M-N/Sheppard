# Phase 12-B: Dual Validator Extension - Research

**Researched:** 2024-04-01
**Domain:** Fact-checking, Numeric Claim Verification, NLP/Regex
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Extend existing citation validator (`src/retrieval/validator.py`).
- Tolerance: `1e-9` for floating point, exact match for integers (Research recommendation: use `1e-6` for computed percentages to handle LLM rounding).
- Implementation depends on Phase 12-A (`engine.py`, `DerivedClaim`, derivation rules).
- No existing validation logic weakened; lexical overlap and entity consistency still run.
- Derived check is ADDITIONAL, not replacement.

### the agent's Discretion
- Detection heuristics for comparative language.
- Implementation of inline re-derivation.
- Exact regex patterns for multi-citation segments.

### Deferred Ideas (OUT OF SCOPE)
- Subjective comparison ("better than", "stronger") without numeric backing.
- Cross-section aggregation (handled by future Smelter phases).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| NUM-VER-01 | Verify derived numeric claims spanning multiple atoms | Established pattern: Parse → Extract → Compute → Verify. |
| NUM-DET-01 | Detect comparative language (delta, percent_change, rank) | Keyword-based set intersection + POS-tag-inspired regex. |
| NUM-TOL-01 | Floating-point tolerance for percentage and delta claims | Standards suggest 10^-6 to 10^-7 for computational verification. |
| NUM-PERF-01 | Inline re-derivation without circular dependencies | `engine.py` is a pure functional module; safe to import in `validator.py`. |
</phase_requirements>

## Summary

Phase 12-B extends the Sheppard truth contract from literal verification to **logical verification**. The existing validator identifies if a claim's numbers appear literally in a source; the dual validator identifies if a claim's numbers are **mathematically derived** from multiple sources.

The research confirms that a robust implementation requires three components: a **citation grouper** (to treat `[A001, A002]` as a single unit), a **comparative detector** (to identify arithmetic intent), and a **numeric normalizer** (to handle suffixes like 'M' or '%').

**Primary recommendation:** Use a triple-signal detection strategy (Multiple Citations + Numeric Value + Comparative Keywords) to trigger the `DerivationEngine` inline.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `re` | Built-in | Text parsing and citation extraction | Fast, standard, sufficient for Sheppard's needs. |
| `math` | Built-in | `isclose` comparison | Handles floating-point precision correctly. |
| `src/research/derivation/engine.py` | Phase 12-A | Arithmetic computation | Canonical source of truth for derivation rules. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| `pytest` | 7.4.3 | Verification | Testing the new validator logic. |

**Installation:**
No new packages required.

## Architecture Patterns

### Pattern 1: Citation Grouping (Regex)
Current code splits text at every individual bracketed citation. To handle multi-source claims, the validator must group adjacent citations.
**Pattern:** `((?:\[[A-Za-z0-9]+\]\s*,?\s*)+)`
**Result:** `[A001], [A002]` is captured as a single "citation part", preventing the segment from being fragmented.

### Pattern 2: Triple-Signal Detection
A claim is treated as "derived" if it satisfies three conditions:
1. **Multi-citation:** The segment's citation part contains `len(ids) >= 2`.
2. **Numeric Content:** The text contains at least one number (including decimals/percentages).
3. **Comparative Intent:** The text contains keywords like "exceeded", "increase", "rank", or "difference".

### Pattern 3: Inline Re-derivation (Interface)
The validator should not trust the `EvidencePacket`'s pre-computed claims. It must:
1. Identify the rule (e.g., "percent_change" if "%" is present).
2. Map text entities (e.g., "Revenue") to atoms.
3. Call `verify_derived_claim` from `engine.py`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Numeric Comparison | `abs(a - b) < 0.001` | `math.isclose(a, b, rel_tol=1e-6)` | Handles zero and relative scale correctly. |
| Number Extraction | `text.split()` | Robust Regex | Handles commas, decimals, and suffixes (1.2M, 15%). |
| Multi-source logic | Custom math in validator | `DerivationEngine` | Keeps math logic centralized and testable. |

## Common Pitfalls

### Pitfall 1: Citation Fragmentation
**What goes wrong:** `re.split(r'(\[A\d+\])', text)` turns `Claim [A001, A002]` into multiple segments, losing the multi-source context.
**How to avoid:** Use the non-capturing grouping regex `((?:\[[A-Za-z0-9]+\]\s*,?\s*)+)` for splitting.

### Pitfall 2: Entity-to-Atom Mapping
**What goes wrong:** In "A exceeded B by 10% [A001, A002]", the code might swap A and B, resulting in -9.09% vs 10%.
**How to avoid:** Check which atom contains which entity (Lexical overlap check handles this; use it to assign "old_value" vs "new_value" based on mention order).

### Pitfall 3: Floating Point Precision
**What goes wrong:** LLM rounds 33.333...% to "33.3%". An exact match fails.
**How to avoid:** Set tolerance to `1e-6` for percentages. This allows for rounding differences while still catching 1% errors.

## Code Examples

### Robust Numeric Extraction (Normalized)
```python
# Source: Verified WebSearch + project pattern
def extract_normalized_numeric(text: str) -> List[float]:
    pattern = r'(?i)(?:[\$€£¥]|USD|EUR|GBP)?\s*(-?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?)\s*([KMB%])?'
    matches = re.finditer(pattern, text)
    multipliers = {'K': 1e3, 'M': 1e6, 'B': 1e9, '%': 1.0} # % stays as whole number for comparison
    results = []
    for m in matches:
        val = float(m.group(1).replace(',', ''))
        suffix = m.group(2).upper() if m.group(2) else None
        if suffix in multipliers and suffix != '%':
            val *= multipliers[suffix]
        results.append(val)
    return results
```

### Citation Grouping Example
```python
# Source: Research Pattern
citation_pattern = r'((?:\[[A-Za-z0-9]+\]\s*,?\s*)+)'
text = "Company A exceeded B by 25% [A001], [A002]."
parts = re.split(citation_pattern, text)
# parts: ['Company A exceeded B by 25% ', '[A001], [A002]', '.']
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.4.3 |
| Config file | pytest.ini |
| Quick run command | `pytest tests/retrieval/test_validator.py` |
| Full suite command | `pytest tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NUM-VER-01 | Validates "A exceeded B by 25% [A001, A002]" | unit | `pytest tests/retrieval/test_validator.py` | ❌ Wave 0 |
| NUM-VER-02 | Fails "A exceeded B by 50% [A001, A002]" (math error) | unit | `pytest tests/retrieval/test_validator.py` | ❌ Wave 0 |
| NUM-DET-01 | Ignores multi-citation if no number present | unit | `pytest tests/retrieval/test_validator.py` | ❌ Wave 0 |
| NUM-PERF-01 | No regression on single-citation items | regression | `pytest tests/retrieval/test_validator.py` | ✅ Existing |

### Sampling Rate
- **Per task commit:** `pytest tests/retrieval/test_validator.py`
- **Per wave merge:** `pytest tests/`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/retrieval/test_validator_derived.py` — specific test suite for multi-citation derived claims.
- [ ] Mocks for `RetrievedItem` with specific numeric content for delta/percent tests.

## Sources

### Primary (HIGH confidence)
- `src/research/derivation/engine.py` - Core logic for re-derivation.
- `src/retrieval/validator.py` - Existing validator codebase analysis.

### Secondary (MEDIUM confidence)
- Google ClaimReview / IBM Watson Fact Check patterns - Multi-source verification strategies.
- spaCy / NLTK POS patterns - Informed the keyword-based comparative detection.

### Tertiary (LOW confidence)
- Floating-point tolerance standards - `1e-6` chosen as a pragmatic engineering compromise.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Pure Python/Regex.
- Architecture: HIGH - Triple-signal detection is a proven pattern.
- Pitfalls: MEDIUM - Entity mapping remains the trickiest edge case.

**Research date:** 2024-04-01
**Valid until:** 2024-05-01
