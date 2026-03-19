"""
Text processing and sanitization utilities.
File: src/utils/text_processing.py
"""

import re
import logging
import unicodedata
from typing import Optional, Union, List
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def is_control(char: str) -> bool:
    """
    Check if a character is a control character.
    
    Args:
        char: Single character to check
        
    Returns:
        bool: True if character is a control character
    """
    # Get Unicode category for character
    category = unicodedata.category(char)
    # Cc: Control, Cf: Format, Cn: Unassigned, Co: Private Use, Cs: Surrogate
    return category.startswith('C')

def sanitize_text(
    text: Union[str, List[str]],
    allow_markdown: bool = False,
    allow_html: bool = False,
    max_length: Optional[int] = None,
    preserve_whitespace: bool = False
) -> str:
    """
    Sanitize text input to prevent injection and ensure safe display.
    
    Args:
        text: Text or list of text fragments to sanitize
        allow_markdown: Whether to allow markdown syntax
        allow_html: Whether to allow HTML tags
        max_length: Maximum length for text
        preserve_whitespace: Whether to preserve original whitespace
        
    Returns:
        str: Sanitized text
    """
    # Handle list input
    if isinstance(text, list):
        text = ' '.join(str(t) for t in text)
    elif not isinstance(text, str):
        text = str(text)
        
    if not text:
        return ""
    
    # Remove null bytes and control characters except newlines and tabs
    cleaned_text = ''.join(
        char for char in text
        if char in '\n\t' or not is_control(char)
    )
    
    if not allow_html:
        # Remove HTML tags while preserving content
        cleaned_text = re.sub(r'<[^>]*>', '', cleaned_text)
    
    if not allow_markdown:
        # Escape markdown special characters
        markdown_chars = ['*', '_', '`', '#', '<', '>', '[', ']', '(', ')', '|', '~']
        for char in markdown_chars:
            cleaned_text = cleaned_text.replace(char, '\\' + char)
    
    if preserve_whitespace:
        # Only remove excessive whitespace
        cleaned_text = re.sub(r'\s{2,}', ' ', cleaned_text)
    else:
        # Normalize whitespace but preserve intentional line breaks
        cleaned_text = '\n'.join(
            ' '.join(line.split()) 
            for line in cleaned_text.splitlines()
        )
    
    # Handle URLs specially
    url_pattern = r'https?://\S+'
    urls = re.findall(url_pattern, cleaned_text)
    for url in urls:
        # Restore any escaped characters in URLs
        original_url = url.replace('\\', '')
        cleaned_text = cleaned_text.replace(url, original_url)
    
    # Truncate if needed
    if max_length and len(cleaned_text) > max_length:
        # Try to break at word boundary
        truncated = cleaned_text[:max_length]
        last_space = truncated.rfind(' ')
        if last_space > max_length * 0.8:  # Only break at word if reasonable
            truncated = truncated[:last_space]
        cleaned_text = truncated + '...'
    
    return cleaned_text.strip()

def clean_text(text: str) -> str:
    """
    Clean and normalize text content by removing unwanted elements and normalizing whitespace.
    
    Args:
        text: Input text to clean
        
    Returns:
        str: Cleaned text
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Remove common unwanted elements
    unwanted = [
        r'<script.*?</script>',
        r'<style.*?</style>',
        r'<[^>]+>',  # HTML tags
        r'(?s)\/\*.*?\*\/',  # Multi-line comments
        r'(?m)^\s*\/\/.*$'  # Single-line comments
    ]
    
    cleaned = text
    for pattern in unwanted:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
    
    # Normalize whitespace
    cleaned = ' '.join(cleaned.split())
    
    return cleaned.strip()

def extract_main_content(text: str) -> str:
    """
    Extract main content from text by removing boilerplate and peripheral content.
    
    Args:
        text: Input text to process
        
    Returns:
        str: Extracted main content
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Split into paragraphs
    paragraphs = text.split('\n\n')
    
    # Filter out likely boilerplate paragraphs
    content_paragraphs = []
    for para in paragraphs:
        # Skip if paragraph is too short
        if len(para.strip()) < 20:
            continue
            
        # Skip if likely navigation/menu text
        if any(marker in para.lower() for marker in ['menu', 'navigation', 'copyright', 'all rights reserved']):
            continue
            
        # Skip if likely advertisement
        if any(marker in para.lower() for marker in ['advertisement', 'sponsored', 'click here']):
            continue
            
        content_paragraphs.append(para.strip())
    
    # Join remaining paragraphs
    main_content = '\n\n'.join(content_paragraphs)
    
    return main_content.strip()

def clean_string(
    text: str,
    preserve_newlines: bool = True,
    preserve_urls: bool = True
) -> str:
    """
    Basic string cleaning for display.
    
    Args:
        text: String to clean
        preserve_newlines: Whether to preserve newline characters
        preserve_urls: Whether to preserve URLs intact
        
    Returns:
        str: Cleaned string
    """
    if not text or not isinstance(text, str):
        return ""
        
    # Store URLs for later restoration if needed
    urls = []
    if preserve_urls:
        urls = re.findall(r'https?://\S+', text)
    
    # Remove control characters based on preservation settings
    if preserve_newlines:
        cleaned_text = ''.join(
            char for char in text
            if char in '\n\t' or not is_control(char)
        )
    else:
        cleaned_text = ''.join(
            char for char in text
            if not is_control(char)
        )
    
    # Normalize whitespace
    if preserve_newlines:
        # Preserve line breaks but normalize other whitespace
        lines = cleaned_text.splitlines()
        cleaned_text = '\n'.join(' '.join(line.split()) for line in lines)
    else:
        cleaned_text = ' '.join(cleaned_text.split())
    
    # Restore URLs if needed
    if preserve_urls:
        for url in urls:
            # Create pattern that matches URL with potential whitespace
            pattern = re.escape(url).replace(r'\ ', r'\s*')
            # Find and replace normalized version with original
            matches = re.finditer(pattern, cleaned_text, re.IGNORECASE)
            for match in matches:
                cleaned_text = cleaned_text[:match.start()] + url + cleaned_text[match.end():]
    
    return cleaned_text.strip()

def extract_urls(text: str) -> List[str]:
    """
    Extract valid URLs from text.
    
    Args:
        text: Text to extract URLs from
        
    Returns:
        List[str]: List of extracted URLs
    """
    if not text or not isinstance(text, str):
        return []
        
    # Match URLs with various schemes and formats
    url_pattern = r'https?://(?:[\w-]|\.|/|\?|=|%|&|#|~|@|\+)+(?<![.,?!])'
    return re.findall(url_pattern, text)

def normalize_whitespace(
    text: str,
    preserve_paragraphs: bool = True
) -> str:
    """
    Normalize whitespace in text while optionally preserving paragraph breaks.
    
    Args:
        text: Text to normalize
        preserve_paragraphs: Whether to preserve paragraph breaks
        
    Returns:
        str: Text with normalized whitespace
    """
    if not text or not isinstance(text, str):
        return ""
        
    if preserve_paragraphs:
        # Split on paragraph breaks (2+ newlines)
        paragraphs = re.split(r'\n\s*\n', text)
        # Normalize each paragraph independently
        normalized_paragraphs = [' '.join(p.split()) for p in paragraphs]
        # Rejoin with double newlines
        return '\n\n'.join(normalized_paragraphs)
    else:
        # Simple whitespace normalization
        return ' '.join(text.split())

def format_memory_content(
    text: str,
    max_length: int = 100,
    add_timestamp: bool = True
) -> str:
    """
    Format text for memory storage display.
    
    Args:
        text: Text to format
        max_length: Maximum display length
        add_timestamp: Whether to add timestamp to content
        
    Returns:
        str: Formatted text
    """
    # Clean the text
    cleaned_text = clean_string(text)
    
    # Truncate if needed
    if len(cleaned_text) > max_length:
        # Try to break at sentence boundary
        truncated = cleaned_text[:max_length-3]
        last_sentence = re.search(r'[.!?]\s+[A-Z]', truncated[::-1])
        if last_sentence and last_sentence.start() < max_length * 0.2:  # Only break at sentence if near end
            truncated = truncated[:-(last_sentence.start())]
        cleaned_text = truncated + "..."
    
    # Add timestamp if requested
    if add_timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cleaned_text = f"[{timestamp}] {cleaned_text}"
    
    return cleaned_text

def strip_markdown(text: str) -> str:
    """
    Remove markdown formatting while preserving content.
    
    Args:
        text: Text containing markdown to strip
        
    Returns:
        str: Text with markdown formatting removed
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    
    # Remove inline code
    text = re.sub(r'`[^`]+`', '', text)
    
    # Remove headers
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    
    # Remove bold/italic
    text = re.sub(r'\*\*?(.*?)\*\*?', r'\1', text)
    text = re.sub(r'__?(.*?)__?', r'\1', text)
    
    # Remove links
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove images
    text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', text)
    
    # Remove blockquotes
    text = re.sub(r'^\s*>\s+', '', text, flags=re.MULTILINE)
    
    # Remove horizontal rules
    text = re.sub(r'^\s*[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    
    return normalize_whitespace(text)
