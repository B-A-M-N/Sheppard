# Phase 12-04 Summary: Structured metrics & tracing

**Status:** ✅ Completed
**Date:** 2026-03-31

## Deliverables

### New file created:
- `src/utils/structured_logger.py` — JSONFormatter, span_ctx, async_span_ctx, emit_event, setup_json_file_handler

### Files modified:
- `src/config/logging.py` — Integrated setup_json_file_handler() into setup_logging()
- `src/utils/__init__.py` — Exported structured logger module
- `src/research/reasoning/assembler.py` — Retrieval wrapped in async_span_ctx("retrieval", mission_id)
- `src/research/reasoning/synthesis_service.py` — Replaced 12-03 string-format logger.info with emit_event("synthesis_complete", ...)
- `src/core/system.py` — _crawl_and_store wrapped with async_span_ctx("frontier_acquisition_condensation", ...)
- `scripts/benchmark_suite.py` — setup_json_file_handler() called at startup; parallel LLM loop retained (12-03)

## Verification

| Check | Result |
|-------|--------|
| All JSON valid | ✅ |
| mission_id in every event | ✅ (4/4, 0 missing) |
| span_start/span_end pairs | ✅ (2 stages: frontier_acquisition_condensation, retrieval) |
| duration_ms captured | ✅ (55240ms, 251ms, 6782ms, 419ms) |
| Guardrail tests | ✅ 99 passed |

## OBS-01: Structured logs
- ✅ All pipeline events emit structured JSON via JSONFormatter
- ✅ Required fields: timestamp (ISO 8601), level, mission_id, stage, event
- ✅ Optional fields: duration_ms, sections_per_minute, llm_total_ms, validator_total_ms, topic

## OBS-02: Distributed tracing
- ✅ mission_id used as global correlation key (no separate trace_id)
- ✅ Span boundaries: span_start + span_end for each instrumented stage
- ✅ Duration measured via time.perf_counter()
- ✅ Nested spans work correctly (retrieval inside frontier_acquisition_condensation)

## Instrumentation Coverage
- ✅ frontier_acquisition_condensation — system.py _crawl_and_store
- ✅ retrieval — assembler.py assemble_all_sections
- ✅ synthesis — synthesis_service.py via emit_event (production path only)
- Storage — benchmark suite handles storage inline; production path through adapter.store_synthesis_*

## Design Decisions
- mission_id = trace_id (no second trace_id)
- JSON logs only (no Prometheus/Statsd)
- Built-in logging with custom JSONFormatter (no structlog/opentelemetry)
- File-based output (logs/metrics.jsonl)
- No HTTP server or API endpoints (deferred)
- CLI-native observability

## Notes
- Span events confirmed in logs/metrics.jsonl with correct nesting and timing
- synthesis span fires via emit_event in generate_master_brief (production path)
- Benchmark exercises inline synthesis loop (not generate_master_brief), so no synthesis_complete events appear in benchmark output — production codepath verified via unit test
