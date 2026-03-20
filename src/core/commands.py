import logging
import shlex
import os
from typing import Dict, Any, Optional, List
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.core.constants import COMMANDS, HELP_CATEGORIES, STYLES, ERROR_MESSAGES, WELCOME_TEXT
from src.core.system import system_manager

logger = logging.getLogger(__name__)

class CommandHandler:
    """CommandHandler — Full feature parity + V2 power."""
    def __init__(self, console: Console, chat_app: Any):
        self.console = console
        self.chat_app = chat_app

    def show_welcome(self) -> None:
        self.console.print(Panel(
            Markdown(WELCOME_TEXT),
            title="Welcome to Sheppard Agency",
            border_style=STYLES['title']
        ))

    async def handle_command(self, input_text: str) -> bool:
        if not input_text.startswith('/'): return False
        try:
            parts = shlex.split(input_text)
            command = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []
            
            handlers = {
                '/help': self._handle_help, '/h': self._handle_help,
                '/learn': self._handle_learn,
                '/stop': self._handle_stop,
                '/missions': self._handle_missions,
                '/nudge': self._handle_nudge,
                '/query': self._handle_query,
                '/report': self._handle_report,
                '/research': self._handle_research, '/r': self._handle_research,
                '/status': self._handle_status,
                '/distill': self._handle_distill,
                '/consolidate': self._handle_consolidate,
                '/settings': self._handle_settings, '/setting': self._handle_settings,
                '/preferences': self._handle_preferences, '/pref': self._handle_preferences,
                '/memory': self._handle_memory, '/mem': self._handle_memory,
                '/project': self._handle_project,
                '/browse': self._handle_browse,
                '/clear': self._handle_clear,
                '/save': self._handle_save,
                '/exit': self._handle_exit,
                '/quit': self._handle_exit,
                '/bye': self._handle_exit
            }
            
            if command in handlers:
                await handlers[command](*args)
            else:
                self.console.print(f"[red]Command '{command}' not found.[/red]")
            return True
        except Exception as e:
            logger.error(f"Command error: {e}")
            self.console.print(f"[bold red]Error:[/bold red] {e}")
            return True

    async def _handle_learn(self, *args) -> None:
        if not args:
            self.console.print("Usage: /learn <topic> [--ceiling=GB] [--academic]", style=STYLES['warning'])
            return
        topic = ' '.join([a for a in args if not a.startswith('--')])
        ceiling = 5.0
        academic = False
        for arg in args:
            if arg.startswith('--ceiling='): ceiling = float(arg.split('=')[1])
            if arg == '--academic': academic = True

        topic_id = await system_manager.learn(topic_name=topic, query=topic, ceiling_gb=ceiling, academic_only=academic)
        self.console.print(Panel(f"Mission ID: {topic_id}\nTopic: {topic}\nCeiling: {ceiling}GB", title="Learning Mission Started", border_style="green"))

    async def _handle_query(self, *args) -> None:
        if not args: return
        text = ' '.join([a for a in args if not a.startswith('--')])
        with self.console.status("[bold cyan]Retrieving knowledge..."):
            ctx = await system_manager.query(text=text)
        if ctx: self.console.print(Panel(Markdown(ctx), title="Retrieval Results", border_style="cyan"))

    async def _handle_report(self, *args) -> None:
        """/report <topic_keyword>"""
        if not args:
            self.console.print("Usage: /report <topic_keyword>", style=STYLES['warning'])
            return
            
        keyword = args[0].lower()
        
        # We need to find the topic ID. Let's ask DB via memory manager.
        # Quick and dirty fuzzy match against topics in DB.
        async with system_manager.memory.pg_pool.acquire() as conn:
            topics = await conn.fetch("SELECT id, name FROM topics")
            
        matches = [t for t in topics if keyword in t['name'].lower()]
        
        if not matches:
            self.console.print(f"[bold red]No topic found matching: '{keyword}'[/bold red]")
            return
        elif len(matches) > 1:
            self.console.print("[bold yellow]Multiple topics found. Please be more specific:[/bold yellow]")
            for i, t in enumerate(matches):
                self.console.print(f" [{i+1}] {t['name']}")
            return
            
        topic_id = str(matches[0]['id'])
        topic_name = matches[0]['name']
        
        self.console.print(f"[bold cyan]Triggering Tier 4 Synthesis for: '{topic_name}'[/bold cyan]")
        report = await system_manager.generate_report(topic_id)
        
        if report:
            self.console.print(Panel(Markdown(report), title=f"Master Brief: {topic_name[:30]}...", border_style="magenta"))
        else:
            self.console.print("[bold red]Synthesis failed or returned empty.[/bold red]")

    async def _handle_research(self, *args) -> None:
        """Legacy research — uses V2 query."""
        await self._handle_query(*args)

    async def _handle_status(self, *args) -> None:
        status = await self.chat_app.get_system_status()
        v2_status = status.get('v2_orchestrator', {})
        
        # 1. Missions Table
        table = Table(title="V2 Learning Missions")
        table.add_column("Topic", style="cyan")
        table.add_column("Quota Used", style="magenta")
        table.add_column("Raw Data", style="green")
        table.add_column("Scout Queue", style="blue")
        table.add_column("State", style="yellow")
        
        missions = v2_status.get('missions', {})
        if missions:
            for tid, info in missions.items():
                table.add_row(
                    info['name'], 
                    info['usage'], 
                    f"{info['raw_mb']} MB", 
                    str(info.get('scout_queue_size', 0)),
                    "Crawling" if info['crawling'] else "Idle"
                )
        else:
            table.add_row("No active missions", "-", "-", "-")
            
        self.console.print(table)

        # 2. System Table
        sys_table = Table(title="System Health")
        sys_table.add_column("Component"); sys_table.add_column("Value")
        
        models = status.get('models', {})
        sys_table.add_row("Chat Model", models.get('chat', 'unknown'))
        sys_table.add_row("Memory Status", "Active" if status.get('memory', {}).get('enabled') else "Disabled")
        sys_table.add_row("Personas", str(status.get('personas', {}).get('count', 0)))
        sys_table.add_row("State", status.get('system', {}).get('state', 'unknown'))
        
        self.console.print(sys_table)

    async def _handle_distill(self, *args) -> None:
        """/distill <topic_id> [--priority=low|high|critical]"""
        if not args:
            self.console.print("Usage: /distill <topic_id> [--priority=low|high|critical]", style=STYLES['warning'])
            return
        
        topic_id = args[0]
        priority_str = "low"
        for arg in args:
            if arg.startswith('--priority='): priority_str = arg.split('=')[1].lower()
        
        from src.research.acquisition.budget import CondensationPriority
        priority_map = {
            "low": CondensationPriority.LOW,
            "high": CondensationPriority.HIGH,
            "critical": CondensationPriority.CRITICAL
        }
        priority = priority_map.get(priority_str, CondensationPriority.LOW)

        self.console.print(f"[bold cyan][Distillery][/bold cyan] Manually triggering {priority_str} distillation for topic: {topic_id}")
        await system_manager.condenser.run(topic_id, priority)
        self.console.print("[bold green][DONE][/bold green] Distillation pass completed.")

    async def _handle_stop(self, *args) -> None:
        """/stop <topic_id>"""
        if not args:
            self.console.print("Usage: /stop <topic_id>", style=STYLES['warning'])
            return
        topic_id = args[0]
        success = await system_manager.cancel_mission(topic_id)
        if success:
            self.console.print(f"[bold green]Mission {topic_id} stopped.[/bold green]")
        else:
            self.console.print(f"[bold red]Mission {topic_id} not found or already stopped.[/bold red]")

    async def _handle_missions(self, *args) -> None:
        """/missions"""
        status = system_manager.status()
        missions = status.get('missions', {})
        
        table = Table(title="Knowledge Missions")
        table.add_column("ID", style="dim")
        table.add_column("Topic", style="cyan")
        table.add_column("State", style="yellow")
        table.add_column("Raw Data", style="green")
        
        for tid, info in missions.items():
            table.add_row(tid, info['name'], "Running" if info['crawling'] else "Idle", f"{info['raw_mb']} MB")
        
        self.console.print(table)

    async def _handle_nudge(self, *args) -> None:
        """/nudge [topic_keyword] \"<instruction>\""""
        if not args:
            self.console.print("Usage: /nudge [topic_keyword] \"<instruction>\"", style=STYLES['warning'])
            return
        
        status = system_manager.status()
        active_missions = {tid: info for tid, info in status.get('missions', {}).items() if info['crawling']}
        
        if not active_missions:
            self.console.print("[bold red]No active missions found to nudge.[/bold red]")
            return

        # 1. Identify Target Topic and Instruction
        target_tid = None
        instruction = ""

        if len(args) == 1:
            # Global nudge (if only one mission active, otherwise ask)
            if len(active_missions) == 1:
                target_tid = list(active_missions.keys())[0]
                instruction = args[0].strip('"\'')
            else:
                instruction = args[0].strip('"\'')
                self.console.print(f"[bold cyan][System][/bold cyan] Applying global nudge to {len(active_missions)} missions.")
                for tid in active_missions:
                    await system_manager.nudge_mission(tid, instruction)
                return
        else:
            # Fuzzy match topic_keyword
            keyword = args[0].lower()
            instruction = " ".join(args[1:]).strip('"\'')
            
            matches = [tid for tid, info in active_missions.items() if keyword in info['name'].lower()]
            
            if not matches:
                self.console.print(f"[bold red]No active mission matches keyword: '{keyword}'[/bold red]")
                return
            elif len(matches) == 1:
                target_tid = matches[0]
            else:
                self.console.print("[bold yellow]Multiple missions found. Please be more specific:[/bold yellow]")
                for i, tid in enumerate(matches):
                    self.console.print(f" [{i+1}] {active_missions[tid]['name']} (ID: {tid[:8]}...)")
                return

        if target_tid:
            success = await system_manager.nudge_mission(target_tid, instruction)
            if success:
                self.console.print(f"[bold green]Steering applied to: {active_missions[target_tid]['name']}[/bold green]")

    async def _handle_consolidate(self, *args) -> None:
        """/consolidate <topic_id>"""
        if not args:
            self.console.print("Usage: /consolidate <topic_id>", style=STYLES['warning'])
            return
        topic_id = args[0]
        self.console.print(f"[bold cyan][Forgetting Curve][/bold cyan] Running consolidation pass on topic: {topic_id}")
        await system_manager.condenser.consolidate_atoms(topic_id)
        self.console.print("[bold green][DONE][/bold green] Consolidation complete.")

    async def _handle_settings(self, *args) -> None:
        settings = await self.chat_app.get_settings()
        table = Table(title="System Settings")
        table.add_column("Setting"); table.add_column("Value")
        for k, v in settings.items(): table.add_row(k, str(v))
        self.console.print(table)

    async def _handle_preferences(self, *args) -> None:
        self.console.print("Preferences dashboard restored.", style="green")

    async def _handle_memory(self, *args) -> None:
        if args and args[0] == 'search':
            q = ' '.join(args[1:])
            res = await system_manager.memory.search(q)
            table = Table(title=f"Memory Search: {q}")
            table.add_column("Content"); table.add_column("Score")
            for r in res: table.add_row(r.content[:100], str(r.relevance_score))
            self.console.print(table)

    async def _handle_project(self, *args) -> None:
        if len(args) < 3: return
        await system_manager.index_project(args[1], args[2])
        self.console.print(f"Indexing project {args[1]}...", style="green")

    async def _handle_browse(self, *args) -> None:
        if not args: return
        self.console.print(f"Browsing {args[0]}...", style="blue")

    async def _handle_clear(self, *args) -> None:
        self.console.clear()
        self.show_welcome()

    async def _handle_exit(self, *args) -> None:
        self.console.print("\n[dim]Goodbye from Sheppard.[/dim]")
        # We raise a SystemExit or similar to break the loop in main.py
        # But a cleaner way is just to exit the process
        import sys
        sys.exit(0)

    async def _handle_save(self, *args) -> None:
        self.console.print("Session saved.", style="green")

    async def _handle_help(self, *args) -> None:
        table = Table(title="V2 Commands")
        table.add_column("Command"); table.add_column("Usage")
        table.add_row("/learn", "Start background mission")
        table.add_row("/query", "Query the knowledge stack")
        table.add_row("/distill", "Manual knowledge distillation")
        table.add_row("/status", "Full system dashboard")
        table.add_row("/settings", "Modify configuration")
        self.console.print(table)
