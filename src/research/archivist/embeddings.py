import hashlib
from .config import EMBEDDING_MODEL
from . import llm

# Initialize FastEmbed model (lazy loading)
_MODEL_INSTANCE = None

def get_model():
    global _MODEL_INSTANCE
    if _MODEL_INSTANCE is None:
        try:
            from fastembed import TextEmbedding
            _MODEL_INSTANCE = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        except:
            return None
    return _MODEL_INSTANCE

# Simple local cache to prevent redundant embedding of the same text
_EMBEDDING_CACHE = {}

def get_embedding(text: str) -> list[float]:
    """
    Generate embeddings for a single string using Sheppard (Ollama) or FastEmbed fallback.
    """
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    if text_hash in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[text_hash]
    
    # Try Sheppard first
    try:
        embedding = llm.embed(text)
        if embedding:
            _EMBEDDING_CACHE[text_hash] = embedding
            return embedding
    except:
        pass

    # Fallback to FastEmbed
    model = get_model()
    if model:
        embedding = list(model.embed([text]))[0].tolist()
        _EMBEDDING_CACHE[text_hash] = embedding
        return embedding
    
    return []

def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts.
    """
    if not texts:
        return []
        
    results = []
    for text in texts:
        results.append(get_embedding(text))
            
    return results
