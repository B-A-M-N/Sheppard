# PHASE 10 — RETRIEVAL & INTERACTIVE AGENT INTEGRATION

## Mission

Audit the interactive query path and verify that the agent can answer from accumulated knowledge while background research continues.

## GSD Workflow

- Discuss: How does retrieval work?
- Plan: Map query → context → response
- Execute: Inspect retrieval and synthesis
- Verify: Produce RETRIEVAL_GROUNDING_REPORT.md

## Prompt for Agent

```
You are executing Phase 10 for Sheppard V3: Retrieval & Interactive Agent Integration.

Mission:
Audit the interactive query path and verify that the agent can answer from accumulated knowledge while background research continues.

Objectives:
1. Identify the interactive chat/query entrypoint
2. Identify retrieval logic over atoms
3. Identify ranking/relevance logic
4. Identify how retrieved context is injected into responses
5. Verify whether live crawl knowledge becomes queryable incrementally
6. Verify fallback behavior when memory lacks coverage

Required method:
- Inspect chat/query code path
- Inspect retrieval adapters to Chroma/Postgres
- Inspect context-building logic
- Inspect whether response synthesis is grounded in stored atoms
- Inspect whether the system leaks back to generic model priors without warning

Deliverables (write to .planning/gauntlet_phases/phase10_retrieval/):
- QUERY_PATH_AUDIT.md
- RETRIEVAL_GROUNDING_REPORT.md
- CONTEXT_ASSEMBLY_AUDIT.md
- LIVE_RESEARCH_INTERACTION_REPORT.md
- PHASE-10-VERIFICATION.md

Mandatory checks:
- Can the user ask a question during an active mission?
- Does the answer use atoms or just the base model?
- Is provenance available in responses?
- Is partial knowledge surfaced honestly?
- Is there a distinction between memory-grounded vs. model-native answer content?

Hard fail conditions:
- Interactive answers are not grounded
- Crawl results are not actually available to chat
- Retrieval exists but is not wired into response generation
- The system pretends certainty when memory is incomplete

Completion bar:
PASS only if interactive answering is truly memory-backed and compatible with async research.
```

## Deliverables

- **QUERY_PATH_AUDIT.md**
- **RETRIEVAL_GROUNDING_REPORT.md**
- **CONTEXT_ASSEMBLY_AUDIT.md**
- **LIVE_RESEARCH_INTERACTION_REPORT.md**
- **PHASE-10-VERIFICATION.md**

## Verification Template

```markdown
# Phase 10 Verification

## Grounding

- [ ] Query path traced from input to response
- [ ] Retrieval uses atoms, not just web
- [ ] Response synthesis includes citations
- [ ] Fallback behavior defined (when memory insufficient)
- [ ] Concurrent research and query verified

## Evidence

- (query code, context building, response templates)

## Verdict

**Status:** PASS / PARTIAL / FAIL

## Grounding Gaps

- (where model hallucinates vs. uses memory)
```

## Completion Criteria

PASS when every answer is demonstrably grounded in stored atoms with provenance.
