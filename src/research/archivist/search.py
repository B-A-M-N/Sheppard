import warnings
import os
import logging
import requests
warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

def search_web(query: str, max_results: int = 5):
    """
    Search the web using SearXNG.
    """
    results = []
    searxng_url = os.getenv('SEARXNG_ENDPOINT', 'http://localhost:8080')

    try:
        # Use SearXNG
        response = requests.get(
            f"{searxng_url}/search",
            params={'q': query, 'format': 'json'},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        for res in data.get('results', [])[:max_results]:
            if res.get('url'):
                results.append(res['url'])

    except Exception as e:
        logger.warning(f"SearXNG search failed: {e}")
        # Fallback to DDG if needed, but for now we prefer local
        pass

    return results
