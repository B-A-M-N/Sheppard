import logging
import asyncio
import os
import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.panel import Panel

from src.research.archivist import run_research
from src.research.models import ResearchType, MemoryType
from src.memory.models import Memory

logger = logging.getLogger(__name__)
console = Console()

class KnowledgeEngine:
    """
    Continuous Accretive Research Engine.
    Handles /learn missions, background processing, and 90% data condensation.
    """
    
    def __init__(self, memory_manager, ollama_client, browser_manager):
        self.memory = memory_manager
        self.llm = ollama_client
        self.browser = browser_manager
        self.active_missions = {}
        self.max_raw_size = 5 * 1024 * 1024 * 1024  # 5GB default limit
        self.condensation_target = 0.10 # 10%
        
    async def start_learning_mission(self, topic: str, max_gb: int = 5):
        """Starts a background learning mission for a subject."""
        if topic in self.active_missions:
            return False, f"Mission for '{topic}' is already active."
            
        self.max_raw_size = max_gb * 1024 * 1024 * 1024
        logger.info(f"Starting learning mission for '{topic}' (Max: {max_gb}GB)")
        
        mission_task = asyncio.create_task(self._learning_loop(topic))
        self.active_missions[topic] = {
            "task": mission_task,
            "start_time": datetime.now(),
            "status": "ingesting",
            "raw_size": 0,
            "cycles": 0
        }
        return True, f"Started learning mission for '{topic}' (Max: {max_gb}GB)"

    async def _learning_loop(self, topic: str):
        """Internal recursive loop for continuous research."""
        logger.info(f"Entering learning loop for topic: {topic}")
        try:
            while True:
                # 1. Check Quota
                logger.info(f"Checking storage quota for '{topic}'...")
                current_size = await self.memory.get_topic_size(topic)
                self.active_missions[topic]["raw_size"] = current_size
                logger.info(f"Current topic size: {current_size / (1024*1024):.2f} MB")
                
                if current_size >= self.max_raw_size:
                    logger.info(f"Topic '{topic}' reached {current_size} bytes. Triggering condensation.")
                    await self._condense_knowledge(topic)
                
                # 2. Run an Archivist Cycle
                cycles = self.active_missions[topic]["cycles"]
                recursive_objective = f"Objective: {topic} (Cycle {cycles + 1}). Find deeper patterns, missing technical details, and niche primary sources not found in previous runs."
                
                logger.info(f"Starting Archivist Cycle {cycles + 1} for '{topic}'...")
                
                # Run the blocking research call in a thread
                loop = asyncio.get_event_loop()
                # Wrap run_research to ensure topic metadata is always included
                def run_with_metadata():
                    # We inject the topic into the state or metadata context
                    # The Archivist loop.py has been updated to accept memory_manager
                    return run_research(
                        recursive_objective,
                        self.memory,
                        self.llm,
                        self.browser,
                        topic=topic # Pass explicit topic for metadata tagging
                    )

                await loop.run_in_executor(None, run_with_metadata)
                
                self.active_missions[topic]["cycles"] += 1
                logger.info(f"Completed Archivist Cycle {cycles + 1} for '{topic}'")
                
                # 3. Saturation Check
                new_size = await self.memory.get_topic_size(topic)
                size_diff = new_size - current_size
                logger.info(f"New data collected: {size_diff / 1024:.2f} KB")
                
                if size_diff < 1024 * 50: # Less than 50KB new data (adjusted threshold)
                    logger.info(f"Topic '{topic}' saturated (Gain: {size_diff/1024:.2f}KB). Terminating mission.")
                    self.active_missions[topic]["status"] = "saturated"
                    await self._condense_knowledge(topic, finalize=True)
                    break
                    
                await asyncio.sleep(5) 
                
        except Exception as e:
            logger.error(f"Learning mission for '{topic}' failed: {e}")
            if topic in self.active_missions:
                self.active_missions[topic]["status"] = "failed"

    async def _condense_knowledge(self, topic: str, finalize: bool = False):
        """
        The 10% Protocol: Distills raw semantic data into the Abstracted Layer.
        """
        self.active_missions[topic]["status"] = "condensing"
        console.print(f"[bold yellow]CRITICAL:[/bold yellow] Condensing knowledge for [cyan]{topic}[/cyan] (Target: 10% reduction)")
        
        # 1. Fetch all raw chunks for this topic
        raw_memories = await self.memory.search(
            query=topic,
            limit=5000,
            metadata_filter={"topic": topic}
        )
        
        # 2. Group into batches for distillation
        # Distillation converts 50MB of raw text into 5MB of "High-Density Facts"
        distilled_data = []
        batch_size = 20 # memories per batch
        
        for i in range(0, len(raw_memories), batch_size):
            batch = raw_memories[i:i+batch_size]
            content_to_distill = "\n---\n".join([m.content for m in batch])
            
            # 3. AI Distillation Call
            distilled_signal = await self.llm.summarize_text(
                content_to_distill,
                max_length=len(content_to_distill) // 10 # Force 10% size
            )
            
            if distilled_signal:
                distilled_data.append(distilled_signal)
        
        # 4. Save to Abstracted Layer
        final_distillation = "\n\n".join(distilled_data)
        abstracted_memory = Memory(
            content=final_distillation,
            metadata={
                "type": "distilled_knowledge",
                "topic": topic,
                "version": self.active_missions[topic]["cycles"],
                "finalized": finalize
            }
        )
        
        await self.memory.store(abstracted_memory)
        
        # 5. Cleanup (Optional: Keep URLs but remove raw text if limit is hard)
        # For now, we keep it for safety unless we're truly out of space.
        
        self.active_missions[topic]["status"] = "ingesting" if not finalize else "complete"
        return True

    def get_status(self):
        return self.active_missions
