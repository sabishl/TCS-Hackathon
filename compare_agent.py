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

from langchain_groq import ChatGroq
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity as sk_cosine

from chunker import sections_to_full_text


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


def _build_llm(groq_api_key: str) -> ChatGroq:
    return ChatGroq(model=LLM_MODEL, temperature=0, api_key=groq_api_key)


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
    llm: ChatGroq,
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
    try:
        response = llm.invoke(prompt_text)
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

    for key in exact_keys:
        a = a_map[key]
        b = b_map[key]
        sim = _cosine_sim(_section_text(a, limit=6000), _section_text(b, limit=6000))
        before = len(results)
        result = _compare_matched_section(llm, a.get("heading", key), a, b, sim)
        results.append(result)
        if result["status"] == "unchanged":
            skipped += 1
        else:
            llm_calls += 1

    for a_key, b_key, sim in fuzzy_matches:
        a = a_map[a_key]
        b = b_map[b_key]
        heading = f"{a.get('heading', a_key)} -> {b.get('heading', b_key)}"
        result = _compare_matched_section(llm, heading, a, b, sim, heading_changed=True)
        results.append(result)
        llm_calls += 1

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
