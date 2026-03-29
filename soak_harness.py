"""
Soak Harness — Phase SOAK
Instruments the fetch → normalize → chunk path without triggering the broken
pydantic/chromadb dependency chain.

Captures:
  - Retry behavior per URL
  - Chunk count stability
  - Validation rejection reasons
  - Normalization determinism (hash comparison across 2 runs)
  - Failure classification

Produces: .planning/gauntlet_phases/SOAK-RESULTS.md
"""

import sys, importlib.util, hashlib, time, json, os, traceback
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# ── Isolated module loader ──────────────────────────────────────────────────

def _load(dotted_path: str, file_path: str):
    """Load a module file directly, bypassing the broken src import chain."""
    if dotted_path in sys.modules:
        return sys.modules[dotted_path]
    spec = importlib.util.spec_from_file_location(dotted_path, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted_path] = mod
    spec.loader.exec_module(mod)
    return mod

BASE = Path(__file__).parent

# Fake out the package stubs so sub-imports don't explode
for pkg in ('src', 'src.research', 'src.research.archivist'):
    if pkg not in sys.modules:
        stub = type(sys)('pkg')
        stub.__path__ = [str(BASE / pkg.replace('.', '/'))]
        stub.__package__ = pkg
        sys.modules[pkg] = stub

cfg  = _load('src.research.archivist.config',
             BASE / 'src/research/archivist/config.py')
chunker = _load('src.research.archivist.chunker',
                BASE / 'src/research/archivist/chunker.py')

# crawler needs requests + bs4 — both available
import requests
from bs4 import BeautifulSoup

# ── Inline crawler (mirrors crawler.fetch_url exactly) ─────────────────────

FIRECRAWL_URL = os.getenv('FIRECRAWL_BASE_URL', 'http://localhost:3002')
USER_AGENT = cfg.USER_AGENT

def _extract_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script","style","nav","footer","iframe","noscript",
                     "header","aside","form","button","label","svg"]):
        tag.decompose()
    main = (soup.find('main') or soup.find('article') or
            soup.find('div', id='content') or
            soup.find('div', class_='content') or soup)
    text = main.get_text(separator="\n")
    lines = (l.strip() for l in text.splitlines())
    chunks = (p.strip() for l in lines for p in l.split("  "))
    cleaned = '\n'.join(c for c in chunks if len(c) > 20)
    junk = ["log in","sign up","privacy policy","cookie policy","subscribe",
            "related articles","follow us on","more from","recommended for you",
            "read more","terms of service","accessibility"]
    filtered, skip = [], False
    for line in cleaned.split('\n'):
        ll = line.lower()
        if any(j in ll for j in ["related topics","most read","editors' picks",
                                  "footer","sidebar","navigation"]):
            skip = True
        if skip:
            continue
        if len(line.split()) < 5 and any(j in ll for j in junk):
            continue
        filtered.append(line)
    return '\n'.join(filtered)


def fetch_url_instrumented(url: str):
    """
    Returns (text, method, retries, error_class).
    method: 'firecrawl' | 'requests' | 'pdf' | None
    error_class: None | 'network' | 'http_error' | 'parse_error' | 'empty_content'
    """
    retries = 0

    # Try Firecrawl
    if not url.lower().endswith('.pdf'):
        try:
            r = requests.post(
                f"{FIRECRAWL_URL}/v1/scrape",
                json={"url": url, "formats": ["markdown"],
                      "onlyMainContent": True, "waitFor": 2000},
                timeout=30
            )
            if r.status_code == 200:
                data = r.json()
                if data.get('success') and 'data' in data:
                    text = data['data'].get('markdown', '')
                elif 'markdown' in data:
                    text = data['markdown']
                else:
                    text = ''
                if text:
                    return text, 'firecrawl', retries, None
        except Exception:
            pass  # fall through to requests

    # Fallback: requests
    headers = {"User-Agent": USER_AGENT}
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            ct = resp.headers.get('Content-Type', '').lower()
            if 'application/pdf' in ct or url.lower().endswith('.pdf'):
                try:
                    import io, pypdf
                    reader = pypdf.PdfReader(io.BytesIO(resp.content))
                    text = "".join(p.extract_text() + "\n" for p in reader.pages)
                    return text, 'pdf', retries, None
                except Exception as e:
                    return None, 'pdf', retries, 'parse_error'
            text = _extract_text(resp.text)
            return text, 'requests', retries, None
        except requests.exceptions.ConnectionError as e:
            last_err = 'network'
            retries += 1
            time.sleep(0.5 * (attempt + 1))
        except requests.exceptions.HTTPError as e:
            return None, 'requests', retries, f'http_{resp.status_code}'
        except requests.exceptions.Timeout:
            last_err = 'timeout'
            retries += 1
            time.sleep(0.5 * (attempt + 1))
        except Exception as e:
            return None, 'requests', retries, 'unknown'

    return None, 'requests', retries, last_err or 'network'


# ── Test URL corpus ─────────────────────────────────────────────────────────
# Varied set: reliable .gov/.edu, news, PDF, long-form, 404, empty

TEST_URLS = [
    # Tier 1 — highly reliable
    ("https://www.nih.gov/about-nih/what-we-do/nih-almanac",          "gov_html"),
    ("https://www.cdc.gov/flu/about/index.html",                      "gov_html"),
    ("https://arxiv.org/abs/2310.06825",                              "arxiv_abstract"),
    # Tier 2 — news / long-form
    ("https://apnews.com",                                             "news_homepage"),
    ("https://www.bbc.com/news",                                       "news_homepage"),
    # Tier 3 — edge cases
    ("https://httpbin.org/status/404",                                 "http_404"),
    ("https://httpbin.org/status/500",                                 "http_500"),
    ("https://httpbin.org/delay/35",                                   "timeout"),
    # Tier 4 — large content
    ("https://en.wikipedia.org/wiki/Machine_learning",                 "wiki_large"),
]

# ── Run soak ────────────────────────────────────────────────────────────────

RUNS = 2   # run each URL twice to check determinism

def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]

def chunk_hash(chunks: list) -> str:
    return hashlib.sha256(json.dumps(chunks).encode()).hexdigest()[:16]

records = []  # list of per-(url,run) dicts

print(f"[SOAK] Starting — {len(TEST_URLS)} URLs × {RUNS} runs = {len(TEST_URLS)*RUNS} total")
print(f"[SOAK] CHUNK_SIZE={cfg.CHUNK_SIZE}  CHUNK_OVERLAP={cfg.CHUNK_OVERLAP}")
print()

for (url, label) in TEST_URLS:
    url_records = []
    for run_idx in range(RUNS):
        rec = {
            "url": url,
            "label": label,
            "run": run_idx + 1,
            "text_len": None,
            "chunk_count": None,
            "content_hash": None,
            "chunk_hash": None,
            "fetch_method": None,
            "fetch_retries": 0,
            "error_class": None,
            "rejection_reason": None,
            "duration_s": None,
        }

        t0 = time.time()
        try:
            text, method, retries, err_class = fetch_url_instrumented(url)
            rec["fetch_method"] = method
            rec["fetch_retries"] = retries

            if err_class:
                rec["error_class"] = err_class
                rec["rejection_reason"] = "fetch_failure"
            elif not text:
                rec["error_class"] = "empty_response"
                rec["rejection_reason"] = "empty_content"
            elif len(text) <= 300:
                rec["text_len"] = len(text)
                rec["rejection_reason"] = "below_length_gate"
                rec["error_class"] = "validation_rejection"
            else:
                rec["text_len"] = len(text)
                rec["content_hash"] = content_hash(text)

                chunks = chunker.chunk_text(text)
                if not chunks:
                    rec["rejection_reason"] = "chunking_returned_empty"
                    rec["error_class"] = "chunking_anomaly"
                else:
                    rec["chunk_count"] = len(chunks)
                    rec["chunk_hash"] = chunk_hash(chunks)

        except Exception as e:
            rec["error_class"] = "unexpected_exception"
            rec["rejection_reason"] = str(e)[:120]

        rec["duration_s"] = round(time.time() - t0, 2)
        url_records.append(rec)
        status = rec["rejection_reason"] or f"{rec['chunk_count']} chunks"
        print(f"  [{label}] run={run_idx+1}  {status}  ({rec['duration_s']}s)")

    records.append(url_records)

# ── Analysis ────────────────────────────────────────────────────────────────

total_urls = len(TEST_URLS)
total_runs = total_urls * RUNS

# Flat list of all individual records
all_recs = [r for pair in records for r in pair]

fetch_failures   = [r for r in all_recs if r["error_class"] in ("network","timeout") or
                    (r["error_class"] and r["error_class"].startswith("http_"))]
rejections       = [r for r in all_recs if r["rejection_reason"] in
                    ("empty_content","below_length_gate","chunking_returned_empty")]
successful       = [r for r in all_recs if r["chunk_count"] is not None]
chunking_anomaly = [r for r in all_recs if r["error_class"] == "chunking_anomaly"]
unexpected       = [r for r in all_recs if r["error_class"] == "unexpected_exception"]

# Retry summary
retry_sources = defaultdict(int)
for r in all_recs:
    if r["fetch_retries"] > 0:
        retry_sources[r["label"]] += r["fetch_retries"]

# Chunking metrics (only successful runs)
chunk_counts = [r["chunk_count"] for r in successful]
avg_chunks = round(sum(chunk_counts)/len(chunk_counts), 1) if chunk_counts else 0
max_chunks = max(chunk_counts) if chunk_counts else 0
min_chunks = min(chunk_counts) if chunk_counts else 0

# Determinism: compare run 1 vs run 2 per URL
determinism_results = []
for pair in records:
    if len(pair) < 2:
        continue
    r1, r2 = pair[0], pair[1]
    label = r1["label"]
    if r1["chunk_count"] is not None and r2["chunk_count"] is not None:
        stable = (r1["content_hash"] == r2["content_hash"] and
                  r1["chunk_hash"]   == r2["chunk_hash"])
        determinism_results.append({
            "label": label,
            "stable": stable,
            "chunks_r1": r1["chunk_count"],
            "chunks_r2": r2["chunk_count"],
        })

# Rejection frequency
rejection_counts = defaultdict(int)
for r in all_recs:
    if r["rejection_reason"]:
        rejection_counts[r["rejection_reason"]] += 1

# Failure classification
failure_class_counts = defaultdict(int)
for r in all_recs:
    if r["error_class"]:
        failure_class_counts[r["error_class"]] += 1

# ── Write SOAK-RESULTS.md ───────────────────────────────────────────────────

output_dir = BASE / ".planning/gauntlet_phases"
output_dir.mkdir(parents=True, exist_ok=True)
out_path = output_dir / "SOAK-RESULTS.md"

lines = []
lines.append("# SOAK-RESULTS")
lines.append(f"\n**Run date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
lines.append(f"**Chunk config:** CHUNK_SIZE={cfg.CHUNK_SIZE}, CHUNK_OVERLAP={cfg.CHUNK_OVERLAP}")
lines.append(f"\n## Duration")
lines.append(f"- Total duration: {sum(r['duration_s'] for r in all_recs):.1f}s")
lines.append(f"- URLs tested: {total_urls}")
lines.append(f"- Runs per URL: {RUNS}")
lines.append(f"- Total fetch attempts: {total_runs}")

lines.append(f"\n## Total URLs processed")
lines.append(f"- Successful (chunked): {len(set(r['url'] for r in successful))}")
lines.append(f"- Rejected/failed: {total_urls - len(set(r['url'] for r in successful))}")

lines.append(f"\n## Retry Summary")
total_retries = sum(r["fetch_retries"] for r in all_recs)
lines.append(f"- Total retry events: {total_retries}")
if retry_sources:
    lines.append("- Sources triggering retries:")
    for label, count in sorted(retry_sources.items(), key=lambda x: -x[1]):
        lines.append(f"  - {label}: {count} retries")
else:
    lines.append("- No retries observed")

lines.append(f"\n## Rejection Summary")
if rejection_counts:
    for reason, count in sorted(rejection_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {reason}: {count}")
else:
    lines.append("- No rejections")

lines.append(f"\n## Chunking Metrics")
if chunk_counts:
    lines.append(f"- Successful chunked runs: {len(successful)}")
    lines.append(f"- Avg chunk count: {avg_chunks}")
    lines.append(f"- Min chunk count: {min_chunks}")
    lines.append(f"- Max chunk count: {max_chunks}")
    lines.append(f"- Anomalies (chunker returned empty): {len(chunking_anomaly)}")
else:
    lines.append("- No successful chunk runs")

lines.append(f"\n## Determinism Checks")
if determinism_results:
    stable_ct   = sum(1 for d in determinism_results if d["stable"])
    unstable_ct = len(determinism_results) - stable_ct
    lines.append(f"- URLs with 2 successful runs: {len(determinism_results)}")
    lines.append(f"- Stable (same hash both runs): {stable_ct}")
    lines.append(f"- Unstable (hash drift detected): {unstable_ct}")
    if unstable_ct > 0:
        for d in determinism_results:
            if not d["stable"]:
                lines.append(f"  - DRIFT: {d['label']}  r1={d['chunks_r1']} chunks  r2={d['chunks_r2']} chunks")
else:
    lines.append("- Not enough successful pairs to check")

lines.append(f"\n## Failure Classification")
if failure_class_counts:
    for fc, count in sorted(failure_class_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {fc}: {count}")
    unclassified = sum(1 for r in all_recs
                       if r["rejection_reason"] == "unexpected_exception")
    if unclassified:
        lines.append(f"\n⚠️  {unclassified} runs hit unexpected_exception — observability gap")
else:
    lines.append("- No failures")

lines.append(f"\n## Per-URL Detail")
for pair in records:
    r = pair[0]
    lines.append(f"\n### {r['label']} — `{r['url'][:80]}`")
    for rec in pair:
        status = rec["rejection_reason"] or f"OK ({rec['chunk_count']} chunks)"
        lines.append(
            f"- run={rec['run']}  method={rec['fetch_method']}  "
            f"retries={rec['fetch_retries']}  len={rec['text_len']}  "
            f"status={status}  ({rec['duration_s']}s)"
        )

lines.append(f"\n## Observations")
lines.append("_Auto-generated. Fill in ingestion-path relevant issues below._")
lines.append("")

# Verdict
print()
print("=" * 60)
print(f"SOAK COMPLETE")
print(f"  Successful chunks: {len(successful)}/{total_runs} runs")
print(f"  Fetch failures: {len(fetch_failures)}")
print(f"  Rejections: {len(rejections)}")
print(f"  Unexpected exceptions: {len(unexpected)}")
if not determinism_results:
    print("  Determinism: INSUFFICIENT DATA")
else:
    stable = sum(1 for d in determinism_results if d["stable"])
    print(f"  Determinism: {stable}/{len(determinism_results)} stable")
print("=" * 60)

out_path.write_text('\n'.join(lines))
print(f"\nResults written to: {out_path}")
