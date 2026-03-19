"""
Async utilities for managing coroutines and event loops.
"""

import asyncio
import functools
import logging
from typing import Any, Callable, TypeVar, ParamSpec

logger = logging.getLogger(__name__)

P = ParamSpec('P')
T = TypeVar('T')

def async_call(func: Callable[P, T]) -> Callable[P, T]:
    """
    Decorator to ensure async functions are called within the correct event loop.
    Handles event loop management and ensures proper coroutine execution.
    """
    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            # Get the current event loop or create a new one
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Execute the coroutine in the current loop
            return await func(*args, **kwargs)

        except Exception as e:
            logger.error(f"Error in async execution of {func.__name__}: {e}", exc_info=True)
            raise

    return wrapper
