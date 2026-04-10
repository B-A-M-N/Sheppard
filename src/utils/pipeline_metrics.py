"""
Pipeline metrics collector.
Emits to both Postgres (queryable) and structured JSON logs (observability).
Batch-flushes to avoid per-metric INSERT overhead.
"""
import json
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)

FLUSH_INTERVAL = 60  # seconds
FLUSH_THRESHOLD = 50  # rows


class MetricsCollector:
    def __init__(self, pg_adapter=None):
        self.pg = pg_adapter
        self._buffer = deque()
        self._last_flush = time.time()

    def record(self, run_id: str, metric_name: str, value: float, labels: dict = None):
        """Buffer a metric for batch flush."""
        self._buffer.append({
            "run_id": run_id,
            "metric_name": metric_name,
            "metric_value": value,
            "labels": json.dumps(labels or {}),
        })

        # Also emit as structured log
        logger.info(json.dumps({
            "event": "pipeline_metric",
            "metric_name": metric_name,
            "metric_value": value,
            "run_id": run_id,
            "labels": labels or {},
        }))

        # Auto-flush if threshold reached
        if len(self._buffer) >= FLUSH_THRESHOLD:
            self.flush()

    def flush(self):
        """Write buffered metrics to Postgres."""
        if not self._buffer or not self.pg:
            return
        rows = list(self._buffer)
        try:
            self.pg.bulk_insert("audit.pipeline_metrics", rows)
            self._buffer.clear()
            self._last_flush = time.time()
        except Exception as e:
            logger.error(f"[Metrics] Bulk insert failed: {e}")
