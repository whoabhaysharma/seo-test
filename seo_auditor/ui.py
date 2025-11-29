import gradio as gr
import pandas as pd
import time
import json
import os
from urllib.parse import urlparse, urljoin

from .config import MAX_PAGES_TO_SCAN
from .crawler import check_robots_txt, fetch_sitemap_urls
from .analyzer import analyze_page
from .reporter import prepare_dataframe, save_excel
from .capturer import capture_screenshots, create_pdf
from .schema_gen import extract_schema_from_url, generate_schema_from_screenshot, compare_and_score_schemas
from .wordpress_api import WordPressClient

# Helper function to store state
schema_state = {}

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

def run_schema_analysis(urls_input, gemini_key, progress=gr.Progress()):
    global schema_state
    schema_state = {} # Reset state

    if not gemini_key:
        return "Please provide a Gemini API Key.", None, None

    urls = [u.strip() for u in urls_input.split(",") if u.strip()]
    if not urls:
        return "Please enter at least one URL.", None, None

    results = []

    for i, url in enumerate(urls):
        if not url.startswith("http"):
            url = "https://" + url

        progress((i+1) / len(urls), desc=f"Processing {url}...")

        # 1. Capture Screenshot (reuse capturer but for single)
        # We need a list for capturer
        screenshot_paths = capture_screenshots([url])
        if not screenshot_paths:
            results.append({"url": url, "error": "Screenshot failed"})
            continue

        screenshot_path = screenshot_paths[0] # Expect one

        # 2. Extract Existing Schema
        old_schema = extract_schema_from_url(url)

        # 3. Generate New Schema
        new_schema = generate_schema_from_screenshot(screenshot_path, gemini_key)

        # 4. Compare & Score
        comparison = compare_and_score_schemas(old_schema, new_schema, gemini_key)

        # Store in state
        schema_state[url] = new_schema

        # Format for display
        results.append({
            "url": url,
            "old_score": comparison.get("old_score", 0),
            "new_score": comparison.get("new_score", 0),
            "analysis": comparison.get("analysis", ""),
            "old_schema": json.dumps(old_schema, indent=2) if old_schema else "None",
            "new_schema": json.dumps(new_schema, indent=2)
        })

    # Create a nice summary string or markdown
    summary_md = ""
    for r in results:
        if "error" in r:
            summary_md += f"### ❌ {r['url']}\nError: {r['error']}\n\n---\n"
        else:
            summary_md += f"### ✅ {r['url']}\n"
            summary_md += f"- **Old Score:** {r['old_score']}/10\n"
            summary_md += f"- **New Score:** {r['new_score']}/10\n"
            summary_md += f"- **Analysis:** {r['analysis']}\n\n"
            summary_md += "<details><summary>View Schemas</summary>\n\n"
            summary_md += "#### Old Schema\n```json\n" + r['old_schema'] + "\n```\n"
            summary_md += "#### New Schema\n```json\n" + r['new_schema'] + "\n```\n"
            summary_md += "</details>\n\n---\n"

    return "Analysis Complete. Review results below.", summary_md, json.dumps(results, indent=2)


def run_schema_update(wp_url, wp_user, wp_app_pass, progress=gr.Progress()):
    global schema_state

    if not schema_state:
        return "No generated schemas found. Please run analysis first."

    if not wp_url or not wp_user or not wp_app_pass:
        return "Please provide WordPress credentials."

    client = WordPressClient(wp_url, wp_user, wp_app_pass)

    logs = ""
    success_count = 0

    for i, (url, schema) in enumerate(schema_state.items()):
        progress((i) / len(schema_state), desc=f"Updating {url}...")

        success, msg = client.update_schema_in_post(url, schema)
        status_icon = "✅" if success else "❌"
        logs += f"{status_icon} **{url}**: {msg}\n"
        if success:
            success_count += 1

    return f"Update Complete. {success_count}/{len(schema_state)} updated.\n\n" + logs

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
                gr.Markdown("Generate and Update JSON-LD Schema using AI and WordPress API.")

                with gr.Row():
                    gemini_key_input = gr.Textbox(label="Gemini API Key", type="password")

                with gr.Row():
                    wp_url_input = gr.Textbox(label="WordPress URL", placeholder="https://example.com")
                    wp_user_input = gr.Textbox(label="WP Username")
                    wp_pass_input = gr.Textbox(label="WP App Password", type="password")

                with gr.Row():
                    urls_input_schema = gr.Textbox(label="Target URL(s)", placeholder="https://example.com/page1, https://example.com/page2")
                    analyze_btn = gr.Button("1. Analyze & Generate Schema", variant="primary")

                schema_status = gr.Markdown("Ready to analyze.")
                schema_results_md = gr.Markdown("")
                # Hidden json output to store data if needed, but we use server-side state variable for simplicity in this demo
                # Note: Server-side global state is not multi-user safe in standard Gradio, but for local tool it's fine.
                # Ideally use gr.State() but that requires passing it around.

                update_btn = gr.Button("2. Confirm & Update on Website", variant="stop")
                update_status = gr.Markdown("")

                analyze_btn.click(
                    run_schema_analysis,
                    inputs=[urls_input_schema, gemini_key_input],
                    outputs=[schema_status, schema_results_md, gr.State()] # State is dummy output
                )

                update_btn.click(
                    run_schema_update,
                    inputs=[wp_url_input, wp_user_input, wp_pass_input],
                    outputs=[update_status]
                )

    return demo
