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
from .wp_handler import push_schema_to_wordpress # <--- IMPORT THE NEW FUNCTION

# ... [Keep run_audit_ui and run_capture_ui exactly as they were] ...

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

# --- UI BUILDER ---
def create_ui():
    with gr.Blocks(title="Advanced SEO Auditor", theme=gr.themes.Soft(primary_hue="blue")) as demo:
        gr.Markdown("# 🚀 Advanced SEO Auditor")

        with gr.Tabs():
            # ... [Tab 1: Audit - Keep existing code] ...
            # ... [Tab 2: Capture - Keep existing code] ...

            # Tab 3: Schema Updater (UPDATED)
            with gr.Tab("Schema Updater"):
                gr.Markdown("### 1. Analyze & Improve Schema")
                with gr.Row():
                    url_input_schema = gr.Textbox(label="Page URL", placeholder="https://example.com/services/wedding")
                    api_key_input = gr.Textbox(label="Gemini API Key", type="password")

                generate_schema_btn = gr.Button("Generate Improved Schema", variant="primary")
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
                
                gr.Markdown("### 2. Push to WordPress")
                gr.Markdown("Enter your WP Username and [Application Password](https://make.wordpress.org/core/2020/11/05/application-passwords-integration-guide/) to update the live site.")
                
                with gr.Row():
                    wp_user_input = gr.Textbox(label="WP Username")
                    wp_pass_input = gr.Textbox(label="WP App Password", type="password")

                gr.Markdown("### 3. Auto-Fix (One Click)")
                auto_fix_btn = gr.Button("⚡ Auto-Fix & Update", variant="primary")

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

    return demo