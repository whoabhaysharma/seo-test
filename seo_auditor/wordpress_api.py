import requests
import json
import base64
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WordPressClient:
    def __init__(self, base_url, username, app_password):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.app_password = app_password
        self.auth = (self.username, self.app_password)

    def find_post_id_by_url(self, url):
        """
        Attempts to find the Post ID for a given URL.
        It tries to match the slug.
        """
        try:
            # Extract slug from URL
            # e.g., https://example.com/my-page/ -> my-page
            # e.g., https://example.com/ -> home page? (Handling home is tricky)

            slug = url.strip('/').split('/')[-1]

            # If slug is empty (homepage), we need a different approach or assume 'home' or similar.
            # Usually front page doesn't have a slug in the URL structure easily map-able if it's just domain.
            # But let's try to search by slug first.

            if not slug:
                 # It might be the front page.
                 # Let's try to fetch pages and check link? Too many pages.
                 logger.warning(f"Could not extract slug from {url}. It might be the homepage.")
                 # Fallback: Assume it's a page and try to list pages to find matching link?
                 # No, better to warn.
                 return None

            # Try pages endpoint
            endpoint = f"{self.base_url}/wp-json/wp/v2/pages"
            params = {'slug': slug}
            response = requests.get(endpoint, params=params, auth=self.auth)

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return data[0]['id']

            # Try posts endpoint if page fails
            endpoint = f"{self.base_url}/wp-json/wp/v2/posts"
            response = requests.get(endpoint, params=params, auth=self.auth)

            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return data[0]['id']

            logger.warning(f"No post/page found for slug: {slug}")
            return None

        except Exception as e:
            logger.error(f"Error finding post ID: {e}")
            return None

    def update_post_content(self, post_id, new_content, is_page=True):
        """
        Updates the content of a post or page.
        """
        type_str = "pages" if is_page else "posts"
        endpoint = f"{self.base_url}/wp-json/wp/v2/{type_str}/{post_id}"

        data = {
            "content": new_content
        }

        try:
            response = requests.post(endpoint, json=data, auth=self.auth)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Error updating content: {e}")
            return False

    def get_post_content(self, post_id, is_page=True):
        type_str = "pages" if is_page else "posts"
        endpoint = f"{self.base_url}/wp-json/wp/v2/{type_str}/{post_id}"

        try:
            response = requests.get(endpoint, auth=self.auth)
            response.raise_for_status()
            return response.json()['content']['raw']
        except Exception as e:
            logger.error(f"Error fetching content: {e}")
            return None

    def update_schema_in_post(self, url, new_schema_json):
        """
        Finds the post/page for the URL, fetches content,
        appends/replaces the schema script, and updates it.
        """
        # 1. Find ID
        post_id = self.find_post_id_by_url(url)
        if not post_id:
            return False, "Could not find Post ID for this URL. Ensure it is a standard Post or Page."

        # 2. Get Content
        # We don't know if it is page or post. We found ID but need to know type.
        # find_post_id_by_url logic was simple. Let's assume Page first, then Post.
        # Actually find_post_id_by_url should return type.

        # Let's Refactor find_post_id to return (id, type)
        # But for now, let's just try both for get_content.

        content = self.get_post_content(post_id, is_page=True)
        is_page = True
        if content is None:
            content = self.get_post_content(post_id, is_page=False)
            is_page = False

        if content is None:
            return False, "Could not fetch content."

        # 3. Modify Content
        # Simple strategy: Append the script tag.
        # If we want to be smarter, we could regex remove existing <script type="application/ld+json">...</script>
        # but that is risky if there are multiple or specific ones we shouldn't touch.
        # However, the user asked to "update" the schema.
        # Let's try to remove any existing schema block that looks like it was added by us or is generic?
        # No, safest is to append. Google reads the last one or merges them.
        # But having two contradictory schemas is bad.
        # Let's try to strip ALL json-ld scripts? No, that might break plugins.

        # Decision: Append the new schema at the end of the content.
        # This will render it in the body.

        schema_script = f'\n\n<script type="application/ld+json">\n{json.dumps(new_schema_json, indent=2)}\n</script>'

        new_content = content + schema_script

        # 4. Update
        success = self.update_post_content(post_id, new_content, is_page=is_page)

        if success:
            return True, "Schema updated successfully (appended to content)."
        else:
            return False, "Failed to update content via API."
