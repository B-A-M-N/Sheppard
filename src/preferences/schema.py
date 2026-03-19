"""
Schema definitions for preference validation.
File: src/preferences/schema.py
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

class PreferenceSchema(BaseModel):
    """Base schema for preference validation."""
    
    key: str = Field(..., description="Unique key identifying the preference")
    value: Any = Field(..., description="Preference value")
    type: str = Field(..., description="Type of preference value")
    category: str = Field(..., description="Category the preference belongs to")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="When the preference was set"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the preference"
    )

    @field_validator('key')
    def validate_key(cls, v: str) -> str:
        """Validate preference key format."""
        if not v or not v.strip():
            raise ValueError("Preference key cannot be empty")
        if len(v) > 50:
            raise ValueError("Preference key too long (max 50 characters)")
        if not v.replace('_', '').isalnum():
            raise ValueError("Preference key must be alphanumeric (underscores allowed)")
        return v.lower()

class CategorySchema(BaseModel):
    """Schema for preference categories."""
    
    name: str = Field(..., description="Category name")
    description: str = Field(..., description="Category description")
    allowed_types: List[str] = Field(..., description="Allowed value types")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional category metadata"
    )

class ExtendedPreferenceSchema(PreferenceSchema):
    """Extended schema with additional validation rules."""
    
    constraints: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional constraints on the preference value"
    )
    validation_rules: Optional[List[str]] = Field(
        None,
        description="Optional validation rules to apply"
    )
    dependencies: Optional[List[str]] = Field(
        None,
        description="Optional list of dependent preferences"
    )

class ValidatorSchema(BaseModel):
    """Schema for preference validators."""
    
    name: str = Field(..., description="Validator name")
    type: str = Field(..., description="Type of validator")
    rules: Dict[str, Any] = Field(..., description="Validation rules")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional validator metadata"
    )

class StoreSchema(BaseModel):
    """Schema for preference storage operations."""
    
    storage_type: str = Field(..., description="Type of storage")
    location: str = Field(..., description="Storage location")
    options: Dict[str, Any] = Field(
        default_factory=dict,
        description="Storage options"
    )

class ProcessorSchema(BaseModel):
    """Schema for preference processors."""
    
    processor_type: str = Field(..., description="Type of processor")
    enabled: bool = Field(default=True, description="Whether processor is enabled")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Processor configuration"
    )

class PreferenceGroupSchema(BaseModel):
    """Schema for preference groups."""
    
    group_id: str = Field(..., description="Group identifier")
    name: str = Field(..., description="Group name")
    preferences: List[PreferenceSchema] = Field(
        default_factory=list,
        description="Preferences in the group"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Group metadata"
    )

class PreferenceHistorySchema(BaseModel):
    """Schema for preference history entries."""
    
    preference_id: str = Field(..., description="Preference identifier")
    old_value: Optional[Any] = Field(None, description="Previous value")
    new_value: Any = Field(..., description="New value")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="When the change occurred"
    )
    change_reason: Optional[str] = Field(None, description="Reason for change")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Change metadata"
    )

class ValidationResultSchema(BaseModel):
    """Schema for validation results."""
    
    is_valid: bool = Field(..., description="Whether validation passed")
    errors: Optional[List[str]] = Field(None, description="Validation errors")
    warnings: Optional[List[str]] = Field(None, description="Validation warnings")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Validation metadata"
    )

class PreferenceSetSchema(BaseModel):
    """Schema for sets of related preferences."""
    
    set_id: str = Field(..., description="Set identifier")
    name: str = Field(..., description="Set name")
    preferences: Dict[str, PreferenceSchema] = Field(
        default_factory=dict,
        description="Map of preference keys to preferences"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Set metadata"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="When the set was created"
    )
