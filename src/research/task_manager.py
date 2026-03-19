"""
Enhanced research task management with progress tracking and memory integration.
File: src/research/task_manager.py
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Set, TYPE_CHECKING
from datetime import datetime
import uuid
from pathlib import Path

# Import just the model classes directly needed
from src.research.models import (
    ResearchTask,
    TaskStatus,
    ResearchType,
    ValidationLevel
)
from src.research.exceptions import (
    TaskError,
    TaskNotFoundError,
    ProcessingError
)
from src.memory.models import Memory
from src.utils.text_processing import sanitize_text

logger = logging.getLogger(__name__)

class ResearchTaskManager:
    """Manages research tasks with progress tracking and memory integration."""
    
    def __init__(
        self,
        memory_manager=None,
        ollama_client=None,
        max_concurrent_tasks: int = 5,
        task_timeout: int = 300,
        results_dir: Optional[Path] = None
    ):
        """Initialize task manager."""
        self.memory_manager = memory_manager
        self.ollama_client = ollama_client
        self.max_concurrent_tasks = max_concurrent_tasks
        self.task_timeout = task_timeout
        
        # Add this attribute for lazy loading
        self._research_system = None
        
        # Initialize task storage
        self.tasks: Dict[str, ResearchTask] = {}
        self.active_tasks: Set[str] = set()
        
        # Set up results directory
        self.results_dir = results_dir
        if self.results_dir:
            self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize task metrics
        self._metrics = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'avg_completion_time': 0.0
        }
        
        # Initialize error tracking
        self._error_count = 0
        self._last_error = None
        self._last_error_time = None
        
        # Initialize state
        self._initialized = False
    
    @property
    def research_system(self):
        """Lazy-load research system to avoid circular imports."""
        if self._research_system is None:
            from src.research.system import ResearchSystem
            self._research_system = ResearchSystem()
        return self._research_system
    
    async def initialize(self) -> None:
        """Initialize task manager."""
        if self._initialized:
            return
        
        try:
            # Create results directory if needed
            if self.results_dir and not self.results_dir.exists():
                self.results_dir.mkdir(parents=True)
            
            self._initialized = True
            logger.info("Task manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize task manager: {str(e)}")
            raise
    
    async def create_task(
        self,
        description: str,
        research_type: ResearchType = ResearchType.WEB_SEARCH,
        depth: int = 3,
        priority: str = "medium",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create new research task.
        
        Args:
            description: Task description
            research_type: Type of research
            depth: Research depth
            priority: Task priority
            metadata: Optional metadata
            
        Returns:
            str: Task ID
        """
        try:
            # Validate inputs
            if not description or not description.strip():
                raise ValueError("Task description cannot be empty")
            
            if depth < 1 or depth > 5:
                raise ValueError("Research depth must be between 1 and 5")
            
            # Generate task ID
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            
            # Create task object
            task = ResearchTask(
                id=task_id,
                description=sanitize_text(description),
                research_type=research_type,
                depth=depth,
                created_at=datetime.now().isoformat(),
                metadata=metadata or {}
            )
            
            # Store task
            self.tasks[task_id] = task
            self._metrics['total_tasks'] += 1
            
            logger.info(f"Created task {task_id}: {description}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to create task: {str(e)}")
            raise TaskError(f"Task creation failed: {str(e)}")
    
    async def get_task(self, task_id: str) -> Optional[ResearchTask]:
        """Get task by ID."""
        task = self.tasks.get(task_id)
        if not task:
            raise TaskNotFoundError(task_id)
        return task
    
    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Update task status.
        
        Args:
            task_id: Task ID
            status: New status
            error: Optional error message
            metadata: Optional metadata updates
        """
        task = await self.get_task(task_id)
        
        # Update status
        task.status = status
        if error:
            task.error = error
        
        # Update metadata
        if metadata:
            task.metadata.update(metadata)
        
        # Update completion time if terminal status
        if status.is_terminal():
            task.completed_at = datetime.now().isoformat()
            
            # Update metrics
            if status == TaskStatus.COMPLETED:
                self._metrics['completed_tasks'] += 1
                
                # Calculate completion time
                start_time = datetime.fromisoformat(task.created_at)
                end_time = datetime.fromisoformat(task.completed_at)
                completion_time = (end_time - start_time).total_seconds()
                
                # Update average completion time
                prev_avg = self._metrics['avg_completion_time']
                completed = self._metrics['completed_tasks']
                self._metrics['avg_completion_time'] = (
                    (prev_avg * (completed - 1) + completion_time) / completed
                )
            
            elif status == TaskStatus.FAILED:
                self._metrics['failed_tasks'] += 1
            
            # Remove from active tasks
            if task_id in self.active_tasks:
                self.active_tasks.remove(task_id)
    
    async def process_task(self, task_id: str, progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """Process research task with structured key findings and better error handling."""
        task = await self.get_task(task_id)
        
        # Add to active tasks
        self.active_tasks.add(task_id)
        task.started_at = datetime.now().isoformat()
        
        try:
            # Update status
            await self.update_task_status(task_id, TaskStatus.IN_PROGRESS)
            
            if progress_callback:
                progress_callback(0.1)
            
            # Add retry logic for research tasks
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    # Get research results
                    result = await self.research_system.research_topic(
                        topic=task.description,
                        research_type=task.research_type,
                        depth=task.depth,
                        progress_callback=progress_callback,
                        metadata=task.metadata
                    )
                    
                    # If we got here, the operation succeeded
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise
                    logger.warning(f"Research attempt {retry_count} failed: {str(e)}. Retrying...")
                    await asyncio.sleep(2 ** retry_count)  # Exponential backoff
            
            # Format result for memory storage with improved type handling
            formatted_findings = []
            for finding in result.get('findings', []):
                # Ensure summary is always a string
                summary = ''
                if isinstance(finding.get('summary'), str):
                    summary = finding['summary']
                elif isinstance(finding.get('summary'), list):
                    summary = "\n".join(str(item) for item in finding['summary'])
                elif finding.get('key_findings', {}).get('summary'):
                    summary_data = finding['key_findings']['summary']
                    if isinstance(summary_data, list):
                        summary = "\n".join(str(item) for item in summary_data)
                    else:
                        summary = str(summary_data)
                
                # Ensure key_takeaways is always a list of strings
                key_takeaways = []
                if isinstance(finding.get('key_takeaways'), list):
                    key_takeaways = [str(item) for item in finding['key_takeaways']]
                elif isinstance(finding.get('key_takeaways'), str):
                    key_takeaways = [finding['key_takeaways']]
                elif finding.get('key_findings', {}).get('key_takeaways'):
                    takeaways_data = finding['key_findings']['key_takeaways']
                    if isinstance(takeaways_data, list):
                        key_takeaways = [str(item) for item in takeaways_data]
                    elif isinstance(takeaways_data, str):
                        key_takeaways = [takeaways_data]
                
                formatted_finding = {
                    'url': finding.get('url', ''),
                    'title': finding.get('title', ''),
                    'summary': summary if summary else '',
                    'key_takeaways': key_takeaways if key_takeaways else [],
                    'detailed_analysis': str(finding.get('key_findings', {}).get('detailed_analysis', '')),
                    'limitations': str(finding.get('key_findings', {}).get('limitations', '')),
                    'actionable_insights': str(finding.get('key_findings', {}).get('actionable_insights', ''))
                }
                formatted_findings.append(formatted_finding)
            
            # Update task result
            task.result = {
                'topic': task.description,
                'findings': formatted_findings,
                'sources_analyzed': result.get('sources_analyzed', 0),
                'successful_extractions': result.get('successful_extractions', 0),
                'timestamp': datetime.now().isoformat()
            }
            
            # Update status
            await self.update_task_status(
                task_id,
                TaskStatus.COMPLETED,
                metadata={'completion_time': datetime.now().isoformat()}
            )
            
            if progress_callback:
                progress_callback(1.0)
            
            return task.result
        
        except Exception as e:
            # Update error tracking with structured error details
            self._error_count += 1
            self._last_error = str(e)
            self._last_error_time = datetime.now()
            
            logger.error(f"Task processing failed: {str(e)}")
            
            # Update task status with error details
            await self.update_task_status(
                task_id,
                TaskStatus.FAILED,
                error=str(e)
            )
            
            raise TaskError(f"Task processing failed: {str(e)}")
            
        finally:
            # Ensure task is removed from active tasks
            if task_id in self.active_tasks:
                self.active_tasks.remove(task_id)
    
    async def _process_web_search(
        self,
        task: ResearchTask,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Process web search task."""
        results = {
            'task_id': task.id,
            'query': task.description,
            'findings': [],
            'sources_analyzed': 0,
            'trusted_sources': 0,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Create memory entry for task if memory manager available
            if self.memory_manager:
                memory = Memory(
                    content=f"Research task: {task.description}",
                    metadata={
                        'type': 'research_task',
                        'task_id': task.id,
                        'research_type': task.research_type.value,
                        'timestamp': datetime.now().isoformat()
                    }
                )
                
                # Generate embedding if Ollama available
                if self.ollama_client:
                    try:
                        embedding = await self.ollama_client.generate_embedding(
                            text=task.description,
                            model="mxbai-embed-large"
                        )
                        memory.embedding = embedding
                    except Exception as e:
                        logger.warning(f"Failed to generate embedding: {str(e)}")
                
                await self.memory_manager.store(memory)
            
            # Process web search results
            if progress_callback:
                progress_callback(0.2)
            
            # Note: Actual web search processing would be handled by the research system
            # This method primarily handles task tracking and memory integration
            
            if progress_callback:
                progress_callback(0.8)
            
            return results
            
        except Exception as e:
            logger.error(f"Web search processing failed: {str(e)}")
            raise ProcessingError(f"Web search failed: {str(e)}")
    
    async def _process_deep_analysis(
        self,
        task: ResearchTask,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Process deep analysis task."""
        results = {
            'task_id': task.id,
            'query': task.description,
            'findings': [],
            'analysis': None,
            'sources_analyzed': 0,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            if progress_callback:
                progress_callback(0.2)
            
            # Note: Actual deep analysis would be handled by the research system
            # This method primarily handles task tracking and memory integration
            
            if progress_callback:
                progress_callback(0.8)
            
            return results
            
        except Exception as e:
            logger.error(f"Deep analysis processing failed: {str(e)}")
            raise ProcessingError(f"Deep analysis failed: {str(e)}")
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task.
        
        Args:
            task_id: Task ID to cancel
            
        Returns:
            bool: True if task was cancelled
        """
        try:
            task = await self.get_task(task_id)
            
            if task.status.is_terminal():
                return False
            
            await self.update_task_status(
                task_id,
                TaskStatus.CANCELLED,
                metadata={'cancellation_time': datetime.now().isoformat()}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Task cancellation failed: {str(e)}")
            return False
    
    async def get_task_results(
        self,
        task_id: str,
        include_content: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Get task results.
        
        Args:
            task_id: Task ID
            include_content: Whether to include full content
            
        Returns:
            Optional[Dict[str, Any]]: Task results if available
        """
        try:
            task = await self.get_task(task_id)
            
            results = {
                'task_id': task_id,
                'status': task.status.value,
                'created_at': task.created_at,
                'started_at': task.started_at,
                'completed_at': task.completed_at,
                'error': task.error,
                'metadata': task.metadata
            }
            
            # Add results if completed
            if task.status == TaskStatus.COMPLETED and task.result:
                if include_content:
                    results['result'] = task.result
                else:
                    # Include only metadata without full content
                    results['result'] = {
                        k: v for k, v in task.result.items()
                        if k != 'findings'
                    }
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get task results: {str(e)}")
            return None
    
    async def cleanup_tasks(self, max_age_hours: int = 24) -> None:
        """
        Clean up old completed tasks.
        
        Args:
            max_age_hours: Maximum age in hours for completed tasks
        """
        try:
            current_time = datetime.now()
            tasks_to_remove = []
            
            for task_id, task in self.tasks.items():
                if not task.status.is_terminal():
                    continue
                
                # Check task age
                completed_time = datetime.fromisoformat(task.completed_at)
                age = (current_time - completed_time).total_seconds() / 3600
                
                if age >= max_age_hours:
                    tasks_to_remove.append(task_id)
            
            # Remove old tasks
            for task_id in tasks_to_remove:
                del self.tasks[task_id]
            
            logger.info(f"Cleaned up {len(tasks_to_remove)} old tasks")
            
        except Exception as e:
            logger.error(f"Task cleanup failed: {str(e)}")
    
    async def get_active_tasks(self) -> List[Dict[str, Any]]:
        """Get list of active tasks."""
        active_tasks = []
        
        for task_id in self.active_tasks:
            try:
                task = await self.get_task(task_id)
                active_tasks.append({
                    'task_id': task_id,
                    'description': task.description,
                    'type': task.research_type.value,
                    'started_at': task.started_at,
                    'duration': (
                        datetime.now() - 
                        datetime.fromisoformat(task.started_at)
                    ).total_seconds()
                })
            except Exception:
                continue
        
        return active_tasks
    
    async def get_task_metrics(self) -> Dict[str, Any]:
        """Get task processing metrics."""
        return {
            'total_tasks': self._metrics['total_tasks'],
            'completed_tasks': self._metrics['completed_tasks'],
            'failed_tasks': self._metrics['failed_tasks'],
            'active_tasks': len(self.active_tasks),
            'avg_completion_time': round(self._metrics['avg_completion_time'], 2),
            'error_count': self._error_count,
            'last_error': self._last_error,
            'last_error_time': self._last_error_time.isoformat() if self._last_error_time else None,
            'timestamp': datetime.now().isoformat()
        }
    
    async def export_task_results(
        self,
        task_id: str,
        format_type: str = 'json',
        file_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Export task results to file.
        
        Args:
            task_id: Task ID
            format_type: Export format ('json' or 'markdown')
            file_path: Optional file path
            
        Returns:
            Optional[str]: Path to exported file if successful
        """
        try:
            # Get task results
            results = await self.get_task_results(task_id)
            if not results:
                return None
            
            # Generate file path if not provided
            if not file_path:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                file_path = f"task_{task_id}_{timestamp}.{format_type}"
            
            # Ensure results directory exists
            if self.results_dir:
                file_path = self.results_dir / file_path
            
            # Export based on format
            if format_type == 'json':
                import json
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2)
            
            elif format_type == 'markdown':
                # Format results as markdown
                markdown_content = []
                markdown_content.append(f"# Research Task Results\n")
                markdown_content.append(f"Task ID: {task_id}")
                markdown_content.append(f"Status: {results['status']}")
                markdown_content.append(f"Created: {results['created_at']}\n")
                
                if results.get('result'):
                    markdown_content.append("## Findings\n")
                    for finding in results['result'].get('findings', []):
                        markdown_content.append(f"### Source: {finding.get('source', 'Unknown')}")
                        markdown_content.append(finding.get('content', ''))
                        markdown_content.append("---\n")
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(markdown_content))
            
            else:
                raise ValueError(f"Unsupported export format: {format_type}")
            
            return str(file_path)
            
        except Exception as e:
            logger.error(f"Failed to export task results: {str(e)}")
            return None
    
    def __str__(self) -> str:
        """Get string representation."""
        return (
            f"ResearchTaskManager("
            f"tasks={len(self.tasks)}, "
            f"active={len(self.active_tasks)}, "
            f"completed={self._metrics['completed_tasks']})"
        )
