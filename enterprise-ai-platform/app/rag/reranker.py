"""
app/rag/reranker.py
-------------------
Cross-encoder reranker.

Takes the hybrid-retrieved candidates and reorders them by semantic
relevance to the query using a sentence-transformers cross-encoder model.

The reranker is optional and degrades gracefully — if the cross-encoder
model is not available (e.g., first run before download, or low-memory
environment) the original RRF-ranked order is preserved.

Default model: cross-encoder/ms-marco-MiniLM-L-6-v2
  - Fast, ~67 MB download, good general-purpose reranking.
  - Swap for a larger model (ms-marco-MiniLM-L-12-v2) for better accuracy.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Tuple

from langchain_core.documents import Document

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

@lru_cache(maxsize=1)
def _get_cross_encoder():
    """Load and cache the cross-encoder model (lazy, once per process)."""
    try:
        from sentence_transformers import CrossEncoder  # lazy

        logger.info("Loading cross-encoder reranker", extra={"model": settings.RERANKER_MODEL})
        model = CrossEncoder(settings.RERANKER_MODEL)
        logger.info("Cross-encoder loaded")
        return model
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Cross-encoder not available — skipping reranking",
            extra={"error": str(exc)},
        )
        return None


class Reranker:
    """
    Reranks a list of candidate Documents using a cross-encoder.

    Args:
        top_n: Number of documents to return after reranking.
               Defaults to settings.RERANKER_TOP_N.
    """

    def __init__(self, top_n: int = 0) -> None:
        self.top_n = top_n or settings.RERANKER_TOP_N

    def rerank(
        self,
        query: str,
        candidates: List[Document],
    ) -> List[Document]:
        """
        Return the *top_n* most relevant documents from *candidates*.

        Falls back to returning candidates[:top_n] if the cross-encoder
        is not available.
        """
        if not candidates:
            return []

        if not settings.RERANKER_ENABLED:
            return candidates[: self.top_n]

        model = _get_cross_encoder()
        if model is None:
            logger.debug("Reranker unavailable — returning top-k from retriever order")
            return candidates[: self.top_n]

        pairs = [(query, doc.page_content) for doc in candidates]
        try:
            scores: List[float] = model.predict(pairs).tolist()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Reranker prediction failed — falling back",
                extra={"error": str(exc)},
            )
            return candidates[: self.top_n]

        ranked: List[Tuple[Document, float]] = sorted(
            zip(candidates, scores),
            key=lambda x: x[1],
            reverse=True,
        )

        # Attach rerank score to metadata for observability
        result: List[Document] = []
        for doc, score in ranked[: self.top_n]:
            doc.metadata["rerank_score"] = round(float(score), 4)
            result.append(doc)

        logger.debug(
            "Reranking complete",
            extra={"candidates_in": len(candidates), "top_n_out": len(result)},
        )
        return result

    def rerank_with_scores(
        self,
        query: str,
        candidates: List[Document],
    ) -> List[Tuple[Document, float]]:
        """Return (Document, score) pairs sorted by descending relevance."""
        reranked = self.rerank(query, candidates)
        return [
            (doc, doc.metadata.get("rerank_score", 0.0)) for doc in reranked
        ]
