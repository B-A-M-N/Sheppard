from . import planner, search, crawler, chunker, embeddings, index, retriever, synth, critic, llm
import time
import concurrent.futures
import threading
from collections import deque
import json
import re
import asyncio
import logging

logger = logging.getLogger(__name__)

class ResearchState:
    def __init__(self, objective):
        self.objective = objective
        self.plan = [] # List of dicts: {'title': str, 'goal': str}
        self.sections = {} # Map title -> content
        self.source_registry = {} # URL -> ID
        self.source_usage = {}    # ID -> Count (Global)
        self.source_summaries = {} # ID -> Dense Summary
        self.next_source_id = 1

def fill_data_gaps(state, section_title, section_goal, browser_manager=None):
    """
    Hunter-Seeker Routine: Aggressively finds missing data by broadening the search.
    """
    logger.info(f"[\U0001f52d] Hunter-Seeker Triggered for: {section_title}")
    
    # Strategy: Broaden search to find reviews, experimental data, and major labs
    queries = [
        f"{section_title} experimental data {state.objective}",
        f"{section_title} performance metrics",
        f"{section_title} review article 2024 2025",
        f"{section_title} failure modes",
        f"{section_title} contradictions"
    ]
    
    new_urls = set()
    for q in queries:
        try:
            logger.info(f"[H-S SEARCH] {q}")
            # Search broadly
            urls = search.search_web(q, max_results=10)
            for u in urls:
                u_l = u.lower()
                is_authoritative = any(x in u_l for x in [
                    '.edu', '.gov', 'arxiv.org', 'nature.com', 'science.org', 
                    'nytimes.com', 'reuters.com', 'apnews.com', 'bbc.com', 'theguardian.com',
                    'documentcloud.org', 'courtlistener.com', 'archives.gov', 'justice.gov',
                    'propublica.org', 'intercept.com'
                ])
                if is_authoritative and u not in state.source_registry:
                    new_urls.add(u)
                elif any(kw in state.objective.lower() for kw in ['epstein', 'files', 'investigation']) and u not in state.source_registry:
                    new_urls.add(u)
        except: pass
        
    # Ingest
    for url in list(new_urls)[:6]:
        try:
            if url not in state.source_registry:
                sid = f"S{state.next_source_id}"
                state.source_registry[url] = sid
                state.next_source_id += 1
            sid = state.source_registry[url]
            
            html = crawler.fetch_url(url, browser_manager=browser_manager)
            if html:
                text = html # crawler.fetch_url already returns extracted text now
                if len(text) > 300:
                    state.source_summaries[sid] = synth.summarize_source(text, url)
                    chunks = chunker.chunk_text(text)
                    embs = embeddings.get_embeddings_batch(chunks)
                    metadatas = [{"source": url, "text": c, "global_id": sid} for c in chunks]
                    index.add_chunks(chunks, embs, metadatas)
                    logger.info(f"[PASS] Ingested: [{sid}] {url}")
        except Exception as e: logger.error(f"[FAIL] {url}: {e}")
            
    return True

def execute_section_cycle(state, section_index, is_patching=False, patch_instruction=None, browser_manager=None):
    if section_index >= len(state.plan):
        return None
        
    section = state.plan[section_index]
    title = section['title']
    goal = patch_instruction if is_patching else section['goal']
    
    logger.info(f"[*] Processing Section {section_index+1}/{len(state.plan)}: {title}")
    
    # 1. Targeted Search
    queries = planner.generate_section_queries(title, goal, state.objective)
    new_urls = set()
    for q in queries[:3]:
        try:
            logger.info(f"[SEARCH] Searching: {q}")
            urls = search.search_web(q, max_results=12)
            for u in urls:
                u_l = u.lower()
                
                # High-Authority Whitelist (Academic + Investigative + Legal)
                is_authoritative = any(x in u_l for x in [
                    '.edu', '.gov', 'arxiv.org', 'nature.com', 'science.org', # Academic
                    'nytimes.com', 'reuters.com', 'apnews.com', 'bbc.com', 'theguardian.com', 'wsj.com', # Journalism
                    'documentcloud.org', 'courtlistener.com', 'archives.gov', 'justice.gov', 'fbi.gov', # Legal/Gov
                    'propublica.org', 'intercept.com', 'newyorker.com', 'theatlantic.com' # Investigative
                ])
                
                # Strict Junk Filter (Avoid noise/social/spam)
                is_junk = any(x in u_l for x in ['whatsapp', 'cocaine', 'recovery', 'wiki', 'game', 'store', 'apps', 'keyword', 'github', 'moon', 'spirit', 'soul', 'consciousness', 'healing', 'podcast', 'blog', 'medium.com', 'tripadvisor', 'youtube', 'tiktok', 'linkedin', 'facebook', 'instagram', 'twitter', 'x.com', 'pinterest'])
                
                # If it's a high-profile investigation, we want authoritative sources or gov documents
                if is_authoritative and not is_junk:
                    if u not in state.source_registry: new_urls.add(u)
                elif any(kw in state.objective.lower() for kw in ['epstein', 'files', 'investigation', 'unredacted']) and not is_junk:
                    # Slightly broader for investigative topics if authoritative list is too narrow
                    if u not in state.source_registry: new_urls.add(u)
        except: pass
            
    # 2. Ingest
    for url in list(new_urls)[:6]:
        try:
            if url not in state.source_registry:
                sid = f"S{state.next_source_id}"
                state.source_registry[url] = sid
                state.next_source_id += 1
            sid = state.source_registry[url]
            
            html = crawler.fetch_url(url, browser_manager=browser_manager)
            if html:
                text = html # crawler.fetch_url already returns text now
                if len(text) > 300:
                    state.source_summaries[sid] = synth.summarize_source(text, url)
                    chunks = chunker.chunk_text(text)
                    embs = embeddings.get_embeddings_batch(chunks)
                    metadatas = [{"source": url, "text": c, "global_id": sid} for c in chunks]
                    index.add_chunks(chunks, embs, metadatas)
                    logger.info(f"[PASS] Ingested: [{sid}] {url}")
        except: pass

    # 3. Retrieve Context
    q_emb = embeddings.get_embedding(f"{state.objective}: {title} {goal}")
    raw_docs = retriever.search(q_emb, top_k=50)
    
    diverse_docs = []
    for d in raw_docs:
        src_url = d['metadata']['source']
        sid = state.source_registry.get(src_url)
        if sid:
            d['global_id'] = sid
            usage = state.source_usage.get(sid, 0)
            if usage < 5: 
                diverse_docs.append(d)
                state.source_usage[sid] = usage + 1
            
    # 4. Write Section
    previous_context = ""
    for i in range(section_index):
        prev_title = state.plan[i]['title']
        if prev_title in state.sections:
            previous_context += f"\n{state.sections[prev_title]}\n"

    section_content = synth.write_section(
        title, 
        goal, 
        diverse_docs[:20], 
        previous_context,
        summaries=state.source_summaries
    )
    
    # 5. Hunter-Seeker Gap Filling
    if "Specific empirical data for this sub-topic was not found" in section_content:
        logger.info("[!] Data Gap Detected. Initiating Hunter-Seeker Protocol...")
        fill_data_gaps(state, title, goal, browser_manager=browser_manager)
        
        # Re-Retrieve with new data
        q_emb = embeddings.get_embedding(f"{state.objective} {title} experimental data")
        raw_docs = retriever.search(q_emb, top_k=60)
        diverse_docs = [] 
        for d in raw_docs:
            src_url = d['metadata']['source']
            sid = state.source_registry.get(src_url)
            if sid:
                d['global_id'] = sid
                diverse_docs.append(d)
        
        logger.info("[*] Re-writing section with Hunter-Seeker data...")
        section_content = synth.write_section(
            title, 
            goal, 
            diverse_docs[:25], 
            previous_context,
            summaries=state.source_summaries
        )

    state.sections[title] = section_content
    return True

def finalize_report(state, subj):
    """
    Consolidates all sections and patches into a seamless narrative.
    """
    logger.info("[*] Performing Final Editorial Polish...")
    
    raw_draft = ""
    for section in state.plan:
        if section['title'] in state.sections:
            raw_draft += f"\n\n## {section['title']}\n{state.sections[section['title']]}"
            
    # Use LLM to smooth transitions if needed, but for now we trust the modular write.
    # We primarily strip the internal "SUPPLEMENTAL AUDIT" headers to make it seamless.
    final_body = raw_draft.replace("### SUPPLEMENTAL AUDIT:", "### Further Analysis:")
    
    # Generate Bibliography
    biblio = "\n\n## DATA ORIGINS\n"
    sorted_sources = sorted(state.source_registry.items(), key=lambda x: int(x[1][1:]))
    for url, sid in sorted_sources:
        biblio += f"- [{sid}] {url}\n"
        
    return f"# RESEARCH REPORT: {subj}\n\n{final_body}{biblio}"

def run_research(objective: str, memory_manager=None, ollama_client=None, browser_manager=None, topic=None):
    match = re.search(r"Objective:\s*(.*?)(?:\n|$)", objective, re.IGNORECASE)
    subj = match.group(1).strip() if match else objective.splitlines()[0][:100].strip()
    subj = re.sub(r"[.,;]$", "", subj)
    
    # Use provided topic for metadata consistency, otherwise fallback to subject
    meta_topic = topic if topic else subj
    
    state = ResearchState(subj)
    # Clear local archivist index but preserve Sheppard's main memory
    index.clear_index()
    
    logger.info(f"[*] Researching: '{subj}'")
    
    # Use Sheppard's LLM if provided, otherwise fallback to local archivist llm
    if ollama_client:
        llm.set_sheppard_client(ollama_client)

    state.plan = planner.plan_outline(subj)
    
    # 1. Execute Main Plan
    for i in range(len(state.plan)):
        execute_section_cycle(state, i, browser_manager=browser_manager)
        # Store intermediate progress in Sheppard's memory if available
        if memory_manager and subj in state.sections:
            asyncio.run(memory_manager.store({
                "content": state.sections[state.plan[i]['title']],
                "metadata": {
                    "type": "research_draft_section",
                    "topic": meta_topic, # Correctly tag with topic
                    "section": state.plan[i]['title']
                }
            }))
    
    # 2. Active Adversarial Audit (Patching Cycle)
    logger.info("[*] Initiating Active Adversarial Audit...")
    report_draft = finalize_report(state, subj)
    audit = critic.critique_answer(subj, report_draft) # Use draft report for audit

    if audit.get('needs_more_info'):
        logger.info(f"[!] Audit critique: {audit.get('critique')[:200]}...")
        missing = audit.get('missing_topics', [])
        for m in missing:
            # Find best section to patch
            best_section_idx = -1
            best_overlap = 0
            for i, section in enumerate(state.plan):
                # Simple keyword overlap check
                m_words = set(re.findall(r'\w+', m.lower()))
                t_words = set(re.findall(r'\w+', section['title'].lower()))
                overlap = len(m_words.intersection(t_words))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_section_idx = i

            if best_section_idx == -1:
                # Fallback to general or last section
                for i, s in enumerate(state.plan):
                    if any(kw in s['title'].lower() for kw in ['unknowns', 'assessment', 'leads']):
                        best_section_idx = i
                        break

            if best_section_idx != -1:
                logger.info(f"[*] Patching Section {best_section_idx+1} ({state.plan[best_section_idx]['title']}) based on Audit...")
                execute_section_cycle(state, best_section_idx, is_patching=True, patch_instruction=m, browser_manager=browser_manager)

    # 3. Final Polish & Assembly
    logger.info("[*] Performing Final Editorial Polish...")
    final_answer = finalize_report(state, subj)
    return {"answer": final_answer, "sources": list(state.source_registry.keys()), "steps": len(state.plan)}