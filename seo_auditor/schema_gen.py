import os
import json
import logging
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_gemini(api_key):
    """Configures the Gemini API with the provided key."""
    if not api_key:
        logger.warning("No Gemini API key provided.")
        return False
    genai.configure(api_key=api_key)
    return True

def extract_schema_from_url(url):
    """
    Extracts existing JSON-LD schema from the given URL.
    Returns a list of schema dictionaries or None if not found.
    """
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "SEOAuditor/1.0"})
        if response.status_code != 200:
            logger.error(f"Failed to fetch {url}: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        scripts = soup.find_all('script', type='application/ld+json')

        schemas = []
        for script in scripts:
            if script.string:
                try:
                    data = json.loads(script.string)
                    schemas.append(data)
                except json.JSONDecodeError:
                    continue

        if not schemas:
            return None

        # Return the first one if multiple, or list?
        return schemas[0] if len(schemas) == 1 else schemas

    except Exception as e:
        logger.error(f"Error extracting schema from {url}: {e}")
        return None

def generate_schema_from_screenshot(image_path, api_key):
    """
    Uses Gemini to generate JSON-LD schema from a screenshot.
    """
    if not setup_gemini(api_key):
        return {"error": "Invalid API Key"}

    try:
        # Use a standard available model
        model = genai.GenerativeModel('gemini-1.5-flash')

        # Open image
        img = Image.open(image_path)

        prompt = """
        Analyze this webpage screenshot and generate a detailed, valid JSON-LD schema markup for it.
        Focus on the main entity of the page (e.g., Article, Product, Organization, LocalBusiness).
        Ensure all relevant properties visible in the image are included.
        Return ONLY the JSON code, without markdown formatting.
        """

        response = model.generate_content([prompt, img])

        # Clean response
        text = response.text.strip()

        # Check finish reason if possible, but python lib abstracts it mostly.
        # However, to be safe against recitation errors:
        if hasattr(response, 'candidates') and response.candidates:
             if response.candidates[0].finish_reason == 4: # RECITATION
                 return {"error": "Model refused to generate due to recitation (copyright)."}

        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        return json.loads(text.strip())

    except Exception as e:
        logger.error(f"Error generating schema with Gemini: {e}")
        return {"error": str(e)}

def compare_and_score_schemas(old_schema, new_schema, api_key):
    """
    Uses Gemini to compare old and new schemas and assign SEO scores.
    """
    if not setup_gemini(api_key):
        return {"error": "Invalid API Key"}

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')

        prompt = f"""
        You are an SEO expert. Compare the following two JSON-LD schemas for the same webpage.

        Old Schema:
        {json.dumps(old_schema, indent=2) if old_schema else "None"}

        New Schema (Generated from visual content):
        {json.dumps(new_schema, indent=2)}

        Task:
        1. Rate the 'Old Schema' out of 10 based on completeness, correctness, and SEO best practices. (If None, score is 0).
        2. Rate the 'New Schema' out of 10 based on completeness, correctness, and SEO best practices.
        3. Explain the key differences and improvements.

        Return the result as a valid JSON object with the following structure:
        {{
            "old_score": <number>,
            "new_score": <number>,
            "analysis": "<string>"
        }}
        Return ONLY the JSON.
        """

        response = model.generate_content(prompt)

        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        return json.loads(text.strip())

    except Exception as e:
        logger.error(f"Error comparing schemas: {e}")
        return {
            "old_score": 0,
            "new_score": 0,
            "analysis": f"Error during comparison: {str(e)}"
        }
