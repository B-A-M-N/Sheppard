# Phase 05A — Atom Deduplication

## Status: NOT STARTED

## Problem

Atoms can be duplicated when distillation runs on the same source multiple times. This degrades retrieval quality, pollutes reports, and inflates semantic memory over time.

## Goal

Make atom storage idempotent for semantically identical extracted atoms.

## Required Changes

- Define a deterministic atom identity rule (content + evidence hash)
- Replace or augment random UUID-only identity with a stable hash key
- Enforce dedupe at the storage boundary (`storage_adapter.py` ATOMS_STORED path)
- Preserve full lineage metadata while preventing duplicate logical atoms

## Acceptance Criteria

- Re-running distillation on the same source does not create duplicate atoms
- Storage path rejects or merges duplicates deterministically
- Retrieval count for repeated identical input remains stable
- Verification shows duplicate atom creation no longer occurs for same input/evidence pair

## Key Files

- `storage_adapter.py` (lines 616–660 — atomic transaction, atom insert path)
- `pipeline.py` (line 83 — atom extraction)

## Deliverables

- `PLAN.md` — concrete implementation steps
- `SUMMARY.md` — what changed and why
- `VERIFICATION.md` — before/after evidence, PASS/FAIL decision
