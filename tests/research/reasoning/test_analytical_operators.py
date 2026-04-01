"""
tests/research/reasoning/test_analytical_operators.py

TDD tests for Phase 12-B: Analytical & Comparative Reasoning Layer.

Tests verify that analytical operators produce deterministic, LLM-free
structured output from raw RetrievedItem atoms.
"""

import sys
import os

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_src = os.path.join(_project_root, "src")
for _p in [_src, _project_root]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest

from retrieval.models import RetrievedItem
from research.reasoning.analytical_operators import (
    AnalyticalBundle,
    compare_contrast_bundle,
    tradeoff_extraction,
    method_result_pairing,
    consensus_divergence,
    source_authority_weight,
    change_detection,
    run_all_operators,
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def make_atom(label, content, item_type="claim", trust_score=0.5, knowledge_level="B",
              recency_days=30, **meta):
    return RetrievedItem(
        content=content,
        source="test",
        strategy="test",
        item_type=item_type,
        trust_score=trust_score,
        knowledge_level=knowledge_level,
        recency_days=recency_days,
        citation_key=f"[{label}]",
        metadata=meta,
    )


# ──────────────────────────────────────────────────────────────
# 1. compare_contrast_bundle
# ──────────────────────────────────────────────────────────────

def test_compare_contrast_groups_by_entity():
    """Atoms sharing entity_id are grouped; one bundle per group."""
    atoms = [
        make_atom("A", "Python is a high-level language", entity_id="python"),
        make_atom("B", "Python supports dynamic typing and is interpreted", entity_id="python"),
        make_atom("C", "Java is a statically typed compiled language", entity_id="java"),
        make_atom("D", "Java runs on the JVM virtual machine", entity_id="java"),
    ]
    bundles = compare_contrast_bundle(atoms)
    assert isinstance(bundles, list)
    assert len(bundles) == 2
    operators = {b.operator for b in bundles}
    assert operators == {"compare_contrast"}
    entities = {b.metadata["entity"] for b in bundles}
    assert entities == {"python", "java"}


def test_compare_contrast_finds_agreements_and_differences():
    """Lexical agreements (shared tokens) and differences (unique tokens) identified."""
    atoms = [
        make_atom("A", "Python is a programming language used for scripting", entity_id="python"),
        make_atom("B", "Python is a language focused on readability and scripting tasks", entity_id="python"),
    ]
    bundles = compare_contrast_bundle(atoms)
    assert len(bundles) == 1
    output = bundles[0].output
    assert "agreements" in output
    assert "differences" in output
    # "python", "language", "scripting" should appear as agreements
    assert len(output["agreements"]) >= 1
    # Each atom should have at least some unique tokens
    assert len(output["differences"]) == 2


def test_compare_contrast_skips_single_atom_group():
    """Groups with only one atom produce no bundle."""
    atoms = [
        make_atom("A", "Python is a programming language", entity_id="python"),
        make_atom("B", "Java is a compiled language", entity_id="java"),
    ]
    # Each entity has only 1 atom → no group qualifies
    bundles = compare_contrast_bundle(atoms)
    assert bundles == []


def test_compare_contrast_skips_atoms_without_entity():
    """Atoms without entity_id/entity/concept_name metadata are skipped gracefully."""
    atoms = [
        make_atom("A", "Some content without entity"),
        make_atom("B", "More content without entity"),
    ]
    bundles = compare_contrast_bundle(atoms)
    assert bundles == []


# ──────────────────────────────────────────────────────────────
# 2. tradeoff_extraction
# ──────────────────────────────────────────────────────────────

def test_tradeoff_extracts_pros_and_cons():
    """Atoms with pro/con language are classified and returned in structured output."""
    atoms = [
        make_atom("A", "The main advantage is speed and low latency performance"),
        make_atom("B", "A significant disadvantage is high memory usage and complexity"),
        make_atom("C", "Another benefit is ease of use and simple API"),
        make_atom("D", "The limitation is poor support for large datasets"),
    ]
    bundle = tradeoff_extraction(atoms)
    assert bundle is not None
    assert bundle.operator == "tradeoff"
    output = bundle.output
    assert "pros" in output and "cons" in output
    assert len(output["pros"]) >= 2
    assert len(output["cons"]) >= 2


def test_tradeoff_returns_none_if_no_pros_or_cons():
    """Returns None when no atoms have identifiable pro or con language."""
    atoms = [
        make_atom("A", "Python is a programming language"),
        make_atom("B", "Java was developed by Sun Microsystems"),
    ]
    bundle = tradeoff_extraction(atoms)
    assert bundle is None


# ──────────────────────────────────────────────────────────────
# 3. method_result_pairing
# ──────────────────────────────────────────────────────────────

def test_method_result_pairs_by_item_type():
    """Atoms with item_type='methodology' paired with item_type='result'."""
    atoms = [
        make_atom("A", "We used random sampling to select 200 participants", item_type="methodology"),
        make_atom("B", "The study showed a 15% improvement in outcomes", item_type="result"),
        make_atom("C", "Double-blind placebo controlled trial was conducted", item_type="methodology"),
        make_atom("D", "Results demonstrated statistical significance p < 0.05", item_type="result"),
    ]
    bundle = method_result_pairing(atoms)
    assert bundle is not None
    assert bundle.operator == "method_result"
    output = bundle.output
    assert "pairs" in output
    assert len(output["pairs"]) >= 1
    for pair in output["pairs"]:
        assert "method_atom_id" in pair
        assert "result_atom_id" in pair


def test_method_result_skips_if_no_pairs():
    """Returns None when no methodology/result atom pairs exist."""
    atoms = [
        make_atom("A", "Python is a language", item_type="claim"),
        make_atom("B", "Java is compiled", item_type="claim"),
    ]
    bundle = method_result_pairing(atoms)
    assert bundle is None


# ──────────────────────────────────────────────────────────────
# 4. consensus_divergence
# ──────────────────────────────────────────────────────────────

def test_consensus_divergence_requires_three_atoms():
    """Returns None when fewer than 3 atoms provided."""
    atoms = [
        make_atom("A", "Python is popular"),
        make_atom("B", "Python is widely used"),
    ]
    bundle = consensus_divergence(atoms)
    assert bundle is None


def test_consensus_divergence_identifies_agreement():
    """Atoms with high lexical overlap form consensus; unique atoms are divergent."""
    atoms = [
        make_atom("A", "Python is a popular high-level programming language"),
        make_atom("B", "Python is a widely used high-level language for programming"),
        make_atom("C", "Python is a popular language used in data science"),
        make_atom("D", "Rust focuses on memory safety and systems programming"),
    ]
    bundle = consensus_divergence(atoms)
    assert bundle is not None
    assert bundle.operator == "consensus_divergence"
    output = bundle.output
    assert "consensus" in output
    assert "divergent" in output
    assert output["total"] == 4
    # At least one divergent (Rust atom is about different topic)
    assert len(output["divergent"]) >= 1


# ──────────────────────────────────────────────────────────────
# 5. source_authority_weight
# ──────────────────────────────────────────────────────────────

def test_source_authority_scores_all_atoms():
    """Every atom receives a score; output contains all atom IDs."""
    atoms = [
        make_atom("A", "Content A", trust_score=0.9, knowledge_level="A", recency_days=10),
        make_atom("B", "Content B", trust_score=0.5, knowledge_level="B", recency_days=100),
        make_atom("C", "Content C", trust_score=0.3, knowledge_level="C", recency_days=500),
    ]
    bundle = source_authority_weight(atoms)
    assert bundle is not None
    assert bundle.operator == "source_authority"
    output = bundle.output
    assert "scores" in output
    assert "ranked" in output
    assert len(output["scores"]) == 3
    assert len(output["ranked"]) == 3


def test_source_authority_prefers_higher_trust():
    """Higher trust_score + better knowledge_level + fresher recency → higher rank."""
    atoms = [
        make_atom("HIGH", "High quality content", trust_score=0.95, knowledge_level="A", recency_days=5),
        make_atom("LOW", "Low quality content", trust_score=0.1, knowledge_level="D", recency_days=3000),
    ]
    bundle = source_authority_weight(atoms)
    ranked = bundle.output["ranked"]
    # HIGH should be first
    assert ranked[0][0] == "[HIGH]"
    assert ranked[0][1] > ranked[1][1]


# ──────────────────────────────────────────────────────────────
# 6. change_detection
# ──────────────────────────────────────────────────────────────

def test_change_detection_computes_delta():
    """Two atoms with numeric values and different recency_days → change bundle."""
    atoms = [
        make_atom("OLD", "Revenue was 100 million in the previous quarter", recency_days=90),
        make_atom("NEW", "Revenue reached 125 million this quarter", recency_days=10),
    ]
    bundle = change_detection(atoms)
    assert bundle is not None
    assert bundle.operator == "change_detection"
    output = bundle.output
    assert "from" in output and "to" in output
    assert "delta" in output and "pct_change" in output
    assert abs(output["delta"] - 25.0) < 1e-6
    assert abs(output["pct_change"] - 25.0) < 1e-6


def test_change_detection_skips_if_insufficient_data():
    """Returns None when fewer than 2 atoms have numeric values."""
    atoms = [
        make_atom("A", "There are no numbers here", recency_days=10),
        make_atom("B", "Also no numbers here", recency_days=90),
    ]
    bundle = change_detection(atoms)
    assert bundle is None


# ──────────────────────────────────────────────────────────────
# run_all_operators (orchestrator)
# ──────────────────────────────────────────────────────────────

def test_run_all_operators_returns_list():
    """run_all_operators returns a flat list of AnalyticalBundle, skipping None results."""
    atoms = [
        make_atom("A", "Python advantage is simple syntax", entity_id="python"),
        make_atom("B", "Python benefit is large ecosystem", entity_id="python"),
        make_atom("C", "The disadvantage is slow execution speed"),
        make_atom("D", "Revenue was 100 million last year", recency_days=365),
        make_atom("E", "Revenue is now 130 million", recency_days=30),
    ]
    results = run_all_operators(atoms)
    assert isinstance(results, list)
    for item in results:
        assert isinstance(item, AnalyticalBundle)
