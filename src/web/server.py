"""
src/web/server.py — Sheppard Web UI Server

FastAPI app. Initializes system_manager on startup, serves the SPA,
and mounts all API + WebSocket routes.
"""

import logging
import sys
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.system import system_manager
from src.core.chat import ChatApp
from src.web.log_broadcaster import log_broadcaster
from src.web.routes import chat, missions, knowledge, logs

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


async def _initialize_system_background(app: FastAPI) -> None:
    """Initialize the full backend stack without blocking ASGI startup."""
    logger.info("[Web] Initializing Sheppard system in background...")
    success, error = await system_manager.initialize()
    app.state.system_init_error = error
    if not success:
        logger.error("[Web] System init failed: %s", error)
        return

    chat_app = ChatApp()
    await chat_app.initialize(system_manager=system_manager)
    app.state.chat_app = chat_app
    logger.info("[Web] System ready.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize system on startup, clean up on shutdown."""
    log_broadcaster.install()
    app.state.chat_app = None
    app.state.system_init_error = None
    app.state.system_init_task = asyncio.create_task(_initialize_system_background(app))
    logger.info("[Web] Startup task scheduled; serving while backend initializes")

    yield

    logger.info("[Web] Shutting down...")
    init_task = getattr(app.state, "system_init_task", None)
    if init_task and not init_task.done():
        init_task.cancel()
    await system_manager.cleanup()


app = FastAPI(title="Sheppard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    """Force no-cache on all /static/* responses so edits are always picked up."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response


app.add_middleware(NoCacheStaticMiddleware)

# All routes — including WebSockets — live under /api
app.include_router(chat.router,      prefix="/api")
app.include_router(missions.router,  prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(logs.router,      prefix="/api")

# Serve static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
async def health():
    status = system_manager.status()
    total_missions = len(status.get("missions", {}))
    total_atoms = None
    if getattr(system_manager, "adapter", None) and getattr(system_manager.adapter, "pg", None):
        try:
            async with system_manager.adapter.pg.pool.acquire() as conn:
                total_missions = await conn.fetchval("SELECT COUNT(*) FROM mission.research_missions")
                total_atoms = await conn.fetchval("SELECT COUNT(*) FROM knowledge.knowledge_atoms")
        except Exception:
            pass
    return {
        "ok": status.get("initialized", False),
        "missions": total_missions,
        "runtime_missions": len(status.get("missions", {})),
        "atoms": total_atoms,
        "startup": status.get("startup", {}),
    }
