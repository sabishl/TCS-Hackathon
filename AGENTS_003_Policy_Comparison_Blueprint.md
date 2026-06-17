# AGENTS_003 – Smart Policy Document Comparison Assistant

## Project Overview
Build an AI-powered application that compares two policy documents and identifies:
- Added sections
- Removed sections
- Modified sections
- Unchanged sections

The system should explain changes using an LLM and provide a chatbot for querying both documents.

## Core Architecture

User Uploads Two PDFs
→ PDF Parsing (PyMuPDF + pdfplumber)
→ Section Extraction
→ Embedding Generation (nomic-embed-text)
→ Cosine Similarity Comparison
→ Added / Removed / Unchanged / Changed Classification
→ Llama 3.1 8B Analysis (only for changed sections)
→ Streamlit Dashboard
→ RAG Chatbot

## Core Innovation

Instead of sending all sections to the LLM:

1. Generate embeddings for each section.
2. Compare sections using cosine similarity.
3. Send only changed sections to Llama.

Benefits:
- 80–90% token reduction
- Faster response
- Lower cost
- Better scalability

## Technology Stack

- Frontend: Streamlit
- PDF Parsing: PyMuPDF + pdfplumber
- Embeddings: nomic-embed-text
- Similarity: Cosine Similarity
- Vector DB: ChromaDB
- LLM: Llama 3.1 8B Instruct
- Deployment: AMD Cloud (vLLM + ROCm)

## Workflow

### Step 1: Upload PDFs
- Old Policy PDF
- New Policy PDF

### Step 2: Extract Content
- Text extraction using PyMuPDF
- Table extraction using pdfplumber

### Step 3: Build Sections
Each section contains:
- Heading
- Content
- Tables
- Page number

### Step 4: Generate Embeddings
Use nomic-embed-text to create vectors.

### Step 5: Similarity Comparison

Similarity >= 0.95 → Unchanged

Similarity < 0.95 → Changed

Missing in new document → Removed

Missing in old document → Added

### Step 6: LLM Analysis

Only changed sections are sent to Llama.

Outputs:
- Change summary
- Impact level
- Key differences

### Step 7: Dashboard

Display:
- Total Sections
- Added
- Removed
- Modified
- Unchanged

Display similarity scores for explainable AI.

### Step 8: RAG Chatbot

Example Questions:
- What changed in leave policy?
- Compare eligibility criteria.
- Show all high-impact changes.
- Which sections were removed?

## Hackathon Advantages

- Uses AI + RAG
- Uses Vector Database
- Uses Explainable AI
- Saves Tokens
- Fast Processing
- Easy Judge Demonstration

## Final Tagline

An AI-powered Policy Comparison Assistant that uses embeddings, cosine similarity, and Llama 3.1 to identify, explain, and query policy changes with minimal token consumption.
