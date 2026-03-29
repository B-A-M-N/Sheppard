# Phase 05D — Retry Policy

## Status: NOT STARTED

## Problem

Retry behavior for fetch, LLM extraction, and DB operations is underdefined. Transient failures may silently drop work or cause noisy infinite loops.

## Goal

Establish an explicit retry policy by failure class. Make transient failures retry predictably; make non-retryable failures fail fast and clearly.

## Required Changes

- Classify failures: retryable (network, transient LLM, transient DB) vs non-retryable (auth, schema mismatch, permanent 4xx)
- Define retry counts and backoff per class (e.g., 3x exponential for network, 2x for LLM, 1x for DB)
- Define terminal failure handling (dead-letter, log, alert)
- Apply policy to: fetch/network failures, LLM extraction failures, DB/projection failures
- Log retry attempts and terminal outcomes at each boundary

## Acceptance Criteria

- Retry behavior is documented and implemented per failure class
- Transient failures retry predictably without silent drops
- Non-retryable failures fail fast with clear log output
- Verification includes at least one forced transient-failure scenario showing correct retry behavior

## Key Files

- `crawler.py` (fetch path)
- `pipeline.py` (LLM extraction path)
- `storage_adapter.py` (DB write path)

## Deliverables

- `PLAN.md` — concrete implementation steps
- `SUMMARY.md` — what changed and why
- `VERIFICATION.md` — forced-failure test evidence, PASS/FAIL decision
