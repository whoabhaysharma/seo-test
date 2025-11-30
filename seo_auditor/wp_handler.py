import requests
import json
from urllib.parse import urlparse

def push_schema_to_wordpress(target_url, username, app_password, schema_json_str):
    """
    1. Derives slug from URL.
    2. Searches WP API for the Page/Post ID.
    3. Updates the 'custom_schema_json' meta field.
    """
    
    # 1. Parse URL to get domain and slug
    parsed = urlparse(target_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    
    # Simple slug extraction (removes trailing slash)
    path_parts = parsed.path.strip("/").split("/")
    slug = path_parts[-1] if path_parts else ""
    
    if not slug:
        # If slug is empty, it might be the homepage.
        # We will try to find the page by matching the 'link' field in the API response.
        pass # We'll handle this in the search loop below

    auth = (username, app_password)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Gemini-SEO-Updater/1.0"
    }

    # 2. Find the Post/Page ID
    # We check both 'pages' and 'posts' endpoints
    post_id = None
    post_type = None
    
    endpoints = ["pages", "posts"]
    
    try:
        for ep in endpoints:
            if slug:
                search_api = f"{base_url}/wp-json/wp/v2/{ep}?slug={slug}"
            else:
                # For homepage (empty slug), list pages and find matching link
                search_api = f"{base_url}/wp-json/wp/v2/{ep}"

            print(f"Searching: {search_api}") # Debug
            resp = requests.get(search_api, timeout=10)
            
            if resp.status_code == 200:
                results = resp.json()
                if results and len(results) > 0:
                    if slug:
                        # Exact slug match
                        post_id = results[0]['id']
                        post_type = ep
                        break
                    else:
                        # URL match for homepage
                        for item in results:
                            # Normalize URLs by stripping trailing slashes
                            if item['link'].rstrip('/') == target_url.rstrip('/'):
                                post_id = item['id']
                                post_type = ep
                                break
                    if post_id: break
        
        if not post_id:
            return False, f"Error: Could not find a Page or Post matching URL '{target_url}' on {base_url}"

        # 3. Update the Meta Field
        # Note: Ensure register_meta() in PHP has 'show_in_rest' => true
        update_url = f"{base_url}/wp-json/wp/v2/{post_type}/{post_id}"
        
        payload = {
            "meta": {
                "custom_schema_json": schema_json_str
            }
        }

        update_resp = requests.post(
            update_url, 
            auth=auth, 
            json=payload, 
            headers=headers
        )

        if update_resp.status_code == 200:
            return True, f"Success! Updated {post_type} ID {post_id}. Status: {update_resp.status_code}"
        else:
            return False, f"Failed to update. API Response: {update_resp.text}"

    except Exception as e:
        return False, f"Connection Error: {str(e)}"

def update_page_meta(target_url, username, app_password, new_title, new_desc):
    """
    Updates the Page Title and a custom meta description field.
    """
    # 1. Parse URL to get domain and slug
    parsed = urlparse(target_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    path_parts = parsed.path.strip("/").split("/")
    slug = path_parts[-1] if path_parts else ""
    
    auth = (username, app_password)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Gemini-SEO-Updater/1.0"
    }

    # 2. Find Post ID (Reuse logic or copy-paste for independence)
    post_id = None
    post_type = None
    endpoints = ["pages", "posts"]
    
    try:
        for ep in endpoints:
            if slug:
                search_api = f"{base_url}/wp-json/wp/v2/{ep}?slug={slug}"
            else:
                search_api = f"{base_url}/wp-json/wp/v2/{ep}"

            resp = requests.get(search_api, timeout=10)
            if resp.status_code == 200:
                results = resp.json()
                if results:
                    if slug:
                        post_id = results[0]['id']
                        post_type = ep
                        break
                    else:
                        for item in results:
                            if item['link'].rstrip('/') == target_url.rstrip('/'):
                                post_id = item['id']
                                post_type = ep
                                break
                    if post_id: break
        
        if not post_id:
            return False, f"ID not found for {target_url}"

        # 3. Update Title and Meta
        update_url = f"{base_url}/wp-json/wp/v2/{post_type}/{post_id}"
        
        # We try to update multiple common meta fields for SEO description
        # to support Yoast, RankMath, AIOSEO, and custom setups.
        meta_payload = {
            "custom_meta_description": new_desc,  # Legacy/Custom
            "_yoast_wpseo_metadesc": new_desc,    # Yoast SEO
            "rank_math_description": new_desc,    # RankMath
            "_aioseop_description": new_desc      # All in One SEO
        }

        payload = {
            "title": new_title,
            "meta": meta_payload
        }

        update_resp = requests.post(update_url, auth=auth, json=payload, headers=headers)
        
        if update_resp.status_code == 200:
            return True, f"Updated ID {post_id}"
        else:
            return False, f"Failed: {update_resp.text}"

    except Exception as e:
        return False, str(e)