# Phase 12-B Research: Dual Validator Extension

## Research Scope

Investigate how to extend the citation validator (`src/retrieval/validator.py`, 171 lines) to verify derived numeric claims that span multiple source atoms — claims like "A exceeded B by 25% [A001, A002]" where the numeric relationship is computed, not literal.

---

## Current State Analysis

### Existing Validator Flow (`validate_response_grounding`, lines 59-170)

The validator operates on two levels — segment-level then per-citation:

1. **Segment extraction** (lines 89-106): Splits prose on citation markers `[A###]` into alternating text/citation segments using regex `(\[[A-Za-z0-9]+\])`
2. **For each cited segment** (lines 112-163), runs three checks:
   - **Lexical overlap** (lines 134-141): Extracted content words from claim ∩ atom content. Requires ≥2 overlapping words. Stopword set is comprehensive (~100 words including contractions).
   - **Numeric consistency** (lines 143-152): Every number in the claim must appear in the atom. Pattern `\d[\d,]*\.?\d*` extracts integers/decimals/commas.
   - **Entity consistency** (lines 154-160): Every capitalized entity in the claim must appear in the atom.

### The Single-Atom Assumption

Each text segment is associated with exactly one citation `[A###]`. It looks up the corresponding `RetrievedItem` from `item_map[cite]`. All three checks operate on that single atom's content.

```python
# Line 131 - single atom lookup
atom = item_map[cite]
atom_content = atom.content
```

This works for direct claims: "The revenue was $10M [A001]" — the number "10" appears in A001, entities match, lexical overlap exists.

### Why It Fails for Derived Claims

Derived claims cite multiple atoms and express relationships not literally present in any single source:

| Claim | Citations | Why Current Validator Rejects |
|-------|-----------|-------------------------------|
| "A exceeded B by 25% [A001, A002]" | A001, A002 | Segment text is "A exceeded B by 25% " which gets associated with citation A002 (the last one in the segment). "25%" doesn't appear in A002. |
| "A's revenue was $3M more than B's [A001, A002]" | A001, A002 | "3" doesn't literally appear in either atom if A=$13M and B=$10M |
| "A ranked 3rd [A001, A002, A003]" | A001, A002, A003 | "3" may not appear in any cited atom |

The numeric consistency check (line 148-152) is the primary failure mode — it looks for the exact number string in the atom content. Derived values are computed, never written.

---

## The Derived Claim Problem

### Derived Claims from Phase 12-A

Phase 12-A created a `DerivationEngine` in `src/research/derivation/engine.py` with three rules:

| Rule | Input | Output | Example |
|------|-------|--------|---------|
| `delta` | 2 atoms with numeric values | A - B | A=$13M, B=$10M → delta=$3M |
| `percent_change` | 2 atoms with numeric values | ((new-old)/old)×100 | A=80, B=100 → -20.0% |
| `rank` | N atoms with numeric values | Sorted (id, value) pairs | A=10, B=30, C=20 → [(B,30), (C,20), (A,10)] |

**Critical property**: Derived claims are **ephemeral** — they live on `EvidencePacket.derived_claims`, NOT in the database. They are projections over source atoms, never persisted as truth.

**Critical constraint**: The validator receives `prose: str` and `retrieved_items: List[RetrievedItem]` — it does NOT receive `DerivedClaim` objects. It must rederive inline from the cited atoms (see 12-A research, Ambiguity #1).

### What the LLM Writes

The LLM receives EvidencePacket which contains `derived_claims: List[DerivedClaim]`. It can reference these derived claims in prose:

- "Company A's revenue of $13M exceeded Company B's $10M by 30% [A001, A002]"
- "A ranked first with 30 points, followed by C (20) and B (10) [A001, A002, A003]"

The validator needs to verify these are correct without having the DerivedClaim objects directly.

---

## External Research: Multi-Source Claim Verification

### Fact-Checking Systems

**IBM Watson Fact Checking**: Uses a two-tier approach — first verifies single-source claims via textual entailment (NLI models), then for multi-source claims, identifies the relationship type (comparative, aggregative, temporal) and applies appropriate verification logic. Comparative claims trigger arithmetic re-derivation from cited sources.

**Google ClaimReview / Fact Check Tools**: Structured markup for fact claims. For numeric comparisons, relies on the fact-checker to cite all sources and provide the computation. The system validates that all cited sources are present and referenced, but does not independently verify arithmetic.

**SemEval-2021 Task 9 (Fact Verification)**: Competition task on table-based fact verification. Winners used structured reasoning — parse table, extract values, apply arithmetic operation, compare claimed result. Pattern: parse → extract → compute → verify.

### NLP Comparative Language Detection

Pattern-based approaches for identifying comparative/derived numeric claims:

| Pattern Category | Example Phrases | Regex Features |
|-----------------|-----------------|----------------|
| Direct comparison | "X exceeded Y by Z%", "X was higher than Y" | "exceeds?\|higher\|lower\|greater\|less" |
| Percent change | "increased by Z%", "dropped Z%" | "increased\|decreased\|dropped\|rose" + \d+% |
| Ranking | "X ranked Nth", "X was the Nth largest" | "ranked\|#\d+\|Nth" |
| Difference | "X was $N more than Y", "a difference of N" | "more than\|less than\|difference" |

**Key insight**: Comparative language + multiple citations + a number = candidate for derived verification.

### Floating-Point Comparison in Verification

Standard approaches:
- **Python `math.isclose(a, b, rel_tol=1e-9, abs_tol=0.0)`** — relative tolerance comparison, handles edge cases at zero
- **Absolute epsilon** — `abs(a - b) < 1e-9` — works when values are bounded away from zero
- **ULP (units in last place)** — most precise, overkill for this use case

For Sheppard's validator, numbers extracted from text via regex are already strings. Converting "25" to 25.0 and then comparing: absolute epsilon of `1e-9` is overkill since most derived values are clean integers or simple percentages. **Recommendation**: Use absolute comparison with tolerance `1e-6` (micro-level precision, enough for percentage claims, handles floating-point rounding).

---

## Detection Strategy for Derived Numeric Claims

### Pattern 1: Multi-Citation Detection

A text segment with ≥2 adjacent citations `[A001][A002]` or comma-separated `[A001,A002]`:

```python
citations = re.findall(r'\[([A-Za-z0-9]+)\]', text)
is_multi_citation = len(citations) >= 2
```

Current code already finds multiple citations (line 256 in synthesis_service `_validate_grounding`), but only checks each one individually.

### Pattern 2: Comparative Language Detection

```python
COMPARATIVE_KEYWORDS = {
    'exceed', 'exceeded', 'exceeds', 'surpass', 'surpassed',
    'higher', 'lower', 'greater', 'less', 'more', 'fewer',
    'increased', 'decreased', 'dropped', 'rose', 'grew', 'shrank',
    'rank', 'ranked', 'ranking', 'first', 'second', 'third',
    'by', 'difference', 'gap'
}

def has_comparative_language(text: str) -> bool:
    words = set(tokenize(text.lower()))
    return bool(words & COMPARATIVE_KEYWORDS)
```

### Pattern 3: Numeric Relationship Detection

```python
def has_numeric_claim(text: str) -> bool:
    numbers = extract_numbers(text)
    percentages = re.findall(r'\d+(?:\.\d+)?%', text)
    return len(numbers) > 0 or len(percentages) > 0
```

### Combined Detection

A segment is a **derived numeric claim candidate** when:
1. `len(citations) >= 2` AND
2. Contains numeric value(s) AND
3. Contains comparative language OR percentage

---

## Integration Approach

### Where the Check Fits

In `validate_response_grounding()`, after the existing numeric consistency check (line 152), add:

```python
# --- Derived Claim Check ---
# If segment cites 2+ atoms AND has numeric+comparative content:
try:
    derived_result = _verify_derived_numeric(text, cited_atoms, item_map)
    if not derived_result.valid:
        errors.append(derived_result.error_message)
except SkipDerivedCheck:
    pass  # Not a derived claim pattern, fall through to single-atom checks
```

### Algorithm for `_verify_derived_numeric`

1. **Extract**: Parse the sentence to find (entities, numbers, comparative type)
2. **Map**: Match entities to cited atoms (which atom is A, which is B)
3. **Derive**: Use the appropriate rule from 12-A (`compute_delta`, `compute_percent_change`, `compute_rank`)
4. **Compare**: `abs(claimed_value - derived_value) <= tolerance`
5. **Report**: Valid if within tolerance, error otherwise

### Key Design Decision: Inline Recomputation vs Direct DerivedClaim Access

The validator does NOT receive `DerivedClaim` objects. It receives only `prose` and `retrieved_items`. Two options:

| Approach | Pros | Cons |
|----------|------|------|
| **Inline derive** (recompute in validator) | No API change, validator is self-contained, works even if derivation was skipped | Duplicates computation logic, slight performance cost |
| **Direct access** (pass DerivedClaims to validator) | No recomputation, canonical values | Requires API change, ties validator to EvidencePacket |

**12-A decision**: Inline recomputation (Ambiguity #1: "The validator receives prose: str and retrieved_items — it does NOT have access to DerivedClaim objects. It must rederive inline").

**This is the right call**: The validator's job is to independently verify, not trust pre-computed values. Recomputation is a fresh check, not a replay.

### Minimal API Change

To avoid changing the function signature of `validate_response_grounding()`, a second overloaded function can be added:

```python
def validate_derived_grounding(
    response_text: str,
    retrieved_items: List[RetrievedItem],
    derived_claims: List[DerivedClaim] = None,  # Optional, for performance optimization
) -> Dict[str, Any]:
```

When `derived_claims` is provided, the validator can use them as a fast path (skip recomputation, just verify the derived claim matches the prose). When absent, it recomputes inline.

### Existing Helper Reuse

The validator already has the right helpers:
- `extract_numbers()` — extracts numeric strings from text (line 36-46)
- `extract_entities()` — extracts capitalized entities (line 48-57)
- `tokenize()` — lowercased alphanumeric tokens (line 29-34)
- `STOPWORDS` — comprehensive stopword set (line 13-27)

What's needed:
- `_extract_comparative_type()` — classify the relationship type (delta vs percent vs rank)
- `_match_entity_to_atom()` — map "Company A" to the atom that contains "Company A"
- `_derive_and_verify()` — apply the derivation rule and compare

---

## Risk Analysis

### False Positives in Derived Detection

| Risk | Scenario | Mitigation |
|------|----------|------------|
| Non-derived multi-citation flagged | "A and B are related [A001, A002]" — no number present | Only trigger when numeric claim detected (pattern 3) |
| Numbers in text not derived values | "Company A generated 5 reports [A001, A002]" — "5" is literal | Skip if "5" appears verbatim in any cited atom |
| Comparative language without math | "A is better than B [A001, A002]" — subjective, no numbers | Skip if no numeric value in sentence |

### Performance Impact

- Detection: regex + set operations = O(n) on text length, negligible
- Recomputation: requires extracting numeric from 2 atoms = O(content_length), same as existing lexical overlap check
- Worst case: every segment triggers recompute. For a report with ~8 sections × 10 sentences each = 80 checks. At ~0.1ms each = 8ms total. Negligible.

### Edge Cases

| Case | Handling |
|------|----------|
| Same entity mentioned in multiple atoms | Use entity matching to determine which atom is "old" vs "new" |
| Numbers in different units ("10M" vs "10,000,000") | Normalize: strip commas, scale suffixes (K/M/B) — future improvement |
| Multiple numbers in sentence | Extract all, match to comparative type (e.g., "A=13, B=10, difference=3" → verify delta) |
| Negative values ("dropped by 20%") | Percent change handles negative naturally |
| Zero denominator ("old value was 0") | Skip derived check, fall back to existing path |

### Backward Compatibility

The existing three checks (lexical, numeric, entity) must run **unchanged**. The derived check is **additional**, not replacement:

```
Existing flow: lexical → numeric → entity → result
New flow:      lexical → numeric (skip if derived) → entity → derived_check → result
```

The numeric consistency check should be **skipped** (not just supplemented) for derived claims, because the number WILL NOT appear in the source atom — it's by definition computed. If we run the existing numeric check AND the derived check, the numeric check will always fail.

---

## Dependencies on Phase 12-A

From 12-B context, prerequisites:

| Dependency | Provided by 12-A | Status |
|-----------|------------------|--------|
| `DerivedClaim` dataclass | `src/research/derivation/engine.py` | Not yet implemented |
| `compute_delta()` | `src/research/derivation/engine.py` | Not yet implemented |
| `compute_percent_change()` | `src/research/derivation/engine.py` | Not yet implemented |
| `EvidencePacket.derived_claims` | `src/research/reasoning/assembler.py` modification | Not yet implemented |
| Derivation rules specification | `.planning/phases/12-A/DERIVATION_RULES.md` | ✅ Exists |
| Derived claim schema | `.planning/phases/12-A/DERIVED_CLAIM_SCHEMA.md` | ✅ Exists |

12-B can start skeleton development (function signatures, detection patterns) but the actual derived claim verification depends on 12-A's engine being importable and correct.

---

## Conclusion

The dual validator extension is a focused, additive change to the existing grounding validator. The key challenge is reliably detecting when a sentence expresses a derived numeric claim (using multiple citations with comparative language and a number) vs a simple direct claim. The detection strategy uses three independent signals — multi-citation, numeric content, and comparative language — combined to minimize false positives.

The inline recomputation approach (12-A's decision) is architecturally sound: it keeps the validator self-contained, independently verifiable, and decoupled from EvidencePacket internals. Performance impact is negligible.
