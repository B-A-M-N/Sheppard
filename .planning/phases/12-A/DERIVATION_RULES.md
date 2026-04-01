# Derivation Rules

## Rule: delta
- **Input:** 2 atoms each containing ≥1 numeric values
- **Output:** `atom_a_value - atom_b_value` (float)
- **Formula:** `Δ = A - B`
- **Preconditions:** Both atoms must contain at least one numeric value
- **Failure:** Skip (atoms without numbers → no delta computed)
- **Metadata:** `{"atom_a_id": str, "atom_b_id": str, "atom_a_value": float, "atom_b_value": float, "formula": "A - B"}`
- **Determinism:** Sorted atom list ensures A < B by global_id → consistent sign

## Rule: percent_change
- **Input:** 2 atoms each containing ≥1 numeric values
- **Output:** `((new_value - old_value) / old_value) * 100` (float)
- **Formula:** `%Δ = ((new - old) / old) × 100`
- **Preconditions:** Both atoms numeric; `old_value != 0`
- **Failure:** Skip (zero denominator, non-numeric, missing atom)
- **Metadata:** `{"old_value": float, "new_value": float, "delta": float, "formula": "((new - old) / old) * 100"}`
- **Determinism:** `atom_a` is "old", `atom_b` is "new" based on global_id sort order

## Rule: rank
- **Input:** N atoms each containing ≥1 numeric values
- **Output:** List of `(atom_id, value)` tuples sorted descending by value, ties broken by global_id ascending
- **Formula:** Sort by `value_desc, global_id_asc`
- **Preconditions:** ≥1 atom numeric
- **Failure:** Skip (no atoms with numbers)
- **Metadata:** `{"metric": str, "ties_broken_by": "global_id", "atom_rankings": List[Tuple[str, float]]}`
- **Determinism:** Identical sorts guaranteed by stable python sort with 2-key comparison

## Common Requirements (All Rules)

| Constraint | Enforcement |
|------------|-------------|
| No LLM calls | Pure functions only; imports limited to stdlib + RetrievedItem |
| Sorted inputs | All functions receive atoms sorted by global_id |
| Skip on failure | Missing atoms, non-numeric, div/zero → silently skip |
| Never fabricate | Missing inputs → no claim produced (never guess) |
| Deterministic ID | sha256(rule:sorted_atom_ids:version)[:16] |
| Performance | <1ms per claim, O(n log n) max complexity |
| Version | "12-A-v1" — change when rule logic changes |

## Numeric Value Extraction

From each RetrievedItem:
1. Check `metadata['numeric_value']` — use if present
2. Else extract from `content` text using `extract_numbers()` helper
3. Take **FIRST numeric value** found for simplicity (future: extract all)

## Error Handling

| Case | Behavior |
|------|----------|
| Missing required atom | Skip |
| Non-numeric input | Skip |
| Div by zero (percent) | Skip |
| Invalid structure | Skip |

**NEVER:** throw, halt pipeline, fabricate output
