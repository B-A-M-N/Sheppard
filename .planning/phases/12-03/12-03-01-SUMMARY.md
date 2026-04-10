# Phase 12-03-01 Summary: Async Worker Pool Refactor

**Status:** ✅ Completed
**Date:** 2026-03-31

## Changes

### Files Modified

| File | Change |
|------|--------|
| `src/research/archivist/synth_adapter.py` | Removed PREVIOUS CONTEXT block from prompt. `"Maintain a logical flow"` instruction removed. |
| `src/config/settings.py` | Added `SYNTHESIS_CONCURRENCY_LIMIT` config (default 8). |
| `src/research/reasoning/synthesis_service.py` | Replaced sequential section loop with bounded async worker pool (`asyncio.Semaphore`), retry logic (3 attempts, exponential backoff), per-section timing metrics, deterministic ordering via `sorted(results, key=lambda x: x[0])`. |

## Guardrail Results

- **Phase 11 invariants:** 8/8 passed
- **Full guardrail (post-benchmark):** 99/99 passed

## Pyright Warnings

- Fixed: 6 "possibly unbound variable" warnings (initialized `prose`, `llm_ms` before retry loop)
- Remaining: cosmetic "not accessed" warnings (unused loop variables)

## Key Design Decisions

- Async worker pool uses `asyncio.Semaphore(settings.SYNTHESIS_CONCURRENCY_LIMIT)` for bounded concurrency
- No `previous_context` dependency — sections generated independently
- Citations assigned after all sections complete (from stable `packet.atom_ids_used`)
- Insufficient evidence sections still stored (required for truth contract invariants)
