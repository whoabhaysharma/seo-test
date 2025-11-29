import google.generativeai as genai
from bs4 import BeautifulSoup
from .utils import get_session
import re

def generate_meta_tags(urls: list[str], api_key: str):
    """
    Analyzes a list of URLs and generates improved Meta Titles and Descriptions.
    Returns a list of dictionaries for a DataFrame.
    """
    if not api_key:
        return []

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    session = get_session()

    results = []

    for url in urls:
        url = url.strip()
        if not url: continue
        
        if not url.startswith("http"):
            url = "https://" + url

        try:
            # 1. Fetch Page Content
            resp = session.get(url, timeout=10)
            if resp.status_code >= 400:
                results.append({
                    "URL": url,
                    "Old Title": "Error fetching",
                    "New Title": "",
                    "Old Desc": "Error fetching",
                    "New Desc": ""
                })
                continue

            soup = BeautifulSoup(resp.text, "lxml")

            # 2. Extract Current Metadata
            old_title = ""
            if soup.title and soup.title.string:
                old_title = soup.title.string.strip()

            old_desc = ""
            meta = soup.find("meta", attrs={"name": re.compile("description", re.I)})
            if meta and meta.get("content"):
                old_desc = meta.get("content").strip()

            # 3. Extract Content for Context (H1 + first few paragraphs)
            h1 = soup.find("h1")
            h1_text = h1.get_text(strip=True) if h1 else ""
            
            paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")[:3]]
            content_snippet = f"H1: {h1_text}\nContent: {' '.join(paragraphs)}"

            # 4. Generate with Gemini
            prompt = f"""
            You are an SEO Expert.
            Analyze this webpage context and current meta tags.
            
            URL: {url}
            Current Title: {old_title}
            Current Description: {old_desc}
            Page Context: {content_snippet}

            Task:
            1. Create a BETTER Meta Title (max 60 chars, compelling, keyword-rich).
            2. Create a BETTER Meta Description (max 160 chars, actionable, summarizes content).

            Output format:
            Title: <new_title>
            Description: <new_description>
            """

            response = model.generate_content(prompt)
            text = response.text.strip()
            
            # Parse output
            new_title = old_title # Fallback
            new_desc = old_desc   # Fallback
            
            for line in text.split('\n'):
                if line.startswith("Title:"):
                    new_title = line.replace("Title:", "").strip()
                elif line.startswith("Description:"):
                    new_desc = line.replace("Description:", "").strip()

            results.append({
                "URL": url,
                "Old Title": old_title,
                "New Title": new_title,
                "Old Desc": old_desc,
                "New Desc": new_desc
            })

        except Exception as e:
            results.append({
                "URL": url,
                "Old Title": "Error",
                "New Title": str(e),
                "Old Desc": "Error",
                "New Desc": ""
            })

    return results
