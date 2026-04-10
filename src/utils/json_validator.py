"""
Fix for JSONValidator to correctly use OllamaClient.chat method.
File: src/utils/json_validator.py

Embedding-Safe Distillation Architecture:
  - All embeddings go through embedding_distiller.safe_embed()
  - Boilerplate stripping + semantic filtering before embedding
  - Sliding window + pooling for large sources
  - No more raw document embedding
"""

import json
import logging
import math
import re
from typing import Dict, Any, List, Optional, Union, Callable
import asyncio
from src.utils.text_processing import repair_json
from src.utils.embedding_distiller import (
    safe_embed,
    gate_source,
    distill_for_embedding,
    rough_token_count,
    clean_boilerplate
)

logger = logging.getLogger(__name__)

class JSONValidator:
    """Validates and repairs LLM-generated JSON responses using iterative prompting."""
    
    def __init__(self, max_attempts: int = 3):
        """Initialize validator with retry settings."""
        self.max_attempts = max_attempts
        self.logger = logging.getLogger(__name__)
    
    async def validate_and_fix_json(
        self, 
        llm_client, 
        response_text: str, 
        schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate and fix JSON from LLM response using iterative prompting.
        
        Args:
            llm_client: Ollama client instance
            response_text: Text response from LLM to parse as JSON
            schema: Expected structure of the JSON
            
        Returns:
            Dict[str, Any]: Valid JSON object
        """
        attempts = 0
        current_json = None
        
        # First try to parse the JSON directly
        try:
            # Extract JSON if surrounded by other text
            json_text = self._extract_json(response_text)
            if json_text:
                current_json = json.loads(json_text)
                # Validate against schema
                if self._validate_schema(current_json, schema):
                    return current_json  # Already valid
        except json.JSONDecodeError as e:
            self.logger.warning(f"Initial JSON parse failed: {str(e)}")
            # Continue to repair flow
        except Exception as e:
            self.logger.warning(f"Initial validation failed: {str(e)}")
            # Continue to repair flow if we have partial JSON
        
        # Iterative repair flow
        while attempts < self.max_attempts:
            attempts += 1
            self.logger.info(f"JSON repair attempt {attempts}/{self.max_attempts}")
            
            try:
                # If we couldn't parse it at all, ask for complete reformat
                if current_json is None:
                    prompt = self._create_format_repair_prompt(response_text, schema)
                else:
                    # If we have JSON but invalid, ask for corrections
                    prompt = self._create_correction_prompt(current_json, schema)
                
                # Get the repair from LLM - using correct parameters for your OllamaClient
                messages = [{"role": "user", "content": prompt}]
                
                # Use the client.chat method with the correct parameters
                repair_content = ""
                async for response in llm_client.chat(
                    messages=messages,
                    stream=True,
                    temperature=0.2  # Low temperature for precision
                ):
                    if response and response.content:
                        repair_content += response.content
                
                # Try to extract and parse JSON from response
                json_text = self._extract_json(repair_content)
                if not json_text:
                    self.logger.warning(f"No JSON found in repair response")
                    if attempts >= self.max_attempts:
                        break
                    continue
                
                try:
                    current_json = json.loads(json_text)
                    
                    # Validate against schema
                    if self._validate_schema(current_json, schema):
                        self.logger.info(f"JSON successfully repaired after {attempts} attempts")
                        return current_json  # Success!
                except Exception as e:
                    self.logger.warning(f"Repair parsing failed: {str(e)}")
                    if attempts >= self.max_attempts:
                        break
                    continue
            
            except Exception as e:
                self.logger.error(f"Repair attempt {attempts} failed: {str(e)}")
                if attempts >= self.max_attempts:
                    break
        
        # If we get here, all attempts failed - return fallback
        self.logger.warning(f"All repair attempts failed, using fallback")
        return self._create_fallback_response(schema)
    
    def _create_format_repair_prompt(self, invalid_text: str, schema: Dict[str, Any]) -> str:
        """Create prompt to format completely invalid JSON."""
        schema_str = json.dumps(schema, indent=2)
        return f"""
        The following text was supposed to be valid JSON but has formatting issues:
        
        ```
        {invalid_text}
        ```
        
        I need you to fix this and provide properly formatted JSON that matches this structure:
        
        ```json
        {schema_str}
        ```
        
        Return ONLY the fixed JSON with no explanation or other text. Make sure all required fields are present.
        The output should be valid JSON that can be parsed by json.loads().
        """
    
    def _create_correction_prompt(self, current_json: Dict[str, Any], schema: Dict[str, Any]) -> str:
        """Create prompt to correct an invalid JSON object."""
        current_str = json.dumps(current_json, indent=2)
        schema_str = json.dumps(schema, indent=2)
        return f"""
        The following JSON does not properly conform to the required structure:
        
        ```json
        {current_str}
        ```
        
        I need you to fix this JSON to match this structure:
        
        ```json
        {schema_str}
        ```
        
        Return the complete fixed JSON object with all required fields.
        Respond ONLY with the fixed JSON and no additional text.
        """
    
    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON from text that might contain other content."""
        # Try to find JSON in code blocks first
        code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        code_matches = re.findall(code_block_pattern, text)
        
        for match in code_matches:
            try:
                # Validate it's parseable
                json.loads(match.strip())
                return match.strip()
            except json.JSONDecodeError:
                continue
        
        # Try to find JSON with brackets
        bracket_pattern = r'(\{[\s\S]*\}|\[[\s\S]*\])'
        bracket_matches = re.findall(bracket_pattern, text)
        
        for match in bracket_matches:
            try:
                json.loads(match.strip())
                return match.strip()
            except json.JSONDecodeError:
                continue
                
        # Try finding the first { and matching closing }
        start_idx = text.find('{')
        if start_idx >= 0:
            # Simple bracket counting - not perfect but often works
            open_count = 0
            for i in range(start_idx, len(text)):
                if text[i] == '{':
                    open_count += 1
                elif text[i] == '}':
                    open_count -= 1
                    if open_count == 0:
                        # Found potential JSON
                        json_text = text[start_idx:i+1]
                        try:
                            json.loads(json_text)
                            return json_text
                        except json.JSONDecodeError:
                            pass
        
        return None
    
    def _validate_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
        """Simple schema validation - checks required fields and basic types."""
        try:
            # Check required fields
            for field in schema.get('required', []):
                if field not in data:
                    self.logger.warning(f"Required field missing: {field}")
                    return False
            
            # Check property types
            for field, field_schema in schema.get('properties', {}).items():
                if field in data:
                    # Check type
                    if field_schema.get('type') == 'string' and not isinstance(data[field], str):
                        self.logger.warning(f"Field {field} should be string, got {type(data[field])}")
                        return False
                    elif field_schema.get('type') == 'array' and not isinstance(data[field], list):
                        self.logger.warning(f"Field {field} should be array, got {type(data[field])}")
                        return False
                    
                    # Check string constraints
                    if field_schema.get('type') == 'string' and field_schema.get('minLength'):
                        min_length = field_schema.get('minLength')
                        if len(data[field]) < min_length:
                            self.logger.warning(f"Field {field} too short: {len(data[field])} < {min_length}")
                            return False
                    
                    # Check array constraints
                    if field_schema.get('type') == 'array' and field_schema.get('minItems'):
                        min_items = field_schema.get('minItems')
                        if len(data[field]) < min_items:
                            self.logger.warning(f"Array {field} too short: {len(data[field])} < {min_items}")
                            return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Schema validation error: {str(e)}")
            return False
    
    def _create_fallback_response(self, schema: Dict[str, Any], context: Optional[Dict] = None) -> Dict[str, Any]:
        """Create a minimal valid response that matches the schema.

        Args:
            schema: The JSON schema to match
            context: Optional context hints for smarter fallbacks
        """
        fallback = {}

        # Fill in required fields with minimal valid values
        for field in schema.get('required', []):
            field_schema = schema.get('properties', {}).get(field, {})
            field_type = field_schema.get('type', 'string')

            if field_type == 'string':
                fallback[field] = context.get('fallback_string', '') if context else ''
            elif field_type == 'array':
                # Check if this is the 'atoms' array with specific item schema
                items_schema = field_schema.get('items', {})
                if items_schema.get('type') == 'object' and items_schema.get('required'):
                    # Don't create fallback objects — return empty array instead
                    # Empty arrays are valid and will be handled upstream
                    fallback[field] = []
                else:
                    fallback[field] = []
            elif field_type == 'number':
                fallback[field] = 0
            elif field_type == 'boolean':
                fallback[field] = False
            elif field_type == 'object':
                fallback[field] = {}
            else:
                fallback[field] = None

        return fallback

# ============================================================================
# Multi-Pass Knowledge Compiler — Deterministic Compilation Pipeline
# ============================================================================
#
# Pipeline:
#   0. Gate: classify_source_quality → skip dictionaries/nav pages
#   1. Extract: MODE: EXTRACT_ATOMS → strict {"atoms": [...]}
#   1.5. Structural Validation: cheap local checks (length, punctuation, verbs)
#   2. Conditional Atomization: ONLY if >30% atoms are FRAGMENT/WEAK
#   3. Critique: MODE: CRITIQUE_ATOMS → validate/repair
#   3.5. Repair Pass: apply fixes for invalid atoms
#   4. Quality Gates: final hard filter (safety net, not primary filter)
#   5. Fallback: if zero yield → relax constraints
#
# NOT: Scrape → Extract → Store (the old broken pipeline)
# ============================================================================

# Source type classification — gates that run BEFORE smelting
_LOW_VALUE_SOURCE_PATTERNS = [
    'dictionary', 'thesaurus', 'define:', 'meaning of',
    'wikihow.com', 'quora.com', 'reddit.com/r/Ask',
    # Explicit dictionary domains (URL may not always contain '/dictionary/')
    'merriam-webster.com', 'oed.com', 'dictionary.com', 'lexico.com',
    'cambridge.org/dictionary', 'collinsdictionary.com',
]

def classify_source_quality(url: str, content: str) -> str:
    """Classify source before extraction. Returns 'skip', 'standard', 'academic'."""
    url_lower = url.lower() if url else ''

    # Hard skip: lexical entries, definitions-only pages
    for pattern in _LOW_VALUE_SOURCE_PATTERNS:
        if pattern in url_lower:
            return 'skip'

    # Also check content for dictionary-like patterns (URL might be masked/redirected)
    if url_lower and not any(x in url_lower for x in ['arxiv.org', 'ieee.org', 'acm.org', 'springer.com', 'nature.com', '.edu/', 'doi.org']):
        content_lower = content[:500].lower() if content else ''
        # Dictionary page indicators in content
        dict_indicators = [
            'see the full definition', 'meaning of', 'pronunciation of',
            'first known use', 'noun (as defined in', 'verb (as defined in',
            'kids definition', 'medical definition', 'legal definition',
            'subscribe to access', 'start your free trial',
        ]
        matches = sum(1 for ind in dict_indicators if ind in content_lower)
        if matches >= 2:
            return 'skip'

    if any(x in url_lower for x in ['arxiv.org', 'ieee.org', 'acm.org', 'springer.com', 'nature.com', '.edu/', 'doi.org']):
        return 'academic'

    return 'standard'


# ── Embedding-assisted source scoring (Gate 0 enhancement) ──

def _cosine_similarity(a, b):
    """Cosine similarity between two vectors. Pure math, no dependencies."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# Reference centroids — structural, not domain-specific.
# These represent information density patterns, not topics.
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


async def _embed_source_quality_check(text, llm_client):
    """
    Gate 0 enhancement: embedding-assisted source quality scoring.

    Uses embedding_distiller.safe_embed() to guarantee no context overflow.
    Compares source text against reference centroids for information density.
    NOT domain-specific — measures structural properties of the text itself.

    Returns: (score_low, score_high, should_skip)
    """
    try:
        # Pre-flight gate: drop oversized sources early
        gate_result, token_count = gate_source(text)
        if gate_result == "DROP":
            logger.info(f"[Distillery] Gate 0: Dropping high-noise source ({token_count} tokens)")
            return 0.0, 0.0, True

        # Safe embed: handles distillation + windowing automatically
        async def embed_fn(chunk):
            return await llm_client.generate_embedding(chunk)

        source_emb, embed_stats = await safe_embed(text, embed_fn)

        if not source_emb:
            # Embedding failed — hard fail, no silent fallback
            logger.warning(f"[Distillery] Gate 0: Embedding failed after distillation — marking as skip")
            return 0.0, 0.0, True

        logger.debug(
            f"[Distillery] Gate 0: Embedded {embed_stats['distillation'].get('chunks', 1)} chunks "
            f"({embed_stats['distillation'].get('sentences_filtered', 0)} atoms)"
        )

        # Compare against centroids (also safe-embedded)
        low_scores = []
        high_scores = []

        for ref_text in _LOW_VALUE_CENTROID_TEXTS:
            ref_emb, _ = await safe_embed(ref_text, embed_fn)
            if ref_emb:
                low_scores.append(_cosine_similarity(source_emb, ref_emb))

        for ref_text in _HIGH_VALUE_CENTROID_TEXTS:
            ref_emb, _ = await safe_embed(ref_text, embed_fn)
            if ref_emb:
                high_scores.append(_cosine_similarity(source_emb, ref_emb))

        score_low = max(low_scores) if low_scores else 0.0
        score_high = max(high_scores) if high_scores else 0.0

        should_skip = score_low > 0.85 and score_high < 0.60

        return score_low, score_high, should_skip

    except Exception as e:
        logger.warning(f"[Distillery] Embedding source quality check failed: {e}")
        return 0.0, 0.0, False


async def _embed_atom_dedup(atoms, llm_client, threshold=0.92):
    """
    Pass 2 enhancement: embedding-based atom deduplication.

    Uses embedding_distiller.safe_embed() for reliable embeddings.
    Groups semantically identical atoms (different wording, same meaning).
    Merges duplicates, keeping the highest-confidence form.

    Returns deduplicated atom list.
    """
    if len(atoms) < 2:
        return atoms

    # Safe embed all atom contents
    async def embed_fn(chunk):
        return await llm_client.generate_embedding(chunk)

    embeddings = []
    for i, atom in enumerate(atoms):
        content = atom.get('content', '')
        emb, stats = await safe_embed(content, embed_fn)
        if emb:
            embeddings.append(emb)
        else:
            # Fallback: zero vector (will never match threshold)
            logger.debug(f"[Distillery] Pass 2.5: Atom {i} embed failed, using zero vector")
            embeddings.append([0.0] * 1024)

    # Greedy dedup: mark duplicates
    n = len(atoms)
    kept = [True] * n
    for i in range(n):
        if not kept[i]:
            continue
        for j in range(i + 1, n):
            if not kept[j]:
                continue
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            if sim >= threshold:
                # Keep the one with higher confidence
                if atoms[j].get('confidence', 0) > atoms[i].get('confidence', 0):
                    kept[i] = False
                else:
                    kept[j] = False

    return [atoms[i] for i in range(n) if kept[i]]


async def _check_semantic_drift(atom, source_text, llm_client, threshold=0.55):
    """
    Pass 3 enhancement: detect semantic drift between atom and source.

    Uses embedding_distiller.safe_embed() for reliable embeddings.
    If an atom's content has low cosine similarity with its source span,
    it likely hallucinated or drifted.

    Returns: (similarity_score, is_drifting)
    """
    content = atom.get('content', '')
    if not content or not source_text:
        return 0.0, True

    try:
        async def embed_fn(chunk):
            return await llm_client.generate_embedding(chunk)

        # Safe embed both (handles distillation automatically)
        atom_emb, _ = await safe_embed(content, embed_fn)
        source_emb, _ = await safe_embed(source_text, embed_fn)

        if not atom_emb or not source_emb:
            return 0.0, True

        sim = _cosine_similarity(atom_emb, source_emb)
        return sim, sim < threshold

    except Exception as e:
        logger.debug(f"[Distillery] Pass 3: Semantic drift check failed: {e}")
        return 0.0, True


def _has_verb(text: str) -> bool:
    """Cheap heuristic: does this sentence have a verb-like word?"""
    # Common verb patterns in technical text
    verb_patterns = [
        ' is ', ' are ', ' was ', ' were ', ' has ', ' have ', ' had ',
        ' can ', ' could ', ' will ', ' would ', ' should ', ' may ',
        ' uses ', ' uses ', ' used ', ' using ', ' provides ', ' provides ',
        ' achieves ', ' reduces ', ' increases ', ' improves ', ' shows ',
        ' demonstrates ', ' implements ', ' requires ', ' supports ',
        ' enables ', ' allows ', ' prevents ', ' detects ', ' generates ',
        ' trains ', ' trained ', ' predicts ', ' evaluates ', ' compares ',
    ]
    text_lower = text.lower()
    return any(v in text_lower for v in verb_patterns)


def _classify_atom_quality(content: str) -> str:
    """Cheap structural validation. Returns 'VALID', 'FRAGMENT', or 'WEAK'."""
    if not content or len(content) < 20:
        return 'FRAGMENT'
    
    # Check for proper sentence termination
    has_period = content.rstrip().endswith(('.', '!', '?', ')', ']'))
    
    # Check for verb presence
    has_v = _has_verb(content)
    
    # Word count
    wc = len(content.split())
    
    if has_period and has_v and wc >= 8:
        return 'VALID'
    elif not has_period or not has_v:
        return 'FRAGMENT'
    else:
        return 'WEAK'  # Has verb and termination but short


async def extract_technical_atoms(
    llm_client,
    text: str,
    topic: str,
    source_url: str = ''
) -> List[Dict[str, Any]]:
    """
    Multi-pass knowledge compiler with embedding-assisted intelligence.

    Gate 0a: String-based source quality classification (fast skip)
    Gate 0b: Embedding-based source quality scoring (information density check)
    Pass 1: Extraction (temp=0.1)
    Pass 1.5: Structural validation (cheap, local)
    Pass 2: Conditional atomization (ONLY if >30% fragments)
    Pass 2.5: Embedding-based atom deduplication (semantic merge)
    Pass 3: Critique + Repair with semantic drift detection (temp=0.0)
    Pass 4: Quality gates (safety net)
    Fallback: Relax constraints if zero yield
    """
    # --- GATE 0a: String-based classification (fast) ---
    source_type = classify_source_quality(source_url, text)
    if source_type == 'skip':
        logger.info(f"[Distillery] Gate 0a: Skipping low-value source for '{source_url[:60]}'")
        return []

    # --- GATE 0b: Embedding-based information density check ---
    try:
        score_low, score_high, should_skip = await _embed_source_quality_check(text, llm_client)
        if should_skip:
            logger.info(f"[Distillery] Gate 0b: Embedding skip — low={score_low:.2f}, high={score_high:.2f} for '{source_url[:60]}'")
            return []
        if score_low > 0 or score_high > 0:
            logger.info(f"[Distillery] Gate 0b: Embedding scores — low={score_low:.2f}, high={score_high:.2f}")
    except Exception as e:
        logger.debug(f"[Distillery] Gate 0b embedding check failed, falling back to string: {e}")

    try:
        # --- PASS 1: Extraction ---
        raw_atoms = await _extract_raw_atoms(llm_client, text, topic, source_type)
        if not raw_atoms:
            logger.info(f"[Distillery] Pass 1: Zero atoms extracted for '{topic}'")
            return []
        logger.info(f"[Distillery] Pass 1: Extracted {len(raw_atoms)} atoms")

        # --- PASS 1.5: Structural Validation (cheap, local) ---
        quality_report = _structural_validation(raw_atoms)
        logger.info(f"[Distillery] Pass 1.5: {quality_report['VALID']} valid, {quality_report['FRAGMENT']} fragment, {quality_report['WEAK']} weak")

        # --- PASS 2: Conditional Atomization ---
        fragment_pct = (quality_report['FRAGMENT'] + quality_report['WEAK']) / max(len(raw_atoms), 1)

        if fragment_pct > 0.30:
            logger.info(f"[Distillery] Pass 2: {fragment_pct:.0%} fragments — activating atomization")
            atomized = await _atomize_fragments(llm_client, raw_atoms, topic)
            logger.info(f"[Distillery] Pass 2: Atomized to {len(atomized)} atoms")
        else:
            logger.info(f"[Distillery] Pass 2: {fragment_pct:.0%} fragments — skipping atomization")
            atomized = raw_atoms

        # --- PASS 2.5: Embedding-based deduplication ---
        deduped = await _embed_atom_dedup(atomized, llm_client, threshold=0.92)
        dedup_count = len(atomized) - len(deduped)
        if dedup_count > 0:
            logger.info(f"[Distillery] Pass 2.5: Merged {dedup_count} semantically duplicate atoms ({len(deduped)} remaining)")
        else:
            logger.info(f"[Distillery] Pass 2.5: No semantic duplicates found")

        # --- PASS 3: Critique + Repair with drift detection ---
        critiqued = await _critique_and_repair(llm_client, deduped)
        logger.info(f"[Distillery] Pass 3: After critique+repair, {len(critiqued)} atoms")

        # --- PASS 3.5: Semantic drift check ---
        drift_flagged = []
        for atom in critiqued:
            sim, drifting = await _check_semantic_drift(atom, text, llm_client, threshold=0.55)
            if drifting:
                atom['_drift_score'] = sim
                drift_flagged.append(atom)
        if drift_flagged:
            logger.info(f"[Distillery] Pass 3.5: {len(drift_flagged)} atoms flagged for semantic drift (will be filtered)")
            # Remove drifting atoms — they're too far from source
            drift_ids = {id(a) for a in drift_flagged}
            critiqued = [a for a in critiqued if id(a) not in drift_ids]

        # --- PASS 4: Quality Gates (safety net) ---
        final_atoms = []
        for atom in critiqued:
            normalized = _normalize_single_atom(atom)
            if normalized:
                final_atoms.append(normalized)

        # --- FALLBACK: If zero yield, relax constraints ---
        if not final_atoms and raw_atoms:
            logger.info(f"[Distillery] Pass 4: Zero yield — activating fallback mode")
            for atom in raw_atoms:
                normalized = _normalize_single_atom_fallback(atom)
                if normalized:
                    final_atoms.append(normalized)
            logger.info(f"[Distillery] Fallback: recovered {len(final_atoms)} atoms")

        if final_atoms:
            logger.info(f"[Distillery] Final: {len(final_atoms)} atoms stored for '{topic}'")
        else:
            logger.warning(f"[Distillery] All passes produced zero valid atoms for '{topic}'")

        # --- ENTITY EXTRACTION: Extract named entities for Frontier discovery ---
        entities = _extract_entities_from_atoms(final_atoms)
        if entities:
            logger.info(f"[Distillery] Extracted {len(entities)} discovery entities: {entities[:10]}")

        return final_atoms

    except Exception as e:
        import traceback
        logger.error(f"[Distillery] extract_technical_atoms FAILED: {e}\n{traceback.format_exc()}")
        return []


# ──────────────────────────────────────────────────────────────────────
# Cognitive Filter v3 — Domain-Agnostic Structural Entity Classification
# ──────────────────────────────────────────────────────────────────────
#
# Philosophy: filter *reusability in reasoning*, not words.
# No subject-matter knowledge. No keyword lists. No domain rules.
#
# Core insight: structural heuristics alone cannot distinguish
# "DOI Digital Object Identifier" from "Neural Architecture Search"
# — they share identical surface properties. The discriminant is
# BEHAVIORAL: real concepts repeat across sources; artifacts don't.
#
# Architecture:
#   extract → structural reject → cross-frequency → tier → gate
#
# Tiers:
#   EXPANDABLE  → Frontier expansion seeds (stable, self-contained concepts)
#   CONTEXTUAL  → stored for reference only (datasets, tools, locations)
#   NOISE       → dropped (fragments, metadata, artifacts)


# ── Structural artifact indicators (NOT domain knowledge) ──
# These detect document/web plumbing, not concepts.
# Domain-agnostic because they exist in ALL documents.
_ARTIFACT_PATTERNS = {
    # Identifier patterns (colon-terminated prefixes)
    "doi:", "isbn:", "issn:", "pmid:", "pmcid:", "arxiv:",
    # Reference abbreviations
    "vol.", "no.", "pp.", "pg.", "cf.", "fig.", "eq.", "sec.",
    # Web UI chrome
    "click here", "read more", "view full", "all rights reserved",
    "powered by", "terms of use", "privacy policy",
    "contact us", "subscribe", "follow us",
}


def _is_artifact_fragment(entity):
    """Reject document/web plumbing via structural patterns only."""
    lower = entity.lower()

    for pattern in _ARTIFACT_PATTERNS:
        if pattern in lower:
            return True

    # URL-like
    if any(c in entity for c in ("://", "www.")):
        return True

    # Email-like
    if "@" in entity:
        return True

    # DOI/identifier (starts with "10." followed by digits)
    if len(entity) > 3 and entity.startswith("10.") and entity[3:5].isdigit():
        return True

    # Pure numeric or numeric range
    stripped = entity.replace(" ", "").replace("-", "").replace(",", "")
    if stripped.isdigit():
        return True

    # Single uppercase letter
    if len(entity) == 1 and entity.isupper():
        return True

    return False


def _is_generic_singleton(entity):
    """
    Reject single-token entity that is too generic to expand.
    Uses structural heuristics, not domain knowledge:
    - Ultra-short words (2-3 chars) are unlikely to be specific concepts
    - Common English function words are not concepts
    """
    words = entity.split()
    if len(words) != 1:
        return False

    w = words[0].lower()

    # Too short to be specific
    if len(w) <= 3:
        return True

    # Common English function words (structural, not domain-specific)
    if w in {
        "the", "a", "an", "of", "in", "on", "at", "to", "for",
        "and", "or", "but", "is", "are", "was", "were", "be",
        "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "can", "could", "may", "might",
        "shall", "should", "must", "need", "dare", "ought",
        "used", "about", "above", "across", "after", "against",
        "along", "among", "around", "before", "behind", "below",
        "beneath", "beside", "between", "beyond", "by", "down",
        "during", "except", "from", "into", "like", "near",
        "off", "onto", "out", "outside", "over", "past",
        "since", "through", "till", "toward", "under", "until",
        "up", "upon", "with", "within", "without",
        # Ultra-generic nouns that appear in every domain
        "thing", "things", "stuff", "way", "ways",
        "one", "ones", "part", "parts",
    }:
        return True

    return False


def _is_language_list(entity):
    """
    Detect language-list extraction artifacts.
    Heuristic: 4+ consecutive capitalized single-word tokens
    that are all common language names.
    """
    words = entity.lower().split()
    if len(words) < 3:
        return False

    known = {
        "english", "spanish", "portuguese", "french", "german",
        "italian", "dutch", "russian", "chinese", "japanese",
        "korean", "arabic", "hindi", "bengali", "turkish",
        "polish", "swedish", "norwegian", "danish", "finnish",
        "greek", "hebrew", "thai", "vietnamese", "indonesian",
        "malay", "tagalog", "swahili", "amharic", "latin",
        "czech", "romanian", "hungarian", "ukrainian", "persian",
        "urdu", "tamil", "telugu", "marathi", "gujarati",
    }
    match_count = sum(1 for w in words if w in known)
    return match_count >= 3


def _conceptual_suffix_score(entity):
    """
    Bonus for morphological markers of abstract concepts.
    Suffixes like -tion, -ing, -ment exist across all technical domains.
    """
    score = 0.0
    suffixes = {
        "ing", "tion", "sion", "ment", "ence", "ance",
        "ity", "ness", "ology", "graphy", "metry",
    }
    for w in entity.lower().split():
        for sfx in suffixes:
            if w.endswith(sfx) and len(w) > len(sfx) + 1:
                score += 0.5
                break
    return score


def _structural_stability(entity):
    """
    Score based on purely structural properties.
    NOTE: this cannot distinguish real concepts from well-formed artifacts.
    Cross-frequency is the primary discriminant.
    """
    score = 0.0
    words = entity.split()

    # Multi-token = more specific
    if len(words) >= 2:
        score += 2.0
    if len(words) >= 3:
        score += 1.0

    # Too long = likely a fragment
    if len(words) > 6:
        score -= 2.0

    # Character length
    if len(entity) < 4:
        score -= 2.0
    if len(entity) > 100:
        score -= 1.0

    # Named concept signal
    if entity[0].isupper() and not entity.isupper():
        score += 0.5

    # All-caps = likely acronym
    if entity.isupper():
        score -= 2.0

    # CamelCase
    if _is_camel_case(entity):
        score += 1.5

    # Proper noun phrase
    if all(w[0].isupper() for w in words if w):
        score += 1.0

    # Hyphenated compound
    if "-" in entity and len(words) == 1:
        score += 1.0

    # Morphological markers
    score += _conceptual_suffix_score(entity)

    # Repetition check
    if len(words) > 1:
        unique_ratio = len(set(w.lower() for w in words)) / len(words)
        if unique_ratio < 0.7:
            score -= 1.0

    return score


def _classify_tier(entity, cross_freq=0):
    """
    Classify entity into tier.

    cross_freq is THE key signal: real concepts appear across multiple
    independent sources; artifacts appear once.

    Returns: "expandable" | "contextual" | "noise"
    """
    # Structural rejects
    if _is_artifact_fragment(entity):
        return "noise"
    if _is_generic_singleton(entity):
        return "noise"
    if _is_language_list(entity):
        return "noise"
    if len(entity) <= 2:
        return "noise"

    # Cross-frequency is the primary filter
    if cross_freq >= 3:
        # Appears in 3+ sources — almost certainly a real concept
        return "expandable"

    if cross_freq == 2:
        # Appears twice — likely real, but needs structural confirmation
        struct = _structural_stability(entity)
        if struct >= 2.0:
            return "expandable"
        return "contextual"

    # cross_freq == 1 (seen only once)
    # High bar: must have strong structural signals
    struct = _structural_stability(entity)
    if struct >= 5.0:
        return "contextual"  # Strong structure but single appearance — hold back
    if struct >= 3.0:
        return "contextual"
    return "noise"


def _canonicalize(entity):
    """
    Canonical form for deduplication.
    Strips determiners, singularizes via suffix rules.
    """
    words = entity.split()

    # Strip determiners
    while words and words[0].lower() in {
        "the", "a", "an", "this", "that", "these", "those",
        "its", "our", "their", "his", "her", "my", "your",
    }:
        words = words[1:]

    if not words:
        return ""

    # Singularize last word via suffix rules
    last = words[-1].lower()
    if last.endswith("ies") and len(last) > 4:
        words[-1] = words[-1][:-3] + "y"
    elif last.endswith("ses") and len(last) > 4 and not last.endswith("sses"):
        words[-1] = words[-1][:-1]
    elif last.endswith("ches") and len(last) > 5:
        words[-1] = words[-1][:-2]
    elif last.endswith("s") and not last.endswith("ss") and len(last) > 3:
        words[-1] = words[-1][:-1]

    return " ".join(words)


def _is_camel_case(token):
    """CamelCase via pure string ops. Requires 2+ uppercase and mixed case."""
    if not token or len(token) < 3:
        return False
    upper_count = sum(1 for ch in token if ch.isupper())
    has_lower = any(ch.islower() for ch in token)
    return has_lower and upper_count >= 2


def _compute_cross_frequency(raw_entities):
    """Count appearances per canonical form. Proxy for cross-source stability."""
    freq = {}
    for e in raw_entities:
        canon = _canonicalize(e)
        if canon:
            freq[canon] = freq.get(canon, 0) + 1
    return freq


def _filter_and_dedup(raw_entities):
    """
    Full cognitive gate:
    1. Cross-frequency computation
    2. Tier classification
    3. Canonicalize + deduplicate
    4. Only EXPANDABLE passes
    """
    freq = _compute_cross_frequency(raw_entities)

    # Group by canonical form
    canonical_groups = {}
    for entity in raw_entities:
        tier = _classify_tier(entity, cross_freq=freq.get(_canonicalize(entity), 0))
        if tier == "noise":
            continue

        canon = _canonicalize(entity)
        if not canon:
            continue

        score = _structural_stability(entity)
        if canon not in canonical_groups:
            canonical_groups[canon] = []
        canonical_groups[canon].append((entity, tier, score))

    # For each group: expandable passes, contextual is held back
    result = []
    for canon, forms in canonical_groups.items():
        expandable = [(e, s) for e, t, s in forms if t == "expandable"]
        if expandable:
            best = max(expandable, key=lambda x: x[1])
            result.append(best[0])

    return result


def _extract_entities_from_atoms(atoms):
    """
    Extract named entities from atoms for Frontier discovery.
    Pipeline: extract → structural reject → cross-frequency → tier → gate

    Only EXPANDABLE tier returned. CONTEXTUAL held back. NOISE dropped.
    Pure string ops. No regex. No domain hardcoding.
    """
    SKIP_PREFIXES = {
        "the", "a", "an", "this", "that", "these", "those",
        "its", "our", "their", "his", "her", "my", "your",
    }

    raw_entities = []  # list to preserve frequency info

    for atom in atoms:
        content = atom.get("content", "")
        if not content:
            continue

        # Normalize
        words = content.replace("-", " ").replace("_", " ")
        for ch in ".,;:!?()[]{}\"'\\/":
            words = words.replace(ch, " ")
        tokens = words.split()

        i = 0
        while i < len(tokens):
            token = tokens[i]

            if _is_camel_case(token):
                raw_entities.append(token)

            if token and len(token) > 1 and token[0].isupper():
                if token.lower() in SKIP_PREFIXES:
                    i += 1
                    continue

                phrase = [token]
                j = i + 1
                while j < len(tokens) and len(tokens[j]) > 1 and tokens[j][0].isupper():
                    if tokens[j].lower() not in SKIP_PREFIXES:
                        phrase.append(tokens[j])
                    j += 1

                if len(phrase) >= 2:
                    raw_entities.append(" ".join(phrase))
                    i = j
                    continue

            i += 1

    return _filter_and_dedup(raw_entities)


# ──────────────────────────────────────────────────────────────────────
# Semantic Cognitive Filter — Embedding-Assisted Entity Clustering
# ──────────────────────────────────────────────────────────────────────
#
# Uses the existing embedding model (mxbai-embed-large) for:
#   1. Semantic deduplication — cluster by meaning, not string suffixes
#   2. Cross-frequency by semantic stability — entities in the same
#      semantic cluster count toward each other's frequency
#
# This is async because it calls the embedding model.
# Called from the pipeline as: await _extract_entities_semantic(atoms, ollama_client)


async def _embed_entities(entities, ollama_client):
    """
    Generate embeddings for a list of entity strings.
    Uses embedding_distiller.safe_embed() for reliability.
    Returns list of embedding vectors (list of floats).
    Falls back to zero-vector on failure.
    """
    async def embed_fn(chunk):
        return await ollama_client.generate_embedding(chunk)

    embeddings = []
    for entity in entities:
        emb, _ = await safe_embed(entity, embed_fn)
        embeddings.append(emb if emb else [0.0] * 1024)
    return embeddings


def _cluster_by_similarity(entities, embeddings, threshold=0.75):
    """
    Cluster entities by embedding cosine similarity.
    Returns list of clusters, where each cluster is a list of entity indices.

    Uses simple greedy clustering: first entity is seed,
    similar entities join its cluster.
    """
    n = len(entities)
    if n == 0:
        return []

    assigned = [False] * n
    clusters = []

    for i in range(n):
        if assigned[i]:
            continue
        # Start new cluster with entity i as seed
        cluster = [i]
        assigned[i] = True
        for j in range(i + 1, n):
            if assigned[j]:
                continue
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            if sim >= threshold:
                cluster.append(j)
                assigned[j] = True
        clusters.append(cluster)

    return clusters


def _pick_cluster_representative(cluster_indices, entities):
    """
    From a cluster of semantically similar entities, pick the best form.
    Heuristic: prefer the longest form with proper capitalization.
    """
    forms = [entities[i] for i in cluster_indices]

    # Score each form: longer + proper case = better
    def form_score(f):
        score = len(f)
        # Bonus for proper noun phrase (each word capitalized)
        words = f.split()
        if all(w[0].isupper() for w in words if w):
            score += 10
        if f[0].isupper() and not f.isupper():
            score += 5
        return score

    return max(forms, key=form_score)


async def _extract_entities_semantic(atoms, ollama_client):
    """
    Full semantic entity extraction with embedding-assisted clustering.

    Pipeline:
    1. Extract raw entities (string scanning)
    2. Structural reject (artifacts, generics, language lists)
    3. Embed remaining entities
    4. Cluster by cosine similarity
    5. Cross-frequency by cluster membership
    6. Tier classification → only EXPANDABLE passes

    Returns list of unique, semantically deduplicated entity names.
    """
    # Step 1: Extract raw entities (reuse the sync scanner)
    SKIP_PREFIXES = {
        "the", "a", "an", "this", "that", "these", "those",
        "its", "our", "their", "his", "her", "my", "your",
    }

    raw_entities = []
    for atom in atoms:
        content = atom.get("content", "")
        if not content:
            continue

        words = content.replace("-", " ").replace("_", " ")
        for ch in ".,;:!?()[]{}\"'\\/":
            words = words.replace(ch, " ")
        tokens = words.split()

        i = 0
        while i < len(tokens):
            token = tokens[i]

            if _is_camel_case(token):
                raw_entities.append(token)

            if token and len(token) > 1 and token[0].isupper():
                if token.lower() in SKIP_PREFIXES:
                    i += 1
                    continue

                phrase = [token]
                j = i + 1
                while j < len(tokens) and len(tokens[j]) > 1 and tokens[j][0].isupper():
                    if tokens[j].lower() not in SKIP_PREFIXES:
                        phrase.append(tokens[j])
                    j += 1

                if len(phrase) >= 2:
                    raw_entities.append(" ".join(phrase))
                    i = j
                    continue

            i += 1

    # Step 2: Structural reject
    candidates = [e for e in raw_entities if not _is_artifact_fragment(e)
                  and not _is_generic_singleton(e)
                  and not _is_language_list(e)
                  and len(e) > 2]

    if not candidates:
        return []

    # Step 3: Embed candidates
    embeddings = await _embed_entities(candidates, ollama_client)

    # Step 4: Semantic clustering
    clusters = _cluster_by_similarity(candidates, embeddings, threshold=0.75)

    # Step 5: Cross-frequency by cluster size
    # Build entity -> cluster frequency map
    cluster_freq = {}
    for cluster in clusters:
        freq = len(cluster)
        for idx in cluster:
            cluster_freq[idx] = freq

    # Step 6: Pick representative + tier classification
    result = []
    for cluster in clusters:
        representative = _pick_cluster_representative(cluster, candidates)
        # Cluster size IS the cross-frequency signal
        cross_freq = len(cluster)
        tier = _classify_tier(representative, cross_freq=cross_freq)
        if tier == "expandable":
            result.append(representative)

    return result


def _structural_validation(atoms: List[Dict[str, Any]]) -> Dict[str, int]:
    """Cheap local validation — no LLM calls. Classifies each atom."""
    report = {'VALID': 0, 'FRAGMENT': 0, 'WEAK': 0}
    for atom in atoms:
        content = atom.get('content', '')
        quality = _classify_atom_quality(content)
        report[quality] += 1
    return report


async def _extract_raw_atoms(
    llm_client,
    text: str,
    topic: str,
    source_type: str = 'standard'
) -> List[Dict[str, Any]]:
    """
    Pass 1: Extraction with source-type-aware generation contract.
    SCHEMA: {"atoms": [{"type": "...", "content": "...", "confidence": 0.0-1.0}]}
    Mode lock: EXTRACT_ATOMS — NEVER critique, NEVER validate, NEVER explain.
    """
    # Source-type aware extraction focus
    focus_instructions = {
        'academic': "Focus on: mechanisms, architectures, equations, tradeoffs, metrics, experimental results.",
        'standard': "Focus on: findings, methods, architectures, algorithms, metrics, definitions.",
    }
    focus = focus_instructions.get(source_type, focus_instructions['standard'])
    
    prompt = f"""MODE: EXTRACT_ATOMS

You are a knowledge extraction engine. You are in extraction mode ONLY.
You MUST return JSON with the key "atoms". If you return anything else, it is invalid.

OUTPUT FORMAT — respond with ONLY this JSON structure:
{{"atoms": [{{"type": "claim", "content": "complete factual statement.", "confidence": 0.8}}]}}

KNOWLEDGE ATOM CONTRACT — every "content" value MUST:
✅ Be a COMPLETE sentence (subject + verb + object)
✅ Be UNDERSTANDABLE without external context
✅ Express a CONCRETE, FALSIFIABLE claim
✅ End with a period
✅ Be at least 8 words
✅ Use third person (no "our model", "this paper", "we found")

❌ NEVER produce:
- Noun phrases ("Prior methods", "Classification networks")
- Clause fragments ("Using CRNNs with convolutional layers...")
- Section headings or titles
- URLs or citations alone
- Meta-statements about the document ("This document discusses...")
- Critique or evaluation of the atoms
- Reasoning or explanation of your choices

{focus}

Additionally, prioritize extracting NAMED ENTITIES — these are critical for discovery:
- Named architectures (e.g., ResNet, Transformer, BERT, CNN, RNN, GPT)
- Algorithms and methods (e.g., Q-learning, PPO, backpropagation, attention)
- Papers, datasets, or benchmarks (e.g., ImageNet, SQuAD, GLUE)
- Specific techniques (e.g., dropout, batch normalization, contrastive learning)
- Frameworks and libraries (e.g., PyTorch, TensorFlow, JAX)

These entities will be used to discover related research — extract them prominently.

VALID EXAMPLES:
✓ "Convolutional Recurrent Neural Networks can achieve up to 43 percent decrease in angular error for direction-of-arrival estimation."
✓ "The FD-Align method aligns pre-trained model features with target task features using a discriminator network."

INVALID EXAMPLES:
✗ "Prior methods"
✗ "Using CRNNs for feature extraction"
✗ "Our model achieves..."

Extract 10-20 atoms.

DOCUMENT:
{text[:4000]}
"""
    return await _call_llm_with_schema_guard(
        llm_client, prompt, expected_schema='atoms',
        temperature=0.1, max_tokens=8192,
        error_prefix="Pass 1"
    )


async def _call_llm_with_schema_guard(
    llm_client, prompt: str, expected_schema: str,
    temperature: float, max_tokens: int,
    error_prefix: str,
    retry_temp: float = 0.05
) -> List[Dict[str, Any]]:
    """
    Generic LLM call with schema guard and automatic retry.
    Detects wrong schema (e.g. critique instead of atoms) and retries.
    """
    messages = [{"role": "user", "content": prompt}]
    response_content = ""

    try:
        async for chunk in llm_client.chat(
            messages=messages, stream=True,
            temperature=temperature, max_tokens=max_tokens
        ):
            if hasattr(chunk, 'content') and chunk.content:
                response_content += chunk.content
            elif isinstance(chunk, dict) and 'content' in chunk:
                response_content += chunk['content']

        if not response_content or len(response_content.strip()) < 10:
            return []

        # Schema guard: detect wrong mode BEFORE attempting parse
        stripped = response_content.strip()
        wrong_schemas = {'atoms': 'critique', 'critique': 'atoms'}
        wrong_key = wrong_schemas.get(expected_schema)
        if wrong_key and stripped.startswith(f'{{"{wrong_key}"'):
            logger.warning(f"[Distillery] {error_prefix}: Model returned '{wrong_key}' instead of '{expected_schema}' — mode contamination")
            return []

        try:
            atoms = _extract_atoms_from_llm_response(response_content, expected_schema=expected_schema)
        except WrongSchemaError:
            # LLM returned valid JSON but wrong schema — retry with stricter prompt
            logger.info(f"[Distillery] {error_prefix}: Wrong schema detected — retrying with strict schema guard")
            atoms = []

        # Retry once with stricter settings if zero yield
        if not atoms:
            logger.info(f"[Distillery] {error_prefix}: Zero atoms — retrying with stricter prompt")
            strict_prompt = f"""MODE: {expected_schema.upper()}

Return ONLY a JSON object with the key "{expected_schema}". NOTHING ELSE.

If {expected_schema == 'atoms':
    '{{"atoms": [{{"type": "claim", "content": "A complete factual statement with subject and verb.", "confidence": 0.8}}]}}'
else:
    '{{"critique": [{{"index": 1, "valid": true}}]}}'}

DOCUMENT (condensed):
{prompt[-2000:] if 'DOCUMENT:' in prompt else prompt[:1500]}
"""
            messages2 = [{"role": "user", "content": strict_prompt}]
            response_content = ""
            async for chunk in llm_client.chat(
                messages=messages2, stream=True,
                temperature=retry_temp, max_tokens=max_tokens
            ):
                if hasattr(chunk, 'content') and chunk.content:
                    response_content += chunk.content
                elif isinstance(chunk, dict) and 'content' in chunk:
                    response_content += chunk['content']

            if response_content and len(response_content.strip()) >= 10:
                return _extract_atoms_from_llm_response(response_content, expected_schema=expected_schema)

        return atoms

    except Exception as e:
        logger.error(f"[Distillery] {error_prefix} LLM call failed: {e}")
        return []


async def _atomize_fragments(
    llm_client,
    raw_atoms: List[Dict[str, Any]],
    topic: str
) -> List[Dict[str, Any]]:
    """
    Pass 2: Atomization — rewrite fragments into complete sentences.
    SCHEMA: {"atoms": [...]} — same as extraction, different task.
    """
    valid_atoms = []
    fragments = []

    for atom in raw_atoms:
        content = atom.get('content', '')
        quality = _classify_atom_quality(content)
        if quality == 'VALID' and not content.startswith('http'):
            valid_atoms.append(atom)
        else:
            fragments.append(atom)

    if not fragments:
        return valid_atoms

    fragment_list = "\n".join(f"{i+1}. {a['content']}" for i, a in enumerate(fragments[:15]))

    prompt = f"""MODE: EXTRACT_ATOMS

Rewrite each fragment below into a complete, standalone factual statement about {topic}.

OUTPUT FORMAT — respond with ONLY this JSON structure:
{{"atoms": [{{"content": "complete sentence."}}]}}

RULES:
- Each output MUST be a complete sentence with subject + verb
- Preserve the original meaning — do NOT invent new facts
- Expand pronouns ("our model" → "the proposed model")
- Each must be at least 8 words and end with a period
- If a fragment cannot be completed, omit it from the output

FRAGMENTS:
{fragment_list}
"""
    rewritten = await _call_llm_with_schema_guard(
        llm_client, prompt, expected_schema='atoms',
        temperature=0.2, max_tokens=4096,
        error_prefix="Pass 2"
    )

    # Merge valid + successfully rewritten
    result = list(valid_atoms)
    for rw in rewritten:
        content = rw.get('content', '').strip()
        if len(content) >= 30:
            result.append({
                "type": "claim",
                "content": content,
                "confidence": 0.6
            })

    return result


async def _critique_and_repair(
    llm_client,
    atoms: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Pass 3: Critique + Repair — validates atoms and applies fixes.
    SCHEMA: {"critique": [{"index": N, "valid": bool, "reason": "...", "fix": "..."}]}
    
    Mode lock: CRITIQUE_ATOMS — NEVER produce atoms.
    After critique: automatically repair invalid atoms with fixes.
    """
    if not atoms:
        return []

    atom_list = "\n".join(
        f"{i+1}. [{a.get('type', 'claim')}] {a.get('content', '')}"
        for i, a in enumerate(atoms[:20])
    )

    prompt = f"""MODE: CRITIQUE_ATOMS

You are a quality reviewer ONLY. You MUST return JSON with the key "critique".
You MUST NOT return atoms, extraction results, or any other schema.

OUTPUT FORMAT:
{{"critique": [
  {{"index": 1, "valid": true}},
  {{"index": 2, "valid": false, "reason": "Fragment — no verb", "fix": "Complete sentence version or null"}}
]}}

CRITERIA:
1. COMPLETE SENTENCE: Has subject + verb + object?
2. STANDALONE: Understandable without external context?
3. CONCRETE: Makes a specific, falsifiable claim?
4. NOT A FRAGMENT: Not a clause, label, or heading?

If valid=true, no reason or fix needed.
If valid=false, provide reason AND a fixed version (or null if unfixable).

ATOMS TO REVIEW:
{atom_list}
"""
    critique_result = await _call_llm_with_schema_guard(
        llm_client, prompt, expected_schema='critique',
        temperature=0.0, max_tokens=4096,
        error_prefix="Pass 3"
    )

    if not critique_result:
        logger.warning("[Distillery] Pass 3: Critique produced no results, keeping original atoms")
        return atoms

    # Merge critique results: keep valid atoms, apply fixes, drop invalid
    result = []
    applied_fixes = 0
    dropped = 0

    # Dedup by atom content to prevent duplicates from repair loop
    seen_content = set()

    def _content_key(text: str) -> str:
        """Hashable key for atom deduplication — dicts are not hashable."""
        return text.strip().lower()[:200]

    for item in critique_result:
        if not isinstance(item, dict):
            continue
        index = item.get('index', 0)
        valid = item.get('valid', False)
        fix = item.get('fix')

        if valid and 0 < index <= len(atoms):
            orig_atom = atoms[index - 1]
            content = orig_atom.get('content', '')
            key = _content_key(content)
            if key not in seen_content:
                seen_content.add(key)
                result.append(orig_atom)
        elif fix and isinstance(fix, str) and len(fix) >= 30:
            orig = atoms[index - 1] if 0 < index <= len(atoms) else {}
            fixed_content = fix.strip()
            key = _content_key(fixed_content)
            if key not in seen_content:
                seen_content.add(key)
                result.append({
                    "type": orig.get('type', 'claim'),
                    "content": fixed_content,
                    "confidence": orig.get('confidence', 0.5)
                })
                applied_fixes += 1
        elif valid is False and 0 < index <= len(atoms):
            dropped += 1  # Invalid and unfixable

    if applied_fixes:
        logger.info(f"[Distillery] Pass 3: Applied {applied_fixes} repairs, dropped {dropped} atoms")

    # If critique parsing failed, keep originals (don't lose all work)
    if not result:
        logger.warning("[Distillery] Pass 3: No valid atoms after critique, keeping originals")
        return atoms

    return result


class WrongSchemaError(Exception):
    """Raised when LLM returns valid JSON but with the wrong schema key."""
    pass


def _extract_atoms_from_llm_response(raw_text: str, expected_schema: str = 'atoms') -> List[Dict[str, Any]]:
    """
    Parse LLM response into structured atoms.

    expected_schema: 'atoms' expects {"atoms": [...]}, 'critique' expects {"critique": [...]}
    Strategy 1: Direct json.loads (valid JSON)
    Strategy 2: repair_json via json_repair library (handles broken/truncated/conversational JSON)

    NO FALLBACK TO LINE PARSING — fail fast instead of corrupting the pipeline.
    """
    valid_types = {"claim", "evidence", "event", "procedure", "contradiction"}

    # Schema keys that must be present for each expected schema
    schema_keys = {
        'atoms': ['atoms', 'facts', 'items', 'results', 'data'],
        'critique': ['critique', 'reviews', 'evaluations', 'analysis']
    }
    required_keys = schema_keys.get(expected_schema, ['atoms'])

    def _has_expected_key(parsed: dict) -> bool:
        """Check if parsed dict contains any of the expected schema keys."""
        return any(key in parsed for key in required_keys)

    # Strategy 1: Direct JSON parse (happy path)
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict) and not _has_expected_key(parsed):
            # Valid JSON but wrong schema — don't waste time on repair
            actual_keys = list(parsed.keys())
            logger.warning(f"[Distillery] Schema mismatch: expected one of {required_keys}, got {actual_keys}")
            raise WrongSchemaError(f"Wrong schema: expected {required_keys}, got {actual_keys}")
        atoms = _normalize_atom_list(parsed, expected_schema=expected_schema)
        if atoms:
            return atoms
    except WrongSchemaError:
        raise
    except json.JSONDecodeError:
        pass

    # Strategy 2: json_repair library handles broken/truncated/conversational JSON
    try:
        parsed = repair_json(raw_text)
        if parsed:
            if isinstance(parsed, dict) and not _has_expected_key(parsed):
                actual_keys = list(parsed.keys())
                logger.warning(f"[Distillery] Schema mismatch after repair: expected {required_keys}, got {actual_keys}")
                raise WrongSchemaError(f"Wrong schema after repair: expected {required_keys}, got {actual_keys}")
            atoms = _normalize_atom_list(parsed, expected_schema=expected_schema)
            if atoms:
                return atoms
    except WrongSchemaError:
        raise
    except Exception as e:
        logger.warning(f"[Distillery] repair_json failed: {e}")

    # NO LINE PARSING FALLBACK — fail fast, don't corrupt the pipeline
    logger.warning(f"[Distillery] ALL JSON extraction failed for {len(raw_text)}-char response")
    return []


def _normalize_atom_list(parsed: Any, expected_schema: str = 'atoms') -> List[Dict[str, Any]]:
    """
    Normalize various JSON structures into a list of atom dicts.
    Handles: {"atoms": [...]}, {"facts": [...]}, bare [...], nested objects, etc.
    
    expected_schema: 'atoms' → look for atoms key, 'critique' → look for Critique key
    """
    if not isinstance(parsed, dict) and not isinstance(parsed, list):
        return []

    # Unwrap top-level dict to find the array
    if isinstance(parsed, dict):
        # First try the expected schema key
        schema_keys = {'atoms': ['atoms', 'facts', 'items', 'results', 'data'],
                       'critique': ['critique', 'reviews', 'evaluations', 'analysis']}
        key_candidates = schema_keys.get(expected_schema, ['atoms', 'facts', 'items'])
        
        raw_items = None
        for key in key_candidates:
            if key in parsed and isinstance(parsed[key], list):
                raw_items = parsed[key]
                break
        
        if raw_items is None:
            # No known key — try first list value found
            for v in parsed.values():
                if isinstance(v, list):
                    raw_items = v
                    break
            else:
                return []
    else:
        raw_items = parsed

    atoms = []
    for item in raw_items:
        try:
            if expected_schema == 'critique':
                # Critique items have: index, valid, reason, fix — not content
                atom = _normalize_critique_item(item)
            else:
                atom = _normalize_single_atom(item)
            if atom:
                atoms.append(atom)
        except (KeyError, TypeError, ValueError) as e:
            # Skip malformed atoms but log the error
            logger.debug(f"[Distillery] Skipping malformed atom: {e}")
            continue

    return atoms


def _normalize_critique_item(item: Any) -> Optional[Dict[str, Any]]:
    """Normalize a critique item into a valid dict with index, valid, reason, fix."""
    if not isinstance(item, dict):
        return None

    index = item.get('index', 0)
    valid = item.get('valid', False)

    # Must have at least index and valid fields
    if not isinstance(index, int) or index < 1:
        return None
    if not isinstance(valid, bool):
        return None

    result = {
        'index': index,
        'valid': valid,
    }

    reason = item.get('reason', '')
    if reason and isinstance(reason, str):
        result['reason'] = reason

    fix = item.get('fix')
    if fix and isinstance(fix, str):
        result['fix'] = fix

    return result


def _normalize_single_atom(item: Any) -> Optional[Dict[str, Any]]:
    """Convert a single item into a valid atom dict. Returns None if unusable."""
    if isinstance(item, dict):
        content = item.get('content', item.get('fact', item.get('text', item.get('statement', ''))))
        if not content or not isinstance(content, str):
            return None

        content = content.strip()
        
        # Quality gate 1: minimum length
        if len(content) < 30:
            return None  # Too short — skip silently

        # Quality gate 2: must end with proper sentence/phrase termination
        # Only accept real terminators — not 's' or '%' which match too many fragments
        _complete_endings = {'.', '!', '?'}
        _acceptable_closers = {')', ']', '"', '>', '°', '%'}  # acceptable after content
        has_complete_ending = any(content.endswith(e) for e in _complete_endings)
        has_acceptable_closer = any(content.endswith(e) for e in _acceptable_closers)
        
        if not has_complete_ending and not has_acceptable_closer:
            return None  # No proper termination — likely truncated
        
        # If it ends with a closer but not a real terminator, be stricter about length
        # e.g., "62%" or "(36%)" — require it to be clearly a complete stat
        if has_acceptable_closer and not has_complete_ending:
            word_count = len(content.split())
            if word_count < 6:
                return None  # Short fragment ending with % or ) — reject

        # Quality gate 3: reject pure URLs
        if content.startswith('http') and ' ' not in content[:100]:
            return None

        atom_type = str(item.get('type', 'claim')).lower().strip()
        valid_types = {"claim", "evidence", "event", "procedure", "contradiction"}
        if atom_type not in valid_types:
            atom_type = "claim"

        confidence = item.get('confidence', 0.6)
        try:
            confidence = float(confidence)
        except (ValueError, TypeError):
            confidence = 0.5

        return {
            "type": atom_type,
            "content": content,
            "confidence": confidence
        }

    elif isinstance(item, str) and len(item.strip()) >= 10:
        return {
            "type": "claim",
            "content": item.strip(),
            "confidence": 0.5
        }

    return None  # Not a usable atom


def _normalize_single_atom_fallback(item: Any) -> Optional[Dict[str, Any]]:
    """Relaxed normalization for fallback mode — shorter sentences allowed."""
    if not isinstance(item, dict):
        return None
    
    content = item.get('content', item.get('fact', item.get('text', item.get('statement', ''))))
    if not content or not isinstance(content, str):
        return None

    content = content.strip()
    
    # Relaxed gate: 20 chars minimum (vs 30 in strict mode)
    if len(content) < 20:
        return None

    # Still require some termination
    _endings = {'.', '!', '?', ')', ']', '"', '>', '%', '°'}
    if not any(content.endswith(e) for e in _endings):
        return None

    # Reject pure URLs
    if content.startswith('http') and ' ' not in content[:100]:
        return None

    atom_type = str(item.get('type', 'claim')).lower().strip()
    valid_types = {"claim", "evidence", "event", "procedure", "contradiction"}
    if atom_type not in valid_types:
        atom_type = "claim"

    confidence = item.get('confidence', 0.5)
    try:
        confidence = float(confidence)
    except (ValueError, TypeError):
        confidence = 0.5

    return {
        "type": atom_type,
        "content": content,
        "confidence": confidence
    }


def _parse_lines_fallback(text: str, valid_types: set) -> List[Dict[str, Any]]:
    """
    Last-resort line parser. Only reached when ALL JSON strategies fail.
    Logs a warning so the failure is visible, not silent.
    """
    atoms = []
    typed_pattern = re.compile(r'^[\s\-\*•]+\[(\w+)\]\s+(.+)$', re.MULTILINE)

    for match in typed_pattern.finditer(text):
        atom_type = match.group(1).strip().lower()
        content = match.group(2).strip()
        if atom_type not in valid_types:
            atom_type = "claim"
        if len(content) >= 10:
            atoms.append({
                "type": atom_type,
                "content": content,
                "confidence": 0.6
            })

    if atoms:
        return atoms

    # Untyped bullet lines
    bullet_pattern = re.compile(r'^[\s\-\*•]+\s+(.+)$', re.MULTILINE)
    for match in bullet_pattern.finditer(text):
        content = match.group(1).strip()
        if len(content) >= 10 and not content.startswith('#'):
            atoms.append({
                "type": "claim",
                "content": content,
                "confidence": 0.4
            })

    return atoms
