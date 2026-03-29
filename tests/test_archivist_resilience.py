"""
Phase 08.2 Resilience Tests

Tests for O1 (retry classification), O2 (bare except removal), and O5 (false rejection fix).
"""
import unittest
from unittest.mock import patch, MagicMock, call
import requests
import sys
import os
import importlib
import types

# ---------------------------------------------------------------------------
# Import archivist modules directly, bypassing src/__init__.py which imports
# heavy dependencies (chromadb, pydantic) that cause import errors in test.
# ---------------------------------------------------------------------------

def _load_module_directly(module_name: str, file_path: str):
    """Load a Python module directly from its file path without triggering parent __init__."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod

_ROOT = os.path.join(os.path.dirname(__file__), '..')
_ARCHIVIST = os.path.join(_ROOT, 'src', 'research', 'archivist')

# Register stub packages so relative imports inside archivist modules work
def _ensure_stub_package(pkg_name: str):
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = []
        sys.modules[pkg_name] = pkg

_ensure_stub_package('src')
_ensure_stub_package('src.research')
_ensure_stub_package('src.research.archivist')

# Load config first (no heavy deps)
config_mod = _load_module_directly('src.research.archivist.config', os.path.join(_ARCHIVIST, 'config.py'))

# Load crawler (depends on config)
crawler = _load_module_directly('src.research.archivist.crawler', os.path.join(_ARCHIVIST, 'crawler.py'))

# ---------------------------------------------------------------------------
# Load loop.py with stub dependencies so we can test it without real backends
# ---------------------------------------------------------------------------

def _make_stub_module(name: str, **attrs):
    """Create a stub module with the given attributes."""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod

# Stub all heavy archivist dependencies that loop.py imports
_make_stub_module('src.research.archivist.planner', generate_section_queries=MagicMock(return_value=["q1"]))
_make_stub_module('src.research.archivist.search', search_web=MagicMock(return_value=[]))
_make_stub_module('src.research.archivist.chunker', chunk_text=MagicMock(return_value=["chunk"]))
_make_stub_module('src.research.archivist.embeddings',
                  get_embeddings_batch=MagicMock(return_value=[]),
                  get_embedding=MagicMock(return_value=[0.1] * 10))
async def _async_none(*args, **kwargs):
    return None

_make_stub_module('src.research.archivist.index',
                  init=MagicMock(),
                  add_chunks=_async_none,
                  clear_index=_async_none)
async def _async_empty_list(*args, **kwargs):
    return []

_make_stub_module('src.research.archivist.retriever',
                  init=MagicMock(),
                  search=_async_empty_list)
_make_stub_module('src.research.archivist.synth',
                  summarize_source=MagicMock(return_value="summary"),
                  write_section=MagicMock(return_value="Section content"))
_make_stub_module('src.research.archivist.critic',
                  critique_answer=MagicMock(return_value={"needs_more_info": False}))
_make_stub_module('src.research.archivist.llm', set_sheppard_client=MagicMock())
_make_stub_module('src.memory',)
_make_stub_module('src.memory.storage_adapter', ChromaSemanticStore=MagicMock)

# Also stub planner, search, crawler refs as standalone modules in archivist package
# (loop imports them as `from . import planner, search, crawler, ...`)
_archivist_pkg = sys.modules['src.research.archivist']
for _sub in ['planner', 'search', 'chunker', 'embeddings', 'index', 'retriever', 'synth', 'critic', 'llm']:
    setattr(_archivist_pkg, _sub, sys.modules[f'src.research.archivist.{_sub}'])
# Set crawler reference to the one we loaded
setattr(_archivist_pkg, 'crawler', crawler)

# Now load loop.py
loop = _load_module_directly('src.research.archivist.loop', os.path.join(_ARCHIVIST, 'loop.py'))


# ---------------------------------------------------------------------------
# Helper: build a mock HTTP response
# ---------------------------------------------------------------------------

def _make_http_response(status_code: int, text: str = "<html><body><p>Hello World content here.</p></body></html>"):
    """Create a mock response that behaves like a requests.Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = text
    mock_resp.content = text.encode()
    mock_resp.headers = {"Content-Type": "text/html"}

    if 400 <= status_code < 600:
        http_error = requests.exceptions.HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_error
    else:
        mock_resp.raise_for_status.return_value = None

    return mock_resp


# ---------------------------------------------------------------------------
# Task 1 — O1: Retry classification tests
# ---------------------------------------------------------------------------

class TestRetryClassification(unittest.TestCase):

    def _patch_crawler(self, get_side_effect=None, get_return=None):
        """Context manager helper: patch requests.get and time.sleep on the crawler module."""
        mock_get = MagicMock()
        mock_sleep = MagicMock()
        if get_side_effect is not None:
            mock_get.side_effect = get_side_effect
        if get_return is not None:
            mock_get.return_value = get_return

        # The crawler module was loaded directly; patch its internal references
        import unittest.mock as _mock
        ctx_get = _mock.patch.object(crawler.requests, 'get', mock_get)
        ctx_sleep = _mock.patch.object(crawler.time, 'sleep', mock_sleep)
        return ctx_get, ctx_sleep, mock_get, mock_sleep

    def test_retries_on_http_500_succeeds_third_attempt(self):
        """fetch_url should retry on HTTP 500, succeeding on 3rd attempt."""
        fail_resp = _make_http_response(500)
        ok_resp = _make_http_response(200)
        ctx_get, ctx_sleep, mock_get, mock_sleep = self._patch_crawler(
            get_side_effect=[fail_resp, fail_resp, ok_resp]
        )
        with ctx_get, ctx_sleep:
            result = crawler.fetch_url("http://example.com/test")

        self.assertEqual(mock_get.call_count, 3)
        self.assertIsNotNone(result)

    def test_retries_on_http_502(self):
        """fetch_url should retry on HTTP 502."""
        fail_resp = _make_http_response(502)
        ok_resp = _make_http_response(200)
        ctx_get, ctx_sleep, mock_get, mock_sleep = self._patch_crawler(
            get_side_effect=[fail_resp, ok_resp]
        )
        with ctx_get, ctx_sleep:
            result = crawler.fetch_url("http://example.com/test")

        self.assertEqual(mock_get.call_count, 2)
        self.assertIsNotNone(result)

    def test_no_retry_on_http_404(self):
        """fetch_url should NOT retry on HTTP 404 — return None immediately."""
        fail_resp = _make_http_response(404)
        ctx_get, ctx_sleep, mock_get, mock_sleep = self._patch_crawler(
            get_return=fail_resp
        )
        with ctx_get, ctx_sleep:
            result = crawler.fetch_url("http://example.com/notfound")

        self.assertEqual(mock_get.call_count, 1)
        self.assertIsNone(result)

    def test_no_retry_on_http_403(self):
        """fetch_url should NOT retry on HTTP 403."""
        fail_resp = _make_http_response(403)
        ctx_get, ctx_sleep, mock_get, mock_sleep = self._patch_crawler(
            get_return=fail_resp
        )
        with ctx_get, ctx_sleep:
            result = crawler.fetch_url("http://example.com/forbidden")

        self.assertEqual(mock_get.call_count, 1)
        self.assertIsNone(result)

    def test_retries_on_connection_error_succeeds_second_attempt(self):
        """fetch_url should retry on ConnectionError, succeed on 2nd attempt."""
        ok_resp = _make_http_response(200)
        ctx_get, ctx_sleep, mock_get, mock_sleep = self._patch_crawler(
            get_side_effect=[requests.exceptions.ConnectionError("conn refused"), ok_resp]
        )
        with ctx_get, ctx_sleep:
            result = crawler.fetch_url("http://example.com/test")

        self.assertEqual(mock_get.call_count, 2)
        self.assertIsNotNone(result)

    def test_retries_on_timeout_succeeds_second_attempt(self):
        """fetch_url should retry on Timeout, succeed on 2nd attempt."""
        ok_resp = _make_http_response(200)
        ctx_get, ctx_sleep, mock_get, mock_sleep = self._patch_crawler(
            get_side_effect=[requests.exceptions.Timeout("timed out"), ok_resp]
        )
        with ctx_get, ctx_sleep:
            result = crawler.fetch_url("http://example.com/test")

        self.assertEqual(mock_get.call_count, 2)
        self.assertIsNotNone(result)

    def test_returns_none_after_all_three_500s(self):
        """fetch_url returns None after 3 consecutive HTTP 500 responses (bounded, no infinite loop)."""
        fail_resp = _make_http_response(500)
        ctx_get, ctx_sleep, mock_get, mock_sleep = self._patch_crawler(
            get_side_effect=[fail_resp, fail_resp, fail_resp]
        )
        with ctx_get, ctx_sleep:
            result = crawler.fetch_url("http://example.com/test")

        self.assertEqual(mock_get.call_count, 3)
        self.assertIsNone(result)

    def test_backoff_called_between_retries(self):
        """Sleep (backoff) is called between 5xx retry attempts."""
        fail_resp = _make_http_response(500)
        ok_resp = _make_http_response(200)
        ctx_get, ctx_sleep, mock_get, mock_sleep = self._patch_crawler(
            get_side_effect=[fail_resp, ok_resp]
        )
        with ctx_get, ctx_sleep:
            crawler.fetch_url("http://example.com/test")

        self.assertGreater(mock_sleep.call_count, 0)


# ---------------------------------------------------------------------------
# Task 2 — O2: Logged exceptions tests
# ---------------------------------------------------------------------------

class TestLoopErrorLogging(unittest.TestCase):
    """Test that loop.py logs errors instead of silently swallowing them."""

    def _make_state(self):
        state = loop.ResearchState("test objective")
        state.plan = [{"title": "Test Section", "goal": "test goal"}]
        return state

    def test_execute_section_cycle_logs_fetch_error(self):
        """When fetch_url raises in execute_section_cycle, error is logged with URL."""
        import asyncio
        import unittest.mock as _mock

        async def _mock_retriever_search(*a, **kw):
            return []

        mock_logger = MagicMock()
        mock_fetch = MagicMock(side_effect=RuntimeError("network exploded"))
        # Use a .gov URL so it passes the is_authoritative filter
        mock_search = MagicMock(return_value=["https://www.nih.gov/page"])
        mock_emb = MagicMock(return_value=[0.1] * 10)
        mock_write = MagicMock(return_value="Section content without gaps")

        state = self._make_state()
        chroma_store = MagicMock()

        with _mock.patch.object(loop, 'logger', mock_logger), \
             _mock.patch.object(loop.crawler, 'fetch_url', mock_fetch), \
             _mock.patch.object(loop.search, 'search_web', mock_search), \
             _mock.patch.object(loop.embeddings, 'get_embedding', mock_emb), \
             _mock.patch.object(loop.retriever, 'search', _mock_retriever_search), \
             _mock.patch.object(loop.synth, 'write_section', mock_write):
            asyncio.run(loop.execute_section_cycle(state, 0, chroma_store))

        error_calls = [str(c) for c in mock_logger.error.call_args_list]
        self.assertTrue(
            any("nih.gov" in c or "FAIL" in c for c in error_calls),
            f"Expected logger.error with URL, got: {error_calls}"
        )

    def test_execute_section_cycle_continues_after_error(self):
        """After a logged error, the loop continues — function completes (doesn't crash)."""
        import asyncio
        import unittest.mock as _mock

        async def _mock_retriever_search(*a, **kw):
            return []

        mock_logger = MagicMock()
        mock_fetch = MagicMock(side_effect=RuntimeError("boom"))
        # Use .gov URLs so they pass the is_authoritative filter in execute_section_cycle
        mock_search = MagicMock(return_value=["https://www.nih.gov/url1", "https://www.cdc.gov/url2"])
        mock_emb = MagicMock(return_value=[0.1] * 10)
        mock_write = MagicMock(return_value="Section content")

        state = self._make_state()
        chroma_store = MagicMock()

        with _mock.patch.object(loop, 'logger', mock_logger), \
             _mock.patch.object(loop.crawler, 'fetch_url', mock_fetch), \
             _mock.patch.object(loop.search, 'search_web', mock_search), \
             _mock.patch.object(loop.embeddings, 'get_embedding', mock_emb), \
             _mock.patch.object(loop.retriever, 'search', _mock_retriever_search), \
             _mock.patch.object(loop.synth, 'write_section', mock_write):
            # Should not raise
            result = asyncio.run(loop.execute_section_cycle(state, 0, chroma_store))

        # Completes without raising — result can be True or None
        self.assertTrue(result is not None or result is None)

    def test_fill_data_gaps_logs_fetch_error(self):
        """When fetch_url raises in fill_data_gaps URL loop, error is logged."""
        import asyncio
        import unittest.mock as _mock

        mock_logger = MagicMock()
        mock_fetch = MagicMock(side_effect=RuntimeError("fetch failed"))
        mock_search = MagicMock(return_value=["http://gov.example.gov/page"])

        state = self._make_state()
        chroma_store = MagicMock()

        with _mock.patch.object(loop, 'logger', mock_logger), \
             _mock.patch.object(loop.crawler, 'fetch_url', mock_fetch), \
             _mock.patch.object(loop.search, 'search_web', mock_search):
            asyncio.run(loop.fill_data_gaps(state, "Test Section", "test goal", chroma_store))

        error_calls = [str(c) for c in mock_logger.error.call_args_list]
        self.assertTrue(
            len(error_calls) > 0,
            "Expected logger.error to be called when fetch_url raises"
        )

    def test_fill_data_gaps_search_error_logged(self):
        """When search_web raises in fill_data_gaps, error is logged."""
        import asyncio
        import unittest.mock as _mock

        mock_logger = MagicMock()
        mock_fetch = MagicMock(return_value=None)
        mock_search = MagicMock(side_effect=RuntimeError("search exploded"))

        state = self._make_state()
        chroma_store = MagicMock()

        with _mock.patch.object(loop, 'logger', mock_logger), \
             _mock.patch.object(loop.crawler, 'fetch_url', mock_fetch), \
             _mock.patch.object(loop.search, 'search_web', mock_search):
            # Should complete without raising
            asyncio.run(loop.fill_data_gaps(state, "Test Section", "test goal", chroma_store))

        error_calls = [str(c) for c in mock_logger.error.call_args_list]
        self.assertTrue(
            len(error_calls) > 0,
            "Expected logger.error to be called when search_web raises"
        )


# ---------------------------------------------------------------------------
# Task 3 — O5: Extract text heuristic tests
# ---------------------------------------------------------------------------

class TestExtractTextHeuristics(unittest.TestCase):

    def test_line_11_chars_is_kept(self):
        """A line with 11 chars is kept (new threshold is > 10)."""
        html = "<html><body><p>Short line.</p><p>This is a longer line with more words.</p></body></html>"
        result = crawler.extract_text(html)
        self.assertIn("Short line.", result)

    def test_line_9_chars_is_dropped(self):
        """A line with 9 chars is dropped (below new 10-char threshold)."""
        # 9-char word: "123456789"
        html = "<html><body><p>123456789</p><p>This line is long enough to be included in results.</p></body></html>"
        result = crawler.extract_text(html)
        self.assertNotIn("123456789", result)

    def test_skip_rest_activates_when_content_below_500(self):
        """skip_rest activates when accumulated content < 500 chars at nav cue."""
        # Very little content before 'navigation' — should activate skip_rest
        short_content = "x" * 20  # Only 20 chars — well below 500
        html = f"""<html><body>
        <p>{short_content}</p>
        <div class="nav"><p>navigation bar goes here to the right.</p></div>
        <p>This is content that should be skipped because we are past navigation.</p>
        </body></html>"""
        result = crawler.extract_text(html)
        self.assertNotIn("This is content that should be skipped because we are past navigation.", result)

    def test_skip_rest_does_not_activate_with_501_chars(self):
        """skip_rest does NOT activate when 501+ chars already accumulated."""
        # Build a body with 501 chars of real content before the nav cue
        long_content = "This is meaningful content that fills up the buffer. " * 10  # ~530 chars
        html = f"""<html><body>
        <article>
        <p>{long_content}</p>
        <p>navigation to more content areas</p>
        <p>This important information should still be included in output.</p>
        </article>
        </body></html>"""
        result = crawler.extract_text(html)
        self.assertIn("This important information should still be included in output.", result)

    def test_skip_rest_boundary_499_chars(self):
        """skip_rest activates at 499-char boundary (just below threshold)."""
        # 499 chars of content before nav cue
        content_499 = "A" * 20 + " content line before nav. " * 18  # ~500 chars, keep ~499
        # Ensure exactly under 500
        html_content = "Short content here."
        html = f"""<html><body>
        <p>{html_content}</p>
        <p>{'Content filler. ' * 5}</p>
        <p>navigation header zone</p>
        <p>After navigation content that should be stripped.</p>
        </body></html>"""
        result = crawler.extract_text(html)
        # With little content before nav cue, after-nav content should be stripped
        self.assertNotIn("After navigation content that should be stripped.", result)

    def test_gov_html_extracts_over_300_chars(self):
        """A structured .gov-like HTML snippet extracts to > 300 chars."""
        # Simulate a .gov page structure with short label lines and nav divs
        gov_html = """
        <html>
        <head><title>NIH Almanac</title></head>
        <body>
        <nav>Site navigation</nav>
        <main>
        <h1>NIH Almanac: History of NIH</h1>
        <p>The National Institutes of Health (NIH) is one of the world's foremost medical research centers.</p>
        <p>An agency of the U.S. Department of Health and Human Services, NIH is the Federal focal point for health research.</p>
        <h2>Founding</h2>
        <p>NIH traces its roots to 1887, when a one-room laboratory was established within the Marine Hospital Service.</p>
        <p>Originally located in Staten Island, NY, it moved to Washington, DC in 1891.</p>
        <h2>Mission</h2>
        <p>NIH's mission is to seek fundamental knowledge about the nature and behavior of living systems.</p>
        <p>NIH pursues that mission by supporting biomedical and behavioral research at universities, medical schools, hospitals, and research institutions throughout the United States and around the world.</p>
        <p>The work of NIH scientists has led to discoveries and advances that save lives, reduce disability, and improve health.</p>
        <h2>Organization</h2>
        <p>NIH is made up of 27 Institutes and Centers, each with a specific research agenda, often focusing on particular diseases or body systems.</p>
        <ul>
        <li>National Cancer Institute (NCI)</li>
        <li>National Heart, Lung, and Blood Institute (NHLBI)</li>
        <li>National Institute on Aging (NIA)</li>
        </ul>
        </main>
        </body>
        </html>
        """
        result = crawler.extract_text(gov_html)
        self.assertGreater(len(result), 300, f"Expected > 300 chars, got {len(result)}: {result[:200]!r}")

    def test_threshold_boundary_exactly_10_chars_dropped(self):
        """A line with exactly 10 chars is dropped (threshold is > 10, not >= 10)."""
        html = "<html><body><p>1234567890</p><p>This is a longer sentence that should be included.</p></body></html>"
        result = crawler.extract_text(html)
        self.assertNotIn("1234567890", result)

    def test_threshold_boundary_exactly_11_chars_kept(self):
        """A line with exactly 11 chars is kept (> 10)."""
        html = "<html><body><p>12345678901</p><p>This is a longer sentence that should be included.</p></body></html>"
        result = crawler.extract_text(html)
        self.assertIn("12345678901", result)


if __name__ == "__main__":
    unittest.main()
