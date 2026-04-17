"""
Phase 08.2 Resilience Tests - Simplified

Tests for crawler retry behavior and text extraction.
Tests loop error logging separately.
"""
import unittest
from unittest.mock import patch, MagicMock
import requests
import time

# Import crawler functions directly
from src.research.archivist.crawler import extract_text, fetch_url


class TestExtractTextHeuristics(unittest.TestCase):
    """Test text extraction heuristics and filtering."""

    def test_line_11_chars_is_kept(self):
        """A line with 11 chars is kept (threshold is > 10)."""
        html = "<html><body><p>Short line.</p><p>This is a longer line with more words.</p></body></html>"
        result = extract_text(html)
        self.assertIn("Short line.", result)

    def test_line_9_chars_is_dropped(self):
        """A line with 9 chars is dropped (below 10-char threshold)."""
        html = "<html><body><p>123456789</p><p>This line is long enough to be included in results.</p></body></html>"
        result = extract_text(html)
        self.assertNotIn("123456789", result)

    def test_gov_html_extracts_over_300_chars(self):
        """A structured .gov-like HTML snippet extracts to > 300 chars."""
        gov_html = """
        <html>
        <head><title>NIH Almanac</title></head>
        <body>
        <main>
        <p>NIH's mission is to seek fundamental knowledge about the nature and behavior of living systems.</p>
        <p>NIH pursues that mission by supporting biomedical and behavioral research at universities and research institutions.</p>
        <p>NIH's mission is to seek fundamental knowledge about the nature and behavior of living systems.</p>
        <p>NIH pursues that mission by supporting biomedical and behavioral research at universities and research institutions.</p>
        <p>NIH's mission is to seek fundamental knowledge about the nature and behavior of living systems.</p>
        <p>NIH pursues that mission by supporting biomedical and behavioral research at universities and research institutions.</p>
        </main>
        </body>
        </html>
        """
        result = extract_text(gov_html)
        self.assertGreater(len(result), 300, f"Expected > 300 chars, got {len(result)}")

    def test_threshold_boundary_exactly_10_chars_dropped(self):
        """A line with exactly 10 chars is dropped (threshold is > 10)."""
        html = "<html><body><p>1234567890</p><p>This is a longer sentence that should be included.</p></body></html>"
        result = extract_text(html)
        self.assertNotIn("1234567890", result)

    def test_threshold_boundary_exactly_11_chars_kept(self):
        """A line with exactly 11 chars is kept (> 10)."""
        html = "<html><body><p>12345678901</p><p>This is a longer sentence that should be included.</p></body></html>"
        result = extract_text(html)
        self.assertIn("12345678901", result)


class TestCrawlerRetryBehavior(unittest.TestCase):
    """Test that fetch_url correctly retries on transient errors."""

    def _make_http_response(self, status_code, text="<html><body><p>Content here.</p></body></html>"):
        """Create a mock response."""
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

    def test_no_retry_on_http_404(self):
        """fetch_url should NOT retry on HTTP 404."""
        fail_resp = self._make_http_response(404)
        
        with patch('src.research.archivist.crawler.requests.post', side_effect=requests.exceptions.ConnectionError), \
             patch('src.research.archivist.crawler.requests.get', return_value=fail_resp) as mock_get, \
             patch('src.research.archivist.crawler.time.sleep'):
            
            result = fetch_url("http://example.com/notfound")

        self.assertEqual(mock_get.call_count, 1)
        self.assertIsNone(result)

    def test_retries_on_connection_error(self):
        """fetch_url should retry on ConnectionError."""
        ok_resp = self._make_http_response(200)
        
        with patch('src.research.archivist.crawler.requests.post', side_effect=requests.exceptions.ConnectionError), \
             patch('src.research.archivist.crawler.requests.get', side_effect=[
                   requests.exceptions.ConnectionError("conn refused"),
                   ok_resp
               ]) as mock_get, \
             patch('src.research.archivist.crawler.time.sleep') as mock_sleep:
            
            result = fetch_url("http://example.com/test")

        self.assertEqual(mock_get.call_count, 2)
        self.assertGreater(mock_sleep.call_count, 0)
        self.assertIsNotNone(result)
