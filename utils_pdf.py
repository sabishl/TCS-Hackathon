"""
utils_pdf.py
------------
PDF compliance report generator using PyMuPDF (fitz).
Generates an executive-level summary and tabular list of updates.
"""

def generate_pdf_report(results: list, old_name: str, new_name: str) -> bytes:
    import fitz
    doc = fitz.open()
    
    # ── FIRST PAGE: COVER & SUMMARY ──────────────────────────────────────
    page = doc.new_page()
    
    # Title
    page.insert_text(fitz.Point(50, 60), "PolicyLens Compliance Report", fontsize=24, fontname="hebo", color=(0.06, 0.15, 0.3))
    page.insert_text(fitz.Point(50, 85), f"Comparison: {old_name}   ->   {new_name}", fontsize=10, fontname="helv", color=(0.4, 0.4, 0.4))
    
    # Draw a divider line
    shape = page.new_shape()
    shape.draw_line(fitz.Point(50, 100), fitz.Point(545, 100))
    shape.finish(color=(0.1, 0.3, 0.6), width=1.5)
    
    # Summary Stats
    counts = {
        "added": sum(1 for r in results if r.get("status") == "added"),
        "removed": sum(1 for r in results if r.get("status") == "removed"),
        "modified": sum(1 for r in results if r.get("status") == "modified"),
        "unchanged": sum(1 for r in results if r.get("status") == "unchanged"),
    }
    
    y = 130
    page.insert_text(fitz.Point(50, y), "Executive Summary Statistics", fontsize=14, fontname="hebo", color=(0.1, 0.1, 0.1))
    
    y += 25
    stats_text = (
        f"• Total Sections Analyzed: {len(results)}\n"
        f"• Sections Added: {counts['added']}\n"
        f"• Sections Removed: {counts['removed']}\n"
        f"• Sections Updated: {counts['modified']}\n"
        f"• Sections Unchanged: {counts['unchanged']}"
    )
    page.insert_textbox(fitz.Rect(50, y, 545, y + 90), stats_text, fontsize=11, fontname="helv", color=(0.2, 0.2, 0.2), lineheight=15)
    
    y += 110
    page.insert_text(fitz.Point(50, y), "Detailed Section-by-Section Changes", fontsize=14, fontname="hebo", color=(0.1, 0.1, 0.1))
    
    y += 20
    # Draw table headers
    headers = [("Section", 50, 220), ("Status", 230, 290), ("Impact", 300, 360), ("Change Summary", 370, 545)]
    shape = page.new_shape()
    # draw header box
    shape.draw_rect(fitz.Rect(50, y - 12, 545, y + 8))
    shape.finish(fill=(0.9, 0.93, 0.96), color=(0.8, 0.8, 0.8), width=0.5)
    for h, x_start, x_end in headers:
        page.insert_text(fitz.Point(x_start + 4, y - 2), h, fontsize=9, fontname="hebo", color=(0.1, 0.15, 0.25))
    
    y += 15
    for res in results:
        # Check page boundaries
        if y > 730:
            page = doc.new_page()
            y = 60
            # Draw header again on new page
            shape = page.new_shape()
            shape.draw_rect(fitz.Rect(50, y - 12, 545, y + 8))
            shape.finish(fill=(0.9, 0.93, 0.96), color=(0.8, 0.8, 0.8), width=0.5)
            for h, x_start, x_end in headers:
                page.insert_text(fitz.Point(x_start + 4, y - 2), h, fontsize=9, fontname="hebo", color=(0.1, 0.15, 0.25))
            y += 15
            
        status = res.get("status", "unchanged").upper()
        impact = res.get("impact", "Low").upper()
        sec_name = res.get("section", "")
        summary = res.get("change_summary", "")
        
        # Color based on status
        stat_color = (0.2, 0.6, 0.2) if status == "ADDED" else ((0.8, 0.2, 0.2) if status == "REMOVED" else ((0.9, 0.5, 0.0) if status == "MODIFIED" else (0.4, 0.4, 0.4)))
        imp_color = (0.8, 0.2, 0.2) if impact == "HIGH" else ((0.9, 0.5, 0.0) if impact == "MEDIUM" else (0.2, 0.5, 0.8))
        
        # Draw cells
        # Section name (shortened if too long)
        sec_disp = sec_name[:30] + "..." if len(sec_name) > 33 else sec_name
        page.insert_text(fitz.Point(54, y + 2), sec_disp, fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
        
        # Status
        page.insert_text(fitz.Point(234, y + 2), status, fontsize=8, fontname="hebo", color=stat_color)
        
        # Impact
        page.insert_text(fitz.Point(304, y + 2), impact, fontsize=8, fontname="hebo", color=imp_color)
        
        # Summary (wrap using insert_textbox)
        page.insert_textbox(fitz.Rect(374, y - 8, 540, y + 15), summary, fontsize=8, fontname="helv", color=(0.2, 0.2, 0.2))
        
        # Draw a bottom border for the row
        shape = page.new_shape()
        shape.draw_line(fitz.Point(50, y + 10), fitz.Point(545, y + 10))
        shape.finish(color=(0.85, 0.85, 0.85), width=0.5)
        
        y += 24
        
    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes
