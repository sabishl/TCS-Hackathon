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
from langchain_groq import ChatGroq
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
    llm = ChatGroq(
        model="llama-3.1-8b-instant",   # LLaMA 3.1 8B Instruct (blueprint spec)
        temperature=0,
        api_key=groq_api_key,
    )

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
