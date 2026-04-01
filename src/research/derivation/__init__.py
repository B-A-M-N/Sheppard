"""
src/research/derivation/__init__.py

Derived Claim Engine module — deterministic, LLM-free transformations
that compute derived facts from retrieved knowledge atoms.
"""

from src.research.derivation.engine import (
    DerivedClaim,
    DerivationConfig,
    DerivationEngine,
    compute_delta,
    compute_percent_change,
    compute_rank,
    compute_ratio,
    compute_chronology,
    compute_support_rollup,
    compute_conflict_rollup,
)

__all__ = [
    "DerivedClaim",
    "DerivationConfig",
    "DerivationEngine",
    "compute_delta",
    "compute_percent_change",
    "compute_rank",
    "compute_ratio",
    "compute_chronology",
    "compute_support_rollup",
    "compute_conflict_rollup",
]
