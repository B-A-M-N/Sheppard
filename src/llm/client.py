"""
llm/client.py — Multi-Host Enhanced wrapper for Ollama API.
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
    """Enhanced wrapper for Ollama API supporting Split-Host Routing."""
    
    def __init__(
        self, 
        model_router: Optional[ModelRouter] = None,
        api_base: Optional[str] = None
    ):
        """Initialize Ollama client."""
        self.router = model_router or ModelRouter()
        # self.api_base is kept for legacy, but we use router.get(task).api_host now
        self.default_api_base = api_base or settings.ollama_api_base
        self.sessions: Dict[str, aiohttp.ClientSession] = {}
        self.MAX_RETRIES = 3
        self.RETRY_DELAY = 1.0

    async def initialize(self) -> None:
        # Sessions are created lazily via _get_session
        pass

    async def _get_session(self, host: str) -> aiohttp.ClientSession:
        """Get or create an aiohttp session for a specific host."""
        # Ensure host has port
        if not any(x in host for x in [":11434", ":8080", ":3000"]):
            host = f"{host}:11434"
            
        if host not in self.sessions or self.sessions[host].closed:
            timeout = aiohttp.ClientTimeout(
                total=settings.REQUEST_TIMEOUT,
                connect=settings.CONNECTION_TIMEOUT,
                sock_read=settings.REQUEST_TIMEOUT
            )
            self.sessions[host] = aiohttp.ClientSession(base_url=host, timeout=timeout)
            logger.debug(f"Initialized new session for host: {host}")
        return self.sessions[host]

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
        """Generate embeddings using the dedicated embedding host."""
        config = self.router.get(TaskType.EMBEDDING)
        last_error = None

        safe_text = text.strip()[:2000]

        for attempt in range(self.MAX_RETRIES):
            try:
                # Fresh session per request to avoid segfaults
                timeout = aiohttp.ClientTimeout(
                    total=settings.REQUEST_TIMEOUT,
                    connect=settings.CONNECTION_TIMEOUT,
                    sock_read=settings.REQUEST_TIMEOUT
                )
                connector = aiohttp.TCPConnector(force_close=True)
                async with aiohttp.ClientSession(base_url=config.api_host, timeout=timeout, connector=connector) as session:
                    payload = {'model': config.model_name, 'prompt': safe_text}

                    async with session.post("/api/embeddings", json=payload) as response:
                        if response.status != 200:
                            await self._handle_api_error(response, "embedding", safe_text)
                        result = await response.json()
                        return result.get('embedding', [])
            except Exception as e:
                last_error = e
                await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))

        raise EmbeddingError(f"Embedding failed after retries: {last_error}")

    async def embed(self, text: str) -> List[float]:
        return await self.generate_embedding(text)

    async def complete(self, task: TaskType, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 1000) -> str:
        """Non-streaming completion routed to the appropriate host."""
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
        if config.seed is not None:
            payload['options']['seed'] = config.seed

        try:
            # Create a fresh session each time to avoid reuse issues leading to segfaults
            timeout = aiohttp.ClientTimeout(
                total=settings.REQUEST_TIMEOUT,
                connect=settings.CONNECTION_TIMEOUT,
                sock_read=settings.REQUEST_TIMEOUT
            )
            # Use force_close to prevent connection reuse
            connector = aiohttp.TCPConnector(force_close=True)
            async with aiohttp.ClientSession(base_url=config.api_host, timeout=timeout, connector=connector) as session:
                async with session.post("/api/chat", json=payload) as response:
                    if response.status != 200:
                        await self._handle_api_error(response, "completion")
                    result = await response.json()
                    return result['message']['content']
        except Exception as e:
            logger.error(f"Completion failed on {config.api_host}: {e}")
            return ""

    async def chat(self, messages: List[dict], stream: bool = True, **kwargs) -> AsyncGenerator[Any, None]:
        model_cfg = self.router.get(TaskType.CHAT)
        model = kwargs.pop('model', model_cfg.model_name)
        
        class ChunkWrap:
            def __init__(self, content): self.content = content

        async for token in self.chat_stream(model=model, messages=messages, **kwargs):
            yield ChunkWrap(token)

    async def chat_stream(self, model: str, messages: List[dict], system_prompt: Optional[str] = None, **kwargs) -> AsyncGenerator[str, None]:
        """Streaming chat routed to the primary reasoning host."""
        config = self.router.get(TaskType.CHAT)
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload = {
            'model': model,
            'messages': full_messages,
            'stream': True,
            'options': {
                'temperature': kwargs.get('temperature', config.temperature),
                'top_p': kwargs.get('top_p', 0.9),
            }
        }

        try:
            # Fresh session with force_close to avoid segfaults from connection reuse
            timeout = aiohttp.ClientTimeout(
                total=settings.REQUEST_TIMEOUT,
                connect=settings.CONNECTION_TIMEOUT,
                sock_read=settings.REQUEST_TIMEOUT
            )
            connector = aiohttp.TCPConnector(force_close=True)
            async with aiohttp.ClientSession(base_url=config.api_host, timeout=timeout, connector=connector) as session:
                async with session.post("/api/chat", json=payload) as response:
                    if response.status != 200:
                        await self._handle_api_error(response, "chat_stream")

                    async for line in response.content:
                        if line:
                            try:
                                chunk = json.loads(line)
                                if 'message' in chunk and 'content' in chunk['message']:
                                    yield chunk['message']['content']
                            except: continue
        except Exception as e:
            logger.error(f"Chat stream failed on {config.api_host}: {e}")

    async def cleanup(self) -> None:
        for host, session in self.sessions.items():
            if not session.closed:
                await session.close()
        self.sessions.clear()
