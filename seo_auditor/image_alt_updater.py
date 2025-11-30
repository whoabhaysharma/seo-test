import requests
import os
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from .utils import get_session

def find_attachment_id_by_url(image_url, base_url, auth):
    """
    Queries WordPress API to find attachment ID by image URL.
    """
    try:
        # Extract filename and clean it (remove -300x200 suffix)
        path = urlparse(image_url).path
        filename = os.path.basename(path)
        name_without_ext = os.path.splitext(filename)[0]

        # Regex to remove dimension suffix like -300x200 or -1024x768
        # This regex looks for a hyphen followed by digits, 'x', digits, at the end of the name
        clean_name = re.sub(r'-\d+x\d+$', '', name_without_ext)

        api_url = f"{base_url}/wp-json/wp/v2/media"
        params = {
            "search": clean_name,
            "per_page": 20
        }

        resp = requests.get(api_url, params=params, auth=auth, timeout=10)
        if resp.status_code != 200:
            return None

        media_items = resp.json()

        for item in media_items:
            # Check full size URL
            if item.get('source_url') == image_url:
                return item.get('id')

            # Check sizes
            if 'media_details' in item and 'sizes' in item['media_details']:
                for size_name, size_data in item['media_details']['sizes'].items():
                    if size_data.get('source_url') == image_url:
                        return item.get('id')

            # Fallback: check if source_url ends with the filename we have
            # This is useful if protocol or domain differs slightly
            source_url = item.get('source_url', '')
            if source_url.endswith(filename):
                return item.get('id')

        return None
    except Exception as e:
        print(f"Error finding attachment ID: {e}")
        return None

def fetch_page_images(page_url, username=None, app_password=None):
    """
    Fetches all images from a given page URL.
    Returns a list of dicts with image info: {url, current_alt, attachment_id}
    If username/app_password are provided, it will attempt to find missing attachment IDs via API.
    """
    session = get_session()
    
    try:
        resp = session.get(page_url, timeout=10)
        if resp.status_code >= 400:
            return []
        
        soup = BeautifulSoup(resp.text, 'lxml')
        images = []
        
        # Prepare WP API info if credentials exist
        base_url = None
        auth = None
        if username and app_password:
            parsed = urlparse(page_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            auth = (username, app_password)

        for img in soup.find_all('img'):
            img_src = img.get('src', '')
            if not img_src:
                continue
            
            # Get current alt text
            current_alt = img.get('alt', '')
            
            # Try to extract attachment ID from WordPress classes
            attachment_id = None
            img_classes = img.get('class', [])
            if isinstance(img_classes, list):
                for cls in img_classes:
                    if cls.startswith('wp-image-'):
                        try:
                            attachment_id = int(cls.replace('wp-image-', ''))
                        except:
                            pass
            
            # If ID not found in class, try API if credentials provided
            if not attachment_id and auth and base_url:
                # Only try for local images (matching domain)
                if base_url in img_src or img_src.startswith('/'):
                    # Handle relative URLs
                    full_src = img_src
                    if img_src.startswith('/'):
                        full_src = f"{base_url}{img_src}"

                    attachment_id = find_attachment_id_by_url(full_src, base_url, auth)

            images.append({
                'url': img_src,
                'current_alt': current_alt,
                'attachment_id': attachment_id
            })
        
        return images
    
    except Exception as e:
        print(f"Error fetching images: {e}")
        return []

def update_image_alts(page_url, username, app_password, image_updates):
    """
    Updates alt text for images on a WordPress page.
    image_updates: list of dicts with {attachment_id, new_alt}
    Returns success status and message.
    """
    parsed = urlparse(page_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    
    auth = (username, app_password)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Gemini-SEO-Updater/1.0"
    }
    
    results = []
    
    for update in image_updates:
        attachment_id = update.get('attachment_id')
        new_alt = update.get('new_alt', '')
        
        if not attachment_id:
            results.append(f"⚠️ Skipped image (no ID found)")
            continue
        
        try:
            # Update via WordPress REST API
            update_url = f"{base_url}/wp-json/wp/v2/media/{attachment_id}"
            
            payload = {
                "alt_text": new_alt
            }
            
            resp = requests.post(update_url, auth=auth, json=payload, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                results.append(f"✅ Updated image ID {attachment_id}")
            else:
                results.append(f"❌ Failed to update ID {attachment_id}: {resp.status_code}")
        
        except Exception as e:
            results.append(f"❌ Error updating ID {attachment_id}: {str(e)}")
    
    return True, "\n".join(results)
