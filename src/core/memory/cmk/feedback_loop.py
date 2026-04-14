"""
cmk/feedback_loop.py — Post-response atom weight updates.

After every answer, evaluates which atoms were used and adjusts their
reliability scores based on response quality signals.

This turns the system from static → adaptive:
  - Atoms that correlate with good answers get boosted
  - Atoms that correlate with hallucinations/errors get downgraded
  - Over time, the knowledge substrate self-organizes toward truth
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from .types import CMKAtom

logger = logging.getLogger(__name__)


# Feedback adjustment rates
UPGRADE_RATE = 0.02    # Good response → small boost
DOWNGRADE_RATE = 0.05  # Bad response → larger penalty (loss aversion)
DECAY_RATE = 0.001     # Slow natural decay for unused atoms


class FeedbackLoop:
    """
    Manages post-response feedback to atom weights.

    Usage:
      1. Track which atoms were used in a response
      2. After response is evaluated, call update()
      3. Atom reliability scores are adjusted in-place
    """

    def __init__(
        self,
        upgrade_rate: float = UPGRADE_RATE,
        downgrade_rate: float = DOWNGRADE_RATE,
        decay_rate: float = DECAY_RATE,
    ):
        self.upgrade_rate = upgrade_rate
        self.downgrade_rate = downgrade_rate
        self.decay_rate = decay_rate

        # Track usage history
        self.usage_log: List[Dict[str, Any]] = []

    def record_usage(
        self,
        atoms_used: List[CMKAtom],
        response_quality: float,  # 0.0-1.0: how good the response was
        response_id: str = "",
    ) -> Dict[str, float]:
        """
        Record atom usage and compute weight updates.

        Does NOT modify atoms directly — returns updates for caller to apply.
        This keeps the feedback loop decoupled from storage.

        Args:
            atoms_used: Atoms that were included in the response context
            response_quality: Quality score of the generated response
            response_id: Optional ID for tracking

        Returns:
            Dict mapping atom_id → delta (positive = upgrade, negative = downgrade)
        """
        updates: Dict[str, float] = {}

        for atom in atoms_used:
            if response_quality >= 0.7:
                # Good response → slight boost
                delta = self.upgrade_rate * response_quality
            elif response_quality >= 0.4:
                # Mediocre response → no change
                delta = 0.0
            else:
                # Bad response → downgrade
                delta = -self.downgrade_rate * (1.0 - response_quality)

            if delta != 0.0:
                updates[atom.id] = delta

        # Log this usage event
        self.usage_log.append({
            "response_id": response_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "quality": response_quality,
            "atom_count": len(atoms_used),
            "updates": updates,
        })

        # Keep log bounded
        if len(self.usage_log) > 1000:
            self.usage_log = self.usage_log[-500:]

        return updates

    def apply_updates(
        self,
        atom_store: Dict[str, CMKAtom],
        updates: Dict[str, float],
    ) -> int:
        """
        Apply weight updates to the atom store.

        Args:
            atom_store: Dict mapping atom_id → CMKAtom
            updates: Dict mapping atom_id → delta

        Returns:
            Number of atoms updated
        """
        count = 0
        for atom_id, delta in updates.items():
            atom = atom_store.get(atom_id)
            if atom is None:
                logger.debug(f"[FeedbackLoop] Atom {atom_id} not found in store")
                continue

            old_reliability = atom.reliability
            atom.reliability = _clamp(atom.reliability + delta)

            if abs(atom.reliability - old_reliability) > 1e-6:
                count += 1
                logger.debug(
                    f"[FeedbackLoop] {atom_id}: "
                    f"{old_reliability:.4f} → {atom.reliability:.4f} ({delta:+.4f})"
                )

        return count

    def apply_decay(
        self,
        atom_store: Dict[str, CMKAtom],
        last_used: Optional[Dict[str, datetime]] = None,
    ) -> int:
        """
        Apply natural decay to unused atoms.

        Atoms that haven't been used recently slowly lose reliability.
        This prevents stale knowledge from dominating.

        Args:
            atom_store: Dict mapping atom_id → CMKAtom
            last_used: Optional dict mapping atom_id → last used timestamp

        Returns:
            Number of atoms decayed
        """
        now = datetime.now(timezone.utc)
        count = 0

        for atom_id, atom in atom_store.items():
            # Check if atom has been used recently
            if last_used and atom_id in last_used:
                days_since = (now - last_used[atom_id]).days
                if days_since < 30:
                    continue  # Recently used, no decay

            # Apply decay
            old_reliability = atom.reliability
            atom.reliability = _clamp(atom.reliability - self.decay_rate)

            if abs(atom.reliability - old_reliability) > 1e-6:
                count += 1

        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get feedback loop statistics."""
        if not self.usage_log:
            return {"total_feedback_events": 0}

        total_upgrades = sum(
            sum(1 for d in event["updates"].values() if d > 0)
            for event in self.usage_log
        )
        total_downgrades = sum(
            sum(1 for d in event["updates"].values() if d < 0)
            for event in self.usage_log
        )
        avg_quality = (
            sum(event["quality"] for event in self.usage_log) / len(self.usage_log)
            if self.usage_log else 0.0
        )

        return {
            "total_feedback_events": len(self.usage_log),
            "total_upgrades": total_upgrades,
            "total_downgrades": total_downgrades,
            "average_response_quality": round(avg_quality, 3),
        }


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
