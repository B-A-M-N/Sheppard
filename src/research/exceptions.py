"""
Research system exceptions for enhanced web content processing and Firecrawl integration.
File: src/research/exceptions.py
"""

from typing import Dict, Any, Optional
from datetime import datetime
import logging

from src.core.base_exceptions import ChatSystemError

logger = logging.getLogger(__name__)

class ResearchError(ChatSystemError):
    """Base exception for research-related errors."""
    def __init__(
        self, 
        message: str = "Research operation failed",
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        if details:
            from src.utils.validation import validate_dict_fields
            is_valid, error = validate_dict_fields(details, {}, {})
            if not is_valid:
                logger.warning(f"Invalid exception details: {error}. Omitting details.")
                details = None
        
        self.details = details or {}
        self.error_code = error_code
        self.timestamp = datetime.now().isoformat()
        
        formatted_message = f"Research Error: {message}"
        if error_code:
            formatted_message = f"[{error_code}] {formatted_message}"
        if self.details:
            formatted_message += f"\nDetails: {self.details}"
            
        super().__init__(formatted_message)
        
        logger.error(
            f"Research error occurred: {message}",
            extra={
                "error_code": error_code,
                "details": self.details,
                "timestamp": self.timestamp
            }
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary."""
        return {
            "error": str(self),
            "type": self.__class__.__name__,
            "error_code": self.error_code,
            "details": self.details,
            "timestamp": self.timestamp
        }

class FirecrawlError(ResearchError):
    """Raised when Firecrawl operations fail."""
    def __init__(
        self,
        message: str = "Firecrawl operation failed",
        api_response: Optional[Dict[str, Any]] = None,
        request_details: Optional[Dict[str, Any]] = None
    ):
        details = {
            "api_response": api_response,
            "request_details": request_details,
            "service": "firecrawl"
        }
        super().__init__(
            message=f"Firecrawl Error: {message}",
            details=details,
            error_code="FIRECRAWL_ERROR"
        )

class BrowserError(ResearchError):
    """Raised when browser operations fail."""
    def __init__(
        self,
        message: str = "Browser operation failed",
        url: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        error_details = details or {}
        if url:
            error_details["url"] = url
            message = f"{message} for URL: {url}"
        super().__init__(message, error_details, "BROWSER_ERROR")

class BrowserNotInitializedError(BrowserError):
    """Raised when browser is not initialized."""
    def __init__(self, operation: str = "browser operation"):
        super().__init__(
            f"Browser not initialized before attempting {operation}",
            details={"operation": operation},
        )

class URLValidationError(ResearchError):
    """Raised when URL validation fails."""
    def __init__(
        self,
        url: str,
        reason: str,
        validation_details: Optional[Dict[str, Any]] = None
    ):
        details = {
            "url": url,
            "validation_details": validation_details or {},
            "timestamp": datetime.now().isoformat()
        }
        super().__init__(
            message=f"URL Validation failed for {url}: {reason}",
            details=details,
            error_code="URL_VALIDATION_ERROR"
        )

class ContentExtractionError(ResearchError):
    """Raised when content extraction fails."""
    def __init__(
        self,
        message: str = "Content extraction failed",
        source_url: Optional[str] = None,
        format_type: Optional[str] = None,
        extraction_details: Optional[Dict[str, Any]] = None  
    ):
        details = {
            "source_url": source_url,
            "format_type": format_type,
            "extraction_details": extraction_details or {}
        }
        super().__init__(
            message=f"Content extraction failed: {message}",
            details=details,
            error_code="EXTRACTION_ERROR"
        )

class ProcessingError(ResearchError):
    """Raised when content processing fails."""
    def __init__(
        self,
        message: str = "Processing failed",
        stage: Optional[str] = None,
        content_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        error_details = details or {}
        if stage:
            error_details["stage"] = stage
        if content_type:
            error_details["content_type"] = content_type
            
        error_code = f"PROC_ERROR_{stage.upper()}" if stage else "PROC_ERROR"
        super().__init__(message, error_details, error_code)

class TaskError(ResearchError):
    """Raised when research task operations fail."""
    def __init__(
        self,
        message: str = "Task operation failed",
        task_id: Optional[str] = None,
        task_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None    
    ):
        error_details = details or {}
        if task_id:
            error_details["task_id"] = task_id
        if task_type:
            error_details["task_type"] = task_type
            
        error_code = f"TASK_ERROR_{task_type.upper()}" if task_type else "TASK_ERROR"
        super().__init__(message, error_details, error_code)

class TaskNotFoundError(ResearchError):
    """Raised when a research task is not found.""" 
    def __init__(
        self,
        task_id: str,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"Research task not found: {task_id}"
        super().__init__(message, details, "TASK_NOT_FOUND")
        
class DependencyError(ResearchError):
    """Raised when a required dependency is missing or unavailable."""
    def __init__(
        self,
        dependency: str,
        required_for: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"Required dependency unavailable: {dependency}"
        if required_for:
            message += f" (required for {required_for})"
        super().__init__(message, details, "DEPENDENCY_ERROR")
        
class ExtractionError(ResearchError):
    """Raised when data extraction fails."""
    def __init__(
        self,
        message: str = "Data extraction failed",
        source: Optional[str] = None,
        extraction_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None  
    ):
        error_details = details or {}
        if source:
            error_details["source"] = source
        if extraction_type:
            error_details["extraction_type"] = extraction_type
            
        error_code = f"EXTRACTION_{extraction_type.upper()}" if extraction_type else "EXTRACTION_ERROR"
        super().__init__(message, error_details, error_code)
        
class ResearchTimeout(ResearchError):
    """Raised when a research operation times out."""
    def __init__(
        self,
        operation: str,
        timeout: float,
        details: Optional[Dict[str, Any]] = None
    ):  
        message = f"Research operation timed out after {timeout} seconds: {operation}"
        super().__init__(message, details, "RESEARCH_TIMEOUT")

class BrowserTimeout(ResearchError):
    """Raised when a browser operation times out."""
    def __init__(
        self,
        operation: str,
        url: Optional[str] = None,
        timeout: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        error_details = details or {}
        if url:
            error_details["url"] = url
        if timeout:
            error_details["timeout"] = timeout
            
        message = f"Browser operation timed out: {operation}"
        if timeout:
            message += f" after {timeout} seconds"
        if url:
            message += f" for URL: {url}"
            
        super().__init__(message, error_details, "BROWSER_TIMEOUT")

class SessionError(ResearchError):
    """Raised when research session operations fail."""
    def __init__(
        self,
        message: str = "Session operation failed",
        session_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        error_details = details or {}
        if session_id:
            error_details["session_id"] = session_id
            message = f"{message} for session: {session_id}"
        super().__init__(message, error_details, "SESSION_ERROR")

class ValidationError(ResearchError):
    """Raised when validation fails."""
    def __init__(
        self,
        message: str = "Validation failed",
        validation_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        error_details = details or {}
        if validation_type:
            error_details["validation_type"] = validation_type
            
        error_code = f"VALIDATION_ERROR_{validation_type.upper()}" if validation_type else "VALIDATION_ERROR"
        super().__init__(message, error_details, error_code)

class InitializationError(ResearchError):
    """Raised when system initialization fails."""
    def __init__(
        self,
        component: str,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        error_details = details or {}
        if cause:
            error_details["cause"] = str(cause)
            
        message = f"Failed to initialize {component}"
        if cause:
            message += f": {str(cause)}"
            
        super().__init__(message, error_details, "INIT_ERROR")
