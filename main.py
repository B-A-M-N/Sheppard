#!/usr/bin/env python3
"""
main.py — Sheppard V2 Entry Point (Non-Blocking UI Edition)

Uses a surgical UI update pattern to ensure typing is never interrupted.
"""

import asyncio
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

# Sheppard V2 Core
from src.core.system import system_manager
from src.core.chat import ChatApp
from src.core.commands import CommandHandler
from src.config.settings import settings
from src.utils.console import console

logger = logging.getLogger(__name__)

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
    Standard UI loop with a non-invasive background status ticker.
    """
    command_handler = CommandHandler(console=console, chat_app=chat_app)
    command_handler.show_welcome()

    async def status_ticker():
        """Silently update mission stats in terminal title or status line."""
        while True:
            status = system_manager.status()
            active = [info for info in status.get('missions', {}).values() if info['crawling']]
            if active:
                # Update terminal title with progress instead of drawing on screen
                mission_sum = " | ".join([f"{m['name'][:15]}: {m['usage']}" for m in active])
                sys.stdout.write(f"\x1b]2;Sheppard Missions: {mission_sum}\x07")
                sys.stdout.flush()
            await asyncio.sleep(5)

    # Start the ticker
    ticker_task = asyncio.create_task(status_ticker())

    while True:
        try:
            # Use a standard input prompt. This is 100% stable.
            user_input = await asyncio.to_thread(input, "\n[Sheppard] > ")
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
        except Exception as e:
            logger.error(f"Chat error: {e}")
            console.print(f"\n[bold red]Error:[/bold red] {e}")
    
    ticker_task.cancel()

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
