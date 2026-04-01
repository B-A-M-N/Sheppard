"""
src/research/derivation/engine.py

Derived Claim Engine — deterministic, LLM-free transformations that compute
derived facts from retrieved knowledge atoms while preserving full provenance.

Rules implemented (Phase 12-A scope):
  - delta: difference between two numeric values
  - percent_change: percentage change from old to new value
  - rank: ordering of atoms by numeric value

All functions are pure: same inputs → same outputs. No LLM calls.
Errors are silently skipped (never halt pipeline, never fabricate).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import logging

if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath('.')), ''))

from research.reasoning.retriever import RetrievedItem

logger = logging.getLogger(__name__)

CONFIG_VERSION = "12-A-v1"


# ──────────────────────────────────────────────────────────────
# Numeric extraction helper
# ──────────────────────────────────────────────────────────────

def _extract_numbers(text: str) -> List[float]:
    """Extract numeric values from text, returning floats."""
    pattern = r'[\d,]+\.?\d*'
    matches = re.findall(pattern, text)
    results = []
    for m in matches:
        cleaned = m.replace(',', '')
        if cleaned:
            try:
                results.append(float(cleaned))
            except ValueError:
                continue
    return results


def _extract_numeric_value(item: RetrievedItem, from_metadata: bool = True) -> Optional[float]:
    """
    Extract a single numeric value from a RetrievedItem.

    Priority:
    1. metadata['numeric_value'] if from_metadata and present
    2. First numeric value found in item.content text
    3. None if no numeric value found
    """
    # Try metadata first if configured
    if from_metadata and item.metadata:
        nv = item.metadata.get('numeric_value')
        if nv is not None:
            try:
                return float(nv)
            except (TypeError, ValueError):
                pass

    # Fall back to regex extraction from content
    numbers = _extract_numbers(item.content)
    if numbers:
        return numbers[0]  # Take first numeric value
    return None


# ──────────────────────────────────────────────────────────────
# Deterministic ID generation
# ──────────────────────────────────────────────────────────────

def make_claim_id(rule: str, atom_ids: List[str], version: str = CONFIG_VERSION) -> str:
    """Generate a deterministic claim ID from rule + sorted atom IDs."""
    sorted_ids = sorted(atom_ids)
    raw = f"{rule}:{','.join(sorted_ids)}:{version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ──────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DerivedClaim:
    """A deterministic transformation over source atoms."""
    id: str                      # Deterministic hash: sha256(rule:sorted_atom_ids:version)[:16]
    rule: str                    # "delta" | "percent_change" | "rank"
    source_atom_ids: List[str]   # Sorted, canonical — never mutated after construction
    output: Any                  # float (delta/percent) or List[Tuple[str, float]] (rank)
    metadata: Dict[str, Any]     # Rule-specific computation details


@dataclass
class DerivationConfig:
    """Configuration for derivation engine."""
    tolerance: float = 1e-9          # For floating-point comparison in validator
    version: str = CONFIG_VERSION    # For deterministic ID generation
    extract_from_metadata: bool = True  # Prefer metadata over content parsing


# ──────────────────────────────────────────────────────────────
# Rule implementations
# ──────────────────────────────────────────────────────────────

def compute_delta(
    atom_a: RetrievedItem,
    atom_b: RetrievedItem,
    config: Optional[DerivationConfig] = None,
) -> Optional[DerivedClaim]:
    """
    Compute the difference between two atoms with numeric values.

    Formula: delta = value_a - value_b

    Returns None if either atom lacks a numeric value.
    Deterministic: atom_a and atom_b are already sorted by citation_key.
    """
    val_a = _extract_numeric_value(atom_a, config.extract_from_metadata if config else True)
    val_b = _extract_numeric_value(atom_b, config.extract_from_metadata if config else True)

    if val_a is None or val_b is None:
        return None

    delta = val_a - val_b
    id_a = atom_a.citation_key or atom_a.metadata.get('atom_id', '')
    id_b = atom_b.citation_key or atom_b.metadata.get('atom_id', '')
    claim_id = make_claim_id("delta", [id_a, id_b], config.version if config else CONFIG_VERSION)

    return DerivedClaim(
        id=claim_id,
        rule="delta",
        source_atom_ids=sorted([id_a, id_b]),
        output=delta,
        metadata={
            "atom_a_id": id_a,
            "atom_b_id": id_b,
            "atom_a_value": val_a,
            "atom_b_value": val_b,
            "formula": "A - B",
        }
    )


def compute_percent_change(
    atom_a: RetrievedItem,
    atom_b: RetrievedItem,
    config: Optional[DerivationConfig] = None,
) -> Optional[DerivedClaim]:
    """
    Compute percentage change from atom_a (old) to atom_b (new).

    Formula: percent_change = ((new - old) / old) * 100

    Returns None if either atom lacks a numeric value or old_value is zero.
    Deterministic: atom_a is "old", atom_b is "new" based on sorted input order.
    """
    val_a = _extract_numeric_value(atom_a, config.extract_from_metadata if config else True)
    val_b = _extract_numeric_value(atom_b, config.extract_from_metadata if config else True)

    if val_a is None or val_b is None:
        return None

    if val_a == 0.0:
        return None  # Skip division by zero

    pct = ((val_b - val_a) / val_a) * 100.0
    id_a = atom_a.citation_key or atom_a.metadata.get('atom_id', '')
    id_b = atom_b.citation_key or atom_b.metadata.get('atom_id', '')
    claim_id = make_claim_id("percent_change", [id_a, id_b], config.version if config else CONFIG_VERSION)

    return DerivedClaim(
        id=claim_id,
        rule="percent_change",
        source_atom_ids=sorted([id_a, id_b]),
        output=pct,
        metadata={
            "old_value": val_a,
            "new_value": val_b,
            "delta": val_b - val_a,
            "formula": "((new - old) / old) * 100",
        }
    )


def compute_rank(
    atoms: List[RetrievedItem],
    config: Optional[DerivationConfig] = None,
) -> Optional[DerivedClaim]:
    """
    Rank all atoms by their first numeric value, descending.

    Returns a list of (atom_id, value) tuples sorted by value descending,
    ties broken by atom_id (citation_key) ascending for determinism.

    Returns None if no atoms contain numeric values.
    """
    if not atoms:
        return None

    extract_from_meta = config.extract_from_metadata if config else True
    ranked = []
    for atom in atoms:
        val = _extract_numeric_value(atom, extract_from_meta)
        if val is not None:
            aid = atom.citation_key or atom.metadata.get('atom_id', '')
            ranked.append((aid, val))

    if not ranked:
        return None

    # Deterministic sort: value descending, then atom_id ascending for ties
    ranked.sort(key=lambda x: (-x[1], x[0]))

    all_ids = sorted([r[0] for r in ranked])
    claim_id = make_claim_id("rank", all_ids, config.version if config else CONFIG_VERSION)

    return DerivedClaim(
        id=claim_id,
        rule="rank",
        source_atom_ids=all_ids,
        output=ranked,
        metadata={
            "metric": "numeric_value",
            "ties_broken_by": "global_id",
            "atom_rankings": ranked,
        }
    )


# ──────────────────────────────────────────────────────────────
# Engine orchestrator
# ──────────────────────────────────────────────────────────────

class DerivationEngine:
    """
    Orchestrates all derivation rules over a list of RetrievedItems.

    Usage:
        engine = DerivationEngine()
        claims = engine.run(items)  # Returns list of DerivedClaim
    """

    def __init__(self, config: Optional[DerivationConfig] = None):
        self.config = config or DerivationConfig()

    def run(self, items: List[RetrievedItem]) -> List[DerivedClaim]:
        """
        Apply all derivation rules to sorted items.

        Items are sorted by citation_key (deterministic order) before
        derivation. All rules are applied; failures are silently skipped.
        """
        # Deterministic input ordering
        sorted_items = sorted(items, key=lambda x: x.citation_key or '')

        claims = []

        try:
            delta_claims = self._compute_all_deltas(sorted_items)
            claims.extend(delta_claims)
        except Exception as e:
            logger.debug(f"[DerivationEngine] Delta computation failed: {e}")

        try:
            pct_claims = self._compute_all_percents(sorted_items)
            claims.extend(pct_claims)
        except Exception as e:
            logger.debug(f"[DerivationEngine] Percent change computation failed: {e}")

        try:
            rank_claim = self._compute_all_ranks(sorted_items)
            if rank_claim is not None:
                claims.append(rank_claim)
        except Exception as e:
            logger.debug(f"[DerivationEngine] Rank computation failed: {e}")

        return claims

    def _compute_all_deltas(self, items: List[RetrievedItem]) -> List[DerivedClaim]:
        """Compute delta for all unique pairs of items with numeric values."""
        claims = []
        numeric_items = []
        for item in items:
            if _extract_numeric_value(item, self.config.extract_from_metadata) is not None:
                numeric_items.append(item)

        for i in range(len(numeric_items)):
            for j in range(i + 1, len(numeric_items)):
                claim = compute_delta(numeric_items[i], numeric_items[j], self.config)
                if claim is not None:
                    claims.append(claim)
        return claims

    def _compute_all_percents(self, items: List[RetrievedItem]) -> List[DerivedClaim]:
        """Compute percent_change for all unique pairs with numeric values."""
        claims = []
        numeric_items = []
        for item in items:
            if _extract_numeric_value(item, self.config.extract_from_metadata) is not None:
                numeric_items.append(item)

        for i in range(len(numeric_items)):
            for j in range(i + 1, len(numeric_items)):
                claim = compute_percent_change(numeric_items[i], numeric_items[j], self.config)
                if claim is not None:
                    claims.append(claim)
        return claims

    def _compute_all_ranks(self, items: List[RetrievedItem]) -> Optional[DerivedClaim]:
        """Rank all items by their numeric values."""
        return compute_rank(items, self.config)


# ──────────────────────────────────────────────────────────────
# Validator helper (used by src/retrieval/validator.py)
# ──────────────────────────────────────────────────────────────

def verify_derived_claim(
    rule: str,
    atom_a: RetrievedItem,
    atom_b: Optional[RetrievedItem],
    claimed_value: float,
    tolerance: float = 1e-9,
) -> Optional[float]:
    """
    Recompute a derived claim and compare against a claimed value.

    Returns the computed value if the recomputation succeeds, or None
    if recomputation fails (insufficient data, etc.).

    The caller should treat the derived claim as INVALID if this returns
    a value that differs from claimed_value by more than tolerance.
    """
    if rule == "delta":
        claim = compute_delta(atom_a, atom_b) if atom_b else None
        if claim is not None:
            computed = float(claim.output)
            if abs(computed - claimed_value) > tolerance:
                return computed  # Mismatch → return computed value for error message
            return None  # Match → no error
        return None

    elif rule == "percent_change":
        claim = compute_percent_change(atom_a, atom_b) if atom_b else None
        if claim is not None:
            computed = float(claim.output)
            if abs(computed - claimed_value) > tolerance:
                return computed
            return None
        return None

    # Unknown rule → no verification possible
    return None
