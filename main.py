#!/usr/bin/env python3
"""
main.py — Sheppard V2 Entry Point (Restored & Enhanced)

Handles full initialization with progress bars and the rich interactive loop.
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
from rich.progress import Progress, SpinnerColumn, TextColumn

# Sheppard V2 Core
from src.core.system import system_manager
from src.core.chat import ChatApp
from src.core.commands import CommandHandler
from src.config.settings import settings
from src.utils.console import console

logger = logging.getLogger(__name__)

def create_directory_structure(base_dir: Path):
    """Restore original directory creation logic."""
    dirs = ['data/raw_docs', 'logs', 'screenshots', 'temp', 'chroma_storage', 'chat_history']
    for d in dirs:
        (base_dir / d).mkdir(parents=True, exist_ok=True)

async def initialize_components(base_dir: Path):
    """Restore original rich progress bar initialization."""
    create_directory_structure(base_dir)
    console.print("Initializing system components...")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Initializing system components...", total=100)
        
        # 1. Boot System Manager (Acquisitions, Condensation, Memory, Reasoning)
        success, error = await system_manager.initialize()
        if not success:
            raise RuntimeError(f"Engine ignition failed: {error}")
        progress.update(task, advance=70)

        # 2. Boot Chat Interface
        chat_app = ChatApp()
        await chat_app.initialize(system_manager=system_manager)
        progress.update(task, advance=30)
        
        return chat_app

async def run_chat(chat_app: ChatApp):
    """Restore original rich interactive loop."""
    command_handler = CommandHandler(console=console, chat_app=chat_app)
    command_handler.show_welcome()

    while True:
        try:
            console.print("\nYou: ", end="", style="green")
            # Use to_thread to prevent blocking the event loop
            user_input = await asyncio.to_thread(input)
            user_input = user_input.strip()

            if not user_input: continue
            if user_input.lower() in {"exit", "quit", "bye"}: break

            if user_input.startswith("/"):
                await command_handler.handle_command(user_input)
                continue

            # Original rich panel display for user
            console.print(Panel(user_input, title="User", border_style="green"))
            
            # Streaming response
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
