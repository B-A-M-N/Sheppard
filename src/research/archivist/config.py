import os
from pathlib import Path

# Models
LLM_MODEL = os.getenv('OLLAMA_MODEL', 'rnj-1:8b-cloud')
EMBEDDING_MODEL = os.getenv('OLLAMA_EMBED_MODEL', 'nomic-embed-text')

# Paths - Integration with Sheppard
BASE_DIR = Path(__file__).parent.parent.parent.parent.absolute()
STORAGE_DIR = os.path.join(BASE_DIR, "data", "archivist")
INDEX_DIR = os.path.join(STORAGE_DIR, "index")
RAW_DOCS_DIR = os.path.join(STORAGE_DIR, "raw_docs")

# Create directories if they don't exist
os.makedirs(INDEX_DIR, exist_ok=True)
os.makedirs(RAW_DOCS_DIR, exist_ok=True)

# Settings (Character-based)
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 300
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
