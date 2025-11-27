import gradio as gr
import pandas as pd
import time
from urllib.parse import urlparse, urljoin

from .config import MAX_PAGES_TO_SCAN
from .crawler import check_robots_txt, fetch_sitemap_urls
from .analyzer import analyze_page
from .reporter import prepare_dataframe, save_excel

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
    for i, url in enumerate(page_list):
        progress((i+1) / len(page_list), desc=f"Analyzing: {url}")
        data.append(analyze_page(url, domain))

    df_raw = pd.DataFrame(data)

    # Organize columns (ALL columns included)
    df_final = prepare_dataframe(df_raw)

    filename = f"audit_{int(time.time())}.xlsx"
    save_excel(df_final, filename)

    summary = f"""
    ### ✅ Audit Complete
    - **Target:** {target_url}
    - **Pages Scanned:** {len(df_final)}
    - **HTTPS:** {"✅ Secure" if 'https_ok' in df_final.columns and df_final['https_ok'].all() else "❌ Insecure pages found"}
    - **Robots.txt:** {"✅ Found" if robots_ok else "❌ Not Found"}
    """

    # Return FULL dataframe for the UI
    return summary, df_final, filename

def create_ui():
    with gr.Blocks(title="Advanced SEO Auditor", theme=gr.themes.Soft(primary_hue="blue")) as demo:
        gr.Markdown("# 🚀 Advanced SEO Auditor")
        gr.Markdown("Full Scan: Sitemaps, HTTPS, Schema Types, Page Size, Broken Links, plus all standard Meta checks.")

        with gr.Row():
            url_input = gr.Textbox(label="Website URL", placeholder="https://example.com")
            audit_btn = gr.Button("Start Audit", variant="primary")

        status_output = gr.Markdown("Ready to scan.")

        with gr.Row():
            download_btn = gr.File(label="Download Complete Excel Report")

        # WRAP=FALSE enables horizontal scrolling
        with gr.Row():
            data_preview = gr.Dataframe(
                label="Live Results (Scroll Right ->)",
                interactive=False,
                wrap=False
            )

        audit_btn.click(
            run_audit_ui,
            inputs=[url_input],
            outputs=[status_output, data_preview, download_btn]
        )
    return demo
