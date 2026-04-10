# Phase 12-E — Context: Multi-Stage Composition Engine

## Position in Stack

**12-E = Composition** — transform structured packets into long, coherent, high-detail output.

Controlled pipeline: packet assembly → first-pass draft → expansion pass → transition coherence → final grounding. Length is earned, not padded — expansion only occurs when evidence density, contradiction state, and derived structure support it.

**Master Invariant:** The writer never invents intelligence; it renders intelligence already mechanically assembled upstream.

---

## Current State

**Existing synthesis** (`synthesis_service.py`, `synth_adapter.py`): single-pass LLM call per section. Writer receives EvidencePacket (atoms + derived claims) and generates prose in one shot. No planning, no expansion control, no multi-pass refinement.

**Gap:** One-pass writing produces "good enough" output but lacks Gemini-class depth, length, and coherence. The writer is too close to raw retrieval and doesn't benefit from intermediate structuring.

---

## What 12-E Must Build

### Pipeline Architecture

**Pass 1: Section Packet Assembly** (uses output from 12-A through 12-D)
- Already exists: `EvidencePacket` + derived claims + analytical bundles + claim graph
- SectionPlanner produces `SectionPlan` with budgets, modes, contradictions
- Output: richly structured per-section material

**Pass 2: First-Pass Draft**
- LLM generates prose from SectionPlan + EvidencePacket
- Strict constraints: can only reference allowed derived claims and required atoms
- Output: complete rough draft of each section

**Pass 3: Expansion Pass** (conditional)
- ONLY runs if evidence density meets threshold
- Identifies sections with sufficient derived structure to support elaboration
- Expands key claims with supporting evidence, examples, implications
- Forbidden: introduce new claims not supported by existing atoms/derived structure
- Output: enriched section text with more detail and transitions

**Pass 4: Transition Coherence Pass**
- Ensures smooth transitions between sections
- Cross-references entities mentioned in adjacent sections
- Eliminates jarring topic shifts
- Output: cohesive full report draft

**Pass 5: Final Grounding/Repair Pass**
- Re-validate every sentence against SectionPlan obligations
- Check contradiction obligations satisfied (section addressed conflict if required)
- Remove unsupported elaboration from Pass 3 that may have drifted
- Output: verified final report text

### Files That Will Change

| File | Change |
|------|--------|
| `src/research/reasoning/synthesis_service_v2.py` | NEW — MultiPassSynthesisService with 5-pipeline |
| `src/research/reasoning/synthesis_service.py` | Keep v1 for backward compatibility; new code goes to v2 |
| `src/research/archivist/synth_adapter.py` | Add multi-prompt handling (first-pass, expansion, repair) |
| `tests/research/reasoning/test_composition_pipeline.py` | NEW — multi-pass tests |
| `.planning/phases/12-E/COMPOSITION_PIPELINE_SPEC.md` | NEW — spec |
| `.planning/phases/12-E/EXPANSION_POLICY.md` | NEW — expansion rules, thresholds |
