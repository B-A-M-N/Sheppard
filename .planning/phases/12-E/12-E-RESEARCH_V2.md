# Phase 12-E: Evidence-Aware Composition & Frontier Scope Fix - Research

**Researched:** 2026-04-01
**Domain:** LLM Synthesis Pipelines & Agentic Search Stopping Conditions
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Pipeline Architecture**: Must implement a 5-pass composition engine:
    1. **Pass 1: Section Packet Assembly**: Assemble `EvidencePacket` with derived claims and analytical bundles.
    2. **Pass 2: First-Pass Draft**: LLM generates prose from `SectionPlan` + `EvidencePacket`.
    3. **Pass 3: Expansion Pass**: Conditional pass based on evidence density for detail enrichment.
    4. **Pass 4: Transition Coherence Pass**: Smooths jarring topic shifts between sections.
    5. **Pass 5: Final Grounding/Repair Pass**: Re-validates every sentence against `SectionPlan` and grounding obligations.
- **Master Invariant**: The writer never invents intelligence; it renders intelligence already mechanically assembled upstream.

### the agent's Discretion
- Implementation details of the "Skeleton Claims" first-pass within the synthesis pipeline.
- Definition of "Saturation-driven corpus budget" and threshold values.
- Internal prompt engineering for Pass 3 (Expansion) and Pass 4 (Transitions).

### Deferred Ideas (OUT OF SCOPE)
- None specified in CONTEXT.md.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| COMP-01 | Upgrade synthesis to two-stage: skeleton claims first, then prose. | Supported by "Skeleton-of-Thought" (SoT) research. |
| COMP-02 | Replacement of `max_pages=100` with saturation budget. | Supported by "Epistemic Yield" monitoring research. |
| COMP-03 | Expansion pass conditional on evidence density. | Supported by `derived_claims` density metrics. |
| COMP-04 | Transition coherence across sections. | Supported by "Cross-Section Context" injection. |
</phase_requirements>

## Summary

Phase 12-E moves the synthesis engine from a single-pass "one-shot" generation to a high-fidelity 5-pass pipeline. The core technical shift is the adoption of a **Skeleton-of-Thought (SoT)** pattern, where the model commits to a structured list of claims before generating prose. This prevents "drift" and ensures every sentence is grounded in the upstream `EvidencePacket`. 

Additionally, the research frontier is upgraded with a **Saturation-Driven Stopping Condition**. Instead of a hardcoded `max_pages=100` limit, the mission terminates when the **Epistemic Yield** (new unique atoms found per source) drops below a critical threshold, ensuring exhaustive coverage for obscure topics while preventing waste on well-documented ones.

**Primary recommendation:** Implement `MultiPassSynthesisService` in `synthesis_service_v2.py` utilizing the V3 Triad (Postgres for canonical truth, Chroma for retrieval) and integrate a `SaturationMonitor` into the `BudgetMonitor` to drive frontier termination.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `Ollama` | latest | LLM Inference | Standard for local, high-fidelity research models (Llama 3, Mistral). |
| `PostgreSQL` | 15+ | Canonical Truth Store | Source of truth for atoms, claims, and artifacts (V3 Triad). |
| `ChromaDB` | latest | Semantic Retrieval | Enables dense retrieval of contextually relevant atoms. |
| `Asyncio` | std | Concurrency | Handles parallel pass processing and bounded worker pools. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| `pydantic` | v2 | Data Validation | Enforcing structure on `SectionPlan` and `Skeleton`. |
| `re` | std | Citation Extraction | Validating [A1], [S2] tags in final grounding pass. |

## Architecture Patterns

### Recommended Project Structure
```
src/research/
├── reasoning/
│   ├── synthesis_service_v2.py    # MultiPassSynthesisService
│   ├── archivist_v2.py            # Expanded prompts for SoT, Expansion, Transition
│   └── saturation.py              # Saturation-driven budget logic
└── acquisition/
    └── budget.py                  # Upgraded to track Epistemic Yield
```

### Pattern 1: Skeleton-to-Prose (Pass 2 & 3)
**What:** The synthesis engine first generates a "Skeleton" of concise, grounded claims, then expands them into prose.
**When to use:** Every section generation in the 12-E pipeline.
**Example:**
```python
# Pass 2: Skeleton Generation
skeleton = await llm.complete(
    task=TaskType.DECOMPOSITION,
    prompt=f"Generate 5-8 concise claims for {section.title} using ONLY atoms: {packet.atoms}"
)

# Pass 3: Prose Generation from Skeleton
prose = await llm.complete(
    task=TaskType.SYNTHESIS,
    prompt=f"Expand these claims into prose: {skeleton}. Cite every fact using [Global ID]."
)
```

### Pattern 2: Saturation-Driven Stopping
**What:** Mission expansion terminates when `New Atoms / Sources Crawled` < Threshold over a sliding window.
**When to use:** Integrated into the `Frontier.run()` loop.
**Formula:** `Yield(W) = Count(Atoms created in window W) / Count(Sources in window W)`. Stop if `Yield(W) < 0.2` (1 atom per 5 sources).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Claim Derivation | Custom logic | `DerivationEngine` | Already exists in Phase 12-A; provides numeric deltas/ranks. |
| JSON Repair | Custom regex | `repair_json` | LLMs frequently break JSON; existing utility is robust. |
| Vector Search | Manual scoring | `ChromaDB` | Standardized semantic retrieval in V3. |

## Common Pitfalls

### Pitfall 1: Citation "Drift" in Expansion
**What goes wrong:** During Pass 3 (Expansion), the LLM adds stylistic detail that isn't backed by an atom but keeps the citation at the end of the paragraph.
**How to avoid:** Pass 5 (Grounding) must split text into sentences and verify that *every* sentence contains a valid citation tag found in the `EvidencePacket`.

### Pitfall 2: Infinite Crawl on General Topics
**What goes wrong:** High-yield topics (e.g., "Artificial Intelligence") may never reach saturation if the threshold is too low.
**How to avoid:** Implement a "Soft Ceiling" in `SaturationMonitor` that tightens the threshold as total ingested bytes increase.

### Pitfall 3: Broken Transitions
**What goes wrong:** Pass 4 (Transitions) might change the meaning of a grounded sentence to make it "flow" better.
**How to avoid:** The Final Grounding Pass (Pass 5) must run *after* transitions to ensure truth preservation.

## Code Examples

### Saturation Monitoring Logic
```python
class SaturationMonitor:
    def __init__(self, threshold=0.2, window_size=20):
        self.threshold = threshold
        self.window_size = window_size
        self.history = [] # List of (sources_processed, atoms_found)

    def is_saturated(self, mission_id: str) -> bool:
        if len(self.history) < self.window_size: return False
        
        recent = self.history[-self.window_size:]
        total_sources = sum(s for s, a in recent)
        total_atoms = sum(a for s, a in recent)
        
        yield_rate = total_atoms / total_sources
        return yield_rate < self.threshold
```

### Expansion Threshold Logic
```python
def should_expand(packet: EvidencePacket) -> bool:
    # Trigger expansion if we have high-density derived structure
    # or a high number of unique supporting atoms.
    return len(packet.derived_claims) > 3 or len(packet.atoms) > 10
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-Pass Synth | Skeleton-of-Thought (SoT) | Phase 12-E | Higher coherence, reduced drift. |
| Fixed Page Limit | Saturation Budget | Phase 12-E | Efficiency; better depth for niche topics. |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.x |
| Config file | `pytest.ini` |
| Quick run command | `pytest tests/research/reasoning/test_composition_pipeline.py -x` |
| Full suite command | `pytest tests/ -m "composition"` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COMP-01 | Two-stage synthesis produces skeleton then prose. | integration | `pytest tests/.../test_pipeline.py::test_soat_flow` | ❌ Wave 0 |
| COMP-02 | Frontier stops when yield rate < threshold. | unit | `pytest tests/.../test_saturation.py` | ❌ Wave 0 |
| COMP-03 | Expansion pass only triggers on high-density packets. | unit | `pytest tests/.../test_expansion.py` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `tests/research/reasoning/test_composition_pipeline.py` — Covers E2E 5-pass flow.
- [ ] `tests/research/acquisition/test_saturation_monitor.py` — Covers stopping logic.

## Sources

### Primary (HIGH confidence)
- `12-E-CONTEXT.md` - Definition of the 5-pass architecture.
- `synthesis_service.py` - Current V1 implementation reference.
- `frontier.py` - Current frontier/stopping logic reference.
- `derivation/engine.py` - Source for grounded numeric claims.

### Secondary (MEDIUM confidence)
- "Skeleton-of-Thought: Large Language Models Can Do Parallel Decoding" (ArXiv 2023).
- "Data Saturation in Qualitative Research" - Conceptual basis for the stopping condition.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Aligned with existing V3 architecture.
- Architecture: HIGH - 5-pass pipeline is explicitly defined in CONTEXT.md.
- Pitfalls: MEDIUM - Based on common LLM grounding challenges.

**Research date:** 2026-04-01
**Valid until:** 2026-05-01
