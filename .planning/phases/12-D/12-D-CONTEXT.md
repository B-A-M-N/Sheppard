# Phase 12-D — Context: Section Planner

## Position in Stack

**12-D = Planning** — explicit report topology before prose generation.

Constructs a structured outline with evidence budgets, section modes, contradiction obligations, and target length bands. The planner decides WHAT the report says, HOW it's organized, and WHERE evidence is thin vs dense — BEFORE the LLM writes anything.

**Master Invariant:** The writer never invents intelligence; it renders intelligence already mechanically assembled upstream.

---

## Current State

**Existing section planner** (`EvidenceAssembler.generate_section_plan()`) calls LLM to generate topics-based sections. This is **LLM-driven, not evidence-driven**. The LLM invents a structure without knowing what evidence actually exists.

**Problem:** LLM-generated structure often ignores evidence gaps, doesn't allocate space for dense clusters, and can't enforce structural guarantees like "this section MUST cover the contradiction between X and Y."

---

## What 12-D Must Replace

The new **evidence-aware section planner** consumes the claim graph (12-C) and evidence packets to produce a deterministic report topology.

### Planner Input

- `EvidenceGraph` from 12-C
- `EvidencePacket` with atoms, derived claims, analytical bundles
- Coverage accounting (which domains have evidence vs which are thin)
- Topic decomposition from frontier (optional)

### SectionPlan Output

```python
@dataclass
class SectionPlan:
    title: str                          # e.g., "Competitive Landscape"
    purpose: str                        # what this section accomplishes
    mode: SectionMode                   # descriptive | comparative | adjudicative | contradi...
    evidence_budget: int                # min atoms/derived_claims needed
    required_atom_ids: List[str]        # evidence that MUST be covered
    allowed_derived_claims: List[str]   # which derivation IDs this section can reference
    contradiction_obligation: Optional[str]  # "address conflict between A001 and A003" if present
    target_length_range: Tuple[int, int]  # (500, 1500) words
    refusal_required: bool              # if evidence insufficient, emit placeholder
    style_mode: str                     # "technical" | "accessible" | "legal" | "academic"
    forbidden_extrapolations: List[str] # what NOT to claim (evidence gaps)
```

### Deterministic Planning Algorithm

1. Analyze claim graph for natural clusters (entities, topics, contradictions)
2. For each cluster, decide section mode:
   - Single entity with many atoms → descriptive
   - Multiple entities compared → comparative
   - Evidence conflicts → adjudicative or contradiction-analysis
   - Methodology + results pairs → implementation-oriented
3. Allocate length budgets based on evidence density
4. Assign required evidence (atoms that MUST be cited)
5. Flag contradictions requiring attention
6. Return sorted SectionPlan list

### Files That Will Change

| File | Change |
|------|--------|
| `src/research/reasoning/section_planner.py` | NEW — EvidenceAwareSectionPlanner class |
| `src/research/reasoning/assembler.py` | Replace LLM-based generate_section_plan with evidence-driven version |
| `SectionPlan` dataclass | Extended with 8+ new fields (see above) |
| `tests/research/reasoning/test_section_planner.py` | NEW — planner determinism, mode assignment, budget allocation tests |
| `.planning/phases/12-D/SECTION_PLANNER_SPEC.md` | NEW — spec |
| `.planning/phases/12-D/REPORT_TOPOLOGY_RULES.md` | NEW — topology rules, mode definitions |
