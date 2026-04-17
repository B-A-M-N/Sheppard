"""
cmk/authority.py — Authority Score Engine + Canonical Knowledge Store.

Authority formula:
  authority_score =
      log(1 + supporting_count) * 0.4
    + confidence * 0.3
    + recency_decay * 0.1
    + contradiction_resolution_score * 0.2

This is what makes the system "expert-like" — repeated confirmation
strengthens truth, contradictions weaken it, staleness gently fades it.
"""

import math
import logging
import uuid
import json
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Authority score weights
AUTHORITY_WEIGHTS = {
    "support_count": 0.4,
    "confidence": 0.3,
    "recency": 0.1,
    "contradiction_resolution": 0.2,
}

# Recency half-life for authority (days)
# Knowledge doesn't "expire" but stale claims get gently deprioritized
# Fast-changing domains (AI, crypto): tau ~ 30
# Stable domains (physics, math): tau ~ 90
AUTHORITY_RECENCY_TAU = 45.0


@dataclass
class CanonicalClaim:
    """A distilled, multi-source canonical claim."""
    id: str
    topic_id: str
    claim: str
    confidence: float

    supporting_atom_ids: List[str] = field(default_factory=list)
    contradicting_atom_ids: List[str] = field(default_factory=list)

    supporting_count: int = 0
    contradicting_count: int = 0

    authority_score: float = 0.0
    stability_score: float = 0.0
    contradiction_pressure: float = 0.0
    revision_count: int = 0

    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def compute_authority(self) -> float:
        """
        Compute authority score using the canonical formula.
        """
        # Supporting count (social proof, log-scaled to prevent runaway growth)
        support_component = math.log(1 + self.supporting_count)

        # Confidence (model belief strength)
        confidence_component = self.confidence

        # Recency decay (soft, not deletion)
        days_old = (datetime.now(timezone.utc) - self.updated_at).days
        recency_component = math.exp(-days_old / AUTHORITY_RECENCY_TAU)

        # Contradiction resolution (resolved = +1, unresolved = +0.5, disputed = +0.2)
        if self.contradicting_count == 0:
            contradiction_component = 1.0
        elif self.contradicting_count <= self.supporting_count:
            contradiction_component = 0.5
        else:
            contradiction_component = 0.2

        self.authority_score = (
            AUTHORITY_WEIGHTS["support_count"] * support_component +
            AUTHORITY_WEIGHTS["confidence"] * confidence_component +
            AUTHORITY_WEIGHTS["recency"] * recency_component +
            AUTHORITY_WEIGHTS["contradiction_resolution"] * contradiction_component
        )

        # Normalize to 0-1 range (log component can push it above 1)
        # Max possible raw score ≈ 0.4*3 + 0.3*1 + 0.1*1 + 0.2*1 = 2.0
        self.authority_score = min(1.0, self.authority_score)

        return self.authority_score

    def compute_stability(self) -> float:
        """
        Compute stability score:
          stability = authority - contradiction_pressure + reinforcement - staleness
        """
        contradiction_pressure = self.contradicting_count * 0.3
        reinforcement = math.log(1 + self.supporting_count) * 0.2
        days_old = (datetime.now(timezone.utc) - self.updated_at).days
        staleness = 1.0 - math.exp(-days_old / (AUTHORITY_RECENCY_TAU * 2))

        self.stability_score = max(0.0, min(1.0,
            self.authority_score
            - contradiction_pressure
            + reinforcement
            - staleness
        ))

        return self.stability_score


class CanonicalKnowledgeStore:
    """
    Canonical Knowledge Store — the distilled truth layer.

    Stores and retrieves canonical claims, not raw atoms.
    Self-improving via reinforcement and contradiction resolution.
    """

    def __init__(self, pg_pool=None):
        self.pg_pool = pg_pool
        self._claims: Dict[str, CanonicalClaim] = {}  # In-memory cache

    async def upsert_claim(self, claim: CanonicalClaim) -> str:
        """
        Insert or update a canonical claim.

        If a similar claim exists (same topic_id + similar content), merge into it.
        Otherwise, insert new.
        """
        # Check for existing similar claim
        existing = await self._find_similar(claim.topic_id, claim.claim)

        if existing:
            # Merge: update version, blend confidence, append supporting atoms
            claim.id = existing.id
            claim.version = existing.version + 1
            claim.confidence = (existing.confidence + claim.confidence) / 2
            claim.supporting_count = existing.supporting_count + len(claim.supporting_atom_ids)
            claim.supporting_atom_ids = existing.supporting_atom_ids + claim.supporting_atom_ids
            claim.contradicting_count = existing.contradicting_count + len(claim.contradicting_atom_ids)
            claim.contradicting_atom_ids = existing.contradicting_atom_ids + claim.contradicting_atom_ids
            claim.revision_count = existing.revision_count
            claim.created_at = existing.created_at

        # Compute scores
        claim.compute_authority()
        claim.compute_stability()

        # Cache
        self._claims[claim.id] = claim

        # Persist to Postgres
        if self.pg_pool:
            await self._persist_claim(claim)

        return claim.id

    async def get_claim(self, claim_id: str) -> Optional[CanonicalClaim]:
        """Get a canonical claim by ID."""
        if claim_id in self._claims:
            return self._claims[claim_id]

        if self.pg_pool:
            claim = await self._load_claim(claim_id)
            if claim:
                self._claims[claim_id] = claim
                return claim

        return None

    async def get_claims_for_topic(self, topic_id: str, min_authority: float = 0.0) -> List[CanonicalClaim]:
        """Get all canonical claims for a topic, filtered by minimum authority."""
        claims = [
            c for c in self._claims.values()
            if c.topic_id == topic_id and c.authority_score >= min_authority
        ]

        if self.pg_pool and not claims:
            claims = await self._load_claims_for_topic(topic_id, min_authority)
            for c in claims:
                self._claims[c.id] = c

        claims.sort(key=lambda c: c.authority_score, reverse=True)
        return claims

    async def _find_similar(self, topic_id: str, claim_text: str) -> Optional[CanonicalClaim]:
        """
        Find a similar existing claim in the same topic.

        Uses simple text overlap for now; could be upgraded to embedding similarity.
        """
        for c in self._claims.values():
            if c.topic_id != topic_id:
                continue

            # Simple Jaccard overlap
            words_a = set(claim_text.lower().split())
            words_b = set(c.claim.lower().split())

            if not words_a or not words_b:
                continue

            overlap = len(words_a & words_b) / len(words_a | words_b)
            if overlap > 0.6:  # 60% word overlap = same claim
                return c

        return None

    async def _persist_claim(self, claim: CanonicalClaim):
        """Persist claim to Postgres."""
        if not self.pg_pool:
            return

        try:
            async with self.pg_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO canonical_knowledge
                        (id, topic_id, claim, confidence, supporting_atom_ids,
                         contradicting_atom_ids, supporting_count, contradicting_count,
                         authority_score, stability_score, contradiction_pressure,
                         revision_count, version, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        claim = EXCLUDED.claim,
                        confidence = EXCLUDED.confidence,
                        supporting_atom_ids = EXCLUDED.supporting_atom_ids,
                        contradicting_atom_ids = EXCLUDED.contradicting_atom_ids,
                        supporting_count = EXCLUDED.supporting_count,
                        contradicting_count = EXCLUDED.contradicting_count,
                        authority_score = EXCLUDED.authority_score,
                        stability_score = EXCLUDED.stability_score,
                        revision_count = EXCLUDED.revision_count,
                        version = EXCLUDED.version,
                        updated_at = NOW()
                    """,
                    claim.id,
                    claim.topic_id,
                    claim.claim,
                    claim.confidence,
                    claim.supporting_atom_ids,
                    claim.contradicting_atom_ids,
                    claim.supporting_count,
                    claim.contradicting_count,
                    claim.authority_score,
                    claim.stability_score,
                    claim.contradiction_pressure,
                    claim.revision_count,
                    claim.version,
                )
        except Exception as e:
            logger.warning(f"[CKS] Failed to persist claim {claim.id}: {e}")

    async def _load_claim(self, claim_id: str) -> Optional[CanonicalClaim]:
        """Load a single claim from Postgres."""
        if not self.pg_pool:
            return None

        try:
            async with self.pg_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM canonical_knowledge WHERE id = $1", claim_id
                )
                if not row:
                    return None

                return CanonicalClaim(
                    id=str(row["id"]),
                    topic_id=str(row["topic_id"]),
                    claim=row["claim"],
                    confidence=float(row["confidence"]),
                    supporting_atom_ids=row.get("supporting_atom_ids") or [],
                    contradicting_atom_ids=row.get("contradicting_atom_ids") or [],
                    supporting_count=row.get("supporting_count", 0),
                    contradicting_count=row.get("contradicting_count", 0),
                    authority_score=float(row.get("authority_score", 0)),
                    stability_score=float(row.get("stability_score", 0)),
                    contradiction_pressure=float(row.get("contradiction_pressure", 0)),
                    revision_count=row.get("revision_count", 0),
                    version=row.get("version", 1),
                )
        except Exception as e:
            logger.debug(f"[CKS] Failed to load claim {claim_id}: {e}")
            return None

    async def _load_claims_for_topic(self, topic_id: str, min_authority: float) -> List[CanonicalClaim]:
        """Load claims for a topic from Postgres."""
        if not self.pg_pool:
            return []

        try:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM canonical_knowledge WHERE topic_id = $1 AND authority_score >= $2 ORDER BY authority_score DESC",
                    topic_id, min_authority,
                )
                return [
                    CanonicalClaim(
                        id=str(r["id"]),
                        topic_id=str(r["topic_id"]),
                        claim=r["claim"],
                        confidence=float(r["confidence"]),
                        supporting_atom_ids=r.get("supporting_atom_ids") or [],
                        contradicting_atom_ids=r.get("contradicting_atom_ids") or [],
                        supporting_count=r.get("supporting_count", 0),
                        contradicting_count=r.get("contradicting_count", 0),
                        authority_score=float(r.get("authority_score", 0)),
                        stability_score=float(r.get("stability_score", 0)),
                        contradiction_pressure=float(r.get("contradiction_pressure", 0)),
                        revision_count=r.get("revision_count", 0),
                        version=r.get("version", 1),
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.debug(f"[CKS] Failed to load claims for {topic_id}: {e}")
            return []
