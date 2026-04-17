import re
import logging
from dataclasses import dataclass
from typing import List, Literal
from .working_state import WorkingState, EscalationLevel

logger = logging.getLogger(__name__)

@dataclass
class EscalationDecision:
    route: Literal["chat", "analysis"]
    level: EscalationLevel
    reasons: List[str]

class EscalationPolicy:
    """
    Decides between conversational chat and deliberate analysis.
    Prevents architectural rigidity by staying light until pressure rises.
    """
    
    # Explicit asks for deeper adjudication or recommendation.
    ANALYSIS_KEYWORDS = [
        r"\bdiagnos(?:e|is|ing)\b",
        r"\btroubleshoot(?:ing)?\b",
        r"\broot\s+cause\b",
        r"\banaly(?:ze|sis)\b",
        r"\bevaluate\b",
        r"\brecommend(?:ation)?\b",
        r"\bwhat\s+should\b",
        r"\bshould\s+we\b",
        r"\btradeoffs?\b",
    ]

    # Signals that a turn is more complex than ordinary chat, but still
    # should remain on the chat path unless state pressure accumulates.
    CHAT_COMPLEXITY_KEYWORDS = [
        r"\bcompare\b",
        r"\bhow\s+to\b",
        r"\bhow\s+do\b",
        r"\bexplain\b",
        r"\bwhy\s+is\s+it\b",
        r"\bdecision\b",
        r"\bchoice\b",
    ]
    
    def decide(self, state: WorkingState, user_text: str) -> EscalationDecision:
        """
        Evaluate current state and input to decide routing.
        """
        analysis_reasons = []
        chat_reasons = []
        user_text_lower = user_text.lower()

        # 1. Direct intent profiling hints
        if state.intent_profile:
            if state.intent_profile.escalation_bias == "high":
                analysis_reasons.append(
                    f"Intent profiling indicates high reasoning bias ({state.intent_profile.primary_intent})"
                )
            elif state.intent_profile.escalation_bias == "medium":
                chat_reasons.append(
                    f"Intent profiling indicates elevated reasoning bias ({state.intent_profile.primary_intent})"
                )

        # 2. Keyword detection in current turn
        for pattern in self.ANALYSIS_KEYWORDS:
            if re.search(pattern, user_text_lower):
                analysis_reasons.append(f"Explicit analysis cue detected: '{pattern}'")
                break

        for pattern in self.CHAT_COMPLEXITY_KEYWORDS:
            if re.search(pattern, user_text_lower):
                chat_reasons.append(f"Complexity cue detected: '{pattern}'")
                break

        # 3. Accumulating state pressure
        if state.confidence_pressure >= 0.85:
            analysis_reasons.append(
                f"Confidence pressure is high ({state.confidence_pressure:.2f})"
            )
        elif state.confidence_pressure >= 0.55:
            chat_reasons.append(
                f"Confidence pressure is elevated ({state.confidence_pressure:.2f})"
            )

        if len(state.active_contradictions) >= 2:
            analysis_reasons.append(
                f"Multiple active contradictions detected ({len(state.active_contradictions)})"
            )

        if state.insufficiency_pressure >= 0.8:
            analysis_reasons.append("Insufficiency pressure is high")
        elif state.insufficiency_pressure >= 0.5:
            chat_reasons.append("Insufficiency pressure is elevated")

        # ── Decision Logic ──

        reasons = analysis_reasons + [r for r in chat_reasons if r not in analysis_reasons]

        if analysis_reasons:
            level: EscalationLevel = "full_analysis"
            route = "analysis"
        elif chat_reasons:
            level: EscalationLevel = "medium"
            route = "chat"
        else:
            level: EscalationLevel = "none"
            route = "chat"
            
        return EscalationDecision(
            route=route,
            level=level,
            reasons=reasons
        )
