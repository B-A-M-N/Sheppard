import re
import json
import requests
import os
import logging
from .config import LLM_MODEL, EMBEDDING_MODEL

logger = logging.getLogger(__name__)

# We'll use direct requests for the local Ollama API to avoid event loop conflicts 
# in Archivist's synchronous thread.
OLLAMA_URL = os.getenv('OLLAMA_API_HOST', 'http://localhost') + ":" + os.getenv('OLLAMA_API_PORT', '11434')

def generate(prompt: str, system_prompt: str = None, model: str = LLM_MODEL, format: str = None, options: dict = None):
    """
    Generate text using local Ollama API via synchronous requests.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt[:10000]})
    
    # Safety clip for context
    messages.append({"role": "user", "content": prompt[:30000]})
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "num_ctx": 12288,
            "temperature": 0.4
        }
    }
    
    if format:
        payload["format"] = format
    if options:
        payload["options"].update(options)
        
    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
        response.raise_for_status()
        return response.json()['message']['content']
    except Exception as e:
        logger.error(f"[LLM ERROR] Generation failed: {e}")
        return ""

def extract_json(text: str):
    try:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            return text[start:end+1]
        
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1:
            return text[start:end+1]
    except:
        pass
    return text.strip()
    
def embed(text: str, model: str = EMBEDDING_MODEL):
    """
    Generate embedding using local Ollama API via synchronous requests.
    """
    if not text or not text.strip():
        return [0.0] * 1024 # Default dimension fallback
        
    # mxbai-embed-large has 512 token context. 
    # Use a safe character limit to avoid "exceeds context length" errors.
    safe_text = text.strip()[:2000] 
    
    payload = {
        "model": model,
        "prompt": safe_text
    }
    
    try:
        response = requests.post(f"{OLLAMA_URL}/api/embeddings", json=payload, timeout=30)
        
        # If we hit a context length error even at 2000 chars, try 1000
        if response.status_code == 413 or (response.status_code != 200 and "context length" in response.text.lower()):
            payload["prompt"] = safe_text[:1000]
            response = requests.post(f"{OLLAMA_URL}/api/embeddings", json=payload, timeout=30)
            
        response.raise_for_status()
        return response.json()['embedding']
    except Exception as e:
        logger.error(f"[LLM ERROR] Embedding failed for text of length {len(safe_text)}: {type(e).__name__}")
        return None

def set_sheppard_client(client):
    # Kept for compatibility with loop.py calls, but we prefer direct requests here
    pass
