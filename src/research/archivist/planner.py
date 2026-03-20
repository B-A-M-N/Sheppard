import json
import re
from .llm import generate, extract_json

OUTLINE_PROMPT = """
[SYSTEM: RESEARCH ARCHITECT]
You are creating a research plan for: {subject}

STEP 1: Determine the Topic Category.
- INVESTIGATIVE: High-profile cases, legal files, events, people, scandals, redacted documents.
- ACADEMIC: Science, physics, AI theory, engineering, biology, mathematics.

STEP 2: Generate Outlines based on Category.

IF INVESTIGATIVE:
Focus on: Disclosed materials, Key Individuals (Negative Attribution), Content vs Media Narratives, Redacted Information, Official Records, and Timeline. 
DO NOT use academic words like "Disciplinary Usage", "Benchmarks", or "Sigma". Use forensic and legal terminology.

IF ACADEMIC:
Focus on: Precise Definitions, Historical Trace, Empirical Evidence, Technical Critiques, and Expert Disagreement.

Return JSON ONLY:
{{
    "category": "INVESTIGATIVE" | "ACADEMIC",
    "outline": [
        {{"title": "Section Title", "goal": "Specific objective for this section..."}},
        ...
    ]
}}
"""

QUERY_PROMPT_ACADEMIC = """
[SYSTEM: SEARCH ENGINEER]
Generate 3 highly specific search queries to find evidence for:
SUBJECT: {subject}
SECTION: {title}
GOAL: {goal}

CONSTRAINT: Every query MUST include the SUBJECT terms.
PRIORITIZE: "Empirical Data", "Benchmarks", "Performance Metrics", "Recent Anomalies".
Focus on finding primary sources (PDFs, ArXiv, datasets).
Return JSON: {{"queries": ["{subject} query1", "{subject} query2", "{subject} query3"]}}
"""

QUERY_PROMPT_INVESTIGATIVE = """
[SYSTEM: SEARCH ENGINEER]
Generate 3 highly specific search queries to find evidence for:
SUBJECT: {subject}
SECTION: {title}
GOAL: {goal}

CONSTRAINT: Every query MUST include the SUBJECT terms.
PRIORITIZE: "Court Documents", "Unredacted Files", "Official Records", "Investigative Reports", "Primary Source Documents".
FORBIDDEN: "Consciousness", "Spirituality", "Fringe", "Speculation".
Return JSON: {{"queries": ["{subject} query1", "{subject} query2", "{subject} query3"]}}
"""

def plan_outline(subject: str):
    """
    Creates a tailored research outline based on the subject type.
    """
    is_investigative_topic = any(kw in subject.lower() for kw in ['epstein', 'files', 'investigation', 'case', 'unredacted', 'court', 'legal', 'names'])
    
    try:
        response = generate(prompt=OUTLINE_PROMPT.format(subject=subject), format='json')
        data = json.loads(extract_json(response))
        
        # Check if the LLM followed instructions or if we should override based on keywords
        category = data.get('category', '').upper()
        if is_investigative_topic and category == 'ACADEMIC':
            # Force investigative fallback if LLM chose wrong category for known investigative topic
            pass 
        elif data.get('outline') and len(data['outline']) >= 5:
            return data['outline']
    except:
        pass

    # Fallback to hardcoded outlines
    if is_investigative_topic:
        return [
            {"title": "I. Scope of Disclosed Materials", "goal": "Identify exactly what documents and files have been released and their origins."},
            {"title": "II. Key Individuals & Negative Attribution", "goal": "List specific names mentioned in a negative or incriminating context."},
            {"title": "III. Verified Content vs Media Narrative", "goal": "Distinguish between confirmed file contents and speculative reporting."},
            {"title": "IV. Technical & Infrastructure Details", "goal": "Analyze any technical details about communication networks or data storage mentioned."},
            {"title": "V. Redacted & Missing Information", "goal": "Identify specific gaps where information remains withheld or suppressed."},
            {"title": "VI. Official Institutional Involvement", "goal": "Map any involvement or oversight by government or international agencies."},
            {"title": "VII. Verified Timeline of Events", "goal": "Reconstruct the timeline based exclusively on file artifacts."},
            {"title": "VIII. Real-World Legal Implications", "goal": "Evaluate current legal actions or investigations directly linked to these files."},
            {"title": "IX. Testable Leads for Further Inquiry", "goal": "Identify specific areas where further forensic data could resolve unknowns."},
            {"title": "X. Final Intelligence Assessment", "goal": "Classify findings into: Hard Evidence, High-Probability, and Unverified Allegations."}
        ]
    else:
        return [
            {"title": "I. Precise Definition & Usage", "goal": "Define the topic, identify competing definitions, and map usage across disciplines."},
            {"title": "II. Historical Trace", "goal": "Trace emergence, original problem solving, and drift in meaning over time."},
            {"title": "III. Strongest Empirical Evidence", "goal": "Identify direct vs indirect evidence, sample sizes, and methodologies."},
            {"title": "IV. Evidence Against & Critiques", "goal": "Map failed replications, negative results, and funding/incentive distortions."},
            {"title": "V. Expert Disagreement", "goal": "Map who disagrees with whom, differing assumptions, and methodological conflicts."},
            {"title": "VI. Unknowns & Open Problems", "goal": "List currently unanswerable questions and data needed to resolve them."},
            {"title": "VII. Misconceptions & Cargo-Cults", "goal": "Identify oversimplifications and industry/popular myths."},
            {"title": "VIII. Real-World Applications & Failures", "goal": "Evaluate where it works, where it fails silently, and edge cases."},
            {"title": "IX. Proposed Hypotheses", "goal": "Propose 3 testable experiments to advance understanding."},
            {"title": "X. Sober Assessment", "goal": "Classify claims into: Confidently True, Probable but Unproven, Likely False."}
        ]

def generate_section_queries(title: str, goal: str, subject: str = "Research Topic"):
    """
    Generates search queries anchored to the main subject with type-awareness.
    """
    is_investigative = any(kw in subject.lower() or kw in title.lower() for kw in ['epstein', 'files', 'investigation', 'case', 'unredacted', 'court', 'legal', 'names'])
    
    try:
        prompt_tmpl = QUERY_PROMPT_INVESTIGATIVE if is_investigative else QUERY_PROMPT_ACADEMIC
        prompt = prompt_tmpl.format(title=title, goal=goal, subject=subject)
        response = generate(prompt=prompt, format='json')
        data = json.loads(extract_json(response))
        queries = data.get('queries', [])
        
        anchored_queries = []
        for q in queries:
            if subject.lower() not in q.lower():
                anchored_queries.append(f"{subject} {q}")
            else:
                anchored_queries.append(q)
                
        return anchored_queries if anchored_queries else [f"{subject} {title}", f"{subject} evidence"]
    except:
        return [f"{subject} {title} records", f"{subject} {title} primary source"]

# Legacy support
def plan_research(question: str):
    return {"keywords": [question]}
