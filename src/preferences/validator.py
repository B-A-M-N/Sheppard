"""
Validator for preference data validation.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from src.preferences.models import (
    Preference,
    PreferenceCategory,
    PreferenceType,
    PreferenceValue,
    PreferenceMetadata
)
from src.preferences.exceptions import ValidationError

logger = logging.getLogger(__name__)

class PreferenceValidator:
    """Validates preferences and their values."""
    
    def __init__(self):
        """Initialize preference validator."""
        self.type_validators = {
            PreferenceType.STRING: self._validate_string,
            PreferenceType.BOOLEAN: self._validate_boolean,
            PreferenceType.INTEGER: self._validate_integer,
            PreferenceType.FLOAT: self._validate_float,
            PreferenceType.ENUM: self._validate_enum,
            PreferenceType.LIST: self._validate_list,
            PreferenceType.DICT: self._validate_dict
        }
        
        # Define common constraints
        self.common_constraints = {
            'string': {
                'max_length': 1000,
                'min_length': 1
            },
            'number': {
                'min': float('-inf'),
                'max': float('inf')
            },
            'list': {
                'max_items': 100,
                'min_items': 0
            }
        }
    
    async def validate_preference(
        self,
        preference: Preference
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a complete preference object.
        
        Args:
            preference: Preference to validate
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            # Validate basic structure
            if not preference.key or not preference.key.strip():
                return False, "Preference key cannot be empty"
            
            if len(preference.key) > 50:
                return False, "Preference key too long (max 50 characters)"
            
            # Validate category
            if not isinstance(preference.category, PreferenceCategory):
                return False, f"Invalid category: {preference.category}"
            
            # Validate value
            value_valid, value_error = await self._validate_value(
                preference.value,
                preference.key
            )
            if not value_valid:
                return False, value_error
            
            # Validate metadata
            metadata_valid, metadata_error = self._validate_metadata(
                preference.metadata
            )
            if not metadata_valid:
                return False, metadata_error
            
            return True, None
            
        except Exception as e:
            logger.error(f"Preference validation failed: {str(e)}")
            return False, str(e)
    
    async def _validate_value(
        self,
        value: PreferenceValue,
        key: str
    ) -> Tuple[bool, Optional[str]]:
        """Validate preference value."""
        try:
            # Check value type
            if not isinstance(value.type, PreferenceType):
                return False, f"Invalid value type: {value.type}"
            
            # Get type-specific validator
            validator = self.type_validators.get(value.type)
            if not validator:
                return False, f"No validator for type: {value.type}"
            
            # Validate value
            is_valid, error = validator(
                value.value,
                value.constraints,
                value.options
            )
            if not is_valid:
                return False, f"Value validation failed for {key}: {error}"
            
            return True, None
            
        except Exception as e:
            return False, str(e)
    
    def _validate_metadata(
        self,
        metadata: PreferenceMetadata
    ) -> Tuple[bool, Optional[str]]:
        """Validate preference metadata."""
        try:
            # Validate source
            if not metadata.source:
                return False, "Metadata source cannot be empty"
            
            # Validate confidence score
            if not 0 <= metadata.confidence <= 1:
                return False, "Confidence score must be between 0 and 1"
            
            # Validate timestamp format
            try:
                datetime.fromisoformat(metadata.timestamp)
            except ValueError:
                return False, "Invalid timestamp format"
            
            return True, None
            
        except Exception as e:
            return False, str(e)
    
    def _validate_string(
        self,
        value: str,
        constraints: Optional[Dict[str, Any]] = None,
        options: Optional[List[Any]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Validate string value."""
        if not isinstance(value, str):
            return False, "Value must be a string"
        
        constraints = constraints or {}
        max_length = constraints.get(
            'max_length',
            self.common_constraints['string']['max_length']
        )
        min_length = constraints.get(
            'min_length',
            self.common_constraints['string']['min_length']
        )
        
        if len(value) > max_length:
            return False, f"String too long (max {max_length} characters)"
        if len(value) < min_length:
            return False, f"String too short (min {min_length} characters)"
        
        return True, None
    
    def _validate_boolean(
        self,
        value: bool,
        constraints: Optional[Dict[str, Any]] = None,
        options: Optional[List[Any]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Validate boolean value."""
        if not isinstance(value, bool):
            return False, "Value must be a boolean"
        return True, None
    
    def _validate_integer(
        self,
        value: int,
        constraints: Optional[Dict[str, Any]] = None,
        options: Optional[List[Any]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Validate integer value."""
        if not isinstance(value, int):
            return False, "Value must be an integer"
        
        constraints = constraints or {}
        min_val = constraints.get(
            'min',
            self.common_constraints['number']['min']
        )
        max_val = constraints.get(
            'max',
            self.common_constraints['number']['max']
        )
        
        if value < min_val:
            return False, f"Value must be >= {min_val}"
        if value > max_val:
            return False, f"Value must be <= {max_val}"
        
        return True, None
    
    def _validate_float(
        self,
        value: float,
        constraints: Optional[Dict[str, Any]] = None,
        options: Optional[List[Any]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Validate float value."""
        if not isinstance(value, (int, float)):
            return False, "Value must be a number"
        
        constraints = constraints or {}
        min_val = constraints.get(
            'min',
            self.common_constraints['number']['min']
        )
        max_val = constraints.get(
            'max',
            self.common_constraints['number']['max']
        )
        
        if value < min_val:
            return False, f"Value must be >= {min_val}"
        if value > max_val:
            return False, f"Value must be <= {max_val}"
        
        return True, None
    
    def _validate_enum(
        self,
        value: Any,
        constraints: Optional[Dict[str, Any]] = None,
        options: Optional[List[Any]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Validate enum value."""
        if not options:
            return False, "Enum options must be provided"
        
        if value not in options:
            return False, f"Value must be one of: {options}"
        
        return True, None
    
    def _validate_list(
        self,
        value: List[Any],
        constraints: Optional[Dict[str, Any]] = None,
        options: Optional[List[Any]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Validate list value."""
        if not isinstance(value, list):
            return False, "Value must be a list"
        
        constraints = constraints or {}
        max_items = constraints.get(
            'max_items',
            self.common_constraints['list']['max_items']
        )
        min_items = constraints.get(
            'min_items',
            self.common_constraints['list']['min_items']
        )
        
        if len(value) > max_items:
            return False, f"List too long (max {max_items} items)"
        if len(value) < min_items:
            return False, f"List too short (min {min_items} items)"
        
        return True, None
    
    def _validate_dict(
        self,
        value: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None,
        options: Optional[List[Any]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Validate dictionary value."""
        if not isinstance(value, dict):
            return False, "Value must be a dictionary"
        
        constraints = constraints or {}
        required_keys = constraints.get('required_keys', [])
        
        # Check required keys
        for key in required_keys:
            if key not in value:
                return False, f"Missing required key: {key}"
        
        return True, None
    
    async def validate_constraints(
        self,
        constraints: Dict[str, Any],
        value_type: PreferenceType
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate constraint definitions.
        
        Args:
            constraints: Constraints to validate
            value_type: Type of value these constraints apply to
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            # Validate constraints based on type
            if value_type == PreferenceType.STRING:
                return self._validate_string_constraints(constraints)
            elif value_type in {PreferenceType.INTEGER, PreferenceType.FLOAT}:
                return self._validate_number_constraints(constraints)
            elif value_type == PreferenceType.LIST:
                return self._validate_list_constraints(constraints)
            elif value_type == PreferenceType.DICT:
                return self._validate_dict_constraints(constraints)
            elif value_type == PreferenceType.ENUM:
                return self._validate_enum_constraints(constraints)
            elif value_type == PreferenceType.BOOLEAN:
                return True, None  # No constraints needed for boolean
            
            return False, f"Unsupported type for constraints: {value_type}"
            
        except Exception as e:
            return False, f"Constraint validation failed: {str(e)}"
    
    def _validate_string_constraints(
        self,
        constraints: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Validate string constraints."""
        for key in constraints:
            if key not in {'max_length', 'min_length', 'pattern'}:
                return False, f"Invalid string constraint: {key}"
            
            if key in {'max_length', 'min_length'}:
                if not isinstance(constraints[key], int) or constraints[key] < 0:
                    return False, f"Invalid {key} value: must be non-negative integer"
            
            if key == 'pattern':
                if not isinstance(constraints[key], str):
                    return False, "Pattern must be a string"
                try:
                    import re
                    re.compile(constraints[key])
                except re.error:
                    return False, "Invalid regex pattern"
        
        return True, None
    
    def _validate_number_constraints(
        self,
        constraints: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Validate number constraints."""
        for key in constraints:
            if key not in {'min', 'max', 'step'}:
                return False, f"Invalid number constraint: {key}"
            
            if not isinstance(constraints[key], (int, float)):
                return False, f"{key} must be a number"
            
        if 'min' in constraints and 'max' in constraints:
            if constraints['min'] > constraints['max']:
                return False, "min cannot be greater than max"
        
        return True, None
    
    def _validate_list_constraints(
        self,
        constraints: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Validate list constraints."""
        for key in constraints:
            if key not in {'max_items', 'min_items', 'unique_items'}:
                return False, f"Invalid list constraint: {key}"
            
            if key in {'max_items', 'min_items'}:
                if not isinstance(constraints[key], int) or constraints[key] < 0:
                    return False, f"Invalid {key} value: must be non-negative integer"
            
            if key == 'unique_items':
                if not isinstance(constraints[key], bool):
                    return False, "unique_items must be boolean"
        
        if ('min_items' in constraints and 'max_items' in constraints and
            constraints['min_items'] > constraints['max_items']):
            return False, "min_items cannot be greater than max_items"
        
        return True, None
    
    def _validate_dict_constraints(
        self,
        constraints: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Validate dictionary constraints."""
        for key in constraints:
            if key not in {'required_keys', 'optional_keys', 'additional_properties'}:
                return False, f"Invalid dictionary constraint: {key}"
            
            if key in {'required_keys', 'optional_keys'}:
                if not isinstance(constraints[key], list):
                    return False, f"{key} must be a list"
                if not all(isinstance(k, str) for k in constraints[key]):
                    return False, f"All {key} must be strings"
            
            if key == 'additional_properties':
                if not isinstance(constraints[key], bool):
                    return False, "additional_properties must be boolean"
        
        return True, None
    
    def _validate_enum_constraints(
        self,
        constraints: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Validate enum constraints."""
        for key in constraints:
            if key != 'values':
                return False, f"Invalid enum constraint: {key}"
            
            if not isinstance(constraints[key], list):
                return False, "enum values must be a list"
            if not constraints[key]:
                return False, "enum values cannot be empty"
        
        return True, None
