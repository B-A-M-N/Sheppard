"""
llm/client.py — Enhanced wrapper for Ollama API with Model Routing.
"""

import json
import logging
import aiohttp
import asyncio
from typing import AsyncGenerator, Optional, Dict, Any, List, Union
from datetime import datetime

from src.config.settings import settings
from src.llm.model_router import ModelRouter, TaskType
from src.llm.exceptions import (
    ModelNotFoundError,
    APIError,
    TokenLimitError,
    EmbeddingError,
    TimeoutError,
    ServiceUnavailableError
)

logger = logging.getLogger(__name__)

class OllamaClient:
    """Enhanced wrapper for Ollama API with ModelRouter and error handling."""
    
    def __init__(
        self, 
        model_router: Optional[ModelRouter] = None,
        api_base: Optional[str] = None
    ):
        """Initialize Ollama client."""
        self.router = model_router or ModelRouter()
        self.api_base = api_base or settings.ollama_api_base
        self.session = None
        self.MAX_RETRIES = 3
        self.RETRY_DELAY = 1.0

    async def initialize(self) -> None:
        await self._ensure_session()

    async def _ensure_session(self) -> None:
        """Ensure aiohttp session exists and is attached to the current loop."""
        current_loop = asyncio.get_event_loop()
        if self.session is None or self.session.closed or getattr(self, '_session_loop', None) != current_loop:
            if self.session and not self.session.closed:
                await self.session.close()
            timeout = aiohttp.ClientTimeout(total=settings.REQUEST_TIMEOUT)
            self.session = aiohttp.ClientSession(timeout=timeout)
            self._session_loop = current_loop

    async def _handle_api_error(self, response: aiohttp.ClientResponse, operation: str, safe_text: str = "") -> None:
        try:
            error_text = await response.text()
            error_data = json.loads(error_text)
            error_msg = error_data.get('error', 'Unknown API error')
        except:
            error_text = "Could not parse error response"
            error_msg = f"API call failed with status {response.status}"
        
        logger.error(f"{operation} failed: {error_msg}")
        
        if response.status == 404:
            raise ModelNotFoundError("Requested model not found")
        elif response.status == 413 or "exceeds the context length" in error_msg.lower():
            raise TokenLimitError(limit=2048, current=len(safe_text))
        else:
            raise APIError(f"API error ({response.status}): {error_msg}")

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embeddings using the routing-defined embed model."""
        model_name = self.router.get_model_name(TaskType.EMBEDDING)
        last_error = None
        
        # Clip to 2000 chars for safety (mxbai has 512 token context)
        safe_text = text.strip()[:2000]
        
        for attempt in range(self.MAX_RETRIES):
            try:
                await self._ensure_session()
                url = f"{self.api_base}/api/embeddings"
                payload = {'model': model_name, 'prompt': safe_text}
                
                async with self.session.post(url, json=payload) as response:
                    if response.status != 200:
                        await self._handle_api_error(response, "embedding", safe_text)
                    result = await response.json()
                    return result.get('embedding', [])
            except Exception as e:
                last_error = e
                await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
        
        raise EmbeddingError(f"Embedding failed after retries: {last_error}")

    async def embed(self, text: str) -> List[float]:
        """Legacy alias for generate_embedding."""
        return await self.generate_embedding(text)

    async def complete(self, task: TaskType, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 1000) -> str:
        """Non-streaming completion for background tasks."""
        config = self.router.get(task)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            'model': config.model_name,
            'messages': messages,
            'stream': False,
            'options': {
                'temperature': config.temperature,
                'num_predict': max_tokens
            }
        }

        try:
            await self._ensure_session()
            async with self.session.post(f"{self.api_base}/api/chat", json=payload) as response:
                if response.status != 200:
                    await self._handle_api_error(response, "completion")
                result = await response.json()
                return result['message']['content']
        except Exception as e:
            logger.error(f"Completion failed: {e}")
            return ""

    async def chat(self, messages: List[dict], stream: bool = True, **kwargs) -> AsyncGenerator[Any, None]:
        """Backward compatibility wrapper for chat_stream."""
        model = kwargs.get('model') or self.router.get_model_name(TaskType.CHAT)
        
        # We need to return an object with a .content attribute to match legacy expectations
        class ChunkWrap:
            def __init__(self, content): self.content = content

        async for token in self.chat_stream(model=model, messages=messages):
            yield ChunkWrap(token)

    async def chat_stream(self, model: str, messages: List[dict], system_prompt: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Streaming chat for CLI interaction."""
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload = {
            'model': model,
            'messages': full_messages,
            'stream': True
        }

        try:
            await self._ensure_session()
            async with self.session.post(f"{self.api_base}/api/chat", json=payload) as response:
                if response.status != 200:
                    await self._handle_api_error(response, "chat_stream")
                
                async for line in response.content:
                    if line:
                        chunk = json.loads(line)
                        if 'message' in chunk and 'content' in chunk['message']:
                            yield chunk['message']['content']
        except Exception as e:
            logger.error(f"Chat stream failed: {e}")

    async def cleanup(self) -> None:
        if self.session:
            await self.session.close()
