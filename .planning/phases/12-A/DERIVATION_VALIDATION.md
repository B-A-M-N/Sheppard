# Derivation Validation

## Validator Extension Algorithm

The existing `validate_response_grounding()` in `src/retrieval/validator.py` checks:
1. Every factual claim has citation
2. Lexical overlap ≥2 content words
3. Numeric consistency (numbers in claim must appear in atom)
4. Entity consistency

**Extension:** When a sentence cites ≥2 atoms AND expresses a numeric relationship (delta/percent/rank), the validator must **recompute** the derived value and verify the claimed value.

### Detection of Derived Claims

A sentence is considered to express a derived claim if it:
1. Contains ≥2 citation markers `[A###]` 
2. Contains ≥1 numeric value (extracted via `extract_numbers()`)
3. Contains comparative language: "higher", "lower", "exceeds", "increased", "decreased", "by X%", "less than", "more than", "ranked", "first", "second", etc.

### Validation Steps

For each sentence detected as expressing a derived claim:

**Step 1: Extract cited atoms**
```python
cited_ids = re.findall(r'\[([A-Z]?\d+)\]', sentence)
claimed_numbers = extract_numbers(sentence)
```

**Step 2: Get atom content**
```python
atom_contents = []
for cid in cited_ids:
    if cid in item_map:
        atom_contents.append(item_map[cid])
```

**Step 3: Identify relationship type**

Pattern match sentence for:
- "exceeds by X" → `delta`, direction = A - B
- "X% higher/lower" → `percent_change`
- "X is first/second/highest" → `rank`

**Step 4: Recompute from atoms**
```python
# Delta: extract first number from each atom
a_val = extract_numbers(atom_contents[0].content)[0]
b_val = extract_numbers(atom_contents[1].content)[0]
expected_delta = a_val - b_val

# Percent change:
expected_pct = ((b_val - a_val) / a_val) * 100

# Rank: sorted(atom_contents, key=numeric_value, reverse=True)
```

**Step 5: Compare**
```python
claimed_val = float(claimed_numbers[0])  # First number in sentence
if abs(claimed_val - expected) > tolerance:
    FAIL (add error: f"Derived claim '{sentence[:50]}' is incorrect: claimed {claimed_val}, computed {expected}")
```

### Tolerance

- **Floating point:** `1e-9` (standard epsilon)
- **Integers:** Exact match (no tolerance)
- **Percentages:** Same tolerance after dividing by 100

### Failure Handling

If validation detects incorrect derived claim:
1. Add error to `errors` list
2. Set `is_valid = False`
3. Add detail: `{'claim': sentence, 'cited': cited_ids, 'error': 'derived_mismatch', 'claimed': claimed_val, 'expected': expected}`

### No Degradation Guarantee

Sentences with single citations: existing path unchanged
Sentences without comparative language: existing path unchanged
Only multi-atom numeric claims trigger recomputation

## Test Cases

### Derived Claim Correct → PASS
```
"A exceeded B by 3 [A001, A002]"  // A=10, B=7 → delta=3 ✓
```

### Derived Claim Incorrect → FAIL
```
"A exceeded B by 50 [A001, A002]"  // A=10, B=7 → delta=3, claimed=50 ✗
```

### Single Citation → Existing Path
```
"A reported revenue of 10M [A001]"  // 10M in atom ✓
```

### No Comparative Language → Existing Path
```
"A and B are both significant [A001, A002]"  // No numeric relationship → skip derived check ✓
```
