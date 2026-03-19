"""
Schema validation models for the chat system using Pydantic.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, field_validator
from src.utils.text_processing import sanitize_text

class EmbeddingSchema(BaseModel):
    """Schema for embedding data validation."""
    
    content: str = Field(..., description="Content to be embedded")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the embedding"
    )
    embedding: Optional[List[float]] = Field(
        None, description="Generated embedding vector"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Timestamp of embedding creation"
    )

    @field_validator('content')
    def clean_content(cls, v: str) -> str:
        return sanitize_text(v)

    class Config:
        json_schema_extra = {
            "example": {
                "content": "User prefers dark mode",
                "metadata": {
                    "type": "preference",
                    "confidence": 0.95
                },
                "embedding": [0.1, 0.2, 0.3],
                "timestamp": "2024-12-11T12:00:00Z"
            }
        }

class ToolCallSchema(BaseModel):
    """Schema for tool call validation."""
    
    name: str = Field(..., description="Name of the tool to call")
    parameters: Dict[str, Any] = Field(
        ..., description="Parameters for the tool call"
    )
    context: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional context for the tool"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Timestamp of tool call"
    )

    @field_validator('name')
    def validate_tool_name(cls, v: str) -> str:
        allowed_tools = {
            'summarize_text',
            'search_memory',
            'generate_embedding',
            'analyze_sentiment',
            'extract_keywords'
        }
        if v not in allowed_tools:
            raise ValueError(
                f"Invalid tool name. Must be one of: {', '.join(allowed_tools)}"
            )
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "name": "summarize_text",
                "parameters": {
                    "text": "Long text to summarize",
                    "max_length": 100
                },
                "context": {
                    "user_id": "123",
                    "session_id": "abc"
                },
                "timestamp": "2024-12-11T12:00:00Z"
            }
        }

class MemorySchema(BaseModel):
    """Schema for memory validation."""
    
    content: str = Field(..., description="Memory content")
    embedding_id: str = Field(..., description="Unique identifier for the embedding")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the memory"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Timestamp of memory creation"
    )
    relevance_score: Optional[float] = Field(
        None,
        description="Optional relevance score",
        ge=0.0,
        le=1.0
    )

    @field_validator('content')
    def clean_content(cls, v: str) -> str:
        return sanitize_text(v)

    @field_validator('embedding_id')
    def validate_embedding_id(cls, v: str) -> str:
        if not v.startswith('mem_'):
            raise ValueError("Embedding ID must start with 'mem_'")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "content": "User prefers dark mode for coding",
                "embedding_id": "mem_abc123",
                "metadata": {
                    "type": "preference",
                    "confidence": 0.95
                },
                "timestamp": "2024-12-11T12:00:00Z"
            }
        }

class SearchResultSchema(BaseModel):
    """Schema for search result validation."""
    
    content: str = Field(..., description="Content of the search result")
    relevance_score: float = Field(
        ..., 
        description="Relevance score of the result",
        ge=0.0,
        le=1.0
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the search result"
    )
    timestamp: str = Field(..., description="Timestamp of the original memory")
    memory_id: Optional[str] = Field(
        None,
        description="Optional memory identifier"
    )

    @field_validator('content')
    def clean_content(cls, v: str) -> str:
        return sanitize_text(v)

    class Config:
        json_schema_extra = {
            "example": {
                "content": "User prefers dark mode for coding",
                "relevance_score": 0.95,
                "metadata": {
                    "type": "preference",
                    "memory_id": "mem_abc123"
                },
                "timestamp": "2024-12-11T12:00:00Z"
            }
        }

class ChatMessageSchema(BaseModel):
    """Schema for chat message validation."""
    
    role: str = Field(
        ..., 
        description="Role of the message sender",
        pattern="^(user|assistant|system)$"
    )
    content: str = Field(..., description="Message content")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Message timestamp"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional message metadata"
    )
    images: Optional[List[str]] = Field(
        None,
        description="Optional list of base64 encoded images"
    )

    @field_validator('content')
    def clean_content(cls, v: str) -> str:
        return sanitize_text(v, allow_markdown=True)

    class Config:
        json_schema_extra = {
            "example": {
                "role": "user",
                "content": "Why is the sky blue?",
                "timestamp": "2024-12-11T12:00:00Z",
                "metadata": {
                    "client_id": "web_interface",
                    "session_id": "abc123"
                }
            }
        }
