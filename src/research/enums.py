"""
Research system enumerations with URL reliability ratings.
File: src/research/enums.py
"""

from enum import Enum
from typing import Dict, Any

class ErrorType(str, Enum):
    """Error types for research operations."""
    VALIDATION = "validation"
    BROWSER = "browser"
    NETWORK = "network"
    TIMEOUT = "timeout"
    PROCESSING = "processing"
    EXTRACTION = "extraction"
    STORAGE = "storage"
    UNKNOWN = "unknown"

    def get_retry_count(self) -> int:
        """Get retry attempts for error type."""
        retries = {
            self.NETWORK: 3,
            self.TIMEOUT: 2,
            self.BROWSER: 1,
            self.PROCESSING: 1
        }
        return retries.get(self, 0)

class ResearchStatus(str, Enum):
    """Research session status."""
    NOT_STARTED = "not_started"
    STARTED = "started"
    SEARCHING = "searching"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"

    def is_active(self) -> bool:
        """Check if status is active."""
        return self in {
            self.STARTED,
            self.SEARCHING,
            self.PROCESSING
        }

    def is_terminal(self) -> bool:
        """Check if status is terminal."""
        return self in {
            self.COMPLETED,
            self.ERROR,
            self.CANCELLED
        }

class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    
    def is_terminal(self) -> bool:
        """Check if status is terminal."""
        return self in {
            self.COMPLETED,
            self.FAILED,
            self.CANCELLED,
            self.TIMEOUT
        }
    
    def is_active(self) -> bool:
        """Check if status is active."""
        return self in {self.PENDING, self.IN_PROGRESS}

class URLSourceType(str, Enum):
    """Types of URL sources."""
    ACADEMIC = "academic"        # .edu domains
    GOVERNMENT = "government"    # .gov domains
    SCIENTIFIC = "scientific"    # Scientific/research sites
    TECHNICAL = "technical"      # Technical documentation
    NEWS = "news"               # News organizations
    BLOG = "blog"               # Blog posts
    SOCIAL = "social"           # Social media
    COMMERCIAL = "commercial"   # Commercial sites
    OTHER = "other"            # Other sources

    def get_base_reliability(self) -> float:
        """Get base reliability score for source type."""
        scores = {
            self.ACADEMIC: 0.95,
            self.GOVERNMENT: 0.95,
            self.SCIENTIFIC: 0.90,
            self.TECHNICAL: 0.85,
            self.NEWS: 0.70,
            self.BLOG: 0.50,
            self.SOCIAL: 0.30,
            self.COMMERCIAL: 0.60,
            self.OTHER: 0.40
        }
        return scores.get(self, 0.40)

class URLReliability(str, Enum):
    """URL reliability ratings."""
    VERIFIED = "verified"       # Manually verified source
    HIGH = "high"              # Highly reliable source
    MEDIUM = "medium"          # Moderately reliable
    LOW = "low"               # Low reliability
    UNKNOWN = "unknown"        # Reliability unknown
    BLOCKED = "blocked"        # Known unreliable/blocked

    def get_score(self) -> float:
        """Get reliability score."""
        scores = {
            self.VERIFIED: 1.0,
            self.HIGH: 0.9,
            self.MEDIUM: 0.7,
            self.LOW: 0.4,
            self.UNKNOWN: 0.2,
            self.BLOCKED: 0.0
        }
        return scores.get(self, 0.0)

class DomainTrust(str, Enum):
    """Domain trust levels."""
    TRUSTED = "trusted"         # Known trusted domains
    VERIFIED = "verified"       # Verified but not trusted
    NEUTRAL = "neutral"         # No trust information
    SUSPICIOUS = "suspicious"   # Potentially untrustworthy
    BLOCKED = "blocked"         # Known untrustworthy

    def get_score(self) -> float:
        """Get trust score."""
        scores = {
            self.TRUSTED: 1.0,
            self.VERIFIED: 0.8,
            self.NEUTRAL: 0.5,
            self.SUSPICIOUS: 0.2,
            self.BLOCKED: 0.0
        }
        return scores.get(self, 0.5)

class ContentType(str, Enum):
    """Content types for processing."""
    MARKDOWN = "markdown"
    HTML = "html"
    TEXT = "text"
    JSON = "json"
    ARTICLE = "article"
    CODE = "code"
    TABLE = "table"
    LIST = "list"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"

class ProcessingStage(str, Enum):
    """Content processing stages."""
    URL_VALIDATION = "url_validation"
    CONTENT_EXTRACTION = "content_extraction"
    MARKDOWN_CONVERSION = "markdown_conversion"
    CONTENT_ANALYSIS = "content_analysis"
    SUMMARIZATION = "summarization"
    INTEGRATION = "integration"

    def get_timeout(self) -> int:
        """Get stage timeout in seconds."""
        timeouts = {
            self.URL_VALIDATION: 30,
            self.CONTENT_EXTRACTION: 120,
            self.MARKDOWN_CONVERSION: 60,
            self.CONTENT_ANALYSIS: 180,
            self.SUMMARIZATION: 60,
            self.INTEGRATION: 30
        }
        return timeouts.get(self, 60)

class ResearchType(str, Enum):
    """Types of research operations."""
    URL_VALIDATION = "url_validation"
    WEB_SEARCH = "web_search"
    DEEP_ANALYSIS = "deep_analysis"
    FACT_CHECK = "fact_check"

    def get_depth(self) -> int:
        """Get research depth."""
        depths = {
            self.URL_VALIDATION: 1,
            self.WEB_SEARCH: 3,
            self.DEEP_ANALYSIS: 5,
            self.FACT_CHECK: 4
        }
        return depths.get(self, 3)

class ValidationLevel(str, Enum):
    """Validation strictness levels."""
    HIGH = "high"      # Strict validation
    MEDIUM = "medium"  # Standard validation
    LOW = "low"       # Basic validation
    NONE = "none"     # No validation

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

    def get_retry_count(self) -> int:
        """Get number of retry attempts for each level."""
        retries = {
            self.HIGH: 3,     # Multiple retries
            self.MEDIUM: 2,   # Two retries
            self.LOW: 1,      # Single retry
            self.NONE: 0      # No retries
        }
        return retries.get(self, 2)

def get_enum_values(enum_class: type) -> Dict[str, Any]:
    """Get dictionary of enum values."""
    return {item.name: item.value for item in enum_class}

def get_enum_by_value(enum_class: type, value: str) -> Any:
    """Get enum member by value."""
    try:
        return next(item for item in enum_class if item.value == value)
    except StopIteration:
        raise ValueError(f"No {enum_class.__name__} with value: {value}")
