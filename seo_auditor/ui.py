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
from .wp_handler import push_schema_to_wordpress, update_page_meta # <--- UPDATED IMPORT
from .meta_gen import generate_meta_tags # <--- NEW IMPORT

# --- FUNCTION 1: AUDIT ---
def run_audit_ui(start_url, max_pages, progress=gr.Progress()):
    if not start_url:
        return None, None, "Please enter a URL."
    
    if not start_url.startswith("http"):
        start_url = "https://" + start_url
        
    domain_netloc = urlparse(start_url).netloc
    
    # 1. Discovery
    progress(0.1, desc="🔍 Discovering pages...")
    urls_to_scan = [start_url]
    
    # Try sitemap
    sitemap_url = urljoin(start_url, "sitemap.xml")
    found_sitemap = fetch_sitemap_urls(sitemap_url)
    if found_sitemap:
        urls_to_scan = list(found_sitemap)
    
    # Limit
    if max_pages > 0:
        urls_to_scan = urls_to_scan[:int(max_pages)]
        
    # 2. Analysis
    results = []
    for i, url in enumerate(urls_to_scan):
        progress((i + 1) / len(urls_to_scan), desc=f"Analyzing {url}")
        res = analyze_page(url, domain_netloc)
        results.append(res)
        
    # 3. Report
    df = pd.DataFrame(results)
    df_display = prepare_dataframe(df)
    
    # Save Excel
    timestamp = int(time.time())
    filename = f"audit_report_{timestamp}.xlsx"
    save_excel(df_display, filename)
    
    return df_display, filename, f"✅ Audit Complete. Scanned {len(urls_to_scan)} pages."

# --- FUNCTION 2: CAPTURE ---
def run_capture_ui(url, progress=gr.Progress()):
    if not url:
        return None, None, "Please enter a URL."
        
    if not url.startswith("http"):
        url = "https://" + url
        
    progress(0.2, desc="📸 Capturing Screenshot...")
    
    # Capture
    screenshot_paths = capture_screenshots([url], progress=progress)
    
    if not screenshot_paths:
        return None, None, "❌ Failed to capture screenshot."
        
    # Create PDF
    progress(0.8, desc="📄 Generating PDF...")
    pdf_filename = f"capture_{int(time.time())}.pdf"
    pdf_path = create_pdf(screenshot_paths, pdf_filename)
    
    return screenshot_paths, pdf_path, "✅ Capture Complete."

# --- UPDATED FUNCTION 3: SCHEMA GENERATION ---
def run_schema_update(url, api_key, progress=gr.Progress()):
    if not url:
        return "Please enter a URL.", "", "", 0, 0
    if not api_key:
        return "Please enter a Gemini API Key.", "", "", 0, 0

    if not url.startswith("http"):
        url = "https://" + url

    progress(0, desc="🚀 Initializing...")
    
    # Returns 5 values: old_schema, new_schema_str, old_score, new_score, summary
    old_schema, new_schema, old_score, new_score, summary = generate_improved_schema(url, api_key)

    status_text = f"✅ Analysis Complete.\nSummary: {summary}"

    return status_text, old_schema, new_schema, old_score, new_score

# --- NEW FUNCTION 4: CONFIRM & PUSH TO WORDPRESS ---
def confirm_and_update(url, new_schema_content, wp_user, wp_pass):
    if not new_schema_content:
        return "Error: No schema content generated yet.", None

    if not wp_user or not wp_pass:
        return "Error: WordPress Username and App Password are required.", None

    if not url.startswith("http"):
        url = "https://" + url

    # 1. Save Local Backup
    timestamp = int(time.time())
    filename = f"backup_schema_{timestamp}.json"
    try:
        with open(filename, "w") as f:
            f.write(new_schema_content)
    except Exception as e:
        return f"Error saving local backup: {e}", None

    # 2. Push to Live Site
    success, message = push_schema_to_wordpress(url, wp_user, wp_pass, new_schema_content)
    
    if success:
        log_msg = f"✅ LIVE UPDATE SUCCESSFUL!\n{message}\n📁 Backup saved: {filename}"
    else:
        log_msg = f"❌ UPDATE FAILED\n{message}\n📁 Backup saved: {filename}"
    
    return log_msg, filename
    
# --- NEW FUNCTION 5: AUTO-FIX LOOP ---
def auto_fix_schema(url, api_key, wp_user, wp_pass, progress=gr.Progress()):
    if not url or not api_key or not wp_user or not wp_pass:
        return "Error: All fields (URL, API Key, WP User, WP Pass) are required for Auto-Fix.", "", "", 0, 0

    if not url.startswith("http"):
        url = "https://" + url

    progress(0.1, desc="🔍 Analyzing & Generating Schema...")
    
    # 1. Generate Schema
    old_schema, new_schema_str, old_score, new_score, summary = generate_improved_schema(url, api_key)
    
    # Check if generation failed
    if not new_schema_str or "Error" in summary:
        return f"❌ Generation Failed: {summary}", old_schema, "", old_score, new_score

    progress(0.5, desc="📊 Evaluating Improvement...")
    
    # 2. Decide whether to update
    # Criteria: New score must be better than old score, or old score is 0 (missing)
    if new_score > old_score:
        progress(0.7, desc="🚀 Pushing to WordPress...")
        
        # 3. Push to WP
        success, message = push_schema_to_wordpress(url, wp_user, wp_pass, new_schema_str)
        
        if success:
            final_msg = f"✅ AUTO-FIX SUCCESSFUL!\n\nSummary: {summary}\n\nWP Update: {message}"
        else:
            final_msg = f"⚠️ Schema Improved but Update Failed.\n\nSummary: {summary}\n\nWP Error: {message}"
            
        return final_msg, old_schema, new_schema_str, old_score, new_score
    else:
        return f"ℹ️ No improvement found. Old Score: {old_score}, New Score: {new_score}. No update performed.", old_schema, new_schema_str, old_score, new_score

# --- FUNCTION 6: META TAGS UI LOGIC ---
def run_meta_gen(urls_text, api_key, progress=gr.Progress()):
    if not urls_text or not api_key:
        return pd.DataFrame(), "Please enter URLs and API Key."
        
    urls = [u.strip() for u in urls_text.split(',') if u.strip()]
    progress(0.1, desc="🧠 Generating Meta Tags...")
    
    results = generate_meta_tags(urls, api_key)
    df = pd.DataFrame(results)
    
    return df, f"✅ Generated suggestions for {len(results)} pages."

def run_meta_update(df, wp_user, wp_pass, progress=gr.Progress()):
    if df is None or df.empty:
        return "No data to update."
    
    if not wp_user or not wp_pass:
        return "Please enter WP Credentials."
        
    log = []
    total = len(df)
    
    for i, row in df.iterrows():
        url = row['URL']
        new_title = row['New Title']
        new_desc = row['New Desc']
        
        progress((i+1)/total, desc=f"Updating {url}...")
        
        success, msg = update_page_meta(url, wp_user, wp_pass, new_title, new_desc)
        status = "✅" if success else "❌"
        log.append(f"{status} {url}: {msg}")
        
    return "\n".join(log)

# --- UI BUILDER ---
def create_ui():
    with gr.Blocks(title="Advanced SEO Auditor", theme=gr.themes.Soft(primary_hue="blue")) as demo:
        gr.Markdown("# 🚀 Advanced SEO Auditor")

        # --- GLOBAL CONFIGURATION ---
        with gr.Accordion("⚙️ Global Configuration (Set these first)", open=True):
            with gr.Row():
                api_key_input = gr.Textbox(label="Gemini API Key", type="password", placeholder="Required for AI features")
                wp_user_input = gr.Textbox(label="WP Username", placeholder="Required for updates")
                wp_pass_input = gr.Textbox(label="WP App Password", type="password", placeholder="Required for updates")
            gr.Markdown("_Note: These credentials will be used for all tools below._")

        with gr.Tabs():
            # Tab 1: Audit
            with gr.Tab("Audit Website"):
                gr.Markdown("### 1. Crawl & Analyze")
                with gr.Row():
                    url_input_audit = gr.Textbox(label="Start URL", placeholder="https://example.com")
                    max_pages_input = gr.Number(label="Max Pages", value=10, precision=0)
                
                audit_btn = gr.Button("🚀 Start Audit", variant="primary")
                audit_status = gr.Markdown("Ready.")
                
                gr.Markdown("### 2. Results")
                audit_df = gr.Dataframe(label="Audit Data", interactive=False)
                audit_download = gr.File(label="Download Excel Report")
                
                audit_btn.click(
                    run_audit_ui,
                    inputs=[url_input_audit, max_pages_input],
                    outputs=[audit_df, audit_download, audit_status]
                )

            # Tab 2: Capture
            with gr.Tab("Capture & PDF"):
                gr.Markdown("### 1. Capture Screenshots")
                url_input_capture = gr.Textbox(label="Page URL", placeholder="https://example.com")
                capture_btn = gr.Button("📸 Capture & Create PDF", variant="primary")
                capture_status = gr.Markdown("Ready.")
                
                with gr.Row():
                    gallery = gr.Gallery(label="Screenshots")
                    pdf_download = gr.File(label="Download PDF")
                    
                capture_btn.click(
                    run_capture_ui,
                    inputs=[url_input_capture],
                    outputs=[gallery, pdf_download, capture_status]
                )

            # Tab 3: Schema Updater
            with gr.Tab("Schema Updater"):
                gr.Markdown("### 1. Analyze & Improve Schema")
                url_input_schema = gr.Textbox(label="Page URL", placeholder="https://example.com/services/wedding")

                with gr.Row():
                    generate_schema_btn = gr.Button("Generate Improved Schema", variant="primary")
                    auto_fix_btn = gr.Button("⚡ Auto-Fix & Update (One Click)", variant="secondary")

                schema_status = gr.Markdown("Waiting...")

                with gr.Row():
                    old_score_disp = gr.Label(label="Old Score")
                    new_score_disp = gr.Label(label="New Score")

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Current Schema")
                        old_schema_display = gr.Code(language="json", label="Current JSON-LD", interactive=False)
                    with gr.Column():
                        gr.Markdown("### Improved Schema (Editable)")
                        new_schema_display = gr.Code(language="json", label="Generated JSON-LD", interactive=True)

                gr.HTML("<hr>")
                
                gr.Markdown("### 2. Manual Push to WordPress")
                with gr.Row():
                    save_schema_btn = gr.Button("✅ Confirm & Update Live Site", variant="stop")
                    download_schema_file = gr.File(label="Download Backup")
                
                update_log = gr.Textbox(label="Update Logs", interactive=False, lines=4)

                # Connect Logic
                generate_schema_btn.click(
                    run_schema_update,
                    inputs=[url_input_schema, api_key_input],
                    outputs=[schema_status, old_schema_display, new_schema_display, old_score_disp, new_score_disp]
                )

                save_schema_btn.click(
                    confirm_and_update,
                    inputs=[url_input_schema, new_schema_display, wp_user_input, wp_pass_input],
                    outputs=[update_log, download_schema_file]
                )

                auto_fix_btn.click(
                    auto_fix_schema,
                    inputs=[url_input_schema, api_key_input, wp_user_input, wp_pass_input],
                    outputs=[schema_status, old_schema_display, new_schema_display, old_score_disp, new_score_disp]
                )

            # Tab 4: Meta Tag Updater
            with gr.Tab("Meta Tag Updater"):
                gr.Markdown("### 1. Bulk Generate Titles & Descriptions")
                gr.Markdown("Enter URLs (comma separated) to generate AI-optimized meta tags.")
                
                meta_urls_input = gr.Textbox(label="URLs (comma separated)", lines=3, placeholder="https://site.com/page1, https://site.com/page2")
                
                meta_gen_btn = gr.Button("✨ Generate Improvements", variant="primary")
                meta_status = gr.Markdown("Ready.")
                
                gr.Markdown("### 2. Review & Edit (Editable Table)")
                # Dataframe with editable columns
                meta_df = gr.Dataframe(
                    label="Meta Tags Preview",
                    headers=["URL", "Old Title", "New Title", "Old Desc", "New Desc"],
                    interactive=True,
                    wrap=True
                )
                
                gr.Markdown("### 3. Push to WordPress")
                meta_update_btn = gr.Button("🚀 Update All Live Pages", variant="stop")
                meta_log = gr.Textbox(label="Update Log", interactive=False, lines=5)
                
                meta_gen_btn.click(
                    run_meta_gen,
                    inputs=[meta_urls_input, api_key_input],
                    outputs=[meta_df, meta_status]
                )
                
                meta_update_btn.click(
                    run_meta_update,
                    inputs=[meta_df, wp_user_input, wp_pass_input],
                    outputs=[meta_log]
                )

    return demo