import google.generativeai as genai
from bs4 import BeautifulSoup
import re
import json
from .utils import get_session

def generate_meta_tags(urls: list[str], api_key: str):
    """
    Analyzes a list of URLs and generates improved Meta Titles and Descriptions.
    Returns a list of dictionaries for a DataFrame.
    """
    if not api_key:
        return []

    genai.configure(api_key=api_key)
    
    # 1. Configure for JSON Mode
    # This forces the model to output valid JSON, preventing parsing errors
    generation_config = {
        "response_mime_type": "application/json",
    }
    
    # 2. Use the requested Gemini 2.5 Flash model
    model = genai.GenerativeModel('gemini-2.5-flash', generation_config=generation_config)
    session = get_session()

    results = []

    for url in urls:
        url = url.strip()
        if not url: continue
        
        if not url.startswith("http"):
            url = "https://" + url

        try:
            # --- Fetch Page Content ---
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

            # --- Extract Current Metadata ---
            old_title = ""
            if soup.title and soup.title.string:
                old_title = soup.title.string.strip()

            old_desc = ""
            meta = soup.find("meta", attrs={"name": re.compile("description", re.I)})
            if meta and meta.get("content"):
                old_desc = meta.get("content").strip()

            # --- Extract Content Context ---
            h1 = soup.find("h1")
            h1_text = h1.get_text(strip=True) if h1 else ""
            
            paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")[:3]]
            content_snippet = f"H1: {h1_text}\nContent: {' '.join(paragraphs)}"

            # --- Generate with Gemini 2.5 Flash ---
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

            Output Requirement:
            Return ONLY a JSON object with this exact structure:
            {{
                "title": "Insert new title here",
                "description": "Insert new description here"
            }}
            """

            response = model.generate_content(prompt)
            
            # --- Parse JSON Output ---
            new_title = old_title # Fallback
            new_desc = old_desc   # Fallback

            try:
                data = json.loads(response.text)
                new_title = data.get("title", old_title)
                new_desc = data.get("description", old_desc)
            except json.JSONDecodeError:
                print(f"JSON Error for {url}")
            
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
