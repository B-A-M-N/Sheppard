# Project Roadmap

**Current Milestone:** v1.2 — Deployment Scaling & Throughput Realization (planned)
**Archived Milestones:**
- v1.0 — Truth Contract Implementation (✅ Shipped 2026-03-30)
- v1.1 — Performance & Observability (✅ Shipped 2026-03-31)

---

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

## Future Work (Next: v1.2)

### Phase 06 — Discovery Engine

| Plan | Name | Status | Tasks (C/T) |
| ---- | ---- | ------ | ----------- |
| 06-01 | Audit | ✅ Completed | 1/1 |
| 06-02 | parent_node_id fix | ✅ Completed | 1/1 |
| 06-03 | Deep mining fix | ✅ Completed | 1/1 |
| 06-04 | Academic filtering | ✅ Completed | 1/1 |
| 06-05 | exhausted_modes persistence | ✅ Completed | 1/1 |
| 06-06 | Queue backpressure | ✅ Completed | 1/1 |
| 06-XX | Validation / Integration | ⬜ Pending | 0/0 |

### Phase 07 — Orchestration Validation

| Plan | Name | Status | Tasks (C/T) |
| ---- | ---- | ------ | ----------- |
| 07-01 | Core invariants | ✅ Completed | 5/5 |

### Phase 08 — Scraping / Content Normalization Audit

| Plan | Name | Status | Tasks (C/T) |
| ---- | ---- | ------ | ----------- |

### Phase 09 — Smelter / Atom Extraction Audit

| Plan | Name | Status | Tasks (C/T) |
| ---- | ---- | ------ | ----------- |
| 09-01 | Atom schema and extraction pipeline | ✅ Completed | 0/0 |
| 09-XX | Gap Closure (soft acceptance) | ✅ Completed | 0/0 |

### Phase 10–11.1 — Truth Contract Implementation (v1.0)

**Status:** ✅ COMPLETE (archived 2026-03-30)

*All phases consolidated under milestone v1.0. See `.planning/milestones/v1.0-ROADMAP.md` for full details.*

**Legend**: ✅ Completed, ⬜ Pending, 🔄 In Progress

## Notes

- All gaps from Phase 06-01 audit have been closed.
- Database migration pending for `exhausted_modes_json` column.
- v1.1 shipped with known limitation: PERF-02 throughput target not met due to deployment constraint (single-endpoint inference). Architecture ready for scaling in v1.2.

