import gradio as gr
import pandas as pd
import time
from urllib.parse import urlparse, urljoin

from .config import MAX_PAGES_TO_SCAN
from .crawler import check_robots_txt, fetch_sitemap_urls
from .analyzer import analyze_page
from .reporter import prepare_dataframe, save_excel
from .capturer import capture_screenshots, create_pdf

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

def run_capture_ui(target_url, progress=gr.Progress()):
    if not target_url.startswith("http"):
        target_url = "https://" + target_url

    progress(0, desc="🔍 Scanning Sitemap for Pages...")
    pages = {target_url}
    pages = fetch_sitemap_urls(urljoin(target_url, "/sitemap.xml"), pages)
    page_list = sorted(list(pages))[:MAX_PAGES_TO_SCAN]

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
            - **Target:** {target_url}
            - **Pages Captured:** {len(screenshot_paths)}
            - **PDF Created:** {pdf_filename}
            """

    return status_msg, pdf_path

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
                gr.Markdown("Capture full-page screenshots of all pages found in the sitemap and compile them into a PDF.")

                with gr.Row():
                    url_input_capture = gr.Textbox(label="Website URL", placeholder="https://example.com")
                    capture_btn = gr.Button("Capture & Create PDF", variant="primary")

                status_output_capture = gr.Markdown("Ready to capture.")

                with gr.Row():
                    download_btn_capture = gr.File(label="Download PDF")

                capture_btn.click(
                    run_capture_ui,
                    inputs=[url_input_capture],
                    outputs=[status_output_capture, download_btn_capture]
                )

    return demo
