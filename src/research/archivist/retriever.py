import json
import concurrent.futures
from .llm import generate, extract_json
from fastembed import TextEmbedding
from src.memory.storage_adapter import ChromaSemanticStore

# Initialize Reranker (Lazy Load)
_RERANKER_INSTANCE = None

# Chroma store injection
_chroma_store: ChromaSemanticStore | None = None


def init(chroma_store: ChromaSemanticStore) -> None:
    """Initialize with the shared ChromaSemanticStore."""
    global _chroma_store
    _chroma_store = chroma_store


def _get_store() -> ChromaSemanticStore:
    if _chroma_store is None:
        raise RuntimeError("Archivist retriever not initialized. Call init() first.")
    return _chroma_store


def get_reranker():
    global _RERANKER_INSTANCE
    if _RERANKER_INSTANCE is None:
        try:
            from fastembed import TextRerank
            _RERANKER_INSTANCE = TextRerank(model_name="jinaai/jina-reranker-v1-turbo-en")
        except:
            # Fallback if specific model/class fails
            try:
                from fastembed import TextRerank
                _RERANKER_INSTANCE = TextRerank(model_name="BAAI/bge-reranker-base")
            except:
                return None
    return _RERANKER_INSTANCE


async def search(query_embedding: list[float], top_k: int = 5, collection_name="archivist_research") -> list[dict]:
    store = _get_store()
    results = await store.query(collection=collection_name, query_embeddings=query_embedding, limit=top_k)
    hits = []
    if results.get('documents') and results['documents'][0]:
        for i in range(len(results['documents'][0])):
            hits.append({
                "text": results['documents'][0][i],
                "metadata": results['metadatas'][0][i]
            })
    return hits

def determine_source_tier(source_url: str) -> str:
    """
    Classifies sources into epistemic tiers.
    """
    source = source_url.lower()
    
    # Tier 1: Primary Literature & Datasets (High Authority)
    if any(x in source for x in ['.gov', '.edu', 'arxiv.org', 'nature.com', 'science.org', 'aps.org', 'nih.gov', 'cern.ch', 'iop.org']):
        return "TIER_1_PRIMARY"
        
    # Tier 2: Reputable Journalism & Reviews (Medium Authority)
    if any(x in source for x in ['nytimes.com', 'bbc.com', 'economist.com', 'reuters.com', 'bloomberg.com', 'ieee.org', 'acm.org']):
        return "TIER_2_SECONDARY"
        
    # Tier 3: General Web (Low Authority - Context Only)
    return "TIER_3_TERTIARY"

def extract_evidence_object(doc, question):
    """
    Surgically extracts an Evidentiary Object from raw text with strict source typing.
    """
    source_url = doc['metadata'].get('source', 'Unknown')
    tier = determine_source_tier(source_url)
    
    prompt = f"""
[EVIDENCE EXTRACTION PROTOCOL]
SUBJECT: {question[:150]}
SOURCE TIER: {tier} ({source_url})
TEXT: {doc['text'][:1000]}

TASK: Extract verifiable data points.
RULES:
1. If TIER 3: Mark all claims as [UNVERIFIED] unless corroborated.
2. EXTRACT ONLY explicit statements. Do not infer.
3. NUMBERS: precise values only.

RETURN JSON:
{{
    "source_id": "{source_url}",
    "tier": "{tier}",
    "claim": "The specific assertion found in text",
    "data": "Exact numbers/metrics or 'None'",
    "context": "Necessary nuance or conditions",
    "quote": "Direct snippet (max 15 words) for verification"
}}
"""
    try:
        response = generate(prompt=prompt, system_prompt="[SYSTEM: DATA ENTRY CLERK] Precision is paramount. No hallucinations.", format='json', options={"num_ctx": 4000, "temperature": 0.0})
        data = json.loads(extract_json(response))
        if not data.get("claim"): return None
        
        # Enforce metadata passthrough
        data['source_id'] = source_url
        data['tier'] = tier
        return data
    except:
        return None

def rerank_docs(question: str, docs: list[dict], limit: int = 15):
    """
    1. Fast Semantic Rerank (Cross-Encoder) to filter noise.
    2. Expensive LLM Extraction on the survivors.
    """
    if not docs: return []
    
    # 1. Fast Reranking
    reranker = get_reranker()
    if reranker:
        try:
            texts = [d['text'] for d in docs]
            # FastEmbed's rerank returns a list of results with score and document index
            ranked_results = list(reranker.rerank(query=question, documents=texts))
            # Sort by score desc
            ranked_results.sort(key=lambda x: x.score, reverse=True)
            
            # Keep top 10 for extraction
            top_indices = [r.index for r in ranked_results[:10]]
            docs = [docs[i] for i in top_indices]
        except Exception as e:
            # print(f"Rerank failed: {e}")
            pass
            
    # 2. LLM Extraction (Source Tiering)
    evidence_pool = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(extract_evidence_object, d, question) for d in docs]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res: evidence_pool.append(res)
            
    # Sort by Tier (Primary first)
    evidence_pool.sort(key=lambda x: x['tier'])
        
    return evidence_pool[:limit]
