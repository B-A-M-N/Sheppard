"""
Text validation and sanitization utilities.
File: src/utils/validation.py
"""

import re
import json
import logging
import os
from typing import Optional, Dict, Any, List, Tuple, Union
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from src.utils.text_processing import sanitize_text, clean_string
from src.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

def validate_metadata(metadata: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate metadata dictionary structure.
    
    Args:
        metadata: Dictionary to validate
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    try:
        if not isinstance(metadata, dict):
            return False, "Metadata must be a dictionary"
            
        # Check for common metadata fields
        if 'timestamp' in metadata:
            timestamp_valid, error = validate_timestamp(metadata['timestamp'])
            if not timestamp_valid:
                return False, f"Invalid timestamp in metadata: {error}"
                
        return True, None
        
    except Exception as e:
        logger.error(f"Metadata validation failed: {str(e)}")
        return False, str(e)

def validate_message_content(
    content: str,
    max_length: Optional[int] = None,
    require_non_empty: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Validate chat message content.
    
    Args:
        content: Message content to validate
        max_length: Optional maximum length
        require_non_empty: Whether to require non-empty content
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    try:
        # Check if content is required
        if require_non_empty and (not content or not content.strip()):
            return False, "Message content cannot be empty"
            
        # Clean content
        cleaned_content = sanitize_text(content)
        
        # Check length
        if max_length and len(cleaned_content) > max_length:
            return False, f"Message content exceeds maximum length of {max_length} characters"
        
        return True, None
        
    except Exception as e:
        logger.error(f"Message content validation failed: {str(e)}")
        return False, str(e)

def validate_content(
    content: str,
    max_length: Optional[int] = None,
    required_fields: Optional[List[str]] = None,
    content_type: str = "text",
    metadata: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate content based on specified rules.
    
    Args:
        content: Content to validate
        max_length: Optional maximum length
        required_fields: Optional list of required fields
        content_type: Type of content being validated
        metadata: Optional metadata about the content
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    try:
        if not content:
            return False, "Content cannot be empty"
            
        # Clean content based on type
        if content_type == "text":
            cleaned_content = sanitize_text(content)
        else:
            cleaned_content = clean_string(content)
            
        # Check length
        if max_length and len(cleaned_content) > max_length:
            return False, f"Content exceeds maximum length of {max_length} characters"
            
        # Check required fields if content is JSON
        if content_type == "json" and required_fields:
            try:
                json_data = json.loads(cleaned_content)
                missing_fields = [
                    field for field in required_fields
                    if field not in json_data
                ]
                if missing_fields:
                    return False, f"Missing required fields: {', '.join(missing_fields)}"
            except json.JSONDecodeError:
                return False, "Invalid JSON format"
        
        return True, None
        
    except Exception as e:
        logger.error(f"Content validation failed: {str(e)}")
        return False, str(e)

def validate_embedding(embedding: List[float], dimension: int) -> bool:
    """
    Validate embedding vector.
    
    Args:
        embedding: Embedding vector to validate
        dimension: Expected embedding dimension
        
    Returns:
        bool: Whether embedding is valid
    """
    try:
        # Check type and length
        if not isinstance(embedding, list):
            return False
        if len(embedding) != dimension:
            return False
            
        # Check values
        return all(isinstance(x, (int, float)) for x in embedding)
        
    except Exception as e:
        logger.error(f"Embedding validation failed: {str(e)}")
        return False

def validate_memory_content(
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
    max_length: int = 10000
) -> Tuple[bool, Optional[str]]:
    """
    Validate memory content.
    
    Args:
        content: Memory content to validate
        metadata: Optional metadata
        max_length: Maximum content length
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    try:
        # Basic content validation
        if not content or not content.strip():
            return False, "Memory content cannot be empty"
        
        # Clean content
        cleaned_content = clean_string(content)
        
        # Check length
        if len(cleaned_content) > max_length:
            return False, f"Content exceeds maximum length of {max_length} characters"
            
        # Validate metadata if provided
        if metadata:
            if not isinstance(metadata, dict):
                return False, "Metadata must be a dictionary"
                
            # Check required metadata fields
            required_fields = {'timestamp', 'type'}
            missing_fields = required_fields - set(metadata.keys())
            if missing_fields:
                return False, f"Missing required metadata fields: {', '.join(missing_fields)}"
        
        return True, None
        
    except Exception as e:
        logger.error(f"Memory content validation failed: {str(e)}")
        return False, str(e)

def validate_file_path(
    path: Union[str, Path],
    required_extensions: Optional[List[str]] = None,
    must_exist: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Validate file path.
    
    Args:
        path: File path to validate
        required_extensions: Optional list of allowed extensions
        must_exist: Whether file must exist
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    try:
        # Convert to Path object
        file_path = Path(path)
        
        # Check existence if required
        if must_exist and not file_path.is_file():
            return False, f"File does not exist: {file_path}"
            
        # Check extension if required
        if required_extensions:
            if file_path.suffix.lower() not in required_extensions:
                return False, f"Invalid file extension. Must be one of: {required_extensions}"
        
        return True, None
        
    except Exception as e:
        logger.error(f"File path validation failed: {str(e)}")
        return False, str(e)

def validate_url(
    url: str,
    allowed_schemes: Optional[List[str]] = None,
    check_format_only: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Validate URL format and optionally scheme.
    
    Args:
        url: URL to validate
        allowed_schemes: Optional list of allowed URL schemes
        check_format_only: Whether to only check format without parsing
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    try:
        if not url:
            return False, "URL cannot be empty"
            
        if check_format_only:
            # Simple format check using regex
            url_pattern = r'https?://(?:[\w-]|\.|/|\?|=|%|&)+(?<![.,?!])'
            if not re.match(url_pattern, url):
                return False, "Invalid URL format"
        else:
            # Full URL parsing
            parsed = urlparse(url)
            if not all([parsed.scheme, parsed.netloc]):
                return False, "Invalid URL format"
                
            # Check scheme if specified
            if allowed_schemes and parsed.scheme not in allowed_schemes:
                return False, f"Invalid URL scheme. Must be one of: {allowed_schemes}"
        
        return True, None
        
    except Exception as e:
        logger.error(f"URL validation failed: {str(e)}")
        return False, str(e)

def validate_timestamp(
    timestamp: str,
    format_string: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate timestamp format.
    
    Args:
        timestamp: Timestamp to validate
        format_string: Optional specific format string
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    try:
        if not timestamp:
            return False, "Timestamp cannot be empty"
            
        if format_string:
            # Try parsing with specific format
            datetime.strptime(timestamp, format_string)
        else:
            # Try parsing as ISO format
            datetime.fromisoformat(timestamp)
        
        return True, None
        
    except ValueError as e:
        return False, f"Invalid timestamp format: {str(e)}"
    except Exception as e:
        logger.error(f"Timestamp validation failed: {str(e)}")
        return False, str(e)

def validate_dict_fields(
    data: Dict[str, Any],
    required_fields: Dict[str, type],
    optional_fields: Optional[Dict[str, type]] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate dictionary fields and types.
    
    Args:
        data: Dictionary to validate
        required_fields: Dictionary of required field names and types
        optional_fields: Optional dictionary of optional field names and types
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    try:
        if not isinstance(data, dict):
            return False, "Input must be a dictionary"
            
        # Check required fields
        for field, field_type in required_fields.items():
            if field not in data:
                return False, f"Missing required field: {field}"
            if not isinstance(data[field], field_type):
                return False, f"Invalid type for field {field}. Expected {field_type}"
        
        # Check optional fields if provided
        if optional_fields:
            for field, field_type in optional_fields.items():
                if field in data and not isinstance(data[field], field_type):
                    return False, f"Invalid type for optional field {field}. Expected {field_type}"
        
        return True, None
        
    except Exception as e:
        logger.error(f"Dictionary validation failed: {str(e)}")
        return False, str(e)

def validate_user_preferences(preferences: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate user preferences.
    
    Args:
        preferences: User preferences dictionary
        
    Returns:
        Tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    try:
        if not isinstance(preferences, dict):
            return False, "Preferences must be a dictionary"
            
        # Validate common preference types
        for key, value in preferences.items():
            # Validate preference values based on key
            if key == "theme" and not isinstance(value, str):
                return False, "Theme preference must be a string"
            elif key == "notifications" and not isinstance(value, bool):
                return False, "Notifications preference must be a boolean"
            elif key == "max_message_length" and not isinstance(value, int):
                return False, "Max message length preference must be an integer"
            elif key == "language" and not isinstance(value, str):
                return False, "Language preference must be a string"
        
        return True, None
        
    except Exception as e:
        logger.error(f"User preferences validation failed: {str(e)}")
        return False, str(e)

def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize filename for safe filesystem use.
    
    Args:
        filename: Filename to sanitize
        max_length: Maximum filename length
        
    Returns:
        str: Sanitized filename
    """
    try:
        # Remove invalid characters
        clean_name = re.sub(r'[<>:"/\\|?*]', '', filename)
        
        # Replace spaces with underscores
        clean_name = clean_name.replace(' ', '_')
        
        # Remove control characters
        clean_name = ''.join(char for char in clean_name if ord(char) >= 32)
        
        # Ensure proper length
        name, ext = os.path.splitext(clean_name)
        if len(clean_name) > max_length:
            return name[:max_length-len(ext)] + ext
            
        return clean_name
        
    except Exception as e:
        logger.error(f"Filename sanitization failed: {str(e)}")
        return "unnamed_file"
