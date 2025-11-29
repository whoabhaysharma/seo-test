import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from .utils import get_session

def fetch_page_images(page_url):
    """
    Fetches all images from a given page URL.
    Returns a list of dicts with image info: {url, current_alt, attachment_id}
    """
    session = get_session()
    
    try:
        resp = session.get(page_url, timeout=10)
        if resp.status_code >= 400:
            return []
        
        soup = BeautifulSoup(resp.text, 'lxml')
        images = []
        
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
