"""
Shared utilities for document processing across all modules.
"""
from utils.document_utils import chunk_text, build_documents, get_embeddings, retrieve_context

__all__ = [
    "chunk_text",
    "build_documents",
    "get_embeddings",
    "retrieve_context",
]
