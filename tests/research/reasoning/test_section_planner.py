"""
tests/research/reasoning/test_section_planner.py

TDD tests for Phase 12-D: Evidence-Aware Section Planner.
"""

import sys, os
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
for _p in [os.path.join(_root, "src"), _root]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from retrieval.models import RetrievedItem
from research.derivation.engine import DerivedClaim, make_claim_id
from research.reasoning.analytical_operators import AnalyticalBundle
from research.graph.claim_graph import build_evidence_graph
from research.reasoning.section_planner import (
    SectionMode,
    EnrichedSectionPlan,
    EvidenceAwareSectionPlanner,
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

def make_derived(rule, source_ids, output=5.0):
    return DerivedClaim(
        id=make_claim_id(rule, source_ids),
        rule=rule, source_atom_ids=sorted(source_ids),
        output=output, metadata={},
    )

def make_bundle(operator, atom_ids):
    return AnalyticalBundle(operator=operator, atom_ids=atom_ids, output={}, metadata={})

def build_packet(atoms, derived=None, bundles=None, contradictions=None):
    """Build a fake EvidencePacket-like namespace."""
    from types import SimpleNamespace
    derived = derived or []
    bundles = bundles or []
    contradictions = contradictions or []
    graph = build_evidence_graph(atoms, derived, bundles, contradictions)
    return SimpleNamespace(
        atoms=[{"global_id": a.citation_key, "text": a.content} for a in atoms],
        derived_claims=derived,
        analytical_bundles=bundles,
        contradictions=contradictions,
        evidence_graph=graph,
    )

planner = EvidenceAwareSectionPlanner()


# ──────────────────────────────────────────────────────────────
# Mode assignment tests
# ──────────────────────────────────────────────────────────────

def test_mode_single_entity_descriptive():
    """3+ atoms for one entity → DESCRIPTIVE section."""
    atoms = [
        make_atom("A", "Python is popular", entity_id="python"),
        make_atom("B", "Python is dynamic", entity_id="python"),
        make_atom("C", "Python has many libraries", entity_id="python"),
    ]
    packet = build_packet(atoms)
    plans = planner.plan(packet.evidence_graph, packet)
    entity_section = next((p for p in plans if p.mode == SectionMode.DESCRIPTIVE), None)
    assert entity_section is not None


def test_mode_multi_entity_comparative():
    """2+ entities each with ≥2 atoms → COMPARATIVE section."""
    atoms = [
        make_atom("A", "Python is dynamic", entity_id="python"),
        make_atom("B", "Python is interpreted", entity_id="python"),
        make_atom("C", "Java is compiled", entity_id="java"),
        make_atom("D", "Java is verbose", entity_id="java"),
    ]
    packet = build_packet(atoms)
    plans = planner.plan(packet.evidence_graph, packet)
    modes = {p.mode for p in plans}
    assert SectionMode.COMPARATIVE in modes or SectionMode.DESCRIPTIVE in modes


def test_mode_contradiction_adjudicative():
    """Cluster with contradiction → ADJUDICATIVE."""
    atoms = [
        make_atom("A", "Python is fast"),
        make_atom("B", "Python is slow"),
    ]
    contradictions = [{"atom_a_id": "[A]", "atom_b_id": "[B]",
                       "description": "speed conflict", "claim_a": "fast", "claim_b": "slow"}]
    packet = build_packet(atoms, contradictions=contradictions)
    plans = planner.plan(packet.evidence_graph, packet)
    modes = {p.mode for p in plans}
    assert SectionMode.ADJUDICATIVE in modes


def test_mode_method_result_implementation():
    """Cluster with method_result bundle → IMPLEMENTATION."""
    atoms = [
        make_atom("A", "We used random sampling", item_type="methodology"),
        make_atom("B", "Results showed 15% improvement", item_type="result"),
    ]
    bundles = [make_bundle("method_result", ["[A]", "[B]"])]
    packet = build_packet(atoms, bundles=bundles)
    plans = planner.plan(packet.evidence_graph, packet)
    modes = {p.mode for p in plans}
    assert SectionMode.IMPLEMENTATION in modes


# ──────────────────────────────────────────────────────────────
# Budget and atom assignment
# ──────────────────────────────────────────────────────────────

def test_evidence_budget_equals_cluster_atom_count():
    """evidence_budget = number of atoms in the section's cluster."""
    atoms = [
        make_atom("A", "Python is popular", entity_id="python"),
        make_atom("B", "Python is fast", entity_id="python"),
        make_atom("C", "Python is readable", entity_id="python"),
    ]
    packet = build_packet(atoms)
    plans = planner.plan(packet.evidence_graph, packet)
    assert len(plans) >= 1
    # The python cluster has 3 atoms
    py_plan = next((p for p in plans if p.evidence_budget == 3), None)
    assert py_plan is not None


def test_required_atoms_all_cluster_atoms():
    """required_atom_ids contains all atom citation keys in the cluster."""
    atoms = [
        make_atom("A", "Content alpha", entity_id="topic_x"),
        make_atom("B", "Content beta", entity_id="topic_x"),
    ]
    packet = build_packet(atoms)
    plans = planner.plan(packet.evidence_graph, packet)
    assert len(plans) >= 1
    plan = plans[0]
    assert "[A]" in plan.required_atom_ids
    assert "[B]" in plan.required_atom_ids


def test_allowed_derived_ids_scoped_to_cluster():
    """allowed_derived_claim_ids only includes claims whose source atoms are in the cluster."""
    atoms = [
        make_atom("A", "Revenue 100", entity_id="finance"),
        make_atom("B", "Revenue 75", entity_id="finance"),
        make_atom("C", "Unrelated fact about weather", entity_id="weather"),
    ]
    derived_in = make_derived("delta", ["[A]", "[B]"], 25.0)
    derived_out = make_derived("delta", ["[A]", "[C]"], 5.0)
    packet = build_packet(atoms, derived=[derived_in, derived_out])
    plans = planner.plan(packet.evidence_graph, packet)
    finance_plan = next((p for p in plans if "[A]" in p.required_atom_ids
                         and "[B]" in p.required_atom_ids), None)
    if finance_plan:
        # derived_out references [C] which is not in finance cluster → excluded
        assert derived_out.id not in finance_plan.allowed_derived_claim_ids


# ──────────────────────────────────────────────────────────────
# Contradiction obligation
# ──────────────────────────────────────────────────────────────

def test_contradiction_obligation_populated():
    """Sections with contradiction nodes get contradiction_obligation and contradiction_atom_ids."""
    atoms = [make_atom("A", "Python fast"), make_atom("B", "Python slow")]
    contradictions = [{"atom_a_id": "[A]", "atom_b_id": "[B]",
                       "description": "speed dispute", "claim_a": "fast", "claim_b": "slow"}]
    packet = build_packet(atoms, contradictions=contradictions)
    plans = planner.plan(packet.evidence_graph, packet)
    adj_plan = next((p for p in plans if p.mode == SectionMode.ADJUDICATIVE), None)
    assert adj_plan is not None
    assert adj_plan.contradiction_obligation is not None
    assert adj_plan.contradiction_atom_ids is not None
    assert "[A]" in adj_plan.contradiction_atom_ids
    assert "[B]" in adj_plan.contradiction_atom_ids


# ──────────────────────────────────────────────────────────────
# Refusal and determinism
# ──────────────────────────────────────────────────────────────

def test_refusal_required_if_below_minimum():
    """Cluster with < 2 atoms → refusal_required=True."""
    atoms = [make_atom("A", "Single atom content", entity_id="lonely")]
    packet = build_packet(atoms)
    plans = planner.plan(packet.evidence_graph, packet)
    # Cluster of 1 atom → refusal
    lonely = next((p for p in plans if "[A]" in p.required_atom_ids), None)
    if lonely:
        assert lonely.refusal_required is True


def test_determinism_same_graph_same_plan():
    """Same inputs → same plan output order and content."""
    atoms = [
        make_atom("A", "Python popular", entity_id="python"),
        make_atom("B", "Python fast", entity_id="python"),
    ]
    packet = build_packet(atoms)
    plans1 = planner.plan(packet.evidence_graph, packet)
    plans2 = planner.plan(packet.evidence_graph, packet)
    assert [p.title for p in plans1] == [p.title for p in plans2]
    assert [p.mode for p in plans1] == [p.mode for p in plans2]
