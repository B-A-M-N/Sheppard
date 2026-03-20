
import asyncio
from src.core.system import system_manager
from src.research.reasoning.retriever import RetrievalQuery

async def diag():
    await system_manager.initialize()
    query_text = "AI orchestration"
    
    print(f"[*] Testing search for: '{query_text}'")
    
    # 1. Lexical Search
    lex_results = await system_manager.memory.lexical_search_atoms([query_text])
    print(f"[*] Lexical search found {len(lex_results)} atoms.")
    for r in lex_results[:3]:
        print(f"  - [{r['atom_type']}] {r['content'][:100]}... (score: {r['score']:.2f})")
        
    # 2. Semantic Search
    try:
        sem_results = await system_manager.memory.chroma_query("knowledge_atoms", query_text)
        print(f"[*] Semantic search (knowledge_atoms) results: {len(sem_results.get('documents', [[]])[0]) if sem_results else 0}")
    except Exception as e:
        print(f"[!] Semantic search failed: {e}")

    # 3. Hybrid Retrieval
    q = RetrievalQuery(text=query_text)
    ctx = await system_manager.retriever.retrieve(q)
    print(f"[*] Hybrid retrieval context empty: {ctx.is_empty}")
    
    formatted = system_manager.retriever.build_context_block(ctx)
    print(f"[*] Formatted context length: {len(formatted)}")
    print("--- CONTEXT ---")
    print(formatted)
    print("---------------")

if __name__ == "__main__":
    asyncio.run(diag())
