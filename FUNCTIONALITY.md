# PolicyLens - Full Functionality

PolicyLens is a Streamlit-based AI policy comparison application. It compares two policy PDF documents, identifies what changed, stores document sections in a local vector database, and provides a source-aware chatbot for asking questions about both policy versions.

## 1. Main Workflow

1. Upload the old policy PDF as Document A.
2. Upload the new policy PDF as Document B.
3. Click `Compare Documents`.
4. The app extracts text and tables from both PDFs.
5. Content is grouped into policy sections.
6. Sections are embedded and stored in ChromaDB.
7. Old and new sections are compared.
8. Results are displayed in a dashboard.
9. User can filter, export, reset, or ask questions using the AI Assistant.

## 2. PDF Upload

- Supports uploading two PDF files:
  - Old Policy - Document A
  - New Policy - Document B
- Shows uploaded file name and file size.
- Analysis is enabled only when both PDFs are available and the Groq API key is configured.
- Includes a `Clear PDFs & Vectors` action to remove uploaded document state and clear ChromaDB vectors.

## 3. Sample Demo Data

- Includes a sample/demo data loader inside the app.
- Demo data simulates policy comparison results without requiring real PDFs.
- Sample comparison includes:
  - Modified eligibility rules
  - Changed coverage limits and copays
  - Removed exclusion clause
  - Added telehealth service section
  - Unchanged definitions section
- Sample data is also stored in the vector database so the chatbot can work during demo mode.

## 4. PDF Parsing

Implemented in `parser.py`.

Features:
- Uses PyMuPDF to extract structured text.
- Detects headings based on font size.
- Uses pdfplumber to extract tables.
- Converts extracted tables into Markdown format.
- Removes common header/footer noise such as:
  - Page numbers
  - Version labels
  - Confidential/internal labels
  - Document IDs
  - Dates
  - Copyright/proprietary lines
- Keeps tables in page order so tables are attached to the correct section.

## 5. Section Building

Implemented in `chunker.py`.

Features:
- Groups raw PDF chunks into section-level objects.
- Each section contains:
  - Heading
  - Text content
  - Tables
  - Source document tag
  - Page number
- Creates an `Introduction` section only when meaningful content exists.
- Avoids tiny header/footer leftovers becoming fake sections.
- Combines section text and tables into full text for embedding and comparison.

## 6. Vector Database

Implemented in `vectorstore.py`.

Features:
- Uses ChromaDB as the local vector database.
- Uses local HuggingFace embeddings with `all-MiniLM-L6-v2`.
- Stores each section as a vector document.
- Stores metadata for each vector:
  - Source: `doc_a` or `doc_b`
  - Section heading
  - Page number
  - Table availability
- Adds explicit source text into each stored document:
  - `SOURCE`
  - `SECTION`
  - `PAGE`
- This helps the chatbot cite Doc A and Doc B correctly.

## 7. Vector Reset / Cleanup

Features:
- Clears old vectors before a new comparison.
- Clears vectors when `Clear PDFs & Vectors` is selected.
- Uses ChromaDB collection APIs instead of deleting locked files directly.
- Handles Windows file-lock issues from ChromaDB `.bin` index files.
- Deletes existing document IDs before recreating the collection.
- Prevents old document vectors from leaking into new comparisons.

## 8. Section Comparison

Implemented in `compare_agent.py`.

The comparison system identifies:
- Added sections
- Removed sections
- Modified sections
- Unchanged sections

Comparison logic:
- Normalizes headings for matching.
- Merges duplicate headings so content is not overwritten.
- Compares full section text, including tables.
- Uses cosine similarity with local embeddings.
- Uses LLaMA 3.1 through Groq for deep analysis of changed sections.
- Uses stricter unchanged detection to avoid missing small but important changes.

## 9. Accuracy Enhancements

The project includes multiple accuracy protections:

- Tables are included in comparison text.
- Numeric, currency, percentage, date, and duration changes are treated as sensitive.
- Very small changes such as `$500 -> $750` are not skipped just because semantic similarity is high.
- Renamed sections are fuzzy-matched by content similarity.
- Renamed but similar sections are treated as modified instead of incorrectly showing as removed plus added.
- LLM output is normalized into a consistent result shape.
- Accidental Markdown fenced JSON from the LLM is cleaned before parsing.

## 10. LLM Comparison Output

For changed sections, the LLM returns structured JSON with:

- `status`
- `change_summary`
- `old_key_points`
- `new_key_points`
- `changed_points`
- `same_points`
- `impact`
- `table_changed`

The app uses this structure to show clear old vs new changes instead of only giving a summary.

## 11. Analysis Dashboard

The dashboard shows:

- Total sections
- Added section count
- Removed section count
- Updated/modified section count
- Unchanged section count

Each comparison result appears in an expandable card.

Each card can show:
- Status badge
- Impact badge
- Similarity score
- Change summary
- Key transitions
- Original policy points
- Updated policy points
- Added content
- Removed content
- Unchanged content

## 12. Filters

Users can filter comparison results by:

- Status:
  - Added
  - Removed
  - Modified
  - Unchanged
- Impact:
  - High
  - Medium
  - Low

The UI shows how many sections match the active filters.

## 13. Report Export

Implemented:
- CSV export of the full structured comparison report.

The CSV includes the comparison result fields available in the app, such as:
- Section
- Status
- Impact
- Summary
- Old key points
- New key points
- Changed points
- Same points
- Similarity score
- Table changed flag

Placeholder UI actions:
- `Export PDF Report`
- `Share Report`

These currently show UI feedback but do not generate a real PDF file or real share link.

## 14. AI Assistant / Chatbot

Implemented in `rag_chain.py` and displayed in `app.py`.

Features:
- Dedicated `AI Assistant` mode.
- Uses RetrievalQA over the ChromaDB vector store.
- Uses Groq LLaMA 3.1 for answers.
- Retrieves top matching document sections.
- Answers only from retrieved policy context.
- Instructed to cite whether information comes from:
  - Old policy / Doc A
  - New policy / Doc B
- Compares both sources when the same topic exists in both documents.
- Refuses unsupported answers by saying it could not find the answer in the provided policies.

## 15. Chatbot Suggestions

The assistant page includes quick suggestion buttons:

- What sections were removed?
- Show high impact changes.
- What changed in eligibility?
- Summarize all updates.

Users can also type custom questions.

## 16. Source References

After chatbot responses, the app can display source references for the last response:

- Source document
- Section name
- Page number
- Retrieved text preview

This improves explainability and helps users verify answers.

## 17. UI / User Experience

The app uses a single-page Streamlit interface with:

- White/light background
- Blue primary buttons
- Clean dashboard cards
- Upload cards
- Metric cards
- Status badges
- Impact badges
- Expandable comparison sections
- Separate comparison and AI Assistant modes
- Clear reset action for PDFs and vectors

## 18. Security / Local Handling

- API key is loaded from `.env`.
- Uploaded PDFs are written to temporary files only for parsing.
- Parsed sections and vectors are stored locally in ChromaDB.
- Local vector cleanup is available through reset actions.
- `.gitignore` excludes `.env`, `venv`, `chroma_db`, caches, and logs.

## 19. Main Project Files

- `app.py` - Streamlit UI, upload flow, processing pipeline, dashboard, export, and chatbot UI.
- `parser.py` - PDF text and table extraction.
- `chunker.py` - Section grouping and full section text generation.
- `compare_agent.py` - Similarity comparison, fuzzy matching, sensitive-change detection, and LLM diffing.
- `vectorstore.py` - ChromaDB storage, embedding, and reset logic.
- `rag_chain.py` - Source-aware RetrievalQA chatbot.
- `requirements.txt` - Python dependencies.
- `.gitignore` - Generated/local file exclusions.

## 20. End-to-End Capability Summary

PolicyLens can:

- Accept two policy PDFs.
- Extract text and tables.
- Build meaningful policy sections.
- Store sections as local vectors.
- Clear old vectors safely.
- Compare old and new policy versions.
- Detect added, removed, modified, and unchanged sections.
- Detect important numeric/table changes.
- Handle renamed sections more accurately.
- Explain changes using LLaMA 3.1.
- Display comparison results in a structured dashboard.
- Export comparison results as CSV.
- Answer policy questions using a source-aware RAG chatbot.
- Show source references for chatbot answers.
