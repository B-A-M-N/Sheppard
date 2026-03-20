from .config import CHUNK_SIZE, CHUNK_OVERLAP

def chunk_text(text: str):
    """
    Split text into manageable chunks.
    Ensures no chunk exceeds the CHUNK_SIZE limit.
    """
    if not text:
        return []
        
    # Clean up excessive newlines
    text = text.replace("\n\n\n", "\n\n")
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        
        # Try to find a logical break point (newline or space)
        if end < len(text):
            # Look back for a newline
            newline_pos = text.rfind("\n", start + CHUNK_SIZE // 2, end)
            if newline_pos != -1:
                end = newline_pos + 1
            else:
                # Look back for a space
                space_pos = text.rfind(" ", start + CHUNK_SIZE // 2, end)
                if space_pos != -1:
                    end = space_pos + 1
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
            
        start += (end - start) - CHUNK_OVERLAP
        # Safety: avoid infinite loop if overlap >= size
        if start >= len(text) or (end - start) <= 0:
            break
            
    return chunks
