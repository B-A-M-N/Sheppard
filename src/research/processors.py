"""
Research data processors and result formatting utilities.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple, AsyncGenerator
from datetime import datetime

from src.utils.text_processing import sanitize_text
from src.research.models import (
    ResearchTask,
    TaskStatus,
    ResearchType,
    ResearchFinding
)
from src.research.exceptions import ProcessingError

logger = logging.getLogger(__name__)

class ResearchProcessor:
    """Base research processor."""
    
    def __init__(self, memory_manager=None, ollama_client=None):
        """
        Initialize research processor.
        
        Args:
            memory_manager: Optional memory manager instance
            ollama_client: Optional Ollama client instance
        """
        self.memory_manager = memory_manager
        self.client = ollama_client
        self.tasks: Dict[str, ResearchTask] = {}
        self.logger = logging.getLogger(__name__)
    
    async def process_findings(
        self,
        findings: List[ResearchFinding],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process research findings."""
        try:
            processed_data = {
                'findings': [],
                'summary': None,
                'metadata': metadata or {},
                'timestamp': datetime.now().isoformat()
            }
            
            for finding in findings:
                processed_finding = await self._process_finding(finding)
                if processed_finding:
                    processed_data['findings'].append(processed_finding)
            
            # Generate summary if findings exist
            if processed_data['findings'] and self.client:
                processed_data['summary'] = await self._generate_summary(
                    processed_data['findings']
                )
            
            return processed_data
            
        except Exception as e:
            logger.error(f"Failed to process findings: {str(e)}")
            raise ProcessingError(f"Failed to process findings: {str(e)}")
    
    async def _process_finding(
        self,
        finding: ResearchFinding
    ) -> Optional[Dict[str, Any]]:
        """Process individual research finding."""
        try:
            # Clean and validate content
            content = sanitize_text(finding.content)
            if not content:
                return None
            
            return {
                'content': content,
                'source': finding.source,
                'source_type': finding.source_type.value,
                'reliability': finding.reliability.value,
                'timestamp': finding.timestamp.isoformat(),
                'metadata': finding.metadata
            }
            
        except Exception as e:
            logger.warning(f"Failed to process finding: {str(e)}")
            return None
    
    async def _generate_summary(
        self,
        findings: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Generate summary of findings."""
        try:
            if not findings or not self.client:
                return None
                
            # Prepare content for summarization
            content = "\n\n".join(
                f"Finding from {f['source']}:\n{f['content']}"
                for f in findings
            )
            
            # Generate summary using client
            summary = await self.client.summarize_text(content)
            return summary
            
        except Exception as e:
            logger.warning(f"Failed to generate summary: {str(e)}")
            return None

class DataProcessor:
    """Processes research data and metrics."""
    
    def __init__(self, ollama_client=None):
        """Initialize data processor."""
        self.client = ollama_client
        self.logger = logging.getLogger(__name__)
    
    async def process_data(
        self,
        data: Any,
        data_type: str = "text",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process research data."""
        try:
            if isinstance(data, str):
                processed = await self._process_text(data)
            elif isinstance(data, dict):
                processed = await self._process_structured(data)
            else:
                processed = str(data)
            
            return {
                'processed_data': processed,
                'data_type': data_type,
                'metadata': metadata or {},
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Data processing failed: {str(e)}")
            raise ProcessingError(f"Failed to process data: {str(e)}")
    
    async def _process_text(self, text: str) -> str:
        """Process text data."""
        return sanitize_text(text)
    
    async def _process_structured(self, data: Dict) -> Dict:
        """Process structured data."""
        return {
            k: sanitize_text(v) if isinstance(v, str) else v
            for k, v in data.items()
        }

class ResultProcessor:
    """Processes and formats research results."""
    
    def __init__(self):
        """Initialize result processor."""
        self.logger = logging.getLogger(__name__)
    
    def process_results(
        self,
        results: List[Any],
        format_type: str = 'default'
    ) -> Dict[str, Any]:
        """
        Process and format results.
        
        Args:
            results: Results to process
            format_type: Type of formatting to apply
            
        Returns:
            Dict[str, Any]: Processed results
        """
        try:
            return {
                "status": "success",
                "results": results,
                "format_type": format_type,
                "count": len(results),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Results processing failed: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
            
    async def process_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Process and format research results properly."""
        try:
            processed_results = {
                'topic': results.get('topic', ''),
                'findings': [],
                'timestamp': datetime.now().isoformat()
            }
            
            # Ensure findings are properly formatted
            raw_findings = results.get('findings', [])
            for finding in raw_findings:
                # Ensure content is a string
                content = finding.get('content', '')
                if isinstance(content, list):
                    # Convert list to string if needed
                    content = '\n'.join(str(item) for item in content)
                
                # Add processed finding
                processed_finding = {
                    'url': finding.get('url', ''),
                    'title': finding.get('title', ''),
                    'content': content,  # Now guaranteed to be a string
                    'timestamp': finding.get('timestamp', datetime.now().isoformat())
                }
                
                # Add key findings if available
                if isinstance(finding.get('key_findings'), dict):
                    processed_finding['key_findings'] = finding['key_findings']
                
                processed_results['findings'].append(processed_finding)
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Result processing failed: {str(e)}")
            # Return minimal valid results on error
            return {
                'topic': results.get('topic', ''),
                'findings': [],
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

    def __str__(self) -> str:
        """Get string representation."""
        return "ResultProcessor"
    
    def summarize_results(
        self,
        results: List[Any],
        summary_format: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate results summary."""
        try:
            summary = {
                "total_count": len(results),
                "timestamp": datetime.now().isoformat()
            }
            
            if results:
                summary.update({
                    "first_result": results[0],
                    "last_result": results[-1],
                    "has_errors": any(
                        'error' in r for r in results 
                        if isinstance(r, dict)
                    )
                })
            
            return {
                "status": "success",
                "summary": summary,
                "format": summary_format
            }
        except Exception as e:
            logger.error(f"Results summarization failed: {str(e)}")
            return {
                "status": "error", 
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

def format_research_results(results: Dict[str, Any]) -> str:
    """Format research results into a visually appealing, well-structured string."""
    if not results.get('findings'):
        return "No research findings were discovered."
        
    topic = results.get('topic', results.get('query', 'Unknown topic'))
    
    formatted_parts = []
    formatted_parts.append(f"# Research Results: {topic}\n")
    
    # Add overall summary if available
    if 'summary' in results:
        formatted_parts.append(f"## Summary")
        summary = results['summary']
        if isinstance(summary, list):
            summary = "\n".join(str(item) for item in summary)
        formatted_parts.append(f"{summary}\n")
    
    # Format findings with better structure and hierarchy
    formatted_parts.append(f"## Key Findings\n")
    
    for idx, finding in enumerate(results['findings'], 1):
        # Format title with source
        title = finding.get('title', 'Unknown Source').strip()
        url = finding.get('url', finding.get('source', '')).strip()
        
        # Create more visually distinct section headers
        formatted_parts.append(f"### {idx}. {title}")
        
        if url:
            formatted_parts.append(f"**Source**: [{url}]({url})")
        
        # Format summary with clear heading
        if finding.get('summary'):
            summary_content = finding['summary']
            if isinstance(summary_content, list):
                summary_content = "\n".join(str(item) for item in summary_content)
            formatted_parts.append(f"\n**Overview**:\n{summary_content}")
        
        # Format key takeaways with bullet points
        if finding.get('key_takeaways'):
            formatted_parts.append(f"\n**Key Points**:")
            takeaways = finding['key_takeaways']
            if isinstance(takeaways, list):
                for point in takeaways:
                    formatted_parts.append(f"* {str(point)}")  # Ensure string conversion
            else:
                formatted_parts.append(f"* {str(takeaways)}")  # Ensure string conversion
        
        # Add separator between findings
        if idx < len(results['findings']):
            formatted_parts.append("\n---")
    
    # Add timestamp in a more readable format
    if results.get('timestamp'):
        try:
            timestamp = datetime.fromisoformat(results['timestamp'])
            formatted_time = timestamp.strftime("%B %d, %Y at %I:%M %p")
            formatted_parts.append(f"\n## Research completed on {formatted_time}")
        except:
            formatted_parts.append(f"\nResearch completed at: {results.get('timestamp')}")
    
    # Ensure all elements are strings before joining
    string_parts = [str(part) for part in formatted_parts]
    return "\n".join(string_parts)
