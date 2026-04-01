import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import json
import asyncio
from ollama import AsyncClient
import numpy as np

logger = logging.getLogger(__name__)

class EmbeddingManager:
    """
    Manages embedding generation and processing for memory system
    """
    def __init__(self, embedding_client: AsyncClient, embedding_model: str):
        self.client = embedding_client
        self.model = embedding_model
        self.embedding_queue = []
        self.embedding_batch_size = 10
        self.processing = False
        self.failed_embeddings = set()
        self.embedding_cache = {}
        self.max_cache_size = 1000
        self.similarity_threshold = 0.95
        self._chroma_lock = asyncio.Lock()  # Serialize ChromaDB operations to prevent ONNX thread-safety crashes

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for given text using dedicated embedding model
        """
        try:
            # Check cache first
            cache_key = hash(text)
            if cache_key in self.embedding_cache:
                return self.embedding_cache[cache_key]

            response = await self.client.embeddings(
                model=self.model,
                prompt=text
            )
            
            if isinstance(response, dict) and 'embedding' in response:
                embedding = response['embedding']
                # Cache the result
                if len(self.embedding_cache) >= self.max_cache_size:
                    self.embedding_cache.pop(next(iter(self.embedding_cache)))
                self.embedding_cache[cache_key] = embedding
                return embedding
            return None
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            self.failed_embeddings.add(hash(text))
            return None

    async def process_embedding_batch(self, items: List[Tuple[str, str, str, float]], chroma_collections: Dict):
        """
        Process a batch of embeddings and store in ChromaDB
        """
        if self.processing:
            return

        try:
            self.processing = True
            tasks = []
            
            for item in items:
                text, key, layer, importance_score = item
                task = asyncio.create_task(self._process_single_embedding(
                    text, key, layer, importance_score, chroma_collections
                ))
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Handle results and any exceptions
            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Error in batch processing item {idx}: {str(result)}")
                    
        except Exception as e:
            logger.error(f"Error processing embedding batch: {str(e)}")
        finally:
            self.processing = False

    async def _process_single_embedding(
        self,
        text: str,
        key: str,
        layer: str,
        importance_score: float,
        chroma_collections: Dict
    ) -> bool:
        """
        Process a single embedding and store in ChromaDB
        """
        try:
            # Skip if previously failed
            if hash(text) in self.failed_embeddings:
                return False

            embedding = await self.generate_embedding(text)
            if embedding:
                # Check for similar existing embeddings
                if await self._check_similar_embeddings(embedding, layer, chroma_collections):
                    logger.info(f"Similar embedding already exists for {key}")
                    return False

                metadata = {
                    "key": key,
                    "layer": layer,
                    "importance_score": importance_score,
                    "timestamp": datetime.now().isoformat()
                }

                collection = chroma_collections.get(layer)
                if collection:
                    async with self._chroma_lock:
                        collection.add(
                            documents=[text],
                            embeddings=[embedding],
                            metadatas=[metadata],
                            ids=[f"{layer}_{key}_{datetime.now().isoformat()}"]
                        )
                    return True
            return False

        except Exception as e:
            logger.error(f"Error processing single embedding: {str(e)}")
            return False

    async def _check_similar_embeddings(
        self,
        embedding: List[float],
        layer: str,
        chroma_collections: Dict
    ) -> bool:
        """
        Check if similar embeddings already exist in ChromaDB
        """
        try:
            collection = chroma_collections.get(layer)
            if collection:
                async with self._chroma_lock:
                    results = collection.query(
                        query_embeddings=[embedding],
                        n_results=1
                    )

                if results and 'distances' in results and results['distances']:
                    distance = results['distances'][0][0]
                    similarity = 1.0 - distance
                    return similarity >= self.similarity_threshold
            return False
        except Exception as e:
            logger.error(f"Error checking similar embeddings: {str(e)}")
            return False

    async def query_similar_embeddings(
        self,
        query_embedding: List[float],
        layer: str,
        chroma_collections: Dict,
        n_results: int = 5,
        similarity_threshold: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Query similar embeddings from ChromaDB
        """
        try:
            collection = chroma_collections.get(layer)
            if not collection:
                return []

            async with self._chroma_lock:
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results
                )

            similar_items = []
            if results and isinstance(results, dict):
                for idx, doc in enumerate(results.get('documents', [[]])[0]):
                    try:
                        distance = results.get('distances', [[]])[0][idx] if 'distances' in results else 1.0
                        similarity = 1.0 - distance

                        if similarity >= similarity_threshold:
                            metadata = results.get('metadatas', [[]])[0][idx] if 'metadatas' in results else {}
                            similar_items.append({
                                'content': doc,
                                'similarity': similarity,
                                'metadata': metadata
                            })
                    except Exception as e:
                        logger.error(f"Error processing query result {idx}: {str(e)}")
                        continue

            return similar_items

        except Exception as e:
            logger.error(f"Error querying similar embeddings: {str(e)}")
            return []

    def calculate_embedding_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings
        """
        try:
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
                
            return dot_product / (norm1 * norm2)
        except Exception as e:
            logger.error(f"Error calculating embedding similarity: {str(e)}")
            return 0.0

    def add_to_embedding_queue(self, text: str, key: str, layer: str, importance_score: float) -> None:
        """
        Add item to embedding queue for batch processing
        """
        self.embedding_queue.append((text, key, layer, importance_score))
        if len(self.embedding_queue) >= self.embedding_batch_size:
            asyncio.create_task(self._process_queued_embeddings())

    async def _process_queued_embeddings(self) -> None:
        """
        Process all queued embeddings
        """
        if self.embedding_queue:
            queue_items = self.embedding_queue.copy()
            self.embedding_queue.clear()
            await self.process_embedding_batch(queue_items)

    def clear_cache(self) -> None:
        """
        Clear embedding cache
        """
        self.embedding_cache.clear()
        self.failed_embeddings.clear()

    async def shutdown(self) -> None:
        """
        Clean shutdown of embedding manager
        """
        try:
            if self.embedding_queue:
                await self._process_queued_embeddings()
            self.clear_cache()
        except Exception as e:
            logger.error(f"Error during embedding manager shutdown: {str(e)}")
