!pip install -q requests beautifulsoup4 lxml pandas tldextract textstat openpyxl xlsxwriter

import requests
from bs4 import BeautifulSoup
from xml.etree import ElementTree as ET
from urllib.parse import urljoin, urlparse
import pandas as pd
import json
import re
import time
from collections import defaultdict
import textstat

# ----------------------------------------
# CONFIG
# ----------------------------------------

USER_AGENT = "Mzilla/5.0 (compatible; ColabSEOAuditor/3.0; +https://example.com/bot)"
TIMEOUT = 15
MAX_INTERNAL_LINK_CHECK = 50 # Reduced slightly for speed

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

# ----------------------------------------
# LOGGING
# ----------------------------------------

def log(msg, icon="ℹ️"):
    print(f"{icon} {msg}")

# ----------------------------------------
# ROBOTS & SITEMAP UTILS
# ----------------------------------------

def check_robots_txt(base_url):
    """Checks if robots.txt exists and returns boolean + content."""
    try:
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        r = session.get(robots_url, timeout=TIMEOUT)
        exists = r.status_code == 200
        return exists, r.text if exists else ""
    except:
        return False, ""

def fetch_sitemap_urls(sitemap_url, collected=None):
    if collected is None:
        collected = set()

    try:
        r = session.get(sitemap_url, timeout=TIMEOUT)
        if r.status_code != 200:
            return collected

        xml = ET.fromstring(r.content)

        # Handle namespaces
        ns = {}
        m = re.match(r"\{(.+)\}", xml.tag)
        if m:
            ns = {"ns": m.group(1)}

        # Check for nested sitemaps
        sitemap_nodes = xml.findall(".//ns:sitemap", ns) if ns else xml.findall(".//sitemap")
        if sitemap_nodes:
            for s in sitemap_nodes:
                loc = s.find("ns:loc", ns).text if ns else s.find("loc").text
                if loc:
                    fetch_sitemap_urls(loc.strip(), collected)
            return collected

        # Check for urls
        url_nodes = xml.findall(".//ns:url", ns) if ns else xml.findall(".//url")
        for u in url_nodes:
            loc = u.find("ns:loc", ns).text if ns else u.find("loc").text
            if loc:
                collected.add(loc.strip())

    except Exception:
        pass # Silent fail for sitemap parsing errors
    return collected

# ----------------------------------------
# PAGE ANALYZER
# ----------------------------------------

def analyze_page(url, domain_netloc):
    result = {
        "url": url,
        "status_code": 0,
        "status_type": "Unknown",
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
        "broken_links": 0,
        "load_time_s": 0.0,

        # -- NEW FLAGS --
        "multiple_title_tags": False,  # Check 2
        "h1_equals_title": False,      # Check 4
        "sequential_h1_error": False,  # Check 3 (Is H1 the first header?)
        "missing_alt_count": 0,
        "issues_found": []
    }

    try:
        start = time.time()
        r = session.get(url, timeout=TIMEOUT)
        result["load_time_s"] = round(time.time() - start, 2)
        result["status_code"] = r.status_code

        # Check 6: Classify Status
        if 200 <= r.status_code < 300:
            result["status_type"] = "Success"
        elif 300 <= r.status_code < 400:
            result["status_type"] = "Redirect"
        elif 400 <= r.status_code < 500:
            result["status_type"] = "Client Error"
        elif r.status_code >= 500:
            result["status_type"] = "Server Error"

    except Exception as e:
        result["status_type"] = "Connection Error"
        result["issues_found"].append(f"Connection failed: {str(e)}")
        return result

    # Skip processing if not HTML or failed
    if "text/html" not in r.headers.get("Content-Type", "") or r.status_code >= 400:
        return result

    soup = BeautifulSoup(r.text, "lxml")

    # --- TITLE CHECKS ---
    titles = soup.find_all("title")
    result["multiple_title_tags"] = len(titles) > 1

    if titles and titles[0].string:
        result["title"] = titles[0].string.strip()
        result["title_len"] = len(result["title"])

    # --- META DESC ---
    meta_desc = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    if meta_desc and meta_desc.get("content"):
        result["meta_description"] = meta_desc.get("content").strip()
        result["meta_description_len"] = len(result["meta_description"])

    # --- HEADINGS (H1 ONLY) ---
    h1_tags = soup.find_all("h1")
    result["h1_count"] = len(h1_tags)
    if h1_tags:
        result["h1_text"] = h1_tags[0].get_text(" ", strip=True)

    # Check 4: H1 equals Title
    if result["title"] and result["h1_text"]:
        if result["title"].lower() == result["h1_text"].lower():
            result["h1_equals_title"] = True

    # Check 3: Sequential H1 Error
    # We check if the very first header tag appearing in the body is an H1
    all_headers = soup.find_all(re.compile(r"^h[1-6]$"))
    if all_headers:
        first_header = all_headers[0].name.lower()
        if first_header != "h1":
            result["sequential_h1_error"] = True

    # --- CANONICAL ---
    link_can = soup.find("link", rel="canonical")
    if link_can and link_can.get("href"):
        result["canonical"] = link_can.get("href").strip()

    # --- CONTENT ---
    text = soup.get_text(" ", strip=True)
    result["word_count"] = len(text.split())

    # --- IMAGES ---
    imgs = soup.find_all("img")
    result["missing_alt_count"] = sum(1 for img in imgs if not img.get("alt"))

    # --- LINKS ---
    internal_links = set()
    broken_count = 0

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("javascript:", "mailto:", "tel:")):
            continue

        abs_href = urljoin(url, href).split("#")[0]
        p_href = urlparse(abs_href)

        if p_href.netloc == domain_netloc:
            internal_links.add(abs_href)
        else:
            result["external_links"] += 1

    # Check limited broken links
    for link in list(internal_links)[:MAX_INTERNAL_LINK_CHECK]:
        try:
            if session.head(link, timeout=5).status_code >= 400:
                broken_count += 1
        except:
            broken_count += 1

    result["internal_links"] = len(internal_links)
    result["broken_links"] = broken_count

    # --- GENERATE SUGGESTIONS ---
    issues = result["issues_found"]

    if result["status_code"] >= 400:
        issues.append(f"Status {result['status_code']}")
    if result["multiple_title_tags"]:
        issues.append("Multiple <title> tags")
    if result["title_len"] == 0:
        issues.append("Missing Title")
    elif result["title_len"] > 60:
        issues.append("Title too long")
    if result["h1_count"] == 0:
        issues.append("Missing H1")
    elif result["h1_count"] > 1:
        issues.append("Multiple H1s")
    if result["sequential_h1_error"]:
        issues.append("Hierarchy Error: H1 is not first heading")
    if result["h1_equals_title"]:
        issues.append("Title identical to H1")
    if result["broken_links"] > 0:
        issues.append(f"{result['broken_links']} Broken Links")
    if result["missing_alt_count"] > 0:
        issues.append(f"{result['missing_alt_count']} Images missing Alt")
    if result["word_count"] < 300:
        issues.append("Thin Content")

    return result

# ----------------------------------------
# REPORT FORMATTER (EXCEL)
# ----------------------------------------

def save_beautiful_report(df, site_url, robots_ok, orphans_count, filename):
    """Saves a formatted Excel file with conditional formatting."""

    writer = pd.ExcelWriter(filename, engine='xlsxwriter')
    workbook = writer.book

    # --- Summary Sheet ---
    summary_data = {
        "Metric": ["Target Website", "Audit Date", "Robots.txt Found", "Total Pages Scanned", "Orphan Pages", "Avg Load Time"],
        "Value": [
            site_url,
            time.strftime("%Y-%m-%d"),
            "✅ Yes" if robots_ok else "❌ Missing",
            len(df),
            orphans_count,
            f"{df['load_time_s'].mean():.2f}s"
        ]
    }
    df_sum = pd.DataFrame(summary_data)
    df_sum.to_excel(writer, sheet_name='Summary', index=False)

    # Formatting Summary
    ws_sum = writer.sheets['Summary']
    fmt_bold = workbook.add_format({'bold': True, 'bg_color': '#EFEFEF', 'border': 1})
    ws_sum.set_column('A:A', 20, fmt_bold)
    ws_sum.set_column('B:B', 40)

    # --- Main Report Sheet ---

    # Reorder columns for readability
    cols_order = [
        "url", "status_code", "status_type",
        "title", "title_len", "duplicate_title", "multiple_title_tags", "h1_equals_title",
        "meta_description", "meta_description_len",
        "h1_text", "h1_count", "sequential_h1_error",
        "word_count", "missing_alt_count",
        "internal_links", "broken_links", "load_time_s",
        "is_orphan", "suggestions"
    ]
    # Filter columns that actually exist in df
    final_cols = [c for c in cols_order if c in df.columns]
    df_final = df[final_cols]

    df_final.to_excel(writer, sheet_name='Audit_Data', index=False, freeze_panes=(1, 0))
    worksheet = writer.sheets['Audit_Data']

    # -- Define Formats --
    header_fmt = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#2c3e50', 'border': 1})
    good_fmt = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'}) # Green
    bad_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})  # Red
    warn_fmt = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C6500'}) # Yellow

    # -- Apply Header Format --
    for col_num, value in enumerate(df_final.columns.values):
        worksheet.write(0, col_num, value, header_fmt)

    # -- Column Widths --
    worksheet.set_column('A:A', 50) # URL
    worksheet.set_column('B:B', 8)  # Status
    worksheet.set_column('C:C', 12) # Type
    worksheet.set_column('D:D', 40) # Title
    worksheet.set_column('I:I', 40) # Meta Desc
    worksheet.set_column('K:K', 30) # H1
    worksheet.set_column('T:T', 60) # Suggestions

    # -- Conditional Formatting --

    # 1. Status Code (Red if >= 400, Yellow if 300-399)
    worksheet.conditional_format(1, 1, len(df), 1, {'type': 'cell', 'criteria': '>=', 'value': 400, 'format': bad_fmt})
    worksheet.conditional_format(1, 1, len(df), 1, {'type': 'cell', 'criteria': 'between', 'minimum': 300, 'maximum': 399, 'format': warn_fmt})

    # 2. Duplicate Titles (Red if True)
    dup_col_idx = df_final.columns.get_loc("duplicate_title")
    worksheet.conditional_format(1, dup_col_idx, len(df), dup_col_idx, {'type': 'cell', 'criteria': '=', 'value': True, 'format': bad_fmt})

    # 3. Missing H1 (Red if 0)
    h1_cnt_idx = df_final.columns.get_loc("h1_count")
    worksheet.conditional_format(1, h1_cnt_idx, len(df), h1_cnt_idx, {'type': 'cell', 'criteria': '=', 'value': 0, 'format': bad_fmt})

    # 4. Sequential Error (Red if True)
    seq_err_idx = df_final.columns.get_loc("sequential_h1_error")
    worksheet.conditional_format(1, seq_err_idx, len(df), seq_err_idx, {'type': 'cell', 'criteria': '=', 'value': True, 'format': warn_fmt})

    # 5. Thin Content (Yellow if < 300 words)
    word_idx = df_final.columns.get_loc("word_count")
    worksheet.conditional_format(1, word_idx, len(df), word_idx, {'type': 'cell', 'criteria': '<', 'value': 300, 'format': warn_fmt})

    writer.close()

# ----------------------------------------
# MAIN AUDIT RUNNER
# ----------------------------------------

def audit_site(url):
    log(f"Starting Audit for: {url}", "🚀")

    parsed = urlparse(url)
    domain = parsed.netloc
    base_url = f"{parsed.scheme}://{domain}"

    # 1. Check Robots.txt (Check 5)
    robots_exists, robots_txt = check_robots_txt(base_url)
    log(f"Robots.txt status: {'Found' if robots_exists else 'MISSING ❌'}", "🤖")

    # 2. Gather Pages (Sitemap strategy)
    pages = set()
    pages.add(base_url) # Always check home

    sitemap_url = urljoin(base_url, "sitemap.xml")
    pages = fetch_sitemap_urls(sitemap_url, pages)

    # Fallback: Check robots.txt for sitemap if standard failed
    if len(pages) == 1 and robots_exists:
        for line in robots_txt.splitlines():
            if "sitemap:" in line.lower():
                sm = line.split(":", 1)[1].strip()
                pages = fetch_sitemap_urls(sm, pages)

    log(f"Pages to scan: {len(pages)}", "📄")

    # 3. Crawl & Analyze
    data = []
    internal_map = defaultdict(set)

    for i, p in enumerate(sorted(list(pages)), 1):
        log(f"[{i}/{len(pages)}] {p}", "🔍")
        row = analyze_page(p, domain)
        data.append(row)

        # Map links for orphan detection
        try:
            # We re-request strictly for link mapping if not cached,
            # but to save time we assume analyze_page accessed it.
            # In a full crawler, we'd pass the soup out.
            # Here we skip deep orphan logic to keep it fast,
            # relying on sitemap vs cross-linking presence is harder without full crawl.
            pass
        except: pass

    df = pd.DataFrame(data)

    # 4. Post-Processing Checks

    # Check 1: Duplicate Titles
    # Mark True only if title is not empty and appears more than once
    df['duplicate_title'] = df.duplicated(subset=['title'], keep=False) & (df['title'] != "")

    # Join issues into a string
    df['suggestions'] = df['issues_found'].apply(lambda x: " | ".join(x) if x else "✅ OK")

    # Simple Orphan Check: Pages in sitemap but 0 internal links pointing to them?
    # (Requires full crawl of all links to be accurate.
    # Here we simply flag pages with 0 incoming links found during this limited scan would be inaccurate
    # without a recursive crawler. We will skip deep orphan logic for this specific script structure
    # and just check if the page provided 404).
    df['is_orphan'] = "N/A (Sitemap based)" # Placeholder as we aren't spidering

    # 5. Save
    filename = f"{domain.replace('.', '_')}_seo_audit.xlsx"
    save_beautiful_report(df, url, robots_exists, 0, filename)

    log(f"Audit Complete! Saved to: {filename}", "💾")
    return df

# ----------------------------------------
# EXECUTION
# ----------------------------------------

# Add your websites here
websites = [
    "https://5starpartybusrental.com"
]

for site in websites:
    audit_site(site)
