# Derived Claim Schema

## Data Model

```python
@dataclass(frozen=True)
class DerivedClaim:
    """A deterministic transformation over source atoms."""
    id: str                      # Deterministic hash: sha256(rule:sorted_atom_ids:version)[:16]
    rule: str                    # One of: "delta", "percent_change", "rank"
    source_atom_ids: List[str]   # Sorted, canonical — never mutated after construction
    output: Any                  # float (delta/percent) or List[Tuple[str, float]] (rank)
    metadata: Dict[str, Any]     # Rule-specific: atom values, computation details, error info
```

## ID Generation

```python
def make_claim_id(rule: str, atom_ids: List[str], version: str = "12-A-v1") -> str:
    sorted_ids = sorted(atom_ids)
    raw = f"{rule}:{','.join(sorted_ids)}:{version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

Properties:
- Deterministic: same rule + atoms → same ID
- Collision-resistant: SHA-256 16-char trunk (~10^19 space)
- Reproducible across runs and machines

## Field Constraints

| Field | Type | Constraints | Immutable? |
|-------|------|-------------|------------|
| id | str | 16-char hex, deterministic | Yes (frozen) |
| rule | str | Must be one of: "delta", "percent_change", "rank" | Yes (frozen) |
| source_atom_ids | List[str] | Sorted ascending, ≥1 atom, never empty | Yes (frozen) |
| output | Any | float for delta/percent, List[Tuple[str, float]] for rank | Yes (frozen) |
| metadata | Dict[str, Any] | Keys depend on rule type | No (dict mutable for testing) |

### Metadata Schema by Rule

**delta:**
```python
{
    "atom_a_id": str,     # First atom ID
    "atom_b_id": str,     # Second atom ID
    "atom_a_value": float,
    "atom_b_value": float,
    "formula": "A - B"
}
```

**percent_change:**
```python
{
    "old_value": float,
    "new_value": float,
    "delta": float,
    "formula": "((new - old) / old) * 100"
}
```

**rank:**
```python
{
    "metric": str,         # Which numeric field was used for sorting
    "ties_broken_by": str, # "global_id" (always for determinism)
    "atom_rankings": List[Tuple[str, float]]  # sorted (atom_id, value)
}
```

## Storage Model

- **NOT persisted to Postgres** (derived = projection, not truth)
- **Ephemeral**: Computed fresh per EvidencePacket construction
- **Attached to**: `EvidencePacket.derived_claims: List[DerivedClaim]`

## Validity Constraints

1. Every DerivedClaim must reference ≥1 source atom ids present in the EvidencePacket
2. `output` must be derivable from source_atom_ids via `rule`
3. `id` must be reproducible from `rule` + `source_atom_ids` + `version`
4. No DerivedClaim without at least one source atom
