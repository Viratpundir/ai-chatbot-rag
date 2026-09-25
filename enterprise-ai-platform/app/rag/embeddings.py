"""
app/rag/embeddings.py
---------------------
Embedding model wrapper.

Preserved from the original src/embeddings.py (all-MiniLM-L6-v2 via
HuggingFaceEmbeddings) and extended with:
  - Singleton caching so the model is loaded only once per process
  - Model name driven by settings (EMBEDDING_MODEL env var)
  - Lazy import to avoid slow startup when embeddings are not needed
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_embeddings():
    """
    Return the shared HuggingFaceEmbeddings instance.

    The model is downloaded on first call and cached in memory for the
    lifetime of the process.  Thread-safe because lru_cache uses a lock.
    """
    try:
        from langchain_huggingface import HuggingFaceEmbeddings  # preferred (langchain>=0.2.2)
    except ImportError:
        from langchain_community.embeddings import HuggingFaceEmbeddings  # fallback  # noqa: PLC0415

    logger.info(
        "Loading embedding model",
        extra={"model": settings.EMBEDDING_MODEL},
    )
    embeddings = HuggingFaceEmbeddings(
        model_name=settings.EMBEDDING_MODEL,
        # Keep the model on CPU; avoids dependency on CUDA drivers in most
        # enterprise deployments.  Switch to "cuda" via env override if GPU
        # is available.
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    logger.info("Embedding model loaded", extra={"model": settings.EMBEDDING_MODEL})
    return embeddings


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Convenience wrapper – embed a list of strings and return float vectors.

    Useful for caching individual embeddings in Redis (Stage 9).
    """
    return get_embeddings().embed_documents(texts)


def embed_query(text: str) -> List[float]:
    """Embed a single query string."""
    return get_embeddings().embed_query(text)
