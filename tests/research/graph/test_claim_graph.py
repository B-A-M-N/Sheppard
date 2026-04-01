"""
tests/research/graph/test_claim_graph.py

TDD tests for Phase 12-C: Evidence Graph / Claim Graph.
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
from research.graph.claim_graph import (
    EvidenceGraph,
    GraphNode,
    GraphEdge,
    EdgeType,
    build_evidence_graph,
)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def make_atom(label, content, item_type="claim", recency_days=30, **meta):
    return RetrievedItem(
        content=content, source="test", strategy="test",
        item_type=item_type, citation_key=f"[{label}]",
        recency_days=recency_days, metadata=meta,
    )


def make_derived_claim(rule, source_ids, output):
    from research.derivation.engine import DerivedClaim, make_claim_id
    return DerivedClaim(
        id=make_claim_id(rule, source_ids),
        rule=rule,
        source_atom_ids=sorted(source_ids),
        output=output,
        metadata={},
    )


def make_analytical_bundle(operator, atom_ids, output):
    from research.reasoning.analytical_operators import AnalyticalBundle
    return AnalyticalBundle(operator=operator, atom_ids=atom_ids, output=output, metadata={})


# ──────────────────────────────────────────────────────────────
# Node construction
# ──────────────────────────────────────────────────────────────

def test_builds_evidence_nodes_from_atoms():
    atoms = [make_atom("A", "Python is fast"), make_atom("B", "Java is verbose")]
    graph = build_evidence_graph(atoms, [], [], [])
    evidence_nodes = [n for n in graph.nodes.values() if n.node_type == "evidence"]
    assert len(evidence_nodes) == 2
    ids = {n.metadata["citation_key"] for n in evidence_nodes}
    assert ids == {"[A]", "[B]"}


def test_builds_derived_nodes_from_claims():
    atoms = [make_atom("A", "Revenue 100"), make_atom("B", "Revenue 75")]
    claim = make_derived_claim("delta", ["[A]", "[B]"], 25.0)
    graph = build_evidence_graph(atoms, [claim], [], [])
    derived_nodes = [n for n in graph.nodes.values() if n.node_type == "derived"]
    assert len(derived_nodes) == 1
    assert derived_nodes[0].metadata["rule"] == "delta"


def test_builds_analytical_nodes_from_bundles():
    atoms = [make_atom("A", "Python advantage"), make_atom("B", "Python disadvantage")]
    bundle = make_analytical_bundle("tradeoff", ["[A]", "[B]"], {"pros": [], "cons": []})
    graph = build_evidence_graph(atoms, [], [bundle], [])
    analytical_nodes = [n for n in graph.nodes.values() if n.node_type == "analytical"]
    assert len(analytical_nodes) == 1
    assert analytical_nodes[0].metadata["operator"] == "tradeoff"


# ──────────────────────────────────────────────────────────────
# Edge construction
# ──────────────────────────────────────────────────────────────

def test_derived_from_edges_connect_to_source_atoms():
    atoms = [make_atom("A", "Revenue 100"), make_atom("B", "Revenue 75")]
    claim = make_derived_claim("delta", ["[A]", "[B]"], 25.0)
    graph = build_evidence_graph(atoms, [claim], [], [])
    derived_from_edges = [e for e in graph.edges.values() if e.edge_type == EdgeType.DERIVED_FROM]
    assert len(derived_from_edges) == 2  # derived node → A, derived node → B


def test_same_entity_edges_connect_analytical_to_atoms():
    atoms = [make_atom("A", "Python fast"), make_atom("B", "Python popular")]
    bundle = make_analytical_bundle("compare_contrast", ["[A]", "[B]"], {})
    graph = build_evidence_graph(atoms, [], [bundle], [])
    same_entity_edges = [e for e in graph.edges.values() if e.edge_type == EdgeType.SAME_ENTITY]
    assert len(same_entity_edges) == 2


def test_contradicts_edges_from_contradiction_list():
    atoms = [make_atom("A", "Python is fast"), make_atom("B", "Python is slow")]
    contradictions = [{"atom_a_id": "[A]", "atom_b_id": "[B]", "description": "speed conflict",
                       "claim_a": "fast", "claim_b": "slow"}]
    graph = build_evidence_graph(atoms, [], [], contradictions)
    contradicts_edges = [e for e in graph.edges.values() if e.edge_type == EdgeType.CONTRADICTS]
    assert len(contradicts_edges) >= 1


def test_elaborates_edges_for_similar_atoms():
    """Atoms with high Jaccard overlap (>=0.4) get ELABORATES edges."""
    atoms = [
        make_atom("A", "Python is a popular high-level programming language used widely"),
        make_atom("B", "Python is a popular high-level language and widely used in industry"),
        make_atom("C", "Rust focuses on memory safety and low-level systems programming"),
    ]
    graph = build_evidence_graph(atoms, [], [], [])
    elaborates_edges = [e for e in graph.edges.values() if e.edge_type == EdgeType.ELABORATES]
    # A and B should have ELABORATES between them (high overlap)
    assert len(elaborates_edges) >= 1


# ──────────────────────────────────────────────────────────────
# Navigation methods
# ──────────────────────────────────────────────────────────────

def test_get_connected_component_returns_related_nodes():
    atoms = [make_atom("A", "Revenue 100"), make_atom("B", "Revenue 75"), make_atom("C", "Unrelated topic here")]
    claim = make_derived_claim("delta", ["[A]", "[B]"], 25.0)
    graph = build_evidence_graph(atoms, [claim], [], [])

    derived_node = next(n for n in graph.nodes.values() if n.node_type == "derived")
    component = graph.get_connected_component(derived_node.id)
    # Should contain the derived node + both source atoms
    assert len(component) >= 3


def test_get_supporting_chain_follows_derived_from_edges():
    atoms = [make_atom("A", "Revenue 100"), make_atom("B", "Revenue 75")]
    claim = make_derived_claim("percent_change", ["[A]", "[B]"], -25.0)
    graph = build_evidence_graph(atoms, [claim], [], [])

    derived_node = next(n for n in graph.nodes.values() if n.node_type == "derived")
    chain = graph.get_supporting_chain(derived_node.id)
    # Must include at least the two source atom IDs
    assert len(chain) >= 2


def test_get_contradictions_returns_contradiction_node_ids():
    atoms = [make_atom("A", "Python is fast"), make_atom("B", "Python is slow")]
    contradictions = [{"atom_a_id": "[A]", "atom_b_id": "[B]", "description": "speed",
                       "claim_a": "fast", "claim_b": "slow"}]
    graph = build_evidence_graph(atoms, [], [], contradictions)
    contradiction_ids = graph.get_contradictions()
    assert len(contradiction_ids) >= 1


# ──────────────────────────────────────────────────────────────
# Determinism
# ──────────────────────────────────────────────────────────────

def test_determinism_same_input_same_graph():
    atoms = [make_atom("A", "Content alpha"), make_atom("B", "Content beta")]
    claim = make_derived_claim("delta", ["[A]", "[B]"], 5.0)
    g1 = build_evidence_graph(atoms, [claim], [], [])
    g2 = build_evidence_graph(atoms, [claim], [], [])
    assert set(g1.nodes.keys()) == set(g2.nodes.keys())
    assert set(g1.edges.keys()) == set(g2.edges.keys())


def test_index_by_entity_populated():
    atoms = [
        make_atom("A", "Python content", entity_id="python"),
        make_atom("B", "Python more content", entity_id="python"),
    ]
    graph = build_evidence_graph(atoms, [], [], [])
    assert "python" in graph.index_by_entity
    assert len(graph.index_by_entity["python"]) == 2
