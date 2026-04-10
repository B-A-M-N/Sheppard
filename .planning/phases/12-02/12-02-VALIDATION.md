---
phase: 12-02
slug: retrieval-latency-optimization
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-30
---

# Phase 12-02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none (uses default discovery) |
| **Quick run command** | `pytest tests/research/reasoning/test_phase11_invariants.py -q` |
| **Full suite command** | `pytest tests/ -q --ignore=tests/test_archivist_resilience.py --ignore=tests/test_chat_integration.py --ignore=tests/test_smelter_status_transition.py` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/research/reasoning/test_phase11_invariants.py -q`
- **After every plan wave:** Run full suite command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-T1 | 12-02-01 | 1 | PERF-01 | unit | `pytest tests/research/reasoning/test_concurrent_assembly.py -q` | ❌ Wave 0 | pending |
| 01-T2 | 12-02-01 | 1 | PERF-01 | code | `grep "RETRIEVAL_CONCURRENCY_LIMIT" src/research/reasoning/assembler.py` | ❌ Wave 0 | pending |
| 02-T1 | 12-02-02 | 2 | PERF-01 | unit | `pytest tests/research/reasoning/test_concurrent_assembly.py -q` | ❌ | pending |
| 02-T2 | 12-02-02 | 2 | PERF-01 | integration | `pytest tests/research/reasoning/test_phase11_invariants.py -q` | ✅ | pending |
| 03-T1 | 12-02-03 | 3 | PERF-01 | benchmark | `python3 scripts/benchmark_suite.py --scenario high_evidence --corpus-tier small --iterations 3` | ✅ (extends) | pending |
| 03-T2 | 12-02-03 | 3 | PERF-01 | benchmark | `python3 scripts/benchmark_suite.py --scenario high_evidence --corpus-tier medium --iterations 3` | ✅ (extends) | pending |

---

## Wave 0 Gaps

- [ ] `tests/research/reasoning/test_concurrent_assembly.py` — covers concurrent section ordering and error fallback (REQ: PERF-01 concurrency correctness)
- [ ] `RETRIEVAL_CONCURRENCY_LIMIT` constant in `src/research/reasoning/assembler.py` — covers PERF-04 configurability
- [ ] No framework install needed (pytest already present, 94 tests passing per BASELINE_METRICS.md)

---

## Nyquist Requirements → Test Coverage

| Requirement | Behavior Under Test | Test File | Status |
|-------------|---------------------|-----------|--------|
| PERF-01 | Total retrieval P95 < 200-300ms with concurrent gather | benchmark_suite.py | Wave 3 |
| PERF-01 | Citation key stability across concurrent runs | test_phase11_invariants.py::test_atom_order_sorted | ✅ existing |
| PERF-01 | atom_ids_used ordering preserved after concurrency | test_phase11_invariants.py::test_evidence_packet_captures_atom_ids | ✅ existing |
| PERF-01 | Section order preserved after concurrent gather | test_concurrent_assembly.py | ❌ Wave 0 |
| PERF-01 | return_exceptions=True handles section failure gracefully | test_concurrent_assembly.py | ❌ Wave 0 |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python asyncio | Concurrent gather | ✓ | 3.10 stdlib | — |
| chromadb | Vector queries | ✓ | 1.5.5 | — |
| PostgreSQL | Atom seeding | ✓ | localhost:5432 | — |
| Redis | System init | ✓ | localhost:6379 | — |
| pytest | Test guardrail | ✓ | existing | — |

No missing dependencies.
