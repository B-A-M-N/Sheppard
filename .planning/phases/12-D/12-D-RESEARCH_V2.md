# Phase 12-D: Section Planner - Research

**Researched:** 2026-04-01
**Domain:** Deterministic evidence-aware report planning
**Confidence:** HIGH

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Deterministic Algorithm:** The planner must follow a 6-step deterministic algorithm (analyze clusters → decide modes → allocate budgets → assign evidence → flag contradictions → return sorted list).
- **Master Invariant:** The writer never invents intelligence; it renders intelligence already mechanically assembled upstream.
- **Planner Input:** `EvidenceGraph` (from 12-C), `EvidencePacket` with atoms and derived claims.
- **SectionPlan Schema:** Extended with 11 specific fields (title, purpose, mode, budget, required_atom_ids, allowed_claims, contradiction_obligation, length_range, refusal_required, style_mode, forbidden_extrapolations).

### the agent's Discretion
- **Clustering Heuristics:** The specific algorithms for graph clustering (e.g., entity-centric vs. community-based) are left to the implementation.
- **Section Sequencing:** The logic for sorting sections for optimal report flow (e.g., intro → comparative → conclusion) is at the agent's discretion.
- **Budgeting Formula:** The exact linear or non-linear mapping from atom count to word length.

### Deferred Ideas (OUT OF SCOPE)
- **Multi-document merging:** Planning across multiple reports or mission histories is deferred.
- **Interactive planning:** User feedback during the planning stage is not yet required.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| 12-D-01 | Replace LLM-based planner with deterministic version | Rule-based clustering and mode assignment logic identified. |
| 12-D-02 | Consume `ClaimGraph` for planning | NetworkX integration confirmed as standard in Phase 12-C. |
| 12-D-03 | Assign `SectionMode` per cluster | Logic for mapping graph topology to modes (descriptive, comparative, etc.) established. |
| 12-D-04 | Allocate deterministic length budgets | Linear formula based on atom/claim count developed. |
| 12-D-05 | Flag structural contradictions | Contradiction edge traversal in `ClaimGraph` verified. |

## Summary

Phase 12-D replaces the LLM-driven report architecting (which is currently prone to hallucination and ignoring evidence gaps) with a deterministic transformer that maps the `ClaimGraph` (from 12-C) to a structured `SectionPlan`. This ensures that the report structure is a direct function of available evidence.

**Primary recommendation:** Use an **entity-centric clustering** strategy to partition the `ClaimGraph`. Each cluster becomes a section, with its "Mode" (descriptive, comparative, adjudicative) determined by the internal connectivity and edge types (e.g., presence of `CONTRADICTS` or `DERIVED_FROM` edges).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| NetworkX | 3.x | Graph analysis and clustering | Confirmed in 12-C-RESEARCH_FULL as the standard for Sheppard graph processing. |
| Dataclasses | Built-in | Plan structure | Existing `assembler.py` and `derivation/engine.py` use dataclasses for state. |
| Enum | Built-in | Section modes | Provides type-safe mode definitions. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| Itertools | Built-in | Deterministic grouping | Using `groupby` and `sorted` for cluster consolidation. |
| Hashlib | Built-in | Deterministic ID generation | Used for generating section IDs if needed for traceability. |

**Installation:**
```bash
# NetworkX should already be available or added in 12-C
npm view networkx version # 3.2.1 as of TRAINING
```

## Architecture Patterns

### Recommended Project Structure
```
src/research/reasoning/
├── section_planner.py   # NEW: EvidenceAwareSectionPlanner class
├── assembler.py         # Modified: Integrated planner replacement
└── models/
    └── section.py       # NEW: SectionPlan and SectionMode definitions
```

### Pattern 1: Graph-to-Plan Transformation
The planner is a pure function (or stateless class) that takes a `ClaimGraph` and returns a list of `SectionPlan` objects.
1. **Cluster Detection:** Partition nodes into Entity Hubs and Conflict Hubs.
2. **Cluster Merging:** Merge hubs sharing >50% atoms into a single `Comparative` section.
3. **Mode Assignment:** Apply rules based on edge types within the cluster.
4. **Budgeting:** Compute word counts based on atom density.
5. **Sequencing:** Sort sections by importance (cluster size) or a fixed narrative template.

### Anti-Patterns to Avoid
- **LLM Refinement:** Do not call LLMs to "clean up" the deterministic plan; the plan must be 100% mechanical.
- **Node Mutation:** Do not mutate the original `ClaimGraph` during planning.
- **Unbounded Word Ranges:** Avoid `(0, inf)` ranges; use evidence count to bound the LLM writer.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Graph Traversal | Custom DFS/BFS | `NetworkX.neighbors` | Avoids bugs in relationship discovery. |
| Sorting | Custom sort logic | `sorted(key=...)` | Standard Pythonic way to ensure determinism. |
| UUIDs | Custom hashing | `uuid.uuid5` | Standard for deterministic namespace-based IDs. |
| Clustering | Complex ML clusters | Connected Components | Small N (10-100 atoms) makes rule-based grouping better. |

## Common Pitfalls

### Pitfall 1: The "Knowledge Sink"
**What goes wrong:** A single generic entity (e.g., "The Market") connects all atoms, leading to one giant section.
**How to avoid:** Limit cluster size (e.g., max 15 atoms). Split by secondary entities if limit is exceeded.

### Pitfall 2: Orphan Evidence
**What goes wrong:** Atoms that don't belong to any recognized entity cluster are skipped.
**How to avoid:** Implement an "Orphan Adoption" pass where orphans are added to a "General Findings" section or the most similar existing cluster.

### Pitfall 3: Determinism Drift
**What goes wrong:** Iterating over dictionaries or sets results in different section orders across runs.
**How to avoid:** All graph traversals and list constructions must be preceded by a `sorted()` call on global IDs or names.

## Code Examples

### Cluster Discovery and Mode Assignment
```python
# Source: Rule-based heuristic for 12-D
def plan_section(cluster_atoms: List[str], cluster_entities: List[str], graph: nx.DiGraph) -> SectionMode:
    # 1. Check for contradictions
    has_conflict = any(graph.has_edge(a, b) and graph[a][b]['type'] == 'contradicts' 
                       for a in cluster_atoms for b in cluster_atoms)
    if has_conflict:
        return SectionMode.ADJUDICATIVE
    
    # 2. Check for comparisons
    if len(cluster_entities) > 1:
        return SectionMode.COMPARATIVE
        
    return SectionMode.DESCRIPTIVE
```

### Deterministic Budgeting
```python
# Source: 12-D-CONTEXT.md logic
def calculate_budget(atoms_count: int, claims_count: int) -> Tuple[int, int]:
    base = 300
    total = base + (atoms_count * 100) + (claims_count * 150)
    return (total, int(total * 1.5))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LLM-based outline | Deterministic Graph-to-Plan | 12-D | Eliminated structure hallucinations; guaranteed evidence coverage. |
| Bag-of-atoms | Structured Evidence Clusters | 12-C/D | Enabled multi-entity comparative analysis. |

## Open Questions

1. **Section Order:** Should the most evidence-dense section always go first, or should we follow a fixed "Summary -> Analysis -> Conflicts" template?
   - Recommendation: Follow a fixed template for common section types, but sort entities by importance (atom count) within those blocks.
2. **Micro-Retrieval:** Does the planner need to trigger more searches if a cluster is thin?
   - Recommendation: Deferred to future. For now, use `refusal_required=True` to emit placeholders.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Pytest 7.4.3 |
| Config file | `pytest.ini` |
| Quick run command | `pytest tests/research/reasoning/test_section_planner.py` |
| Full suite command | `pytest tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| 12-D-01 | No LLM calls during planning | Unit | `pytest tests/research/reasoning/test_section_planner.py::test_no_llm_calls` | ❌ Wave 0 |
| 12-D-02 | Deterministic output for same graph | Unit | `pytest tests/research/reasoning/test_section_planner.py::test_determinism` | ❌ Wave 0 |
| 12-D-03 | Correct mode assignment | Unit | `pytest tests/research/reasoning/test_section_planner.py::test_mode_logic` | ❌ Wave 0 |
| 12-D-04 | Valid budget calculation | Unit | `pytest tests/research/reasoning/test_section_planner.py::test_budget_calc` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `tests/research/reasoning/test_section_planner.py` — core logic verification.
- [ ] Mock `ClaimGraph` fixtures for testing different topologies (comparative, conflicting).

## Sources

### Primary (HIGH confidence)
- `.planning/phases/12-D/12-D-CONTEXT.md` - Planner requirements and schema.
- `.planning/phases/12-C/12-C-RESEARCH_FULL.md` - Graph architecture and NetworkX usage.
- `src/research/reasoning/assembler.py` - Current planning logic and integration point.

### Metadata

**Confidence breakdown:**
- Standard stack: HIGH - NetworkX is the established tool in this repo.
- Architecture: HIGH - Deterministic planning is a locked decision.
- Pitfalls: MEDIUM - Scaling to extremely large evidence packets is unproven.

**Research date:** 2026-04-01
**Valid until:** 2026-05-01
