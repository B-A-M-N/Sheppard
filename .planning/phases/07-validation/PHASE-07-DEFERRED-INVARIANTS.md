# Phase 07 — Deferred Invariants Contract

**Important**: These invariants are **NOT** part of Phase 07 pass criteria. They are tracked to preserve traceability and will be reactivated in their assigned future phases.

**Purpose**: A controlled backlog of validation invariants that belong to later phases. Each entry has clear ownership, dependencies, and validation intent.

**Do not** treat this as a dumping ground. Each item must be explicitly planned into its assigned phase's validation contract.

---

## V-11: ExhaustedModesSurviveRestart

**ID**: V-11
**Name**: Exhausted modes persistence verification

**Origin**:
- Original ambiguity: A.5 (exhausted_modes persistence)
- Phase 06 gap: B05
- Fixed in: Phase 06-05

**Reason Deferred**: This is a Phase 06 gap-closure verification item. It should have been verified immediately after the fix. Including it in Phase 07 creates unnecessary coupling; it belongs with its fix.

**Assigned Phase**: Phase 06.1 (or as minor addition to Phase 06 verification)
**Priority**: HIGH — already fixed, only verification pending

**Dependencies**:
- Phase 06-05 commit present
- Checkpoint/restart mechanism functional

**Validation Intent**:
Prove that after checkpoint/restart, `exhausted_modes` sets are restored exactly per node. No epistemic progress lost.

**Suggested test**:
1. Generate nodes, exhaust some modes
2. Checkpoint
3. Restart with same mission_id
4. Verify `FrontierNode.exhausted_modes` matches saved state

**Status**: DEFERRED (should be verified near Phase 06)

---

## V-12: AcademicFilteringEnforced

**ID**: V-12
**Name**: Academic-only URL filtering verification

**Origin**:
- Original ambiguity: A.3 (URL filtering)
- Phase 06 gap: B03
- Fixed in: Phase 06-04

**Reason Deferred**: Phase 06 gap-closure verification item. Should be verified with its fix, not in Phase 07.

**Assigned Phase**: Phase 06.1 (or as minor addition to Phase 06 verification)
**Priority**: HIGH — already fixed, only verification pending

**Dependencies**:
- Phase 06-04 commit present
- `academic_only=True` configuration active

**Validation Intent**:
Prove that when `academic_only=True`, non-academic URLs are rejected at enqueue boundary. When False, all URLs accepted.

**Suggested test**:
1. Configure `academic_only=True`
2. Attempt enqueue of academic URL → should succeed
3. Attempt enqueue of non-academic URL → should be rejected
4. Repeat with `False` → both succeed

**Status**: DEFERRED (should be verified near Phase 06)

---

## V-03: ReportQualityEvaluable

**ID**: V-03
**Name**: Report quality evaluation framework

**Origin**: A.11 (report synthesis), A.30 (summary quality)

**Reason Deferred**: Product quality validation, not orchestration correctness. Requires golden dataset and LLM judge. This belongs to a dedicated quality gate phase.

**Assigned Phase**: Phase 09 (Quality Validation) or Phase 10 (Production Readiness)
**Priority**: MEDIUM

**Dependencies**:
- Golden dataset created (Phase 07 task originally)
- LLM-as-judge harness implemented
- Report generation stable

**Validation Intent**:
Prove that generated reports score ≥ 0.85 on factual accuracy, completeness, contradiction handling, readability using LLM judge vs golden references.

**Suggested test**:
- Run missions on 3–5 golden topics
- Evaluate reports with judge
- Verify thresholds met

**Status**: DEFERRED (Phase 09)

---

## V-05: FirecrawlTestStrategyDefined

**ID**: V-05
**Name**: Firecrawl testing without external cost

**Origin**: A.27 — How to test with real Firecrawl without spending money?

**Reason Deferred**: Test infrastructure concern, not core behavior. Should be addressed in a testability hardening phase.

**Assigned Phase**: Phase 08 (Test Infrastructure Hardening)
**Priority**: MEDIUM

**Dependencies**:
- Test suite structure exists
- Mocking strategy chosen (cassettes, local server, fixtures)

**Validation Intent**:
Prove that default test suite runs entirely offline with no uncontrolled external API calls. Integration tests requiring live Firecrawl are explicitly marked and excluded from default CI.

**Suggested test**:
- Scan test code for `firecrawl` domain calls
- Run `pytest -m "not integration"` in isolated network (no internet)
- Verify zero external calls attempted

**Status**: DEFERRED (Phase 08)

---

## V-06: ResearchSystemOrchestratorIntegration

**ID**: V-06
**Name**: Legacy ResearchSystem decoupling verification

**Origin**: A.28 — Relationship between `ResearchSystem` and new `Orchestrator`

**Reason Deferred**: Migration quality; verifies no hybrid code paths exist. Not core to orchestrator runtime correctness.

**Assigned Phase**: Phase 08 (Legacy Decoupling Validation)
**Priority**: MEDIUM

**Dependencies**:
- Orchestrator implementation complete
- Legacy ResearchSystem still present (for fallback)
- Configuration flag `USE_ORCHESTRATOR` exists

**Validation Intent**:
Prove that when orchestrator is enabled, no code path invokes `ResearchSystem.research_topic()`. The two systems are mutually exclusive.

**Suggested test**:
- Static analysis: grep for `ResearchSystem` usage in main application
- Dynamic: set `USE_ORCHESTRATOR=True`, monitor logs/metrics for any ResearchSystem calls
- Assert zero cross-dependency

**Status**: DEFERRED (Phase 08)

---

## V-07: ConfigExposesRequiredMetrics

**ID**: V-07
**Name**: Configuration completeness verification

**Origin**: A.12 — Configuration options needed?

**Reason Deferred**: Configuration should be designed and implemented pre-validation. If not done, this becomes an "operational readiness" gap.

**Assigned Phase**: Phase 08 (Operational Readiness)
**Priority**: MEDIUM

**Dependencies**:
- Config system in place
- List of required parameters identified

**Validation Intent**:
Prove all runtime-tunable parameters (ceiling, thresholds, queue depth, batch size) are documented and configurable via environment variables or config file. No magic numbers in critical paths.

**Suggested test**:
- Audit `config.py` for each required parameter
- Verify env var override works for each
- Check docs list each parameter

**Status**: DEFERRED (Phase 08)

---

## V-08: LlmErrorsHandledGracefully

**ID**: V-08
**Name**: LLM error handling in interactive queries

**Origin**: A.15 — How to handle LLM errors during interactive queries?

**Reason Deferred**: Interactive query layer (Phase 5) concern, not orchestration spine. Product UX, not core correctness.

**Assigned Phase**: Phase 11 (Interactive Query Validation) or Phase 10 (API Hardening)
**Priority**: LOW

**Dependencies**:
- `query_knowledge()` endpoint implemented
- LLM client configured with retry/timeout

**Validation Intent**:
Prove that `query_knowledge()` never crashes due to LLM failures. Transient errors retry (max 3). Permanent errors return user-friendly messages without stack traces.

**Suggested test**:
- Mock LLM to simulate timeout, malformed response, rate limit, 500 error
- Call query endpoint; verify retry behavior and error messages
- Assert server never crashes

**Status**: DEFERRED (Phase 11)

---

## Summary Table

| ID | Invariant | Assigned Phase | Priority | Dependencies |
|-----|-----------|----------------|----------|--------------|
| V-11 | Exhausted modes survive restart | Phase 06.1 | HIGH | Phase 06-05 fix |
| V-12 | Academic filtering enforced | Phase 06.1 | HIGH | Phase 06-04 fix |
| V-03 | Report quality evaluable | Phase 09 | MEDIUM | Golden dataset, judge harness |
| V-05 | Firecrawl test strategy defined | Phase 08 | MEDIUM | Mocking infrastructure |
| V-06 | ResearchSystem/orchestrator integration | Phase 08 | MEDIUM | Orchestrator complete |
| V-07 | Config exposes required metrics | Phase 08 | MEDIUM | Config system |
| V-08 | LLM errors handled gracefully | Phase 11 | LOW | Query layer implemented |

---

## Action Items for Future Planning

1. **Phase 06.1**: Immediately verify V-11 and V-12 (these are gap closures already implemented).
2. **Phase 08 planning**: Incorporate V-05, V-06, V-07 into validation contract.
3. **Phase 09 planning**: Incorporate V-03 into quality gate validation.
4. **Phase 11 planning**: Incorporate V-08 into interactive query validation.
5. **Do not** let these slip through unvalidated. Each must be explicitly reactivated in its assigned phase's contract.

---

**Locking principle**: Deferred does not mean forgotten. These are tracked with ownership and will be planned into their respective phases.
