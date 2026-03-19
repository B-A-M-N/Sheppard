"""
Enhanced memory system integration for research tasks with full validation and error handling.
File: src/research/memory_integration.py
"""

import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime

from src.memory.manager import MemoryManager
from src.memory.models import Memory, MemorySearchResult
from src.research.models import ResearchTask, TaskStatus, ResearchType, ResearchFinding
from src.research.exceptions import ProcessingError
from src.llm.client import OllamaClient

logger = logging.getLogger(__name__)

class MemoryIntegrator:
    """Core integration between research and memory systems."""
    
    def __init__(self, embedding_model: str = 'mxbai-embed-large'):
        """
        Initialize memory integrator.
        
        Args:
            embedding_model: Model to use for embeddings
        """
        self.embedding_model = embedding_model
        self.logger = logging.getLogger(__name__)

    async def integrate(
        self,
        memory: Memory,
        memory_manager: MemoryManager,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Integrate research memory into memory system.
        
        Args:
            memory: Memory to integrate
            memory_manager: Memory manager instance
            metadata: Optional additional metadata
            
        Raises:
            ProcessingError: If integration fails
        """
        try:
            # Ensure memory content is a string
            if not isinstance(memory.content, str):
                if isinstance(memory.content, list):
                    memory.content = "\n".join(str(item) for item in memory.content)
                else:
                    memory.content = str(memory.content)
            
            # Add integration metadata
            if metadata:
                memory.metadata.update(metadata)
            memory.metadata['integrated_at'] = datetime.now().isoformat()
            memory.metadata['integration_source'] = 'research'
            
            # Store in memory system
            await memory_manager.store(memory)
            self.logger.info(f"Successfully integrated memory: {memory.embedding_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to integrate memory: {str(e)}")
            raise ProcessingError(f"Failed to integrate memory: {str(e)}")

    async def integrate_finding(
        self,
        finding: ResearchFinding,
        memory_manager: MemoryManager,
        task_id: Optional[str] = None
    ) -> str:
        """
        Integrate a research finding into memory.
        
        Args:
            finding: Research finding to integrate
            memory_manager: Memory manager instance
            task_id: Optional associated task ID
            
        Returns:
            str: Memory ID of stored finding
            
        Raises:
            ProcessingError: If integration fails
        """
        try:
            # Ensure content is properly formatted as a string
            content = finding.content
            if isinstance(content, list):
                content = "\n\n".join(str(item) for item in content)
            elif not isinstance(content, str):
                content = str(content)
            memory = Memory(
                content=content,
                metadata={
                    'type': 'research_finding',
                    'source': finding.source,
                    'task_id': task_id,
                    'source_type': finding.source_type.value,
                    'research_type': finding.research_source.value,
                    'reliability': finding.reliability.value,
                    'timestamp': finding.timestamp.isoformat(),
                    **finding.metadata
                }
            )
            
            # Integrate memory
            await self.integrate(memory, memory_manager)
            return memory.embedding_id
            
        except Exception as e:
            self.logger.error(f"Failed to integrate finding: {str(e)}")
            raise ProcessingError(f"Failed to integrate finding: {str(e)}")

    async def store_findings(
        self,
        findings: List[ResearchFinding],
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Store research findings in memory.
        
        Args:
            findings: List of research findings
            metadata: Optional metadata to include
            
        Returns:
            List[str]: Memory IDs of stored findings
            
        Raises:
            ProcessingError: If storing findings fails
        """
        memory_ids = []
        
        try:
            for finding in findings:
                memory_id = await self.integrate_finding(
                    finding,
                    metadata=metadata
                )
                memory_ids.append(memory_id)
                
        except Exception as e:
            self.logger.error(f"Failed to store findings: {str(e)}")
            raise ProcessingError(f"Failed to store findings: {str(e)}")
        
        return memory_ids
