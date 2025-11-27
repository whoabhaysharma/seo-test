import os
import tempfile
import subprocess
import sys
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from PIL import Image

def _install_browsers():
    """
    Installs playwright browsers if they are missing.
    """
    print("Installing Playwright browsers...")
    try:
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        print("Browsers installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install browsers: {e}")

def _install_deps():
    """
    Installs playwright system dependencies.
    """
    print("Installing Playwright dependencies (requires sudo/root)...")
    try:
        subprocess.check_call([sys.executable, "-m", "playwright", "install-deps"])
        print("Dependencies installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")

def capture_screenshots(urls: list[str], progress=None) -> list[str]:
    """
    Captures full-page screenshots for a list of URLs.
    Returns a list of file paths to the screenshots.
    """
    screenshot_paths = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except PlaywrightError as e:
            error_str = str(e)
            if "Executable doesn't exist" in error_str:
                _install_browsers()
                browser = p.chromium.launch()
            elif "Host system is missing dependencies" in error_str:
                _install_deps()
                browser = p.chromium.launch()
            else:
                raise e

        context = browser.new_context(viewport={"width": 1280, "height": 1024})

        for i, url in enumerate(urls):
            if progress:
                progress((i + 1) / len(urls), desc=f"Capturing: {url}")
            try:
                page = context.new_page()
                # wait_until="domcontentloaded" is faster, but "networkidle" is safer for full rendering.
                # Using domcontentloaded + a small sleep or just networkidle if speed isn't critical.
                page.goto(url, timeout=30000, wait_until="networkidle")

                # Create a temp file path
                temp_dir = tempfile.gettempdir()
                # sanitize url for filename
                safe_name = "".join([c if c.isalnum() else "_" for c in url])[-50:]
                filename = f"screenshot_{i}_{safe_name}.png"
                filepath = os.path.join(temp_dir, filename)

                page.screenshot(path=filepath, full_page=True)
                screenshot_paths.append(filepath)
                page.close()
            except Exception as e:
                print(f"Failed to capture {url}: {e}")

        browser.close()

    return screenshot_paths

def create_pdf(image_paths: list[str], output_filename: str) -> str:
    """
    Combines a list of image paths into a single PDF.
    Returns the path to the PDF.
    """
    if not image_paths:
        return None

    images = []
    for path in image_paths:
        try:
            img = Image.open(path)
            # Convert to RGB (PDF doesn't support RGBA)
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            images.append(img)
        except Exception as e:
            print(f"Failed to load image {path}: {e}")

    if not images:
        return None

    # Save the first image and append the rest
    try:
        images[0].save(
            output_filename, "PDF", resolution=100.0, save_all=True, append_images=images[1:]
        )
        return output_filename
    except Exception as e:
        print(f"Failed to create PDF: {e}")
        return None
