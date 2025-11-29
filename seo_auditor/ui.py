import gradio as gr
import pandas as pd
import time
import json
from urllib.parse import urlparse, urljoin

# Import your local modules
from .config import MAX_PAGES_TO_SCAN
from .crawler import check_robots_txt, fetch_sitemap_urls
from .analyzer import analyze_page
from .reporter import prepare_dataframe, save_excel
from .capturer import capture_screenshots, create_pdf
from .schema_gen import generate_improved_schema

# --- ORIGINAL FUNCTION 1: AUDIT ---
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

# --- ORIGINAL FUNCTION 2: CAPTURE ---
def run_capture_ui(target_url_input, capture_all, progress=gr.Progress()):
    urls = [u.strip() for u in target_url_input.split(",") if u.strip()]
    if not urls:
        return "Please enter at least one URL.", None

    first_url = urls[0]
    if not first_url.startswith("http"):
        first_url = "https://" + first_url

    page_list = []

    if capture_all:
        progress(0, desc="🔍 Scanning Sitemap for Pages...")
        parsed = urlparse(first_url)
        domain_url = f"{parsed.scheme}://{parsed.netloc}"
        pages = {first_url}
        pages = fetch_sitemap_urls(urljoin(domain_url, "/sitemap.xml"), pages)
        page_list = sorted(list(pages))[:MAX_PAGES_TO_SCAN]
    else:
        for u in urls:
            if not u.startswith("http"):
                u = "https://" + u
            page_list.append(u)
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

# --- UPDATED FUNCTION 3: SCHEMA GENERATION ---
def run_schema_update(url, api_key, progress=gr.Progress()):
    if not url:
        return "Please enter a URL.", "", "", 0, 0
    if not api_key:
        return "Please enter a Gemini API Key.", "", "", 0, 0

    if not url.startswith("http"):
        url = "https://" + url

    progress(0, desc="🚀 Initializing...")

    # Now returns 5 values
    old_schema, new_schema, old_score, new_score, summary = generate_improved_schema(url, api_key)

    # Format status message
    status_text = f"✅ Analysis Complete.\nSummary: {summary}"

    return status_text, old_schema, new_schema, old_score, new_score

# --- NEW FUNCTION 4: CONFIRM UPDATE ---
def confirm_and_update(url, new_schema_content):
    if not new_schema_content:
        return "Error: No schema content.", None

    # 1. Save Backup
    filename = f"new_schema_{int(time.time())}.json"
    with open(filename, "w") as f:
        f.write(new_schema_content)

    # 2. Update Logic (Simulated for now - add your Requests/WordPress code here)
    # Example:
    # response = requests.post(f"{url}/wp-json/custom/v1/update_schema", json=json.loads(new_schema_content))
    
    log = f"✅ Backup saved to {filename}\n✅ Schema update trigger sent to {url} (Simulated)"
    
    return log, filename

# --- UI BUILDER ---
def create_ui():
    with gr.Blocks(title="Advanced SEO Auditor", theme=gr.themes.Soft(primary_hue="blue")) as demo:
        gr.Markdown("# 🚀 Advanced SEO Auditor")

        with gr.Tabs():
            # Tab 1: Audit
            with gr.Tab("Audit Report"):
                gr.Markdown("Full Scan: Sitemaps, HTTPS, Schema Types, etc.")
                with gr.Row():
                    url_input_audit = gr.Textbox(label="Website URL", placeholder="[https://example.com](https://example.com)")
                    audit_btn = gr.Button("Start Audit", variant="primary")
                status_output_audit = gr.Markdown("Ready to scan.")
                with gr.Row():
                    download_btn_audit = gr.File(label="Download Excel Report")
                with gr.Row():
                    data_preview = gr.Dataframe(label="Live Results", interactive=False, wrap=False)
                
                audit_btn.click(
                    run_audit_ui,
                    inputs=[url_input_audit],
                    outputs=[status_output_audit, data_preview, download_btn_audit]
                )

            # Tab 2: Capture
            with gr.Tab("PDF Capture"):
                gr.Markdown("Capture screenshots to PDF.")
                with gr.Row():
                    url_input_capture = gr.Textbox(label="Website URL(s)")
                    capture_all_checkbox = gr.Checkbox(label="Capture all pages from sitemap")
                    capture_btn = gr.Button("Capture & Create PDF", variant="primary")
                status_output_capture = gr.Markdown("Ready to capture.")
                with gr.Row():
                    download_btn_capture = gr.File(label="Download PDF")
                
                capture_btn.click(
                    run_capture_ui,
                    inputs=[url_input_capture, capture_all_checkbox],
                    outputs=[status_output_capture, download_btn_capture]
                )

            # Tab 3: Schema Updater (UPDATED)
            with gr.Tab("Schema Updater"):
                gr.Markdown("Capture page, analyze via Gemini, and Auto-Update.")

                with gr.Row():
                    url_input_schema = gr.Textbox(label="Page URL", placeholder="[https://example.com/product/1](https://example.com/product/1)")
                    api_key_input = gr.Textbox(label="Gemini API Key", type="password")

                generate_schema_btn = gr.Button("Generate Improved Schema", variant="primary")
                schema_status = gr.Markdown("Waiting...")

                # New Score Display
                with gr.Row():
                    old_score_disp = gr.Label(label="Old Score")
                    new_score_disp = gr.Label(label="New Score")

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Current Schema")
                        old_schema_display = gr.Code(language="json", label="Current JSON-LD", interactive=False)
                    with gr.Column():
                        gr.Markdown("### Improved Schema")
                        new_schema_display = gr.Code(language="json", label="Generated JSON-LD", interactive=True)

                with gr.Row():
                    save_schema_btn = gr.Button("✅ Confirm & Update Live Site", variant="stop")
                    download_schema_file = gr.File(label="Download Backup")
                
                update_log = gr.Textbox(label="Update Logs", interactive=False)

                # Connect Logic
                generate_schema_btn.click(
                    run_schema_update,
                    inputs=[url_input_schema, api_key_input],
                    outputs=[schema_status, old_schema_display, new_schema_display, old_score_disp, new_score_disp]
                )

                save_schema_btn.click(
                    confirm_and_update,
                    inputs=[url_input_schema, new_schema_display],
                    outputs=[update_log, download_schema_file]
                )

    return demo