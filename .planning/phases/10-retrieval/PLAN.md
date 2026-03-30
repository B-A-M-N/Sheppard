---
phase: 10-retrieval
plan: 01
type: audit
wave: 1
depends_on:
  - phase09_smelter
files_modified:
  - src/research/reasoning/ (inspection only)
  - src/core/commands.py (interactive query entrypoint)
autonomous: false
requirements:
  - RETRIEVAL-GROUNDING
  - PROVENANCE
  - CONCURRENT-RESEARCH
must_haves:
  truths:
    - "Interactive queries are answered from stored atoms, not just base model priors"
    - "Retrieval uses atoms (knowledge_atoms collection) as primary source"
    - "Responses include citations/provenance (atom_id or source_id)"
    - "When memory insufficient, fallback behavior is explicit (e.g., 'I don't know')"
    - "Live background research can continue while user queries are answered"
  artifacts:
    - path: "src/core/commands.py"
      provides: "Chat/query command handler"
      contains: "handle_chat_message or query entrypoint"
    - path: "src/research/reasoning/"
      provides: "Retrieval logic over Chroma/Postgres"
      contains: "retriever, v3_retriever, assembler"
    - path: "src/research/reasoning/synthesis_service.py"
      provides: "Response synthesis with context"
      contains: "write_section or answer generation"
  key_links:
    - from: "src/core/commands.py"
      to: "src/research/reasoning/assembler.py"
      via: "calls to retrieve and synthesize answer"
      pattern: "assemble_answer|retrieve_context"
    - from: "src/research/reasoning/v3_retriever.py"
      to: "chroma_store.query"
      via: "semantic search over knowledge_atoms"
      pattern: "query.*knowledge_atoms"
    - from: "src/research/reasoning/synthesis_service.py"
      to: "llm_client.chat"
      via: "context injection into prompt"
      pattern: "system.*user.*assistant"
---

<objective>
Audit the interactive query path to verify that answers are grounded in stored atoms, that provenance is available, and that live background research continues concurrently.

Scope: Inspection only. Produce audit reports.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/gauntlet_phases/phase10_retrieval/PHASE-10-PLAN.md
@src/core/commands.py
@src/research/reasoning/
@src/research/condensation/pipeline.py (status signaling)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Identify interactive query entrypoint and flow</name>
  <files>
    - src/core/commands.py
    - any chat/query handlers
  </files>
  <read_first>
    - Command handler that receives user messages
    - How it determines whether to answer from memory vs. trigger research
  </read_first>
  <behavior>
    - Trace from user input to final response.
    - Identify retrieval calls: which retriever, which collection (knowledge_atoms?), what top_k.
    - Identify whether retrieval is optional or mandatory for chat responses.
  </behavior>
  <action>
Create `QUERY_PATH_AUDIT.md` documenting:
- Entrypoint function (file, line, function name)
- Step-by-step flow: receive message → retrieval → synthesis → response
- Retrieval configuration (collection, filters, top_k)
- Any branching (e.g., if no retrieval results)
</action>
  <verify>
    <automated>test -f .planning/phases/10-retrieval/QUERY_PATH_AUDIT.md && grep -q "entrypoint" .planning/phases/10-retrieval/QUERY_PATH_AUDIT.md</automated>
  </verify>
  <acceptance_criteria>
    - QUERY_PATH_AUDIT.md exists with clear flow description
    - Retrieval usage is explicit (does chat call retriever?)
  </acceptance_criteria>
  <done>
    Query path traced and documented.
  </done>
</task>

<task type="auto">
  <name>Task 2: Verify retrieval grounding — does response use atoms?</name>
  <files>
    - src/research/reasoning/v3_retriever.py
    - src/research/reasoning/assembler.py
    - src/research/reasoning/synthesis_service.py
  </files>
  <read_first>
    - Retriever implementation: does it query Chroma's knowledge_atoms collection?
    - Assembler: how retrieved atoms are formatted into context
    - Synthesis: how LLM is prompted to use the context
  </read_first>
  <behavior>
    - Determine if retrieval pulls from atoms (vs. raw corpus chunks).
    - Check if retrieved items include provenance (atom_id, source_id).
    - Verify that the synthesis prompt instructs the model to ground in provided context.
  </behavior>
  <action>
Create `RETRIEVAL_GROUNDING_REPORT.md` with:
- Retriever target collection and query parameters
- Evidence that retrieved items are atoms (not raw chunks)
- Whether synthesis enforces grounding (e.g., "answer using context" instruction)
- Observed risk: can LLM ignore context and answer from priors?
</action>
  <verify>
    <automated>test -f .planning/phases/10-retrieval/RETRIEVAL_GROUNDING_REPORT.md && grep -qi "atoms" .planning/phases/10-retrieval/RETRIEVAL_GROUNDING_REPORT.md</automated>
  </verify>
  <acceptance_criteria>
    - Report exists
    - Clarifies whether chat answers are atom-grounded or model-native
  </acceptance_criteria>
  <done>
    Retrieval grounding assessed and documented.
  </done>
</task>

<task type="auto">
  <name>Task 3: Verify provenance/citations in responses</name>
  <files>
    - src/research/reasoning/synthesis_service.py
    - response formatting/templates
  </files>
  <read_first>
    - Does the response include citations (e.g., atom_id, source reference)?
    - Are citations injected by synthesis or left to model discretion?
  </read_first>
  <behavior>
    - Look for explicit citation formatting in the synthesis output.
    - Determine if atom metadata (e.g., atom_id, source_url) is preserved and presented.
  </behavior>
  <action>
Add to `RETRIEVAL_GROUNDING_REPORT.md` or create `PROVENANCE_AUDIT.md` covering:
- Citation mechanism (inline markers, footnotes, references)
- Whether citations are mandatory or optional
- If missing, is that a failure condition?
</action>
  <verify>
    <automated>grep -qi "provenance\|citation\|source.*ref" .planning/phases/10-retrieval/*.md</automated>
  </verify>
  <acceptance_criteria>
    - Provenance handling documented
    - Clarity on whether user sees source attribution
  </acceptance_criteria>
  <done>
    Provenance in responses documented.
  </done>
</task>

<task type="auto">
  <name>Task 4: Verify fallback behavior when memory lacks coverage</name>
  <files>
    - src/core/commands.py
    - retrieval/assembler logic
  </files>
  <read_first>
    - What happens if retrieval returns zero atoms?
    - Does the system say "I don't know" or make up an answer from base model?
  </read_first>
  <behavior>
    - Identify fallback path: no-retrieval response, generic answer, or explicit acknowledge lack of knowledge.
    - Check if fallback is configurable or hard-coded.
  </behavior>
  <action>
Create `FALLBACK_BEHAVIOR_AUDIT.md` (or add to existing) describing:
- Zero-retrieval response strategy
- Whether the LLM is allowed to answer from its own training
- Any prompts that restrict model to provided context only
</action>
  <verify>
    <automated>test -f .planning/phases/10-retrieval/FALLBACK_BEHAVIOR_AUDIT.md && grep -qi "fallback\|no.*retriev\|don't know" .planning/phases/10-retrieval/FALLBACK_BEHAVIOR_AUDIT.md</automated>
  </verify>
  <acceptance_criteria>
    - Fallback behavior clearly documented
    - Assessment: does fallback avoid hallucination?
  </acceptance_criteria>
  <done>
    Fallback behavior documented.
  </done>
</task>

<task type="auto">
  <name>Task 5: Verify concurrent research and query</name>
  <files>
    - src/research/condensation/pipeline.py (background processing)
    - src/core/commands.py (does query block research?)
  </files>
  <read_first>
    - Are research (smelting) and query handling on independent paths?
    - Does a long-running query affect background ingestion?
  </read_first>
  <behavior>
    - Check for locks, queues, or separation of concerns.
    - Determine if queries read from a consistent snapshot while writes continue.
  </behavior>
  <action>
Create `LIVE_RESEARCH_INTERACTION_REPORT.md` covering:
- Architecture: separate processes/threads for research vs. query?
- Data consistency: can queries see partially-updated state?
- Throughput considerations (any queues or blocking?)
</action>
  <verify>
    <automated>test -f .planning/phases/10-retrieval/LIVE_RESEARCH_INTERACTION_REPORT.md && grep -qi "concurrent\|async\|background" .planning/phases/10-retrieval/LIVE_RESEARCH_INTERACTION_REPORT.md</automated>
  </verify>
  <acceptance_criteria>
    - Report exists
    - Clarifies whether query and research proceed independently
  </acceptance_criteria>
  <done>
    Concurrent research/query interaction documented.
  </done>
</task>

<task type="auto">
  <name>Task 6: Produce PHASE-10-VERIFICATION.md with PASS/PARTIAL/FAIL</name>
  <files>
    - All previous audit reports
  </files>
  <read_first>
    - Consolidate findings from Tasks 1-5
  </read_first>
  <behavior>
    - Evaluate each must_have truth:
      * Interactive answers grounded in atoms?
      * Retrieval uses atoms?
      * Citations present?
      * Fallback explicit?
      * Concurrent research verified?
    - Set VERDICT: PASS, PARTIAL, or FAIL
    - Document grounding gaps if any
  </behavior>
  <action>
Create `PHASE-10-VERIFICATION.md` using template, with checklist, evidence refs, verdict, and gaps.
</action>
  <verify>
    <automated>test -f .planning/phases/10-retrieval/PHASE-10-VERIFICATION.md && grep -q "Status:" .planning/phases/10-retrieval/PHASE-10-VERIFICATION.md</automated>
  </verify>
  <acceptance_criteria>
    - PHASE-10-VERIFICATION.md exists with clear VERDICT
    - All must_haves evaluated
  </acceptance_criteria>
  <done>
    Phase 10 verification complete.
  </done>
</task>

</tasks>

<verification>
Audit scope: retrieval grounding, provenance, fallback, concurrency. No code changes; reporting only.

Hard fails:
- Answers not grounded in atoms
- Retrieval not wired into synthesis
- System pretends certainty when memory insufficient

PASS only if interactive answering is demonstrably memory-backed with provenance.
</verification>

<success_criteria>
- QUERY_PATH_AUDIT.md exists
- RETRIEVAL_GROUNDING_REPORT.md exists
- Provenance/citations documented (somehow)
- Fallback behavior documented
- LIVE_RESEARCH_INTERACTION_REPORT.md exists
- PHASE-10-VERIFICATION.md exists with PASS/PARTIAL/FAIL
</success_criteria>

<output>
Deliverables go to:
- .planning/phases/10-retrieval/
- Also optionally mirror to .planning/gauntlet_phases/phase10_retrieval/
</output>
