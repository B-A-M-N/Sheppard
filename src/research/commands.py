"""
Research command handling for the chat system.
File: src/research/commands.py
"""

import logging
import shlex
import asyncio
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live

from src.research.models import ResearchType
from src.research.exceptions import BrowserError, CommandError
from src.core.constants import STYLES, ERROR_MESSAGES
from src.utils.text_processing import sanitize_text
from src.research.processors import format_research_results
from src.utils.console import console

logger = logging.getLogger(__name__)

class ResearchCommands:
    """Handles research-specific commands."""

    def __init__(
        self,
        console: Console,
        research_system: Any,
        screenshot_dir: Optional[Path] = None
    ):
        """Initialize research commands."""
        self.console = console
        self.research_system = research_system
        self.screenshot_dir = screenshot_dir
        self.command_history: List[Dict[str, Any]] = []

    async def handle_command(
        self,
        command: str,
        *args,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle research command."""
        try:
            # Map commands to handlers
            handlers = {
                'research': self._handle_research,
                'browse': self._handle_browse,
                'screenshot': self._handle_screenshot,
                'save': self._handle_save,
                'status': self._handle_status,
                'help': self._handle_help
            }

            command = command.lower().strip()
            handler = handlers.get(command)
            if not handler:
                raise CommandError(f"Unknown command: {command}")

            return await handler(*args, metadata=metadata)

        except Exception as e:
            logger.error(f"Command handling failed: {str(e)}")
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

    async def _display_research_progress(self, task, progress, topic, research_fn, *args, **kwargs):
        """Display research progress with improved visual indicators."""
        # Define process steps with better indicators
        steps = [
            ("Initializing research", 0.05),
            ("Searching for sources", 0.15),
            ("Extracting content", 0.30),
            ("Analyzing information", 0.50),
            ("Processing insights", 0.70),
            ("Preparing results", 0.90)
        ]
        
        # Use rich's SpinnerColumn for better visualization
        spinner_column = SpinnerColumn('dots')
        
        # Initial task setup
        task = progress.add_task(
            description=f"[cyan]Researching: {topic}",
            total=100,
            start=True
        )
        
        # Function to update progress with current step
        def progress_callback(p):
            # Determine which step we're in based on progress
            step_idx = min(int(p * len(steps)), len(steps) - 1)
            step_desc, _ = steps[step_idx]
            
            # Update progress
            progress.update(task, completed=p * 100, description=f"[cyan]{step_desc}")
        
        # Run the research function with our progress callback
        result = await research_fn(*args, **kwargs, progress_callback=progress_callback)
        
        # Show completion
        progress.update(task, description="[green]Research completed", completed=100)
        
        return result

    async def _handle_research(self, *args, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Handle research command with enhanced output formatting."""
        if not args:
            self.console.print(
                ERROR_MESSAGES['invalid_usage'].format(command='research'),
                style=STYLES['error']
            )
            return {'error': 'No research topic provided'}
        # Get topic by joining all non-option args
        topic_args = [arg for arg in args if not arg.startswith('--')]
        topic = ' '.join(topic_args)
        # Parse options
        depth = 3  # Default depth
        # Parse optional args
        for arg in args:
            if arg.startswith('--depth='):
                try:
                    depth = int(arg.split('=')[1])
                    depth = max(1, min(depth, 5))  # Clamp between 1-5
                except ValueError:
                    self.console.print(
                        "Invalid depth value. Using default.",
                        style=STYLES['warning']
                    )
        if not topic:
            self.console.print(
                "Please provide a research topic.",
                style=STYLES['error']
            )
            return {'error': 'Empty research topic'}
        # Create progress display with improved visuals
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            try:
                # Use the new progress display method
                results = await self._display_research_progress(
                    progress.add_task(f"[cyan]Researching: {topic}", total=100),
                    progress,
                    topic,
                    self.research_system.research_topic,
                    topic=topic,
                    research_type=ResearchType.WEB_SEARCH,
                    depth=depth
                )
                
                if results:
                    # Format results with enhanced rendering
                    formatted_output = format_research_results(results)
                    
                    # Display results in a clean panel without debug info
                    self.console.print(Panel(
                        Markdown(formatted_output),
                        title=f"Research Results: {topic}",
                        border_style=STYLES['success'],
                        expand=True
                    ))
                    
                    # Return the results
                    return {
                        'status': 'success',
                        'results': results,
                        'formatted': formatted_output
                    }
                else:
                    self.console.print(
                        "No significant findings were discovered.",
                        style=STYLES['warning']
                    )
                    return {'status': 'empty', 'results': None}
            except Exception as e:
                error_msg = f"Research failed: {str(e)}"
                logger.error(error_msg, exc_info=True)
                self.console.print(
                    ERROR_MESSAGES['research_failed'].format(error=str(e)),
                    style=STYLES['error']
                )
                return {'error': error_msg}

    async def _handle_browse(
        self,
        *args,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle browse command."""
        if not args:
            self.console.print(
                ERROR_MESSAGES['invalid_usage'].format(command='browse'),
                style=STYLES['error']
            )
            return

        url = args[0]

        try:
            content = await self.research_system.browser.gather_content(url)
            if content:
                self.console.print(Panel(
                    content[:500] + "..." if len(content) > 500 else content,
                    title=f"Content from {url}",
                    border_style=STYLES['success']
                ))
                return {'content': content, 'url': url}
            else:
                self.console.print(
                    "No content extracted from URL.",
                    style=STYLES['warning']
                )
                return {'error': 'No content extracted'}

        except Exception as e:
            error_msg = f"Browser error: {str(e)}"
            logger.error(error_msg)
            self.console.print(
                ERROR_MESSAGES['browser_error'].format(error=str(e)),
                style=STYLES['error']
            )
            return {'error': error_msg}

    async def _handle_screenshot(
        self,
        *args,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle screenshot command."""
        if not args:
            self.console.print(
                ERROR_MESSAGES['invalid_usage'].format(command='screenshot'),
                style=STYLES['error']
            )
            return

        url = args[0]
        filename = args[1] if len(args) > 1 else f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"

        try:
            if not self.screenshot_dir:
                self.screenshot_dir = Path("screenshots")
                self.screenshot_dir.mkdir(exist_ok=True)

            filepath = self.screenshot_dir / filename
            
            # Take screenshot
            result = await self.research_system.browser.take_screenshot(url, str(filepath))
            
            if result:
                self.console.print(
                    f"Screenshot saved to: {filepath}",
                    style=STYLES['success']
                )
                return {'filepath': str(filepath), 'url': url}
            else:
                self.console.print(
                    "Failed to capture screenshot.",
                    style=STYLES['error']
                )
                return {'error': 'Screenshot capture failed'}

        except Exception as e:
            error_msg = f"Screenshot error: {str(e)}"
            logger.error(error_msg)
            self.console.print(
                ERROR_MESSAGES['browser_error'].format(error=str(e)),
                style=STYLES['error']
            )
            return {'error': error_msg}

    async def _handle_save(
        self,
        *args,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle save command."""
        if len(args) < 2:
            self.console.print(
                ERROR_MESSAGES['invalid_usage'].format(command='save'),
                style=STYLES['error']
            )
            return

        save_type = args[0]
        filename = args[1]

        try:
            if save_type == 'research':
                return await self._save_research(filename, metadata)
            elif save_type == 'results':
                return await self._save_results(filename, metadata)
            else:
                error_msg = f"Unknown save type: {save_type}"
                self.console.print(error_msg, style=STYLES['error'])
                return {'error': error_msg}

        except Exception as e:
            error_msg = f"Save failed: {str(e)}"
            logger.error(error_msg)
            self.console.print(error_msg, style=STYLES['error'])
            return {'error': error_msg}

    async def _handle_status(
        self,
        *args,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle status command."""
        try:
            status = await self.research_system.get_status()
            self.console.print(Panel(
                f"Research System Status:\n" +
                f"Browser: {'✓' if status['browser'] else '✗'}\n" +
                f"Active Tasks: {status['active_tasks']}\n" +
                f"Completed Tasks: {status['completed_tasks']}",
                title="Status",
                border_style=STYLES['info']
            ))
            return status

        except Exception as e:
            error_msg = f"Status check failed: {str(e)}"
            logger.error(error_msg)
            self.console.print(error_msg, style=STYLES['error'])
            return {'error': error_msg}

    async def _handle_help(
        self,
        *args,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle help command."""
        command = args[0] if args else None

        help_text = {
            'research': 'Research a topic: /research <topic> [--depth=N]',
            'browse': 'Browse a URL: /browse <url>',
            'screenshot': 'Take screenshot: /screenshot <url> [filename]',
            'save': 'Save results: /save <type> <filename>',
            'status': 'Get system status: /status',
            'help': 'Show command help: /help [command]'
        }

        if command:
            if command in help_text:
                self.console.print(Panel(
                    help_text[command],
                    title=f"Help: {command}",
                    border_style=STYLES['info']
                ))
                return {'command': command, 'help': help_text[command]}
            else:
                error_msg = f"Unknown command: {command}"
                self.console.print(error_msg, style=STYLES['error'])
                return {'error': error_msg}
        else:
            # Show all commands
            self.console.print(Panel(
                "\n".join([f"{cmd}: {desc}" for cmd, desc in help_text.items()]),
                title="Available Commands",
                border_style=STYLES['info']
            ))
            return {'commands': help_text}

    async def _save_research(
        self,
        filename: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Save research results to file."""
        try:
            results = await self.research_system.get_latest_results()
            if not results:
                return {'error': 'No research results to save'}

            save_dir = Path("research_results")
            save_dir.mkdir(exist_ok=True)
            filepath = save_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(format_research_results(results))

            self.console.print(
                f"Research results saved to: {filepath}",
                style=STYLES['success']
            )
            return {'filepath': str(filepath), 'results': results}

        except Exception as e:
            error_msg = f"Failed to save research: {str(e)}"
            logger.error(error_msg)
            return {'error': error_msg}

    async def _save_results(
        self,
        filename: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Save current results to file."""
        try:
            if not metadata or 'results' not in metadata:
                return {'error': 'No results to save'}

            save_dir = Path("results")
            save_dir.mkdir(exist_ok=True)
            filepath = save_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(metadata['results'])

            self.console.print(
                f"Results saved to: {filepath}",
                style=STYLES['success']
            )
            return {'filepath': str(filepath)}

        except Exception as e:
            error_msg = f"Failed to save results: {str(e)}"
            logger.error(error_msg)
            return {'error': error_msg}

    def __str__(self) -> str:
        """Get string representation."""
        return "ResearchCommands()"
