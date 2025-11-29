import gradio as gr
import pandas as pd
import time
import json
from urllib.parse import urlparse, urljoin

from .config import MAX_PAGES_TO_SCAN
from .crawler import check_robots_txt, fetch_sitemap_urls
from .analyzer import analyze_page
from .reporter import prepare_dataframe, save_excel
from .capturer import capture_screenshots, create_pdf
from .schema_gen import generate_improved_schema

def run_audit_ui(target_url, progress=gr.Progress()):
    if not target_url.startswith("http"):
        target_url = "https://" + target_url

    parsed = urlparse(target_url)
    domain = parsed.netloc

    progress(0, desc="🔍 Scanning Robots.txt & Sitemap...")
    robots_ok = check_robots_txt(f"{parsed.scheme}://{domain}")

    # Find pages
    pages = {target_url}
    pages = fetch_sitemap_urls(urljoin(target_url, "/sitemap.xml"), pages)
    page_list = sorted(list(pages))[:MAX_PAGES_TO_SCAN]

    data = []
    # Audit phase
    for i, url in enumerate(page_list):
        progress((i+1) / len(page_list), desc=f"Analyzing: {url}")
        data.append(analyze_page(url, domain))

    df_raw = pd.DataFrame(data)

    # Organize columns (ALL columns included)
    df_final = prepare_dataframe(df_raw)

    timestamp = int(time.time())
    excel_filename = f"audit_{timestamp}.xlsx"
    save_excel(df_final, excel_filename)

    summary = f"""
    ### ✅ Audit Complete
    - **Target:** {target_url}
    - **Pages Scanned:** {len(df_final)}
    - **HTTPS:** {"✅ Secure" if 'https_ok' in df_final.columns and df_final['https_ok'].all() else "❌ Insecure pages found"}
    - **Robots.txt:** {"✅ Found" if robots_ok else "❌ Not Found"}
    """

    return summary, df_final, excel_filename

def run_capture_ui(target_url_input, capture_all, progress=gr.Progress()):
    # Split by comma and clean up
    urls = [u.strip() for u in target_url_input.split(",") if u.strip()]

    if not urls:
        return "Please enter at least one URL.", None

    # Handle first URL for sitemap logic if needed
    first_url = urls[0]
    if not first_url.startswith("http"):
        first_url = "https://" + first_url

    page_list = []

    if capture_all:
        progress(0, desc="🔍 Scanning Sitemap for Pages...")
        parsed = urlparse(first_url)
        domain_url = f"{parsed.scheme}://{parsed.netloc}"

        # Use set to avoid duplicates
        pages = {first_url}
        # Try to fetch sitemap from the domain of the first URL
        pages = fetch_sitemap_urls(urljoin(domain_url, "/sitemap.xml"), pages)
        page_list = sorted(list(pages))[:MAX_PAGES_TO_SCAN]
    else:
        # Just use the provided list, ensuring they have http/https
        for u in urls:
            if not u.startswith("http"):
                u = "https://" + u
            page_list.append(u)
        # Remove duplicates if any
        page_list = sorted(list(set(page_list)))

    timestamp = int(time.time())

    progress(0, desc="📸 Capturing Screenshots...")
    screenshot_paths = capture_screenshots(page_list, progress=progress)

    pdf_path = None
    status_msg = f"No screenshots captured. Found {len(page_list)} pages."

    if screenshot_paths:
        pdf_filename = f"website_capture_{timestamp}.pdf"
        pdf_path = create_pdf(screenshot_paths, pdf_filename)
        if pdf_path:
             status_msg = f"""
            ### ✅ Capture Complete
            - **Target:** {target_url_input}
            - **Pages Captured:** {len(screenshot_paths)}
            - **PDF Created:** {pdf_filename}
            """

    return status_msg, pdf_path

def run_schema_update(url, api_key, progress=gr.Progress()):
    if not url:
        return "Please enter a URL.", "", ""
    if not api_key:
        return "Please enter a Gemini API Key.", "", ""

    if not url.startswith("http"):
        url = "https://" + url

    progress(0, desc="🚀 Initializing...")

    old_schema, new_schema = generate_improved_schema(url, api_key)

    return "✅ Generation Complete. Review changes below.", old_schema, new_schema

def save_new_schema(new_schema_content):
    if not new_schema_content:
        return None

    filename = f"new_schema_{int(time.time())}.json"
    with open(filename, "w") as f:
        f.write(new_schema_content)

    return filename

def create_ui():
    with gr.Blocks(title="Advanced SEO Auditor", theme=gr.themes.Soft(primary_hue="blue")) as demo:
        gr.Markdown("# 🚀 Advanced SEO Auditor")

        with gr.Tabs():
            # Tab 1: Audit Report
            with gr.Tab("Audit Report"):
                gr.Markdown("Full Scan: Sitemaps, HTTPS, Schema Types, Page Size, Broken Links, plus all standard Meta checks.")

                with gr.Row():
                    url_input_audit = gr.Textbox(label="Website URL", placeholder="https://example.com")
                    audit_btn = gr.Button("Start Audit", variant="primary")

                status_output_audit = gr.Markdown("Ready to scan.")

                with gr.Row():
                    download_btn_audit = gr.File(label="Download Excel Report")

                # WRAP=FALSE enables horizontal scrolling
                with gr.Row():
                    data_preview = gr.Dataframe(
                        label="Live Results (Scroll Right ->)",
                        interactive=False,
                        wrap=False
                    )

                audit_btn.click(
                    run_audit_ui,
                    inputs=[url_input_audit],
                    outputs=[status_output_audit, data_preview, download_btn_audit]
                )

            # Tab 2: PDF Creation
            with gr.Tab("PDF Capture"):
                gr.Markdown("Capture full-page screenshots of pages and compile them into a PDF.")

                with gr.Row():
                    url_input_capture = gr.Textbox(label="Website URL(s)", placeholder="https://example.com, https://example.com/page2")
                    capture_all_checkbox = gr.Checkbox(label="Capture all pages from sitemap (using domain from first URL)")
                    capture_btn = gr.Button("Capture & Create PDF", variant="primary")

                status_output_capture = gr.Markdown("Ready to capture.")

                with gr.Row():
                    download_btn_capture = gr.File(label="Download PDF")

                capture_btn.click(
                    run_capture_ui,
                    inputs=[url_input_capture, capture_all_checkbox],
                    outputs=[status_output_capture, download_btn_capture]
                )

            # Tab 3: Schema Updater
            with gr.Tab("Schema Updater"):
                gr.Markdown("Capture a page screenshot, analyze existing Schema, and generate an improved JSON-LD schema using Google Gemini.")

                with gr.Row():
                    url_input_schema = gr.Textbox(label="Page URL", placeholder="https://example.com/product/1")
                    api_key_input = gr.Textbox(label="Gemini API Key", placeholder="Enter your Google Gemini API Key", type="password")

                generate_schema_btn = gr.Button("Generate Improved Schema", variant="primary")

                schema_status = gr.Markdown("")

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Current Schema")
                        old_schema_display = gr.Code(language="json", label="Current JSON-LD")
                    with gr.Column():
                        gr.Markdown("### Improved Schema (Gemini)")
                        new_schema_display = gr.Code(language="json", label="Generated JSON-LD", interactive=True)

                with gr.Row():
                    save_schema_btn = gr.Button("Confirm & Save New Schema")
                    download_schema_file = gr.File(label="Download JSON")

                generate_schema_btn.click(
                    run_schema_update,
                    inputs=[url_input_schema, api_key_input],
                    outputs=[schema_status, old_schema_display, new_schema_display]
                )

                save_schema_btn.click(
                    save_new_schema,
                    inputs=[new_schema_display],
                    outputs=[download_schema_file]
                )

    return demo
