# PHASE 08.2 — RESILIENCE HARDENING

## Mission

Prove the repaired Phase 08 ingestion pipeline (chunking + validation) is robust under adverse but realistic conditions. This is a **local hardening band** — not platform-wide fault tolerance.

## Scope

**In scope (ingestion/chunking/validation path only):**
- Ingestion retries under transient failures
- Transient vs. non-retryable error classification
- Malformed / partial input handling
- Boundary-size behavior (very small, very large, edge-case content)
- Duplicate / replay safety (no duplicate chunk insertion from retry loops)
- Deterministic recovery behavior (same valid input → same output, always)
- Race and ordering edge cases directly around ingestion/chunking/validation
- LLM/external dependency failure handling (timeouts, malformed responses, empty responses)

**Out of scope (belongs in Phase 13 or later):**
- Full platform-wide fault tolerance
- Cluster/distributed recovery architecture
- Generalized orchestration failure semantics
- Database (Postgres/Redis/Chroma) availability failures
- Worker death/recovery
- Future-stage synthesis / atom contradiction logic
- Any component not touched by Phase 08 or 08.1

## GSD Workflow

- Discuss: What adversarial conditions directly threaten the repaired ingestion path?
- Plan: Map each success criterion to targeted tests and/or code changes
- Execute: Implement hardening; produce evidence for each criterion
- Verify: Produce PHASE-08.2-VERIFICATION.md with PASS/PARTIAL/FAIL verdict

## Success Criteria

PASS only if all six criteria are proven:

### 1. Transient failure behavior is explicit
- Retryable vs. non-retryable errors are classified
- Bounded retries exist (no infinite loops)
- Terminal failures are surfaced clearly (not swallowed)

### 2. Validation remains non-bypassable under failure
- Partial failures cannot cause invalid content to slip into storage
- Retry paths do not skip preconditions (early rejection, content validation)

### 3. Chunking remains deterministic under retries / re-entry
- Same valid input → same chunk outputs, even on re-entry
- No duplicate chunk insertion from retry loops unless explicitly deduplicated

### 4. Partial-ingestion states are controlled
- No half-written artifact state presented as success
- Outcome is either: atomic completion or explicit failed/incomplete state

### 5. Race-condition edges are covered
- Concurrent or repeated ingestion requests do not corrupt state
- Duplicate submissions behave predictably (idempotent or clearly rejected)

### 6. LLM / external dependency failures are bounded
- Timeouts handled explicitly
- Malformed responses handled explicitly
- Empty responses handled explicitly
- Exceptions do not produce silent false-success

## Deliverables

Write to `.planning/gauntlet_phases/phase08.2_resilience_hardening/`:

- **RETRY_CLASSIFICATION.md** — retryable vs. non-retryable error map for the ingestion path
- **VALIDATION_BYPASS_AUDIT.md** — evidence that no failure path bypasses validation
- **CHUNKING_DETERMINISM_UNDER_FAILURE.md** — evidence chunking is stable under retries/re-entry
- **PARTIAL_STATE_AUDIT.md** — evidence of atomic completion or explicit incomplete state
- **RACE_CONDITION_AUDIT.md** — concurrent ingestion behavior evidence
- **EXTERNAL_DEPENDENCY_FAILURE_AUDIT.md** — LLM/fetch timeout and malformed response handling
- **PHASE-08.2-VERIFICATION.md** — final verdict with per-criterion evidence

## Hard Fail Conditions

- Any failure path bypasses content validation
- Retry loops can insert duplicate chunks without deduplication
- Empty/malformed input produces a stored Memory artifact
- Concurrent ingestion corrupts chunk ordering or metadata
- LLM timeout or malformed response is silently swallowed as success

## Completion Bar

PASS only if the repaired ingestion pipeline is proven robust:
bounded, deterministic, non-bypassable, and failure-explicit.
