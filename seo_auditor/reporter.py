import pandas as pd
import time

def prepare_dataframe(df):
    """
    Organizes columns for both Display and Excel.
    Ensures NOTHING is dropped.
    """
    priority_cols = [
        "url", "status_code", "status_type",
        "https_ok", "page_size_kb", "schema_types",
        "title", "title_len",
        "h1_text", "h1_count",
        "meta_description", "meta_description_len",
        "word_count", "internal_links", "external_links", "broken_links", # Added broken_links
        "load_time_s", "issues_found"
    ]
    all_cols = list(df.columns)
    # Append any columns that are in df but not in priority_cols
    final_cols = priority_cols + [c for c in all_cols if c not in priority_cols]

    # Handle cases where some priority cols might not be in df (e.g. empty results)
    final_cols = [c for c in final_cols if c in df.columns]

    # Beautify issues list
    if 'issues_found' in df.columns:
        df['issues_found'] = df['issues_found'].apply(lambda x: " | ".join(x) if isinstance(x, list) and x else "✅ OK")

    return df[final_cols]

def save_excel(df, filename):
    writer = pd.ExcelWriter(filename, engine='xlsxwriter')
    workbook = writer.book
    df.to_excel(writer, sheet_name='Audit', index=False)
    ws = writer.sheets['Audit']

    header = workbook.add_format({'bold': True, 'bg_color': '#2c3e50', 'font_color': 'white'})
    bad = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
    # warn = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C6500'})

    for i, col in enumerate(df.columns):
        ws.write(0, i, col, header)
    ws.set_column('A:A', 40)

    if "https_ok" in df.columns:
        idx = df.columns.get_loc("https_ok")
        ws.conditional_format(1, idx, len(df), idx, {'type': 'cell', 'criteria': '=', 'value': False, 'format': bad})

    if "broken_links" in df.columns:
        idx = df.columns.get_loc("broken_links")
        ws.conditional_format(1, idx, len(df), idx, {'type': 'cell', 'criteria': '>', 'value': 0, 'format': bad})

    writer.close()
    return filename
