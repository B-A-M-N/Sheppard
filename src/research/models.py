"""
Research system data models with circular import fixes.
File: src/research/models.py
"""

import os
import uuid
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Union, Tuple, TYPE_CHECKING

# --- ENUM CLASSES ---
# Define ValidationLevel here to avoid circular imports with validators.py
class ValidationLevel(str, Enum):
    """Validation strictness levels."""
    HIGH = "high"      # Strict validation
    MEDIUM = "medium"  # Standard validation
    LOW = "low"        # Basic validation
    NONE = "none"      # No validation

    def get_required_checks(self) -> Dict[str, bool]:
        """Get required validation checks for each level."""
        checks = {
            self.HIGH: {
                "url_format": True,
                "domain_trust": True,
                "ssl_verify": True,
                "content_type": True,
                "redirect_check": True,
                "malware_check": True
            },
            self.MEDIUM: {
                "url_format": True,
                "domain_trust": True,
                "ssl_verify": True,
                "content_type": True,
                "redirect_check": False,
                "malware_check": False
            },
            self.LOW: {
                "url_format": True,
                "domain_trust": False,
                "ssl_verify": True,
                "content_type": False,
                "redirect_check": False,
                "malware_check": False
            },
            self.NONE: {
                "url_format": False,
                "domain_trust": False,
                "ssl_verify": False,
                "content_type": False,
                "redirect_check": False,
                "malware_check": False
            }
        }
        return checks.get(self, checks[self.MEDIUM])

    def get_timeout(self) -> int:
        """Get validation timeout in seconds for each level."""
        timeouts = {
            self.HIGH: 60,    # Comprehensive validation
            self.MEDIUM: 30,  # Standard validation
            self.LOW: 15,     # Basic validation
            self.NONE: 5      # Minimal validation
        }
        return timeouts.get(self, 30)

# --- CHAT SYSTEM MODEL CLASSES ---
# These classes are needed by src.core.chat

class ResponseType(str, Enum):
    """Types of chat responses."""
    NORMAL = "normal"
    ERROR = "error"
    SYSTEM = "system"
    RESEARCH = "research"
    STREAMING = "streaming"
    THINKING = "thinking"
    LOADING = "loading"

class PersonaType(str, Enum):
    """Types of personas."""
    DEFAULT = "default"
    CUSTOM = "custom"
    SYSTEM = "system"
    EXPERT = "expert"
    ASSISTANT = "assistant"

class MessageRole(str, Enum):
    """Roles for message participants."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    FUNCTION = "function"
    
@dataclass
class ChatMetadata:
    """Metadata for chat responses."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    response_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request_id: Optional[str] = None
    duration_ms: Optional[float] = None
    model: Optional[str] = None
    tokens: Optional[Dict[str, int]] = None
    sources: List[Dict[str, Any]] = field(default_factory=list)
    thinking_steps: List[str] = field(default_factory=list)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    context_type: Optional[str] = None
    custom_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MessageMetadata:
    """Metadata for individual messages."""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    client_info: Optional[Dict[str, Any]] = None
    context_info: Optional[Dict[str, Any]] = None
    custom_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Message:
    """Model for chat messages."""
    role: MessageRole
    content: str
    metadata: MessageMetadata = field(default_factory=MessageMetadata)
    
    def __post_init__(self):
        """Validate message after initialization."""
        if not isinstance(self.role, MessageRole):
            self.role = MessageRole(self.role)
        if not self.content:
            self.content = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "role": self.role.value,
            "content": self.content,
            "metadata": {
                "message_id": self.metadata.message_id,
                "timestamp": self.metadata.timestamp,
                "user_id": self.metadata.user_id,
                "session_id": self.metadata.session_id,
                "client_info": self.metadata.client_info,
                "context_info": self.metadata.context_info,
                "custom_data": self.metadata.custom_data
            }
        }

@dataclass
class ChatResponse:
    """Model for chat responses."""
    content: str
    response_type: ResponseType = ResponseType.NORMAL
    metadata: Optional[ChatMetadata] = None
    thinking: Optional[str] = None
    sources: List[Dict[str, Any]] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate response after initialization."""
        if not isinstance(self.response_type, ResponseType):
            self.response_type = ResponseType(self.response_type)
        if self.metadata is None:
            self.metadata = ChatMetadata()

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary."""
        return {
            "content": self.content,
            "response_type": self.response_type.value,
            "metadata": {
                "timestamp": self.metadata.timestamp if self.metadata else datetime.now().isoformat(),
                "response_id": self.metadata.response_id if self.metadata else str(uuid.uuid4()),
                "request_id": self.metadata.request_id if self.metadata else None,
                "duration_ms": self.metadata.duration_ms if self.metadata else None,
                "model": self.metadata.model if self.metadata else None,
                "tokens": self.metadata.tokens if self.metadata else None,
                "sources": self.metadata.sources if self.metadata else [],
                "thinking_steps": self.metadata.thinking_steps if self.metadata else [],
                "citations": self.metadata.citations if self.metadata else [],
                "context_type": self.metadata.context_type if self.metadata else None,
                "custom_data": self.metadata.custom_data if self.metadata else {}
            },
            "thinking": self.thinking,
            "sources": self.sources
        }
        
@dataclass
class UserPreferences:
    """User preferences for chat interaction."""
    theme: str = "default"
    notifications: bool = True
    message_history: bool = True
    auto_citations: bool = True
    language: str = "en"
    verbose_responses: bool = False
    research_depth: int = 3
    content_filtering: bool = True
    max_message_length: int = 2000
    timezone: Optional[str] = None
    custom_settings: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert preferences to dictionary."""
        return {
            "theme": self.theme,
            "notifications": self.notifications,
            "message_history": self.message_history,
            "auto_citations": self.auto_citations,
            "language": self.language,
            "verbose_responses": self.verbose_responses,
            "research_depth": self.research_depth,
            "content_filtering": self.content_filtering,
            "max_message_length": self.max_message_length,
            "timezone": self.timezone,
            "custom_settings": self.custom_settings
        }

@dataclass
class User:
    """User model for chat system."""
    id: str
    username: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())
    permissions: List[str] = field(default_factory=list)
    preferences: UserPreferences = field(default_factory=UserPreferences)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate user after initialization."""
        if not self.id:
            raise ValueError("User ID cannot be empty")
        if not self.username:
            raise ValueError("Username cannot be empty")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "permissions": self.permissions,
            "preferences": self.preferences.to_dict(),
            "metadata": self.metadata
        }

@dataclass
class Persona:
    """Persona model for chat interactions."""
    id: str
    name: str
    description: str
    persona_type: PersonaType = PersonaType.CUSTOM
    system_prompt: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def __post_init__(self):
        """Validate persona after initialization."""
        if not self.id:
            raise ValueError("Persona ID cannot be empty")
        if not self.name:
            raise ValueError("Persona name cannot be empty")
        if not isinstance(self.persona_type, PersonaType):
            self.persona_type = PersonaType(self.persona_type)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert persona to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "persona_type": self.persona_type.value,
            "system_prompt": self.system_prompt,
            "parameters": self.parameters,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

@dataclass
class MemoryType(str, Enum):
    """Types of memory entries."""
    CONVERSATION = "conversation"
    RESEARCH = "research"
    PREFERENCE = "preference"
    CONTEXT = "context"
    KNOWLEDGE = "knowledge"
    TASK = "task"
    
class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    SEARCHING = "searching"
    SCRAPING = "scraping"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    IN_PROGRESS = "in_progress"

    def is_active(self) -> bool:
        """Check if status is active."""
        return self in {
            self.PENDING,
            self.SEARCHING,
            self.SCRAPING,
            self.ANALYZING,
            self.IN_PROGRESS
        }

    def is_terminal(self) -> bool:
        """Check if status is terminal."""
        return self in {
            self.COMPLETED,
            self.FAILED,
            self.CANCELLED
        }

class TaskPriority(str, Enum):
    """Priority levels for research tasks."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    def get_timeout(self) -> int:
        """Get timeout in seconds based on priority."""
        timeouts = {
            self.HIGH: 300,   # 5 minutes
            self.MEDIUM: 600, # 10 minutes
            self.LOW: 1200    # 20 minutes
        }
        return timeouts.get(self, 600)

    def get_max_retries(self) -> int:
        """Get maximum number of retries based on priority."""
        retries = {
            self.HIGH: 5,
            self.MEDIUM: 3,
            self.LOW: 1
        }
        return retries.get(self, 3)

class ResearchType(str, Enum):
    """Types of research operations."""
    URL_VALIDATION = "url_validation"
    WEB_SEARCH = "web_search"
    DEEP_ANALYSIS = "deep_analysis"
    DEEP_RESEARCH = "deep_research"
    FACT_CHECK = "fact_check"
    MULTI_SOURCE = "multi_source"
    SUMMARY = "summary"
    COMPARISON = "comparison"

    def get_depth(self) -> int:
        """Get default research depth."""
        depths = {
            self.URL_VALIDATION: 1,
            self.WEB_SEARCH: 3,
            self.DEEP_ANALYSIS: 5,
            self.DEEP_RESEARCH: 7,
            self.FACT_CHECK: 4,
            self.MULTI_SOURCE: 4,
            self.SUMMARY: 2,
            self.COMPARISON: 3
        }
        return depths.get(self, 3)

    def get_reliability_threshold(self) -> float:
        """Get minimum source reliability threshold."""
        thresholds = {
            self.WEB_SEARCH: 0.6,
            self.DEEP_ANALYSIS: 0.8,
            self.FACT_CHECK: 0.85,
            self.MULTI_SOURCE: 0.75,
            self.SUMMARY: 0.7,
            self.COMPARISON: 0.75
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
    DATASET = "dataset"
    OTHER = "other"

    def get_base_reliability(self) -> float:
        """Get base reliability score for source type."""
        scores = {
            self.SCHOLARLY: 0.9,
            self.SCIENTIFIC: 0.9,
            self.GOVERNMENT: 0.9,
            self.TECHNICAL: 0.8,
            self.NEWS: 0.7,
            self.WEBPAGE: 0.5,
            self.REFERENCE: 0.8,
            self.SOCIAL: 0.3,
            self.DATASET: 0.85,
            self.OTHER: 0.4
        }
        return scores.get(self, 0.4)
class SourceReliability(str, Enum):
    """Reliability ratings for research sources."""
    VERIFIED = "verified"     # Verified by trusted authorities
    HIGH = "high"            # Highly reliable source
    MEDIUM = "medium"        # Moderately reliable
    LOW = "low"             # Low reliability
    UNKNOWN = "unknown"      # Reliability not determined
    UNRELIABLE = "unreliable" # Known unreliable source

    def get_score(self) -> float:
        """Get numerical reliability score."""
        scores = {
            self.VERIFIED: 1.0,
            self.HIGH: 0.8,
            self.MEDIUM: 0.6,
            self.LOW: 0.4,
            self.UNKNOWN: 0.2,
            self.UNRELIABLE: 0.0
        }
        return scores.get(self, 0.0)

@dataclass
class BrowserConfig:
    """Configuration for browser automation."""
    headless: bool = True
    window_size: Tuple[int, int] = (1920, 1080)
    screenshot_dir: Optional[Path] = None
    download_dir: Optional[Path] = None
    timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 1.0
    options: Dict[str, Any] = field(default_factory=lambda: {
        "no-sandbox": None,
        "disable-dev-shm-usage": None,
        "disable-gpu": None,
        "disable-extensions": None,
        "disable-notifications": None
    })
    request_headers: Dict[str, str] = field(default_factory=lambda: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "DNT": "1"
    })

    def __post_init__(self):
        """Validate and initialize browser configuration."""
        if self.screenshot_dir is not None and isinstance(self.screenshot_dir, str):
            self.screenshot_dir = Path(self.screenshot_dir)
        if self.download_dir is not None and isinstance(self.download_dir, str):
            self.download_dir = Path(self.download_dir)
        
        # Validate timeout and retry settings
        if self.timeout < 0:
            raise ValueError("Timeout must be non-negative")
        if self.retry_attempts < 0:
            raise ValueError("Retry attempts must be non-negative")
        if self.retry_delay < 0:
            raise ValueError("Retry delay must be non-negative")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'headless': self.headless,
            'window_size': self.window_size,
            'screenshot_dir': str(self.screenshot_dir) if self.screenshot_dir else None,
            'download_dir': str(self.download_dir) if self.download_dir else None,
            'timeout': self.timeout,
            'retry_attempts': self.retry_attempts,
            'retry_delay': self.retry_delay,
            'options': self.options,
            'request_headers': self.request_headers
        }

@dataclass
class ResearchResult:
    """Model for research operation results."""
    query: str
    research_type: ResearchType
    findings: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]
    summary: Optional[str] = None
    analysis: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def __post_init__(self):
        """Validate result after initialization."""
        if not self.query:
            raise ValueError("Query cannot be empty")
        if not isinstance(self.research_type, ResearchType):
            raise ValueError("Invalid research type")
        if not isinstance(self.findings, list):
            raise ValueError("Findings must be a list")
        if not isinstance(self.sources, list):
            raise ValueError("Sources must be a list")

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            'result_id': self.result_id,
            'query': self.query,
            'research_type': self.research_type.value,
            'findings': self.findings,
            'sources': self.sources,
            'summary': self.summary,
            'analysis': self.analysis,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchResult':
        """Create result from dictionary."""
        if 'research_type' in data:
            data['research_type'] = ResearchType(data['research_type'])
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)
        
@dataclass
class ResearchTask:
    """Model for research tasks."""
    id: str
    description: str
    research_type: ResearchType = ResearchType.WEB_SEARCH
    status: TaskStatus = TaskStatus.PENDING
    depth: int = field(default_factory=lambda: ResearchType.WEB_SEARCH.get_depth())
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.MEDIUM
    validation_level: ValidationLevel = ValidationLevel.MEDIUM
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: Optional[int] = None
    require_citations: bool = False
    browser_config: Optional[BrowserConfig] = None
    reliability_threshold: Optional[float] = None

    def __post_init__(self):
        """Initialize after creation."""
        if not self.id:
            raise ValueError("Task ID cannot be empty")
        if not self.description:
            raise ValueError("Task description cannot be empty")
        
        # Set reliability threshold based on research type
        if self.reliability_threshold is None:
            self.reliability_threshold = self.research_type.get_reliability_threshold()
            
        # Set timeout based on priority if not specified
        if self.timeout is None:
            self.timeout = self.priority.get_timeout()

    def update_status(self, new_status: TaskStatus, error: Optional[str] = None) -> None:
        """Update task status."""
        self.status = new_status
        if error:
            self.error = error
        
        if new_status == TaskStatus.COMPLETED:
            self.completed_at = datetime.now().isoformat()

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
            'result': self.result,
            'metadata': self.metadata,
            'priority': self.priority.value,
            'validation_level': self.validation_level.value,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'timeout': self.timeout,
            'require_citations': self.require_citations,
            'browser_config': self.browser_config.to_dict() if self.browser_config else None,
            'reliability_threshold': self.reliability_threshold
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchTask':
        """Create task from dictionary."""
        if 'research_type' in data:
            data['research_type'] = ResearchType(data['research_type'])
        if 'status' in data:
            data['status'] = TaskStatus(data['status'])
        if 'priority' in data:
            data['priority'] = TaskPriority(data['priority'])
        if 'validation_level' in data:
            data['validation_level'] = ValidationLevel(data['validation_level'])
        if 'browser_config' in data and data['browser_config']:
            data['browser_config'] = BrowserConfig(**data['browser_config'])
        return cls(**data)
        
@dataclass
class ResearchSource:
    """Model for research sources."""
    url: str
    source_type: SourceType
    reliability: SourceReliability
    title: Optional[str] = None
    published_date: Optional[str] = None
    validation_level: ValidationLevel = ValidationLevel.MEDIUM
    metadata: Dict[str, Any] = field(default_factory=dict)
    content: Optional[str] = None
    summary: Optional[str] = None
    extracted_at: Optional[str] = None
    citation_count: int = 0
    references: List[str] = field(default_factory=list)
    authors: List[str] = field(default_factory=list)
    domain: Optional[str] = None
    last_updated: Optional[str] = None
    content_hash: Optional[str] = None
    word_count: int = 0
    verification_status: Optional[str] = None
    archive_url: Optional[str] = None
    language: str = "en"
    license_info: Optional[str] = None
    content_type: Optional[str] = None

    def __post_init__(self):
        """Validate source after initialization."""
        if not self.url:
            raise ValueError("URL cannot be empty")
        if not isinstance(self.source_type, SourceType):
            raise ValueError("Invalid source type")
        if not isinstance(self.reliability, SourceReliability):
            raise ValueError("Invalid reliability rating")
        if not isinstance(self.validation_level, ValidationLevel):
            raise ValueError("Invalid validation level")

    def calculate_content_hash(self) -> None:
        """Calculate hash of content for deduplication."""
        if self.content:
            import hashlib
            self.content_hash = hashlib.sha256(
                self.content.encode('utf-8')
            ).hexdigest()

    def update_word_count(self) -> None:
        """Update word count of content."""
        if self.content:
            self.word_count = len(self.content.split())

    def to_dict(self) -> Dict[str, Any]:
        """Convert source to dictionary."""
        return {
            'url': self.url,
            'source_type': self.source_type.value,
            'reliability': self.reliability.value,
            'title': self.title,
            'published_date': self.published_date,
            'validation_level': self.validation_level.value,
            'metadata': self.metadata,
            'content': self.content,
            'summary': self.summary,
            'extracted_at': self.extracted_at,
            'citation_count': self.citation_count,
            'references': self.references,
            'authors': self.authors,
            'domain': self.domain,
            'last_updated': self.last_updated,
            'content_hash': self.content_hash,
            'word_count': self.word_count,
            'verification_status': self.verification_status,
            'archive_url': self.archive_url,
            'language': self.language,
            'license_info': self.license_info,
            'content_type': self.content_type
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchSource':
        """Create source from dictionary."""
        if 'source_type' in data:
            data['source_type'] = SourceType(data['source_type'])
        if 'reliability' in data:
            data['reliability'] = SourceReliability(data['reliability'])
        if 'validation_level' in data:
            data['validation_level'] = ValidationLevel(data['validation_level'])
        return cls(**data)
        
@dataclass
class ResearchFinding:
    """Model for individual research findings."""
    content: str
    source: str
    source_type: SourceType = SourceType.OTHER
    reliability: SourceReliability = SourceReliability.UNKNOWN
    research_source: ResearchType = ResearchType.WEB_SEARCH
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    analysis: Optional[Dict[str, Any]] = None
    citations: List[str] = field(default_factory=list)
    key_points: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    finding_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    related_findings: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    extracted_entities: Dict[str, List[str]] = field(default_factory=dict)
    sentiment_scores: Dict[str, float] = field(default_factory=dict)
    fact_checks: List[Dict[str, Any]] = field(default_factory=list)
    verification_status: str = "unverified"
    last_verified: Optional[str] = None
    relevance_score: float = 0.0

    def __post_init__(self):
        """Validate finding after initialization."""
        if not self.content:
            raise ValueError("Finding content cannot be empty")
        if not self.source:
            raise ValueError("Source cannot be empty")
        if not isinstance(self.source_type, SourceType):
            raise ValueError("Invalid source type")
        if not isinstance(self.reliability, SourceReliability):
            raise ValueError("Invalid reliability rating")
        if not isinstance(self.research_source, ResearchType):
            raise ValueError("Invalid research source")
        if not 0 <= self.confidence_score <= 1:
            raise ValueError("Confidence score must be between 0 and 1")
        if not 0 <= self.relevance_score <= 1:
            raise ValueError("Relevance score must be between 0 and 1")

    def add_fact_check(self, claim: str, verification: bool, evidence: str) -> None:
        """Add a fact check result."""
        self.fact_checks.append({
            'claim': claim,
            'verified': verification,
            'evidence': evidence,
            'timestamp': datetime.now().isoformat()
        })

    def update_verification(self, status: str) -> None:
        """Update verification status."""
        self.verification_status = status
        self.last_verified = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert finding to dictionary."""
        return {
            'content': self.content,
            'source': self.source,
            'source_type': self.source_type.value,
            'reliability': self.reliability.value,
            'research_source': self.research_source.value,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata,
            'analysis': self.analysis,
            'citations': self.citations,
            'key_points': self.key_points,
            'confidence_score': self.confidence_score,
            'finding_id': self.finding_id,
            'related_findings': self.related_findings,
            'categories': self.categories,
            'extracted_entities': self.extracted_entities,
            'sentiment_scores': self.sentiment_scores,
            'fact_checks': self.fact_checks,
            'verification_status': self.verification_status,
            'last_verified': self.last_verified,
            'relevance_score': self.relevance_score
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchFinding':
        """Create finding from dictionary."""
        if 'source_type' in data:
            data['source_type'] = SourceType(data['source_type'])
        if 'reliability' in data:
            data['reliability'] = SourceReliability(data['reliability'])
        if 'research_source' in data:
            data['research_source'] = ResearchType(data['research_source'])
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)
        
@dataclass
class ResearchSession:
    """Model for research sessions."""
    query: str
    research_type: ResearchType
    timestamp: datetime = field(default_factory=datetime.now)
    status: TaskStatus = TaskStatus.PENDING
    findings: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    duration: float = 0.0
    sources_analyzed: int = 0
    successful_extractions: int = 0
    failed_extractions: int = 0
    total_findings: int = 0
    error_count: int = 0
    validation_level: ValidationLevel = ValidationLevel.MEDIUM
    browser_config: Optional[BrowserConfig] = None

    def __post_init__(self):
        """Initialize session after creation."""
        if not self.query:
            raise ValueError("Query cannot be empty")
        if not isinstance(self.research_type, ResearchType):
            raise ValueError("Invalid research type")
        if not isinstance(self.validation_level, ValidationLevel):
            raise ValueError("Invalid validation level")

    def update_stats(self) -> None:
        """Update session statistics."""
        if self.end_time:
            self.duration = (self.end_time - self.start_time).total_seconds()
        self.total_findings = len(self.findings)

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary."""
        return {
            'session_id': self.session_id,
            'query': self.query,
            'research_type': self.research_type.value,
            'status': self.status.value,
            'timestamp': self.timestamp.isoformat(),
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration': self.duration,
            'sources_analyzed': self.sources_analyzed,
            'successful_extractions': self.successful_extractions,
            'failed_extractions': self.failed_extractions,
            'total_findings': self.total_findings,
            'error_count': self.error_count,
            'validation_level': self.validation_level.value,
            'browser_config': self.browser_config.to_dict() if self.browser_config else None,
            'metadata': self.metadata
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResearchSession':
        """Create session from dictionary."""
        if 'research_type' in data:
            data['research_type'] = ResearchType(data['research_type'])
        if 'status' in data:
            data['status'] = TaskStatus(data['status'])
        if 'validation_level' in data:
            data['validation_level'] = ValidationLevel(data['validation_level'])
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        if 'start_time' in data and isinstance(data['start_time'], str):
            data['start_time'] = datetime.fromisoformat(data['start_time'])
        if 'end_time' in data and isinstance(data['end_time'], str):
            data['end_time'] = datetime.fromisoformat(data['end_time'])
        if 'browser_config' in data and data['browser_config']:
            data['browser_config'] = BrowserConfig(**data['browser_config'])
        return cls(**data)
        
@dataclass
class FirecrawlConfig:
    """Configuration for Firecrawl integration."""
    api_key: str = field(default_factory=lambda: os.getenv('FIRECRAWL_API_KEY', ''))
    base_url: str = "https://api.firecrawl.dev"
    version: str = "v1"
    formats: List[str] = field(default_factory=lambda: ["markdown"])
    max_pages: int = 100
    timeout: int = 300
    poll_interval: int = 30
    exclude_paths: List[str] = field(default_factory=list)
    include_paths: List[str] = field(default_factory=list)
    request_headers: Dict[str, str] = field(default_factory=lambda: {
        "User-Agent": "Sheppard-Research-Bot/1.0",
        "Accept": "application/json"
    })
    scrape_options: Dict[str, Any] = field(default_factory=lambda: {
        "waitFor": 2000,
        "timeout": 30000,
        "removeScripts": True,
        "removeStyles": True,
        "removeTracking": True,
        "removeAds": True,
        "removeNavigation": True,
        "preserveFormatting": True
    })
    retries: int = 3
    retry_delay: float = 1.0
    concurrent_limit: int = 5
    follow_redirects: bool = True
    verify_ssl: bool = True
    respect_robots_txt: bool = True
    extract_metadata: bool = True
    extract_links: bool = True
    save_snapshots: bool = False
    snapshot_dir: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'api_key': self.api_key,
            'base_url': self.base_url,
            'version': self.version,
            'formats': self.formats,
            'max_pages': self.max_pages,
            'timeout': self.timeout,
            'poll_interval': self.poll_interval,
            'exclude_paths': self.exclude_paths,
            'include_paths': self.include_paths,
            'request_headers': self.request_headers,
            'scrape_options': self.scrape_options,
            'retries': self.retries,
            'retry_delay': self.retry_delay,
            'concurrent_limit': self.concurrent_limit,
            'follow_redirects': self.follow_redirects,
            'verify_ssl': self.verify_ssl,
            'respect_robots_txt': self.respect_robots_txt,
            'extract_metadata': self.extract_metadata,
            'extract_links': self.extract_links,
            'save_snapshots': self.save_snapshots,
            'snapshot_dir': self.snapshot_dir
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FirecrawlConfig':
        """Create configuration from dictionary."""
        return cls(**data)
        
@dataclass
class NavigationConfig:
    """Configuration for web navigation."""
    max_depth: int = 3
    follow_internal_links: bool = True
    follow_external_links: bool = False
    max_links_per_page: int = 20
    delay_between_requests: float = 0.5
    allowed_domains: Set[str] = field(default_factory=set)
    excluded_paths: Set[str] = field(default_factory=set)
    url_patterns: Set[str] = field(default_factory=set)
    requires_javascript: bool = False
    handle_redirects: bool = True
    respect_robots_txt: bool = True
    verify_ssl: bool = True

    def __post_init__(self):
        """Validate navigation configuration."""
        if self.max_depth < 1:
            raise ValueError("Maximum depth must be at least 1")
        if self.max_links_per_page < 1:
            raise ValueError("Maximum links per page must be at least 1")
        if self.delay_between_requests < 0:
            raise ValueError("Delay between requests must be non-negative")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'max_depth': self.max_depth,
            'follow_internal_links': self.follow_internal_links,
            'follow_external_links': self.follow_external_links,
            'max_links_per_page': self.max_links_per_page,
            'delay_between_requests': self.delay_between_requests,
            'allowed_domains': list(self.allowed_domains),
            'excluded_paths': list(self.excluded_paths),
            'url_patterns': list(self.url_patterns),
            'requires_javascript': self.requires_javascript,
            'handle_redirects': self.handle_redirects,
            'respect_robots_txt': self.respect_robots_txt,
            'verify_ssl': self.verify_ssl
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NavigationConfig':
        """Create configuration from dictionary."""
        if 'allowed_domains' in data and isinstance(data['allowed_domains'], list):
            data['allowed_domains'] = set(data['allowed_domains'])
        if 'excluded_paths' in data and isinstance(data['excluded_paths'], list):
            data['excluded_paths'] = set(data['excluded_paths'])
        if 'url_patterns' in data and isinstance(data['url_patterns'], list):
            data['url_patterns'] = set(data['url_patterns'])
        return cls(**data)

@dataclass
class ScrapingConfig:
    """Configuration for web scraping."""
    user_agent: str = "Sheppard-Research-Bot/1.0"
    enable_javascript: bool = False
    extract_text_only: bool = True
    enable_images: bool = False
    enable_videos: bool = False
    max_scrape_time: int = 60
    wait_for_selectors: List[str] = field(default_factory=list)
    extract_metadata: bool = True
    preserve_formatting: bool = True
    remove_ads: bool = True
    remove_navigation: bool = True
    remove_social: bool = True
    extract_schema_org: bool = True
    extract_opengraph: bool = True
    extract_microdata: bool = True
    text_content_selectors: List[str] = field(default_factory=lambda: [
        "article", "main", "[role='main']",
        ".content", "#content", ".article"
    ])
    ignore_elements: Set[str] = field(default_factory=lambda: {
        "script", "style", "noscript", "iframe",
        "header", "footer", "nav", "aside"
    })

    def __post_init__(self):
        """Validate scraping configuration."""
        if self.max_scrape_time < 1:
            raise ValueError("Maximum scrape time must be at least 1 second")
        if not self.user_agent:
            raise ValueError("User agent cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'user_agent': self.user_agent,
            'enable_javascript': self.enable_javascript,
            'extract_text_only': self.extract_text_only,
            'enable_images': self.enable_images,
            'enable_videos': self.enable_videos,
            'max_scrape_time': self.max_scrape_time,
            'wait_for_selectors': self.wait_for_selectors,
            'extract_metadata': self.extract_metadata,
            'preserve_formatting': self.preserve_formatting,
            'remove_ads': self.remove_ads,
            'remove_navigation': self.remove_navigation,
            'remove_social': self.remove_social,
            'extract_schema_org': self.extract_schema_org,
            'extract_opengraph': self.extract_opengraph,
            'extract_microdata': self.extract_microdata,
            'text_content_selectors': self.text_content_selectors,
            'ignore_elements': list(self.ignore_elements)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScrapingConfig':
        """Create configuration from dictionary."""
        if 'ignore_elements' in data and isinstance(data['ignore_elements'], list):
            data['ignore_elements'] = set(data['ignore_elements'])
        return cls(**data)
        
@dataclass
class ContentProcessingConfig:
    """Configuration for content processing."""
    max_content_length: int = 1000000
    chunk_size: int = 1000
    chunk_overlap: int = 100
    min_chunk_length: int = 100
    extract_metadata: bool = True
    preserve_formatting: bool = True
    remove_duplicates: bool = True
    extract_citations: bool = True
    extract_quotes: bool = True
    extract_dates: bool = True
    extract_statistics: bool = True
    normalize_whitespace: bool = True
    strip_html: bool = True
    minimum_content_length: int = 50
    maximum_content_length: int = 100000
    summarization_params: Dict[str, Any] = field(default_factory=lambda: {
        'max_length': 1000,
        'min_length': 100,
        'do_sample': False
    })

    def __post_init__(self):
        """Validate content processing configuration."""
        if self.chunk_size < 1:
            raise ValueError("Chunk size must be at least 1")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap must be less than chunk size")
        if self.min_chunk_length < 1:
            raise ValueError("Minimum chunk length must be at least 1")
        if self.minimum_content_length < 1:
            raise ValueError("Minimum content length must be at least 1")
        if self.maximum_content_length < self.minimum_content_length:
            raise ValueError("Maximum content length must be greater than minimum content length")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'max_content_length': self.max_content_length,
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'min_chunk_length': self.min_chunk_length,
            'extract_metadata': self.extract_metadata,
            'preserve_formatting': self.preserve_formatting,
            'remove_duplicates': self.remove_duplicates,
            'extract_citations': self.extract_citations,
            'extract_quotes': self.extract_quotes,
            'extract_dates': self.extract_dates,
            'extract_statistics': self.extract_statistics,
            'normalize_whitespace': self.normalize_whitespace,
            'strip_html': self.strip_html,
            'minimum_content_length': self.minimum_content_length,
            'maximum_content_length': self.maximum_content_length,
            'summarization_params': self.summarization_params
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContentProcessingConfig':
        """Create configuration from dictionary."""
        return cls(**data)

@dataclass
class ResearchConfig:
    """Main research system configuration."""
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    navigation: NavigationConfig = field(default_factory=NavigationConfig)
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)
    content: ContentProcessingConfig = field(default_factory=ContentProcessingConfig)
    firecrawl: Optional[FirecrawlConfig] = None
    
    # System settings
    max_retries: int = 3
    retry_delay: float = 2.0
    max_pages: int = 5
    min_reliability: float = 0.7
    chunk_size: int = 1000
    chunk_overlap: int = 100
    max_concurrent_tasks: int = 5
    task_timeout: int = 600
    embed_findings: bool = True
    save_results: bool = True
    results_dir: Optional[Path] = None
    log_level: str = "INFO"
    auto_save_interval: int = 300  # 5 minutes
    max_memory_usage: int = 1024  # MB
    cleanup_interval: int = 3600  # 1 hour
    max_task_history: int = 1000
    enable_diagnostics: bool = True
    diagnostic_interval: int = 60  # 1 minute
    error_threshold: int = 5  # Max consecutive errors before fallback
    fallback_mode: bool = True
    recovery_delay: int = 300  # 5 minutes
    max_recovery_attempts: int = 3
    
def __post_init__(self):
        """Validate and initialize research configuration."""
        # Convert paths
        if self.results_dir is not None and isinstance(self.results_dir, str):
            self.results_dir                                                                            
