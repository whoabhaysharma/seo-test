from bs4 import BeautifulSoup
from .config import TIMEOUT
from .utils import get_session

# Initialize session once or per request? Using shared session for now.
session = get_session()

def check_robots_txt(base_url):
    """
    Checks if robots.txt exists.
    Returns True if status code is 200.
    """
    try:
        r = session.get(f"{base_url.rstrip('/')}/robots.txt", timeout=TIMEOUT)
        return r.status_code == 200
    except:
        return False

def fetch_sitemap_urls(sitemap_url, collected=None):
    """
    Recursively fetches URLs from a sitemap.
    """
    if collected is None:
        collected = set()
    try:
        r = session.get(sitemap_url, timeout=TIMEOUT)
        if r.status_code != 200:
            return collected

        # Using lxml-xml or xml parser
        soup = BeautifulSoup(r.content, "xml")

        # Handle nested sitemaps
        for sitemap in soup.find_all("sitemap"):
            loc = sitemap.find("loc")
            if loc:
                fetch_sitemap_urls(loc.text.strip(), collected)

        # Handle urls
        for url in soup.find_all("url"):
            loc = url.find("loc")
            if loc:
                collected.add(loc.text.strip())

    except Exception:
        pass
    return collected
