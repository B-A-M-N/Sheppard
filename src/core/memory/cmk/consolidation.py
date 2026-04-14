"""
cmk/consolidation.py — Episodic Compression Pipeline.

The hippocampus → cortex consolidation of Sheppard.

Pipeline:
  1. Fetch atoms per topic
  2. Cluster semantically similar atoms (via embeddings)
  3. LLM synthesis: merge cluster → single canonical claim
  4. Upsert into Canonical Knowledge Store
  5. Compute authority scores
  6. Create belief nodes + edges in global graph

Run after /learn cycles or on schedule.
"""

import logging
import uuid
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from .types import CMKAtom
from .authority import CanonicalKnowledgeStore, CanonicalClaim
from .embedder import OllamaEmbedder

logger = logging.getLogger(__name__)


# LLM synthesis prompt
CONSOLIDATION_PROMPT = """\
You are a knowledge distillation engine.

TASK:
Merge multiple evidence atoms into a single canonical claim.

INPUT:
The following atoms represent extracted facts about a topic.
Some may overlap, contradict, or complement each other.

RULES:
1. Preserve uncertainty — don't inflate confidence beyond what evidence supports
2. Resolve contradictions explicitly — if atoms conflict, note it
3. Prefer higher quality sources (higher confidence atoms)
4. Do NOT hallucinate — only synthesize what the evidence supports
5. Output a single, clear, standalone claim

OUTPUT JSON ONLY:
{
  "claim": "The synthesized canonical claim",
  "confidence": 0.0-1.0,
  "supporting_atoms": ["atom_id1", "atom_id2"],
  "contradicting_atoms": ["atom_id3"]
}
"""


class ConsolidationPipeline:
    """
    Episodic → Semantic compression pipeline.

    Converts raw atoms into distilled canonical claims.
    """

    def __init__(
        self,
        cks: CanonicalKnowledgeStore,
        embedder: OllamaEmbedder,
        llm_client=None,
        llm_model: str = "mistral",
    ):
        self.cks = cks
        self.embedder = embedder
        self.llm_client = llm_client
        self.llm_model = llm_model

    async def consolidate_topic(
        self,
        topic_id: str,
        atoms: List[CMKAtom],
    ) -> List[str]:
        """
        Consolidate atoms for a topic into canonical claims.

        Args:
            topic_id: Topic identifier
            atoms: Raw atoms to consolidate

        Returns:
            List of canonical claim IDs created/updated
        """
        if not atoms:
            return []

        # Step 1: Cluster atoms by semantic similarity
        clusters = self._cluster_atoms(atoms)
        logger.info(f"[Consolidation] {topic_id}: {len(atoms)} atoms → {len(clusters)} clusters")

        # Step 2: Synthesize each cluster
        claim_ids = []
        for cluster in clusters:
            claim_id = await self._synthesize_cluster(topic_id, cluster)
            if claim_id:
                claim_ids.append(claim_id)

        logger.info(f"[Consolidation] {topic_id}: {len(claim_ids)} canonical claims created")

        return claim_ids

    def _cluster_atoms(self, atoms: List[CMKAtom]) -> List[List[CMKAtom]]:
        """
        Cluster atoms by semantic similarity.

        Uses embedding similarity if available, falls back to type-based grouping.
        """
        atoms_with_embeddings = [a for a in atoms if a.embedding is not None]

        if len(atoms_with_embeddings) < 2:
            return [atoms]

        # Simple clustering: for each atom, find nearest neighbor cluster
        clusters: List[List[CMKAtom]] = []

        for atom in atoms_with_embeddings:
            best_cluster = None
            best_similarity = 0.0

            for i, cluster in enumerate(clusters):
                # Compare against cluster centroid
                centroid = self._compute_centroid(cluster)
                sim = _cosine(atom.embedding, centroid)
                if sim > best_similarity:
                    best_similarity = sim
                    best_cluster = i

            if best_cluster is not None and best_similarity > 0.75:
                clusters[best_cluster].append(atom)
            else:
                clusters.append([atom])

        # Add atoms without embeddings as singletons
        atoms_without = [a for a in atoms if a.embedding is None]
        for atom in atoms_without:
            clusters.append([atom])

        return clusters

    def _compute_centroid(self, atoms: List[CMKAtom]) -> List[float]:
        """Compute embedding centroid of a cluster."""
        import numpy as np
        embeddings = [a.embedding for a in atoms if a.embedding is not None]
        if not embeddings:
            return []
        return np.mean(np.array(embeddings, dtype=float), axis=0).tolist()

    async def _synthesize_cluster(
        self,
        topic_id: str,
        cluster: List[CMKAtom],
    ) -> Optional[str]:
        """
        Synthesize a cluster into a single canonical claim.

        If LLM is available, use it for synthesis.
        Otherwise, use the highest-confidence atom as the canonical claim.
        """
        if not cluster:
            return None

        if len(cluster) == 1:
            # Single atom — use directly as canonical claim
            atom = cluster[0]
            claim = CanonicalClaim(
                id=str(uuid.uuid4()),
                topic_id=topic_id,
                claim=atom.content,
                confidence=atom.reliability,
                supporting_atom_ids=[atom.id],
                supporting_count=1,
            )
            claim.compute_authority()
            return await self.cks.upsert_claim(claim)

        # Multiple atoms — synthesize
        if self.llm_client:
            claim = await self._llm_synthesize(cluster, topic_id)
        else:
            claim = self._fallback_synthesize(cluster, topic_id)

        return await self.cks.upsert_claim(claim)

    async def _llm_synthesize(
        self,
        cluster: List[CMKAtom],
        topic_id: str,
    ) -> CanonicalClaim:
        """Use LLM to synthesize a cluster into a canonical claim."""
        # Format atoms for LLM
        atom_texts = []
        for atom in cluster:
            atom_texts.append(
                f"[{atom.id}] (reliability={atom.reliability:.2f}) {atom.content}"
            )

        prompt = (
            f"Topic: {topic_id}\n\n"
            "Evidence atoms:\n" + "\n".join(atom_texts)
        )

        messages = [
            {"role": "system", "content": CONSOLIDATION_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.llm_client.chat(
                model=self.llm_model,
                messages=messages,
                format="json",
            )

            content = response.get("message", {}).get("content", "")
            if isinstance(content, str):
                result = json.loads(content)
            else:
                result = content

            return CanonicalClaim(
                id=str(uuid.uuid4()),
                topic_id=topic_id,
                claim=result.get("claim", "No claim synthesized"),
                confidence=float(result.get("confidence", 0.5)),
                supporting_atom_ids=result.get("supporting_atoms", []),
                contradicting_atom_ids=result.get("contradicting_atoms", []),
                supporting_count=len(result.get("supporting_atoms", [])),
                contradicting_count=len(result.get("contradicting_atoms", [])),
            )
        except Exception as e:
            logger.warning(f"[Consolidation] LLM synthesis failed: {e}")
            return self._fallback_synthesize(cluster, topic_id)

    def _fallback_synthesize(
        self,
        cluster: List[CMKAtom],
        topic_id: str,
    ) -> CanonicalClaim:
        """
        Fallback synthesis: use highest-confidence atom + concatenate others.
        """
        sorted_atoms = sorted(cluster, key=lambda a: a.reliability, reverse=True)
        best = sorted_atoms[0]

        # Build claim from best atom
        claim_text = best.content

        # If other atoms exist, append them as supporting evidence
        if len(sorted_atoms) > 1:
            others = sorted_atoms[1:4]  # Up to 3 additional
            others_text = "; ".join(a.content for a in others)
            claim_text = f"{claim_text}. Additional context: {others_text}"

        supporting_ids = [a.id for a in sorted_atoms]
        contradicting_ids = [a.id for a in sorted_atoms if a.reliability < 0.4]

        return CanonicalClaim(
            id=str(uuid.uuid4()),
            topic_id=topic_id,
            claim=claim_text,
            confidence=sum(a.reliability for a in cluster) / len(cluster),
            supporting_atom_ids=supporting_ids,
            contradicting_atom_ids=contradicting_ids,
            supporting_count=len(supporting_ids) - len(contradicting_ids),
            contradicting_count=len(contradicting_ids),
        )


def _cosine(a: List[float], b: List[float]) -> float:
    import numpy as np
    if not a or not b or len(a) != len(b):
        return 0.0
    a_np = np.array(a, dtype=float)
    b_np = np.array(b, dtype=float)
    norm_a = np.linalg.norm(a_np)
    norm_b = np.linalg.norm(b_np)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a_np, b_np) / (norm_a * norm_b))
