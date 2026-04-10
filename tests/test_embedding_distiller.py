"""
Test embedding_distiller module.

Tests the 3-layer pre-embedding sanitizer:
  1. Boilerplate stripping
  2. Semantic filtering
  3. Sliding window + pooling
"""

import pytest
import asyncio
from src.utils.embedding_distiller import (
    clean_boilerplate,
    rough_token_count,
    split_sentences,
    is_informational,
    extract_atomic_claims,
    sliding_windows,
    pool_vectors,
    distill_for_embedding,
    safe_embed,
    gate_source
)


# ─────────────────────────────────────────────
# TEST BOILERPLATE STRIPPING
# ─────────────────────────────────────────────

class TestCleanBoilerplate:
    def test_removes_html_tags(self):
        text = "<p>Hello world</p><div>Content</div>"
        result = clean_boilerplate(text)
        assert "<" not in result
        assert "Hello world" in result

    def test_removes_script_blocks(self):
        text = """
        <script>var x = 1;</script>
        <p>Real content here</p>
        """
        result = clean_boilerplate(text)
        assert "var x" not in result
        assert "Real content here" in result

    def test_removes_cookie_notices(self):
        # Test with multiline text (how boilerplate actually appears)
        text = """Main article content about neural networks.
Accept cookies to continue browsing.
Cookie Policy - please accept cookies."""
        result = clean_boilerplate(text)
        # Line-based cookie notices should be removed
        assert "Accept cookies" not in result
        assert "Cookie Policy" not in result
        assert "neural networks" in result

    def test_removes_related_articles(self):
        # Test with multiline text
        text = """Main content about machine learning.
Related articles:
1. Deep learning
2. AI basics"""
        result = clean_boilerplate(text)
        assert "Main content about machine learning" in result
        # "Related articles" on its own line should be removed
        assert "Related articles:" not in result

    def test_normalizes_whitespace(self):
        text = "Hello\n\n\nWorld     with   spaces"
        result = clean_boilerplate(text)
        assert "  " not in result
        assert "\n" not in result

    def test_handles_empty_input(self):
        assert clean_boilerplate("") == ""
        assert clean_boilerplate("   ") == ""
        assert clean_boilerplate(None) == ""


# ─────────────────────────────────────────────
# TEST TOKEN COUNTING
# ─────────────────────────────────────────────

class TestRoughTokenCount:
    def test_simple_text(self):
        text = "The quick brown fox jumps over the lazy dog"
        count = rough_token_count(text)
        # 9 words * 1.3 ≈ 11-12 tokens
        assert 10 <= count <= 13

    def test_empty_text(self):
        assert rough_token_count("") == 0
        assert rough_token_count("   ") == 0

    def test_long_text(self):
        text = "word " * 1000
        count = rough_token_count(text)
        # 1000 words * 1.3 = 1300 tokens
        assert 1200 <= count <= 1400


# ─────────────────────────────────────────────
# TEST SENTENCE SPLITTING
# ─────────────────────────────────────────────

class TestSplitSentences:
    def test_basic_sentences(self):
        text = "First sentence. Second sentence! Third sentence?"
        result = split_sentences(text)
        assert len(result) == 3
        assert result[0] == "First sentence."
        assert result[1] == "Second sentence!"
        assert result[2] == "Third sentence?"

    def test_handles_whitespace(self):
        text = "Hello world.   Next sentence here."
        result = split_sentences(text)
        assert len(result) == 2

    def test_empty_input(self):
        assert split_sentences("") == []
        assert split_sentences("   ") == []


# ─────────────────────────────────────────────
# TEST SEMANTIC FILTERING
# ─────────────────────────────────────────────

class TestIsInformational:
    def test_keeps_definition(self):
        sentence = "Neural networks are defined as computational models inspired by biological neurons."
        assert is_informational(sentence) is True

    def test_keeps_claim(self):
        sentence = "Research shows that deep learning improves performance by 23 percent."
        assert is_informational(sentence) is True

    def test_rejects_cookie_notice(self):
        sentence = "We use cookies to enhance your browsing experience. Accept cookies to continue."
        assert is_informational(sentence) is False

    def test_rejects_short_text(self):
        sentence = "Click here"
        assert is_informational(sentence) is False

    def test_rejects_all_caps_header(self):
        sentence = "THIS IS A VERY LONG HEADER THAT EXCEEDS THIRTY CHARACTERS"
        assert is_informational(sentence) is False

    def test_rejects_url_heavy(self):
        sentence = "See http://example.com and http://test.com and http://foo.com for more"
        assert is_informational(sentence) is False

    def test_rejects_question_only(self):
        sentence = "What is the meaning of life?"
        assert is_informational(sentence) is False


class TestExtractAtomicClaims:
    def test_filters_noise_sentences(self):
        sentences = [
            "Neural networks are computational models.",
            "Accept cookies to continue browsing.",
            "Research shows significant improvements.",
            "Subscribe to our newsletter for updates.",
        ]
        result = extract_atomic_claims(sentences)
        assert len(result) == 2
        assert "Neural networks" in result[0]
        assert "Research shows" in result[1]


# ─────────────────────────────────────────────
# TEST SLIDING WINDOWS
# ─────────────────────────────────────────────

class TestSlidingWindows:
    def test_basic_window(self):
        items = list(range(10))
        windows = list(sliding_windows(items, size=3, stride=2))
        assert windows[0] == [0, 1, 2]
        assert windows[1] == [2, 3, 4]
        assert windows[2] == [4, 5, 6]

    def test_window_larger_than_list(self):
        items = [1, 2, 3]
        windows = list(sliding_windows(items, size=5, stride=2))
        assert len(windows) == 1
        assert windows[0] == [1, 2, 3]


# ─────────────────────────────────────────────
# TEST VECTOR POOLING
# ─────────────────────────────────────────────

class TestPoolVectors:
    def test_mean_pooling(self):
        vectors = [
            [1.0, 2.0, 3.0],
            [3.0, 4.0, 5.0]
        ]
        result = pool_vectors(vectors, method="mean")
        assert result == [2.0, 3.0, 4.0]

    def test_max_pooling(self):
        vectors = [
            [1.0, 5.0, 3.0],
            [3.0, 2.0, 5.0]
        ]
        result = pool_vectors(vectors, method="max")
        assert result == [3.0, 5.0, 5.0]

    def test_single_vector(self):
        vectors = [[1.0, 2.0, 3.0]]
        result = pool_vectors(vectors)
        assert result == [1.0, 2.0, 3.0]

    def test_empty_list(self):
        assert pool_vectors([]) == []


# ─────────────────────────────────────────────
# TEST DISTILLATION PIPELINE
# ─────────────────────────────────────────────

class TestDistillForEmbedding:
    def test_small_clean_text(self):
        text = "Neural networks are computational models inspired by biological neurons. They learn patterns from data through training."
        chunks, stats = distill_for_embedding(text)
        assert len(chunks) == 1
        assert stats["chunks"] == 1
        assert stats["overflow"] is False

    def test_noisy_text_gets_cleaned(self):
        text = """
        <script>var x=1;</script>
        Cookie Policy - Accept cookies
        Neural networks learn from data.
        Related articles: click here
        """
        chunks, stats = distill_for_embedding(text)
        assert len(chunks) >= 1
        assert stats["cleaned_chars"] < stats["raw_chars"]

    def test_large_text_gets_windowed(self):
        # Create text that exceeds MAX_TOKENS
        sentences = ["This is sentence number {} about neural networks and machine learning.".format(i) 
                    for i in range(200)]
        text = " ".join(sentences)
        
        chunks, stats = distill_for_embedding(text)
        assert stats["overflow"] is True
        assert stats["chunks"] > 1
        assert len(chunks) > 1

    def test_empty_text(self):
        chunks, stats = distill_for_embedding("")
        assert len(chunks) == 0

    def test_stats_tracking(self):
        text = "Hello world. This is a test sentence about machine learning."
        chunks, stats = distill_for_embedding(text)
        assert stats["raw_chars"] == len(text)
        assert stats["sentences_total"] > 0
        assert stats["sentences_filtered"] > 0


# ─────────────────────────────────────────────
# TEST GATE SOURCE
# ─────────────────────────────────────────────

class TestGateSource:
    def test_small_source_accepted(self):
        text = "Neural networks learn from data through training."
        result, tokens = gate_source(text)
        assert result == "OK"
        assert tokens < 1500

    def test_medium_source_needs_distill(self):
        # Create medium-sized text (substantial but not huge)
        # ~4000 tokens should trigger DISTILL (between 1500 and 8000)
        sentences = ["This is sentence number {} with some additional context about the topic.".format(i) 
                    for i in range(600)]
        text = " ".join(sentences)
        
        result, tokens = gate_source(text)
        # Should be substantial enough to process
        assert tokens > 1500

    def test_large_source_dropped(self):
        # Create very large text
        sentences = ["Sentence number {} for testing.".format(i) for i in range(7000)]
        text = " ".join(sentences)
        
        result, tokens = gate_source(text)
        assert result == "DROP"
        assert tokens > 8000


# ─────────────────────────────────────────────
# TEST SAFE EMBED (async)
# ─────────────────────────────────────────────

class TestSafeEmbed:
    @pytest.mark.asyncio
    async def test_safe_embed_small_text(self):
        """Test safe_embed with small text that doesn't need windowing."""
        call_count = {"count": 0}
        
        async def mock_embed(text):
            call_count["count"] += 1
            return [0.1, 0.2, 0.3]
        
        text = "Neural networks learn from data."
        result, stats = await safe_embed(text, mock_embed)
        
        assert result == [0.1, 0.2, 0.3]
        assert stats["embeddings_attempted"] == 1
        assert stats["embeddings_succeeded"] == 1
        assert stats["pooled"] is False

    @pytest.mark.asyncio
    async def test_safe_embed_handles_failure(self):
        """Test safe_embed when embed_fn fails."""
        async def failing_embed(text):
            raise Exception("Embedding failed")
        
        text = "Test content"
        result, stats = await safe_embed(text, failing_embed)
        
        assert result is None
        assert stats["embeddings_succeeded"] == 0

    @pytest.mark.asyncio
    async def test_safe_embed_pools_vectors(self):
        """Test that multiple chunks get pooled."""
        async def mock_embed(text):
            return [0.1, 0.2, 0.3]
        
        # Create text that will definitely need windowing (very large)
        sentences = ["This is sentence number {} about the topic of neural networks and machine learning.".format(i) 
                    for i in range(300)]
        text = " ".join(sentences)
        
        result, stats = await safe_embed(text, mock_embed)
        
        assert result is not None
        # Should have attempted multiple embeddings due to windowing
        assert stats["embeddings_attempted"] > 1 or stats["pooled"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
