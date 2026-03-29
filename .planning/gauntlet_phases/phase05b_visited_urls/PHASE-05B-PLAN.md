# Phase 05B — Persist visited_urls

## Status: NOT STARTED

## Problem

URL visitation state lives only in memory/runtime. On restart, previously visited URLs can be rediscovered and re-enqueued, causing unnecessary churn and duplicate ingestion.

## Goal

Make crawl visitation idempotent beyond in-memory state.

## Required Changes

- Persist visited/discovered URL state in canonical V3 storage (Postgres or Redis with persistence)
- Use normalized URL identity (canonical form, strip tracking params)
- Ensure discovery checks persisted visited state before enqueue
- Retain current in-process dedupe as defense-in-depth, not primary control

## Acceptance Criteria

- Restarting the system does not lose visited URL knowledge
- Previously visited URLs are not re-enqueued unless explicitly allowed
- Queue volume drops for repeated runs on same mission/domain set
- Verification shows visited state survives restart and prevents duplicate scheduling

## Key Files

- `crawler.py` (lines 295, 313 — URL discovery and enqueue)
- V3 storage layer (Postgres `research_missions` / sourcing tables)

## Deliverables

- `PLAN.md` — concrete implementation steps
- `SUMMARY.md` — what changed and why
- `VERIFICATION.md` — before/after evidence, PASS/FAIL decision
