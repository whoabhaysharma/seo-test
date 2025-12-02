import os
import tempfile
import subprocess
import sys
import asyncio
from playwright.async_api import async_playwright, Error as PlaywrightError
from PIL import Image

def _install_browsers():
    """
    Installs playwright browsers if they are missing.
    Returns True if successful, False otherwise.
    """
    print("Installing Playwright browsers...")
    try:
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        print("Browsers installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install browsers: {e}")
        return False

def _install_deps():
    """
    Installs playwright system dependencies.
    Returns True if successful, False otherwise.
    """
    print("Installing Playwright dependencies (requires sudo/root)...")
    try:
        subprocess.check_call([sys.executable, "-m", "playwright", "install-deps"])
        print("Dependencies installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        return False

async def capture_screenshots(urls: list[str], progress=None) -> list[str]:
    """
    Captures full-page screenshots for a list of URLs concurrently.
    Returns a list of file paths to the screenshots.
    """
    launch_args = ["--no-sandbox", "--disable-setuid-sandbox"]

    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(args=launch_args)
        except PlaywrightError as e:
            error_str = str(e)
            installed = False
            if "Executable doesn't exist" in error_str:
                if _install_browsers():
                    installed = True
            elif "Host system is missing dependencies" in error_str:
                if _install_deps():
                    installed = True

            if installed:
                try:
                    browser = await p.chromium.launch(args=launch_args)
                except PlaywrightError as e2:
                    print(f"Failed to launch browser after installation attempts: {e2}")
                    return []
            else:
                print(f"Browser launch failed: {e}")
                return []

        context = await browser.new_context(viewport={"width": 1280, "height": 1024})
        sem = asyncio.Semaphore(5)

        async def capture_task(idx, url):
            async with sem:
                try:
                    page = await context.new_page()
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    temp_dir = tempfile.gettempdir()
                    safe_name = "".join([c if c.isalnum() else "_" for c in url])[-50:]
                    filename = f"screenshot_{idx}_{safe_name}.png"
                    filepath = os.path.join(temp_dir, filename)
                    await page.screenshot(path=filepath, full_page=True)
                    await page.close()
                    return (idx, filepath)
                except Exception as e:
                    print(f"Failed to capture {url}: {e}")
                    return (idx, None)

        tasks = [capture_task(i, url) for i, url in enumerate(urls)]

        results = []
        if progress:
            # Manually tracking progress
            for f in asyncio.as_completed(tasks):
                res = await f
                results.append(res)
                progress(len(results) / len(urls), desc=f"Captured {len(results)}/{len(urls)}")
        else:
            results = await asyncio.gather(*tasks)

        await browser.close()

    # Sort results by index to maintain original URL order
    results.sort(key=lambda x: x[0])

    # Filter out None and return only paths
    return [path for idx, path in results if path]

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
