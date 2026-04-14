"""
cmk/clustering.py — Atom clustering into concept clusters.

Default: KMeans (fast, stable, predictable)
Optional: HDBSCAN (better for irregular clusters, but heavier dependency)
"""

import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


def cluster_kmeans(vectors: List[List[float]], k: int = 12) -> Tuple[Dict[int, List[int]], List[List[float]]]:
    """
    Cluster embedding vectors using KMeans.

    Args:
        vectors: List of embedding vectors
        k: Number of clusters

    Returns:
        (clusters dict mapping cluster_id → atom_indices, centroid_vectors)
    """
    try:
        import numpy as np
        from sklearn.cluster import KMeans
    except ImportError:
        logger.warning("[clustering] sklearn not available, falling back to simple clustering")
        return _fallback_cluster(vectors, k)

    vectors_np = np.array(vectors, dtype=float)

    # Handle edge case: fewer vectors than clusters
    actual_k = min(k, len(vectors))
    if actual_k < 2:
        return {0: list(range(len(vectors)))}, vectors

    model = KMeans(n_clusters=actual_k, n_init="auto", random_state=42, max_iter=100)
    labels = model.fit_predict(vectors_np)

    clusters: Dict[int, List[int]] = {}
    for idx, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(idx)

    centroids = model.cluster_centers_.tolist()

    return clusters, centroids


def cluster_hdbscan(vectors: List[List[float]], min_cluster_size: int = 5) -> Dict[int, List[int]]:
    """
    Cluster embedding vectors using HDBSCAN.

    Better for irregular cluster shapes, but requires hdbscan package.
    Returns dict mapping cluster_id → atom_indices (excludes noise points with label -1).

    Args:
        vectors: List of embedding vectors
        min_cluster_size: Minimum cluster size

    Returns:
        clusters dict (no centroids — compute separately if needed)
    """
    try:
        import hdbscan
    except ImportError:
        logger.warning("[clustering] hdbscan not available, falling back to KMeans")
        clusters, _ = cluster_kmeans(vectors)
        return clusters

    import numpy as np
    vectors_np = np.array(vectors, dtype=float)

    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean")
    labels = clusterer.fit_predict(vectors_np)

    clusters: Dict[int, List[int]] = {}
    for idx, label in enumerate(labels):
        if label == -1:  # Noise points
            continue
        clusters.setdefault(int(label), []).append(idx)

    return clusters


def _fallback_cluster(vectors: List[List[float]], k: int) -> Tuple[Dict[int, List[int]], List[List[float]]]:
    """
    Simple fallback: assign vectors to k buckets by index.
    Used when sklearn is not available.
    """
    clusters: Dict[int, List[int]] = {}
    for i in range(len(vectors)):
        cluster_id = i % k
        clusters.setdefault(cluster_id, []).append(i)

    # Compute simple centroids (mean of vectors in each cluster)
    import numpy as np
    centroids = []
    for cluster_id in sorted(clusters.keys()):
        indices = clusters[cluster_id]
        cluster_vectors = [vectors[i] for i in indices]
        centroid = np.mean(np.array(cluster_vectors, dtype=float), axis=0).tolist()
        centroids.append(centroid)

    return clusters, centroids


def compute_centroid(vectors: List[List[float]]) -> List[float]:
    """
    Compute centroid (mean vector) from a list of embedding vectors.
    """
    import numpy as np
    if not vectors:
        return []
    return np.mean(np.array(vectors, dtype=float), axis=0).tolist()
