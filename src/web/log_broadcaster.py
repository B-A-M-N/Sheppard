"""
src/web/log_broadcaster.py

A logging handler that fans out log records to all connected WebSocket
clients on /api/ws/logs.

Thread-safe: _queues mutations are guarded by a threading.Lock, and
cross-thread puts use loop.call_soon_threadsafe() since asyncio.Queue
is not safe to call from outside the event loop.
"""

import asyncio
import json
import logging
import threading
from datetime import datetime
from typing import Set


class LogBroadcaster:
    """Singleton that holds all active log WebSocket queues."""

    def __init__(self):
        self._queues: Set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._installed = False

    def install(self):
        """Attach to the root logger. Call once at startup, from the lifespan."""
        if self._installed:
            return
        handler = _BroadcastHandler(self)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        root = logging.getLogger()
        root.addHandler(handler)
        # Root logger defaults to WARNING — INFO logs from the pipeline never reach any handler.
        # Set to INFO so the web UI actually shows what's happening.
        if root.level == logging.NOTSET or root.level > logging.INFO:
            root.setLevel(logging.INFO)
        self._installed = True

    def subscribe(self) -> asyncio.Queue:
        """Register a new WebSocket client. Must be called from the running event loop."""
        self._loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._lock:
            self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        with self._lock:
            self._queues.discard(q)

    def broadcast(self, record: logging.LogRecord):
        """Called from the logging handler — may be any thread."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        skip = ("urllib3", "httpx", "chromadb", "asyncio", "uvicorn.access")
        if any(record.name.startswith(s) for s in skip):
            return

        msg = {
            "ts": datetime.utcnow().strftime("%H:%M:%S"),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        payload = json.dumps(msg)

        with self._lock:
            queues = list(self._queues)

        def _put(q):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass  # drop message for slow clients

        for q in queues:
            try:
                loop.call_soon_threadsafe(_put, q)
            except RuntimeError:
                pass  # loop closed or stopped


class _BroadcastHandler(logging.Handler):
    def __init__(self, broadcaster: LogBroadcaster):
        super().__init__()
        self._bc = broadcaster

    def emit(self, record: logging.LogRecord):
        try:
            self._bc.broadcast(record)
        except Exception:
            self.handleError(record)


log_broadcaster = LogBroadcaster()
