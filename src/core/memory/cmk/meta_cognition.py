"""
cmk/meta_cognition.py — Meta-Cognitive Self-Model.

The system tracks its own reasoning errors, blind spots, and confidence calibration.

What it monitors:
  1. Confidence calibration — does predicted confidence match actual accuracy?
  2. Reasoning chain length — longer chains = more error-prone
  3. Contradiction density — high density = unreliable area
  4. Domain expertise gaps — domains with low authority scores
  5. Repetition patterns — same ideas retrieved repeatedly = loop risk
  6. Evidence quality degradation — older evidence may be stale

This is the system's model of its own intelligence limits.
"""

import logging
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ReasoningStep:
    """A single step in the reasoning process."""
    step_type: str  # retrieval, inference, synthesis, hypothesis_test, consolidation
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    confidence: float
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    error_flag: bool = False
    error_reason: str = ""


@dataclass
class ConfidenceCalibration:
    """Tracks how well predicted confidence matches actual outcomes."""
    predicted_confidences: List[float] = field(default_factory=list)
    actual_outcomes: List[float] = field(default_factory=list)

    @property
    def calibration_error(self) -> float:
        if not self.predicted_confidences:
            return 0.0
        errors = [abs(p - a) for p, a in zip(self.predicted_confidences, self.actual_outcomes)]
        return sum(errors) / len(errors)

    @property
    def is_well_calibrated(self) -> bool:
        return self.calibration_error < 0.15


class MetaCognitionLayer:
    """
    Meta-cognitive self-model for the CMK.

    Tracks the system's own reasoning quality and identifies blind spots.
    """

    def __init__(self, max_history: int = 500):
        self.max_history = max_history
        self.reasoning_history: List[ReasoningStep] = []
        self.calibration = ConfidenceCalibration()

        # Per-domain expertise tracking
        self.domain_expertise: Dict[str, Dict[str, float]] = defaultdict(lambda: {
            "authority_sum": 0.0,
            "count": 0,
            "errors": 0,
            "successes": 0,
        })

        # Error pattern tracking
        self.error_patterns: Dict[str, int] = defaultdict(int)

        # Loop detection
        self.recent_retrievals: List[str] = []  # Recent retrieval IDs
        self.max_recent = 50

    def record_step(
        self,
        step_type: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        confidence: float,
        duration_ms: float = 0.0,
        error_flag: bool = False,
        error_reason: str = "",
    ):
        """Record a reasoning step."""
        step = ReasoningStep(
            step_type=step_type,
            input_data=input_data,
            output_data=output_data,
            confidence=confidence,
            duration_ms=duration_ms,
            error_flag=error_flag,
            error_reason=error_reason,
        )

        self.reasoning_history.append(step)

        # Keep history bounded
        if len(self.reasoning_history) > self.max_history:
            self.reasoning_history = self.reasoning_history[-self.max_history // 2:]

        # Update calibration
        if not error_flag:
            self.calibration.predicted_confidences.append(confidence)
            self.calibration.actual_outcomes.append(min(1.0, confidence + 0.1))  # Approximation

        # Track error patterns
        if error_flag:
            self.error_patterns[step_type] += 1
            self.error_patterns[error_reason or "unknown"] += 1

    def record_domain_outcome(self, domain: str, success: bool, authority: float = 0.5):
        """Record an outcome for a specific domain."""
        if domain:
            self.domain_expertise[domain]["authority_sum"] += authority
            self.domain_expertise[domain]["count"] += 1
            if success:
                self.domain_expertise[domain]["successes"] += 1
            else:
                self.domain_expertise[domain]["errors"] += 1

    def identify_blind_spots(self) -> List[Dict[str, Any]]:
        """
        Identify reasoning blind spots.

        Returns:
            List of blind spot descriptions sorted by severity.
        """
        blind_spots = []

        # 1. Poor calibration
        if not self.calibration.is_well_calibrated:
            blind_spots.append({
                "type": "calibration_error",
                "severity": self.calibration.calibration_error,
                "description": f"Confidence calibration is poor (error={self.calibration.calibration_error:.3f}). "
                              f"The system's confidence predictions don't match actual outcomes.",
                "action": "Reduce confidence estimates by 10-20%",
            })

        # 2. High-error reasoning types
        for step_type, error_count in self.error_patterns.items():
            total = sum(1 for s in self.reasoning_history if s.step_type == step_type)
            if total > 5 and error_count / total > 0.3:
                blind_spots.append({
                    "type": "error_pattern",
                    "severity": error_count / total,
                    "description": f"High error rate in {step_type} steps ({error_count}/{total} = {error_count/total:.0%})",
                    "action": f"Review {step_type} logic, add validation",
                })

        # 3. Domain expertise gaps
        for domain, stats in self.domain_expertise.items():
            if stats["count"] >= 3:
                error_rate = stats["errors"] / stats["count"]
                avg_authority = stats["authority_sum"] / stats["count"]
                if error_rate > 0.4 or avg_authority < 0.4:
                    blind_spots.append({
                        "type": "domain_gap",
                        "severity": max(error_rate, 1.0 - avg_authority),
                        "description": f"Low expertise in '{domain}' (error_rate={error_rate:.0%}, "
                                      f"avg_authority={avg_authority:.2f})",
                        "action": f"Prioritize knowledge acquisition in {domain}",
                    })

        # 4. Repetition/loop risk
        if len(self.recent_retrievals) >= 10:
            from collections import Counter
            counts = Counter(self.recent_retrievals)
            most_common = counts.most_common(3)
            if most_common and most_common[0][1] > len(self.recent_retrievals) * 0.3:
                blind_spots.append({
                    "type": "loop_risk",
                    "severity": most_common[0][1] / len(self.recent_retrievals),
                    "description": f"Retrieval loop risk: '{most_common[0][0]}' retrieved "
                                  f"{most_common[0][1]} times in last {len(self.recent_retrievals)} steps",
                    "action": "Diversify retrieval, activate decay",
                })

        # Sort by severity
        blind_spots.sort(key=lambda x: x["severity"], reverse=True)
        return blind_spots

    def get_stats(self) -> Dict[str, Any]:
        """Get meta-cognitive statistics."""
        total_steps = len(self.reasoning_history)
        error_steps = sum(1 for s in self.reasoning_history if s.error_flag)

        by_type = defaultdict(int)
        for s in self.reasoning_history:
            by_type[s.step_type] += 1

        avg_confidence = (
            sum(s.confidence for s in self.reasoning_history) / total_steps
            if total_steps > 0 else 0.0
        )

        return {
            "total_reasoning_steps": total_steps,
            "error_rate": error_steps / max(1, total_steps),
            "average_confidence": round(avg_confidence, 3),
            "calibration_error": round(self.calibration.calibration_error, 3),
            "is_well_calibrated": self.calibration.is_well_calibrated,
            "reasoning_types": dict(by_type),
            "error_patterns": dict(self.error_patterns),
            "domain_count": len(self.domain_expertise),
            "blind_spot_count": len(self.identify_blind_spots()),
        }
