"""
cmk/config.py — Configuration for the Cognitive Memory Kernel.

Centralizes all CMK tunable parameters:
  - Embedding model settings
  - Clustering settings
  - Scoring weights
  - Retrieval thresholds
  - Store/cache settings
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class EmbeddingConfig:
    model: str = "nomic-embed-text"
    host: str = "http://localhost:11434"
    dimension: int = 768  # nomic-embed-text default
    batch_timeout: float = 30.0


@dataclass
class ClusteringConfig:
    algorithm: str = "kmeans"  # "kmeans" or "hdbscan"
    kmeans_k: int = 32
    hdbscan_min_cluster_size: int = 8
    rebuild_interval_hours: int = 24  # How often to rebuild concepts


@dataclass
class ScoringConfig:
    weights: Dict[str, float] = field(default_factory=lambda: {
        "reliability": 0.35,
        "specificity": 0.20,
        "centrality": 0.15,
        "recency": 0.10,
        "query_relevance": 0.20,
    })
    min_score_threshold: float = 0.3
    type_boost_factor: float = 1.3


@dataclass
class RetrievalConfig:
    top_k_concepts: int = 5
    top_k_atoms_per_concept: int = 10
    max_total_atoms: int = 30
    min_reliability: float = 0.3


@dataclass
class StoreConfig:
    redis_enabled: bool = True
    redis_url: str = "redis://localhost:6379"
    redis_ttl_seconds: int = 3600
    postgres_enabled: bool = True
    concepts_table: str = "cmk.concepts"
    embeddings_table: str = "cmk.atom_embeddings"


@dataclass
class CMKConfig:
    """Top-level CMK configuration."""
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    clustering: ClusteringConfig = field(default_factory=ClusteringConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    store: StoreConfig = field(default_factory=StoreConfig)

    # Feature toggles
    enable_concepts: bool = True
    enable_intent_profiling: bool = True
    enable_evidence_planning: bool = True
    enable_dynamic_scoring: bool = True
    enable_contradiction_detection: bool = True
    enable_feedback_loop: bool = True

    # Prompt settings
    max_context_length: int = 4000  # chars for LLM context
    include_low_confidence: bool = False  # Include LOW tier in context?

    @classmethod
    def from_env(cls) -> "CMKConfig":
        """Load config from environment variables (optional overrides)."""
        import os

        config = cls()

        if os.getenv("CMK_EMBED_MODEL"):
            config.embedding.model = os.environ["CMK_EMBED_MODEL"]
        if os.getenv("CMK_EMBED_HOST"):
            config.embedding.host = os.environ["CMK_EMBED_HOST"]
        if os.getenv("CMK_CLUSTER_K"):
            config.clustering.kmeans_k = int(os.environ["CMK_CLUSTER_K"])
        if os.getenv("CMK_CLUSTER_ALGO"):
            config.clustering.algorithm = os.environ["CMK_CLUSTER_ALGO"]
        if os.getenv("CMK_RETRIEVAL_TOP_K"):
            config.retrieval.top_k_concepts = int(os.environ["CMK_RETRIEVAL_TOP_K"])
        if os.getenv("CMK_DISABLE_CONCEPTS"):
            config.enable_concepts = False

        return config

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "embedding": {
                "model": self.embedding.model,
                "host": self.embedding.host,
                "dimension": self.embedding.dimension,
            },
            "clustering": {
                "algorithm": self.clustering.algorithm,
                "kmeans_k": self.clustering.kmeans_k,
                "hdbscan_min_cluster_size": self.clustering.hdbscan_min_cluster_size,
            },
            "scoring": self.scoring.weights,
            "retrieval": {
                "top_k_concepts": self.retrieval.top_k_concepts,
                "max_total_atoms": self.retrieval.max_total_atoms,
            },
            "features": {
                "concepts": self.enable_concepts,
                "intent_profiling": self.enable_intent_profiling,
                "evidence_planning": self.enable_evidence_planning,
                "dynamic_scoring": self.enable_dynamic_scoring,
                "contradiction_detection": self.enable_contradiction_detection,
                "feedback_loop": self.enable_feedback_loop,
            },
        }
