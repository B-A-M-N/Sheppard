"""
cmk/activation.py — Two-layer memory architecture.

Layer A — Long-term semantic memory (knowledge_confidence, never decays)
Layer B — Working/activation memory (activation_score, decays via exp curve)

This is NOT TTL deletion. Knowledge persists; access priority fades.
Human cognition mapping:
  Hippocampus (temporary activation) → Redis activation layer
  Cortex (long-term knowledge) → Postgres KG
  Synaptic strengthening → reinforcement scoring
  Forgetting access priority → activation decay
  Rare memory retention → low-activation persistence
"""

import math
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# Decay configuration
# After 48 hours, activation drops to ~50% of original
# After 7 days, ~25%
# After 30 days, ~5%
# Knowledge itself is NEVER deleted — only retrieval priority fades
ACTIVATION_DECAY_RATE = 0.01  # Per hour
ACTIVATION_REINFORCE_AMOUNT = 1.0
MIN_ACTIVATION = 0.0
MAX_ACTIVATION = 10.0  # No upper bound — frequently-used knowledge stays "top of mind"


class ActivationMemory:
    """
    Manages activation scores for atoms and concepts.

    In production, uses Redis as primary store with Postgres mirror.
    For now, uses in-memory dict (upgraded when Redis client is injected).
    """

    def __init__(self, redis_client=None, pg_pool=None):
        self.redis = redis_client
        self.pg_pool = pg_pool

        # In-memory fallback
        self._memory: Dict[str, Dict[str, Any]] = {}

    # ── Core operations ──

    async def activate(self, atom_id: str, amount: float = ACTIVATION_REINFORCE_AMOUNT) -> float:
        """
        Reinforce an atom's activation score (called on retrieval/use).

        Returns new activation score.
        """
        current = await self.get_activation(atom_id)
        new_score = min(MAX_ACTIVATION, current + amount)
        await self.set_activation(atom_id, new_score)

        # Also update Postgres tracking
        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO cmk.activation_tracking (atom_id, activation_score, last_accessed) "
                        "VALUES ($1, $2, NOW()) "
                        "ON CONFLICT (atom_id) DO UPDATE SET "
                        "activation_score = EXCLUDED.activation_score, "
                        "last_accessed = NOW()",
                        atom_id, new_score,
                    )
                    await conn.execute(
                        "UPDATE knowledge.knowledge_atoms SET "
                        "usage_count = COALESCE(usage_count, 0) + 1, "
                        "last_accessed = NOW() "
                        "WHERE atom_id = $1",
                        atom_id,
                    )
            except Exception as e:
                logger.debug(f"[ActivationMemory] Postgres update failed for {atom_id}: {e}")

        return new_score

    async def get_activation(self, atom_id: str) -> float:
        """Get current activation score for an atom."""
        # Try Redis first
        if self.redis:
            try:
                val = await self.redis.get(f"cmk:act:{atom_id}")
                if val is not None:
                    return float(val)
            except Exception:
                pass

        # Check Postgres mirror
        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT activation_score FROM cmk.activation_tracking WHERE atom_id = $1",
                        atom_id,
                    )
                    if row:
                        return float(row["activation_score"])
            except Exception:
                pass

        # In-memory fallback
        return self._memory.get(atom_id, {}).get("activation", 0.0)

    async def set_activation(self, atom_id: str, score: float):
        """Set activation score."""
        # Write to Redis with TTL (attention window, not knowledge deletion)
        if self.redis:
            try:
                # 7-day attention window — after that, activation naturally decays to near-zero
                await self.redis.set(f"cmk:act:{atom_id}", str(score), ex=7 * 24 * 3600)
            except Exception:
                pass

        # Update in-memory
        if atom_id not in self._memory:
            self._memory[atom_id] = {"activation": 0.0, "last_accessed": time.time()}
        self._memory[atom_id]["activation"] = score
        self._memory[atom_id]["last_accessed"] = time.time()

    # ── Decay ──

    def apply_decay(self, activation: float, hours_since_access: float) -> float:
        """
        Apply exponential decay to an activation score.

        Does NOT modify storage — caller must write back if needed.
        """
        if hours_since_access <= 0:
            return activation

        decayed = activation * math.exp(-ACTIVATION_DECAY_RATE * hours_since_access)
        return max(MIN_ACTIVATION, decayed)

    async def decay_all(self, max_age_hours: float = 168) -> int:
        """
        Apply decay to all tracked atoms.

        Returns number of atoms decayed.
        """
        now = time.time()
        decayed = 0

        for atom_id, data in list(self._memory.items()):
            last = data.get("last_accessed", now)
            hours = (now - last) / 3600.0

            if hours > max_age_hours:
                # Very old — clear from working memory (knowledge persists in Postgres)
                del self._memory[atom_id]
                if self.redis:
                    try:
                        await self.redis.delete(f"cmk:act:{atom_id}")
                    except Exception:
                        pass
                decayed += 1
            elif hours > 1:
                old_score = data["activation"]
                new_score = self.apply_decay(old_score, hours)
                data["activation"] = new_score
                data["last_accessed"] = now
                if abs(old_score - new_score) > 0.01:
                    decayed += 1

        logger.debug(f"[ActivationMemory] Decayed {decayed} atoms")
        return decayed

    # ── Retrieval fusion scoring ──

    def compute_retrieval_score(
        self,
        vector_similarity: float,
        authority_score: float = 0.5,
        activation_score: float = 0.0,
        context_alignment: float = 0.5,
    ) -> float:
        """
        Final retrieval ranking formula:
          final_score = vector_sim * 0.4 + authority * 0.35 + recency_bias * 0.15 + context * 0.10

        Where recency_bias = activation_score / MAX_ACTIVATION (normalized)
        """
        recency_bias = min(1.0, activation_score / max(1.0, MAX_ACTIVATION))

        score = (
            0.40 * vector_similarity +
            0.35 * authority_score +
            0.15 * recency_bias +
            0.10 * context_alignment
        )

        return max(0.0, min(1.0, score))

    # ── Stats ──

    def get_stats(self) -> Dict[str, Any]:
        return {
            "tracked_atoms": len(self._memory),
            "high_activation": sum(
                1 for d in self._memory.values() if d.get("activation", 0) > 2.0
            ),
            "low_activation": sum(
                1 for d in self._memory.values() if d.get("activation", 0) < 0.5
            ),
        }
