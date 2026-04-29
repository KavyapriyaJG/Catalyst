"""
Shared document processing utilities for chunking, embedding, and context retrieval.
Reusable across backlog generation, PRD generation, and other flows.
"""
import os
from typing import Any, List, Dict
from langchain_core.documents import Document

def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> List[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    chunks: List[str] = []
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        chunks.append(cleaned[start:end])
        start += step
    return chunks

def build_documents(supporting_documents: List[Dict[str, str]]) -> List[Document]:
    documents: List[Document] = []
    for source_index, item in enumerate(supporting_documents, start=1):
        filename = item.get("filename", f"document-{source_index}.txt")
        content = item.get("content", "")
        for chunk_index, chunk in enumerate(chunk_text(content), start=1):
            documents.append(
                Document(
                    page_content=chunk,
                    metadata={"source": filename, "chunk": chunk_index},
                )
            )
    return documents

# def get_embeddings() -> Any:
#     try:
#         from langchain_huggingface import HuggingFaceEmbeddings
#     except ImportError as error:
#         raise RuntimeError(
#             "Missing dependency 'langchain-huggingface'. Install with: "
#             "pip install langchain-huggingface sentence-transformers"
#         ) from error
#     model_name = os.getenv(
#         "HUGGINGFACE_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
#     ).strip()
#     if not model_name:
#         model_name = "sentence-transformers/all-MiniLM-L6-v2"
#     return HuggingFaceEmbeddings(model_name=model_name)

def get_embeddings() -> Any:
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise RuntimeError(
            "Missing dependency 'langchain-huggingface'. Install with: "
            "pip install langchain-huggingface sentence-transformers"
        ) from error

    model_name = os.getenv(
        "HUGGINGFACE_EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2"
    ).strip() or "sentence-transformers/all-MiniLM-L6-v2"

    # Define local directory inside your project
    local_model_path = os.path.join(os.getcwd(), "models", "embeddings")

    # Create directory if it doesn't exist
    os.makedirs(local_model_path, exist_ok=True)

    # Download and save model locally (only first time)
    if not os.listdir(local_model_path):
        model = SentenceTransformer(model_name)
        model.save(local_model_path)

    # Load embeddings from local path
    return HuggingFaceEmbeddings(model_name=local_model_path)


def retrieve_context(query: str, documents: List[Document], top_k: int = 6) -> str:
    if not documents:
        return ""
    try:
        from langchain_core.vectorstores import InMemoryVectorStore
    except ImportError as error:
        raise RuntimeError(
            "Missing dependency 'langchain-core'. Install with: "
            "pip install langchain-core"
        ) from error
    embeddings = get_embeddings()
    vectorstore = InMemoryVectorStore.from_documents(documents, embeddings)
    results = vectorstore.similarity_search(query, k=top_k)
    return "\n".join([doc.page_content for doc in results])
