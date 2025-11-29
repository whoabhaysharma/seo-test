import os
import json
import google.generativeai as genai
from PIL import Image
from bs4 import BeautifulSoup
from .utils import get_session, get_raw_schema
from .capturer import capture_screenshots

def generate_improved_schema(url: str, api_key: str):
    """
    Coordinates process: fetch, screenshot, analyze with Gemini.
    Returns:
        tuple: (old_schema_str, new_schema_str, old_score, new_score, summary)
    """
    if not api_key:
        return "Error: Gemini API Key is required.", "", 0, 0, ""

    genai.configure(api_key=api_key)
    # Using Flash model for speed and efficiency
    model = genai.GenerativeModel('gemini-1.5-flash') 

    # 1. Fetch Current Schema
    try:
        session = get_session()
        response = session.get(url, timeout=10)
        if response.status_code >= 400:
             return f"Error: Status {response.status_code}", "", 0, 0, ""
        soup = BeautifulSoup(response.text, "lxml")
        old_schema = get_raw_schema(soup)
    except Exception as e:
        return f"Error fetching schema: {str(e)}", "", 0, 0, ""

    # 2. Capture Screenshot
    try:
        screenshot_paths = capture_screenshots([url])
        if not screenshot_paths:
            return old_schema, "Error: Screenshot failed.", 0, 0, ""
        screenshot_path = screenshot_paths[0]
    except Exception as e:
        return old_schema, f"Error capturing screenshot: {str(e)}", 0, 0, ""

    # 3. Generate New Schema & Scores
    # We ask for a JSON response containing scores and the schema
    prompt = """
    You are an expert Technical SEO Specialist.
    Analyze the provided screenshot of a webpage and its current JSON-LD schema.

    Task:
    1. Analyze the current schema's quality.
    2. Generate an IMPROVED, COMPLETE, and VALID JSON-LD schema based on the visual content of the screenshot (add ratings, breadcrumbs, prices, etc., if visible).
    3. Score both the old and new schema out of 10 based on SEO best practices (completeness, syntax, entity depth).

    Current Schema:
    {current_schema}

    Output format:
    Return a SINGLE JSON object with this exact structure (no markdown formatting):
    {
        "old_score": <integer 0-10>,
        "new_score": <integer 0-10>,
        "new_schema": <the valid json-ld object>,
        "improvement_summary": "<short 1-sentence explanation of changes>"
    }
    """
    
    prompt_filled = prompt.replace("{current_schema}", old_schema)

    try:
        img = Image.open(screenshot_path)
        response = model.generate_content([prompt_filled, img])
        
        # Cleanup response to ensure valid JSON
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        
        data = json.loads(raw_text.strip())
        
        # Extract string version of new schema for the UI editor
        new_schema_str = json.dumps(data.get("new_schema", {}), indent=2)
        old_score = data.get("old_score", 0)
        new_score = data.get("new_score", 0)
        summary = data.get("improvement_summary", "Schema updated.")

        return old_schema, new_schema_str, old_score, new_score, summary

    except Exception as e:
        return old_schema, f"Error Gemini/Parse: {str(e)}", 0, 0, ""