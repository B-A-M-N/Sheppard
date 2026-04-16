"""
routes/logs.py — WebSocket log streaming endpoint.

WS /api/ws/logs  — streams JSON log records to the client in real time.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.web.log_broadcaster import log_broadcaster

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    await websocket.accept()
    q = log_broadcaster.subscribe()
    try:
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=30)
                await websocket.send_text(payload)
            except asyncio.TimeoutError:
                # Send a keepalive ping so the connection stays alive
                await websocket.send_text('{"ping":true}')
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("[logs ws] disconnected: %s", e)
    finally:
        log_broadcaster.unsubscribe(q)
