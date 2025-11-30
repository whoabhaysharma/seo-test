import google.generativeai as genai
from bs4 import BeautifulSoup
import re
import json
from .utils import get_session

def clean_json_text(text: str) -> str:
    """
    Cleans the AI response to ensure it's valid JSON.
    Removes markdown code blocks (```json ... ```) and leading/trailing whitespace.
    """
    text = text.strip()
    # Remove markdown code blocks if present
    if "```" in text:
        text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    return text

def generate_meta_tags(urls: list[str], api_key: str):
    if not api_key:
        return []

    genai.configure(api_key=api_key)
    
    # Use JSON mode for structure
    generation_config = {
        "response_mime_type": "application/json",
    }
    
    model = genai.GenerativeModel('gemini-2.5-flash', generation_config=generation_config)
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
                results.append({"URL": url, "New Title": "Error", "New Desc": "Error"})
                continue

            soup = BeautifulSoup(resp.text, "lxml")

            # 2. Extract Current Metadata (Robust Scraping)
            old_title = soup.title.string.strip() if (soup.title and soup.title.string) else ""

            old_desc = ""
            # Look for standard description OR og:description as backup
            meta = soup.find("meta", attrs={"name": re.compile("description", re.I)})
            if not meta:
                meta = soup.find("meta", attrs={"property": re.compile("og:description", re.I)})
            
            if meta and meta.get("content"):
                old_desc = meta.get("content").strip()

            # 3. Extract Context (Enhanced for Gallery Pages)
            # Since your example is a gallery, it might not have many <p> tags.
            # We add H2s and Image Alts to give the AI more context.
            h1 = soup.find("h1")
            h1_text = h1.get_text(strip=True) if h1 else ""
            
            paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")[:5]]
            
            # Also grab some image alt text if paragraphs are scarce (helpful for galleries)
            images = [img.get('alt', '') for img in soup.find_all('img', alt=True)[:5]]
            
            content_snippet = f"H1: {h1_text}\nContent: {' '.join(paragraphs)}\nImages: {' '.join(images)}"

            # 4. Generate
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

            IMPORTANT: Return raw JSON only. No markdown formatting.
            Structure:
            {{
                "title": "New Title Here",
                "description": "New Description Here"
            }}
            """

            response = model.generate_content(prompt)
            
            # 5. Parse Safely
            cleaned_text = clean_json_text(response.text)
            
            new_title = old_title
            new_desc = old_desc

            try:
                data = json.loads(cleaned_text)
                new_title = data.get("title", old_title)
                new_desc = data.get("description", old_desc)
                
                # Double check: if AI returns empty string, keep old
                if not new_title: new_title = old_title
                if not new_desc: new_desc = old_desc

            except json.JSONDecodeError as e:
                print(f"JSON Error for {url}: {e}")
                # Fallback: Try regex if JSON fails
                title_match = re.search(r'"title":\s*"(.*?)"', cleaned_text)
                desc_match = re.search(r'"description":\s*"(.*?)"', cleaned_text)
                if title_match: new_title = title_match.group(1)
                if desc_match: new_desc = desc_match.group(1)

            results.append({
                "URL": url,
                "Old Title": old_title,
                "New Title": new_title,
                "Old Desc": old_desc,
                "New Desc": new_desc
            })

        except Exception as e:
            print(f"Error processing {url}: {e}")
            results.append({
                "URL": url,
                "Old Title": "Error",
                "New Title": "",
                "Old Desc": "Error",
                "New Desc": ""
            })

    return results
