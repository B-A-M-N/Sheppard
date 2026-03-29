# Deferred Validation Backlog (Phase 07+)

**Purpose**: Track invariants that are relevant to system quality but **out of scope** for the core Phase 07 orchestration validation. These will be planned into later phases (e.g., Phase 08 hardening, Phase 09 product validation).

**Source**: Derived from `PHASE-07-VALIDATION-CONTRACT.md` initial set of 12 invariants; 5 kept for Phase 07, 7 deferred.

---

## Deferred Invariants

### V-03: ReportQualityEvaluable

**Description**: Final reports must be scorable against golden reference on dimensions: factual accuracy, completeness, contradiction handling, readability. Requires golden dataset + LLM judge.

**Why deferred**: Product quality validation, not orchestration correctness. Suitable for a later "quality gate" phase after orchestration is proven.

**Suggested phase**: Phase 09 (Quality Validation) or Phase 10 (Production Readiness)

---

### V-05: FirecrawlTestStrategyDefined

**Description**: Tests must not require uncontrolled external Firecrawl calls. Must use mocks/cassettes; integration tests clearly marked and excluded from default CI.

**Why deferred**: Test infrastructure concern, not core orchestration behavior. Can be addressed as a separate "testability" improvement phase.

**Suggested phase**: Phase 08 (Test Infrastructure Hardening)

---

### V-06: ResearchSystemOrchestratorIntegration

**Description**: New `ResearchOrchestrator` must be fully decoupled from legacy `ResearchSystem`. No mixed code paths; configuration flag mutually exclusive.

**Why deferred**: Integration correctness should be verified, but it's a **refactoring quality** not core to orchestrator's runtime behavior. Could be verified in a Phase 08 "migration validation" phase.

**Suggested phase**: Phase 08 (Legacy Decoupling Validation)

---

### V-07: ConfigExposesRequiredMetrics

**Description**: All runtime-tunable parameters (ceiling, thresholds, queue depth, batch size) must be documented and configurable via env/config.

**Why deferred**: Configuration design is a pre-implementation concern; by the time we reach validation, config should already be in place. If not, this becomes a "configuration audit" phase.

**Suggested phase**: Phase 08 (Operational Readiness) or earlier planning fix

---

### V-08: LlmErrorsHandledGracefully

**Description**: `query_knowledge()` must never crash due to LLM failures. Transient errors retry (max 3); permanent errors return graceful messages.

**Why deferred**: Interactive query layer is **product UX**, not orchestration spine. This belongs to Phase 5's interactive query validation, not Phase 07.

**Suggested phase**: Phase 11 (Interactive Query Validation) if not already done

---

### V-11: ExhaustedModesSurviveRestart

**Description**: After checkpoint/restart, `exhausted_modes` for each node must be restored exactly. No epistemic progress lost.

**Why deferred**: This is a **Phase 06 gap-closure** verification item. It should have been verified immediately after Phase 06-05 fix, not postponed to Phase 07. If not yet verified, schedule a small Phase 06.1 verification or add to Phase 07 if absolutely necessary.

**Suggested action**: Check if this was already verified during Phase 06 gap-closure. If not, create a quick verification task before Phase 07 or include as a minor addition.

---

### V-12: AcademicFilteringEnforced

**Description**: If `academic_only=True`, no non-academic URL enters queue. Filter must be active at enqueue boundary.

**Why deferred**: Also a **Phase 06 gap-closure** verification item (fix was 06-04). Should have been validated immediately after that fix.

**Suggested action**: Check if verified during Phase 06. If not, schedule quick verification or add to Phase 07 as a minor invariant.

---

## Summary Table

| Invariant | Category | Reason for deferral | Suggested phase |
|-----------|----------|---------------------|-----------------|
| V-03 | Product quality | Not core orchestration | 09 (Quality Gate) |
| V-05 | Test infrastructure | Separate concern | 08 (Test Hardening) |
| V-06 | Legacy decoupling | Migration quality | 08 (Decoupling Validation) |
| V-07 | Configuration | Should be done pre-validation | 08 (Ops Readiness) |
| V-08 | UX error handling | Interactive query layer | 11 (Query UX) |
| V-11 | Phase 06 gap | Already closed; verify near fix | 06.1 or 07 minor |
| V-12 | Phase 06 gap | Already closed; verify near fix | 06.1 or 07 minor |

---

## Action Items

1. **Phase 06 gap verification (V-11, V-12)**: Confirm these were verified during Phase 06 gap-closure. If not, create verification tasks immediately (small effort).
2. **Future planning**: When planning Phase 08+, consult this backlog to incorporate deferred invariants into the appropriate phase's contract.
3. **Do not** add these to Phase 07 plan — keep Phase 07 tightly scoped to the 5 core orchestration invariants.

---

**Locked**: This backlog is informational only. It does not affect the current Phase 07 definition.
