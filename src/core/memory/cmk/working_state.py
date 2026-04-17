from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, List, Dict, Any

# Import IntentProfile from its original source of truth
from .intent_profiler import IntentProfile


EscalationLevel = Literal["none", "light", "medium", "full_analysis"]
ContradictionStatus = Literal["live", "damped", "escalated", "resolved"]


@dataclass
class ActiveConcept:
    concept_id: str
    label: str
    salience: float
    source: str  # query, carryover, contradiction, retrieval, analyst, critic


@dataclass
class ActiveContradiction:
    contradiction_id: str
    atom_ids: List[str]
    severity: float
    status: ContradictionStatus
    summary: str


@dataclass
class SoftHypothesis:
    hypothesis_id: str
    text: str
    confidence: float
    support_atom_ids: List[str] = field(default_factory=list)
    challenge_atom_ids: List[str] = field(default_factory=list)


@dataclass
class WorkingState:
    session_id: str
    mission_id: Optional[str] = None
    topic_id: Optional[str] = None
    turn_index: int = 0

    intent_profile: Optional[IntentProfile] = None

    active_atom_ids: List[str] = field(default_factory=list)
    active_derived_claim_ids: List[str] = field(default_factory=list)
    active_concepts: List[ActiveConcept] = field(default_factory=list)
    active_contradictions: List[ActiveContradiction] = field(default_factory=list)
    soft_hypotheses: List[SoftHypothesis] = field(default_factory=list)

    candidate_frames: List[str] = field(default_factory=list)
    unresolved_questions: List[str] = field(default_factory=list)
    recent_topics: List[str] = field(default_factory=list)

    confidence_pressure: float = 0.0
    insufficiency_pressure: float = 0.0
    escalation_level: EscalationLevel = "none"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state for Redis storage."""
        import dataclasses
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkingState:
        """Deserialize state from Redis storage."""
        if not data:
            return cls(session_id="unknown")
        
        # Handle nested dataclasses
        if data.get("intent_profile"):
            data["intent_profile"] = IntentProfile(**data["intent_profile"])
        
        if data.get("active_concepts"):
            data["active_concepts"] = [ActiveConcept(**c) for c in data["active_concepts"]]
            
        if data.get("active_contradictions"):
            data["active_contradictions"] = [ActiveContradiction(**c) for c in data["active_contradictions"]]
            
        if data.get("soft_hypotheses"):
            data["soft_hypotheses"] = [SoftHypothesis(**h) for h in data["soft_hypotheses"]]
            
        return cls(**data)
