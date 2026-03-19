"""
Schema validation implementation with proper embedding dimension handling.
File: src/schemas/validator.py
"""

import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime
from pydantic import ValidationError as PydanticValidationError

from src.config.settings import settings
from src.schemas.exceptions import ValidationError, ProcessingError
from src.schemas.validation_schemas import (
    EmbeddingSchema,
    ToolCallSchema,
    MemorySchema,
    SearchResultSchema,
    ChatMessageSchema
)
from src.utils.text_processing import sanitize_text

logger = logging.getLogger(__name__)

class SchemaValidator:
    """Validates and processes schema-based operations."""
    
    def __init__(self, ollama_client):
        """
        Initialize validator with Ollama client.
        
        Args:
            ollama_client: Ollama client instance for embeddings/completions
        """
        self.client = ollama_client
        self.embedding_dimension = settings.EMBEDDING_DIMENSION

    async def validate_embedding_data(
        self,
        data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate embedding data against schema.
        
        Args:
            data: Data to validate
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            # Validate basic structure
            embedding_schema = EmbeddingSchema(**data)
            
            # Validate embedding dimension if present
            if embedding_schema.embedding is not None:
                if len(embedding_schema.embedding) != self.embedding_dimension:
                    return False, (
                        f"Embedding dimension mismatch: got {len(embedding_schema.embedding)}, "
                        f"expected {self.embedding_dimension}"
                    )
            
            return True, None
            
        except PydanticValidationError as e:
            logger.error(f"Embedding validation error: {str(e)}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Unexpected validation error: {str(e)}")
            return False, f"Validation failed: {str(e)}"

    async def validate_tool_call(
        self,
        data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate tool call data against schema.
        
        Args:
            data: Tool call data to validate
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            # Validate tool call structure
            tool_schema = ToolCallSchema(**data)
            
            # Additional validation based on tool type
            if tool_schema.name == "generate_embedding":
                # Validate text content for embedding
                if "text" not in tool_schema.parameters:
                    return False, "Missing 'text' parameter for embedding generation"
                    
                # Clean text content
                tool_schema.parameters["text"] = sanitize_text(
                    tool_schema.parameters["text"]
                )
            
            return True, None
            
        except PydanticValidationError as e:
            logger.error(f"Tool call validation error: {str(e)}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Unexpected validation error: {str(e)}")
            return False, f"Validation failed: {str(e)}"

    async def validate_memory(
        self,
        data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate memory data against schema.
        
        Args:
            data: Memory data to validate
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            # Validate memory structure
            memory_schema = MemorySchema(**data)
            
            # Validate embedding if present
            if memory_schema.embedding is not None:
                if len(memory_schema.embedding) != self.embedding_dimension:
                    return False, (
                        f"Memory embedding dimension mismatch: got {len(memory_schema.embedding)}, "
                        f"expected {self.embedding_dimension}"
                    )
            
            # Ensure required metadata fields
            required_fields = {'timestamp', 'type'}
            missing_fields = required_fields - set(memory_schema.metadata.keys())
            if missing_fields:
                return False, f"Missing required metadata fields: {', '.join(missing_fields)}"
            
            return True, None
            
        except PydanticValidationError as e:
            logger.error(f"Memory validation error: {str(e)}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Unexpected validation error: {str(e)}")
            return False, f"Validation failed: {str(e)}"

    async def validate_search_result(
        self,
        data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate search result data against schema.
        
        Args:
            data: Search result data to validate
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            # Validate search result structure
            search_schema = SearchResultSchema(**data)
            
            # Validate relevance score range
            if not (0 <= search_schema.relevance_score <= 1):
                return False, "Relevance score must be between 0 and 1"
            
            # Validate embedding if present
            if "embedding" in data:
                if len(data["embedding"]) != self.embedding_dimension:
                    return False, (
                        f"Search result embedding dimension mismatch: got {len(data['embedding'])}, "
                        f"expected {self.embedding_dimension}"
                    )
            
            return True, None
            
        except PydanticValidationError as e:
            logger.error(f"Search result validation error: {str(e)}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Unexpected validation error: {str(e)}")
            return False, f"Validation failed: {str(e)}"

    async def validate_chat_message(
        self,
        data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate chat message data against schema.
        
        Args:
            data: Chat message data to validate
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            # Validate chat message structure
            message_schema = ChatMessageSchema(**data)
            
            # Validate role
            valid_roles = {'user', 'assistant', 'system'}
            if message_schema.role not in valid_roles:
                return False, f"Invalid role: {message_schema.role}. Must be one of: {valid_roles}"
            
            # Clean content
            message_schema.content = sanitize_text(
                message_schema.content,
                allow_markdown=True
            )
            
            return True, None
            
        except PydanticValidationError as e:
            logger.error(f"Chat message validation error: {str(e)}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Unexpected validation error: {str(e)}")
            return False, f"Validation failed: {str(e)}"

    async def process_embedding(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> EmbeddingSchema:
        """
        Process and validate embedding generation.
        
        Args:
            content: Content to embed
            metadata: Optional metadata
            
        Returns:
            EmbeddingSchema: Validated embedding data
            
        Raises:
            ValidationError: If validation fails
            ProcessingError: If embedding generation fails
        """
        try:
            # Clean content
            cleaned_content = sanitize_text(content)
            
            # Generate embedding
            embedding = await self.client.generate_embedding(cleaned_content)
            
            # Verify dimension
            if len(embedding) != self.embedding_dimension:
                raise ValidationError(
                    f"Generated embedding dimension {len(embedding)} does not match "
                    f"expected dimension {self.embedding_dimension}"
                )
            
            # Create and validate schema
            embedding_data = {
                "content": cleaned_content,
                "embedding": embedding,
                "metadata": metadata or {},
                "timestamp": datetime.now().isoformat()
            }
            
            return EmbeddingSchema(**embedding_data)
            
        except PydanticValidationError as e:
            logger.error(f"Embedding validation error: {str(e)}")
            raise ValidationError(str(e))
        except Exception as e:
            logger.error(f"Embedding generation error: {str(e)}")
            raise ProcessingError(f"Failed to generate embedding: {str(e)}")

    async def validate_and_process_chat_message(
        self,
        message: Union[str, Dict[str, Any]],
        role: str = "user"
    ) -> ChatMessageSchema:
        """
        Validate and process a chat message.
        
        Args:
            message: Message content or message dict
            role: Message role if string provided
            
        Returns:
            ChatMessageSchema: Validated message
            
        Raises:
            ValidationError: If validation fails
            ProcessingError: If processing fails
        """
        try:
            # Handle string or dict input
            if isinstance(message, str):
                message_data = {
                    "role": role,
                    "content": message,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                message_data = {
                    **message,
                    "timestamp": message.get("timestamp", datetime.now().isoformat())
                }
            
            # Clean content
            message_data["content"] = sanitize_text(
                message_data["content"],
                allow_markdown=True
            )
            
            # Validate message
            return ChatMessageSchema(**message_data)
            
        except PydanticValidationError as e:
            logger.error(f"Chat message validation error: {str(e)}")
            raise ValidationError(f"Invalid chat message: {str(e)}")
        except Exception as e:
            logger.error(f"Chat message processing error: {str(e)}")
            raise ProcessingError(f"Failed to process chat message: {str(e)}")

    def __str__(self) -> str:
        """Get string representation."""
        return f"SchemaValidator(embedding_dim={self.embedding_dimension})"
