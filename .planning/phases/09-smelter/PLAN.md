---
phase: 09-smelter
plan: 01
type: audit
wave: 1
depends_on:
  - phase08_scraping
files_modified:
  - src/research/smelter/* (inspection only — no modifications)
autonomous: false
requirements:
  - V3-ATOM-SCHEMA
  - EVIDENCE-BINDING
  - JSON-REPAIR-SAFETY
must_haves:
  truths:
    - "Atoms are standalone records with explicit schema (no implicit fields)"
    - "Evidence binding is explicit (source_chunk_id or provenance fields mandatory)"
    - "Atom types are consistent (fact/claim/tradeoff/etc) and enforced by validator"
    - "JSON repair logic cannot mutate semantic meaning (only structural fixes)"
    - "Deduplication is deterministic (same atom content → same atom ID)"
    - "Invalid extraction outputs are rejected (logging + backpressure), not silently stored"
  artifacts:
    - path: "src/research/smelter/"
      provides: "Extraction pipeline, prompts, parsers, validators, storage handoff"
      contains: "extract_atoms, Atom dataclass, validation rules"
    - path: "src/research/smelter/prompts/"
      provides: "Distillation prompts that shape model output"
      contains: "atom_extraction"
    - path: "tests/test_atom_schema.py (if exists)"
      provides: "Schema validation tests"
      contains: "AtomValidator"
  key_links:
    - from: "src/research/smelter/extractor.py"
      to: "src/research/critic/llm_interface.py"
      via: "LLM call with atom extraction prompt"
      pattern: "extract_atoms"
    - from: "src/research/smelter/validator.py"
      to: "src/research/smelter/atom.py"
      via: "schema.validate(atom_dict)"
      pattern: "required.*fields"
    - from: "src/research/index/writer.py"
      to: "chroma_store.add"
      via: "atom write path"
      pattern: "add_atoms"
---

<objective>
Audit the smelter's atom extraction path to verify: schema correctness, parsing robustness, evidence integrity, dedupe determinism, and safe JSON repair.

Purpose: Ensure the atom layer is production-ready — bounded, typed, evidence-backed, and resilient to malformed LLM output.

Scope: Inspection only — do not modify code. Produce audit documents reporting findings and hard-fail conditions if any.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/gauntlet_phases/phase09_smelter/PHASE-09-PLAN.md
@src/research/smelter/
@src/research/critic/
@src/research/index/
</context>

<tasks>

<task type="auto">
  <name>Task 1: Identify and document the atom schema</name>
  <files>
    - src/research/smelter/atom.py (or equivalent)
    - src/research/smelter/validator.py
    - any schema definitions (pydantic, dataclass, jsonschema)
  </files>
  <read_first>
    - All files defining atom structure
  </read_first>
  <behavior>
    - Extract the full schema: required fields, types, constraints
    - Determine if evidence linkage (source_chunk_id, document_id, confidence) is mandatory or optional
    - Identify atom types/classifications (fact, claim, tradeoff, etc.) and how they're enforced
    - Document any schema evolution or versioning
  </behavior>
  <action>
Create `ATOM_SCHEMA_AUDIT.md` in the phase directory with:
- Schema definition (full fields table: field, type, required, description)
- Evidence binding requirements
- Type system (enum of allowed types, if any)
- Validation rules (what causes rejection)
- Missing or ambiguous aspects
  </action>
  <verify>
    <automated>test -f .planning/phases/09-smelter/ATOM_SCHEMA_AUDIT.md && grep -q "required" .planning/phases/09-smelter/ATOM_SCHEMA_AUDIT.md</automated>
  </verify>
  <acceptance_criteria>
    - ATOM_SCHEMA_AUDIT.md exists with complete fields table
    - Schema audit clearly states whether evidence is mandatory
    - Atom types are documented and their enforcement mechanism is described
  </acceptance_criteria>
  <done>
    Atom schema documented with fields, types, evidence requirements, and type system.
  </done>
</task>

<task type="auto">
  <name>Task 2: Verify extraction prompts, parsers, and pipeline</name>
  <files>
    - src/research/smelter/prompts/atom_extraction prompt file(s)
    - src/research/smelter/extractor.py (or equivalent)
    - src/research/smelter/parser.py (JSON parsing, repair logic)
  </files>
  <read_first>
    - Extraction prompt content
    - Parser code that transforms LLM output to atoms
  </read_first>
  <behavior>
    - Read the exact prompt sent to the model — does it instruct structured output? Examples?
    - Identify parser: how is raw LLM response turned into Python objects? (json.loads, custom parser, etc.)
    - Locate malformed JSON handling: try/except, repair attempts (json_repair, manual fixes)
    - Determine if repair logic could mutate meaning (e.g., dropping fields, rewrites)
  </behavior>
  <action>
Create `EXTRACTION_PIPELINE_REPORT.md` with:
- Prompt excerpts or summary (what the model is told to produce)
- Parser algorithm (step-by-step from raw response to atom dict)
- JSON repair strategy (when invoked, what transformations applied)
- Risks: where could malformed output cause incorrect atoms?
  </action>
  <verify>
    <automated>test -f .planning/phases/09-smelter/EXTRACTION_PIPELINE_REPORT.md && grep -q "repair" .planning/phases/09-smelter/EXTRACTION_PIPELINE_REPORT.md</automated>
  </verify>
  <acceptance_criteria>
    - EXTRACTION_PIPELINE_REPORT.md exists
    - Prompt strategy described
    - Parser flow documented
    - JSON repair logic identified and assessed for semantic safety
  </acceptance_criteria>
  <done>
    Extraction pipeline documented with prompt, parser, and repair mechanics.
  </done>
</task>

<task type="auto">
  <name>Task 3: Verify deduplication and idempotency logic</name>
  <files>
    - src/research/smelter/dedupe.py (or equivalent)
    - src/research/index/writer.py (storage handoff)
  </files>
  <read_first>
    - Dedupe code: how are duplicate atoms detected and suppressed?
    - Atom ID generation: deterministic or random?
  </read_first>
  <behavior>
    - Find where dedupe happens: before validation, after validation, at storage?
    - Identify the dedupe key: full content hash? (atom content + evidence)? What hash algo?
    - Check if same content always produces same atom_id (determinism)
    - Note if dedupe affects throughput or introduces non-determinism under race conditions
  </behavior>
  <action>
Create `DEDUPE_AUDIT.md` (or include in EXTRACTION_PIPELINE_REPORT.md) documenting:
- Dedupe mechanism (hash-based, ID-based, content-based)
- Determinism assessment (same input → same atom_id always?)
- Where dedupe occurs in the pipeline
- Edge cases: near-dupes, different ordering, evidence variations
  </action>
  <verify>
    <automated>test -f .planning/phases/09-smelter/DEDUPE_AUDIT.md || grep -qi "dedup" .planning/phases/09-smelter/EXTRACTION_PIPELINE_REPORT.md</automated>
  </verify>
  <acceptance_criteria>
    - Deduplication behavior documented
    - Determinism assessment provided (PASS or concerns noted)
  </acceptance_criteria>
  <done>
    Deduplication logic documented with determinism evaluation.
  </done>
</task>

<task type="auto">
  <name>Task 4: Verify atom typing and evidence binding</name>
  <files>
    - src/research/smelter/atom.py (type definitions)
    - src/research/smelter/validator.py (type enforcement)
    - src/research/index/writer.py (storage, evidence linkage)
  </files>
  <read_first>
    - How atom types are assigned (from model? post-hoc classification?)
    - Whether evidence (source chunk, doc id, line numbers) is required and stored
    - How evidence links back to original source material
  </read_first>
  <behavior>
    - Check if atoms have a `type` field with allowed values; who enforces it?
    - Confirm that every atom stores explicit evidence pointers (not just implied)
    - Determine if evidence can be missing, and what happens if it is
  </behavior>
  <action>
Add to `ATOM_SCHEMA_AUDIT.md` sections:
- Atom type system: allowed types, assignment mechanism, enforcement
- Evidence binding: required fields, storage format, retrieval path
- Gaps: where evidence could be lost or become disconnected
  </action>
  <verify>
    <automated>grep -qi "evidence" .planning/phases/09-smelter/ATOM_SCHEMA_AUDIT.md && grep -qi "type" .planning/phases/09-smelter/ATOM_SCHEMA_AUDIT.md</automated>
  </verify>
  <acceptance_criteria>
    - Type system documented with enforcement
    - Evidence binding requirements explicit
    - Gaps or weaknesses highlighted
  </acceptance_criteria>
  <done>
    Typing and evidence binding documented with clarity on mandates and gaps.
  </done>
</task>

<task type="auto">
  <name>Task 5: Verify invalid extraction rejection criteria and handling</name>
  <files>
    - src/research/smelter/validator.py
    - src/research/smelter/extractor.py (failure paths)
    - logging configuration for extraction failures
  </files>
  <read_first>
    - What makes an atom invalid? (missing required fields, type mismatch, evidence null)
    - What happens when invalid extraction output is encountered? (reject, fallback, store anyway?)
    - How are failures logged and monitored? (metrics, alerts)
  </read_first>
  <behavior>
    - Identify rejection criteria at validation time
    - Trace failure handling: does invalid output get discarded? Does it trigger retries or backpressure?
    - Check for silent acceptance (soft validation) vs hard rejection
  </behavior>
  <action>
Create `ATOM_VALIDATION_AND_REJECTION_RULES.md` containing:
- List of rejection conditions (schema violation, type unknown, evidence missing, repair failure)
- Action taken on rejection (discard, alert, retry, quarantine)
- Observability: logs, metrics, alarms
- Hard fail determination: any condition that would allow invalid atoms to be stored?
  </action>
  <verify>
    <automated>test -f .planning/phases/09-smelter/ATOM_VALIDATION_AND_REJECTION_RULES.md && grep -qi "reject" .planning/phases/09-smelter/ATOM_VALIDATION_AND_REJECTION_RULES.md</automated>
  </verify>
  <acceptance_criteria>
    - Rejection rules clearly enumerated
    - Handling strategy for invalid output documented
    - Any soft spots (where invalid atoms could slip through) are called out
  </acceptance_criteria>
  <done>
    Validation and rejection rules documented with failure-mode analysis.
  </done>
</task>

<task type="auto">
  <name>Task 6: Produce PHASE-09-VERIFICATION.md with pass/fail assessment</name>
  <files>
    - All previously created audit documents
  </files>
  <read_first>
    - Consolidate findings from Tasks 1-5
  </read_first>
  <behavior>
    - Evaluate each must_have truth:
      * Atoms standalone? (no implicit fields, self-contained)
      * Evidence binding mandatory?
      * Type system consistent and enforced?
      * JSON repair semantic-safe?
      * Dedupe deterministic?
      * Invalid outputs rejected?
    - Set overall VERDICT: PASS, PARTIAL, or FAIL
    - Document schema violations or weaknesses (if any)
  </behavior>
  <action>
Create `PHASE-09-VERIFICATION.md` using the template from gauntlet plan, with:
- Checklist status for each quality criterion
- Evidence references (which audit files support each check)
- Verdict and rationale
- Schema violations or gaps (if PARTIAL/FAIL)
  </action>
  <verify>
    <automated>test -f .planning/phases/09-smelter/PHASE-09-VERIFICATION.md && grep -q "Status:" .planning/phases/09-smelter/PHASE-09-VERIFICATION.md</automated>
  </verify>
  <acceptance_criteria>
    - PHASE-09-VERIFICATION.md exists with VERDICT and checklist
    - All must_haves evaluated
    - Evidence traces to audit documents
  </acceptance_criteria>
  <done>
    Phase verification complete; audit package ready for review.
  </done>
</task>

</tasks>

<verification>
Audit completeness: All six tasks produce documented artifacts that collectively assess:
- Atom schema strictness
- Extraction pipeline integrity
- Dedupe determinism
- Evidence backing
- Validation rigor

No code changes, only inspection and reporting.

Hard fails if:
- Schema is soft or evidence optional
- JSON repair can alter meaning
- Invalid atoms can be stored

PASS only when atom layer is provably bounded and evidence-backed.
</verification>

<success_criteria>
- ATOM_SCHEMA_AUDIT.md exists and defines fields/evidence/types
- EXTRACTION_PIPELINE_REPORT.md exists and covers prompts/parser/repair
- Deduplication behavior documented (somewhere)
- Atom typing and evidence binding documented
- ATOM_VALIDATION_AND_REJECTION_RULES.md exists
- PHASE-09-VERIFICATION.md exists with PASS/PARTIAL/FAIL and checklist
- All acceptance criteria per task met
</success_criteria>

<output>
After completion, ensure deliverables exist in:
- .planning/phases/09-smelter/
- Also optionally mirror to .planning/gauntlet_phases/phase09_smelter/ for consistency
</output>
