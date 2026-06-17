# PolicyLens Code Submission

This document contains all source files for the PolicyLens application, compiled for hackathon submission.

---

## File: `.env`

```dotenv
# PolicyLens — Environment Variables
# Groq API Key (pre-configured for TCS Hackathon demo)
GROQ_API_KEY=YOUR_GROQ_API_KEY_HERE
ENV=groq


```

---

## File: `requirements.txt`

```text
streamlit>=1.35.0
pymupdf>=1.24.0
pdfplumber>=0.11.0
langchain>=0.2.0
langchain-community>=0.2.0
langchain-groq>=0.1.6
sentence-transformers>=3.0.0
scikit-learn>=1.4.0
chromadb>=0.5.0
pandas>=2.2.0
python-dotenv>=1.0.0
langchain-openai>=0.1.0
psutil>=5.9.0


```

---

## File: `config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()

ENV = os.getenv("ENV", "local")

def get_llm(groq_api_key: str = None):
    """Return LLM instance depending on environment."""
    if ENV == "local":
        # Local Ollama LLaMA 3.1 8B
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
            model="llama3.1:8b",
            temperature=0
        )
    elif ENV == "groq":
        from langchain_groq import ChatGroq
        api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set in environment or session state.")
        return ChatGroq(
            api_key=api_key,
            model="llama-3.1-8b-instant",
            temperature=0
        )
    else:
        # AMD Cloud — vLLM serving LLaMA on MI300X via ROCm
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url="http://127.0.0.1:8000/v1",
            api_key="EMPTY",
            model="meta-llama/Llama-3.1-8B-Instruct",
            temperature=0
        )

def get_embeddings():
    """Return embedding model instance depending on environment."""
    if ENV == "groq":
        # Local CPU embeddings for Groq cloud fallback
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError:
            from langchain_community.embeddings import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    else:
        # Both "local" (Ollama local) and "amd_cloud" (Ollama ROCm) use Ollama nomic-embed-text
        from langchain_community.embeddings import OllamaEmbeddings
        return OllamaEmbeddings(
            base_url="http://127.0.0.1:11434",
            model="nomic-embed-text"
        )

def get_system_metrics():
    """Retrieve system CPU, RAM, GPU, and LLaMA process metrics dynamically."""
    import psutil
    import subprocess
    import shutil
    import os
    
    metrics = {
        "cpu_pct": psutil.cpu_percent(interval=0.1),
        "ram_pct": psutil.virtual_memory().percent,
        "gpu_name": None,
        "gpu_pct": None,
        "vram_pct": None,
        "raw_gpu": "",
        "llama_cpu": 0.0,
        "llama_ram_gb": 0.0
    }
    
    # Track LLaMA/Ollama process usage (e.g. ollama.exe, llama-server.exe)
    for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_info']):
        try:
            pname = proc.info['name'].lower()
            if 'ollama' in pname or 'llama' in pname:
                metrics["llama_cpu"] += proc.info['cpu_percent'] or 0.0
                metrics["llama_ram_gb"] += (proc.info['memory_info'].rss or 0) / (1024 * 1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    metrics["llama_ram_gb"] = round(metrics["llama_ram_gb"], 2)
    metrics["llama_cpu"] = round(metrics["llama_cpu"], 1)
    
    # Try AMD ROCm GPU
    if shutil.which("rocm-smi"):
        try:
            res = subprocess.run(["rocm-smi"], capture_output=True, text=True, timeout=1.5)
            lines = res.stdout.splitlines()
            for line in lines:
                parts = line.strip().split()
                if parts and parts[0].isdigit():
                    if len(parts) >= 10:
                        vram = parts[-2].replace("%", "")
                        gpu_use = parts[-1].replace("%", "")
                        metrics["gpu_name"] = "AMD Instinct GPU"
                        metrics["gpu_pct"] = float(gpu_use) if gpu_use.isdigit() else 0.0
                        metrics["vram_pct"] = float(vram) if vram.isdigit() else 0.0
                        metrics["raw_gpu"] = res.stdout
                        break
        except Exception:
            pass
            
    # Try NVIDIA GPU (checking standard PATH and common Windows installations)
    else:
        nvidia_smi_path = shutil.which("nvidia-smi") or r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
        if os.path.exists(nvidia_smi_path):
            try:
                res = subprocess.run([nvidia_smi_path, "--query-gpu=name,utilization.gpu,utilization.memory", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=1.5)
                parts = res.stdout.strip().split(",")
                if len(parts) >= 3:
                    metrics["gpu_name"] = parts[0].strip()
                    metrics["gpu_pct"] = float(parts[1].strip())
                    metrics["vram_pct"] = float(parts[2].strip())
            except Exception:
                pass
                
        # Fallback for Windows Intel/AMD/NVIDIA GPU when specialized smi commands are missing
        if not metrics["gpu_name"] and os.name == 'nt':
            try:
                # Query GPU Name using PowerShell CIM
                cmd_name = "powershell -Command \"Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name\""
                res_name = subprocess.run(cmd_name, shell=True, capture_output=True, text=True, timeout=1.5)
                if res_name.returncode == 0 and res_name.stdout.strip():
                    metrics["gpu_name"] = res_name.stdout.strip().splitlines()[0]
                    
                # Query GPU utilization
                cmd_util = "powershell -Command \"Get-CimInstance -Query 'SELECT UtilizationPercentage FROM Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine' | Measure-Object -Property UtilizationPercentage -Max | Select-Object -ExpandProperty Maximum\""
                res_util = subprocess.run(cmd_util, shell=True, capture_output=True, text=True, timeout=1.5)
                if res_util.returncode == 0 and res_util.stdout.strip():
                    metrics["gpu_pct"] = float(res_util.stdout.strip())
                else:
                    metrics["gpu_pct"] = 0.0
                    
                metrics["vram_pct"] = 0.0  # Shared memory used by Intel doesn't map directly to VRAM % in the same way
            except Exception:
                pass
            
    return metrics


from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from typing import Any

class TokenTrackerCallback(BaseCallbackHandler):
    """Callback handler to track prompt, completion, and total tokens from LLMResult across any provider (Groq, Ollama, OpenAI, etc.)."""
    def __init__(self):
        super().__init__()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            for generations in response.generations:
                for gen in generations:
                    # Try extraction from generation_info
                    if gen.generation_info and 'token_usage' in gen.generation_info:
                        usage = gen.generation_info['token_usage']
                        self.prompt_tokens += usage.get('prompt_tokens', 0)
                        self.completion_tokens += usage.get('completion_tokens', 0)
                        self.total_tokens += usage.get('total_tokens', 0)
                    elif gen.generation_info and 'usage' in gen.generation_info:
                        usage = gen.generation_info['usage']
                        self.prompt_tokens += usage.get('prompt_tokens', 0)
                        self.completion_tokens += usage.get('completion_tokens', 0)
                        self.total_tokens += usage.get('total_tokens', 0)
                    # Try extraction from message response_metadata
                    elif gen.message and hasattr(gen.message, 'response_metadata') and gen.message.response_metadata:
                        meta = gen.message.response_metadata
                        if 'token_usage' in meta:
                            self.prompt_tokens += meta['token_usage'].get('prompt_tokens', 0)
                            self.completion_tokens += meta['token_usage'].get('completion_tokens', 0)
                            self.total_tokens += meta['token_usage'].get('total_tokens', 0)
                        elif 'usage' in meta:
                            self.prompt_tokens += meta['usage'].get('prompt_tokens', 0)
                            self.completion_tokens += meta['usage'].get('completion_tokens', 0)
                            self.total_tokens += meta['usage'].get('total_tokens', 0)
        except Exception:
            pass



```

---

## File: `utils_pdf.py`

```python
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

```

---

## File: `compare_agent.py`

```python
"""
compare_agent.py
----------------
Section-by-section policy comparison with local embeddings and LLM analysis.

Accuracy choices:
- Compare full section text, including tables.
- Treat tiny numeric/date/currency changes as modified even if cosine
  similarity is high.
- Fuzzy-match renamed headings by content similarity before marking sections
  as added or removed.
"""
import json
import re
from typing import Any
import streamlit as st

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity as sk_cosine

from chunker import sections_to_full_text
from config import get_llm


SIMILARITY_THRESHOLD = 0.95
FUZZY_SECTION_MATCH_THRESHOLD = 0.78
SAFE_UNCHANGED_THRESHOLD = 0.985
EMBED_MODEL = "all-MiniLM-L6-v2"
LLM_MODEL = "llama-3.1-8b-instant"

_embed_model: SentenceTransformer | None = None


def _get_embed_model() -> SentenceTransformer:
    """Lazy-load the sentence-transformer model."""
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(EMBED_MODEL)
    return _embed_model


def _cosine_sim(text_a: str, text_b: str) -> float:
    """Compute cosine similarity between two strings."""
    model = _get_embed_model()
    vecs = model.encode([text_a, text_b], normalize_embeddings=True)
    return float(sk_cosine([vecs[0]], [vecs[1]])[0][0])


def _section_text(section: dict, limit: int | None = None) -> str:
    """Return comparison text with heading, body, and tables."""
    full_text = sections_to_full_text(section)
    text = f"SECTION: {section.get('heading', '')}\n{full_text}".strip()
    if limit and len(text) > limit:
        half = limit // 2
        return text[:half] + "\n...[middle omitted for length]...\n" + text[-half:]
    return text


def _normalize_heading(heading: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", heading.lower())).strip()


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _sensitive_tokens(text: str) -> set[str]:
    """Extract values where small changes are policy-significant."""
    pattern = r"[$₹€£]?\s*\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|percent|days?|months?|years?|hours?)?"
    return {re.sub(r"\s+", "", token.lower()) for token in re.findall(pattern, text, flags=re.I)}


def _has_sensitive_differences(text_a: str, text_b: str) -> bool:
    return _sensitive_tokens(text_a) != _sensitive_tokens(text_b)


def _merge_duplicate_headings(sections: list[dict]) -> dict[str, dict]:
    """Merge duplicate headings so later duplicates do not overwrite content."""
    merged: dict[str, dict] = {}
    for section in sections:
        key = _normalize_heading(section.get("heading", ""))
        if not key:
            key = f"section-{len(merged) + 1}"
        if key not in merged:
            merged[key] = {
                **section,
                "content": list(section.get("content", [])),
                "tables": list(section.get("tables", [])),
            }
            continue
        merged[key]["content"].extend(section.get("content", []))
        merged[key]["tables"].extend(section.get("tables", []))
    return merged


def _content_points(section: dict, limit: int = 5) -> list[str]:
    points: list[str] = []
    for item in section.get("content", []):
        text = str(item).strip()
        if text:
            points.append(text)
        if len(points) >= limit:
            break
    if len(points) < limit:
        for table in section.get("tables", []):
            text = str(table).strip()
            if text:
                points.append(text)
            if len(points) >= limit:
                break
    return points


def _same_points(points_a: list[str], points_b: list[str], limit: int = 5) -> list[str]:
    normalized_b = {p.strip().lower(): p for p in points_b}
    same: list[str] = []
    for point in points_a:
        if point.strip().lower() in normalized_b:
            same.append(point)
        if len(same) >= limit:
            break
    return same


def _ensure_result_shape(result: dict) -> dict:
    result.setdefault("status", "modified")
    result.setdefault("change_summary", "This section changed between the old and new policy.")
    result.setdefault("old_key_points", [])
    result.setdefault("new_key_points", [])
    result.setdefault("changed_points", [])
    result.setdefault("same_points", [])
    result.setdefault("impact", "Low")
    result.setdefault("table_changed", False)
    if result["status"] not in {"modified", "unchanged"}:
        result["status"] = "modified"
    if result["impact"] not in {"High", "Medium", "Low"}:
        result["impact"] = "Low"
    result["table_changed"] = bool(result["table_changed"])
    return result


def _parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if match:
        raw = match.group(0)
    return json.loads(raw)


def _build_llm(groq_api_key: str) -> Any:
    return get_llm(groq_api_key)


COMPARE_PROMPT_TEMPLATE = """You are a policy document analyst. Compare these two sections.

SECTION MATCH: {section_name}

OLD POLICY (Doc A):
{doc_a_text}

NEW POLICY (Doc B):
{doc_b_text}

Return a JSON object with exactly these fields:
{{
  "status": "modified" | "unchanged",
  "change_summary": "short direct statement of the exact change",
  "old_key_points": ["old policy point that changed or was removed"],
  "new_key_points": ["new policy point that changed or was added"],
  "changed_points": ["clear before-to-after change, including old value and new value when available"],
  "same_points": ["important points that stayed the same"],
  "impact": "High" | "Medium" | "Low",
  "table_changed": true | false
}}

Rules:
- Compare headings, text, numbers, dates, limits, eligibility, exclusions, and tables.
- Do not give a high-level summary only.
- For changed_points, write clear before -> after statements.
- If nothing changed, status must be "unchanged" and changed_points must be [].
- Keep each array item short, factual, and grounded in the provided text.
- Return ONLY valid JSON, no markdown fences, no extra text."""


def _find_fuzzy_matches(
    a_map: dict[str, dict],
    b_map: dict[str, dict],
    unmatched_a: list[str],
    unmatched_b: list[str],
) -> list[tuple[str, str, float]]:
    """Greedily match renamed sections by content similarity."""
    candidates: list[tuple[float, str, str]] = []
    for a_key in unmatched_a:
        text_a = _section_text(a_map[a_key], limit=6000)
        for b_key in unmatched_b:
            text_b = _section_text(b_map[b_key], limit=6000)
            sim = _cosine_sim(text_a, text_b)
            if sim >= FUZZY_SECTION_MATCH_THRESHOLD:
                candidates.append((sim, a_key, b_key))

    matches: list[tuple[str, str, float]] = []
    used_a: set[str] = set()
    used_b: set[str] = set()
    for sim, a_key, b_key in sorted(candidates, reverse=True):
        if a_key in used_a or b_key in used_b:
            continue
        matches.append((a_key, b_key, sim))
        used_a.add(a_key)
        used_b.add(b_key)
    return matches


def _compare_matched_section(
    llm: Any,
    heading: str,
    a: dict,
    b: dict,
    sim: float,
    heading_changed: bool = False,
) -> dict:
    text_a_full = _section_text(a)
    text_b_full = _section_text(b)
    text_a = _section_text(a, limit=6000)
    text_b = _section_text(b, limit=6000)
    old_points = _content_points(a)
    new_points = _content_points(b)
    same_points = _same_points(old_points, new_points)
    normalized_equal = _normalize_text(text_a_full) == _normalize_text(text_b_full)
    sensitive_changed = _has_sensitive_differences(text_a_full, text_b_full)
    tables_changed = "\n\n".join(a.get("tables", [])) != "\n\n".join(b.get("tables", []))

    if not heading_changed and (normalized_equal or (sim >= SAFE_UNCHANGED_THRESHOLD and not sensitive_changed and not tables_changed)):
        return {
            "section": heading,
            "status": "unchanged",
            "change_summary": f"No material change detected. Similarity: {sim:.1%}.",
            "old_key_points": old_points,
            "new_key_points": new_points,
            "changed_points": [],
            "same_points": same_points or new_points,
            "impact": "Low",
            "table_changed": False,
            "similarity_score": round(sim, 4),
        }

    prompt_text = COMPARE_PROMPT_TEMPLATE.format(
        section_name=heading,
        doc_a_text=text_a,
        doc_b_text=text_b,
    )
    tokens_used = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    try:
        from config import TokenTrackerCallback
        tracker = TokenTrackerCallback()
        response = llm.invoke(prompt_text, config={"callbacks": [tracker]})
        
        tokens_used = {
            "prompt_tokens": tracker.prompt_tokens,
            "completion_tokens": tracker.completion_tokens,
            "total_tokens": tracker.total_tokens
        }
        result = _parse_json_response(response.content)
    except Exception as exc:
        result = {
            "status": "modified",
            "change_summary": f"Could not parse LLM response: {exc}",
            "old_key_points": old_points,
            "new_key_points": new_points,
            "changed_points": ["AI comparison failed; review the old and new points shown below."],
            "same_points": same_points,
            "impact": "Low",
            "table_changed": tables_changed,
        }

    result = _ensure_result_shape(result)
    if heading_changed:
        heading_note = f"Heading changed: '{a.get('heading', '')}' -> '{b.get('heading', '')}'."
        result["status"] = "modified"
        result["changed_points"] = [heading_note] + result.get("changed_points", [])
        if result.get("change_summary") == "This section changed between the old and new policy.":
            result["change_summary"] = heading_note
    result["section"] = heading
    result["similarity_score"] = round(sim, 4)
    result["table_changed"] = bool(result.get("table_changed")) or tables_changed
    result["tokens"] = tokens_used
    return result


def compare_sections(
    doc_a_sections: list[dict],
    doc_b_sections: list[dict],
    groq_api_key: str,
) -> list[dict]:
    """Compare all sections between two policy documents."""
    llm = _build_llm(groq_api_key)
    a_map = _merge_duplicate_headings(doc_a_sections)
    b_map = _merge_duplicate_headings(doc_b_sections)

    exact_keys = [key for key in a_map if key in b_map]
    unmatched_a = [key for key in a_map if key not in b_map]
    unmatched_b = [key for key in b_map if key not in a_map]
    fuzzy_matches = _find_fuzzy_matches(a_map, b_map, unmatched_a, unmatched_b)
    fuzzy_a = {a_key for a_key, _, _ in fuzzy_matches}
    fuzzy_b = {b_key for _, b_key, _ in fuzzy_matches}

    results: list[dict] = []
    skipped = 0
    llm_calls = 0

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0

    for key in exact_keys:
        a = a_map[key]
        b = b_map[key]
        sim = _cosine_sim(_section_text(a, limit=6000), _section_text(b, limit=6000))
        result = _compare_matched_section(llm, a.get("heading", key), a, b, sim)
        results.append(result)
        if result["status"] == "unchanged":
            skipped += 1
        else:
            llm_calls += 1
            toks = result.get("tokens", {})
            total_prompt_tokens += toks.get("prompt_tokens", 0)
            total_completion_tokens += toks.get("completion_tokens", 0)
            total_tokens += toks.get("total_tokens", 0)

    for a_key, b_key, sim in fuzzy_matches:
        a = a_map[a_key]
        b = b_map[b_key]
        heading = f"{a.get('heading', a_key)} -> {b.get('heading', b_key)}"
        result = _compare_matched_section(llm, heading, a, b, sim, heading_changed=True)
        results.append(result)
        llm_calls += 1
        toks = result.get("tokens", {})
        total_prompt_tokens += toks.get("prompt_tokens", 0)
        total_completion_tokens += toks.get("completion_tokens", 0)
        total_tokens += toks.get("total_tokens", 0)

    st.session_state["comparison_tokens"] = {
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_tokens": total_tokens,
    }

    for key in unmatched_b:
        if key in fuzzy_b:
            continue
        b = b_map[key]
        results.append({
            "section": b.get("heading", key),
            "status": "added",
            "change_summary": "This section was added in the new policy.",
            "old_key_points": [],
            "new_key_points": _content_points(b),
            "changed_points": ["New section added in Document B."],
            "same_points": [],
            "impact": "High",
            "table_changed": len(b.get("tables", [])) > 0,
            "similarity_score": None,
        })

    for key in unmatched_a:
        if key in fuzzy_a:
            continue
        a = a_map[key]
        results.append({
            "section": a.get("heading", key),
            "status": "removed",
            "change_summary": "This section was removed in the new policy.",
            "old_key_points": _content_points(a),
            "new_key_points": [],
            "changed_points": ["Section from Document A is not present in Document B."],
            "same_points": [],
            "impact": "High",
            "table_changed": len(a.get("tables", [])) > 0,
            "similarity_score": None,
        })

    total_both = llm_calls + skipped
    if total_both > 0:
        savings_pct = round(skipped / total_both * 100)
        print(
            f"[compare_agent] LLM calls: {llm_calls} | "
            f"Skipped (unchanged): {skipped} | "
            f"Token savings: ~{savings_pct}%"
        )

    return results

```

---

## File: `rag_chain.py`

```python
"""
rag_chain.py
------------
Source-aware RAG chatbot chain.

The custom RAG_PROMPT instructs the LLM to:
  - Always cite whether information is from Doc A (old policy) or Doc B (new policy).
  - Compare both sources when the same topic appears in both.
  - Refuse to speculate beyond the retrieved context.
"""

try:
    from langchain.chains import RetrievalQA
except ModuleNotFoundError:
    from langchain_classic.chains import RetrievalQA

try:
    from langchain.prompts import PromptTemplate
except ModuleNotFoundError:
    from langchain_classic.prompts import PromptTemplate
from config import get_llm
from langchain_community.vectorstores import Chroma


RAG_PROMPT = """You are a policy document assistant. Answer ONLY based on the provided context.

Rules:
- Always specify whether information comes from the OLD policy (Doc A) or NEW policy (Doc B).
- If the same topic exists in both documents, compare them explicitly.
- If the answer is not found in the context, say "I could not find this in the provided policies."
- Be concise and structured. Use bullet points when listing multiple points.

Context:
{context}

Question: {question}

Answer (always cite Doc A or Doc B):"""


def build_rag_chain(vectorstore: Chroma, groq_api_key: str) -> RetrievalQA:
    """
    Build a LangChain RetrievalQA chain over the ChromaDB vectorstore.

    Args:
        vectorstore  : populated Chroma vectorstore
        groq_api_key : Groq API key

    Returns:
        RetrievalQA chain (call with {"query": "your question"})
    """
    llm = get_llm(groq_api_key)

    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={
            "k": 6,          # retrieve top-6 chunks for balanced coverage
        },
    )

    chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        chain_type_kwargs={
            "prompt": PromptTemplate(
                template=RAG_PROMPT,
                input_variables=["context", "question"],
            )
        },
        return_source_documents=True,
    )

    return chain

```

---

## File: `vectorstore.py`

```python
"""
vectorstore.py
--------------
ChromaDB vector store management with local HuggingFace embeddings.

Every new comparison clears the previous Chroma collection so old PDF vectors
do not bleed into new results.
"""

import gc
import os

from typing import Any
from langchain_community.vectorstores import Chroma
from config import get_embeddings


PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION = "policy_compare"
EMBED_MODEL = "all-MiniLM-L6-v2"


def _get_embeddings() -> Any:
    """Return the embedding model instance depending on environment."""
    return get_embeddings()


def reset_collection() -> None:
    """
    Delete and recreate the ChromaDB collection.

    NEVER use shutil.rmtree on the chroma_db folder while Streamlit is running.
    ChromaDB keeps .bin index files locked on Windows (WinError 32).
    Instead, use the ChromaDB client API to drop and recreate the collection.
    """
    import chromadb

    os.makedirs(PERSIST_DIR, exist_ok=True)
    gc.collect()

    try:
        client = chromadb.PersistentClient(path=PERSIST_DIR)
    except Exception:
        # If even opening fails (corrupt DB), wipe folder with error handler
        import shutil
        import time

        def _on_error(func, path, exc_info):
            """Silently skip locked files on Windows."""
            pass

        shutil.rmtree(PERSIST_DIR, onexc=_on_error)
        time.sleep(0.3)
        os.makedirs(PERSIST_DIR, exist_ok=True)
        client = chromadb.PersistentClient(path=PERSIST_DIR)

    try:
        collection = client.get_collection(name=COLLECTION)
        existing = collection.get(include=[])
        ids = existing.get("ids", [])
        if ids:
            for start in range(0, len(ids), 500):
                collection.delete(ids=ids[start:start + 500])
    except Exception:
        pass

    try:
        client.delete_collection(name=COLLECTION)
    except Exception:
        pass

    try:
        client.get_or_create_collection(name=COLLECTION)
    except Exception:
        pass

    gc.collect()


def store_sections(sections: list[dict]) -> Chroma:
    """
    Embed and persist a list of section dicts into ChromaDB.

    Each section becomes one document in the store with metadata:
        source    : "doc_a" | "doc_b"
        section   : heading text
        page      : page number
        has_table : bool
    """
    from chunker import sections_to_full_text

    texts: list[str] = []
    metadatas: list[dict] = []

    for sec in sections:
        full_text = sections_to_full_text(sec)
        if not full_text.strip():
            continue
        source_label = "Doc A (old policy)" if sec["source"] == "doc_a" else "Doc B (new policy)"
        texts.append(
            f"SOURCE: {source_label}\n"
            f"SECTION: {sec['heading']}\n"
            f"PAGE: {sec.get('page', 0)}\n\n"
            f"{full_text}"
        )
        metadatas.append(
            {
                "source": sec["source"],
                "section": sec["heading"],
                "page": sec.get("page", 0),
                "has_table": str(len(sec["tables"]) > 0),
            }
        )

    embeddings = _get_embeddings()
    return Chroma.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        collection_name=COLLECTION,
        persist_directory=PERSIST_DIR,
    )


def load_vectorstore() -> Chroma:
    """Load an existing persisted ChromaDB collection without re-embedding."""
    embeddings = _get_embeddings()
    return Chroma(
        collection_name=COLLECTION,
        embedding_function=embeddings,
        persist_directory=PERSIST_DIR,
    )

```

---

## File: `chunker.py`

```python
"""
chunker.py
----------
Section-aware chunking.
Groups flat text/table chunks (from parser.py) under their parent heading,
producing richer, semantically-complete sections that embed far better
than fixed-size character windows.
"""


def build_section_chunks(raw_chunks: list[dict]) -> list[dict]:
    """
    Merge raw_chunks into section dicts keyed by heading.

    Each section dict has:
        heading   : str  – the heading text that introduced this section
        content   : list[str] – plain text paragraphs inside the section
        tables    : list[str] – markdown table strings inside the section
        source    : str  – "doc_a" or "doc_b"
        page      : int  – page number of the heading (or first content block)

    The default "Introduction" catch-all is only emitted if it contains
    meaningful content (>30 chars). Tiny intro sections are almost always
    header/footer scraps that slipped through the parser.

    Args:
        raw_chunks : output of parse_pdf_smart()

    Returns:
        list of section dicts
    """
    sections: list[dict] = []

    # Minimum total characters for the default "Introduction" section
    # to be considered real content (not just header/footer leftovers).
    _MIN_INTRO_CHARS = 30

    # Seed a default section for content that comes before any heading
    current_section: dict = {
        "heading": "Introduction",
        "content": [],
        "tables":  [],
        "source":  raw_chunks[0]["source"] if raw_chunks else "",
        "page":    1,
    }

    for chunk in raw_chunks:
        if chunk["type"] == "heading":
            # Flush current section before starting a new one
            if current_section["content"] or current_section["tables"]:
                # Skip trivially small "Introduction" sections (header/footer noise)
                if current_section["heading"] == "Introduction":
                    total_chars = sum(len(t) for t in current_section["content"])
                    if total_chars < _MIN_INTRO_CHARS and not current_section["tables"]:
                        # Too small — discard this noise section
                        current_section = {
                            "heading": chunk["text"],
                            "content": [],
                            "tables":  [],
                            "source":  chunk["source"],
                            "page":    chunk["page"],
                        }
                        continue
                sections.append(current_section)
            current_section = {
                "heading": chunk["text"],
                "content": [],
                "tables":  [],
                "source":  chunk["source"],
                "page":    chunk["page"],
            }
        elif chunk["type"] == "table":
            current_section["tables"].append(chunk["text"])
        else:                               # plain text
            current_section["content"].append(chunk["text"])

    # Flush the last section
    if current_section["content"] or current_section["tables"]:
        # Same intro guard for the last section
        if current_section["heading"] == "Introduction":
            total_chars = sum(len(t) for t in current_section["content"])
            if total_chars < _MIN_INTRO_CHARS and not current_section["tables"]:
                pass  # discard noise
            else:
                sections.append(current_section)
        else:
            sections.append(current_section)

    return sections


def sections_to_full_text(section: dict) -> str:
    """
    Combine text paragraphs and markdown tables of a section into a
    single string that is stored in ChromaDB.
    """
    parts = ["\n".join(section["content"])]
    if section["tables"]:
        parts.append("\n\nTABLES IN THIS SECTION:\n" + "\n\n".join(section["tables"]))
    return "\n".join(parts).strip()

```

---

## File: `parser.py`

```python
"""
parser.py
---------
Dual-parser strategy for extracting text and tables from PDF files.
- PyMuPDF extracts structured text and detects headings by font size.
- pdfplumber extracts tables and converts them to Markdown.
"""

import re

import fitz
import pdfplumber


_HEADER_FOOTER_PATTERNS = [
    re.compile(r"^(legacy|modernized|revised|updated|draft|final)\s+v?\d", re.I),
    re.compile(r"^v\d+(\.\d+)+", re.I),
    re.compile(r"^version\s+\d", re.I),
    re.compile(r"^(confidential|internal|restricted|public)\b", re.I),
    re.compile(r"^(effective|issued|revised)\s+(date|on)", re.I),
    re.compile(r"^page\s+\d+", re.I),
    re.compile(r"^\d+\s*$"),
    re.compile(r"^(doc|document)\s*(id|#|no|number)", re.I),
    re.compile(r"^(copyright|©)\s*\d{4}", re.I),
    re.compile(r"^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\s*$"),
    re.compile(r"^(all rights reserved|proprietary)", re.I),
]

_MAX_NOISE_LEN = 80


def _is_header_footer_noise(text: str) -> bool:
    """Return True if the text looks like document header/footer metadata."""
    if len(text) > _MAX_NOISE_LEN:
        return False
    return any(pattern.search(text) for pattern in _HEADER_FOOTER_PATTERNS)


def table_to_markdown(table: list[list]) -> str:
    """Convert a 2-D list from pdfplumber into GitHub-style Markdown."""
    if not table or not table[0]:
        return ""
    header = "| " + " | ".join(str(cell or "").strip() for cell in table[0]) + " |"
    separator = "| " + " | ".join(["---"] * len(table[0])) + " |"
    rows = [
        "| " + " | ".join(str(cell or "").strip() for cell in row) + " |"
        for row in table[1:]
    ]
    return "\n".join([header, separator] + rows)


def parse_pdf_smart(pdf_path: str, source_tag: str) -> list[dict]:
    """
    Parse a PDF and return ordered chunks:
        {text, type, page, source}

    Tables are emitted immediately after the text from the same page. This keeps
    the chunker from attaching every table to the final section in the document.
    """
    chunks: list[dict] = []

    doc = fitz.open(pdf_path)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(doc):
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    if block["type"] != 0:
                        continue
                    lines = block.get("lines", [])
                    if not lines:
                        continue

                    text = " ".join(
                        span["text"]
                        for line in lines
                        for span in line.get("spans", [])
                    ).strip()

                    if not text or _is_header_footer_noise(text):
                        continue

                    font_size = lines[0]["spans"][0]["size"] if lines[0].get("spans") else 11
                    chunks.append(
                        {
                            "text": text,
                            "type": "heading" if font_size > 13 else "text",
                            "page": page_num + 1,
                            "source": source_tag,
                        }
                    )

                if page_num >= len(pdf.pages):
                    continue
                for table in pdf.pages[page_num].extract_tables():
                    table_md = table_to_markdown(table)
                    if table_md:
                        chunks.append(
                            {
                                "text": f"[TABLE on page {page_num + 1}]\n{table_md}",
                                "type": "table",
                                "page": page_num + 1,
                                "source": source_tag,
                            }
                        )
    finally:
        doc.close()

    return chunks

```

---

## File: `app.py`

```python
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
# Determine dynamic backend to show in top status badge
current_env = config.ENV
if "inference_env_select" in st.session_state:
    selected = st.session_state["inference_env_select"]
    current_env = "groq" if "Groq" in selected else "local"

if current_env == "amd_cloud":
    system_status_html = "<span class='system-badge'><span class='system-badge-dot'></span>System Ready (AMD Instinct MI300X)</span>"
elif current_env == "local":
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

    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
    
    # ── Inference settings container ──────────────────────────────────────────
    with st.container():
        st.markdown("""
        <div style='background:#FFFFFF; border:1px solid #E2E8F0; border-radius:16px; padding:20px 24px; margin-bottom:24px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);'>
            <div style='font-family:Outfit,sans-serif; font-size:1.1rem; font-weight:700; color:#0F172A; margin-bottom:6px;'>
                ⚙️ LLM Inference Engine Config
            </div>
            <div style='font-size:0.85rem; color:#64748B; margin-bottom:16px;'>
                Select the runtime environment for analysis. Groq runs fast on the cloud, while Local LLaMA runs on your local machine using Ollama.
            </div>
        """, unsafe_allow_html=True)
        
        cfg_col1, cfg_col2 = st.columns([1.5, 2.5])
        with cfg_col1:
            selected_env = st.selectbox(
                "Inference Engine",
                options=["Groq Cloud (Fast)", "Local LLaMA (Ollama)"],
                index=0 if config.ENV == "groq" else 1,
                key="inference_env_select",
                label_visibility="visible"
            )
            # Update config ENV dynamically
            if selected_env == "Groq Cloud (Fast)":
                config.ENV = "groq"
            else:
                config.ENV = "local"
                
        with cfg_col2:
            if config.ENV == "groq":
                api_key_val = st.text_input(
                    "Groq API Key",
                    value=st.session_state.get("groq_api_key", "") if st.session_state.get("groq_api_key") != "EMPTY" else _ENV_GROQ_KEY,
                    type="password",
                    key="groq_key_input"
                )
                if api_key_val:
                    st.session_state["groq_api_key"] = api_key_val
                else:
                    st.session_state["groq_api_key"] = _ENV_GROQ_KEY
            else:
                st.session_state["groq_api_key"] = "EMPTY"
                st.markdown("""
                <div style='padding: 10px 14px; background-color:#EFF6FF; border:1px solid #BFDBFE; border-radius:8px; font-size:0.8rem; color:#1E3A8A; display:flex; align-items:center; gap:8px;'>
                    <span>💡 Running via Ollama locally. LLaMA 3.1 8B on CPU/GPU is utilized.</span>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

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
        
        col_p1, col_p2, col_p3, col_p4, col_p5 = st.columns(5)
        
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

        # LLaMA process memory card
        llama_ram = sys_metrics.get('llama_ram_gb', 0.0)
        llama_cpu = sys_metrics.get('llama_cpu', 0.0)
        col_p5.markdown(f"""
        <div class='stat-card' style='border-left: 4px solid #8B5CF6;'>
            <div class='stat-num' style='color:#8B5CF6;'>{llama_ram} GB</div>
            <div class='stat-lbl'>🦙 LLaMA Memory</div>
            <div style='font-size:0.75rem; color:#64748B; margin-top:4px;'>
                CPU Usage: {llama_cpu}%
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
                tokens = res.get("tokens")
                token_html = ""
                if tokens and tokens.get("total_tokens", 0) > 0:
                    token_html = f"""
                    <span style='background-color:#E0F7FA; color:#006064; border-radius:12px; padding:3px 10px; font-size:0.75rem; font-weight:600; font-family:monospace; margin-left:8px; border: 1px solid #B2EBF2;'>
                        ⚡ {tokens['total_tokens']} tokens (In: {tokens['prompt_tokens']} | Out: {tokens['completion_tokens']})
                    </span>
                    """
                st.markdown(
                    f"<div style='margin-bottom:12px; display:flex; gap:8px; align-items:center;'>{badge_status} {badge_impact} {token_html}</div>",
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
            try:
                from utils_pdf import generate_pdf_report
                pdf_data = generate_pdf_report(
                    results,
                    st.session_state.get("old_doc_name", "Document A"),
                    st.session_state.get("new_doc_name", "Document B")
                )
                st.download_button(
                    label="Export PDF Report",
                    data=pdf_data,
                    file_name="policy_compliance_report.pdf",
                    mime="application/pdf",
                    key="pdf_export_real",
                    use_container_width=True
                )
            except Exception as e:
                st.button("Export PDF Report", key="pdf_export_err", disabled=True, use_container_width=True)
                st.error(f"Failed to generate PDF: {e}")
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
            <div>⚡ Last Query: {chat_tokens['total_tokens']} tokens (In: {chat_tokens['prompt_tokens']} | Out: {chat_tokens['completion_tokens']})</div>
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
                    from config import TokenTrackerCallback
                    tracker = TokenTrackerCallback()
                    chain = st.session_state["rag_chain"]
                    raw = chain.invoke({"query": query_to_send}, config={"callbacks": [tracker]})
                    answer  = raw.get("result") or raw.get("output") or str(raw)
                    sources = raw.get("source_documents", [])
                    st.session_state["chat_tokens"] = {
                        "prompt_tokens": tracker.prompt_tokens,
                        "completion_tokens": tracker.completion_tokens,
                        "total_tokens": tracker.total_tokens,
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

```

---

