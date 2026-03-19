import requests
from bs4 import BeautifulSoup
from .config import USER_AGENT
import io
import pypdf
import os

def fetch_url(url: str, browser_manager=None) -> str:
    """
    Fetches the content of a URL using local Firecrawl or fallback requests.
    Returns the extracted text.
    """
    # Try Firecrawl first for high-quality extraction
    firecrawl_url = os.getenv('FIRECRAWL_BASE_URL', 'http://localhost:3002')
    
    # Skip Firecrawl for PDFs as it might not handle them as well as pypdf locally
    if not url.lower().endswith('.pdf'):
        try:
            response = requests.post(
                f"{firecrawl_url}/v1/scrape",
                json={
                    "url": url,
                    "formats": ["markdown"],
                    "onlyMainContent": True,
                    "waitFor": 2000
                },
                timeout=60
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and 'data' in data:
                    return data['data'].get('markdown', '')
                elif 'markdown' in data: # Direct response
                    return data['markdown']
        except Exception as e:
            print(f"Firecrawl failed for {url}, falling back: {e}")

    # Approach 2: Try Sheppard's BrowserManager (Playwright) if available
    if browser_manager:
        try:
            import asyncio
            result = asyncio.run(browser_manager.gather_content(url))
            if result and result.get('results'):
                # BrowserManager.gather_content returns a list of snippets usually for searches,
                # but if we used it for a single URL it might behave differently.
                # Let's check for a more direct 'browse' method if it exists.
                pass
        except:
            pass

    # Fallback to manual requests
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()
        
        # Check if it's a PDF
        content_type = response.headers.get('Content-Type', '').lower()
        if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
            try:
                pdf_file = io.BytesIO(response.content)
                reader = pypdf.PdfReader(pdf_file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                return text
            except Exception as pdf_err:
                print(f"Error parsing PDF {url}: {pdf_err}")
                return None
                
        return extract_text(response.text)
    except Exception as e:
        return None

def extract_text(html: str) -> str:
    """
    Extracts visible text from HTML content, cleaning up scripts and styles.
    """
    if not html:
        return ""
        
    soup = BeautifulSoup(html, "html.parser")
    
    for tag in soup(["script", "style", "nav", "footer", "iframe", "noscript", "header", "aside", "form", "button", "label", "svg"]):
        tag.decompose()
        
    main_content = soup.find('main') or soup.find('article') or soup.find('div', id='content') or soup.find('div', class_='content') or soup
    text = main_content.get_text(separator="\n")
    
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    cleaned_text = '\n'.join(chunk for chunk in chunks if len(chunk) > 20)
    
    junk_lines = ["log in", "sign up", "privacy policy", "cookie policy", "subscribe", "related articles", "follow us on", "more from", "recommended for you", "read more", "terms of service", "accessibility"]
    filtered_lines = []
    skip_rest = False
    for line in cleaned_text.split('\n'):
        l_lower = line.lower()
        if any(j in l_lower for j in ["related topics", "most read", "editors' picks", "footer", "sidebar", "navigation"]):
            skip_rest = True
        if skip_rest: continue
        
        if len(line.split()) < 5 and any(j in l_lower for j in junk_lines):
            continue
        filtered_lines.append(line)
    
    return '\n'.join(filtered_lines)
