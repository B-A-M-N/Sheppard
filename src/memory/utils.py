"""
Utility functions for memory management and processing.
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from src.config.logging import get_logger

logger = get_logger(__name__)

def generate_memory_id(content: str, timestamp: Optional[str] = None) -> str:
    """
    Generate a unique memory ID based on content and timestamp.
    
    Args:
        content: Memory content
        timestamp: Optional timestamp (defaults to current UTC time)
    
    Returns:
        str: Unique memory ID
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    
    # Create unique string combining content and timestamp
    unique_string = f"{content}{timestamp}"
    
    # Generate SHA-256 hash and take first 12 characters
    hash_object = hashlib.sha256(unique_string.encode())
    return f"mem_{hash_object.hexdigest()[:12]}"

def extract_memory_type(content: str) -> str:
    """
    Determine memory type based on content analysis.
    
    Args:
        content: Memory content
    
    Returns:
        str: Memory type classification
    """
    content_lower = content.lower()
    
    # Check for different types of content
    if any(word in content_lower for word in ['favorite', 'prefer', 'like', 'love', 'hate', 'dislike']):
        return 'preference'
    elif any(word in content_lower for word in ['always', 'never', 'must', 'should', 'rule']):
        return 'rule'
    elif any(word in content_lower for word in ['remember', 'recall', 'note', 'important']):
        return 'important'
    else:
        return 'general'

def create_memory_metadata(
    content: str,
    memory_type: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create standardized metadata for a memory.
    
    Args:
        content: Memory content
        memory_type: Optional explicit memory type
        extra_metadata: Additional metadata to include
    
    Returns:
        Dict[str, Any]: Structured metadata
    """
    metadata = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'type': memory_type or extract_memory_type(content),
        'length': len(content),
        'word_count': len(content.split())
    }
    
    if extra_metadata:
        metadata.update(extra_metadata)
    
    return metadata

def validate_memory_content(content: str) -> Tuple[bool, Optional[str]]:
    """
    Validate memory content for storage.
    
    Args:
        content: Memory content to validate
    
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    # Check for empty content
    if not content or not content.strip():
        return False, "Memory content cannot be empty"
    
    # Check length limits
    if len(content) > 10000:
        return False, "Memory content exceeds maximum length (10000 characters)"
    
    # Check for basic content requirements
    if len(content.split()) < 2:
        return False, "Memory content must contain at least two words"
    
    return True, None

def process_memory_for_storage(
    content: str,
    extra_metadata: Optional[Dict[str, Any]] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Process and prepare memory content for storage.
    
    Args:
        content: Raw memory content
        extra_metadata: Additional metadata to include
    
    Returns:
        Tuple[str, Dict[str, Any]]: (processed_content, metadata)
    """
    # Validate content
    is_valid, error = validate_memory_content(content)
    if not is_valid:
        raise ValueError(f"Invalid memory content: {error}")
    
    # Process content
    processed_content = content.strip()
    
    # Create metadata
    metadata = create_memory_metadata(
        processed_content,
        extra_metadata=extra_metadata
    )
    
    return processed_content, metadata

def format_memory_for_display(
    content: str,
    metadata: Dict[str, Any],
    include_metadata: bool = True
) -> str:
    """
    Format memory for display in console or logs.
    
    Args:
        content: Memory content
        metadata: Memory metadata
        include_metadata: Whether to include metadata in output
    
    Returns:
        str: Formatted memory string
    """
    formatted = content
    
    if include_metadata and metadata:
        timestamp = metadata.get('timestamp', '')
        mem_type = metadata.get('type', 'general')
        formatted = f"{formatted}\n[metadata](Type: {mem_type}, Recorded: {timestamp})[/metadata]"
    
    return formatted

def serialize_memory(
    content: str,
    metadata: Dict[str, Any]
) -> str:
    """
    Serialize memory for storage.
    
    Args:
        content: Memory content
        metadata: Memory metadata
    
    Returns:
        str: Serialized memory string
    """
    memory_data = {
        'content': content,
        'metadata': metadata
    }
    return json.dumps(memory_data, ensure_ascii=False)
