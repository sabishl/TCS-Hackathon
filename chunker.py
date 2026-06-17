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
