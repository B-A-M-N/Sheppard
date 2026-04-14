"""
cmk/embedder.py — Ollama embedding wrapper.

Uses existing Ollama client infrastructure to embed atom content.
Supports batch processing with safe chunking.
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class OllamaEmbedder:
    """
    Embedding wrapper using Ollama's /api/embeddings endpoint.
    Compatible with any Ollama embedding model (nomic-embed-text, mxbai-embed-large, etc.)
    """

    def __init__(self, model: str = "nomic-embed-text", host: str = "http://localhost:11434"):
        """
        Args:
            model: Ollama embedding model name
            host: Ollama host URL
        """
        self.model = model
        self.host = host.rstrip("/")
        self._session = None

    def _get_session(self):
        """Lazy HTTP session initialization."""
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def embed(self, text: str) -> Optional[List[float]]:
        """
        Embed a single text string.

        Returns:
            List of floats (embedding vector), or None on failure.
        """
        if not text or not text.strip():
            return None

        try:
            session = self._get_session()
            resp = session.post(
                f"{self.host}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("embedding")
        except Exception as e:
            logger.warning(f"[OllamaEmbedder] Embedding failed for text '{text[:50]}...': {e}")
            return None

    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Embed a batch of texts.
        Processes sequentially (Ollama doesn't support batch embeddings yet).

        Returns:
            List of embeddings (None for failed items).
        """
        results = []
        for i, text in enumerate(texts):
            emb = self.embed(text)
            if emb is None:
                logger.debug(f"[OllamaEmbedder] Failed to embed item {i}")
            results.append(emb)
        return results

    def embed_atoms(self, atoms) -> List[Optional[List[float]]]:
        """
        Embed a list of CMKAtom objects in-place.

        Modifies each atom's embedding field directly.
        Returns list of embeddings (None for failures).
        """
        texts = [a.content for a in atoms]
        embeddings = self.embed_batch(texts)

        for atom, emb in zip(atoms, embeddings):
            if emb is not None:
                atom.embedding = emb

        return embeddings

    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """
        Compute cosine similarity between two vectors.
        """
        import numpy as np
        a_np = np.array(a, dtype=float)
        b_np = np.array(b, dtype=float)

        norm_a = np.linalg.norm(a_np)
        norm_b = np.linalg.norm(b_np)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(a_np, b_np) / (norm_a * norm_b))

    def close(self):
        """Close HTTP session."""
        if self._session:
            self._session.close()
            self._session = None
