"""
Tests for src/research/graph/gap_scorer.py

Covers:
  - Empty graph → empty list
  - All four gap types are detected and carry correct priority
  - Derived node with a DERIVED_FROM edge is NOT flagged
  - Evidence node with edges is not flagged as isolated (but may be sparse_cluster)
  - Evidence node in multi-node component is not flagged as sparse_cluster
  - Content truncated to 120 chars
  - Empty-content nodes are skipped for isolated / sparse_cluster
  - Deduplication by query string
  - Priority ordering (contradiction > unsupported_derived > isolated > sparse_cluster)
  - max_gaps cap
  - Determinism: repeated calls on same graph produce identical lists
"""

import pytest

from src.research.graph.claim_graph import EdgeType, EvidenceGraph, GraphEdge, GraphNode
from src.research.graph.gap_scorer import RetrievalGap, score_gaps


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _node(nid: str, node_type: str, content: str = "test content") -> GraphNode:
    return GraphNode(id=nid, node_type=node_type, content=content)


def _edge(source: str, target: str, edge_type: EdgeType) -> GraphEdge:
    eid = f"{source}:{edge_type.value}:{target}"
    return GraphEdge(id=eid, source_id=source, target_id=target, edge_type=edge_type)


def _graph(*nodes: GraphNode, edges: list[GraphEdge] | None = None) -> EvidenceGraph:
    g = EvidenceGraph()
    for n in nodes:
        g.nodes[n.id] = n
    for e in (edges or []):
        g.edges[e.id] = e
    return g


# ──────────────────────────────────────────────────────────────
# Empty graph
# ──────────────────────────────────────────────────────────────

def test_empty_graph_returns_empty_list():
    assert score_gaps(EvidenceGraph()) == []


# ──────────────────────────────────────────────────────────────
# Contradiction gaps (priority 0.9)
# ──────────────────────────────────────────────────────────────

def test_contradiction_node_produces_gap():
    n = _node("c1", "contradiction", "conflicting claim about X")
    g = _graph(n)
    gaps = score_gaps(g)
    assert len(gaps) == 1
    assert gaps[0].gap_type == "contradiction"
    assert gaps[0].priority == 0.9
    assert gaps[0].query == "conflicting claim about X"
    assert gaps[0].source_node_ids == ["c1"]


def test_contradiction_gap_uses_fallback_when_content_empty():
    n = _node("c1", "contradiction", "")
    g = _graph(n)
    gaps = score_gaps(g)
    assert gaps[0].query == "unresolved contradiction"


def test_contradiction_content_truncated_to_120():
    content = "x" * 200
    n = _node("c1", "contradiction", content)
    g = _graph(n)
    gaps = score_gaps(g)
    assert gaps[0].query == "x" * 120


# ──────────────────────────────────────────────────────────────
# Unsupported derived gaps (priority 0.7)
# ──────────────────────────────────────────────────────────────

def test_derived_node_without_derived_from_edge_flagged():
    n = _node("d1", "derived", "a derived insight")
    g = _graph(n)
    gaps = score_gaps(g)
    assert len(gaps) == 1
    assert gaps[0].gap_type == "unsupported_derived"
    assert gaps[0].priority == 0.7
    assert gaps[0].source_node_ids == ["d1"]


def test_derived_node_with_derived_from_edge_not_flagged():
    ev = _node("ev1", "evidence", "atom content")
    dr = _node("d1", "derived", "a derived insight")
    e = _edge("d1", "ev1", EdgeType.DERIVED_FROM)
    g = _graph(ev, dr, edges=[e])
    gaps = score_gaps(g)
    # ev1 has degree 1 (not isolated), d1 has DERIVED_FROM support
    # Only possible gap: sparse_cluster (ev1 is in size-1 component? No — d1 is also connected)
    # Both nodes share an edge so the component has 2 members (d1 + ev1).
    # But d1 is "derived", not "evidence", so connected_evidence = {ev1},
    # and component restricted to connected_evidence = {ev1} (size 1 → sparse_cluster).
    types = [g.gap_type for g in gaps]
    assert "unsupported_derived" not in types


def test_derived_node_uses_fallback_when_content_empty():
    n = _node("d1", "derived", "")
    g = _graph(n)
    gaps = score_gaps(g)
    assert gaps[0].query == "derived claim"


# ──────────────────────────────────────────────────────────────
# Isolated evidence gaps (priority 0.6)
# ──────────────────────────────────────────────────────────────

def test_isolated_evidence_node_flagged():
    n = _node("ev1", "evidence", "orphaned fact")
    g = _graph(n)
    gaps = score_gaps(g)
    assert len(gaps) == 1
    assert gaps[0].gap_type == "isolated"
    assert gaps[0].priority == 0.6


def test_connected_evidence_node_not_flagged_as_isolated():
    ev1 = _node("ev1", "evidence", "fact one")
    ev2 = _node("ev2", "evidence", "fact two")
    e = _edge("ev1", "ev2", EdgeType.SUPPORTS)
    g = _graph(ev1, ev2, edges=[e])
    types = [g.gap_type for g in score_gaps(g)]
    assert "isolated" not in types


def test_isolated_evidence_skipped_when_content_empty():
    n = _node("ev1", "evidence", "")
    g = _graph(n)
    assert score_gaps(g) == []


# ──────────────────────────────────────────────────────────────
# Sparse cluster gaps (priority 0.5)
# ──────────────────────────────────────────────────────────────

def test_singleton_connected_component_flagged_as_sparse_cluster():
    # ev1 has a SUPPORTS edge to a derived node — degree > 0, but the evidence-only
    # component is size 1.
    ev1 = _node("ev1", "evidence", "lone connected fact")
    dr = _node("d1", "derived", "some claim")
    e = _edge("ev1", "d1", EdgeType.SUPPORTS)
    g = _graph(ev1, dr, edges=[e])
    types = [g.gap_type for g in score_gaps(g)]
    assert "sparse_cluster" in types


def test_multi_node_evidence_component_not_sparse_cluster():
    ev1 = _node("ev1", "evidence", "fact one")
    ev2 = _node("ev2", "evidence", "fact two")
    e = _edge("ev1", "ev2", EdgeType.SUPPORTS)
    g = _graph(ev1, ev2, edges=[e])
    types = [g.gap_type for g in score_gaps(g)]
    assert "sparse_cluster" not in types


def test_sparse_cluster_skipped_when_content_empty():
    ev1 = _node("ev1", "evidence", "")
    dr = _node("d1", "derived", "some claim")
    e = _edge("ev1", "d1", EdgeType.SUPPORTS)
    g = _graph(ev1, dr, edges=[e])
    types = [g.gap_type for g in score_gaps(g)]
    assert "sparse_cluster" not in types


# ──────────────────────────────────────────────────────────────
# Deduplication by query string
# ──────────────────────────────────────────────────────────────

def test_duplicate_query_strings_deduplicated():
    # Two contradiction nodes with identical content → only one gap.
    n1 = _node("c1", "contradiction", "same query text")
    n2 = _node("c2", "contradiction", "same query text")
    g = _graph(n1, n2)
    gaps = score_gaps(g, max_gaps=10)
    queries = [gp.query for gp in gaps]
    assert queries.count("same query text") == 1


# ──────────────────────────────────────────────────────────────
# Priority ordering
# ──────────────────────────────────────────────────────────────

def test_priority_ordering_contradiction_first():
    contradiction = _node("c1", "contradiction", "conflict")
    derived = _node("d1", "derived", "unsupported derived")
    isolated = _node("ev1", "evidence", "isolated atom")
    g = _graph(contradiction, derived, isolated)
    gaps = score_gaps(g, max_gaps=10)
    priorities = [gp.priority for gp in gaps]
    assert priorities == sorted(priorities, reverse=True)
    assert priorities[0] == 0.9


def test_unsupported_derived_before_isolated():
    derived = _node("d1", "derived", "unsupported claim")
    isolated = _node("ev1", "evidence", "isolated atom")
    g = _graph(derived, isolated)
    gaps = score_gaps(g, max_gaps=10)
    types = [gp.gap_type for gp in gaps]
    assert types.index("unsupported_derived") < types.index("isolated")


# ──────────────────────────────────────────────────────────────
# max_gaps cap
# ──────────────────────────────────────────────────────────────

def test_max_gaps_caps_output():
    nodes = [_node(f"c{i}", "contradiction", f"conflict {i}") for i in range(10)]
    g = _graph(*nodes)
    gaps = score_gaps(g, max_gaps=3)
    assert len(gaps) == 3


def test_max_gaps_zero_returns_empty():
    n = _node("c1", "contradiction", "conflict")
    g = _graph(n)
    assert score_gaps(g, max_gaps=0) == []


# ──────────────────────────────────────────────────────────────
# Determinism
# ──────────────────────────────────────────────────────────────

def test_same_graph_produces_identical_output():
    n1 = _node("c1", "contradiction", "conflict A")
    n2 = _node("c2", "contradiction", "conflict B")
    n3 = _node("ev1", "evidence", "orphan")
    g = _graph(n1, n2, n3)
    first = score_gaps(g, max_gaps=10)
    second = score_gaps(g, max_gaps=10)
    assert [(gp.gap_type, gp.query, gp.priority) for gp in first] == \
           [(gp.gap_type, gp.query, gp.priority) for gp in second]


# ──────────────────────────────────────────────────────────────
# Non-evidence/derived/contradiction node types ignored
# ──────────────────────────────────────────────────────────────

def test_analytical_node_not_flagged_as_isolated():
    n = _node("a1", "analytical", "some analytical bundle")
    g = _graph(n)
    assert score_gaps(g) == []


# ──────────────────────────────────────────────────────────────
# RetrievalGap dataclass basics
# ──────────────────────────────────────────────────────────────

def test_retrieval_gap_defaults():
    gap = RetrievalGap(query="test", priority=0.5, gap_type="isolated")
    assert gap.source_node_ids == []
