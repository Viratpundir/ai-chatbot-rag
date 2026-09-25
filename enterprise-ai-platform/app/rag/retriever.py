"""Authorization-aware dense, BM25, and section-aware hybrid retrieval."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set, Tuple

from langchain_core.documents import Document

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.vector_store import VectorStoreManager, get_vector_store

logger = get_logger(__name__)
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*")
_STOPWORDS = {"a", "an", "and", "are", "is", "it", "of", "on", "or", "the", "to", "what"}


class HybridRetriever:
    """Retrieve a high-recall authorized candidate set for reranking."""

    def __init__(
        self,
        allowed_document_ids: Optional[Set[str]] = None,
        top_k: int = 0,
        initial_k: int = 0,
        vector_store: Optional[VectorStoreManager] = None,
    ) -> None:
        self.allowed_document_ids = allowed_document_ids
        self.final_k = top_k or settings.FINAL_RETRIEVAL_K
        self.initial_k = max(initial_k or settings.INITIAL_RETRIEVAL_K, self.final_k)
        self._vs = vector_store or get_vector_store()

    def query_variants(self, query: str) -> List[str]:
        """Add deterministic aliases only when the query contains known shorthand."""
        variants = [query.strip()]
        if not settings.QUERY_EXPANSION_ENABLED:
            return variants
        expansions = {
            "wfh": "work from home remote work",
            "remote work": "work from home WFH remote working",
            "exception": "exception exemption special case unless",
            "eligibility": "eligible qualification requirements who can",
            "notice period": "notice period advance notice deadline days",
        }
        lowered = query.lower()
        additions = [value for term, value in expansions.items() if term in lowered]
        if additions:
            variants.append(f"{query} {' '.join(additions)}")
        return variants

    def retrieve_candidates(self, query: str) -> List[Document]:
        """Return up to INITIAL_RETRIEVAL_K fused candidates."""
        scored = self.retrieve_with_scores(query, limit=self.initial_k)
        return [doc for doc, _ in scored]

    def retrieve(self, query: str) -> List[Document]:
        """Backward-compatible final-k retrieval interface."""
        return self.retrieve_candidates(query)[: self.final_k]

    def retrieve_with_scores(
        self,
        query: str,
        limit: Optional[int] = None,
    ) -> List[Tuple[Document, float]]:
        started = time.perf_counter()
        variants = self.query_variants(query)
        auth_ids = list(self.allowed_document_ids) if self.allowed_document_ids is not None else None

        dense: Dict[str, Tuple[Document, float]] = {}
        dense_started = time.perf_counter()
        for variant in variants:
            try:
                for doc, distance in self._vs.similarity_search_with_score(
                    variant, k=self.initial_k, filter_document_ids=auth_ids
                ):
                    key = _doc_key(doc)
                    similarity = 1.0 / (1.0 + max(float(distance), 0.0))
                    if key not in dense or similarity > dense[key][1]:
                        dense[key] = (doc, similarity)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[VECTOR SEARCH] failed", extra={"error": str(exc)})
        dense_ms = (time.perf_counter() - dense_started) * 1000

        corpus = self._vs.iter_documents(filter_document_ids=auth_ids)
        lexical_started = time.perf_counter()
        lexical = self._bm25_search(variants, corpus, self.initial_k)
        lexical_ms = (time.perf_counter() - lexical_started) * 1000

        candidates: Dict[str, Document] = {}
        for doc, _ in dense.values():
            candidates[_doc_key(doc)] = doc
        for doc, _ in lexical:
            candidates[_doc_key(doc)] = doc

        dense_scores = _normalize({key: score for key, (_, score) in dense.items()})
        lexical_scores = _normalize({_doc_key(doc): score for doc, score in lexical})
        scored: List[Tuple[Document, float]] = []
        for key, doc in candidates.items():
            vector_score = dense_scores.get(key, 0.0)
            bm25_score = lexical_scores.get(key, 0.0)
            section_boost = _section_match_boost(query, doc)
            hybrid_score = (
                settings.VECTOR_WEIGHT * vector_score
                + settings.BM25_WEIGHT * bm25_score
                + section_boost
            )
            doc.metadata["vector_score"] = round(vector_score, 6)
            doc.metadata["bm25_score"] = round(bm25_score, 6)
            doc.metadata["hybrid_score"] = round(hybrid_score, 6)
            scored.append((doc, hybrid_score))

        scored.sort(key=lambda item: item[1], reverse=True)
        result = scored[: limit or self.initial_k]
        logger.info(
            "[HYBRID FUSION] complete",
            extra={
                "dense_hits": len(dense),
                "bm25_hits": len(lexical),
                "candidates": len(result),
                "dense_ms": round(dense_ms, 1),
                "bm25_ms": round(lexical_ms, 1),
                "total_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return result

    def expand_context(self, documents: List[Document]) -> List[Document]:
        """Add bounded same-document neighbors for answers spanning chunks."""
        if not settings.CONTEXT_EXPANSION_ENABLED or not documents:
            return documents
        auth_ids = list(self.allowed_document_ids) if self.allowed_document_ids is not None else None
        corpus = self._vs.iter_documents(filter_document_ids=auth_ids)
        by_doc: Dict[str, List[Document]] = defaultdict(list)
        for doc in corpus:
            by_doc[str(doc.metadata.get("document_id", ""))].append(doc)
        for chunks in by_doc.values():
            chunks.sort(key=lambda doc: int(doc.metadata.get("chunk_index", 0)))

        selected = {_doc_key(doc) for doc in documents}
        expanded = list(documents)
        neighbor_count = max(settings.CONTEXT_EXPANSION_NEIGHBORS, 0)
        for doc in documents:
            chunks = by_doc.get(str(doc.metadata.get("document_id", "")), [])
            try:
                index = next(i for i, item in enumerate(chunks) if _doc_key(item) == _doc_key(doc))
            except StopIteration:
                continue
            for neighbor in chunks[max(0, index - neighbor_count): index + neighbor_count + 1]:
                key = _doc_key(neighbor)
                if key not in selected and _same_context(doc, neighbor):
                    selected.add(key)
                    neighbor.metadata.setdefault("context_neighbor", True)
                    expanded.append(neighbor)
        return expanded

    @staticmethod
    def _bm25_search(
        queries: Iterable[str],
        corpus: List[Document],
        top_k: int,
    ) -> List[Tuple[Document, float]]:
        if not corpus:
            return []
        tokenized = [_tokenize(doc.page_content) for doc in corpus]
        if not any(tokenized):
            return []
        try:
            from rank_bm25 import BM25Okapi

            bm25 = BM25Okapi(tokenized, k1=settings.BM25_K1, b=settings.BM25_B)
            query_tokens = [_tokenize(query) for query in queries]
            scores = [bm25.get_scores(tokens) for tokens in query_tokens]
            merged = [
                max(values) + max(
                    len(set(tokens) & set(document_tokens)) / max(len(tokens), 1)
                    for tokens in query_tokens
                )
                for document_tokens, values in zip(tokenized, zip(*scores))
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("[BM25 SEARCH] unavailable; using lexical fallback", extra={"error": str(exc)})
            merged = [sum(token in tokens for query in queries for token in _tokenize(query)) for tokens in tokenized]
        ranked = sorted(enumerate(merged), key=lambda item: item[1], reverse=True)
        return [(corpus[index], float(score)) for index, score in ranked[:top_k] if score > 0]


def _tokenize(text: str) -> List[str]:
    return [
        token.lower()
        for token in _TOKEN_RE.findall(text)
        if token.lower() not in _STOPWORDS
    ]


def _normalize(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    maximum = max(scores.values())
    minimum = min(scores.values())
    if maximum == minimum:
        return {key: 1.0 for key in scores}
    return {key: (value - minimum) / (maximum - minimum) for key, value in scores.items()}


def _section_match_boost(query: str, doc: Document) -> float:
    query_terms = set(_tokenize(query))
    section_terms = set(_tokenize(" ".join(
        [str(doc.metadata.get("section", "")), str(doc.metadata.get("subsection", ""))]
    )))
    if not query_terms or not section_terms:
        return 0.0
    overlap = len(query_terms & section_terms) / len(query_terms)
    return min(overlap * 0.2, 0.2)


def _same_context(first: Document, second: Document) -> bool:
    return (
        first.metadata.get("document_id") == second.metadata.get("document_id")
        and first.metadata.get("section", "") == second.metadata.get("section", "")
    )


def _doc_key(doc: Document) -> str:
    document_id = doc.metadata.get("document_id", "")
    chunk_id = doc.metadata.get("chunk_id") or doc.metadata.get("chunk_index", "")
    return f"{document_id}:{chunk_id}" if document_id or chunk_id != "" else str(hash(doc.page_content))


def get_retriever(
    allowed_document_ids: Optional[Set[str]] = None,
    top_k: Optional[int] = None,
) -> HybridRetriever:
    return HybridRetriever(allowed_document_ids=allowed_document_ids, top_k=top_k or settings.FINAL_RETRIEVAL_K)
