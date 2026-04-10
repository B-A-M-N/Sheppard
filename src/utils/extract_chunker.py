"""
Token-based chunking for knowledge extraction.
Chunks at sentence boundaries with overlap to preserve finding completeness.
"""
import logging
from typing import List

logger = logging.getLogger(__name__)

# tiktoken cl100k_base counts ~25% more tokens than Llama 3's actual tokenizer
LLAMA3_CORRECTION = 0.75

# Activation threshold: only chunk if text exceeds this many tokens
CHUNK_ACTIVATION_THRESHOLD = 3500
CHUNK_SIZE = 512
CHUNK_OVERLAP = 200

_encoder = None


def _get_encoder():
    """Lazy-load tiktoken encoder."""
    global _encoder
    if _encoder is None:
        import tiktoken
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def _count_tokens(text: str) -> int:
    """Count tokens using tiktoken with Llama 3 correction."""
    encoder = _get_encoder()
    return int(len(encoder.encode(text)) * LLAMA3_CORRECTION)


def chunk_for_extraction(
    text: str,
    max_tokens: int = CHUNK_SIZE,
    overlap_tokens: int = CHUNK_OVERLAP,
) -> List[str]:
    """
    Split text into token-sized chunks at sentence boundaries with overlap.

    Only activates when text exceeds CHUNK_ACTIVATION_THRESHOLD tokens.
    Returns list of chunks, or [text] if chunking not needed.
    """
    from src.utils.embedding_distiller import clean_boilerplate, split_sentences

    cleaned = clean_boilerplate(text)
    token_count = _count_tokens(cleaned)

    if token_count <= CHUNK_ACTIVATION_THRESHOLD:
        return [cleaned]

    sentences = split_sentences(cleaned)
    if not sentences:
        return [cleaned[:4000]]  # Fallback: preserve existing behavior

    chunks: List[str] = []
    current_sentences: List[str] = []
    current_tokens = 0

    for sentence in sentences:
        sent_tokens = _count_tokens(sentence)

        if current_tokens + sent_tokens > max_tokens and current_sentences:
            # Emit current chunk
            chunks.append(" ".join(current_sentences))

            # Build overlap: keep last sentences that fit within overlap budget
            overlap_sentences: List[str] = []
            overlap_count = 0
            for j in range(len(current_sentences) - 1, -1, -1):
                s_tokens = _count_tokens(current_sentences[j])
                if overlap_count + s_tokens <= overlap_tokens:
                    overlap_sentences.insert(0, current_sentences[j])
                    overlap_count += s_tokens
                else:
                    break

            current_sentences = overlap_sentences
            current_tokens = overlap_count

        current_sentences.append(sentence)
        current_tokens += sent_tokens

    # Emit final chunk
    if current_sentences:
        chunks.append(" ".join(current_sentences))

    logger.info(f"[Chunker] Split {token_count} tokens into {len(chunks)} chunks "
                f"(size={max_tokens}, overlap={overlap_tokens})")
    return chunks if chunks else [cleaned]
