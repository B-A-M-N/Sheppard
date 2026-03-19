"""
Data models for LLM interactions.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class ChatMessage(BaseModel):
    """Model representing a chat message."""
    
    role: str = Field(..., description="Role of the message sender (user/assistant)")
    content: str = Field(..., description="Content of the message")
    images: Optional[List[str]] = Field(None, description="Optional list of base64 encoded images")
    
    class Config:
        json_schema_extra = {
            "example": {
                "role": "user",
                "content": "Tell me about neural networks",
                "images": None
            }
        }

class ChatResponse(BaseModel):
    """Model representing a chat response."""
    
    content: str = Field(..., description="Content of the response")
    role: str = Field(default="assistant", description="Role of the response")
    done: bool = Field(default=False, description="Whether this is the final response")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional response metadata"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "content": "Neural networks are...",
                "role": "assistant",
                "done": True,
                "metadata": {
                    "tokens_generated": 42,
                    "processing_time": 1.23
                }
            }
        }
