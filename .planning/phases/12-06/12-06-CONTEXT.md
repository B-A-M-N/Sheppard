# Phase 12-06: High-Evidence E2E Integration Test — Context

**Gathered:** 2026-04-01
**Status:** Ready for planning
**Source:** User-directed scope for 12-06 + REQUIREMENTS.md E2E-01/02/03

---

<domain>
## Phase Boundary

**Goal:** Prove the full high-evidence path works under real conditions. Validate the complete truth chain: mission → frontier → ingestion → retrieval → contradictions → synthesis → report persistence.

**Requirements Addressed:** E2E-01, E2E-02, E2E-03

**Decisions (LOCKED):**
- **Approach:** Correctness-first E2E verification with benchmark continuity
- **Tooling:** Run `scripts/benchmark_suite.py --scenario high_evidence` for execution, `scripts/e2e_verifier.py` for validation
- **No App Code Changes:** This phase only adds verification/test code, does not modify synthesis/retrieval logic
- **Database:** Validate state in `knowledge_atoms`, `synthesis_sections`, `synthesis_citations` via direct PG queries
- **Observability:** Validate `logs/metrics.jsonl` contains complete timeline for the mission
- **Contradictions:** Verify they surface via V3 path (not fallback), though count may be zero if extraction data is sparse
- **Output:** `e2e_report.json` (machine readable), `e2e_verification.md` (human readable)
- **Constraint:** Must explicitly note 12-03 single-endpoint bottleneck impact on E2E throughput
</domain>

<must_haves>
- E2E-01: Full pipeline executes, no exceptions
- E2E-02: Verification assertions:
  - At least one atom retrieved per section on average
  - All section citations match `atom_ids_used` stored in DB
  - Report passes validator (re-check via script)
  - `atom_ids_used` array matches `synthesis_citations` rows
- E2E-03: Deterministic topic, reproducible results
- Guardrails: 99/99 tests before and after
- No truth-contract weakening
- No validator bypass
- No mission_id/provenance changes
</must_haves>

<forbidden>
- NO logic changes to synthesis, retrieval, or validator
- NO ranking changes
- NO modifications to `mission_id` or provenance rules
- NO bypass of truth checks (all must be verified, not mocked)
</forbidden>

<canonical_refs>
- `.planning/REQUIREMENTS.md` — E2E-01, E2E-02, E2E-03 definitions
- `scripts/benchmark_suite.py` — Existing high_evidence runner
- `src/research/reasoning/synthesis_service.py` — Validator logic (read for re-check pattern)
- `src/utils/structured_logger.py` — 12-04 observability artifacts
- `src/config/database.py` — DB connection config for verifier script
</canonical_refs>
