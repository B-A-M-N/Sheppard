# Phase 05E — Race-Condition Hardening Review

## Status: NOT STARTED

## Problem

Concurrent discovery/ingestion/distillation paths are not fully characterized for race conditions. Duplicate processing risk has not been systematically reviewed.

## Goal

Enumerate and harden the most likely concurrency edges. Either prevent duplicate processing or explicitly tolerate it with idempotency.

## Required Changes

- Audit concurrent hot paths: discovery→enqueue, fetch→ingest, ingest→distill
- Confirm queue claim semantics are sufficient (Redis SETNX / BLPOP / atomic dequeue)
- Confirm atom dedupe/storage boundaries are concurrency-safe (after 05A)
- Add guards where real collisions are possible (locks, atomic checks, idempotency keys)
- Document any accepted races with explicit rationale

## Acceptance Criteria

- Known concurrent hot paths are enumerated in VERIFICATION.md
- Duplicate processing risk is either prevented or explicitly tolerated with idempotency guarantee
- Verification includes at least one concurrent/repeated execution scenario
- No newly discovered hard race remains undocumented

## Key Files

- `crawler.py` (discovery/enqueue concurrency)
- `system.py` (ingest_source — concurrent call safety)
- `storage_adapter.py` (atom/chunk write concurrency)
- Redis queue claim logic

## Dependencies

- Complete after 05A (Atom Deduplication) — dedupe is a prerequisite for clean race analysis

## Deliverables

- `PLAN.md` — concrete implementation steps
- `SUMMARY.md` — what changed and why
- `VERIFICATION.md` — concurrent execution evidence, PASS/FAIL decision
