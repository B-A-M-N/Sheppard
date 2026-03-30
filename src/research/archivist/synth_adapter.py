"""
archivist/synth_adapter.py

The V2 Wrapper for the Archivist Synthesis Engine.
Applies the strict 'Scholarly Archivist' persona to the modern EvidencePackets.
"""

import logging
from typing import List, Dict
from src.llm.client import OllamaClient
from src.llm.model_router import TaskType
from src.research.reasoning.assembler import EvidencePacket

logger = logging.getLogger(__name__)

SCHOLARLY_ARCHIVIST_PROMPT = """
[SYSTEM: SENIOR RESEARCH ANALYST]
You are a Senior Research Analyst. Write ONE section of a larger comprehensive report.

STRICT INTEGRITY RULES:
1. CONTEXT PINNING: You may ONLY cite facts, numbers, historical events, and data points that appear explicitly in the provided EVIDENCE BRIEF.
2. NO HALLUCINATION: Do NOT use your internal training data for specific metrics, dates, or detailed facts unless they are present in the snippets.
3. SOURCE BINDING: Every claim must be traceably bound to its Global Source ID (e.g., [S4] or [A1]).
4. CONTRADICTIONS: If the evidence contains contradictory claims, you must explicitly state the disagreement. Do not smooth it over.
5. PER-SENTENCE CITATION: Each factual sentence must contain at least one citation. Do not place a single citation at the end of a multi-fact paragraph; cite each fact individually.
6. NO INFERENCE: Do not combine, infer, or extrapolate across sources to create new conclusions. If the evidence does not directly support a claim, do not write it.

STYLE GUIDELINES:
- PROSE EXCLUSIVITY: Dense, sophisticated paragraphs. NO bulleted lists unless explicitly requested.
- TONE: Professional, objective, and appropriate for the subject matter (technical, historical, scientific, etc.).
"""

class ArchivistSynthAdapter:
    def __init__(self, ollama: OllamaClient):
        self.ollama = ollama

    def _format_evidence_brief(self, packet: EvidencePacket) -> str:
        brief = ""
        for atom in packet.atoms:
            brief += f"{atom.get('global_id', '[A]')} TYPE: {atom.get('type')}\nCONTENT: {atom.get('text')}\n\n"
            
        if packet.contradictions:
            brief += "\n### IDENTIFIED CONTRADICTIONS IN EVIDENCE:\n"
            for c in packet.contradictions:
                brief += f"- CONFLICT: {c.get('description')}\n  CLAIM A: {c.get('claim_a')}\n  CLAIM B: {c.get('claim_b')}\n\n"
                
        return brief

    async def write_section(self, packet: EvidencePacket, previous_context: str) -> str:
        """Execute the Archivist synthesis constraint on a specific evidence packet."""
        evidence_brief = self._format_evidence_brief(packet)
        
        prompt = f"""
### SECTION TITLE: {packet.section_title}
### SECTION GOAL: {packet.section_objective}

### EVIDENCE BRIEF (ONLY USE DATA FROM THESE SNIPPETS):
{evidence_brief}

### PREVIOUS CONTEXT (FOR FLOW):
{previous_context[-2000:] if previous_context else "This is the introduction to the report."}

### TASK:
Write this section of the report.
- Integrate the provided evidence using stable Global IDs (e.g. [A1], [S2]).
- Maintain a logical flow with the previous sections.
- IF THE PROVIDED EVIDENCE IS INSUFFICIENT to meet the goal, state: "Specific empirical data for this sub-topic was not found in the primary search phase."
- DO NOT invent "Adversarial Scenarios" or theoretical examples using fake data. Only report real disputes or facts found in the text.
"""
        logger.info(f"[Archivist] Writing section: '{packet.section_title}' using {len(packet.atoms)} atoms.")
        
        resp = await self.ollama.complete(
            task=TaskType.SYNTHESIS,
            prompt=prompt,
            system_prompt=SCHOLARLY_ARCHIVIST_PROMPT,
            max_tokens=3000
        )
        return resp
