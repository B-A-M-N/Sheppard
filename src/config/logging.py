# src/config/logging.py
"""
Enhanced logging configuration for the chat system.
"""

import logging
import sys
from pathlib import Path
from typing import Optional, Dict
from rich.logging import RichHandler
from rich.traceback import install as install_rich_traceback
from rich.console import Console

# Initialize console for rich output
console = Console()

def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    module_levels: Optional[Dict[str, str]] = None
) -> None:
    """
    Set up application logging with rich output and file logging.
    
    Args:
        level: Overall logging level
        log_file: Optional file path for logging
        module_levels: Dict of module-specific log levels
    """
    # Set default log level
    default_level = level or 'INFO'
    
    # Configure rich handler
    rich_handler = RichHandler(
        console=console,
        show_path=True,
        enable_link_path=True,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        tracebacks_extra_lines=2,
        tracebacks_theme='monokai',
        show_time=True,
        show_level=True
    )
    
    # Get root logger and remove existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Add rich handler
    root_logger.addHandler(rich_handler)
    root_logger.setLevel(default_level)
    
    # Add file handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        root_logger.addHandler(file_handler)
    
    # Set module-specific log levels
    if module_levels:
        for module, level in module_levels.items():
            logging.getLogger(module).setLevel(level)
    
    # Install rich traceback handler
    install_rich_traceback(show_locals=True)
    
    # Log initial configuration
    logger = logging.getLogger(__name__)
    logger.info("Logging initialized:")
    logger.info(f"Default level: {default_level}")
    if log_file:
        logger.info(f"Log file: {log_file}")
    if module_levels:
        logger.info("Module-specific levels:")
        for module, level in module_levels.items():
            logger.info(f"  {module}: {level}")

def get_logger(name: str) -> logging.Logger:
    """Get a configured logger instance."""
    return logging.getLogger(name)
