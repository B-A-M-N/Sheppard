import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
import chromadb
from chromadb.config import Settings
import logging
import warnings

# warnings.filterwarnings("ignore", message=".*model_fields.*")
from .config import INDEX_DIR
import uuid

# Initialize persistent client
client = chromadb.PersistentClient(path=INDEX_DIR, settings=Settings(anonymized_telemetry=False))

def get_collection(name="archivist_research"):
    """
    Get or create the ChromaDB collection.
    """
    return client.get_or_create_collection(name=name)

import hashlib

def clear_index(collection_name="archivist_research"):
    """
    Deletes the collection to clear all previous data.
    """
    try:
        client.delete_collection(name=collection_name)
    except:
        pass

def add_chunks(chunks: list[str], embeddings: list[list[float]], metadatas: list[dict], collection_name="archivist_research"):
    """
    Add chunks with their embeddings and metadata to the index.
    Uses hash of text as ID to prevent duplicates.
    """
    collection = get_collection(collection_name)
    
    # Use deterministic IDs based on content hash to avoid duplicates
    ids = [hashlib.md5(c.encode()).hexdigest() for c in chunks]
    
    collection.upsert(
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids
    )
    # print(f"Added {len(chunks)} chunks to collection '{collection_name}'")
