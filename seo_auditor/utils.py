import json
import requests
from .config import USER_AGENT

def get_session():
    """Returns a configured requests Session."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session

def get_schema_types(soup):
    """Recursively extracts all @type values from JSON-LD."""
    types_found = set()
    scripts = soup.find_all('script', type='application/ld+json')

    def extract_recursive(data):
        if isinstance(data, dict):
            if "@type" in data:
                t = data["@type"]
                if isinstance(t, list):
                    types_found.update(t)
                else:
                    types_found.add(t)
            for key, value in data.items():
                extract_recursive(value)
        elif isinstance(data, list):
            for item in data:
                extract_recursive(item)

    for script in scripts:
        if script.string:
            try:
                data = json.loads(script.string)
                extract_recursive(data)
            except:
                continue
    return ", ".join(sorted(list(types_found)))
