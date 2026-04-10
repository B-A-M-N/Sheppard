#!/usr/bin/env python3
"""
main.py — Sheppard V2 Entry Point (Non-Blocking UI Edition)

Uses a surgical UI update pattern to ensure typing is never interrupted.
"""

import faulthandler
faulthandler.enable()

import os as _main_os
_main_os.environ.setdefault("OMP_NUM_THREADS", "1")
_main_os.environ.setdefault("MKL_NUM_THREADS", "1")
_main_os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
_main_os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
_main_os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
del _main_os

import asyncio
import json
import logging
import sys
import os
import traceback
from pathlib import Path
from datetime import datetime

import nest_asyncio
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn
from rich.table import Table
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML

# Ensure src/ is on the Python path for absolute imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

# Sheppard V2 Core
from src.core.system import system_manager
from src.core.chat import ChatApp
from src.core.commands import CommandHandler
from src.config.settings import settings
from src.utils.console import console

logger = logging.getLogger(__name__)


class StatusBar:
    """Aggregates Redis pub/sub events into a renderable bottom toolbar."""

    def __init__(self):
        self._state: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def update(self, component: str, event: dict):
        async with self._lock:
            self._state[component] = event

    def render(self) -> HTML:
        try:
            if not self._state:
                return HTML("")
            parts = []
            for comp, ev in sorted(self._state.items()):
                event_type = ev.get("event", "?")
                data = ev.get("data", {})
                if event_type == "stats":
                    parts.append(f"<ansicyan>{comp}</ansicyan>: dq={data.get('dequeued',0)} sc={data.get('scraped',0)} fl={data.get('failed',0)}")
                elif event_type == "dispatch":
                    parts.append(f"<ansiyellow>{comp}</ansiyellow>: {data.get('node', '')}")
                elif event_type == "batch_complete":
                    parts.append(f"<ansigreen>{comp}</ansigreen>: {data.get('atoms', 0)} atoms")
                elif event_type == "mission_start":
                    parts.append(f"<ansimagenta>{comp}</ansimagenta>: {data.get('topic', '')[:20]}")
                else:
                    parts.append(f"<grey>{comp}: {event_type}</grey>")
            return HTML("  |  ".join(parts[:4]))
        except Exception:
            return HTML("")


async def status_subscriber(bar: StatusBar, redis_client):
    """Subscribe to sheppard:status and update the status bar."""
    import redis.asyncio as redis
    backoff = 1
    while True:
        try:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe("sheppard:status")
            backoff = 1
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    await bar.update(data["component"], data)
        except (ConnectionError, TimeoutError, redis.ConnectionError):
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"[StatusBar] Error: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

def create_directory_structure(base_dir: Path):
    dirs = ['data/raw_docs', 'logs', 'screenshots', 'temp', 'chroma_storage', 'chat_history']
    for d in dirs:
        (base_dir / d).mkdir(parents=True, exist_ok=True)

async def initialize_components(base_dir: Path):
    create_directory_structure(base_dir)
    console.print("[bold blue][System][/bold blue] Initializing Sheppard Infrastructure...")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Igniting engine components...", total=100)
        success, error = await system_manager.initialize()
        if not success:
            raise RuntimeError(f"Engine ignition failed: {error}")
        progress.update(task, advance=70)

        chat_app = ChatApp()
        await chat_app.initialize(system_manager=system_manager)
        progress.update(task, advance=30)
        
        return chat_app

async def run_chat(chat_app: ChatApp):
    """
    Chat loop with prompt_toolkit and background status bar.
    """
    command_handler = CommandHandler(console=console, chat_app=chat_app)
    command_handler.show_welcome()

    # Create status bar and start subscriber
    bar = StatusBar()
    redis_client = system_manager.redis_client
    sub_task = asyncio.create_task(status_subscriber(bar, redis_client))

    session = PromptSession(
        style=Style.from_dict({"prompt": "#4caf50 bold"}),
        bottom_toolbar=bar.render,
        refresh_interval=1.0,
    )

    while True:
        try:
            user_input = await session.prompt_async()
            user_input = user_input.strip()

            if not user_input: continue
            if user_input.lower() in {"exit", "quit", "bye"}: break

            if user_input.startswith("/"):
                await command_handler.handle_command(user_input)
                continue

            console.print(Panel(user_input, title="User", border_style="green"))
            console.print("[bold blue]Sheppard:[/bold blue] ", end="")
            async for response in chat_app.process_input(user_input):
                if response and response.content:
                    console.print(response.content, end="", highlight=False)
            console.print()

        except KeyboardInterrupt:
            break
        except EOFError:
            break
        except Exception as e:
            logger.error(f"Chat error: {e}")
            console.print(f"\n[bold red]Error:[/bold red] {e}")

    sub_task.cancel()
    try:
        await sub_task
    except asyncio.CancelledError:
        pass

async def async_main():
    nest_asyncio.apply()
    base_dir = Path(__file__).parent
    try:
        chat_app = await initialize_components(base_dir)
        await run_chat(chat_app)
    finally:
        await system_manager.cleanup()
        console.print("\n[dim]Sheppard offline.[/dim]")

if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]Fatal Error:[/bold red] {e}")
        traceback.print_exc()
        sys.exit(1)
