"""
Enhanced validators for LLM interactions and schema validation.
File: src/llm/validators.py
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime

from src.llm.models import ChatMessage, ChatResponse
from src.llm.exceptions import ValidationError

logger = logging.getLogger(__name__)

class SchemaValidator:
    """Validates data against schemas using LLM capabilities."""
    
    def __init__(self, llm_client):
        """
        Initialize schema validator with LLM client.
        
        Args:
            llm_client: Ollama client instance
        """
        self.client = llm_client
        self.logger = logging.getLogger(__name__)
    
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
            # Validate required fields
            required_fields = {'content', 'embedding'}
            missing_fields = required_fields - set(data.keys())
            if missing_fields:
                return False, f"Missing required fields: {', '.join(missing_fields)}"
            
            # Validate content
            if not isinstance(data['content'], str) or not data['content'].strip():
                return False, "Content must be a non-empty string"
            
            # Validate embedding
            if not isinstance(data['embedding'], list):
                return False, "Embedding must be a list of floats"
            if not all(isinstance(x, (int, float)) for x in data['embedding']):
                return False, "All embedding values must be numeric"
            
            # Validate metadata if present
            if 'metadata' in data and not isinstance(data['metadata'], dict):
                return False, "Metadata must be a dictionary"
            
            return True, None
            
        except Exception as e:
            self.logger.error(f"Embedding validation error: {str(e)}")
            return False, str(e)
    
    async def validate_chat_message(
        self,
        message: Union[Dict[str, Any], ChatMessage]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a chat message.
        
        Args:
            message: Message to validate
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            # Convert to dict if needed
            if isinstance(message, ChatMessage):
                message = message.model_dump()
            
            # Validate required fields
            required_fields = {'role', 'content'}
            missing_fields = required_fields - set(message.keys())
            if missing_fields:
                return False, f"Missing required fields: {', '.join(missing_fields)}"
            
            # Validate role
            valid_roles = {'user', 'assistant', 'system'}
            if message['role'] not in valid_roles:
                return False, f"Invalid role. Must be one of: {', '.join(valid_roles)}"
            
            # Validate content
            if not isinstance(message['content'], str) or not message['content'].strip():
                return False, "Content must be a non-empty string"
            
            # Validate images if present
            if 'images' in message:
                if not isinstance(message['images'], list):
                    return False, "Images must be a list"
                if not all(isinstance(img, str) for img in message['images']):
                    return False, "All images must be base64 strings"
            
            return True, None
            
        except Exception as e:
            self.logger.error(f"Chat message validation error: {str(e)}")
            return False, str(e)
    
    async def validate_tool_call(
        self,
        data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a tool call request.
        
        Args:
            data: Tool call data to validate
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            # Validate required fields
            required_fields = {'name', 'parameters'}
            missing_fields = required_fields - set(data.keys())
            if missing_fields:
                return False, f"Missing required fields: {', '.join(missing_fields)}"
            
            # Validate name
            if not isinstance(data['name'], str) or not data['name'].strip():
                return False, "Tool name must be a non-empty string"
            
            # Validate parameters
            if not isinstance(data['parameters'], dict):
                return False, "Parameters must be a dictionary"
            
            return True, None
            
        except Exception as e:
            self.logger.error(f"Tool call validation error: {str(e)}")
            return False, str(e)

class ChatResponseValidator:
    """Validates and enhances chat responses."""
    
    def __init__(self, llm_client):
        """
        Initialize response validator.
        
        Args:
            llm_client: Ollama client instance
        """
        self.client = llm_client
        self.logger = logging.getLogger(__name__)
        
        # Response validation patterns
        self.validation_patterns = {
            'code_block': r'```[\s\S]*?```',
            'list_item': r'^\s*[-*]\s+.+$',
            'table_row': r'^\s*\|.+\|\s*$'
        }
    
    async def validate_response(
        self,
        response: ChatResponse,
        original_query: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a chat response.
        
        Args:
            response: Response to validate
            original_query: Original query that generated the response
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            # Validate basic structure
            if not response.content:
                return False, "Empty response content"
            
            # Validate response format
            if '```' in original_query:
                # If query contains code, response should too
                if '```' not in response.content:
                    return False, "Missing code block in response"
            
            if '?' in original_query:
                # If query is a question, response should be informative
                min_length = 50
                if len(response.content) < min_length:
                    return False, f"Response too short for question ({len(response.content)} chars)"
            
            # Check response coherence
            coherence = await self._check_response_coherence(
                response.content,
                original_query
            )
            if not coherence['is_coherent']:
                return False, coherence['message']
            
            return True, None
            
        except Exception as e:
            self.logger.error(f"Response validation error: {str(e)}")
            return False, str(e)
    
    async def _check_response_coherence(
        self,
        content: str,
        query: str
    ) -> Dict[str, Any]:
        """Check if response is coherent with query."""
        try:
            # Check for command/instruction acknowledgment
            if 'please' in query.lower() or 'could you' in query.lower():
                if not any(word in content.lower() for word in ['here', 'sure', 'yes', 'okay']):
                    return {
                        'is_coherent': False,
                        'message': "Response doesn't acknowledge request"
                    }
            
            # Check for question answering
            if '?' in query:
                if not any(char in content for char in '.!'):
                    return {
                        'is_coherent': False,
                        'message': "Response doesn't contain complete sentences"
                    }
            
            # Check for code formatting
            if '```' in content:
                if content.count('```') % 2 != 0:
                    return {
                        'is_coherent': False,
                        'message': "Mismatched code block markers"
                    }
            
            return {'is_coherent': True, 'message': None}
            
        except Exception as e:
            self.logger.error(f"Coherence check error: {str(e)}")
            return {
                'is_coherent': False,
                'message': f"Coherence check failed: {str(e)}"
            }

class EmbeddingValidator:
    """Validates embeddings and their usage."""
    
    def __init__(self, embedding_dimension: int = 1024):
        """
        Initialize embedding validator.
        
        Args:
            embedding_dimension: Expected embedding dimension
        """
        self.embedding_dimension = embedding_dimension
        self.logger = logging.getLogger(__name__)
    
    async def validate_embedding(
        self,
        embedding: List[float],
        content: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate an embedding vector.
        
        Args:
            embedding: Embedding to validate
            content: Optional content that generated the embedding
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            # Check type and content
            if not isinstance(embedding, list):
                return False, "Embedding must be a list"
            
            if not embedding:
                return False, "Empty embedding"
            
            # Check values
            if not all(isinstance(x, (int, float)) for x in embedding):
                return False, "All embedding values must be numeric"
            
            # Check dimension
            if len(embedding) != self.embedding_dimension:
                return False, f"Incorrect embedding dimension: {len(embedding)} (expected {self.embedding_dimension})"
            
            # Check range
            if not all(-10 <= x <= 10 for x in embedding):
                return False, "Embedding values outside expected range"
            
            # Validate with content if provided
            if content:
                if not isinstance(content, str):
                    return False, "Content must be a string"
                if not content.strip():
                    return False, "Empty content"
            
            return True, None
            
        except Exception as e:
            self.logger.error(f"Embedding validation error: {str(e)}")
            return False, str(e)
    
    async def validate_embedding_batch(
        self,
        embeddings: List[List[float]]
    ) -> Dict[str, Any]:
        """
        Validate a batch of embeddings.
        
        Args:
            embeddings: List of embeddings to validate
            
        Returns:
            Dict[str, Any]: Validation results
        """
        results = {
            "is_valid": True,
            "total_embeddings": len(embeddings),
            "valid_embeddings": 0,
            "errors": []
        }
        
        for i, embedding in enumerate(embeddings):
            is_valid, error = await self.validate_embedding(embedding)
            if is_valid:
                results["valid_embeddings"] += 1
            else:
                results["is_valid"] = False
                results["errors"].append({
                    "index": i,
                    "error": error
                })
        
        return results
