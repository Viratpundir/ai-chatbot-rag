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

import hashlib
import threading
from collections import OrderedDict
from functools import lru_cache
from typing import List, Tuple

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


_QUERY_CACHE_SIZE = 128
_query_embedding_cache: OrderedDict[Tuple[str, bytes], Tuple[float, ...]] = OrderedDict()
_query_embedding_cache_lock = threading.Lock()


def _clear_query_embedding_cache() -> None:
    with _query_embedding_cache_lock:
        _query_embedding_cache.clear()


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Convenience wrapper – embed a list of strings and return float vectors.

    Useful for caching individual embeddings in Redis (Stage 9).
    """
    return get_embeddings().embed_documents(texts)


def embed_query(text: str) -> List[float]:
    """Embed a single query string."""
    key = (settings.EMBEDDING_MODEL, hashlib.sha256(text.encode("utf-8")).digest())
    with _query_embedding_cache_lock:
        cached = _query_embedding_cache.get(key)
        if cached is not None:
            _query_embedding_cache.move_to_end(key)
            return list(cached)

    embedding = tuple(get_embeddings().embed_query(text))
    with _query_embedding_cache_lock:
        _query_embedding_cache[key] = embedding
        _query_embedding_cache.move_to_end(key)
        if len(_query_embedding_cache) > _QUERY_CACHE_SIZE:
            _query_embedding_cache.popitem(last=False)
    return list(embedding)
