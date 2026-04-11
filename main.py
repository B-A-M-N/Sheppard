#!/usr/bin/env python3
"""
main.py — Sheppard V3 Entry Point (3-Pane TUI)

┌──────────────┬─────────────────────────────────────────────┐
│  MENU        │              CHAT                           │
│  Status      │              History + Input                │
│  Missions    │                                             │
├──────────────┴─────────────────────────────────────────────┤
│                    LOGS (streaming)                         │
└─────────────────────────────────────────────────────────────┘
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
from collections import deque
from datetime import datetime
from pathlib import Path

import nest_asyncio
from prompt_toolkit import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout import (
    HSplit, VSplit, Window, Layout,
    WindowAlign, ConditionalMargin, NumberedMargin,
    ScrollablePane,
)
from prompt_toolkit.layout.controls import (
    BufferControl, FormattedTextControl,
)
from prompt_toolkit.layout.dimension import LayoutDimension as D
from prompt_toolkit.layout.processors import PasswordProcessor
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.key_binding import KeyBindings

# Ensure src/ is on the Python path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.core.system import system_manager
from src.core.chat import ChatApp
from src.core.commands import CommandHandler
from src.config.settings import settings
from src.utils.console import console

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# 3-Pane TUI Buffers
# ──────────────────────────────────────────────────────────────

LOG_MAX_LINES = 500

class TUI:
    """3-pane terminal UI: Menu | Chat | Logs"""

    def __init__(self):
        # Chat buffers
        self.chat_history = TextArea(
            text="",
            read_only=True,
            wrap_lines=True,
            focusable=False,
            style="class:chat-history",
        )
        self.chat_input = TextArea(
            multiline=False,
            prompt="[Sheppard] > ",
            style="class:chat-input",
            focus_on_input=True,
        )

        # Log buffer (scrolling, read-only, auto-scroll)
        self._log_lines = deque(maxlen=LOG_MAX_LINES)
        self.log_area = TextArea(
            text="",
            read_only=True,
            wrap_lines=True,
            focusable=False,
            style="class:log-area",
        )

        # Menu/status buffer
        self._menu_lines = []
        self.menu_area = TextArea(
            text="",
            read_only=True,
            wrap_lines=True,
            focusable=False,
            style="class:menu-area",
        )

        # Status bar
        self.status_text = "Initializing..."

        # Build layout
        self.layout = self._build_layout()
        self.kb = self._build_keybindings()
        self.app = None

    def _build_layout(self):
        """3-pane layout: Menu (left 25%) | Chat (center 75%) over Logs (bottom 8 lines)"""
        # Left panel: Menu/Status (width=25%)
        menu_panel = VSplit([
            Window(
                content=BufferControl(buffer=self.menu_area.buffer),
                width=D(preferred=28, max=35),
                style="class:menu-panel",
            ),
        ])

        # Center panel: Chat history + input
        chat_panel = VSplit([
            Window(
                content=BufferControl(buffer=self.chat_history.buffer),
                wrap_lines=True,
                style="class:chat-history",
            ),
            Window(height=1, char="\u2500", style="class:separator"),
            Window(
                content=BufferControl(buffer=self.chat_input.buffer),
                height=1,
                style="class:chat-input",
            ),
        ])

        # Bottom panel: Streaming logs (height=8 lines)
        log_panel = Window(
            content=BufferControl(buffer=self.log_area.buffer),
            height=D(preferred=10, max=15),
            wrap_lines=True,
            style="class:log-panel",
            dont_extend_height=True,
        )

        return Layout(
            HSplit([
                # Top: Menu | Chat
                VSplit([
                    menu_panel,
                    Window(width=1, char="\u2502", style="class:separator"),
                    chat_panel,
                ]),
                # Separator
                Window(height=1, char="\u2500", style="class:separator"),
                # Bottom: Logs
                log_panel,
            ])
        )

    def _build_keybindings(self):
        kb = KeyBindings()

        @kb.add("c-c")
        def _(event):
            event.app.exit(result="exit")

        @kb.add("enter", filter=lambda: get_app().layout.has_focus(self.chat_input.buffer))
        def _(event):
            text = self.chat_input.buffer.text.strip()
            if text:
                self.chat_input.buffer.text = ""
                self._on_input(text)
            return None

        return kb

    def set_on_input(self, callback):
        self._on_input = callback

    def append_chat(self, text: str, prefix: str = ""):
        """Add text to chat history."""
        if prefix:
            text = f"{prefix}{text}"
        current = self.chat_history.text
        self.chat_history.text = current + ("\n" if current else "") + text
        # Auto-scroll: move cursor to end
        self.chat_history.buffer.cursor_position = len(self.chat_history.buffer.text)

    def append_log(self, text: str):
        """Add a line to the log panel."""
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {text}"
        self._log_lines.append(line)
        self.log_area.text = "\n".join(self._log_lines)
        self.log_area.buffer.cursor_position = len(self.log_area.buffer.text)

    def update_menu(self, lines: list[str]):
        """Update the menu/status panel."""
        self.menu_area.text = "\n".join(lines)

    def set_status(self, text: str):
        self.status_text = text


def log_handler_factory(tui: TUI):
    """Create a logging handler that writes to the TUI log panel."""
    class TUIHandler(logging.Handler):
        def emit(self, record):
            try:
                msg = self.format(record)
                # Filter out noisy messages
                skip_prefixes = [
                    "urllib3",
                    "httpx",
                    "chromadb",
                ]
                if any(record.name.startswith(p) for p in skip_prefixes):
                    return
                tui.append_log(msg)
            except Exception:
                self.handleError(record)
    return TUIHandler()


def create_directory_structure(base_dir: Path):
    dirs = ['data/raw_docs', 'logs', 'screenshots', 'temp', 'chroma_storage', 'chat_history']
    for d in dirs:
        (base_dir / d).mkdir(parents=True, exist_ok=True)


async def run_tui(tui: TUI):
    """Main 3-pane TUI loop."""
    command_handler = None
    chat_app = None

    def on_chat_input(text: str):
        """Handle user input from chat pane."""
        nonlocal command_handler, chat_app
        if not text:
            return

        tui.append_chat(text, prefix="User: ")

        if text.lower() in {"exit", "quit", "bye"}:
            get_app().exit(result="exit")
            return

        if text.startswith("/"):
            if command_handler:
                # Run command in background so UI doesn't freeze
                asyncio.create_task(_handle_command(command_handler, text, tui))
            return

        # Normal chat
        if chat_app:
            asyncio.create_task(_process_chat(chat_app, text, tui))

    tui.set_on_input(on_chat_input)

    # Initialize system
    tui.append_log("Initializing Sheppard...")
    tui.update_menu([
        "╔══════════════════════╗",
        "║   SHEPPARD v1.3      ║",
        "║                      ║",
        "║  Initializing...     ║",
        "╚══════════════════════╝",
    ])

    create_directory_structure(Path(__file__).parent)

    try:
        success, error = await system_manager.initialize()
        if not success:
            tui.append_log(f"FATAL: {error}")
            tui.update_menu([
                "╔══════════════════════╗",
                "║   SHEPPARD v1.3      ║",
                "║                      ║",
                "║  INIT FAILED         ║",
                f"║  {error[:18]:<20}║",
                "╚══════════════════════╝",
            ])
            return

        chat_app = ChatApp()
        await chat_app.initialize(system_manager=system_manager)
        command_handler = CommandHandler(console=console, chat_app=chat_app)

        tui.append_log("System initialized.")
        tui.update_menu([
            "╔══════════════════════╗",
            "║   SHEPPARD v1.3      ║",
            "║                      ║",
            "║  Status: Online      ║",
            "║  /help  for commands║",
            "║  /learn  start topic║",
            "╚══════════════════════╝",
        ])

        # Start log streamer from logging
        tui_handler = log_handler_factory(tui)
        tui_handler.setLevel(logging.INFO)
        tui_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        logging.getLogger().addHandler(tui_handler)

        # Start mission status updater
        asyncio.create_task(_update_menu_status(tui))

    except Exception as e:
        tui.append_log(f"Init error: {e}")
        tui.append_log(traceback.format_exc())

    # Build prompt_toolkit Application
    style = Style.from_dict({
        "menu-panel": "#1a1a2e bg:#16213e",
        "menu-area": "#e0e0e0 bg:#16213e",
        "chat-history": "#e0e0e0 bg:#0f0f23",
        "chat-input": "#4caf50 bg:#0a0a1a bold",
        "log-panel": "#888 bg:#0a0a1a",
        "log-area": "#888 bg:#0a0a1a",
        "separator": "#333",
    })

    app = Application(
        layout=tui.layout,
        key_bindings=tui.kb,
        full_screen=True,
        style=style,
        mouse_support=False,
    )

    # Focus the chat input
    tui.layout.focus(tui.chat_input.buffer)

    result = await app.run_async_asyncio()
    if result == "exit":
        await system_manager.cleanup()


async def _handle_command(command_handler, text: str, tui: TUI):
    """Handle a command and write output to chat."""
    try:
        tui.append_chat(f"[Running: {text}]")
        await command_handler.handle_command(text)
    except Exception as e:
        tui.append_chat(f"[Error: {e}]", prefix="")
        tui.append_log(f"Command error: {e}")


async def _process_chat(chat_app: ChatApp, text: str, tui: TUI):
    """Process a chat message and stream response."""
    try:
        tui.append_chat("Sheppard: ", prefix="")
        async for response in chat_app.process_input(text):
            if response and response.content:
                tui.append_chat(response.content)
    except Exception as e:
        tui.append_chat(f"[Error: {e}]")
        tui.append_log(f"Chat error: {e}")


async def _update_menu_status(tui: TUI):
    """Periodically update menu with mission status."""
    while True:
        try:
            status = system_manager.status()
            missions = status.get("missions", {})
            lines = [
                "╔══════════════════════╗",
                "║   SHEPPARD v1.3      ║",
                "╠══════════════════════╣",
            ]
            if missions:
                for mid, info in list(missions.items())[:3]:
                    name = info.get("name", "Unknown")[:16]
                    usage = info.get("usage", "?")
                    crawling = "🟢" if info.get("crawling") else "⏳"
                    lines.append(f"║ {crawling} {name:<12} {usage:>4} ║")
            else:
                lines.append("║  No active missions  ║")
                lines.append("║                      ║")
                lines.append("║  /learn <topic>      ║")
            lines.append("╠══════════════════════╣")
            models = status.get("models", "")
            if models:
                lines.append(f"║  {str(models)[:20]:<20}║")
            lines.append("╚══════════════════════╝")

            tui.update_menu(lines)
        except Exception:
            pass
        await asyncio.sleep(3)


async def async_main():
    nest_asyncio.apply()
    tui = TUI()
    try:
        await run_tui(tui)
    finally:
        await system_manager.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"Fatal Error: {e}")
        traceback.print_exc()
        sys.exit(1)
