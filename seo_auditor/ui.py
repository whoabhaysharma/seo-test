import gradio as gr
import pandas as pd
import time
from urllib.parse import urlparse, urljoin

from .config import MAX_PAGES_TO_SCAN
from .crawler import check_robots_txt, fetch_sitemap_urls
from .analyzer import analyze_page
from .reporter import prepare_dataframe, save_excel
from .capturer import capture_screenshots, create_pdf

def run_audit_ui(target_url, capture_site=False, progress=gr.Progress()):
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

    output_files = [excel_filename]

    # Capture phase
    if capture_site:
        progress(0, desc="📸 Capturing Screenshots...")
        screenshot_paths = capture_screenshots(page_list, progress=progress)

        if screenshot_paths:
            pdf_filename = f"website_capture_{timestamp}.pdf"
            pdf_path = create_pdf(screenshot_paths, pdf_filename)
            if pdf_path:
                output_files.append(pdf_path)

    summary = f"""
    ### ✅ Audit Complete
    - **Target:** {target_url}
    - **Pages Scanned:** {len(df_final)}
    - **HTTPS:** {"✅ Secure" if 'https_ok' in df_final.columns and df_final['https_ok'].all() else "❌ Insecure pages found"}
    - **Robots.txt:** {"✅ Found" if robots_ok else "❌ Not Found"}
    """
    if capture_site:
        summary += f"\n- **Screenshots Captured:** {len(output_files) > 1}"

    # Return FULL dataframe for the UI
    return summary, df_final, output_files

def create_ui():
    with gr.Blocks(title="Advanced SEO Auditor", theme=gr.themes.Soft(primary_hue="blue")) as demo:
        gr.Markdown("# 🚀 Advanced SEO Auditor")

        with gr.Tabs():
            with gr.Tab("Website Auditor"):
                gr.Markdown("Full Scan: Sitemaps, HTTPS, Schema Types, Page Size, Broken Links, plus all standard Meta checks.")

                with gr.Row():
                    url_input = gr.Textbox(label="Website URL", placeholder="https://example.com")
                    capture_checkbox = gr.Checkbox(label="Capture Website (Create PDF of screenshots)", value=False)
                    audit_btn = gr.Button("Start Audit", variant="primary")

                status_output = gr.Markdown("Ready to scan.")

                with gr.Row():
                    download_btn = gr.File(label="Download Report(s)", file_count="multiple")

                # WRAP=FALSE enables horizontal scrolling
                with gr.Row():
                    data_preview = gr.Dataframe(
                        label="Live Results (Scroll Right ->)",
                        interactive=False,
                        wrap=False
                    )

                audit_btn.click(
                    run_audit_ui,
                    inputs=[url_input, capture_checkbox],
                    outputs=[status_output, data_preview, download_btn]
                )

            # Placeholder for future tools
            # with gr.Tab("Other Tool"):
            #     gr.Markdown("Coming Soon...")

    return demo
