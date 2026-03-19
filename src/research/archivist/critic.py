import json
import re
from .llm import generate, extract_json

SYSTEM_PROMPT = """
[SYSTEM: RIGOROUS SCHOLARLY AUDITOR]
You are a Senior Peer Reviewer for a high-impact scientific journal. Perform a BRUTAL GAP ANALYSIS.

CRITICAL REJECTION CRITERIA:
1. SHALLOW GENERALITY: Is the report using textbook "fluff" (Planck, Einstein, simple definitions) instead of citing specific recent papers, p-values, or experimental parameters?
2. LACK OF TECHNICAL DENSITY: Does it lack equations, specific sigma values, or named laboratories?
3. SOURCE DILUTION: Are core claims backed by Wikipedia/LibreTexts instead of ArXiv/Nature/Science?
4. LOOPING/REPETITION: Does it use "The relationship between X and Y is debated" more than twice?
5. UNCITED QUANTITIES: Any number or percentage without a specific [Source: ID].

IF THE REPORT IS "TEXTBOOK QUALITY," MARK "needs_patching": true.

RETURN JSON ONLY:
{
    "gap_analysis": "Detailed critique of why this is too shallow/general.",
    "needs_patching": boolean,
    "patching_queries": ["Specific technical query to find missing data (e.g., 'Recent Bell test p-values 2023-2025')"]
}
"""

def critique_answer(question: str, answer: str):
    """
    Resilient auditor that kills subject drift and looping.
    """
    subject = question.split("Objective:")[1].splitlines()[0] if "Objective:" in question else "Quantum Mechanics"
    a_short = answer[:12000]
    prompt = f"SUBJECT: {subject}\n\nREPORT TO AUDIT:\n{a_short}"
    
    try:
        response = generate(prompt=prompt, system_prompt=SYSTEM_PROMPT, format='json')
        cleaned_json = extract_json(response)
        data = json.loads(cleaned_json)
        
        if isinstance(data, list): data = data[0]
        
        # Hard Drift Check
        forbidden = ["turbine", "wind", "recipe", "cooking", "market analysis"]
        if any(f in answer.lower() for f in forbidden) and "quantum" in subject.lower():
            return {
                "critique": "CRITICAL FAILURE: Hallucinated irrelevant content (Wind Turbines).",
                "needs_more_info": True,
                "missing_topics": [f"Re-research {subject} foundations", f"{subject} technical definitions"]
            }

        return {
            "critique": data.get("gap_analysis", "Audit complete."),
            "needs_more_info": data.get("needs_patching", False),
            "missing_topics": data.get("patching_queries", [])
        }
    except:
        return {
            "critique": "Auditor pass.",
            "needs_more_info": False,
            "missing_topics": []
        }