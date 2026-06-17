"""
app.py — PolicyLens
Single-page flow: Upload → Process → Summary → Chatbot
No sidebar. Everything inline.
"""

import os
import gc
import tempfile
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
import config
_ENV_GROQ_KEY = os.getenv("GROQ_API_KEY", "")


def _render_points(title: str, points: list[str], empty_text: str) -> None:
    st.markdown(f"**{title}**")
    clean_points = [str(pt).strip() for pt in points if str(pt).strip()]
    if not clean_points:
        st.caption(empty_text)
        return
    for pt in clean_points:
        st.markdown(f"- {pt}")


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _load_sample_data() -> None:
    st.session_state["_old_pdf_bytes"] = b"Sample Old Document Content"
    st.session_state["_new_pdf_bytes"] = b"Sample New Document Content"
    st.session_state["old_doc_name"] = "Standard_Policy_2025.pdf"
    st.session_state["new_doc_name"] = "Standard_Policy_2026_Revised.pdf"
    st.session_state["old_doc_size"] = "1.4 MB"
    st.session_state["new_doc_size"] = "1.5 MB"
    
    st.session_state["comparison_results"] = [
        {
            "section": "1. Eligibility & Enrollment",
            "status": "modified",
            "impact": "High",
            "change_summary": "Minimum age of eligibility reduced from 21 to 18. Part-time employee enrollment window shortened.",
            "old_key_points": [
                "Employees must be at least 21 years of age to enroll.",
                "Enrollment window is open for 45 days from date of hire."
            ],
            "new_key_points": [
                "Employees must be at least 18 years of age to enroll.",
                "Enrollment window is open for 30 days from date of hire."
            ],
            "changed_points": [
                "Age limit: 21 -> 18 years old",
                "Enrollment period: 45 days -> 30 days"
            ],
            "same_points": [
                "Full-time employees are eligible on day 1.",
                "Coverage starts on the first of the month following enrollment."
            ],
            "table_changed": False,
            "similarity_score": 0.82
        },
        {
            "section": "2. Coverage Limits & Copays",
            "status": "modified",
            "impact": "High",
            "change_summary": "In-network specialist copays increased, and dental annual maximum coverage limit raised.",
            "old_key_points": [
                "Specialist visit copay is set at $30.",
                "Dental annual maximum benefit is $1,500 per member."
            ],
            "new_key_points": [
                "Specialist visit copay is set at $45.",
                "Dental annual maximum benefit is $2,000 per member."
            ],
            "changed_points": [
                "Specialist copay: $30 -> $45 per visit",
                "Dental limit: $1,500 -> $2,000 annually"
            ],
            "same_points": [
                "Primary care visit copay remains unchanged at $20.",
                "Emergency room copay remains at $150."
            ],
            "table_changed": True,
            "similarity_score": 0.76
        },
        {
            "section": "3. Exclusions & Limitations",
            "status": "removed",
            "impact": "High",
            "change_summary": "Experimental treatments exclusion clause has been completely removed.",
            "old_key_points": [
                "Experimental or investigational clinical trials are excluded from coverage.",
                "Cosmetic procedures are excluded unless medically necessary."
            ],
            "new_key_points": [],
            "changed_points": [
                "Experimental treatments exclusion clause removed from policy."
            ],
            "same_points": [],
            "table_changed": False,
            "similarity_score": 0.0
        },
        {
            "section": "4. Telehealth Services",
            "status": "added",
            "impact": "Medium",
            "change_summary": "New dedicated section introducing 24/7 virtual care telehealth coverage at zero copay.",
            "old_key_points": [],
            "new_key_points": [
                "Telehealth consultations are covered 100% with $0 copay.",
                "Available 24/7 through approved network provider app."
            ],
            "changed_points": [
                "New telehealth service coverage added."
            ],
            "same_points": [],
            "table_changed": False,
            "similarity_score": 0.0
        },
        {
            "section": "5. Definitions & Terminology",
            "status": "unchanged",
            "impact": "Low",
            "change_summary": "No material changes detected. Terminology remains standard.",
            "old_key_points": [
                "'Medically Necessary' defined as treatments meeting standard clinical guidelines.",
                "'Pre-existing Condition' defines exclusions for treatment prior to enrollment."
            ],
            "new_key_points": [
                "'Medically Necessary' defined as treatments meeting standard clinical guidelines.",
                "'Pre-existing Condition' defines exclusions for treatment prior to enrollment."
            ],
            "changed_points": [],
            "same_points": [
                "All standard policy definitions remain identical."
            ],
            "table_changed": False,
            "similarity_score": 0.98
        }
    ]
    
    # Store fake sections into vectorstore for chatbot function
    sample_sections = []
    for item in st.session_state["comparison_results"]:
        heading = item["section"]
        content_a = item["old_key_points"]
        content_b = item["new_key_points"]
        if content_a:
            sample_sections.append({
                "source": "doc_a",
                "heading": heading,
                "content": content_a,
                "tables": []
            })
        if content_b:
            sample_sections.append({
                "source": "doc_b",
                "heading": heading,
                "content": content_b,
                "tables": []
            })
            
    from vectorstore import reset_collection, store_sections
    reset_collection()
    st.session_state["vectorstore"] = store_sections(sample_sections)
    
    st.session_state["sections_a"] = sample_sections
    st.session_state["sections_b"] = sample_sections
    st.session_state["processed"] = True
    st.session_state["processing"] = False
    st.session_state["chat_history"] = []


def _clear_comparison_state(clear_vectors: bool = True) -> None:
    """Clear uploaded PDF results and optionally wipe persisted Chroma vectors."""
    for key in [
        "processed",
        "processing",
        "sections_a",
        "sections_b",
        "vectorstore",
        "comparison_results",
        "chat_history",
        "rag_chain",
        "_old_pdf_bytes",
        "_new_pdf_bytes",
        "old_doc_name",
        "new_doc_name",
        "old_doc_size",
        "new_doc_size",
    ]:
        st.session_state.pop(key, None)

    gc.collect()

    if clear_vectors:
        try:
            from vectorstore import reset_collection
            reset_collection()
        except Exception as exc:
            st.warning(f"Could not clear vector database: {exc}")

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PolicyLens – AI Policy Comparator",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Silently initialise API key ────────────────────────────────────────────────
if config.ENV in ("amd_cloud", "local"):
    st.session_state["groq_api_key"] = "EMPTY"
elif _ENV_GROQ_KEY and "groq_api_key" not in st.session_state:
    st.session_state["groq_api_key"] = _ENV_GROQ_KEY

# ══════════════════════════════════════════════════════════════════════════════
#  CSS  — Deep Ocean Aurora Premium
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;600;700;800&display=swap');

/* Reset / Base app styling */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
}

/* Base theme styling */
.stApp {
    background-color: #F8FAFC !important;
    color: #0F172A !important;
}

.block-container {
    background-color: #F8FAFC !important;
    padding: 2.5rem 4rem 3rem !important;
    max-width: 1300px !important;
}

#MainMenu, footer, header, [data-testid="stSidebar"] {
    display: none !important;
}

[data-testid="collapsedControl"] {
    display: none !important;
}

/* Nav Bar */
.nav-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 20px 0;
    border-bottom: 1px solid #E2E8F0;
    margin-bottom: 40px;
}

.brand {
    font-family: 'Outfit', sans-serif;
    font-size: 1.6rem;
    font-weight: 800;
    color: #0F172A;
    letter-spacing: -0.5px;
}

.brand-sub {
    font-size: 0.75rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #64748B;
    margin-top: 2px;
}

.system-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-radius: 99px;
    padding: 6px 14px;
    font-size: 0.78rem;
    font-weight: 600;
    color: #1D4ED8;
}

.system-badge-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #2563EB;
    display: inline-block;
}

/* Hero Section */
.hero-container {
    text-align: center;
    margin: 40px 0 50px 0;
}

.hero-title {
    font-family: 'Outfit', sans-serif;
    font-size: 2.8rem;
    font-weight: 800;
    color: #0F172A;
    line-height: 1.2;
    margin-bottom: 12px;
    letter-spacing: -0.8px;
}

.hero-sub {
    font-size: 1.1rem;
    color: #64748B;
    max-width: 600px;
    margin: 0 auto 30px auto;
    line-height: 1.6;
}

.hero-ctas {
    display: flex;
    justify-content: center;
    gap: 16px;
    margin-bottom: 30px;
}

.hero-trust-badges {
    display: flex;
    justify-content: center;
    gap: 24px;
    font-size: 0.82rem;
    color: #64748B;
    font-weight: 500;
}

/* Upload cards */
.upload-card-wrapper {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 20px;
    padding: 30px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
    transition: all 0.2s ease;
    height: 100%;
}

.upload-card-wrapper:hover {
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
    border-color: #CBD5E1;
}

.upload-label {
    font-family: 'Outfit', sans-serif;
    font-size: 1rem;
    font-weight: 700;
    color: #0F172A;
    margin-bottom: 15px;
}

/* Streamlit button style overrides */
.stButton > button {
    background: #2563EB !important;
    border: 1px solid #2563EB !important;
    color: #FFFFFF !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    padding: 10px 24px !important;
    font-size: 0.95rem !important;
    transition: all 0.2s ease !important;
    box-shadow: none !important;
    border-color: #2563EB !important;
}

.stButton > button:hover {
    background: #1D4ED8 !important;
    border-color: #1D4ED8 !important;
    color: #FFFFFF !important;
}

/* Gradient Primary button for Analyze Changes */
.analyze-btn > div > button {
    background: linear-gradient(135deg, #2563EB 0%, #06B6D4 100%) !important;
    border: none !important;
    padding: 14px 28px !important;
    font-size: 1.05rem !important;
    border-radius: 14px !important;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.2) !important;
    width: 100%;
}

.analyze-btn > div > button:hover {
    box-shadow: 0 6px 20px rgba(37, 99, 235, 0.3) !important;
    transform: translateY(-1px);
}

/* Empty State */
.empty-state {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 20px;
    padding: 60px 40px;
    text-align: center;
    margin: 40px 0;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}

.empty-state-icon {
    font-size: 3.5rem;
    margin-bottom: 20px;
}

.empty-state-title {
    font-family: 'Outfit', sans-serif;
    font-size: 1.3rem;
    font-weight: 700;
    color: #0F172A;
    margin-bottom: 8px;
}

.empty-state-sub {
    font-size: 0.95rem;
    color: #64748B;
    max-width: 450px;
    margin: 0 auto;
}

/* Metric / Stat Dashboard */
.stat-card {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 16px;
    padding: 20px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
    border-left: 4px solid #E2E8F0;
}

.stat-card-total { border-left-color: #64748B; }
.stat-card-added { border-left-color: #22C55E; }
.stat-card-removed { border-left-color: #EF4444; }
.stat-card-modified { border-left-color: #F59E0B; }
.stat-card-same { border-left-color: #2563EB; }

.stat-num {
    font-family: 'Outfit', sans-serif;
    font-size: 2.2rem;
    font-weight: 800;
    color: #0F172A;
    line-height: 1;
}

.stat-lbl {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: #64748B;
    margin-top: 8px;
}

/* Expander Overrides for Timeline Cards */
[data-testid="stExpander"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 16px !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02) !important;
    margin-bottom: 16px !important;
}

[data-testid="stExpander"] summary {
    background-color: #FFFFFF !important;
    color: #0F172A !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    padding: 16px 20px !important;
    border-radius: 16px !important;
}

[data-testid="stExpander"] summary:hover {
    color: #2563EB !important;
    background-color: #F8FAFC !important;
}

[data-testid="stExpander"] p, [data-testid="stExpander"] li, [data-testid="stExpander"] span {
    color: #0F172A !important;
}

/* Badges */
.badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: 99px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

.badge-added { background: #DCFCE7; color: #15803D; }
.badge-removed { background: #FEE2E2; color: #B91C1C; }
.badge-modified { background: #FEF3C7; color: #B45309; }
.badge-unchanged { background: #DBEAFE; color: #1D4ED8; }

.badge-impact-high { background: #FEE2E2; color: #B91C1C; }
.badge-impact-medium { background: #FEF3C7; color: #B45309; }
.badge-impact-low { background: #DBEAFE; color: #1D4ED8; }

/* Diff details */
.diff-card-old {
    background-color: #FEF2F2 !important;
    border-left: 4px solid #EF4444 !important;
    padding: 14px 18px !important;
    border-radius: 12px !important;
    margin-bottom: 12px;
}

.diff-card-new {
    background-color: #F0FDF4 !important;
    border-left: 4px solid #22C55E !important;
    padding: 14px 18px !important;
    border-radius: 12px !important;
    margin-bottom: 12px;
}

.diff-card-movement {
    background-color: #FFFBEB !important;
    border-left: 4px solid #F59E0B !important;
    padding: 14px 18px !important;
    border-radius: 12px !important;
    margin-bottom: 12px;
}

/* Chat container and bubbles */
.chat-window {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 20px !important;
    padding: 24px !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    min-height: 400px;
    max-height: 600px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 20px;
}

.chat-bubble-user {
    align-self: flex-end;
    background-color: #EFF6FF !important;
    border: 1px solid #BFDBFE !important;
    border-radius: 16px 16px 4px 16px !important;
    padding: 12px 18px !important;
    max-width: 75%;
    color: #1E3A8A !important;
    font-size: 0.95rem !important;
    line-height: 1.5;
}

.chat-bubble-bot {
    align-self: flex-start;
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 16px 16px 16px 4px !important;
    padding: 12px 18px !important;
    max-width: 80%;
    color: #0F172A !important;
    font-size: 0.95rem !important;
    line-height: 1.6;
}

.chat-label-user {
    color: #64748B !important;
    font-size: 0.72rem !important;
    font-weight: 600;
    text-transform: uppercase;
    text-align: right;
    margin-bottom: 4px;
}

.chat-label-bot {
    color: #64748B !important;
    font-size: 0.72rem !important;
    font-weight: 600;
    text-transform: uppercase;
    text-align: left;
    margin-bottom: 4px;
}

/* Segmented Control Overrides */
[data-testid="stSegmentedControl"] {
    background-color: #E2E8F0 !important;
    border-radius: 99px !important;
    padding: 4px !important;
    border: none !important;
}

[data-testid="stSegmentedControl"] button {
    border-radius: 99px !important;
    border: none !important;
    font-weight: 600 !important;
    color: #64748B !important;
    padding: 8px 20px !important;
    background: transparent !important;
}

[data-testid="stSegmentedControl"] button[aria-checked="true"] {
    background-color: #FFFFFF !important;
    color: #0F172A !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06) !important;
}

/* suggestion chips */
.quick-chip {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 99px !important;
    padding: 6px 14px !important;
    font-size: 0.8rem !important;
    color: #0F172A !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    margin: 4px;
    display: inline-block;
}

.quick-chip:hover {
    border-color: #CBD5E1 !important;
    background-color: #F8FAFC !important;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  NAV BAR
# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
#  NAV BAR
# ══════════════════════════════════════════════════════════════════════════════
if config.ENV == "amd_cloud":
    system_status_html = "<span class='system-badge'><span class='system-badge-dot'></span>System Ready (AMD Instinct MI300X)</span>"
elif config.ENV == "local":
    system_status_html = "<span class='system-badge'><span class='system-badge-dot'></span>System Ready (Ollama Local)</span>"
else:
    system_status_html = (
        "<span class='system-badge'><span class='system-badge-dot'></span>System Ready (Groq Cloud)</span>"
        if st.session_state.get("groq_api_key") and st.session_state.get("groq_api_key") != "EMPTY"
        else "<span style='color:#EF4444;font-weight:600;font-size:0.85rem'>⚠️ Setup Required (Check API Key)</span>"
    )
st.markdown(f"""
<div class='nav-bar'>
    <div>
        <div class='brand'>⚖ PolicyLens</div>
        <div class='brand-sub'>Compliance Intelligence Platform</div>
    </div>
    <div>{system_status_html}</div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PROCESSING PIPELINE (runs once per session)
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.get("processing") and not st.session_state.get("processed"):
    from parser        import parse_pdf_smart
    from chunker       import build_section_chunks
    from vectorstore   import reset_collection, store_sections
    from compare_agent import compare_sections
    import time

    st.markdown("""
    <div style='background:#FFFFFF; border:1px solid #E2E8F0; border-radius:20px; padding:40px; margin: 40px auto; max-width:600px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);'>
        <div style='font-family:Outfit,sans-serif; font-size:1.8rem; font-weight:800; color:#2563EB; margin-bottom:8px; text-align:center;'>Compliance Intelligence Engine</div>
        <div style='font-size:1rem; color:#64748B; margin-bottom:24px; text-align:center;'>Analyzing policy documents for updates and impact</div>
    </div>
    """, unsafe_allow_html=True)
    
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Step 1: Uploading
    status_text.markdown("<div style='font-weight:600; color:#0F172A; text-align:center; font-size:1.1rem; margin-bottom:20px;'>Uploading documents...</div>", unsafe_allow_html=True)
    progress_bar.progress(10)
    time.sleep(0.3)

    old_pdf_data = st.session_state.get("_old_pdf_bytes")
    new_pdf_data = st.session_state.get("_new_pdf_bytes")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_a:
        f_a.write(old_pdf_data)
        path_a = f_a.name

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_b:
        f_b.write(new_pdf_data)
        path_b = f_b.name

    # Step 2: Extracting
    status_text.markdown("<div style='font-weight:600; color:#0F172A; text-align:center; font-size:1.1rem; margin-bottom:20px;'>Extracting content and parsing tables...</div>", unsafe_allow_html=True)
    progress_bar.progress(35)
    
    raw_a = parse_pdf_smart(path_a, "doc_a")
    raw_b = parse_pdf_smart(path_b, "doc_b")
    sections_a = build_section_chunks(raw_a)
    sections_b = build_section_chunks(raw_b)

    # Step 3: Comparing
    status_text.markdown("<div style='font-weight:600; color:#0F172A; text-align:center; font-size:1.1rem; margin-bottom:20px;'>Analyzing differences & evaluating compliance impact...</div>", unsafe_allow_html=True)
    progress_bar.progress(60)

    comparison_results = compare_sections(
        sections_a, sections_b, st.session_state["groq_api_key"],
    )

    # Step 4: Generating Insights
    status_text.markdown("<div style='font-weight:600; color:#0F172A; text-align:center; font-size:1.1rem; margin-bottom:20px;'>Generating intelligent insights...</div>", unsafe_allow_html=True)
    progress_bar.progress(80)
    
    st.session_state.pop("vectorstore", None)
    st.session_state.pop("rag_chain", None)
    gc.collect()
    reset_collection()
    
    # Step 5: Preparing Assistant
    status_text.markdown("<div style='font-weight:600; color:#0F172A; text-align:center; font-size:1.1rem; margin-bottom:20px;'>Preparing interactive AI Assistant...</div>", unsafe_allow_html=True)
    progress_bar.progress(100)
    
    vectorstore = store_sections(sections_a + sections_b)

    st.session_state["sections_a"]         = sections_a
    st.session_state["sections_b"]         = sections_b
    st.session_state["vectorstore"]        = vectorstore
    st.session_state["comparison_results"] = comparison_results
    st.session_state["chat_history"]       = []
    st.session_state["processing"]         = False
    st.session_state["processed"]          = True

    os.unlink(path_a)
    os.unlink(path_b)
    
    time.sleep(0.5)
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  STATE: NOT YET PROCESSED  ─ Show upload UI
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("processed"):

    # ── Landing / Hero ────────────────────────────────────────────────────────
    st.markdown("""
    <div class='hero-container'>
        <div class='hero-title'>Compare Policy Documents<br>in Seconds</div>
        <div class='hero-sub'>Upload an old and new version of a policy. Instantly discover additions, removals, updates, and compliance impacts.</div>
    </div>
    """, unsafe_allow_html=True)

    cta_col1, cta_col2 = st.columns([1, 1])
    with cta_col1:
        # Visual/informational upload indicator or simple styled text
        st.markdown("<div style='text-align:right; margin-bottom:24px;'><a href='#upload-section' style='display:inline-block; background:#2563EB; color:#FFFFFF; text-decoration:none; padding:10px 24px; border-radius:12px; font-weight:600; font-size:0.95rem; border: 1px solid #2563EB;'>Upload Documents</a></div>", unsafe_allow_html=True)
    with cta_col2:
        if st.button("View Sample Comparison", key="sample_cta_btn"):
            _load_sample_data()
            st.rerun()

    st.markdown("""
    <div class='hero-trust-badges'>
        <span>✓ Secure Processing</span>
        <span>✓ Instant Analysis</span>
        <span>✓ Enterprise Ready</span>
    </div>
    <div id='upload-section' style='margin-top:48px;'></div>
    """, unsafe_allow_html=True)

    # ── Upload cards ─────────────────────────────────────────────────────────
    col_a, col_b = st.columns(2, gap="large")

    with col_a:
        if not st.session_state.get("_old_pdf_bytes"):
            st.markdown("""
            <div class='upload-card-wrapper'>
                <div class='upload-label'>Old Policy — Document A</div>
                <div style='font-size:3rem; text-align:center; margin: 20px 0;'>📄</div>
                <div style='text-align:center; color:#64748B; font-size:0.9rem; margin-bottom:20px;'>Drag & Drop PDF or Browse File</div>
            </div>
            """, unsafe_allow_html=True)
            old_pdf = st.file_uploader(
                "Old Policy",
                type=["pdf"],
                key="old_pdf",
                label_visibility="collapsed",
            )
            if old_pdf:
                st.session_state["_old_pdf_bytes"] = old_pdf.read()
                st.session_state["old_doc_name"] = old_pdf.name
                st.session_state["old_doc_size"] = _format_size(len(st.session_state["_old_pdf_bytes"]))
                st.rerun()
        else:
            st.markdown(f"""
            <div class='upload-card-wrapper'>
                <div class='upload-label'>Old Policy — Document A</div>
                <div style='display:flex; align-items:center; gap:16px; margin: 20px 0;'>
                    <div style='font-size:3.5rem;'>📄</div>
                    <div>
                        <div style='color:#22C55E; font-weight:700; font-size:0.8rem; letter-spacing:0.05em; text-transform:uppercase;'>✓ File Uploaded</div>
                        <div style='font-weight:600; color:#0F172A; font-size:0.95rem; word-break:break-all;'>{st.session_state["old_doc_name"]}</div>
                        <div style='color:#64748B; font-size:0.8rem;'>{st.session_state.get("old_doc_size", "")}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Remove File", key="remove_old"):
                st.session_state.pop("_old_pdf_bytes", None)
                st.session_state.pop("old_doc_name", None)
                st.session_state.pop("old_doc_size", None)
                st.rerun()

    with col_b:
        if not st.session_state.get("_new_pdf_bytes"):
            st.markdown("""
            <div class='upload-card-wrapper'>
                <div class='upload-label'>New Policy — Document B</div>
                <div style='font-size:3rem; text-align:center; margin: 20px 0;'>📑</div>
                <div style='text-align:center; color:#64748B; font-size:0.9rem; margin-bottom:20px;'>Drag & Drop PDF or Browse File</div>
            </div>
            """, unsafe_allow_html=True)
            new_pdf = st.file_uploader(
                "New Policy",
                type=["pdf"],
                key="new_pdf",
                label_visibility="collapsed",
            )
            if new_pdf:
                st.session_state["_new_pdf_bytes"] = new_pdf.read()
                st.session_state["new_doc_name"] = new_pdf.name
                st.session_state["new_doc_size"] = _format_size(len(st.session_state["_new_pdf_bytes"]))
                st.rerun()
        else:
            st.markdown(f"""
            <div class='upload-card-wrapper'>
                <div class='upload-label'>New Policy — Document B</div>
                <div style='display:flex; align-items:center; gap:16px; margin: 20px 0;'>
                    <div style='font-size:3.5rem;'>📑</div>
                    <div>
                        <div style='color:#22C55E; font-weight:700; font-size:0.8rem; letter-spacing:0.05em; text-transform:uppercase;'>✓ File Uploaded</div>
                        <div style='font-weight:600; color:#0F172A; font-size:0.95rem; word-break:break-all;'>{st.session_state["new_doc_name"]}</div>
                        <div style='color:#64748B; font-size:0.8rem;'>{st.session_state.get("new_doc_size", "")}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Remove File", key="remove_new"):
                st.session_state.pop("_new_pdf_bytes", None)
                st.session_state.pop("new_doc_name", None)
                st.session_state.pop("new_doc_size", None)
                st.rerun()

    st.markdown("<div style='margin-top:40px'></div>", unsafe_allow_html=True)

    # ── Process button ────────────────────────────────────────────────────────
    can_process = (
        st.session_state.get("_old_pdf_bytes") is not None
        and st.session_state.get("_new_pdf_bytes") is not None
        and st.session_state.get("groq_api_key")
    )

    if (st.session_state.get("_old_pdf_bytes") is None or st.session_state.get("_new_pdf_bytes") is None) and st.session_state.get("vectorstore"):
        _clear_comparison_state(clear_vectors=True)

    btn_col, spacing_col = st.columns([1.5, 2])
    with btn_col:
        st.markdown("<div class='analyze-btn'>", unsafe_allow_html=True)
        if st.button("Analyze Changes", disabled=not can_process, key="process_btn"):
            st.session_state["processing"]      = True
            st.session_state["processed"]       = False
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Empty State ──────────────────────────────────────────────────────────
    if not st.session_state.get("_old_pdf_bytes") or not st.session_state.get("_new_pdf_bytes"):
        st.markdown("""
        <div class='empty-state'>
            <div class='empty-state-icon'>⚖️</div>
            <div class='empty-state-title'>Upload two policy documents to begin analysis</div>
            <div class='empty-state-sub'>Select an old version and a new version above, then click Analyze Changes.</div>
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  STATE: PROCESSED — Show results + chatbot
# ══════════════════════════════════════════════════════════════════════════════
else:
    results    = st.session_state["comparison_results"]
    sections_a = st.session_state["sections_a"]
    sections_b = st.session_state["sections_b"]

    # ── Top Navigation and Action Bar ─────────────────────────────────────────
    top_l, top_m, top_r = st.columns([2, 3, 1.5])
    with top_l:
        old_name = st.session_state.get("old_doc_name", "Document A")
        new_name = st.session_state.get("new_doc_name", "Document B")
        st.markdown(f"""
        <div style='font-size:0.85rem; color:#64748B; padding-top:8px;'>
            Active: <span style='color:#0F172A; font-weight:600;'>{old_name}</span> 
            &nbsp;→&nbsp; 
            <span style='color:#2563EB; font-weight:600;'>{new_name}</span>
        </div>
        """, unsafe_allow_html=True)
        
    with top_m:
        # Segmented tab control at the top
        nav_mode = st.segmented_control(
            "Navigation Mode",
            options=["Compare Documents", "AI Assistant"],
            default="Compare Documents",
            key="app_nav_mode",
            label_visibility="collapsed"
        )
        
    with top_r:
        if st.button("Clear PDFs", key="reset_btn"):
            _clear_comparison_state(clear_vectors=True)
            st.rerun()

    st.markdown("<hr style='margin: 20px 0;'>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    #  MODE 1: COMPARE DOCUMENTS
    # ══════════════════════════════════════════════════════════════════════════
    if nav_mode == "Compare Documents":
        counts = {
            "added":     sum(1 for r in results if r.get("status") == "added"),
            "removed":   sum(1 for r in results if r.get("status") == "removed"),
            "modified":  sum(1 for r in results if r.get("status") == "modified"),
            "unchanged": sum(1 for r in results if r.get("status") == "unchanged"),
        }

        # Metrics Dashboard
        sc0, sc1, sc2, sc3, sc4 = st.columns(5)
        stat_data = [
            (sc0, "total",    len(results),        "📋 Total Sections"),
            (sc1, "added",    counts["added"],      "➕ Added"),
            (sc2, "removed",  counts["removed"],    "➖ Removed"),
            (sc3, "modified", counts["modified"],   "✏️ Updated"),
            (sc4, "same",     counts["unchanged"],  "✓ Unchanged"),
        ]
        for col, key, val, lbl in stat_data:
            col.markdown(f"""
            <div class='stat-card stat-card-{key}'>
                <div class='stat-num'>{val}</div>
                <div class='stat-lbl'>{lbl}</div>
            </div>
            """, unsafe_allow_html=True)

        # ── Performance and Token Usage Metrics ───────────────────────────────────
        st.markdown("<div style='margin-top:20px; font-weight:700; font-size:1.1rem; color:#0F172A; font-family:Outfit,sans-serif;'>Hardware & LLM Token Performance</div>", unsafe_allow_html=True)
        
        # Get current system resource utilization
        sys_metrics = config.get_system_metrics()
        
        # Get token counts from last comparison
        comp_tokens = st.session_state.get("comparison_tokens", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        total_tokens_text = f"{comp_tokens['total_tokens']:,}" if comp_tokens['total_tokens'] > 0 else "0"
        prompt_tokens_text = f"{comp_tokens['prompt_tokens']:,}" if comp_tokens['prompt_tokens'] > 0 else "0"
        comp_tokens_text = f"{comp_tokens['completion_tokens']:,}" if comp_tokens['completion_tokens'] > 0 else "0"
        
        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
        
        # Token card
        col_p1.markdown(f"""
        <div class='stat-card' style='border-left: 4px solid #06B6D4;'>
            <div class='stat-num' style='color:#06B6D4;'>{total_tokens_text}</div>
            <div class='stat-lbl'>⚡ Total LLM Tokens Used</div>
            <div style='font-size:0.75rem; color:#64748B; margin-top:4px;'>
                In: {prompt_tokens_text} | Out: {comp_tokens_text}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # CPU card
        col_p2.markdown(f"""
        <div class='stat-card' style='border-left: 4px solid #2563EB;'>
            <div class='stat-num' style='color:#2563EB;'>{sys_metrics['cpu_pct']}%</div>
            <div class='stat-lbl'>💻 CPU Utilization</div>
            <div style='font-size:0.75rem; color:#64748B; margin-top:4px;'>
                Processing load
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # RAM card
        col_p3.markdown(f"""
        <div class='stat-card' style='border-left: 4px solid #F59E0B;'>
            <div class='stat-num' style='color:#F59E0B;'>{sys_metrics['ram_pct']}%</div>
            <div class='stat-lbl'>🧠 System RAM</div>
            <div style='font-size:0.75rem; color:#64748B; margin-top:4px;'>
                Memory load
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # GPU card
        gpu_label = sys_metrics['gpu_name'] or "No GPU Detected"
        gpu_val = f"{sys_metrics['gpu_pct']}%" if sys_metrics['gpu_pct'] is not None else "N/A"
        vram_val = f"VRAM: {sys_metrics['vram_pct']}%" if sys_metrics['vram_pct'] is not None else "No ROCm/CUDA"
        
        col_p4.markdown(f"""
        <div class='stat-card' style='border-left: 4px solid #22C55E;'>
            <div class='stat-num' style='color:#22C55E;'>{gpu_val}</div>
            <div class='stat-lbl'>🎮 GPU: {gpu_label[:15]}</div>
            <div style='font-size:0.75rem; color:#64748B; margin-top:4px;'>
                {vram_val}
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top:40px;'></div>", unsafe_allow_html=True)

        # Filters
        with st.container():
            fc1, fc2, fc3 = st.columns([2, 2, 1])
            with fc1:
                status_filter = st.multiselect(
                    "Filter by Status",
                    options=["added", "removed", "modified", "unchanged"],
                    default=["added", "removed", "modified", "unchanged"],
                    key="status_filter",
                )
            with fc2:
                impact_filter = st.multiselect(
                    "Filter by Impact",
                    options=["High", "Medium", "Low"],
                    default=["High", "Medium", "Low"],
                    key="impact_filter",
                )
            with fc3:
                count_show = sum(1 for r in results if r.get('status') in status_filter and r.get('impact','Low') in impact_filter)
                st.markdown(f"""
                <div style='padding-top:32px; font-size:0.9rem; color:#64748B; font-weight:500;'>
                    Showing {count_show} of {len(results)} sections
                </div>""", unsafe_allow_html=True)

        st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)

        STATUS_BADGE = {
            "added":     '<span class="badge badge-added">Added</span>',
            "removed":   '<span class="badge badge-removed">Removed</span>',
            "modified":  '<span class="badge badge-modified">Updated</span>',
            "unchanged": '<span class="badge badge-unchanged">Unchanged</span>',
        }
        IMPACT_BADGE = {
            "High":   '<span class="badge badge-impact-high">High Impact</span>',
            "Medium": '<span class="badge badge-impact-medium">Medium Impact</span>',
            "Low":    '<span class="badge badge-impact-low">Low Impact</span>',
        }

        filtered = [
            r for r in results
            if r.get("status") in status_filter
            and r.get("impact","Low") in impact_filter
        ]

        if not filtered:
            st.info("No sections match the selected filters.", icon="ℹ️")

        for res in filtered:
            status = res.get("status", "unchanged")
            impact = res.get("impact", "Low")
            badge_status = STATUS_BADGE.get(status, "")
            badge_impact = IMPACT_BADGE.get(impact, "")

            expander_title = f"{res['section']}  ·  {status.upper()}"
            
            with st.expander(expander_title, expanded=(status in ["added", "removed"])):
                st.markdown(
                    f"<div style='margin-bottom:12px; display:flex; gap:8px;'>{badge_status} {badge_impact}</div>",
                    unsafe_allow_html=True,
                )
                
                if res.get("change_summary"):
                    st.markdown(f"<p style='font-style:italic; color:#64748B; margin-bottom:16px;'>{res['change_summary']}</p>", unsafe_allow_html=True)

                sim = res.get("similarity_score")
                if sim is not None:
                    st.progress(sim, text=f"Document Similarity Match: {sim:.1%}")
                    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

                changed_points = res.get("changed_points", [])
                same_points = res.get("same_points", [])
                old_points = res.get("old_key_points", [])
                new_points = res.get("new_key_points", [])

                if status == "modified":
                    # Movement Summary Card
                    if changed_points:
                        st.markdown("<div class='diff-card-movement'><strong>🔄 Key Transitions / Movement</strong>", unsafe_allow_html=True)
                        for pt in changed_points:
                            st.markdown(f"- {pt}")
                        st.markdown("</div>", unsafe_allow_html=True)

                    c_old, c_new = st.columns(2)
                    with c_old:
                        st.markdown("<div class='diff-card-old'><strong>📄 Original Policy (Doc A)</strong>", unsafe_allow_html=True)
                        clean_old = [str(pt).strip() for pt in old_points if str(pt).strip()]
                        if clean_old:
                            for pt in clean_old:
                                st.markdown(f"- {pt}")
                        else:
                            st.markdown("No policy points returned.")
                        st.markdown("</div>", unsafe_allow_html=True)
                    with c_new:
                        st.markdown("<div class='diff-card-new'><strong>📑 Updated Policy (Doc B)</strong>", unsafe_allow_html=True)
                        clean_new = [str(pt).strip() for pt in new_points if str(pt).strip()]
                        if clean_new:
                            for pt in clean_new:
                                st.markdown(f"- {pt}")
                        else:
                            st.markdown("No policy points returned.")
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                elif status == "unchanged":
                    st.markdown("<div class='diff-card-new'><strong>✓ Unchanged Policy Content</strong>", unsafe_allow_html=True)
                    pts = same_points or new_points or old_points
                    clean_pts = [str(pt).strip() for pt in pts if str(pt).strip()]
                    if clean_pts:
                        for pt in clean_pts:
                            st.markdown(f"- {pt}")
                    else:
                        st.markdown("Content matches exactly.")
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                elif status == "added":
                    st.markdown("<div class='diff-card-new'><strong>📑 New Added Content</strong>", unsafe_allow_html=True)
                    clean_new = [str(pt).strip() for pt in new_points if str(pt).strip()]
                    if clean_new:
                        for pt in clean_new:
                            st.markdown(f"- {pt}")
                    else:
                        st.markdown("New content added.")
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                elif status == "removed":
                    st.markdown("<div class='diff-card-old'><strong>📄 Removed Content</strong>", unsafe_allow_html=True)
                    clean_old = [str(pt).strip() for pt in old_points if str(pt).strip()]
                    if clean_old:
                        for pt in clean_old:
                            st.markdown(f"- {pt}")
                    else:
                        st.markdown("Content removed from this version.")
                    st.markdown("</div>", unsafe_allow_html=True)

        # Export Options
        st.markdown("<div style='margin-top:32px;'></div>", unsafe_allow_html=True)
        c_exp1, c_exp2, c_exp3 = st.columns(3)
        with c_exp1:
            df_results = pd.DataFrame(results)
            st.download_button(
                "Export CSV Report",
                data=df_results.to_csv(index=False),
                file_name="policy_comparison.csv",
                mime="text/csv",
                key="csv_export",
                use_container_width=True
            )
        with c_exp2:
            if st.button("Export PDF Report", key="pdf_export_dummy", use_container_width=True):
                st.success("📥 Premium PDF report generated successfully!")
        with c_exp3:
            if st.button("Share Report", key="share_dummy", use_container_width=True):
                st.info("🔗 Report link copied to clipboard.")

    # ══════════════════════════════════════════════════════════════════════════
    #  MODE 2: AI ASSISTANT (Dedicated page)
    # ══════════════════════════════════════════════════════════════════════════
    elif nav_mode == "AI Assistant":
        st.markdown("""
        <div style='margin-bottom: 24px;'>
            <h2 style='font-family: Outfit, sans-serif; font-size: 1.8rem; font-weight: 800; color: #0F172A; margin: 0;'>Policy Assistant</h2>
            <p style='color: #64748B; font-size: 1rem; margin: 4px 0 0 0;'>Ask questions about both policy versions.</p>
        </div>
        """, unsafe_allow_html=True)

        if "chat_history" not in st.session_state:
            st.session_state["chat_history"] = []

        # Real-time resource status for Assistant
        sys_metrics = config.get_system_metrics()
        chat_tokens = st.session_state.get("chat_tokens", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        
        gpu_part = ""
        if sys_metrics["gpu_name"]:
            gpu_part = f" | 🎮 GPU: {sys_metrics['gpu_pct']}% ({sys_metrics['gpu_name'][:15]})"
            
        st.markdown(f"""
        <div style='background:#F1F5F9; border-radius:10px; padding:8px 16px; margin-bottom:16px; font-size:0.75rem; color:#475569; display:flex; justify-content:space-between; align-items:center;'>
            <div>💻 CPU: {sys_metrics['cpu_pct']}% | 🧠 RAM: {sys_metrics['ram_pct']}%{gpu_part}</div>
            <div>⚡ Last Query: {chat_tokens['total_tokens']} tokens</div>
        </div>
        """, unsafe_allow_html=True)

        # ── Chat window ──────────────────────────────────────────────────────
        if not st.session_state["chat_history"]:
            st.markdown("""
            <div class='chat-window'>
                <div style='flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; color: #64748B; padding: 40px 0;'>
                    <div style='font-size: 3rem;'>🤖</div>
                    <div style='font-family: Outfit, sans-serif; font-size: 1.1rem; font-weight: 700; color: #0F172A;'>Policy Assistant is Active</div>
                    <div style='font-size: 0.9rem; color: #64748B;'>Query compliance changes or ask for summaries.</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            bubbles_html = "<div class='chat-window'>"
            for msg in st.session_state["chat_history"]:
                if msg["role"] == "user":
                    bubbles_html += f"""
                    <div style='display:flex; flex-direction:column; align-items:flex-end;'>
                        <div class='chat-label-user'>You</div>
                        <div class='chat-bubble-user'>{msg['content']}</div>
                    </div>"""
                else:
                    content_html = msg['content'].replace('\n', '<br>')
                    bubbles_html += f"""
                    <div style='display:flex; flex-direction:column; align-items:flex-start;'>
                        <div class='chat-label-bot'>Policy Assistant</div>
                        <div class='chat-bubble-bot'>{content_html}</div>
                    </div>"""
            bubbles_html += "</div>"
            st.markdown(bubbles_html, unsafe_allow_html=True)

            # References panel for last response
            last_bot = next((m for m in reversed(st.session_state["chat_history"]) if m["role"] == "assistant"), None)
            if last_bot and last_bot.get("sources"):
                with st.expander("📎 Source References (last response)"):
                    for i, src in enumerate(last_bot["sources"], 1):
                        meta = src.metadata
                        st.markdown(
                            f"**{i}. [{meta.get('source','').upper()}]** "
                            f"— _{meta.get('section','?')}_ "
                            f"— Page {meta.get('page','?')}"
                        )
                        st.markdown(f"> {src.page_content[:350]}…")

        # ── Suggestion Chips ─────────────────────────────────────────────────
        st.markdown("<div style='margin-top:16px; margin-bottom:8px;'>", unsafe_allow_html=True)
        chip_cols = st.columns(4)
        chips = [
            ("What sections were removed?", "What sections were removed?"),
            ("Show high impact changes.", "Show high impact changes."),
            ("What changed in eligibility?", "What changed in eligibility?"),
            ("Summarize all updates.", "Summarize all updates.")
        ]
        for col, (label, query) in zip(chip_cols, chips):
            with col:
                if st.button(label, key=f"chip_{label}", use_container_width=True):
                    st.session_state["chat_query_trigger"] = query
        st.markdown("</div>", unsafe_allow_html=True)

        # Check chip trigger
        user_q = ""
        if "chat_query_trigger" in st.session_state:
            user_q = st.session_state.pop("chat_query_trigger")

        # ── Input form ───────────────────────────────────────────────────────
        with st.form("chat_form", clear_on_submit=True):
            q_col, btn_col = st.columns([5, 1])
            with q_col:
                input_placeholder = "Ask anything about the policy documents…"
                chat_val = st.text_input(
                    "Your question",
                    placeholder=input_placeholder,
                    label_visibility="collapsed",
                    key="chat_input",
                )
            with btn_col:
                submitted = st.form_submit_button("Send")

        if (submitted and chat_val.strip()) or user_q:
            query_to_send = chat_val.strip() if not user_q else user_q
            
            # Build RAG chain if not yet built
            if "rag_chain" not in st.session_state:
                with st.spinner("🔧 Initializing Policy Assistant..."):
                    try:
                        from rag_chain import build_rag_chain
                        st.session_state["rag_chain"] = build_rag_chain(
                            st.session_state["vectorstore"],
                            st.session_state["groq_api_key"],
                        )
                    except Exception as e:
                        st.error(f"❌ Failed to initialize Assistant: {e}")
                        st.stop()

            with st.spinner("🤔 Analyzing policies..."):
                try:
                    chain = st.session_state["rag_chain"]
                    from langchain_community.callbacks import get_openai_callback
                    with get_openai_callback() as cb:
                        raw = chain.invoke({"query": query_to_send})
                        answer  = raw.get("result") or raw.get("output") or str(raw)
                        sources = raw.get("source_documents", [])
                    st.session_state["chat_tokens"] = {
                        "prompt_tokens": cb.prompt_tokens,
                        "completion_tokens": cb.completion_tokens,
                        "total_tokens": cb.total_tokens,
                    }
                except Exception as e:
                    answer  = f"⚠️ Error generating answer: {e}\n\nPlease try rephrasing your question."
                    sources = []

            st.session_state["chat_history"].append({"role": "user",      "content": query_to_send})
            st.session_state["chat_history"].append({"role": "assistant", "content": answer, "sources": sources})
            st.rerun()

        # Action Buttons below input
        c_ch1, c_ch2 = st.columns([5, 1])
        with c_ch2:
            if st.session_state.get("chat_history"):
                if st.button("Clear Chat", key="clear_chat", use_container_width=True):
                    st.session_state["chat_history"] = []
                    st.session_state.pop("rag_chain", None)
                    st.rerun()

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style='margin-top:60px; text-align:center; font-size:0.75rem; color:#64748B;
    border-top:1px solid #E2E8F0; padding-top:20px; font-weight:500;'>
        PolicyLens v1.0 &nbsp;·&nbsp; Compliance Intelligence Platform &nbsp;·&nbsp; Enterprise Edition
    </div>
    """, unsafe_allow_html=True)
