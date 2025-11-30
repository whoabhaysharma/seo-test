import requests
import json
from urllib.parse import urlparse

def find_post_id_by_url(target_url, auth=None):
    """
    Finds the WordPress Post or Page ID for a given URL.
    Returns (post_id, post_type, error_message).
    """
    parsed = urlparse(target_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    path_parts = parsed.path.strip("/").split("/")
    slug = path_parts[-1] if path_parts else ""
    
    endpoints = ["pages", "posts"]
    
    for ep in endpoints:
        if slug:
            search_api = f"{base_url}/wp-json/wp/v2/{ep}?slug={slug}"
        else:
            # For homepage (empty slug), list pages/posts to find match
            search_api = f"{base_url}/wp-json/wp/v2/{ep}"

        try:
            resp = requests.get(search_api, auth=auth, timeout=10)
            
            if resp.status_code == 200:
                results = resp.json()
                if results and len(results) > 0:
                    if slug:
                        # Exact slug match
                        return results[0]['id'], ep, None
                    else:
                        # URL match for homepage or if slug lookup was ambiguous
                        for item in results:
                            # Normalize URLs by stripping trailing slashes
                            if item['link'].rstrip('/') == target_url.rstrip('/'):
                                return item['id'], ep, None
        except Exception as e:
            # Continue to next endpoint if one fails, but log/return error if all fail?
            # For now just continue search
            pass

    return None, None, f"Error: Could not find a Page or Post matching URL '{target_url}' on {base_url}"

def push_schema_to_wordpress(target_url, username, app_password, schema_json_str):
    """
    1. Derives slug from URL.
    2. Searches WP API for the Page/Post ID.
    3. Updates the 'custom_schema_json' meta field.
    """

    parsed = urlparse(target_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    auth = (username, app_password)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Gemini-SEO-Updater/1.0"
    }

    # 2. Find the Post/Page ID
    post_id, post_type, error_msg = find_post_id_by_url(target_url, auth=None)

    if not post_id:
        return False, error_msg

    # 3. Update the Meta Field
    try:
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
    parsed = urlparse(target_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    auth = (username, app_password)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Gemini-SEO-Updater/1.0"
    }

    # 2. Find Post ID
    post_id, post_type, error_msg = find_post_id_by_url(target_url, auth=None)
    
    if not post_id:
        return False, f"ID not found for {target_url}: {error_msg}"

    # 3. Update Title and Meta
    try:
        update_url = f"{base_url}/wp-json/wp/v2/{post_type}/{post_id}"
        
        # We try to update multiple common meta fields for SEO description
        meta_payload = {
            "custom_meta_description": new_desc,  # Legacy/Custom
            "_yoast_wpseo_metadesc": new_desc,    # Yoast SEO
            "rank_math_description": new_desc,    # RankMath
            "_aioseop_description": new_desc,      # All in One SEO
            "description": new_desc
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
