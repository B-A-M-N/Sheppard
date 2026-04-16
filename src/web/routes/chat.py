"""
routes/chat.py — Chat and /analyze WebSocket endpoints.

WS /api/ws/chat    — streaming conversational chat
WS /api/ws/analyze — streaming analysis (problem framing → analyst → critic)
"""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.core.system import system_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """Stream conversational chat tokens to the client."""
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            messages = data.get("messages", [])
            if not messages:
                continue

            await websocket.send_text(json.dumps({"type": "start"}))
            try:
                async for token in system_manager.chat(messages=messages):
                    await websocket.send_text(json.dumps({"type": "token", "text": token}))
            except Exception as e:
                logger.error("[ws/chat] error: %s", e)
                await websocket.send_text(json.dumps({"type": "error", "text": str(e)}))
            await websocket.send_text(json.dumps({"type": "done"}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("[ws/chat] disconnected: %s", e)


@router.websocket("/ws/analyze")
async def ws_analyze(websocket: WebSocket):
    """Stream analysis pipeline progress + result."""
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            problem = data.get("problem", "").strip()
            mission_filter = data.get("mission_filter") or None
            topic_filter = data.get("topic_filter") or None

            if not problem:
                continue

            await websocket.send_text(json.dumps({"type": "start"}))
            try:
                async for chunk in system_manager.analyze_stream(
                    problem_statement=problem,
                    mission_filter=mission_filter,
                    topic_filter=topic_filter,
                ):
                    await websocket.send_text(json.dumps({"type": "chunk", "text": chunk}))
            except Exception as e:
                logger.error("[ws/analyze] error: %s", e)
                await websocket.send_text(json.dumps({"type": "error", "text": str(e)}))
            await websocket.send_text(json.dumps({"type": "done"}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("[ws/analyze] disconnected: %s", e)
