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

# ──────────────────────────────────────────────────────────────
# MUST run before ANY imports: suppress ANSI from ALL libs
# ──────────────────────────────────────────────────────────────
import os
os.environ.setdefault("NO_COLOR", "1")  # Rich respects this globally
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
del os

# ──────────────────────────────────────────────────────────────
# KILL ALL STDOUT HANDLERS BEFORE any project imports
# This prevents ANSI/ANSI-like leakage from RichHandler/StreamHandler
# ──────────────────────────────────────────────────────────────
import logging as _logging
_root = _logging.getLogger()
_h = None
for _h in _root.handlers[:]:
    if not isinstance(_h, _logging.FileHandler):
        _root.removeHandler(_h)
        _h.close()
del _h
# Prevent basicConfig from re-adding stdout handlers
_logging.basicConfig = lambda *a, **k: None
# Set root to CRITICAL to suppress any stray log messages during imports
_root.setLevel(_logging.CRITICAL)
del _logging, _root

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
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout import (
    HSplit, VSplit, Window, Layout,
)
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.dimension import LayoutDimension as D
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout

import re


# ──────────────────────────────────────────────────────────────
# TUI-safe console wrapper: intercepts Rich output and routes to log panel
# ──────────────────────────────────────────────────────────────
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return _ANSI_RE.sub('', text)

# Ensure src/ is on the Python path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.core.system import system_manager
from src.core.chat import ChatApp
from src.core.commands import CommandHandler
from src.config.settings import settings

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
            focusable=True,
            style="class:chat-history",
        )
        self.chat_input = TextArea(
            multiline=False,
            prompt="[Sheppard] > ",
            style="class:chat-input",
        )

        # Log buffer (scrolling, read-only, auto-scroll)
        self._log_lines = deque(maxlen=LOG_MAX_LINES)
        self.log_area = TextArea(
            text="",
            read_only=True,
            wrap_lines=True,
            focusable=True,
            style="class:log-area",
        )

        # Menu/status buffer
        self._menu_lines = []
        self.menu_area = TextArea(
            text="",
            read_only=True,
            wrap_lines=True,
            focusable=True,
            style="class:menu-area",
        )

        # Status bar
        self.status_text = "Initializing..."

        # Build layout
        self.layout = self._build_layout()
        self.kb = self._build_keybindings()
        self.app = None

    def _build_layout(self):
        """3-pane layout: Menu (left 28) | Chat (rest) over Logs (bottom 10)"""
        # Left panel: Menu/Status (fixed width)
        menu_panel = Window(
            content=BufferControl(buffer=self.menu_area.buffer),
            width=D(preferred=28, max=28),
            style="class:menu-panel",
            dont_extend_width=True,
        )

        # Center panel: Chat history + input
        chat_panel = HSplit([
            Window(
                content=BufferControl(buffer=self.chat_history.buffer),
                wrap_lines=True,
                style="class:chat-history",
            ),
            Window(height=1, char="\u2500", style="class:separator"),
            Window(
                content=BufferControl(buffer=self.chat_input.buffer),
                height=1,
                style="class:chat-input-area",
            ),
        ])

        # Bottom panel: Streaming logs (fixed height, scrollable via keyboard)
        log_panel = Window(
            content=BufferControl(buffer=self.log_area.buffer),
            height=D(preferred=10, max=10),
            wrap_lines=True,
            style="class:log-panel",
        )

        return Layout(
            HSplit([
                # Top: Menu | Chat side-by-side
                VSplit([
                    menu_panel,
                    Window(width=1, char="\u2502", style="class:separator"),
                    chat_panel,
                ], height=D(weight=1)),
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

        @kb.add("tab")
        def _(event):
            # Cycle: chat_input -> chat_history -> log_area -> menu -> chat_input
            current = event.app.layout.current_buffer
            if current is self.chat_input.buffer:
                event.app.layout.focus(self.chat_history.buffer)
            elif current is self.chat_history.buffer:
                event.app.layout.focus(self.log_area.buffer)
            elif current is self.log_area.buffer:
                event.app.layout.focus(self.menu_area.buffer)
            else:
                event.app.layout.focus(self.chat_input.buffer)

        @kb.add("s-tab")
        def _(event):
            # Reverse cycle
            current = event.app.layout.current_buffer
            if current is self.chat_input.buffer:
                event.app.layout.focus(self.menu_area.buffer)
            elif current is self.menu_area.buffer:
                event.app.layout.focus(self.log_area.buffer)
            elif current is self.log_area.buffer:
                event.app.layout.focus(self.chat_history.buffer)
            else:
                event.app.layout.focus(self.chat_input.buffer)

        @kb.add("up")
        @kb.add("c-up")
        def _(event):
            buf = event.app.layout.current_buffer
            if buf is not self.chat_input.buffer and buf is not None:
                try:
                    buf.cursor_up()
                except Exception:
                    pass

        @kb.add("down")
        @kb.add("c-down")
        def _(event):
            buf = event.app.layout.current_buffer
            if buf is not self.chat_input.buffer and buf is not None:
                try:
                    buf.cursor_down()
                except Exception:
                    pass

        @kb.add("pageup")
        def _(event):
            buf = event.app.layout.current_buffer
            if buf is not self.chat_input.buffer and buf is not None:
                try:
                    buf.cursor_up(count=15)
                except Exception:
                    pass

        @kb.add("pagedown")
        def _(event):
            buf = event.app.layout.current_buffer
            if buf is not self.chat_input.buffer and buf is not None:
                try:
                    buf.cursor_down(count=15)
                except Exception:
                    pass

        @kb.add("enter")
        def _(event):
            # Only handle Enter when chat input is focused
            focused = event.app.layout.current_buffer
            if focused is self.chat_input.buffer:
                text = self.chat_input.buffer.text.strip()
                if text:
                    self.chat_input.buffer.text = ""
                    if hasattr(self, "_on_input"):
                        self._on_input(text)
                return None
            # Let prompt_toolkit handle Enter for other buffers (scrolling etc)
            event.app.layout.current_buffer.newline()
            return None

        return kb

    def set_on_input(self, callback):
        self._on_input = callback

    def append_chat(self, text: str, prefix: str = "", flush: bool = True):
        """Add text to chat history. flush=True adds a newline (new message)."""
        if prefix:
            text = f"{prefix}{text}"
        current = self.chat_history.text
        if flush and current:
            self.chat_history.text = current + "\n" + text
        elif current:
            self.chat_history.text = current + text
        else:
            self.chat_history.text = text
        # Auto-scroll to bottom
        self.chat_history.buffer.cursor_position = len(self.chat_history.buffer.text)

    def append_log(self, text: str):
        """Add a line to the log panel."""
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {text}"
        self._log_lines.append(line)
        self.log_area.text = "\n".join(self._log_lines)
        # Auto-scroll to bottom
        self.log_area.buffer.cursor_position = len(self.log_area.buffer.text)

    def update_menu(self, lines: list[str]):
        """Update the menu/status panel."""
        self.menu_area.text = "\n".join(lines)

    def set_status(self, text: str):
        self.status_text = text


class TUIConsole:
    """Drop-in replacement for Rich Console that routes output to TUI chat panel."""
    def __init__(self, tui: TUI):
        self._tui = tui
        import io as _io
        from rich.console import Console as _RichConsole
        self._render_buf = _io.StringIO()
        self._silent_console = _RichConsole(
            file=self._render_buf,
            force_terminal=False,
            width=120,
            no_color=True,
        )

    def _render_to_text(self, *objects) -> str:
        """Render Rich objects to plain text."""
        from rich.text import Text
        
        parts = []
        for obj in objects:
            if isinstance(obj, str):
                # If it looks like Rich markup (contains brackets), try to render it
                if '[' in obj and ']' in obj:
                    try:
                        text = Text.from_markup(obj)
                        parts.append(text.plain)
                    except Exception:
                        # Fallback to raw string if markup fails
                        parts.append(obj)
                else:
                    parts.append(obj)
            else:
                # Use Rich console for complex objects (Tables, Panels)
                self._render_buf.seek(0)
                self._render_buf.truncate(0)
                self._silent_console.print(obj, soft_wrap=True)
                self._render_buf.seek(0)
                parts.append(self._render_buf.read().strip())
        
        return "\n".join(p for p in parts if p.strip()).strip()

    def print(self, *objects, **kwargs):
        """Route Rich output to TUI chat panel."""
        if not objects:
            return
        text = self._render_to_text(*objects)
        if text:
            for line in text.splitlines():
                line = line.strip()
                if line:
                    self._tui.append_chat(line, prefix="", flush=True)
        else:
            raw = ' '.join(str(o) for o in objects)
            if raw.strip():
                self._tui.append_chat(raw.strip(), prefix="", flush=True)

    def status(self, *args, **kwargs):
        class _DummyStatus:
            def __enter__(self): return self
            def __exit__(self, *a): pass
        return _DummyStatus()

    def clear(self):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


def _patch_global_console(tui: TUI):
    """Replace the global Rich console with a TUI-safe wrapper."""
    import src.utils.console as console_mod
    console_mod.console = TUIConsole(tui)


def _silence_ansi_logging():
    """Remove ALL RichHandler/StreamHandler from root logger to prevent ANSI leakage into TUI."""
    root_logger = logging.getLogger()
    # Remove any handlers that write to stdout (RichHandler, StreamHandler)
    handlers_to_keep = []
    for handler in root_logger.handlers:
        # Keep only file handlers
        if isinstance(handler, logging.FileHandler):
            handlers_to_keep.append(handler)
        else:
            handler.close()
    root_logger.handlers = handlers_to_keep
    # Keep root at INFO level so child handlers receive messages
    root_logger.setLevel(logging.INFO)


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
                # Filter noisy embedding messages
                if "safe_embed" in msg.lower() or "embedding" in msg.lower():
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

    # Patch the global Rich console BEFORE any subsystem uses it
    _patch_global_console(tui)

    # Silence ANSI logging handlers to prevent terminal corruption
    _silence_ansi_logging()

    # Add TUI logging handler early so init logs get captured
    tui_handler = log_handler_factory(tui)
    tui_handler.setLevel(logging.INFO)
    tui_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    logging.getLogger().addHandler(tui_handler)

    # Initialize system
    tui.append_log("Initializing Sheppard...")
    tui.update_menu([
        "\u250c" + "\u2500" * 22 + "\u2510",
        "\u2502   SHEPPARD v1.3      \u2502",
        "\u2502                      \u2502",
        "\u2502  Initializing...     \u2502",
        "\u2514" + "\u2500" * 22 + "\u2518",
    ])

    create_directory_structure(Path(__file__).parent)

    try:
        success, error = await system_manager.initialize()
        if not success:
            tui.append_log(f"FATAL: {error}")
            tui.update_menu([
                "\u250c" + "\u2500" * 22 + "\u2510",
                "\u2502   SHEPPARD v1.3      \u2502",
                "\u2502                      \u2502",
                "\u2502  INIT FAILED         \u2502",
                f"\u2502  {error[:18]:<20}\u2502",
                "\u2514" + "\u2500" * 22 + "\u2518",
            ])
            return

        chat_app = ChatApp()
        await chat_app.initialize(system_manager=system_manager)

        # Use the patched global console (TUI-safe, strips ANSI)
        import src.utils.console as console_mod
        command_handler = CommandHandler(console=console_mod.console, chat_app=chat_app)

        tui.append_log("System initialized.")
        tui.update_menu([
            "\u250c" + "\u2500" * 22 + "\u2510",
            "\u2502   SHEPPARD v1.3      \u2502",
            "\u2502                      \u2502",
            "\u2502  Status: Online      \u2502",
            "\u2502  /help  for commands \u2502",
            "\u2502  /learn  start topic \u2502",
            "\u2514" + "\u2500" * 22 + "\u2518",
        ])

        # Start mission status updater
        asyncio.create_task(_update_menu_status(tui))

    except Exception as e:
        tui.append_log(f"Init error: {e}")
        tui.append_log(traceback.format_exc())

    # Build prompt_toolkit Application
    style = Style.from_dict({
        # Black background everywhere
        "menu-panel": "bg:#000000",
        "menu-area": "#ffffff bg:#000000",
        "chat-history": "#ffffff bg:#000000",
        "chat-input-area": "#dc143c bg:#000000 bold",
        "log-panel": "bg:#000000",
        "log-area": "#888888 bg:#000000",
        "separator": "#dc143c",
    })

    app = Application(
        layout=tui.layout,
        key_bindings=tui.kb,
        full_screen=True,
        style=style,
        mouse_support=True,
    )

    from prompt_toolkit.patch_stdout import patch_stdout

    # Focus the chat input
    app.layout.focus(tui.chat_input.buffer)

    # patch_stdout() captures all print()/logging output and routes it
    # through prompt_toolkit's renderer instead of corrupting the terminal
    with patch_stdout():
        result = await app.run_async()
    if result == "exit":
        await system_manager.cleanup()


async def _handle_command(command_handler, text: str, tui: TUI):
    """Handle a command and write output to chat."""
    try:
        tui.append_chat(f"[Command: {text}]", prefix="", flush=True)
        # Pass TUI reference for direct buffer writes
        if hasattr(command_handler, 'handle_command_with_tui'):
            await command_handler.handle_command_with_tui(text, tui)
        else:
            # Fallback: inject _tui via kwargs for _handle_knowledge
            import src.core.commands as cmd_mod
            if text.lower().startswith('/knowledge') or text.lower().startswith('/kb'):
                await cmd_mod.CommandHandler._handle_knowledge(command_handler, _tui=tui)
            else:
                await command_handler.handle_command(text)
    except Exception as e:
        tui.append_chat(f"[Error: {e}]", prefix="", flush=True)
        tui.append_log(f"Command error: {e}")


async def _process_chat(chat_app: ChatApp, text: str, tui: TUI):
    """Process a chat message and stream response."""
    try:
        tui.append_chat("Sheppard: ", prefix="", flush=True)
        async for response in chat_app.process_input(text):
            if response and response.content:
                tui.append_chat(response.content, prefix="", flush=False)
        # Final newline after response is complete
        tui.append_chat("", prefix="", flush=True)
    except Exception as e:
        tui.append_chat(f"[Error: {e}]", prefix="", flush=True)
        tui.append_log(f"Chat error: {e}")


async def _update_menu_status(tui: TUI):
    """Periodically update menu with mission status."""
    while True:
        try:
            status = system_manager.status()
            missions = status.get("missions", {})
            lines = [
                "\u250c" + "\u2500" * 22 + "\u2510",
                "\u2502   SHEPPARD v1.3      \u2502",
                "\u251c" + "\u2500" * 22 + "\u2524",
            ]
            if missions:
                for mid, info in list(missions.items())[:3]:
                    name = info.get("name", "Unknown")[:16]
                    usage = info.get("usage", "?")
                    crawling = "\U0001f7e2" if info.get("crawling") else "\u23f3"
                    line = f"\u2502 {crawling} {name:<12} {str(usage):>4} \u2502"
                    # Pad or truncate to exact width
                    lines.append(line[:24].ljust(24) + "\u2502")
            else:
                lines.append("\u2502  No active missions  \u2502")
                lines.append("\u2502                      \u2502")
                lines.append("\u2502  /learn <topic>      \u2502")
            lines.append("\u251c" + "\u2500" * 22 + "\u2524")
            models = status.get("models", "")
            if models:
                # Format dict nicely
                if isinstance(models, dict):
                    model_str = ", ".join(f"{k}:{v}" for k, v in models.items())
                else:
                    model_str = str(models)
                model_display = f"  {model_str[:20]:<20}"
                lines.append(f"\u2502{model_display}\u2502")
            lines.append("\u251c" + "\u2500" * 22 + "\u2524")
            lines.append("\u2502 Tab: cycle focus  \u2502")
            lines.append("\u2502 PgUp/Dn: scroll   \u2502")
            lines.append("\u2514" + "\u2500" * 22 + "\u2518")

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
