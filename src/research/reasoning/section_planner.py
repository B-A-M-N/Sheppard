"""
src/research/reasoning/section_planner.py

Evidence-Aware Section Planner — Phase 12-D.

Produces EnrichedSectionPlan objects from EvidenceGraph + EvidencePacket.
Deterministic, LLM-free: same inputs → same plan structure.

Algorithm:
1. Cluster atoms by entity metadata (from graph.index_by_entity)
2. Assign SectionMode per cluster based on graph topology
3. Compute evidence budgets, required atoms, allowed derivations
4. Flag contradiction obligations and refusal thresholds
5. Return sorted EnrichedSectionPlan list
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Enums and data model
# ──────────────────────────────────────────────────────────────

class SectionMode(str, Enum):
    DESCRIPTIVE    = "descriptive"     # single entity with many supporting atoms
    COMPARATIVE    = "comparative"     # multiple entities compared
    ADJUDICATIVE   = "adjudicative"    # evidence conflict requires resolution
    IMPLEMENTATION = "implementation"  # method/result pairs dominate
    SURVEY         = "survey"          # broad coverage, no single focus


@dataclass
class EnrichedSectionPlan:
    """Fully structured section plan with evidence budget and obligations."""
    title: str
    purpose: str
    mode: SectionMode
    evidence_budget: int                        # min atoms for this section
    required_atom_ids: List[str]                # must be cited
    allowed_derived_claim_ids: List[str]        # derivations scoped to this section
    contradiction_obligation: Optional[str]     # description of conflict to address
    contradiction_atom_ids: Optional[List[str]] # [atom_a_id, atom_b_id] for gate verification
    target_length_range: Tuple[int, int]        # (min_words, max_words)
    refusal_required: bool                      # True if evidence below minimum
    forbidden_extrapolations: List[str]         # gaps — warn the writer
    order: int                                  # 1-indexed section position


# ──────────────────────────────────────────────────────────────
# Planner
# ──────────────────────────────────────────────────────────────

_MIN_ATOMS_BEFORE_REFUSAL = 2
_WORDS_PER_ATOM_MIN = 80
_WORDS_PER_ATOM_MAX = 200
_LENGTH_FLOOR = 300
_LENGTH_CEILING = 3000


class EvidenceAwareSectionPlanner:
    """
    Deterministic, LLM-free evidence-aware section planner.

    Usage:
        plans = EvidenceAwareSectionPlanner().plan(evidence_graph, packet)
    """

    def plan(self, graph, packet) -> List[EnrichedSectionPlan]:
        """
        Produce a sorted list of EnrichedSectionPlan from graph + packet.
        Returns [] on any error (never raises).
        """
        try:
            return self._plan(graph, packet)
        except Exception as e:
            logger.debug(f"[SectionPlanner] plan() failed: {e}")
            return []

    def _plan(self, graph, packet) -> List[EnrichedSectionPlan]:
        all_atom_ids = {n.metadata["citation_key"]
                        for n in graph.nodes.values()
                        if n.node_type == "evidence"}

        # --- Build clusters from entity index ---
        clusters: Dict[str, List[str]] = {}  # entity → sorted atom_ids

        for entity, node_ids in sorted(graph.index_by_entity.items()):
            atom_ids = []
            for nid in node_ids:
                node = graph.nodes.get(nid)
                if node and node.node_type == "evidence":
                    atom_ids.append(node.metadata["citation_key"])
            if atom_ids:
                clusters[entity] = sorted(atom_ids)

        # --- Unclustered atoms → SURVEY ---
        clustered_atom_ids: set = set()
        for ids in clusters.values():
            clustered_atom_ids.update(ids)
        unclustered = sorted(all_atom_ids - clustered_atom_ids)

        # --- Contradiction lookup per atom_id ---
        contradiction_map: Dict[str, Dict] = {}  # atom_id → contradiction dict
        for n in graph.nodes.values():
            if n.node_type == "contradiction":
                a = n.metadata.get("atom_a_id", "")
                b = n.metadata.get("atom_b_id", "")
                if a:
                    contradiction_map[a] = n.metadata
                if b:
                    contradiction_map[b] = n.metadata

        # --- Analytical bundle lookup ---
        method_result_atom_ids: set = set()
        for bundle in getattr(packet, "analytical_bundles", []):
            if bundle.operator == "method_result":
                for aid in bundle.atom_ids:
                    method_result_atom_ids.add(aid)

        # --- Derived claim lookup ---
        derived_claims = getattr(packet, "derived_claims", [])

        plans: List[EnrichedSectionPlan] = []
        order = 1

        # Sort clusters by atom count desc, then entity name for ties
        sorted_clusters = sorted(clusters.items(), key=lambda x: (-len(x[1]), x[0]))

        for entity, atom_ids in sorted_clusters:
            mode = self._assign_mode(entity, atom_ids, contradiction_map,
                                     method_result_atom_ids, clusters)

            # Contradiction obligation
            contr_obligation = None
            contr_atom_ids = None
            for aid in atom_ids:
                if aid in contradiction_map:
                    c = contradiction_map[aid]
                    contr_obligation = c.get("description", "")
                    contr_atom_ids = [c.get("atom_a_id"), c.get("atom_b_id")]
                    contr_atom_ids = [x for x in contr_atom_ids if x]
                    break

            # Allowed derived claims: only those whose source atoms are all in this cluster
            atom_id_set = set(atom_ids)
            allowed_derived = [
                c.id for c in derived_claims
                if atom_id_set.issuperset(c.source_atom_ids)
            ]

            # Length budget
            budget = len(atom_ids)
            min_words = max(_LENGTH_FLOOR, budget * _WORDS_PER_ATOM_MIN)
            max_words = min(_LENGTH_CEILING, budget * _WORDS_PER_ATOM_MAX)

            # Forbidden extrapolations: other entity names not in this cluster
            forbidden = sorted(set(clusters.keys()) - {entity})

            plans.append(EnrichedSectionPlan(
                title=entity.replace("_", " ").title(),
                purpose=f"Cover evidence about {entity}",
                mode=mode,
                evidence_budget=budget,
                required_atom_ids=atom_ids,
                allowed_derived_claim_ids=allowed_derived,
                contradiction_obligation=contr_obligation,
                contradiction_atom_ids=contr_atom_ids,
                target_length_range=(min_words, max_words),
                refusal_required=(budget < _MIN_ATOMS_BEFORE_REFUSAL),
                forbidden_extrapolations=forbidden,
                order=order,
            ))
            order += 1

        # --- SURVEY/mixed section for unclustered atoms ---
        if unclustered:
            budget = len(unclustered)
            # Determine mode for unclustered group
            has_contradiction = any(aid in contradiction_map for aid in unclustered)
            has_method_result = any(aid in method_result_atom_ids for aid in unclustered)
            if has_contradiction:
                unclustered_mode = SectionMode.ADJUDICATIVE
            elif has_method_result:
                unclustered_mode = SectionMode.IMPLEMENTATION
            else:
                unclustered_mode = SectionMode.SURVEY

            # Contradiction obligation for unclustered group
            unc_contr_obligation = None
            unc_contr_atom_ids = None
            for aid in unclustered:
                if aid in contradiction_map:
                    c = contradiction_map[aid]
                    unc_contr_obligation = c.get("description", "")
                    unc_contr_atom_ids = [c.get("atom_a_id"), c.get("atom_b_id")]
                    unc_contr_atom_ids = [x for x in unc_contr_atom_ids if x]
                    break

            plans.append(EnrichedSectionPlan(
                title="Additional Evidence",
                purpose="Cover evidence not tied to a specific entity",
                mode=unclustered_mode,
                evidence_budget=budget,
                required_atom_ids=unclustered,
                allowed_derived_claim_ids=[
                    c.id for c in derived_claims
                    if set(c.source_atom_ids).issubset(set(unclustered))
                ],
                contradiction_obligation=unc_contr_obligation,
                contradiction_atom_ids=unc_contr_atom_ids,
                target_length_range=(
                    max(_LENGTH_FLOOR, budget * _WORDS_PER_ATOM_MIN),
                    min(_LENGTH_CEILING, budget * _WORDS_PER_ATOM_MAX),
                ),
                refusal_required=(budget < _MIN_ATOMS_BEFORE_REFUSAL),
                forbidden_extrapolations=[],
                order=order,
            ))

        return plans

    def _assign_mode(
        self,
        entity: str,
        atom_ids: List[str],
        contradiction_map: Dict,
        method_result_ids: set,
        all_clusters: Dict,
    ) -> SectionMode:
        # Contradiction in cluster → ADJUDICATIVE
        if any(aid in contradiction_map for aid in atom_ids):
            return SectionMode.ADJUDICATIVE

        # Method/result bundle covers cluster atoms → IMPLEMENTATION
        if any(aid in method_result_ids for aid in atom_ids):
            return SectionMode.IMPLEMENTATION

        # 2+ entities with ≥2 atoms each → COMPARATIVE
        multi_entity_clusters = [e for e, ids in all_clusters.items() if len(ids) >= 2]
        if len(multi_entity_clusters) >= 2:
            return SectionMode.COMPARATIVE

        # Single entity with many atoms → DESCRIPTIVE
        if len(atom_ids) >= 2:
            return SectionMode.DESCRIPTIVE

        # Fallback
        return SectionMode.SURVEY
