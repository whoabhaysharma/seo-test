import os
import json
import google.generativeai as genai
from bs4 import BeautifulSoup
from .utils import get_session, get_raw_schema
from .capturer import capture_screenshots

def generate_improved_schema(url: str, api_key: str):
    """
    Coordinates the process of capturing a screenshot, fetching current schema,
    and using Gemini to generate an improved schema.

    Returns:
        tuple: (old_schema_str, new_schema_str)
    """
    if not api_key:
        return "Error: Gemini API Key is required.", ""

    # Configure Gemini
    genai.configure(api_key=api_key)

    # Select model - gemini-1.5-flash is good for vision and speed
    model = genai.GenerativeModel('gemini-2.5-flash')

    # 1. Fetch Current Schema
    try:
        session = get_session()
        response = session.get(url, timeout=10)
        if response.status_code >= 400:
             return f"Error: Failed to fetch page. Status code {response.status_code}", ""

        soup = BeautifulSoup(response.text, "lxml")
        old_schema = get_raw_schema(soup)
    except Exception as e:
        return f"Error fetching current schema: {str(e)}", ""

    # 2. Capture Screenshot
    # We use capture_screenshots which returns a list of paths
    try:
        screenshot_paths = capture_screenshots([url])
        if not screenshot_paths:
            return old_schema, "Error: Failed to capture screenshot."

        screenshot_path = screenshot_paths[0]
    except Exception as e:
        return old_schema, f"Error capturing screenshot: {str(e)}"

    # 3. Generate New Schema with Gemini
    prompt = """
    You are an expert Technical SEO Specialist.
    Analyze the provided screenshot of a webpage and its current JSON-LD schema (provided below).

    Your task is to generate an IMPROVED, COMPLETE, and VALID JSON-LD schema for this page.

    - Fix any errors in the current schema.
    - Add missing properties that are visible in the screenshot (e.g., Breadcrumbs, Product details, Review ratings, FAQ, Article data, etc.).
    - Ensure the syntax is correct.
    - Return ONLY the JSON code, no markdown fencing (```json ... ```) or explanation.

    Current Schema:
    {current_schema}
    """

    prompt_filled = prompt.replace("{current_schema}", old_schema)

    try:
        # Load image for Gemini
        img_file = genai.upload_file(screenshot_path)

        # Generate content
        response = model.generate_content([prompt_filled, img_file])

        new_schema = response.text.strip()

        # Clean up markdown if present
        if new_schema.startswith("```json"):
            new_schema = new_schema[7:]
        if new_schema.startswith("```"):
            new_schema = new_schema[3:]
        if new_schema.endswith("```"):
            new_schema = new_schema[:-3]

        return old_schema, new_schema.strip()

    except Exception as e:
        return old_schema, f"Error calling Gemini API: {str(e)}"
