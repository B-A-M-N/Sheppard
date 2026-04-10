# Phase 12-04: Structured metrics & tracing — Context

**Gathered:** 2026-03-31
**Status:** Ready for planning
**Source:** Direct user decisions (authoritative input)

---

<domain>

## Phase Boundary

**Goal:** Add structured JSON logging and lightweight span-based tracing to the local CLI-first system, enabling full mission timeline reconstruction from logs alone.

**Requirements Addressed:** OBS-01, OBS-02
**Deferred to later phase:** OBS-03 (API endpoints), OBS-04 (Dashboard infrastructure)

**Out of Scope:**
- HTTP server / REST API
- Prometheus, Statsd, or external observability systems
- Grafana or web dashboards
- PostgreSQL or Redis tables for metrics

---

</domain>

<decisions>

## Implementation Decisions (LOCKED)

### Where Metrics Live

- **Architecture:** JSON logs first, HTTP endpoints later (deferred)
- **Phase scope:** CLI-native observability only
- **No web server** in this phase
- **Log file:** `logs/metrics.jsonl` (one JSON object per line)

### Metrics Format

- **Only JSON structured logs** — no Prometheus, no Statsd
- **Zero heavy dependencies** — no structlog, opentelemetry, prometheus_client
- Use built-in `logging` with custom JSON formatter

### Trace ID Strategy

- **`mission_id` IS the trace ID** — no separate trace_id generation
- **`mission_id` MUST appear in every structured log event**
- No contextvars/propagation — mission_id is already available at all orchestration points

### Span Instrumentation Model

- **Lightweight custom span context manager** (NOT OpenTelemetry)
- Pattern:
  ```python
  with span_ctx("retrieval", mission_id):
      result = await retriever.retrieve(...)
  ```
- Each span emits:
  - `span_start` event when entering
  - `span_end` event with `duration_ms` when exiting
  - Stage name included in both events
- Instrument at orchestration boundaries only — not 82 individual logging sites
- Focus on major pipeline stages as entry points

### Required Pipeline Spans

All 6 stages MUST emit span events:
1. `frontier`
2. `acquisition`
3. `condensation`
4. `retrieval`
5. `synthesis`
6. `storage`

### Dashboard (OBS-04)

- **CLI + file-based only** in this phase
- Output: timeline reconstructed from `logs/metrics.jsonl`
- No Grafana, no HTML page
- Future: `sheppard timeline <mission_id>` CLI command (deferred)

### Backward Compatibility (12-03 metrics)

- **Replace** 12-03 string-format `logger.info(...)` calls with structured JSON logs
- **Do NOT** keep both formats — single canonical format only
- Example replacement:
  ```python
  # OLD
  logger.info(f"[Synthesis] Total synthesis: {total_synthesis_s:.2f}s; sections/min: {spm:.2f}")

  # NEW
  logger.info("synthesis_complete", mission_id=mission_id, event="synthesis_complete",
              stage="synthesis", duration_ms=total_synthesis_s*1000, sections_per_minute=spm, ...)
  ```

### Dependencies

- **Use:** built-in `logging`, `json`, `time`, custom JSON formatter
- **Forbidden:** structlog, opentelemetry, prometheus_client, statsd, any HTTP framework

### Storage Strategy

- **File-based JSON logs ONLY**
- `logs/metrics.jsonl` — append-only, one JSON object per line
- No Postgres tables, no Redis, no external storage
- File rotates via standard logging `RotatingFileHandler` (optional, not required)

### Scope Split

| Requirement | Status |
|-------------|--------|
| OBS-01 (structured metrics JSON) | ✅ IN scope |
| OBS-02 (distributed tracing spans) | ✅ IN scope |
| OBS-03 (API endpoints) | ❌ OUT — deferred |
| OBS-04 (Dashboard) | ❌ OUT — deferred |

### Success Criteria

- **OBS-01:** All pipeline logs emit structured JSON with `mission_id` present in every event
- **OBS-02:** All 6 pipeline stages emit `span_start` + `span_end` events with `duration_ms`
- **Verification:** A complete mission's timeline can be reconstructed from `logs/metrics.jsonl` alone — showing stage start/end timestamps and durations

### Forbidden Optimizations

- **DO NOT** add HTTP server or web framework
- **DO NOT** introduce external observability dependencies
- **DO NOT** modify business logic for instrumentation
- **DO NOT** change truth contract behavior (Phase 10/11 invariants preserved)
- **DO NOT** modify 99/99 guardrail test behavior

---

### Claude's Discretion

- Exact JSON schema for log events (beyond required fields)
- Whether to use `contextvars` for implicit mission_id propagation or explicit parameter
- Whether to create a dedicated metrics/tracing module or integrate with existing `src/config/logging.py`
- Rotation policy for `logs/metrics.jsonl` (daily, size-based, or unbounded)

---

</decisions>

<canonical_refs>

## Canonical References

**Downstream agents MUST read these before planning or implementing:**

### Phase scope & requirements
- `.planning/REQUIREMENTS.md` — OBS-01, OBS-02 definitions (scope split with OBS-03/04 deferred)
- `.planning/ROADMAP.md` — Phase 12-04 entry in milestone v1.1

### Prior work (must not break)
- `.planning/phases/12-03/` — 12-03 metrics instrumentation (will be replaced with structured format)
- `.planning/phases/12-02/` — PERF-01 retrieval timing (spans should measure same boundaries)
- `.planning/phases/10-11/` — Truth contract phases (invariants preserved)

### Source code (instrumentation targets)
- `src/config/logging.py` — Current logging setup (extend with JSON formatter)
- `src/core/system.py` — `system_manager.learn()` orchestration entry point
- `src/research/reasoning/synthesis_service.py` — 12-03 refactored code (replace string logs)
- `src/research/reasoning/v3_retriever.py` — Retrieval stage
- `src/research/condensation/pipeline.py` — Condensation stage
- `src/research/acquisition/frontier.py` — Frontier stage
- `scripts/benchmark_suite.py` — Benchmark timing code (keep as-is, add structured emission)

**Event model (REQUIRED fields per log line):**
```json
{
  "timestamp": "ISO 8601 UTC",
  "mission_id": "<correlation key>",
  "stage": "frontier|acquisition|condensation|retrieval|synthesis|storage",
  "event": "span_start|span_end|<custom_event>",
  "duration_ms": 142
}
```

---

</canonical_refs>

<specifics>

## Specific Ideas

### JSON Formatter

- Custom `logging.Formatter` subclass that converts Python log records to JSON
- Fields: `timestamp`, `level`, `logger`, `message` (or `event`), `mission_id`, + extra kwargs
- Configure via `DictConfig` or replace existing RichHandler for structured output

### Span Context Manager

```python
@contextmanager
def span_ctx(stage: str, mission_id: str, **extra_meta):
    start = time.perf_counter()
    logger.info(json_event("span_start", stage=stage, mission_id=mission_id, **extra_meta))
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(json_event("span_end", stage=stage, mission_id=mission_id,
                               duration_ms=duration_ms, **extra_meta))
```

### Instrumentation Points

1. `system_manager.learn()` — wraps full pipeline
2. Frontier dispatch — `frontier.py` search/discovery
3. Condensation — pipeline processing
4. Retrieval — `v3_retriever.retrieve_many()` or equivalent
5. Synthesis — `SynthesisService.generate_master_brief()` parallel block
6. Storage — section/citation persistence

### Verification Approach

- Run a mission with logging enabled
- Read `logs/metrics.jsonl`
- Filter by `mission_id`
- Verify 6 `span_start` + 6 `span_end` events present
- Verify `duration_ms` values sum approximately to total mission time

---

</specifics>

<deferred>

## Deferred Ideas

- OBS-03: HTTP API endpoints (`/api/v1/missions/{id}/timeline`, `/metrics`, `/retrieval`)
- OBS-04: Grafana/HTML dashboard
- Prometheus/Statsd metrics export
- `sheppard timeline <mission_id>` CLI command
- Log rotation / archival strategy
- Multi-endpoint comparison metrics

---

</deferred>

---

*Phase: 12-04 — Structured metrics & tracing*
*Context gathered: 2026-03-31 via direct user decisions*
