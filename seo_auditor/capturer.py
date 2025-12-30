import os
import tempfile
import subprocess
import sys
import asyncio
import zipfile
import shutil
from playwright.async_api import async_playwright, Error as PlaywrightError
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
import io

def _install_browsers():
    """Installs playwright browsers if they are missing."""
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
    NOTE: This often requires root/sudo. If this fails in a restricted environment
    (like Hugging Face Spaces), you must use 'packages.txt'.
    """
    print("Installing Playwright dependencies...")
    try:
        # Try installing only chromium dependencies to be faster
        subprocess.check_call([sys.executable, "-m", "playwright", "install-deps", "chromium"])
        print("Dependencies installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        return False

async def capture_screenshots(urls: list[str], progress=None, output_folder: str = None) -> tuple[str, list[str]]:
    """
    Captures full-page screenshots for a list of URLs concurrently.
    """
    # Added --single-process and --no-zygote for better container compatibility
    launch_args = [
        "--no-sandbox", 
        "--disable-setuid-sandbox", 
        "--disable-dev-shm-usage",
        "--single-process", 
        "--no-zygote"
    ]
    
    if output_folder is None:
        import time
        timestamp = int(time.time())
        output_folder = os.path.join(tempfile.gettempdir(), f"screenshots_{timestamp}")
    
    os.makedirs(output_folder, exist_ok=True)

    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(args=launch_args)
        except PlaywrightError as e:
            error_str = str(e)
            print(f"Initial launch failed: {error_str}")
            
            installed = False
            # Check for various missing component errors
            if "Executable doesn't exist" in error_str:
                if _install_browsers():
                    installed = True
            # FIX: Specifically catch shared library errors (libatk, libgbm, etc.)
            elif "Host system is missing dependencies" in error_str or "error while loading shared libraries" in error_str:
                if _install_deps():
                    installed = True
            
            # If we think we fixed it, try launching again
            if installed:
                try:
                    print("Retrying browser launch...")
                    browser = await p.chromium.launch(args=launch_args)
                except PlaywrightError as e2:
                    print(f"CRITICAL: Failed to launch browser after installation attempts: {e2}")
                    return (output_folder, [])
            else:
                # If we couldn't install deps (e.g., no sudo), we return empty
                print("Could not resolve browser dependencies automatically.")
                return (output_folder, [])

        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 1024},
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )

            sem = asyncio.Semaphore(5)

            async def capture_task(idx, url):
                async with sem:
                    try:
                        print(f"Starting capture for: {url}")
                        page = await context.new_page()
                        # Increased timeout to 60s for slow sites
                        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                        filename = f"{idx + 1}.png"
                        filepath = os.path.join(output_folder, filename)
                        await page.screenshot(path=filepath, full_page=True)
                        await page.close()
                        print(f"Saved: {filename}")
                        return (idx, filepath)
                    except Exception as e:
                        print(f"ERROR: Failed to capture {url}: {e}")
                        return (idx, None)

            tasks = [capture_task(i, url) for i, url in enumerate(urls)]

            results = []
            completed_count = 0
            total_count = len(urls)
            
            for f in asyncio.as_completed(tasks):
                res = await f
                results.append(res)
                completed_count += 1
                if progress:
                    try:
                        progress(completed_count / total_count, desc=f"📸 Captured {completed_count}/{total_count}")
                    except: pass
        finally:
            if browser:
                await browser.close()

    results.sort(key=lambda x: x[0])
    screenshot_paths = [path for idx, path in results if path]
    
    if not screenshot_paths:
        print("WARNING: No screenshots were captured successfully.")
        
    return (output_folder, screenshot_paths)

def _compress_image(path):
    try:
        img = Image.open(path)
        size_kb = os.path.getsize(path) / 1024
        if size_kb < 100:
            return img.convert('RGB') if img.mode == 'RGBA' else img
        
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        
        if img.width > 2000:
            ratio = 2000 / img.width
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        return img
    except Exception as e:
        print(f"Failed to compress image {path}: {e}")
        return None

def create_zip(folder_path: str, output_filename: str = None) -> str:
    if not folder_path or not os.path.exists(folder_path):
        return None
    
    image_files = sorted(
        [f for f in os.listdir(folder_path) if f.endswith('.png')],
        key=lambda x: int(x.replace('.png', '')) if x.replace('.png', '').isdigit() else 0
    )
    
    if not image_files:
        print("No images found to ZIP")
        return None
    
    if output_filename is None:
        import time
        output_filename = f"screenshots_{int(time.time())}.zip"
    
    try:
        with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for img_file in image_files:
                img_path = os.path.join(folder_path, img_file)
                zipf.write(img_path, img_file)
        return output_filename
    except Exception as e:
        print(f"ZIP creation error: {e}")
        return None

def create_pdf(image_paths: list[str], output_filename: str) -> str:
    if not image_paths:
        print("Error: No image paths provided for PDF creation.")
        return None

    try:
        images = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            compressed = list(executor.map(_compress_image, image_paths))
            images = [img for img in compressed if img is not None]

        if not images:
            print("Error: No valid images processed for PDF.")
            return None

        jpeg_images = []
        for img in images:
            try:
                jpeg_img = img.convert('RGB')
                jpeg_images.append(jpeg_img)
            except Exception as e:
                print(f"Conversion error: {e}")

        if not jpeg_images:
            return None

        jpeg_images[0].save(
            output_filename,
            "PDF",
            resolution=100.0,
            save_all=True,
            append_images=jpeg_images[1:],
            optimize=True,
            quality=80
        )
        return output_filename
    except Exception as e:
        print(f"PDF creation error: {e}")
        return None
