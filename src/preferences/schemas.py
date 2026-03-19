"""
Preference-specific schemas for enhanced memory management.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class PreferenceSchema(BaseModel):
    """Schema for user preferences."""
    
    type: str = Field(..., description="Type of preference")
    value: str = Field(..., description="Preference value")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="When the preference was recorded"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the preference"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "color",
                "value": "blue",
                "timestamp": "2024-12-11T12:00:00Z",
                "metadata": {
                    "context": "user_input",
                    "confidence": 1.0
                }
            }
        }

class PreferenceSetSchema(BaseModel):
    """Schema for a set of related preferences."""
    
    preferences: Dict[str, PreferenceSchema] = Field(
        ..., 
        description="Map of preference types to values"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="When the preference set was recorded"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the preference set"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "preferences": {
                    "color": {
                        "type": "color",
                        "value": "blue",
                        "timestamp": "2024-12-11T12:00:00Z"
                    },
                    "flavor": {
                        "type": "flavor",
                        "value": "chocolate",
                        "timestamp": "2024-12-11T12:00:00Z"
                    }
                },
                "timestamp": "2024-12-11T12:00:00Z",
                "metadata": {
                    "source": "user_input",
                    "interaction_id": "abc123"
                }
            }
        }

class PreferenceSearchSchema(BaseModel):
    """Schema for preference search results."""
    
    preference: PreferenceSchema = Field(..., description="Found preference")
    relevance_score: float = Field(
        ..., 
        description="Search relevance score",
        ge=0.0,
        le=1.0
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Search result metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "preference": {
                    "type": "color",
                    "value": "blue",
                    "timestamp": "2024-12-11T12:00:00Z"
                },
                "relevance_score": 0.95,
                "metadata": {
                    "memory_id": "mem_abc123",
                    "context": "direct_match"
                }
            }
        }
