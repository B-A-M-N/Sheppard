import re
from .llm import generate

# The "Scholarly Archivist" Persona - Hardened for Integrity
SCHOLARLY_ARCHIVIST_PROMPT = """
[SYSTEM: SENIOR TECHNICAL RESEARCHER]
You are a Senior Research Analyst. Write ONE section of a larger technical report.

STRICT INTEGRITY RULES:
1. CONTEXT PINNING: You may ONLY cite facts, numbers, and data points that appear explicitly in the provided EVIDENCE BRIEF. 
2. NO HALLUCINATION: Do NOT use your internal training data for specific metrics (e.g., sigma values, p-values, dates) unless they are present in the snippets. If the brief says "p < 0.05", you may not write "p < 0.001".
3. SOURCE BINDING: Every claim must be traceably bound to its Global Source ID (e.g., [S4]).
4. QUOTE INTEGRITY: When citing a critical data point, include a 3-5 word verbatim snippet in parentheses to prove provenance.

STYLE GUIDELINES:
- PROSE EXCLUSIVITY: Dense, sophisticated paragraphs. NO lists.
- TECHNICAL DENSITY: Use precise scientific terminology.
"""

def summarize_source(text: str, source_url: str) -> str:
    """
    Level 1 Map-Reduce: Compress a raw source into a dense 'Key Findings' card.
    """
    prompt = f"""
SOURCE: {source_url}
TEXT: {text[:6000]}

TASK: Extract unique empirical claims, specific numbers (p-values, sigma, metrics), and technical definitions.
Output a dense, high-information paragraph. Ignore generic fluff or introductory filler.
"""
    try:
        return generate(prompt=prompt, system_prompt="[SYSTEM: DATA COMPRESSOR]", options={"temperature": 0.1, "num_ctx": 8000})
    except:
        return "Summary unavailable."

def format_docs(docs):
    """
    Formats documents using their Global IDs for stable referencing.
    """
    brief = ""
    for d in docs:
        # Use the injected Global ID from loop.py
        sid = d.get('global_id', 'Unknown')
        src = d['metadata'].get('source', 'Unknown')
        # Providing more text to ensure 'Context Pinning' has enough to work with
        brief += f"[{sid}] SOURCE: {src}\nCONTENT: {d['text']}\n\n"
    return brief

def write_section(title, goal, docs, previous_context, summaries=None):
    evidence_brief = format_docs(docs)
    
    # Inject summaries if provided for higher-level context
    summary_blob = ""
    if summaries:
        summary_blob = "### SOURCE SUMMARIES (High-Level Context):\n"
        for sid, text in summaries.items():
            if any(d.get('global_id') == sid for d in docs):
                summary_blob += f"[{sid} Summary]: {text}\n"
    
    task = f"""
### SECTION TITLE: {title}
### SECTION GOAL: {goal}

{summary_blob}

### EVIDENCE BRIEF (ONLY USE DATA FROM THESE SNIPPETS):
{evidence_brief}

### PREVIOUS CONTEXT (FOR FLOW):
{previous_context[-1500:]}

### TASK:
Write this section of the report.
- Integrate the provided evidence using stable Global IDs (e.g. [S1], [S2]).
- Maintain technical flow with the previous sections.
- IF THE PROVIDED EVIDENCE IS INSUFFICIENT to meet the goal, state: "Specific empirical data for this sub-topic was not found in the primary search phase."
- DO NOT invent "Adversarial Scenarios" using fake numbers. Only report real technical disputes found in the text.

MINIMUM 600 WORDS.
"""
    return generate(prompt=task, system_prompt=SCHOLARLY_ARCHIVIST_PROMPT, options={"temperature": 0.4, "num_ctx": 16000})

def synthesize_answer(question, docs):
    # This is a legacy wrapper for direct calls if any exist
    return "Synthesis moved to modular write_section."
