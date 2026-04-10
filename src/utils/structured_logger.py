"""
Structured logging utilities for Phase 12-04: Structured metrics & tracing.

Provides JSON-formatted log output, span-based tracing, and event emission
for observability without external infrastructure.
"""

import json
import logging
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path

# Metrics logger - writes to logs/metrics.jsonl
_metrics_logger = logging.getLogger("sheppard.metrics")


class JSONFormatter(logging.Formatter):
    """Format log records as JSON lines for structured observability."""

    def __init__(self, **defaults):
        super().__init__()
        self._defaults = defaults

    def format(self, record: logging.LogRecord) -> str:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "mission_id": getattr(record, "mission_id", ""),
            "stage": getattr(record, "stage", self._defaults.get("stage", "")),
            "event": getattr(record, "event", record.getMessage()),
            "message": record.getMessage(),
        }
        if hasattr(record, "duration_ms"):
            event["duration_ms"] = record.duration_ms
        for key in (
            "sections_per_minute",
            "sections_count",
            "llm_total_ms",
            "validator_total_ms",
            "retrieval_ms",
            "atom_count",
            "error",
            "topic",
        ):
            val = getattr(record, key, None)
            if val is not None:
                event[key] = val
        return json.dumps(event, default=str)


def setup_json_file_handler(log_path: str = "logs/metrics.jsonl"):
    """Configure a FileHandler for structured JSON metrics output."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path)
    handler.setFormatter(JSONFormatter())
    handler.setLevel(logging.INFO)
    _metrics_logger.addHandler(handler)
    _metrics_logger.setLevel(logging.INFO)


def emit_event(event: str, mission_id: str, stage: str = "", **extra_fields):
    """Emit a structured event to the metrics logger."""
    extra = {"mission_id": mission_id, "stage": stage, "event": event}
    extra.update(extra_fields)
    _metrics_logger.info(event, extra=extra)


@contextmanager
def span_ctx(stage: str, mission_id: str, **extra_meta):
    """Sync context manager that emits span_start and span_end events."""
    start = time.perf_counter()
    emit_event("span_start", mission_id=mission_id, stage=stage, **extra_meta)
    try:
        yield
    except Exception as e:
        emit_event(
            "span_error",
            mission_id=mission_id,
            stage=stage,
            error=str(type(e).__name__),
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        raise
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        emit_event("span_end", mission_id=mission_id, stage=stage, duration_ms=duration_ms, **extra_meta)


@asynccontextmanager
async def async_span_ctx(stage: str, mission_id: str, **extra_meta):
    """Async context manager that emits span_start and span_end events."""
    start = time.perf_counter()
    emit_event("span_start", mission_id=mission_id, stage=stage, **extra_meta)
    try:
        yield
    except Exception as e:
        emit_event(
            "span_error",
            mission_id=mission_id,
            stage=stage,
            error=str(type(e).__name__),
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        raise
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        emit_event("span_end", mission_id=mission_id, stage=stage, duration_ms=duration_ms, **extra_meta)
