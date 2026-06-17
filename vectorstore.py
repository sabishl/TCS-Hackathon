"""
vectorstore.py
--------------
ChromaDB vector store management with local HuggingFace embeddings.

Every new comparison clears the previous Chroma collection so old PDF vectors
do not bleed into new results.
"""

import gc
import os

from langchain_community.vectorstores import Chroma

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings


PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION = "policy_compare"
EMBED_MODEL = "all-MiniLM-L6-v2"


def _get_embeddings() -> HuggingFaceEmbeddings:
    """Return a local HuggingFace embedding model instance."""
    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


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
