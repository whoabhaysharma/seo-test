import time
import re
import asyncio
import aiohttp
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import textstat
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import TIMEOUT, MAX_BROKEN_LINK_CHECKS
from .utils import get_session, get_schema_types

session = get_session()

async def fetch_page_async(url, session_obj=None):
    """Async fetch a page using aiohttp for true concurrent loading."""
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session_async:
            async with session_async.get(url, ssl=False, allow_redirects=True) as resp:
                return url, resp.status, await resp.read(), resp.headers
    except asyncio.TimeoutError:
        return url, 0, None, {}
    except Exception as e:
        return url, 0, None, {}

async def fetch_pages_async(urls):
    """Fetch multiple pages concurrently using async."""
    tasks = [fetch_page_async(url) for url in urls]
    return await asyncio.gather(*tasks)

def check_link_status(url):
    """Checks the status of a single link."""
    try:
        resp = session.head(url, timeout=5)
        return resp.status_code >= 400
    except:
        return True

def analyze_page(url, domain_netloc):
    result = {
        "url": url,
        "status_code": 0,
        "status_type": "Unknown",

        # --- NEW METRICS ---
        "https_ok": False,
        "page_size_kb": 0.0,
        "schema_types": "",

        # --- ORIGINAL METRICS ---
        "title": "",
        "title_len": 0,
        "meta_description": "",
        "meta_description_len": 0,
        "h1_text": "",
        "h1_count": 0,
        "word_count": 0,
        "canonical": "",
        "internal_links": 0,
        "external_links": 0,
        "broken_links": 0,  # Added this
        "load_time_s": 0.0,

        # --- FLAGS ---
        "multiple_title_tags": False,
        "h1_equals_title": False,
        "sequential_h1_error": False,
        "missing_alt_count": 0,
        "issues_found": []
    }

    try:
        start = time.time()
        r = session.get(url, timeout=TIMEOUT)
        result["load_time_s"] = round(time.time() - start, 2)
        result["status_code"] = r.status_code

        # 1. Page Size (KB)
        result["page_size_kb"] = round(len(r.content) / 1024, 2)

        # 2. HTTPS Check
        result["https_ok"] = r.url.startswith("https://")

        # Status Type
        if 200 <= r.status_code < 300: result["status_type"] = "Success"
        elif 300 <= r.status_code < 400: result["status_type"] = "Redirect"
        elif 400 <= r.status_code < 500: result["status_type"] = "Client Error"
        else: result["status_type"] = "Server Error"

    except Exception as e:
        result["issues_found"].append(f"Conn Error: {str(e)}")
        return result

    if "text/html" not in r.headers.get("Content-Type", "") or r.status_code >= 400:
        return result

    soup = BeautifulSoup(r.text, "lxml")

    # 3. Schema Types
    result["schema_types"] = get_schema_types(soup)

    # --- SEO CHECKS ---
    titles = soup.find_all("title")
    result["multiple_title_tags"] = len(titles) > 1
    if titles and titles[0].string:
        result["title"] = titles[0].string.strip()
        result["title_len"] = len(result["title"])

    meta_desc = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    if meta_desc and meta_desc.get("content"):
        result["meta_description"] = meta_desc.get("content").strip()
        result["meta_description_len"] = len(result["meta_description"])

    h1s = soup.find_all("h1")
    result["h1_count"] = len(h1s)
    if h1s: result["h1_text"] = h1s[0].get_text(" ", strip=True)

    if result["title"] and result["h1_text"] and result["title"].lower() == result["h1_text"].lower():
        result["h1_equals_title"] = True

    headers = soup.find_all(re.compile(r"^h[1-6]$"))
    if headers and headers[0].name.lower() != "h1":
        result["sequential_h1_error"] = True

    can_tag = soup.find("link", rel="canonical")
    if can_tag and can_tag.get("href"):
        result["canonical"] = can_tag.get("href")

    result["word_count"] = len(soup.get_text(" ", strip=True).split())

    imgs = soup.find_all("img")
    result["missing_alt_count"] = sum(1 for img in imgs if not img.get("alt"))

    # Links & Broken Link Check
    internal_urls_to_check = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue

        full_href = urljoin(url, href)
        parsed_href = urlparse(full_href)

        if parsed_href.netloc == domain_netloc:
            result["internal_links"] += 1
            internal_urls_to_check.add(full_href)
        else:
            result["external_links"] += 1

    # Check a subset of internal links for 404s
    broken_count = 0
    # Convert to list and slice
    links_to_test = list(internal_urls_to_check)[:MAX_BROKEN_LINK_CHECKS]

    # Concurrent broken link checking with increased workers
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_url = {executor.submit(check_link_status, link): link for link in links_to_test}
        for future in as_completed(future_to_url):
            is_broken = future.result()
            if is_broken:
                broken_count += 1

    result["broken_links"] = broken_count

    # --- ISSUES LIST ---
    issues = result["issues_found"]
    if not result["https_ok"]: issues.append("Not HTTPS")
    if result["page_size_kb"] > 2000: issues.append("Large Page (>2MB)")
    if not result["schema_types"]: issues.append("No Schema")
    if result["title_len"] == 0: issues.append("Missing Title")
    elif result["title_len"] > 60: issues.append("Title > 60 chars")
    if result["h1_count"] == 0: issues.append("Missing H1")
    elif result["h1_count"] > 1: issues.append("Multiple H1s")
    if result["h1_equals_title"]: issues.append("Title == H1")
    if result["missing_alt_count"] > 0: issues.append(f"{result['missing_alt_count']} Images missing Alt")
    if result["broken_links"] > 0: issues.append(f"{result['broken_links']} Broken Links")

    return result
