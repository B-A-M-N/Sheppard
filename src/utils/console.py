"""
Enhanced console implementation for the chat system.
"""

import logging
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.theme import Theme
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.syntax import Syntax
from rich.traceback import install as install_rich_traceback
from rich.logging import RichHandler
from rich.align import Align
from rich.box import Box, ROUNDED

# Define custom theme with a modern color palette
SHEPPARD_THEME = {
    # Core message types
    "info": "cyan",
    "warning": "yellow",
    "error": "red bold",
    "success": "green bold",
    "debug": "grey70",
    
    # Chat roles
    "user": "#4caf50 bold",  # Green
    "assistant": "#2196f3 bold",  # Blue
    "system": "#ff9800 bold",  # Orange
    
    # Content types
    "code": "#9c27b0",  # Purple
    "url": "#03a9f4 underline",  # Light Blue
    "path": "#00bcd4",  # Teal
    "command": "bold #00bcd4",  # Bold Teal
    
    # Memory and context
    "memory": "#e91e63",  # Pink
    "context": "#00bcd4",  # Teal
    "metadata": "grey85",
    "timestamp": "grey70",
    
    # Research elements
    "source": "#2196f3",  # Blue
    "finding": "#4caf50",  # Green
    "task": "#ff9800",  # Orange
    "progress": "#00bcd4",  # Teal
    
    # UI elements
    "title": "bold #2196f3",  # Bold Blue
    "header": "bold white on #1976d2",  # White on Dark Blue
    "separator": "#78909c",  # Blue Grey
    "prompt": "#4caf50 bold"  # Bold Green
}

# Using built-in ROUNDED box style instead of custom SHEPPARD_BOX
# This avoids the error with incorrect number of lines

class SheppardConsole(Console):
    """Enhanced console with Sheppard-specific styling and functionality."""
    
    def __init__(self, **kwargs):
        """Initialize enhanced console with theme."""
        self.theme = Theme(SHEPPARD_THEME)
        super().__init__(
            theme=self.theme,
            highlight=True,
            record=True,
            markup=True,
            **kwargs
        )
        self._progress = None
    
    def display_welcome(self, version: str = "0.2.0"):
        """Display a stylish welcome message."""
        welcome_text = f"""
        [title]╭──────────────────────────────────────────╮[/title]
        [title]│                                          │[/title]
        [title]│            SHEPPARD AGENCY               │[/title]
        [title]│                                          │[/title]
        [title]│  [success]Powered by Ollama Language Models[/success]  │[/title]
        [title]│                                          │[/title]
        [title]│  [info]Version: {version}[/info]                      │[/title]
        [title]│                                          │[/title]
        [title]╰──────────────────────────────────────────╯[/title]
        """
        
        capabilities = [
            "[success]✓[/success] [bold]Advanced Memory System[/bold]: Context-aware conversations",
            "[success]✓[/success] [bold]Research Capabilities[/bold]: Live web browsing and information extraction",
            "[success]✓[/success] [bold]Learning Preferences[/bold]: Adapts to your communication style",
            "[success]✓[/success] [bold]Ollama Integration[/bold]: Powered by local language models"
        ]
        
        self.print(welcome_text)
        self.print("\n[title]CAPABILITIES:[/title]")
        for capability in capabilities:
            self.print(f"  {capability}")
        
        self.print("\n[info]Type [command]/help[/command] to see available commands[/info]")
        self.print("[info]Type [command]/exit[/command] to quit the application[/info]\n")
    
    def display_message(
        self,
        content: str,
        role: str = "assistant",
        metadata: Optional[Dict[str, Any]] = None,
        style: Optional[str] = None
    ) -> None:
        """Display a chat message with appropriate styling."""
        # Get appropriate style for role
        if not style:
            style = SHEPPARD_THEME.get(role, "default")
        
        # Create panel title based on role
        title = "You" if role == "user" else "Sheppard"
        
        # Format content based on metadata
        display_content = content
        if metadata and metadata.get('type') == 'code':
            # Handle code blocks
            language = metadata.get('language', 'text')
            display_content = Syntax(
                content,
                language,
                theme="monokai",
                line_numbers=True,
                word_wrap=True
            )
        else:
            # Handle markdown for normal messages
            display_content = Markdown(content)
        
        # Create and display panel with custom box style
        panel = Panel(
            display_content,
            title=title,
            title_align="left",
            border_style=style,
            box=ROUNDED,
            padding=(1, 2),
            expand=False
        )
        self.print(panel)
    
    def display_error(self, message: str, title: Optional[str] = None) -> None:
        """Display error message in panel."""
        self.print(Panel(
            message,
            title=title or "Error",
            style="error",
            border_style="red",
            box=ROUNDED
        ))
    
    def display_warning(self, message: str, title: Optional[str] = None) -> None:
        """Display warning message in panel."""
        self.print(Panel(
            message,
            title=title or "Warning",
            style="warning",
            border_style="yellow",
            box=ROUNDED
        ))
    
    def display_success(self, message: str, title: Optional[str] = None) -> None:
        """Display success message in panel."""
        self.print(Panel(
            message,
            title=title or "Success",
            style="success",
            border_style="green",
            box=ROUNDED
        ))
    
    def display_code(
        self,
        code: str,
        language: str = "python",
        title: Optional[str] = None,
        line_numbers: bool = True
    ) -> None:
        """Display code with syntax highlighting."""
        syntax = Syntax(
            code,
            language,
            theme="monokai",
            line_numbers=line_numbers,
            word_wrap=True
        )
        if title:
            syntax = Panel(
                syntax,
                title=title,
                border_style="code",
                box=ROUNDED
            )
        self.print(syntax)
    
    def display_markdown(self, content: str, title: Optional[str] = None) -> None:
        """Display markdown content in panel."""
        markdown = Markdown(content)
        if title:
            self.print(Panel(
                markdown,
                title=title,
                border_style="info",
                box=ROUNDED
            ))
        else:
            self.print(markdown)
    
    def create_table(
        self,
        title: Optional[str] = None,
        headers: Optional[List[str]] = None
    ) -> Table:
        """Create styled table."""
        table = Table(
            title=title,
            title_style="title",
            header_style="header",
            border_style="blue",
            box=ROUNDED,
            expand=False
        )
        if headers:
            for header in headers:
                table.add_column(header)
        return table
    
    def display_status(
        self,
        status: Dict[str, Any],
        title: str = "System Status"
    ) -> None:
        """Display status information in table."""
        table = self.create_table(title=title)
        table.add_column("Component", style="bold")
        table.add_column("Status", style="")
        
        for component, value in status.items():
            if isinstance(value, dict):
                details = "\n".join(f"{k}: {v}" for k, v in value.items())
                table.add_row(component, details)
            else:
                status_value = value
                if isinstance(value, bool):
                    status_value = "[success]Active[/success]" if value else "[error]Inactive[/error]"
                table.add_row(component, str(status_value))
        
        self.print(table)
    
    def create_progress(
        self,
        description: str = "Processing",
        total: Optional[int] = None
    ) -> Progress:
        """Create progress display."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(complete_style="progress"),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self
        )
        
    def display_input_prompt(self):
        """Display a stylish input prompt."""
        self.print("[prompt]You:[/prompt] ", end="")
        
    def display_memory_context(self, memories: List[Dict[str, Any]], title: str = "Relevant Memories"):
        """Display relevant memory context in a styled panel."""
        if not memories:
            return
            
        memory_text = []
        for memory in memories:
            memory_text.append(f"[timestamp]{memory.get('timestamp', 'Unknown')}[/timestamp]")
            memory_text.append(f"[memory]{memory.get('content', '')}[/memory]")
            memory_text.append("[separator]──────────────────[/separator]")
            
        self.print(Panel(
            "\n".join(memory_text),
            title=title,
            border_style="memory",
            box=ROUNDED,
            padding=(1, 2)
        ))
        
    def display_research_results(self, research: Dict[str, Any], title: str = "Research Findings"):
        """Display research results in a styled format."""
        if not research:
            return
            
        findings = research.get('findings', [])
        sources = research.get('sources', [])
        
        research_text = []
        
        # Add summary if available
        summary = research.get('summary', '')
        if summary:
            research_text.append(f"[bold]Summary:[/bold]\n{summary}\n")
            
        # Add findings
        if findings:
            research_text.append("[bold]Key Findings:[/bold]")
            for i, finding in enumerate(findings, 1):
                research_text.append(f"[finding]{i}. {finding}[/finding]")
            research_text.append("")
            
        # Add sources
        if sources:
            research_text.append("[bold]Sources:[/bold]")
            for i, source in enumerate(sources, 1):
                url = source.get('url', '')
                title = source.get('title', 'Unknown Source')
                research_text.append(f"[source]{i}. {title}[/source]")
                research_text.append(f"   [url]{url}[/url]")
            
        self.print(Panel(
            "\n".join(research_text),
            title=title,
            border_style="info",
            box=ROUNDED,
            padding=(1, 2)
        ))

# Configure logging with rich handler
def setup_logging(level=logging.INFO):
    """Setup logging with rich handler."""
    console = Console(theme=Theme(SHEPPARD_THEME))
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[
            RichHandler(
                console=console,
                show_path=False,
                enable_link_path=True,
                markup=True,
                rich_tracebacks=True
            )
        ]
    )

    # Install rich traceback handler
    install_rich_traceback(
        console=console,
        show_locals=True
    )

# Create global console instance
console = SheppardConsole()

# Export console instance
__all__ = ['console', 'setup_logging']
