import re
from dataclasses import dataclass, field
from typing import Literal, Optional, List, Any


@dataclass
class IntentProfile:
    """
    User query intent classification result.
    Additive fields support the cognitive working memory layer.
    """
    # Original CMK v1 fields
    type: Literal["factual", "conceptual", "procedural", "comparative", "exploratory"]
    depth: Literal["surface", "medium", "deep"]
    stability: Literal["static", "evolving", "controversial"]
    risk_of_hallucination: float  # 0.0-1.0
    entities: Optional[List[str]] = None

    # Working Memory Layer Additions (Phase 1)
    primary_intent: str = "exploratory"
    confidence: float = 0.8
    candidate_frames: List[str] = field(default_factory=list)
    ambiguity_score: float = 0.0
    escalation_bias: str = "none"


class IntentProfiler:
    """
    Lightweight rule-based intent classifier.
    No ML model needed — uses keyword patterns + heuristics.
    """

    # ── Type classification patterns ──

    _FACTUAL_PATTERNS = [
        r'\bwhat\s+is\b', r'\bdefine\b', r'\bwho\s+is\b', r'\bwho\s+was\b',
        r'\bwhere\s+is\b', r'\bwhen\s+(did|was|does)\b', r'\bwhat\s+does?\b',
        r'\bwhat\s+are\b', r'\blist\b', r'\bname\b.*\b(?:of|the)\b',
    ]

    _COMPARATIVE_PATTERNS = [
        r'\b(compare|comparison|versus|vs\.?|difference\s+between)\b',
        r'\b(?:how\s+does?\b.*\b(?:compare|differ|different))\b',
        r'\b(?:better|worse|superior|inferior)\b.*\b(?:than|or)\b',
        r'\b(?:pros?\s+and\s+cons|advantages?\s+(?:and|or|vs\.?)\s+disadvantages?)\b',
    ]

    _PROCEDURAL_PATTERNS = [
        r'\bhow\s+to\b', r'\bhow\s+do(?:es|s)?\b.*\b(work|build|create|make|install|setup)\b',
        r'\bsteps?\s+(?:to|for)\b', r'\bguide\b', r'\btutorial\b',
        r'\b(?:process|method|algorithm)\b.*\b(?:for|to)\b',
    ]

    _CONCEPTUAL_PATTERNS = [
        r'\bwhy\b', r'\bexplain\b', r'\bunderstand\b', r'\bconcept\b',
        r'\b(?:mechanism|principle|theory|model)\b',
        r'\b(?:how\s+does|why\s+does|why\s+do)\b',
        r'\bwhat\s+(?:causes|drives|motivates|influences)\b',
    ]

    # Depth estimation patterns
    _DEEP_PATTERNS = [
        r'\b(in\s+depth|deeply|thoroughly|detailed|comprehensive|explain)\b',
        r'\b(?:history|evolution|timeline|background)\b',
        r'\b(?:analyze|analysis|critique|evaluate|review)\b',
        r'\b(?:all|everything|complete)\b.*\b(?:about|of|on)\b',
    ]

    _SURFACE_PATTERNS = [
        r'\b(?:brief|short|quick|summary|overview|overview|tl;?dr)\b',
        r'\b(?:one|a)\s+(?:sentence|paragraph|line)\b',
    ]

    # Stability patterns
    _CONTROVERSIAL_TOPICS = [
        r'\b(?:climate\s+change|vaccine|nuclear|ai\s+safety|consciousness)\b',
        r'\b(?:debate|controversial|disputed|unresolved|conflicting)\b',
        r'\b(?:ethics|moral|ethical|philosophical)\b',
    ]

    _EVOLVING_TOPICS = [
        r'\b(?:latest|recent|new|current|today|202[4-9])\b',
        r'\b(?:update|change|evolving|emerging|trending)\b',
        r'\b(?:AI|LLM|GPT|transformer|diffusion|quantum)\b',
    ]

    def profile(self, query: str, prior_state: Any = None) -> IntentProfile:
        """
        Classify a user query into an intent profile.

        Args:
            query: The user's query string
            prior_state: Optional WorkingState for context-aware profiling

        Returns:
            IntentProfile with type, depth, stability, and hallucination risk
        """
        query_lower = query.lower().strip()

        query_type = self._classify_type(query_lower)
        depth = self._estimate_depth(query_lower)
        stability = self._detect_stability(query_lower)
        risk = self._hallucination_risk(query_type, depth, stability)
        entities = self._extract_entities(query_lower, query_type)

        # ── Working Memory Additions (Phase 1) ──
        
        # Primary intent mapping
        primary_intent = query_type
        
        # Candidate frames based on type and keywords
        candidate_frames = []
        if query_type == "comparative":
            candidate_frames = ["comparison", "tradeoff_evaluation"]
        elif query_type == "procedural":
            candidate_frames = ["how_to", "implementation_plan"]
        elif query_type == "conceptual":
            candidate_frames = ["explanation", "mechanism_mapping"]
        elif query_type == "factual":
            candidate_frames = ["lookup"]
        
        # Escalation bias heuristics
        escalation_bias = "none"
        if query_type in ("comparative", "conceptual") and depth == "deep":
            escalation_bias = "medium"
        
        # Ambiguity score
        ambiguity_score = 0.5
        if len(query_lower.split()) < 4:
            ambiguity_score = 0.8  # Short queries are often ambiguous
        elif entities and len(entities) >= 2:
            ambiguity_score = 0.2  # Specific entities reduce ambiguity

        return IntentProfile(
            type=query_type,
            depth=depth,
            stability=stability,
            risk_of_hallucination=risk,
            entities=entities,
            primary_intent=primary_intent,
            confidence=0.8,
            candidate_frames=candidate_frames,
            ambiguity_score=ambiguity_score,
            escalation_bias=escalation_bias,
        )

    def _classify_type(self, query: str) -> str:
        """Classify query into intent type."""
        # Check comparative first (most specific)
        for pattern in self._COMPARATIVE_PATTERNS:
            if re.search(pattern, query):
                return "comparative"

        # Check procedural
        for pattern in self._PROCEDURAL_PATTERNS:
            if re.search(pattern, query):
                return "procedural"

        # Check conceptual (why/explain)
        for pattern in self._CONCEPTUAL_PATTERNS:
            if re.search(pattern, query):
                return "conceptual"

        # Check factual
        for pattern in self._FACTUAL_PATTERNS:
            if re.search(pattern, query):
                return "factual"

        # Default: exploratory
        return "exploratory"

    def _estimate_depth(self, query: str) -> str:
        """Estimate required answer depth."""
        # Check for explicit depth requests
        for pattern in self._DEEP_PATTERNS:
            if re.search(pattern, query):
                return "deep"

        for pattern in self._SURFACE_PATTERNS:
            if re.search(pattern, query):
                return "surface"

        # Infer from type
        type_ = self._classify_type(query)
        if type_ in ("conceptual", "comparative"):
            return "deep"
        elif type_ == "procedural":
            return "medium"
        elif type_ == "factual":
            return "surface"

        return "medium"

    def _detect_stability(self, query: str) -> str:
        """Detect whether the topic is static, evolving, or controversial."""
        for pattern in self._CONTROVERSIAL_TOPICS:
            if re.search(pattern, query):
                return "controversial"

        for pattern in self._EVOLVING_TOPICS:
            if re.search(pattern, query):
                return "evolving"

        return "static"

    def _hallucination_risk(self, query_type: str, depth: str, stability: str) -> float:
        """
        Estimate hallucination risk score (0.0-1.0).

        Higher risk = more need for strict evidence gating.
        """
        risk = 0.3  # base risk

        # Type contribution
        type_risk = {
            "factual": 0.1,
            "conceptual": 0.3,
            "procedural": 0.2,
            "comparative": 0.4,
            "exploratory": 0.5,
        }
        risk += type_risk.get(query_type, 0.3)

        # Depth contribution
        depth_risk = {"surface": 0.0, "medium": 0.1, "deep": 0.2}
        risk += depth_risk.get(depth, 0.1)

        # Stability contribution
        stability_risk = {"static": 0.0, "evolving": 0.15, "controversial": 0.3}
        risk += stability_risk.get(stability, 0.1)

        return min(1.0, max(0.0, risk))

    def _extract_entities(self, query: str, query_type: str) -> list[str]:
        """
        Extract key entities from query (for comparative/procedural queries).

        Returns list of entity strings that should be matched in retrieval.
        """
        if query_type not in ("comparative", "procedural"):
            return None

        # Simple noun-phrase extraction via stopword filtering
        stopwords = {
            'what', 'is', 'are', 'the', 'a', 'an', 'how', 'to', 'do', 'does',
            'did', 'can', 'could', 'would', 'should', 'will', 'shall',
            'in', 'on', 'at', 'by', 'for', 'with', 'from', 'of', 'and',
            'or', 'but', 'not', 'no', 'than', 'then', 'that', 'this',
            'these', 'those', 'it', 'its', 'be', 'been', 'being',
            'have', 'has', 'had', 'about', 'between', 'into', 'through',
            'during', 'before', 'after', 'above', 'below', 'up', 'down',
            'out', 'off', 'over', 'under', 'again', 'further', 'here',
            'there', 'when', 'where', 'why', 'which', 'who', 'whom',
            'compare', 'comparison', 'versus', 'vs', 'difference',
            'explain', 'define', 'tell', 'me', 'us', 'show',
        }

        # Split on common separators
        tokens = re.split(r'[\s,;]+', query)
        entities = [
            t.strip() for t in tokens
            if len(t.strip()) > 2 and t.strip().lower() not in stopwords
        ]

        return entities if entities else None
