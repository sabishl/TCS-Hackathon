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
