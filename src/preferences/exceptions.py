"""
Exceptions specific to preference handling.
File: src/preferences/exceptions.py

This module defines the exception hierarchy for the preferences system.
All exceptions inherit from PreferenceError which itself inherits from ChatSystemError.

The exceptions defined here are used throughout the preferences system to provide
detailed error information and maintain consistent error handling patterns.
"""

from typing import Optional, Dict, Any
from src.core.exceptions import ChatSystemError

class PreferenceError(ChatSystemError):
    """
    Base exception for all preference-related errors.
    
    This class serves as the root of the preference exception hierarchy.
    All preference-specific exceptions should inherit from this class.
    """
    def __init__(
        self,
        message: str = "Preference operation failed",
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize preference error.
        
        Args:
            message: Error message
            details: Optional dictionary containing additional error details
        """
        self.details = details or {}
        formatted_message = f"Preference Error: {message}"
        if self.details:
            formatted_message += f"\nDetails: {self.details}"
        super().__init__(formatted_message)

class ValidationError(PreferenceError):
    """
    Raised when preference validation fails.
    
    This exception is raised when a preference fails to meet
    the required validation criteria, such as data type mismatches,
    invalid values, or schema violations.
    """
    def __init__(
        self,
        message: str = "Validation failed",
        validation_errors: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize validation error.
        
        Args:
            message: Error message
            validation_errors: Optional dictionary containing validation error details
        """
        details = {"validation_errors": validation_errors} if validation_errors else {}
        super().__init__(f"Validation Error: {message}", details)

class StorageError(PreferenceError):
    """
    Raised when preference storage operations fail.
    
    This exception is raised when there are issues storing or retrieving
    preferences from the persistence layer, such as database errors,
    connection issues, or storage constraints.
    """
    def __init__(
        self,
        message: str = "Storage operation failed",
        storage_details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize storage error.
        
        Args:
            message: Error message
            storage_details: Optional dictionary containing storage error details
        """
        details = {"storage_details": storage_details} if storage_details else {}
        super().__init__(f"Storage Error: {message}", details)

class ProcessingError(PreferenceError):
    """
    Raised when preference processing fails.
    
    This exception is raised when there are issues during preference
    processing operations, such as transformation errors, computation
    failures, or processing pipeline issues.
    """
    def __init__(
        self,
        message: str = "Processing failed",
        processing_details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize processing error.
        
        Args:
            message: Error message
            processing_details: Optional dictionary containing processing error details
        """
        details = {"processing_details": processing_details} if processing_details else {}
        super().__init__(f"Processing Error: {message}", details)

class PreferenceNotFoundError(PreferenceError):
    """
    Raised when a requested preference is not found.
    
    This exception is raised when attempting to access or modify
    a preference that doesn't exist in the system.
    """
    def __init__(
        self,
        key: str,
        lookup_details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize preference not found error.
        
        Args:
            key: Key of the preference that wasn't found
            lookup_details: Optional dictionary containing lookup attempt details
        """
        details = {
            "preference_key": key,
            **(lookup_details or {})
        }
        super().__init__(f"Preference not found: {key}", details)

class CategoryNotFoundError(PreferenceError):
    """
    Raised when a preference category is not found.
    
    This exception is raised when attempting to access or modify
    a preference category that doesn't exist in the system.
    """
    def __init__(
        self,
        category: str,
        category_details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize category not found error.
        
        Args:
            category: Name of the category that wasn't found
            category_details: Optional dictionary containing category lookup details
        """
        details = {
            "category_name": category,
            **(category_details or {})
        }
        super().__init__(f"Category not found: {category}", details)

class InvalidPreferenceError(PreferenceError):
    """
    Raised when preference data is invalid.
    
    This exception is raised when preference data fails to meet
    the required format, structure, or business rules, distinct
    from validation errors which are schema-based.
    """
    def __init__(
        self,
        message: str = "Invalid preference data",
        invalid_data: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize invalid preference error.
        
        Args:
            message: Error message
            invalid_data: Optional dictionary containing details about the invalid data
        """
        details = {"invalid_data": invalid_data} if invalid_data else {}
        super().__init__(f"Invalid Preference: {message}", details)

class ConflictError(PreferenceError):
    """
    Raised when there are conflicting preferences.
    
    This exception is raised when attempting to set or modify preferences
    that would create conflicts with existing preferences or business rules.
    """
    def __init__(
        self,
        key: str,
        details: str = "",
        conflict_data: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize conflict error.
        
        Args:
            key: Key of the preference causing the conflict
            details: Additional details about the conflict
            conflict_data: Optional dictionary containing conflict details
        """
        message = f"Preference conflict for {key}"
        if details:
            message += f": {details}"
        
        conflict_details = {
            "preference_key": key,
            "conflict_description": details,
            **(conflict_data or {})
        }
        super().__init__(message, conflict_details)

class PreferenceTypeError(PreferenceError):
    """
    Raised when there are preference type mismatches.
    
    This exception is raised when preference values don't match
    their expected types or when type conversion fails.
    """
    def __init__(
        self,
        expected_type: str,
        actual_type: str,
        value: Any,
        type_details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize preference type error.
        
        Args:
            expected_type: Expected type of the preference
            actual_type: Actual type received
            value: The value that caused the type error
            type_details: Optional dictionary containing type mismatch details
        """
        message = f"Type mismatch: expected {expected_type}, got {actual_type}"
        details = {
            "expected_type": expected_type,
            "actual_type": actual_type,
            "value": str(value),
            **(type_details or {})
        }
        super().__init__(message, details)

class PreferenceVersionError(PreferenceError):
    """
    Raised when there are preference version incompatibilities.
    
    This exception is raised when attempting to process preferences
    with incompatible versions or during version migration issues.
    """
    def __init__(
        self,
        current_version: str,
        required_version: str,
        version_details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize preference version error.
        
        Args:
            current_version: Current preference version
            required_version: Required preference version
            version_details: Optional dictionary containing version mismatch details
        """
        message = f"Version mismatch: current {current_version}, required {required_version}"
        details = {
            "current_version": current_version,
            "required_version": required_version,
            **(version_details or {})
        }
        super().__init__(message, details)

class PreferenceLimitError(PreferenceError):
    """
    Raised when preference limits are exceeded.
    
    This exception is raised when attempting to exceed defined limits
    for preferences, such as maximum count, size, or depth constraints.
    """
    def __init__(
        self,
        limit_type: str,
        current_value: int,
        max_value: int,
        limit_details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize preference limit error.
        
        Args:
            limit_type: Type of limit that was exceeded
            current_value: Current value that exceeded the limit
            max_value: Maximum allowed value
            limit_details: Optional dictionary containing limit details
        """
        message = f"Preference limit exceeded for {limit_type}: {current_value} > {max_value}"
        details = {
            "limit_type": limit_type,
            "current_value": current_value,
            "max_value": max_value,
            **(limit_details or {})
        }
        super().__init__(message, details)

class PreferenceAccessError(PreferenceError):
    """
    Raised when preference access is denied.
    
    This exception is raised when attempting to access or modify
    preferences without proper permissions or in invalid contexts.
    """
    def __init__(
        self,
        operation: str,
        reason: str,
        access_details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize preference access error.
        
        Args:
            operation: Operation that was attempted
            reason: Reason for access denial
            access_details: Optional dictionary containing access error details
        """
        message = f"Access denied for operation '{operation}': {reason}"
        details = {
            "operation": operation,
            "denial_reason": reason,
            **(access_details or {})
        }
        super().__init__(message, details)

class PreferenceSyncError(PreferenceError):
    """
    Raised when preference synchronization fails.
    
    This exception is raised when there are issues synchronizing
    preferences across different parts of the system or with
    external storage.
    """
    def __init__(
        self,
        sync_type: str,
        message: str = "Synchronization failed",
        sync_details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize preference sync error.
        
        Args:
            sync_type: Type of synchronization that failed
            message: Error message
            sync_details: Optional dictionary containing sync error details
        """
        formatted_message = f"{sync_type} synchronization failed: {message}"
        details = {
            "sync_type": sync_type,
            "error_message": message,
            **(sync_details or {})
        }
        super().__init__(formatted_message, details)
