# src/core/memory/cleanup.py
import logging
from datetime import datetime
from typing import Dict, Any
import asyncio

logger = logging.getLogger(__name__)

class CleanupManager:
    """Manages memory cleanup operations

    IMPORTANT: Must not instantiate StorageManager (which creates its own Chroma client).
    Instead, accept an injected chroma_store (canonical Chroma store implementation).
    """

    def __init__(self, importance_threshold: float, chroma_store=None):
        self.importance_threshold = importance_threshold
        self.chroma_store = chroma_store
        self.cleanup_running = False
        self.last_cleanup = datetime.now()
        self.cleanup_stats = {
            "total_cleaned": 0,
            "last_cleanup_duration": 0,
            "errors": 0,
            "last_run": datetime.now().isoformat()
        }

    async def perform_full_cleanup(self) -> Dict[str, Any]:
        """Perform full cleanup of all storage types using injected chroma_store.

        Does NOT instantiate StorageManager. Uses the provided chroma_store
        directly if it supports cleanup_old_memories (legacy VectorStoreManager interface).
        """
        if self.cleanup_running:
            return self.cleanup_stats

        self.cleanup_running = True
        start_time = datetime.now()

        # Default empty results
        cleanup_results = {
            "total_removed": 0,
            "timestamp": start_time.isoformat(),
            "layers_cleaned": []
        }

        try:
            # If no chroma_store provided, skip cleanup
            if self.chroma_store is None:
                logger.warning("CleanupManager: no chroma_store provided, skipping cleanup")
                return cleanup_results

            # If the chroma_store supports cleanup_old_memories (e.g., legacy VectorStoreManager),
            # use it directly. Otherwise, skip.
            if not hasattr(self.chroma_store, 'cleanup_old_memories'):
                logger.info("CleanupManager: chroma_store does not support cleanup_old_memories; skipping")
                return cleanup_results

            layers = ["episodic", "semantic", "contextual", "general", "abstracted"]
            cleanup_tasks = []

            # Create cleanup tasks for each layer
            for layer in layers:
                task = asyncio.create_task(
                    self.chroma_store.cleanup_old_memories(
                        layer=layer,
                        days_threshold=30,
                        importance_threshold=self.importance_threshold
                    )
                )
                cleanup_tasks.append((layer, task))

            # Wait for all cleanup tasks
            total_removed = 0
            for layer, task in cleanup_tasks:
                try:
                    result = await task
                    removed = result.get("removed", 0)
                    total_removed += removed
                    cleanup_results["layers_cleaned"].append(layer)
                except Exception as e:
                    logger.error(f"Error cleaning up layer {layer}: {str(e)}")
                    self.cleanup_stats["errors"] += 1

            cleanup_results["total_removed"] = total_removed
            self.cleanup_stats["total_cleaned"] += total_removed
            self.cleanup_stats["last_cleanup_duration"] = (
                datetime.now() - start_time
            ).total_seconds()
            self.cleanup_stats["last_run"] = datetime.now().isoformat()

            self.last_cleanup = datetime.now()
            logger.info(f"Memory cleanup completed: removed {total_removed} items")
            return cleanup_results

        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            self.cleanup_stats["errors"] += 1
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                **cleanup_results
            }

        finally:
            self.cleanup_running = False

    def get_cleanup_stats(self) -> Dict[str, Any]:
        """Get cleanup statistics"""
        return {
            **self.cleanup_stats,
            "last_cleanup": self.last_cleanup.isoformat(),
            "is_cleaning": self.cleanup_running,
            "importance_threshold": self.importance_threshold
        }
