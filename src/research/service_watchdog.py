"""
src/research/service_watchdog.py — Research stack health checker and auto-starter.

Called once during SystemManager.initialize() to ensure SearXNG, Playwright, and
Firecrawl are reachable. If any service is down it launches it and waits for it
to come up before returning. Never raises — logs warnings and continues so a
partial outage doesn't block the whole boot.
"""

import asyncio
import logging
import os
import socket
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Service definitions ────────────────────────────────────────────────────────

SHEPPARD_DIR = Path(__file__).parents[2]
FIRECRAWL_DIR = Path("/home/bamn/firecrawl-local")
SEARXNG_DIR = Path("/home/bamn/Progeny/ai-companion/searxng_server")
LOG_DIR = SHEPPARD_DIR / "logs"

SERVICES = [
    {
        "name": "SearXNG",
        "port": 8080,
        "startup_timeout": 30,
        "launch": lambda: _launch_searxng(),
    },
    {
        "name": "Playwright",
        "port": 3003,
        "startup_timeout": 20,
        "launch": lambda: _launch_playwright(),
    },
    {
        "name": "Firecrawl",
        "port": 3002,
        "startup_timeout": 20,
        "launch": lambda: _launch_firecrawl(),
    },
]

# ── Port helpers ───────────────────────────────────────────────────────────────

def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if something is listening on host:port."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except (ConnectionRefusedError, OSError):
        return False


async def _wait_for_port(port: int, timeout: int) -> bool:
    """Poll until port is open or timeout (seconds) elapses. Returns True on success."""
    elapsed = 0
    interval = 2
    while elapsed < timeout:
        if _port_open(port):
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return False


# ── Per-service launchers ──────────────────────────────────────────────────────

def _popen(cmd: list[str], cwd: str, env: dict | None = None) -> subprocess.Popen:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    full_env = {**os.environ, **(env or {})}
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        env=full_env,
        stdout=open(LOG_DIR / f"{cmd[-1].replace('/', '_')}.log", "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _launch_searxng() -> None:
    python_bin = str(SEARXNG_DIR / "venv" / "bin" / "python")
    _popen(
        [python_bin, "searx/webapp.py"],
        cwd=str(SEARXNG_DIR),
        env={
            "SEARXNG_SETTINGS_PATH": str(SEARXNG_DIR / "settings.yml"),
            "SEARXNG_SECRET": "sheppard_secret",
            "PORT": "8080",
        },
    )


def _launch_playwright() -> None:
    _popen(
        ["node", "dist/api.js"],
        cwd=str(FIRECRAWL_DIR / "apps" / "playwright-service-ts"),
        env={
            "REDIS_URL": "redis://127.0.0.1:6379",
            "PORT": "3003",
            "NODE_ENV": "production",
        },
    )


def _launch_firecrawl() -> None:
    _popen(
        ["node", "dist/src/index.js"],
        cwd=str(FIRECRAWL_DIR / "apps" / "api"),
        env={
            "REDIS_URL": "redis://127.0.0.1:6379",
            "REDIS_RATE_LIMIT_URL": "redis://127.0.0.1:6379",
            "PLAYWRIGHT_MICROSERVICE_URL": "http://127.0.0.1:3003/scrape",
            "USE_DB_AUTHENTICATION": "false",
            "PORT": "3002",
            "HOST": "0.0.0.0",
            "SEARXNG_ENDPOINT": "http://127.0.0.1:8080",
        },
    )


# ── Public API ─────────────────────────────────────────────────────────────────

async def ensure_research_stack() -> None:
    """
    Check each required service. If a service is down, start it and wait.
    Runs at system boot — must never raise.
    """
    for svc in SERVICES:
        name = svc["name"]
        port = svc["port"]
        timeout = svc["startup_timeout"]

        if _port_open(port):
            logger.debug("[Watchdog] %s already up on port %d", name, port)
            continue

        logger.warning("[Watchdog] %s not running on port %d — starting it...", name, port)
        try:
            svc["launch"]()
            ok = await _wait_for_port(port, timeout)
            if ok:
                logger.info("[Watchdog] %s started successfully on port %d", name, port)
            else:
                logger.error(
                    "[Watchdog] %s failed to start within %ds — research may be degraded",
                    name, timeout,
                )
        except Exception as exc:
            logger.error("[Watchdog] Error starting %s: %s", name, exc)
