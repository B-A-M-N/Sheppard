# Project Roadmap

**Current Milestone:** none (accepting new milestone)
**Archived Milestones:**
- v1.0 — Truth Contract Implementation (✅ Shipped 2026-03-30)
- v1.1 — Performance & Observability (✅ Shipped 2026-03-31)
- v1.2 — Derived Insight & Report Excellence Layer (✅ Shipped 2026-04-01)

---

## v1.2 — Derived Insight & Report Excellence Layer (Archived)

All phase details archived in `.planning/milestones/v1.2-ROADMAP.md`.

<details>
<summary>Expand for brief status</summary>

- 12-A Derived Claim Engine ✅
- 12-B Dual Validator Extension ✅
- 12-C Evidence Graph / Claim Graph ✅
- 12-D Evidence-Aware Section Planner ✅
- 12-E Multi-Pass Composition Pipeline ✅
- 12-F Longform Verifier ✅

**Summary:** v1.2 delivers advanced analytical reasoning with deterministic derived claims, evidence graph clustering, multil-pass synthesis, and 7-gate longform verification.

</details>

## v1.1 — Performance & Observability (Archived)

All phase details archived in `.planning/milestones/v1.1-ROADMAP.md`.

<details>
<summary>Expand for brief status</summary>

- 12-01 Benchmark suite ✅
- 12-02 Retrieval optimization ✅
- 12-02.1 Latency diagnosis ✅
- 12-02.2 Batch queries ✅
- 12-03 Synthesis throughput 🟡 (partial: deployment-bound)
- 12-04 Observability ✅
- 12-05 Contradictions V3 ✅
- 12-06 High-evidence E2E ✅
- 12-07 Ranking ✅

**Known limitation:** PERF-02 (throughput target) not met due to single-endpoint inference serialization; architecture ready for multi-endpoint scaling.

</details>

## v1.0 — Truth Contract Implementation (Archived)

All phase details archived in `.planning/milestones/v1.0-ROADMAP.md`.

<details>
<summary>Expand for brief status</summary>

- Phase 10 Interactive Truth-Grounded Retrieval ✅
- Phase 11 Synthesis Truth Contract ✅
- Phase 11.1 Remediation ✅

**Verdict:** PASS. End-to-end truth guarantees enforced.

</details>

---

## Future Work

*Next milestone to be defined via `/gsd:new-milestone`.*

**Legend**: ✅ Completed, ⬜ Pending, 🔄 In Progress

## Notes

- All gaps from Phase 06-01 audit have been closed.
- Database migration pending for `exhausted_modes_json` column.
- v1.1 shipped with known limitation: PERF-02 throughput target not met due to deployment constraint (single-endpoint inference). Architecture ready for scaling in v1.2.
- v1.2 shipped with complete derived insight pipeline; LongformVerifier integration ready for Pass 5 plug-in.

