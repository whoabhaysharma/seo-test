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

    # Configure Gemini
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash') 

    # 1. Fetch Current Schema
    try:
        session = get_session()
        response = session.get(url, timeout=10)
        if response.status_code >= 400:
             return f"Error: Failed to fetch page. Status code {response.status_code}", "", 0, 0, ""

        soup = BeautifulSoup(response.text, "lxml")
        old_schema = get_raw_schema(soup)
    except Exception as e:
        return f"Error fetching current schema: {str(e)}", "", 0, 0, ""

    # 2. Capture Screenshot
    try:
        screenshot_paths = capture_screenshots([url])
        if not screenshot_paths:
            return old_schema, "Error: Failed to capture screenshot.", 0, 0, ""

        screenshot_path = screenshot_paths[0]
    except Exception as e:
        return old_schema, f"Error capturing screenshot: {str(e)}", 0, 0, ""

    # 3. Generate New Schema with Gemini (asking for JSON output)
    prompt = """
    You are an expert Technical SEO Specialist.
    Analyze the provided screenshot of a webpage and its current JSON-LD schema (provided below).

    Your task is to:
    1. Generate an IMPROVED, COMPLETE, and VALID JSON-LD schema.
    2. Score the OLD schema out of 10.
    3. Score the NEW schema out of 10.
    4. Provide a very short summary of changes.

    Current Schema:
    {current_schema}

    Output Requirement:
    Return ONLY a valid JSON object with this exact structure:
    {
        "old_score": 5,
        "new_score": 9,
        "new_schema": { ... your json ld object ... },
        "improvement_summary": "Added missing aggregateRating and price attributes."
    }
    """

    prompt_filled = prompt.replace("{current_schema}", old_schema)

    try:
        # Load image
        img = Image.open(screenshot_path)

        # Generate content
        response = model.generate_content([prompt_filled, img])

        # clean markdown if gemini adds it
        text_response = response.text.strip()
        if text_response.startswith("```json"):
            text_response = text_response[7:]
        if text_response.startswith("```"):
            text_response = text_response[3:]
        if text_response.endswith("```"):
            text_response = text_response[:-3]

        # Parse JSON
        data = json.loads(text_response.strip())

        new_schema_obj = data.get("new_schema", {})
        new_schema_str = json.dumps(new_schema_obj, indent=2)
        old_score = data.get("old_score", 0)
        new_score = data.get("new_score", 0)
        summary = data.get("improvement_summary", "Schema generated.")

        return old_schema, new_schema_str, old_score, new_score, summary

    except Exception as e:
        # Fallback in case of JSON parse error or API error
        return old_schema, f"Error parsing Gemini response: {str(e)}", 0, 0, ""