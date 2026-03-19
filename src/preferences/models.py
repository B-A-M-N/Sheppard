"""
Data models for preference management.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

class PreferenceCategory(str, Enum):
    """Categories for user preferences."""
    APPEARANCE = "appearance"
    BEHAVIOR = "behavior"
    COMMUNICATION = "communication"
    INTERFACE = "interface"
    CONTENT = "content"
    PRIVACY = "privacy"
    NOTIFICATIONS = "notifications"
    ACCESSIBILITY = "accessibility"
    LANGUAGE = "language"
    TIMEZONE = "timezone"
    FORMATTING = "formatting"

class PreferenceType(str, Enum):
    """Types of preference values."""
    STRING = "string"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    ENUM = "enum"
    LIST = "list"
    DICT = "dict"

@dataclass
class PreferenceValue:
    """Model representing a preference value with validation."""
    type: PreferenceType
    value: Any
    options: Optional[List[Any]] = None
    constraints: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate value after initialization."""
        self._validate_value()

    def _validate_value(self) -> None:
        """Validate preference value based on type and constraints."""
        if self.type == PreferenceType.STRING:
            if not isinstance(self.value, str):
                raise ValueError("Value must be a string")
            if self.constraints and 'max_length' in self.constraints:
                if len(self.value) > self.constraints['max_length']:
                    raise ValueError(f"String too long (max {self.constraints['max_length']} characters)")
                
        elif self.type == PreferenceType.BOOLEAN:
            if not isinstance(self.value, bool):
                raise ValueError("Value must be a boolean")
                
        elif self.type == PreferenceType.INTEGER:
            if not isinstance(self.value, int):
                raise ValueError("Value must be an integer")
            if self.constraints:
                if 'min' in self.constraints and self.value < self.constraints['min']:
                    raise ValueError(f"Value must be >= {self.constraints['min']}")
                if 'max' in self.constraints and self.value > self.constraints['max']:
                    raise ValueError(f"Value must be <= {self.constraints['max']}")
                    
        elif self.type == PreferenceType.FLOAT:
            if not isinstance(self.value, (int, float)):
                raise ValueError("Value must be a number")
            if self.constraints:
                if 'min' in self.constraints and self.value < self.constraints['min']:
                    raise ValueError(f"Value must be >= {self.constraints['min']}")
                if 'max' in self.constraints and self.value > self.constraints['max']:
                    raise ValueError(f"Value must be <= {self.constraints['max']}")
                    
        elif self.type == PreferenceType.ENUM:
            if not self.options:
                raise ValueError("Options must be provided for enum type")
            if self.value not in self.options:
                raise ValueError(f"Value must be one of: {self.options}")
                
        elif self.type == PreferenceType.LIST:
            if not isinstance(self.value, list):
                raise ValueError("Value must be a list")
            if self.constraints and 'max_items' in self.constraints:
                if len(self.value) > self.constraints['max_items']:
                    raise ValueError(f"List too long (max {self.constraints['max_items']} items)")
                    
        elif self.type == PreferenceType.DICT:
            if not isinstance(self.value, dict):
                raise ValueError("Value must be a dictionary")
            if self.constraints and 'required_keys' in self.constraints:
                for key in self.constraints['required_keys']:
                    if key not in self.value:
                        raise ValueError(f"Missing required key: {key}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'type': self.type.value,
            'value': self.value,
            'options': self.options,
            'constraints': self.constraints
        }

@dataclass
class PreferenceMetadata:
    """Metadata for a preference."""
    source: str
    confidence: float = 1.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    context: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate metadata after initialization."""
        if not 0 <= self.confidence <= 1:
            raise ValueError("Confidence score must be between 0 and 1")
        if self.context is None:
            self.context = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'source': self.source,
            'confidence': self.confidence,
            'timestamp': self.timestamp,
            'context': self.context
        }

@dataclass
class Preference:
    """Model representing a complete preference."""
    key: str
    value: PreferenceValue
    category: PreferenceCategory
    metadata: PreferenceMetadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = None

    def __post_init__(self):
        """Validate preference after initialization."""
        if not self.key or not self.key.strip():
            raise ValueError("Preference key cannot be empty")
        if len(self.key) > 50:
            raise ValueError("Preference key too long (max 50 characters)")
        if not self.key.replace('_', '').isalnum():
            raise ValueError("Preference key must be alphanumeric (underscores allowed)")
        self.key = self.key.lower()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'key': self.key,
            'value': self.value.to_dict(),
            'category': self.category.value,
            'metadata': self.metadata.to_dict(),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

@dataclass
class PreferenceSet:
    """Model representing a set of related preferences."""
    id: str
    preferences: Dict[str, Preference]
    name: Optional[str] = None
    description: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_preference(self, preference: Preference) -> None:
        """Add a preference to the set."""
        self.preferences[preference.key] = preference
        self.metadata['last_updated'] = datetime.now().isoformat()

    def remove_preference(self, key: str) -> None:
        """Remove a preference from the set."""
        if key in self.preferences:
            del self.preferences[key]
            self.metadata['last_updated'] = datetime.now().isoformat()

    def get_preference(self, key: str) -> Optional[Preference]:
        """Get a preference by key."""
        return self.preferences.get(key)

    def to_dict(self) -> Dict[str, Any]:
        """Convert preference set to dictionary format."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'preferences': {
                k: v.to_dict() for k, v in self.preferences.items()
            },
            'created_at': self.created_at,
            'metadata': self.metadata
        }

@dataclass
class PreferenceValidationResult:
    """Result of preference validation."""
    is_valid: bool
    errors: Optional[List[str]] = None
    warnings: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Initialize default values after creation."""
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            'is_valid': self.is_valid,
            'errors': self.errors,
            'warnings': self.warnings,
            'metadata': self.metadata
        }

class PreferenceType(str, Enum):
    """Types of preference values."""
    STRING = "string"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    ENUM = "enum"
    LIST = "list"
    DICT = "dict"

@dataclass
class PreferenceValue:
    """Model representing a preference value with validation."""
    type: PreferenceType
    value: Any
    options: Optional[List[Any]] = None
    constraints: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate value after initialization."""
        self._validate_value()

    def _validate_value(self) -> None:
        """Validate preference value based on type and constraints."""
        # ... (rest of validation logic remains the same)
        pass

@dataclass
class PreferenceMetadata:
    """Metadata for a preference."""
    source: str
    confidence: float = 1.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    context: Optional[Dict[str, Any]] = None

@dataclass
class Preference:
    """Model representing a complete preference."""
    key: str
    value: PreferenceValue
    category: PreferenceCategory
    metadata: PreferenceMetadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = None

@dataclass
class PreferenceSet:
    """Model representing a set of related preferences."""
    id: str
    preferences: Dict[str, Preference]
    name: Optional[str] = None
    description: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_preference(self, preference: Preference) -> None:
        """Add a preference to the set."""
        self.preferences[preference.key] = preference
        self.metadata['last_updated'] = datetime.now().isoformat()

    def remove_preference(self, key: str) -> None:
        """Remove a preference from the set."""
        if key in self.preferences:
            del self.preferences[key]
            self.metadata['last_updated'] = datetime.now().isoformat()

    def get_preference(self, key: str) -> Optional[Preference]:
        """Get a preference by key."""
        return self.preferences.get(key)

    def to_dict(self) -> Dict[str, Any]:
        """Convert preference set to dictionary format."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'preferences': {
                k: v.to_dict() for k, v in self.preferences.items()
            },
            'created_at': self.created_at,
            'metadata': self.metadata
        }
