"""
cmk/prompt_contract.py — Constrained LLM prompt generation.

Builds system prompts that enforce:
  - Evidence-tier usage rules (HIGH = truth, MEDIUM = explanation, LOW = ignore)
  - Anti-paraphrase constraints (no rephrasing the same idea)
  - Abstraction gating (no generalization from single source)
  - Multi-source definition requirements
  - Citation requirements (every claim must reference an atom ID)
  - Novelty enforcement (each sentence must introduce a distinct fact)

This is where most RAG systems fail — the prompt must CONTROL the LLM's
relationship to the evidence, not just say "use this context".
"""

from typing import Optional, List, Dict, Any

from .evidence_pack import EvidencePack
from .intent_profiler import IntentProfile
from .grounding import (
    AbstractionGate,
    EvidenceItem,
    build_evidence_locked_context,
    analyze_novelty,
)


# Base system prompt — applies to all queries
BASE_SYSTEM_PROMPT = """\
You are Sheppard, a knowledge-grounded reasoning system operating in CMK Evidence Mode.

You will receive a user query and structured evidence from your knowledge base.
The evidence is organized into confidence tiers. You MUST follow these rules:\
"""

# HARDENED evidence rules — anti-paraphrase, anti-hallucination
EVIDENCE_RULES = """\
EVIDENCE USAGE RULES:
1. HIGH CONFIDENCE FACTS are ground truth. Use them as the foundation of your answer.
2. SUPPORTING CONTEXT provides explanation. Use it to elaborate on HIGH CONFIDENCE facts.
3. LOW CONFIDENCE data may be unreliable. Do NOT use it as fact. Only reference it when
   explicitly discussing uncertainty or disputed topics.
4. CONFLICTING EVIDENCE indicates disputed knowledge. If relevant, acknowledge the conflict
   rather than picking a side without basis.

ANTI-PARAPHRASE RULES:
5. Do NOT define concepts unless explicitly supported by at least 2 independent atoms.
6. Do NOT paraphrase the same idea in multiple ways. Each sentence must introduce a DISTINCT fact.
7. Do NOT merge concepts unless overlap is explicit in the evidence.
8. If evidence is weak or insufficient, say: "insufficient grounded data to confirm."
9. Do NOT generalize. Do NOT abstract. Do NOT complete the pattern.
10. If the evidence does not contain information relevant to the query, say so directly.\
"""

# Abstraction gate instructions (injected when generalization is blocked)
ABSTENTION_PROMPT = """\
ABSTRACTION BLOCKED: The available evidence comes from a single source or semantic cluster.
You may report the specific facts available, but you MUST NOT generalize, define, or abstract
beyond what is explicitly stated. Do not synthesize a broader concept from limited data.\
"""

# Multi-source definition requirement
DEFINITION_REQUIREMENT = """\
DEFINITION RULE: You may only provide a definition if at least 2 distinct evidence atoms
independently support it. If only 1 atom covers the concept, report that specific fact
without generalizing it into a definition.\
"""

# Depth-controlled response length guidelines
DEPTH_GUIDELINES = {
    "surface": "Keep your response brief — 1-2 short paragraphs. Direct answer first. Cite atom IDs.",
    "medium": "Provide a thorough answer — 2-4 paragraphs. Include key details and context. Cite atom IDs.",
    "deep": "Give a comprehensive response — multiple paragraphs. Include mechanisms, edge cases, "
            "and supporting detail. Structure with clear sections. Cite atom IDs.",
}


def build_cmk_prompt(
    evidence_pack: EvidencePack,
    user_query: str,
    intent: Optional[IntentProfile] = None,
    conversation_history: Optional[List[dict]] = None,
    abstraction_gate: Optional[AbstractionGate] = None,
    definition_supported: Optional[bool] = None,
) -> List[dict]:
    """
    Build a complete message list for LLM generation with constrained evidence.

    Args:
        evidence_pack: Tiered evidence from CMK
        user_query: The user's query string
        intent: Optional intent profile for depth control
        conversation_history: Optional prior messages
        abstraction_gate: Optional abstraction gate result
        definition_supported: Whether multi-source definition is supported

    Returns:
        List of messages (system + context + history + user) ready for LLM
    """
    messages = []

    # 1. System prompt with hardened rules
    system_content = BASE_SYSTEM_PROMPT + "\n\n" + EVIDENCE_RULES

    # Add abstraction gate warning
    if abstraction_gate and not abstraction_gate.can_generalize:
        system_content += "\n\n" + ABSTENTION_PROMPT

    # Add definition requirement
    if definition_supported is False:
        system_content += "\n\n" + DEFINITION_REQUIREMENT

    # Add depth guideline
    if intent:
        depth_text = DEPTH_GUIDELINES.get(intent.depth, DEPTH_GUIDELINES["medium"])
        system_content += f"\n\nRESPONSE DEPTH: {depth_text}"

        # Add stability guidance
        if intent.stability == "controversial":
            system_content += (
                "\n\nTOPIC NOTE: This topic is controversial or disputed. "
                "Present multiple viewpoints where appropriate. Avoid definitive "
                "statements on unsettled matters."
            )
        elif intent.stability == "evolving":
            system_content += (
                "\n\nTOPIC NOTE: This topic is rapidly evolving. "
                "Note that information may have changed since it was recorded."
            )

        # Add hallucination risk guidance
        if intent.risk_of_hallucination > 0.7:
            system_content += (
                "\n\nRISK NOTE: This query has high hallucination risk. "
                "Be especially careful to only use provided evidence. "
                "If uncertain, state your uncertainty clearly."
            )

    messages.append({"role": "system", "content": system_content})

    # 2. Evidence context (now with atom IDs for citation)
    if not evidence_pack.is_empty:
        context_content = _format_evidence_context(evidence_pack)
        messages.append({"role": "system", "content": context_content})
    else:
        messages.append({
            "role": "system",
            "content": "No relevant knowledge was found in the knowledge base. "
                       "Answer based on your general knowledge, but clearly distinguish "
                       "what is from your knowledge base vs general knowledge. "
                       "If uncertain, state: 'insufficient grounded data to confirm.'",
        })

    # 3. Conversation history
    if conversation_history:
        messages.extend(conversation_history[-5:])  # Last 5 exchanges

    # 4. User query
    messages.append({"role": "user", "content": user_query})

    return messages


def _format_evidence_context(pack: EvidencePack) -> str:
    """
    Format evidence pack into LLM-readable context.

    Uses clear tier labels so the LLM knows the confidence level of each fact.
    """
    sections = []

    sections.append("=== KNOWLEDGE BASE EVIDENCE ===\n")

    if pack.high_confidence:
        sections.append("--- HIGH CONFIDENCE (ground truth) ---")
        for i, atom in enumerate(pack.high_confidence, 1):
            source = f" (source: {atom.source_id})" if atom.source_id else ""
            sections.append(f"[H{i}] {atom.content}{source}")
        sections.append("")

    if pack.supporting_context:
        sections.append("--- SUPPORTING CONTEXT (explanation only) ---")
        for i, atom in enumerate(pack.supporting_context, 1):
            source = f" (source: {atom.source_id})" if atom.source_id else ""
            sections.append(f"[S{i}] {atom.content}{source}")
        sections.append("")

    if pack.contradictions:
        sections.append("--- CONFLICTING EVIDENCE (acknowledge if relevant) ---")
        for i, contradiction in enumerate(pack.contradictions, 1):
            desc = contradiction.get("description", "Unknown conflict")
            sections.append(f"[C{i}] {desc}")
        sections.append("")

    if not pack.high_confidence and not pack.supporting_context and pack.low_confidence:
        # Only show low confidence if nothing better is available
        sections.append("--- LOW CONFIDENCE (unreliable — use with caution) ---")
        for i, atom in enumerate(pack.low_confidence[:10], 1):
            sections.append(f"[L{i}] {atom.content}")
        sections.append("")

    return "\n".join(sections)


def build_summary_prompt(
    evidence_pack: EvidencePack,
    user_query: str,
) -> str:
    """
    Build a short summary prompt for the short-context model.

    Used for context summarization before main generation.
    """
    if evidence_pack.is_empty:
        return "No relevant knowledge found."

    parts = []

    if evidence_pack.high_confidence:
        parts.append("Key facts:")
        for atom in evidence_pack.high_confidence[:5]:
            parts.append(f"- {atom.content}")

    if evidence_pack.contradictions:
        parts.append("Conflicts:")
        for c in evidence_pack.contradictions[:3]:
            parts.append(f"- {c.get('description', '?')[:100]}")

    return "\n".join(parts)
