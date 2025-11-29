import gradio as gr
import pandas as pd
import time
import json
from urllib.parse import urlparse, urljoin

# ==========================================
# 📦 LOCAL IMPORTS
# ==========================================
try:
    from .config import MAX_PAGES_TO_SCAN
    from .crawler import check_robots_txt, fetch_sitemap_urls
    from .analyzer import analyze_page
    from .reporter import prepare_dataframe, save_excel
    from .capturer import capture_screenshots, create_pdf
    from .schema_gen import generate_improved_schema
    from .wp_handler import push_schema_to_wordpress, update_page_meta
    from .meta_gen import generate_meta_tags
except ImportError:
    pass

# ==========================================
# 🧠 LOGIC HANDLERS
# ==========================================

def run_audit_ui(urls_input, max_pages, progress=gr.Progress()):
    if not urls_input:
        return None, None, "Please enter URL(s)."
    
    urls_list = [u.strip() for u in urls_input.split(',') if u.strip()]
    
    for i, url in enumerate(urls_list):
        if not url.startswith("http"):
            urls_list[i] = "https://" + url
    
    if len(urls_list) == 1:
        start_url = urls_list[0]
        domain_netloc = urlparse(start_url).netloc
        progress(0.1, desc="🔍 Discovering pages...")
        sitemap_url = urljoin(start_url, "sitemap.xml")
        found_sitemap = fetch_sitemap_urls(sitemap_url)
        if found_sitemap:
            urls_to_scan = list(found_sitemap)
        else:
            urls_to_scan = urls_list
    else:
        urls_to_scan = urls_list
        domain_netloc = urlparse(urls_to_scan[0]).netloc
    
    if max_pages > 0:
        urls_to_scan = urls_to_scan[:int(max_pages)]
        
    results = []
    for i, url in enumerate(urls_to_scan):
        progress((i + 1) / len(urls_to_scan), desc=f"Analyzing {url}")
        res = analyze_page(url, domain_netloc)
        results.append(res)
        
    df = pd.DataFrame(results)
    df_display = prepare_dataframe(df)
    
    timestamp = int(time.time())
    filename = f"audit_report_{timestamp}.xlsx"
    save_excel(df_display, filename)
    
    return df_display, filename, f"✅ Audit Complete. Scanned {len(urls_to_scan)} pages."

def run_capture_ui(urls_input, progress=gr.Progress()):
    if not urls_input:
        return None, None, "Please enter URL(s)."
    
    urls_list = [u.strip() for u in urls_input.split(',') if u.strip()]
    for i, url in enumerate(urls_list):
        if not url.startswith("http"):
            urls_list[i] = "https://" + url
        
    progress(0.2, desc=f"📸 Capturing {len(urls_list)} page(s)...")
    screenshot_paths = capture_screenshots(urls_list, progress=progress)
    
    if not screenshot_paths:
        return None, None, "❌ Failed to capture screenshots."
        
    progress(0.8, desc="📄 Generating PDF...")
    pdf_filename = f"capture_{int(time.time())}.pdf"
    pdf_path = create_pdf(screenshot_paths, pdf_filename)
    
    return screenshot_paths, pdf_path, f"✅ Capture Complete. {len(screenshot_paths)} page(s) captured."

def run_schema_update(urls_input, api_key, progress=gr.Progress()):
    if not urls_input:
        return "Please enter URL(s).", "", "", 0, 0
    if not api_key:
        return "Please enter a Gemini API Key.", "", "", 0, 0

    urls_list = [u.strip() for u in urls_input.split(',') if u.strip()]
    url = urls_list[0]
    if not url.startswith("http"):
        url = "https://" + url

    progress(0, desc="🚀 Initializing...")
    old_schema, new_schema, old_score, new_score, summary = generate_improved_schema(url, api_key)

    status_text = f"✅ Analysis Complete for {url}\nSummary: {summary}"
    if len(urls_list) > 1:
        status_text += f"\n⚠️ Note: Only processed first URL. {len(urls_list)-1} URL(s) skipped."

    return status_text, old_schema, new_schema, old_score, new_score

def confirm_and_update(url, new_schema_content, wp_user, wp_pass):
    if not new_schema_content:
        return "Error: No schema content generated yet.", None
    if not wp_user or not wp_pass:
        return "Error: WordPress Username and App Password are required.", None
    if not url.startswith("http"):
        url = "https://" + url

    timestamp = int(time.time())
    filename = f"backup_schema_{timestamp}.json"
    try:
        with open(filename, "w") as f:
            f.write(new_schema_content)
    except Exception as e:
        return f"Error saving local backup: {e}", None

    success, message = push_schema_to_wordpress(url, wp_user, wp_pass, new_schema_content)
    
    if success:
        log_msg = f"✅ LIVE UPDATE SUCCESSFUL!\n{message}\n📁 Backup saved: {filename}"
    else:
        log_msg = f"❌ UPDATE FAILED\n{message}\n📁 Backup saved: {filename}"
    
    return log_msg, filename
    
def auto_fix_schema(urls_input, api_key, wp_user, wp_pass, progress=gr.Progress()):
    if not urls_input or not api_key or not wp_user or not wp_pass:
        return "Error: All fields are required for Auto-Fix.", "", "", 0, 0

    urls_list = [u.strip() for u in urls_input.split(',') if u.strip()]
    url = urls_list[0]
    if not url.startswith("http"):
        url = "https://" + url

    progress(0.1, desc="🔍 Analyzing & Generating Schema...")
    old_schema, new_schema_str, old_score, new_score, summary = generate_improved_schema(url, api_key)
    
    if not new_schema_str or "Error" in summary:
        return f"❌ Generation Failed: {summary}", old_schema, "", old_score, new_score

    progress(0.5, desc="📊 Evaluating Improvement...")
    if new_score > old_score:
        progress(0.7, desc="🚀 Pushing to WordPress...")
        success, message = push_schema_to_wordpress(url, wp_user, wp_pass, new_schema_str)
        
        if success:
            final_msg = f"✅ AUTO-FIX SUCCESSFUL for {url}!\n\nSummary: {summary}\n\nWP Update: {message}"
        else:
            final_msg = f"⚠️ Schema Improved but Update Failed for {url}.\n\nSummary: {summary}\n\nWP Error: {message}"
        
        if len(urls_list) > 1:
            final_msg += f"\n⚠️ Note: Only processed first URL. {len(urls_list)-1} URL(s) skipped."
            
        return final_msg, old_schema, new_schema_str, old_score, new_score
    else:
        msg = f"ℹ️ No improvement found for {url}. Old Score: {old_score}, New Score: {new_score}. No update performed."
        return msg, old_schema, new_schema_str, old_score, new_score

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

def run_sitemap_extract(homepage_url, progress=gr.Progress()):
    if not homepage_url:
        return None, "Please enter a homepage URL.", None
    if not homepage_url.startswith("http"):
        homepage_url = "https://" + homepage_url
    
    progress(0.1, desc="🔍 Looking for sitemap...")
    sitemap_url = urljoin(homepage_url, "sitemap.xml")
    
    progress(0.3, desc=f"📥 Fetching from {sitemap_url}...")
    urls = fetch_sitemap_urls(sitemap_url)
    
    if not urls:
        sitemap_url = urljoin(homepage_url, "sitemap_index.xml")
        progress(0.5, desc=f"📥 Trying {sitemap_url}...")
        urls = fetch_sitemap_urls(sitemap_url)
    
    if not urls:
        return None, f"❌ No URLs found. Tried {sitemap_url}", None
    
    progress(0.9, desc="📋 Preparing results...")
    df = pd.DataFrame({"URL": sorted(list(urls))})
    
    timestamp = int(time.time())
    filename = f"sitemap_urls_{timestamp}.csv"
    df.to_csv(filename, index=False)
    
    return df, f"✅ Found {len(urls)} URLs", filename

# ==========================================
# 🎨 UI REDESIGN (Modern / Dashboard)
# ==========================================

custom_css = """
body { background-color: #f8fafc; }
.gradio-container { max-width: 95% !important; margin-top: 20px; }
h1, h2, h3 { font-family: 'Inter', sans-serif; }
.contain { background-color: transparent !important; }
#sidebar { background-color: #ffffff; border-right: 1px solid #e2e8f0; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }
#main_content { background-color: transparent; padding-left: 20px; }
.primary-btn { background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) !important; border: none; color: white !important; }
.card { background: white; padding: 20px; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 20px; }
"""

theme = gr.themes.Soft(
    primary_hue="indigo",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui"],
    radius_size=gr.themes.sizes.radius_md,
)

def create_ui():
    with gr.Blocks(title="SEO Command Center", theme=theme, css=custom_css) as demo:
        
        # Application Header
        with gr.Row(elem_id="header"):
            gr.Markdown(
                """
                # ⚡ SEO Command Center
                ### AI-Powered Audit, Schema & Content Optimization
                """
            )

        with gr.Row():
            # ==========================
            # LEFT SIDEBAR: CONFIG
            # ==========================
            with gr.Column(scale=1, elem_id="sidebar", min_width=300):
                gr.Markdown("### ⚙️ Global Settings")
                gr.Markdown("Configure your keys once for all tools.")
                
                with gr.Group():
                    api_key_input = gr.Textbox(
                        label="Gemini API Key", 
                        type="password", 
                        placeholder="sk-...", 
                        info="Required for Schema & Meta Gen"
                    )
                    
                    gr.HTML("<div style='margin-top: 15px;'></div>")
                    
                    wp_user_input = gr.Textbox(
                        label="WordPress Username", 
                        placeholder="admin", 
                        elem_id="wp_user"
                    )
                    wp_pass_input = gr.Textbox(
                        label="WP App Password", 
                        type="password", 
                        placeholder="xxxx xxxx xxxx xxxx",
                        info="Required for Auto-Updates"
                    )
                
                gr.Markdown("---")
                
                with gr.Accordion("📝 Setup Instructions", open=False):
                    gr.Markdown("""
                    **For WordPress Updates:**
                    1. Go to Users > Profile.
                    2. Scroll to 'Application Passwords'.
                    3. Generate a new password.
                    
                    **For Schema:**
                    Ensure the PHP snippet is added to your theme's `functions.php`.
                    """)

            # ==========================
            # RIGHT MAIN CONTENT: TOOLS
            # ==========================
            with gr.Column(scale=4, elem_id="main_content"):
                
                with gr.Tabs(elem_classes="main_tabs"):
                    
                    # ------------------------
                    # TAB 1: AUDIT
                    # ------------------------
                    with gr.Tab("🔍 Audit & Crawl"):
                        with gr.Group(elem_classes="card"):
                            gr.Markdown("### 🕷️ Site Crawler")
                            with gr.Row():
                                url_input_audit = gr.Textbox(
                                    label="Target URL(s)", 
                                    placeholder="https://example.com", 
                                    scale=3
                                )
                                max_pages_input = gr.Number(
                                    label="Page Limit", 
                                    value=10, 
                                    precision=0, 
                                    scale=1
                                )
                            audit_btn = gr.Button("Start Audit", variant="primary", elem_classes="primary-btn")
                        
                        with gr.Group():
                            audit_status = gr.Markdown("Waiting for input...")
                            with gr.Accordion("📊 Audit Results", open=True):
                                # FIXED: Removed height param
                                audit_df = gr.Dataframe(interactive=False)
                                audit_download = gr.File(label="Download Report (.xlsx)")

                        audit_btn.click(
                            run_audit_ui,
                            inputs=[url_input_audit, max_pages_input],
                            outputs=[audit_df, audit_download, audit_status]
                        )

                    # ------------------------
                    # TAB 2: SCHEMA
                    # ------------------------
                    with gr.Tab("🧠 Schema AI"):
                        with gr.Group(elem_classes="card"):
                            gr.Markdown("### 🧬 JSON-LD Generator & Fixer")
                            url_input_schema = gr.Textbox(
                                label="Page URL", 
                                placeholder="https://example.com/service-page"
                            )
                            with gr.Row():
                                generate_schema_btn = gr.Button("Analyze & Generate", variant="secondary")
                                auto_fix_btn = gr.Button("⚡ Auto-Fix & Push Live", variant="primary", elem_classes="primary-btn")
                        
                        schema_status = gr.Markdown("")
                        
                        # Comparison View
                        with gr.Row():
                            with gr.Column():
                                gr.Label("Current Status", color="grey")
                                old_score_disp = gr.Number(label="SEO Score", interactive=False)
                                old_schema_display = gr.Code(language="json", label="Existing Schema", interactive=False, lines=15)
                            
                            with gr.Column():
                                gr.Label("AI Recommendation", color="green")
                                new_score_disp = gr.Number(label="Predicted Score", interactive=False)
                                new_schema_display = gr.Code(language="json", label="Generated Schema (Editable)", interactive=True, lines=15)

                        # Manual Actions
                        with gr.Accordion("🚀 Manual Push Controls", open=False):
                            with gr.Row():
                                save_schema_btn = gr.Button("Confirm & Update Live Site", variant="stop")
                                download_schema_file = gr.File(label="Download JSON Backup")
                            # FIXED: Changed from gr.Code(language="text") to gr.Textbox
                            update_log = gr.Textbox(label="Transaction Logs", interactive=False, lines=10, show_copy_button=True)

                        # Connect Logic
                        generate_schema_btn.click(
                            run_schema_update,
                            inputs=[url_input_schema, api_key_input],
                            outputs=[schema_status, old_schema_display, new_schema_display, old_score_disp, new_score_disp]
                        )
                        auto_fix_btn.click(
                            auto_fix_schema,
                            inputs=[url_input_schema, api_key_input, wp_user_input, wp_pass_input],
                            outputs=[schema_status, old_schema_display, new_schema_display, old_score_disp, new_score_disp]
                        )
                        save_schema_btn.click(
                            confirm_and_update,
                            inputs=[url_input_schema, new_schema_display, wp_user_input, wp_pass_input],
                            outputs=[update_log, download_schema_file]
                        )

                    # ------------------------
                    # TAB 3: META TAGS
                    # ------------------------
                    with gr.Tab("🏷️ Meta Tags"):
                        with gr.Group(elem_classes="card"):
                            gr.Markdown("### 🤖 Bulk Meta Tag Optimizer")
                            meta_urls_input = gr.Textbox(
                                label="URLs to Optimize (Comma separated)", 
                                placeholder="https://site.com/a, https://site.com/b",
                                lines=2
                            )
                            meta_gen_btn = gr.Button("Generate Suggestions", variant="primary", elem_classes="primary-btn")

                        meta_status = gr.Markdown()
                        
                        gr.Markdown("**Review Suggestions (Double click cells to edit)**")
                        # FIXED: Removed height param
                        meta_df = gr.Dataframe(
                            headers=["URL", "Old Title", "New Title", "Old Desc", "New Desc"],
                            interactive=True,
                            wrap=True
                        )
                        
                        with gr.Row():
                            meta_update_btn = gr.Button("🚀 Push Updates to WordPress", variant="stop")
                            # FIXED: Changed from gr.Code(language="text") to gr.Textbox
                            meta_log = gr.Textbox(label="Update Log", interactive=False, lines=5, show_copy_button=True)

                        meta_gen_btn.click(run_meta_gen, inputs=[meta_urls_input, api_key_input], outputs=[meta_df, meta_status])
                        meta_update_btn.click(run_meta_update, inputs=[meta_df, wp_user_input, wp_pass_input], outputs=[meta_log])

                    # ------------------------
                    # TAB 4: UTILITIES
                    # ------------------------
                    with gr.Tab("🛠️ Utilities"):
                        with gr.Row():
                            # Capture Tool
                            with gr.Column():
                                with gr.Group(elem_classes="card"):
                                    gr.Markdown("### 📸 Visual Capture")
                                    url_input_capture = gr.Textbox(label="URLs", placeholder="https://example.com")
                                    capture_btn = gr.Button("Capture & PDF", variant="secondary")
                                    
                                    capture_status = gr.Markdown("")
                                    pdf_download = gr.File(label="Download PDF")
                                    gallery = gr.Gallery(label="Previews", height=200, columns=2)
                                    
                                    capture_btn.click(
                                        run_capture_ui,
                                        inputs=[url_input_capture],
                                        outputs=[gallery, pdf_download, capture_status]
                                    )
                            
                            # Sitemap Tool
                            with gr.Column():
                                with gr.Group(elem_classes="card"):
                                    gr.Markdown("### 🗺️ Sitemap Extractor")
                                    sitemap_url_input = gr.Textbox(label="Homepage URL", placeholder="https://example.com")
                                    sitemap_extract_btn = gr.Button("Extract URLs", variant="secondary")
                                    
                                    sitemap_status = gr.Markdown("")
                                    sitemap_download = gr.File(label="Download CSV")
                                    
                                    sitemap_extract_btn.click(
                                        run_sitemap_extract,
                                        inputs=[sitemap_url_input],
                                        outputs=[gr.Dataframe(visible=False), sitemap_status, sitemap_download]
                                    )

    return demo
