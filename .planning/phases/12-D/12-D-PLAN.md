---
phase: 12-D
plan: 01
type: tdd
depends_on:
  - 12-C  # EvidenceGraph
  - 12-B  # AnalyticalBundle (consumed by graph)
  - 12-A  # DerivedClaim (consumed by graph)
files_modified:
  - src/research/reasoning/section_planner.py
  - tests/research/reasoning/test_section_planner.py
autonomous: true
---

<objective>
Build EvidenceAwareSectionPlanner — a deterministic, LLM-free planner that reads
EvidenceGraph + EvidencePacket and produces enriched SectionPlan objects with:
modes, evidence budgets, required atoms, contradiction obligations, and refusal flags.

Replaces the gap in the current stack: LLM's generate_section_plan() invents structure
without knowing what evidence exists. This planner makes structure evidence-driven.

Output:
- src/research/reasoning/section_planner.py
- tests/research/reasoning/test_section_planner.py
</objective>

<interfaces>
**EvidenceGraph** (from 12-C):
- nodes: Dict[str, GraphNode] — node_type in {"evidence", "derived", "analytical", "contradiction"}
- index_by_entity: Dict[str, List[str]]
- get_contradictions() → List[str]
- get_connected_component(node_id) → Set[str]

**EvidencePacket** (from assembler.py):
- atoms: List[dict] — each has "global_id", "text", "type", "metadata"
- derived_claims: List[DerivedClaim]
- analytical_bundles: List[AnalyticalBundle]
- contradictions: List[dict]
- evidence_graph: EvidenceGraph

**Existing SectionPlan** (assembler.py, line ~30):
- order, title, purpose, target_evidence_roles: List[str]
→ Keep existing SectionPlan for assembler compatibility.
→ New EnrichedSectionPlan extends/wraps it with new fields.
</interfaces>

<feature>
  <name>EvidenceAwareSectionPlanner</name>
  <files>
    src/research/reasoning/section_planner.py
    tests/research/reasoning/test_section_planner.py
  </files>

  <data_model>
    class SectionMode(str, Enum):
        DESCRIPTIVE = "descriptive"        # single entity, many atoms
        COMPARATIVE = "comparative"        # 2+ entities compared
        ADJUDICATIVE = "adjudicative"      # evidence conflicts must be resolved
        IMPLEMENTATION = "implementation"  # method/result pairs dominate
        SURVEY = "survey"                  # broad coverage, no single focus

    @dataclass
    class EnrichedSectionPlan:
        title: str
        purpose: str
        mode: SectionMode
        evidence_budget: int                       # min atoms needed
        required_atom_ids: List[str]               # must cite these
        allowed_derived_claim_ids: List[str]       # derivations scoped to this section
        contradiction_obligation: Optional[str]    # None or description of conflict to address
        contradiction_atom_ids: Optional[List[str]]  # [atom_id_a, atom_id_b] for Gate 3 verification
        target_length_range: Tuple[int, int]       # (min_words, max_words)
        refusal_required: bool                     # True if evidence_budget not met
        forbidden_extrapolations: List[str]        # evidence gaps → warn writer
        order: int                                 # section order (1-indexed)
  </data_model>

  <algorithm>
    class EvidenceAwareSectionPlanner:
        def plan(graph: EvidenceGraph, packet: EvidencePacket) → List[EnrichedSectionPlan]:

        Step 1: Cluster atoms by entity (graph.index_by_entity)
        Step 2: Assign SectionMode per cluster:
            - 1 entity, ≥3 atoms → DESCRIPTIVE
            - 2+ entities in same graph component → COMPARATIVE
            - cluster has contradiction nodes → ADJUDICATIVE
            - cluster has method_result analytical bundle → IMPLEMENTATION
            - no clear cluster (sparse/mixed) → SURVEY
        Step 3: Allocate evidence_budget = len(atom_ids_in_cluster)
        Step 4: required_atom_ids = atom_ids in cluster
        Step 5: allowed_derived_claim_ids = derived claims whose source_atom_ids ⊆ cluster atoms
        Step 6: contradiction_obligation = description of first contradiction in cluster (or None)
        Step 7: target_length_range = (budget * 80, budget * 200) words, clamped (300, 3000)
        Step 8: refusal_required = True if len(required_atom_ids) < 2
        Step 9: forbidden_extrapolations = entity names in graph NOT covered by cluster atoms
        Step 10: Sort sections by order (entity clusters sorted by atom count desc)

        Also emit one SURVEY section at end if unclustered atoms > 0.
  </algorithm>

  <behavior>
    RED: 10 tests covering:
    1. test_mode_single_entity_descriptive
    2. test_mode_multi_entity_comparative
    3. test_mode_contradiction_adjudicative
    4. test_mode_method_result_implementation
    5. test_evidence_budget_equals_cluster_atom_count
    6. test_required_atoms_all_cluster_atoms
    7. test_contradiction_obligation_populated
    8. test_refusal_required_if_below_minimum
    9. test_determinism_same_graph_same_plan
    10. test_allowed_derived_ids_scoped_to_cluster

    GREEN: implement EvidenceAwareSectionPlanner
    REFACTOR: ensure skip-on-failure, sort order deterministic
  </behavior>
</feature>

<implementation>
  RED → GREEN → REFACTOR.

  No LLM calls. All deterministic.
  Skip-on-failure: if graph is empty or malformed, return [] (never raise).
  Deterministic: sort atoms/entities alphabetically before processing.
  No integration into assembler.py — section_planner is called by 12-E pipeline.
</implementation>

<verification>
  <automated>PYTHONPATH=src python -m pytest tests/research/reasoning/test_section_planner.py -v</automated>
  <automated>PYTHONPATH=src python -m pytest tests/research/ -x -q</automated>
</verification>

<success_criteria>
- tests/research/reasoning/test_section_planner.py with 10 tests, all pass
- No regression in existing test suite
- SectionMode enum has 5 values
- EnrichedSectionPlan has all 11 fields
- Planner is deterministic (same graph → same output order and content)
- refusal_required=True when atom count < 2
</success_criteria>
