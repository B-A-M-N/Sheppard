"""
llm_schemas.py — JSON schema constants for grammar-constrained decoding.

These schemas are passed to Ollama via the 'format' parameter.
Ollama >= 0.1.30 uses grammar masking to guarantee structural compliance.
"""

import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Ollama Format Schemas — Grammar-Constrained Decoding
# ──────────────────────────────────────────────────────────────────────

ATOM_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "atoms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["claim", "evidence", "event", "procedure", "contradiction"]
                    },
                    "content": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                },
                "required": ["type", "content", "confidence"]
            },
            "minItems": 1
        }
    },
    "required": ["atoms"]
}

CRITIQUE_SCHEMA = {
    "type": "object",
    "properties": {
        "critique": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "minimum": 1},
                    "valid": {"type": "boolean"},
                    "reason": {"type": "string"},
                    "fix": {"type": "string"}
                },
                "required": ["index", "valid"]
            },
            "minItems": 1
        }
    },
    "required": ["critique"]
}

# Compression schema — converts ANY text into claims, regardless of structure.
COMPRESSION_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                },
                "required": ["content", "confidence"]
            },
            "minItems": 1
        }
    },
    "required": ["claims"]
}

# ──────────────────────────────────────────────────────────────────────
# Source classification constants
# ──────────────────────────────────────────────────────────────────────

_LOW_VALUE_SOURCE_PATTERNS = [
    'dictionary', 'thesaurus', 'define:', 'meaning of',
    'wikihow.com', 'quora.com', 'reddit.com/r/Ask',
    'merriam-webster.com', 'oed.com', 'dictionary.com', 'lexico.com',
    'cambridge.org/dictionary', 'collinsdictionary.com',
]

# ──────────────────────────────────────────────────────────────────────
# Embedding centroid references
# ──────────────────────────────────────────────────────────────────────

_LOW_VALUE_CENTROID_TEXTS = [
    "This page defines the term. It provides a brief explanation.",
    "What is X? X is a concept that means something in a certain context.",
    "Read more about this topic. Click here for additional information.",
    "Introduction to the subject. Background and overview for beginners.",
    "Table of contents: Section 1, Section 2, Section 3. See also related pages.",
    "This article is a stub. You can help expand it by editing.",
    "Glossary of terms and definitions. Alphabetical listing of concepts.",
]

_HIGH_VALUE_CENTROID_TEXTS = [
    "We propose a novel approach that achieves significant improvements over prior methods. Our experiments demonstrate a 23 percent reduction in error across three benchmark datasets.",
    "The architecture consists of three interconnected modules: an encoder that processes input sequences, a transformer layer with multi-head attention, and a decoder that generates output tokens through autoregressive sampling.",
    "We trained the model on 1.5 trillion tokens using AdamW optimizer with learning rate warmup followed by cosine decay. Results show state-of-the-art performance on twelve evaluation tasks including reasoning and generation benchmarks.",
    "Ablation studies reveal that removing the normalization layer degrades performance by 15 percent while eliminating the residual connections causes training divergence after 200 epochs.",
]

# ──────────────────────────────────────────────────────────────────────
# Compression prompt
# ──────────────────────────────────────────────────────────────────────

_COMPRESS_PROMPT = """Convert the following text into 3-10 factual, atomic knowledge claims.

Rules:
- Each claim must be a standalone factual statement (understandable without context)
- Each claim must be a complete sentence
- Preserve the original meaning — do NOT invent new facts
- Remove meta-references ("this article discusses", "the paper shows")
- Remove URLs, citations, and formatting
- Prefer generalizable facts over specific examples
- If the text is vague, extract the core ideas as general claims

OUTPUT FORMAT — respond with ONLY this JSON structure:
{{"claims": [{{"content": "A factual claim.", "confidence": 0.7}}]}}

TEXT TO COMPRESS:
{text}
"""
