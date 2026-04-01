---
phase: 12-07
slug: ranking-improvements
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-31
---

# Phase 12-07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio |
| **Config file** | `pytest.ini` or `pyproject.toml` |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-07-01-01 | 01 | 1 | RANK-04 | unit | `python -m pytest tests/ -x -q -k "ranking"` | ❌ W0 | ⬜ pending |
| 12-07-01-02 | 01 | 1 | RANK-01 | unit | `python -m pytest tests/ -x -q -k "composite_score or ranking"` | ❌ W0 | ⬜ pending |
| 12-07-01-03 | 01 | 1 | RANK-02 | unit | `python -m pytest tests/ -x -q -k "deterministic or ranking"` | ❌ W0 | ⬜ pending |
| 12-07-01-04 | 01 | 1 | RANK-03 | unit | `python -m pytest tests/ -x -q -k "no_filter or ranking"` | ❌ W0 | ⬜ pending |
| 12-07-02-01 | 02 | 2 | RANK-01–04 | integration | `python -m pytest tests/ -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ranking.py` — unit tests for `RankingConfig`, `enable_ranking` flag, composite sort key, determinism with `global_id` tiebreaker, no-filter guarantee
- [ ] `tests/conftest.py` — shared fixtures (already exists; may need `RetrievedItem` factory fixture)

*Existing infrastructure (pytest + pytest-asyncio) covers the framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Default behavior preserved for production callers | RANK-04 | No test covers all callers; manual inspection needed | Run `grep -r "RetrievalQuery" src/ --include="*.py"` and verify none pass `enable_ranking=True` in prod paths |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
