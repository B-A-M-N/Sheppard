"""
Enhanced research task model with Firecrawl integration.
File: src/research/models_task.py
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum, auto

class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    SEARCHING = "searching"
    SCRAPING = "scraping"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    
    def is_active(self) -> bool:
        """Check if status is active."""
        return self in {
            self.PENDING,
            self.SEARCHING,
            self.SCRAPING,
            self.ANALYZING
        }
    
    def is_terminal(self) -> bool:
        """Check if status is terminal."""
        return self in {
            self.COMPLETED,
            self.FAILED,
            self.CANCELLED
        }

class ResearchType(str, Enum):
    """Types of research operations."""
    WEB_SEARCH = "web_search"
    DEEP_ANALYSIS = "deep_analysis"
    FACT_CHECK = "fact_check"
    TOPIC_SUMMARY = "topic_summary"
    
    def get_default_depth(self) -> int:
        """Get default research depth."""
        depths = {
            self.WEB_SEARCH: 3,
            self.DEEP_ANALYSIS: 5,
            self.FACT_CHECK: 4,
            self.TOPIC_SUMMARY: 2
        }
        return depths.get(self, 3)
    
    def get_reliability_threshold(self) -> float:
        """Get minimum source reliability threshold."""
        thresholds = {
            self.WEB_SEARCH: 0.6,
            self.DEEP_ANALYSIS: 0.8,
            self.FACT_CHECK: 0.85,
            self.TOPIC_SUMMARY: 0.7
        }
        return thresholds.get(self, 0.6)

class SourceType(str, Enum):
    """Types of content sources."""
    SCHOLARLY = "scholarly"
    SCIENTIFIC = "scientific"
    GOVERNMENT = "government"
    TECHNICAL = "technical"
    NEWS = "news"
    WEBPAGE = "webpage"
    REFERENCE = "reference"
    SOCIAL = "social"
    
    def get_base_reliability(self) -> float:
        """Get base reliability score."""
        scores = {
            self.SCHOLARLY: 0.9,
            self.SCIENTIFIC: 0.9,
            self.GOVERNMENT: 0.9,
            self.TECHNICAL: 0.8,
            self.NEWS: 0.7,
            self.WEBPAGE: 0.5,
            self.REFERENCE: 0.8,
            self.SOCIAL: 0.3
        }
        return scores.get(self, 0.5)

@dataclass
class ResearchTask:
    """Model for research tasks."""
    
    id: str
    description: str
    research_type: ResearchType = ResearchType.WEB_SEARCH
    status: TaskStatus = TaskStatus.PENDING
    depth: int = field(default_factory=lambda: ResearchType.WEB_SEARCH.get_default_depth())
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    
    # Task configuration
    reliability_threshold: float = field(
        default_factory=lambda: ResearchType.WEB_SEARCH.get_reliability_threshold()
    )
    max_sources: int = 5
    require_markdown: bool = True
    extract_citations: bool = True
    
    # Task results
    sources: List[Dict[str, Any]] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Firecrawl results
    markdown_content: Dict[str, str] = field(default_factory=dict)
    scrape_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate task after initialization."""
        if not self.id:
            raise ValueError("Task ID cannot be empty")
        if not self.description:
            raise ValueError("Task description cannot be empty")
        
        # Set reliability threshold based on research type if not explicitly set
        if 'reliability_threshold' not in self.__dict__:
            self.reliability_threshold = self.research_type.get_reliability_threshold()
    
    def update_status(self, new_status: TaskStatus, error: Optional[str] = None) -> None:
        """Update task status."""
        self.status = new_status
        if error:
            self.error = error
        
        if new_status == TaskStatus.COMPLETED:
            self.completed_at = datetime.now().isoformat()
    
    def add_source(
        self,
        url: str,
        title: str,
        source_type: SourceType,
        reliability: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a source to the task."""
        source = {
            'url': url,
            'title': title,
            'source_type': source_type.value,
            'reliability': reliability,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        self.sources.append(source)
    
    def add_finding(
        self,
        content: str,
        source_url: str,
        confidence: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a finding to the task."""
        finding = {
            'content': content,
            'source_url': source_url,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        self.findings.append(finding)
    
    def add_markdown_content(self, url: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add markdown content from Firecrawl."""
        self.markdown_content[url] = content
        if metadata:
            self.scrape_metadata[url] = metadata
    
    def get_valid_sources(self) -> List[Dict[str, Any]]:
        """Get sources meeting reliability threshold."""
        return [
            source for source in self.sources
            if source['reliability'] >= self.reliability_threshold
        ]
    
    def get_source_stats(self) -> Dict[str, Any]:
        """Get source statistics."""
        stats = {
            'total_sources': len(self.sources),
            'valid_sources': len(self.get_valid_sources()),
            'source_types': {},
            'avg_reliability': 0.0,
            'urls_with_markdown': len(self.markdown_content)
        }
        
        # Count source types
        for source in self.sources:
            source_type = source['source_type']
            stats['source_types'][source_type] = stats['source_types'].get(source_type, 0) + 1
        
        # Calculate average reliability
        if self.sources:
            total_reliability = sum(source['reliability'] for source in self.sources)
            stats['avg_reliability'] = total_reliability / len(self.sources)
        
        return stats
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary."""
        return {
            'id': self.id,
            'description': self.description,
            'research_type': self.research_type.value,
            'status': self.status.value,
            'depth': self.depth,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'error': self.error,
            'reliability_threshold': self.reliability_threshold,
            'max_sources': self.max_sources,
            'require_markdown': self.require_markdown,
            'extract_citations': self.extract_citations,
            'sources': self.sources,
            'findings': self.findings,
            'metadata': self.metadata,
            'markdown_content': self.markdown_content,
            'scrape_metadata': self.scrape_metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchTask':
        """Create task from dictionary."""
        # Convert string enums back to enum types
        if 'research_type' in data:
            data['research_type'] = ResearchType(data['research_type'])
        if 'status' in data:
            data['status'] = TaskStatus(data['status'])
        
        return cls(**data)
    
    def __str__(self) -> str:
        """Get string representation."""
        return (
            f"ResearchTask(id={self.id}, "
            f"type={self.research_type.value}, "
            f"status={self.status.value}, "
            f"sources={len(self.sources)}, "
            f"findings={len(self.findings)})"
        )
