---
phase: 12-E
plan: 01
type: tdd
depends_on:
  - 12-D  # EnrichedSectionPlan
  - 12-C  # EvidenceGraph
  - 12-B  # AnalyticalBundle
  - 12-A  # DerivedClaim
files_modified:
  - src/research/reasoning/synthesis_service_v2.py
  - tests/research/reasoning/test_composition_pipeline.py
autonomous: true
---

<objective>
Build MultiPassSynthesisService — a 5-pass composition pipeline that transforms
structured EvidencePackets + EnrichedSectionPlans into coherent long-form prose.
Keeps v1 synthesis_service.py untouched for backward compatibility.

Output:
- src/research/reasoning/synthesis_service_v2.py
- tests/research/reasoning/test_composition_pipeline.py
</objective>

<interfaces>
**Input to pipeline:**
  - EnrichedSectionPlan (from 12-D)
  - EvidencePacket (atoms, derived_claims, analytical_bundles, evidence_graph)
  - OllamaClient (LLM, mocked in tests)

**Output:**
  @dataclass
  class SectionDraft:
      section_title: str
      text: str
      pass_log: List[str]          # which passes ran
      was_expanded: bool
      grounding_report: Dict       # from 12-F verifier (or empty dict pre-12-F)

  @dataclass
  class ReportDraft:
      sections: List[SectionDraft]
      topic_name: str
      total_passes: int
      quality_metrics: Dict

**Existing synthesis_service.py:**
  - DO NOT modify. synthesis_service_v2.py is standalone.

**OllamaClient interface (from src/llm/client.py):**
  - await client.complete(task: TaskType, prompt: str, system_prompt: Optional[str]) → str
  - Use TaskType.SYNTHESIS for all passes (temperature=0.0, seed=12345 → deterministic)

**Entry points:**
  - compose_section(plan, packet, previous_text=None) → SectionDraft
      previous_text: text of previously drafted section for Pass 3 transitions
  - compose_report(plans, packet, topic_name) → ReportDraft
      Iterates sections, passes previous_text sequentially

**quality_metrics keys:**
  {"total_words": int, "expanded_sections": int, "total_sections": int, "avg_pass_count": float}
</interfaces>

<feature>
  <name>MultiPassSynthesisService</name>
  <files>
    src/research/reasoning/synthesis_service_v2.py
    tests/research/reasoning/test_composition_pipeline.py
  </files>

  <pipeline>
    Pass 1: First-pass draft
      - Build prompt from SectionPlan.required_atom_ids + SectionPlan.mode
      - Constrain: "cite only: {required_atom_ids}; derived: {allowed_derived_claim_ids}"
      - Call LLM → raw draft text
      - Log: pass_log.append("pass1_draft")

    Pass 2: Expansion (conditional)
      - EXPANSION_THRESHOLD = 3 (min atoms in section to trigger expansion)
      - ONLY run if len(plan.required_atom_ids) >= EXPANSION_THRESHOLD
      - Prompt: "Expand the following section using only the cited evidence..."
      - Forbidden: introduce claims not in allowed_derived_claim_ids or required_atom_ids
      - Log: pass_log.append("pass2_expanded") if ran, else pass_log.append("pass2_skipped")

    Pass 3: Transition coherence
      - Takes previous_text: Optional[str] (text of prior section, or None for first section)
      - If previous_text is not None: prompt LLM to prepend 1-2 sentence transition
      - No new facts introduced
      - Log: pass_log.append("pass3_transitions")

    Pass 4: Grounding repair
      - Check for any sentence containing comparative/analytical language without [citations]
      - Prompt: "Remove or cite any unsupported comparative claims in: {text}"
      - Log: pass_log.append("pass4_repair")

    Pass 5 (placeholder — full implementation in 12-F):
      - Reserved for LongformVerifier integration
      - Currently: no-op, appends "pass5_pending" to log
  </pipeline>

  <behavior>
    RED: 8 tests:
    1. test_pipeline_produces_section_draft
    2. test_pass_log_records_all_passes
    3. test_expansion_skipped_below_threshold
    4. test_expansion_runs_above_threshold
    5. test_refusal_section_skips_passes_if_refusal_required
    6. test_report_draft_contains_all_sections
    7. test_pipeline_calls_llm_for_each_pass
    8. test_section_draft_has_was_expanded_flag

    GREEN: implement MultiPassSynthesisService
    REFACTOR: extract prompt builders to private methods
  </behavior>
</feature>

<implementation>
  RED → GREEN → REFACTOR.

  Tests mock OllamaClient: AsyncMock returning deterministic strings.
  Pipeline is async (await LLM calls).
  Pass 5 is a no-op stub (reserved for 12-F integration).
  EXPANSION_THRESHOLD = 3 atoms (configurable).
  If plan.refusal_required=True: emit placeholder text, skip all LLM passes.
</implementation>

<verification>
  <automated>PYTHONPATH=src python -m pytest tests/research/reasoning/test_composition_pipeline.py -v</automated>
  <automated>PYTHONPATH=src python -m pytest tests/research/ -x -q</automated>
</verification>

<success_criteria>
- 8 tests pass
- SectionDraft and ReportDraft dataclasses exist with correct fields
- EXPANSION_THRESHOLD respected
- Refusal sections emit placeholder without LLM call
- No changes to synthesis_service.py
- No regressions
</success_criteria>
