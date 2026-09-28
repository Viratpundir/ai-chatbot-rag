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
        self._corpus_snapshot: Optional[List[Document]] = None
        self.last_timings: Dict[str, float] = {}

    def _authorized_corpus(self) -> List[Document]:
        if self._corpus_snapshot is None:
            auth_ids = list(self.allowed_document_ids) if self.allowed_document_ids is not None else None
            started = time.perf_counter()
            self._corpus_snapshot = self._vs.iter_documents(filter_document_ids=auth_ids)
            self.last_timings["authorized_corpus_snapshot_ms"] = (
                time.perf_counter() - started
            ) * 1000
        return self._corpus_snapshot

    def query_variants(self, query: str) -> List[str]:
        """Add deterministic terminology and named-section aliases for recall."""
        variants = [query.strip()]
        if not settings.QUERY_EXPANSION_ENABLED:
            return variants
        lowered = query.lower()
        additions: List[str] = []
        expansions = {
            "wfh": "work from home remote work",
            "remote work": "work from home WFH remote working",
            "exception": "exception exemption special case unless",
            "eligibility": "eligible qualification requirements who can",
            "notice period": "notice period advance notice deadline days",
            "explainability": "interpretability explainable AI decision rationale",
            "fairness": "equity bias discrimination algorithmic fairness",
            "robustness": "reliability resilience stability AI systems",
            "transparency": "openness disclosure AI system transparency",
            "privacy": "personal information data protection confidentiality",
        }
        additions.extend(value for term, value in expansions.items() if term in lowered)

        mentions_ai = bool(re.search(r"\b(ai|artificial intelligence)\b", lowered))
        mentions_ethics = "ethic" in lowered
        mentions_pillars = any(term in lowered for term in ("pillar", "principle"))
        if mentions_ai and mentions_ethics:
            additions.extend((
                "AI ethics principles ethical AI pillars",
                "principles for ethical artificial intelligence",
            ))
            if mentions_pillars:
                additions.append("THE FIVE PILLARS OF AI ETHICS")

        if additions:
            variants.extend(additions)
        return list(dict.fromkeys(variant for variant in variants if variant))

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
        self.last_timings = {}

        dense: Dict[str, Tuple[Document, float]] = {}
        dense_started = time.perf_counter()
        for variant in variants:
            try:
                search_timings: Dict[str, float] = {}
                for doc, distance in self._vs.similarity_search_with_score(
                    variant,
                    k=self.initial_k,
                    filter_document_ids=auth_ids,
                    timings=search_timings,
                ):
                    key = _doc_key(doc)
                    similarity = 1.0 / (1.0 + max(float(distance), 0.0))
                    if key not in dense or similarity > dense[key][1]:
                        dense[key] = (doc, similarity)
                for name, value in search_timings.items():
                    self.last_timings[name] = self.last_timings.get(name, 0.0) + value
            except Exception as exc:  # noqa: BLE001
                logger.warning("[VECTOR SEARCH] failed", extra={"error": str(exc)})
        dense_ms = (time.perf_counter() - dense_started) * 1000

        corpus = self._authorized_corpus()
        lexical_started = time.perf_counter()
        lexical = self._bm25_search(variants, corpus, self.initial_k)
        lexical_ms = (time.perf_counter() - lexical_started) * 1000
        self.last_timings["dense_search_ms"] = dense_ms
        self.last_timings["lexical_search_ms"] = lexical_ms
        self.last_timings["authorized_corpus_chunks"] = float(len(corpus))
        exact_sections = [doc for doc in corpus if _exact_section_match(variants, doc)]

        candidates: Dict[str, Document] = {}
        for doc, _ in dense.values():
            candidates[_doc_key(doc)] = doc
        for doc, _ in lexical:
            candidates[_doc_key(doc)] = doc
        for doc in exact_sections:
            candidates[_doc_key(doc)] = doc

        dense_scores = _normalize({key: score for key, (_, score) in dense.items()})
        lexical_scores = _normalize({_doc_key(doc): score for doc, score in lexical})
        scored: List[Tuple[Document, float]] = []
        for key, doc in candidates.items():
            vector_score = dense_scores.get(key, 0.0)
            bm25_score = lexical_scores.get(key, 0.0)
            section_boost = _section_match_boost(variants, doc)
            hybrid_score = (
                settings.VECTOR_WEIGHT * vector_score
                + settings.BM25_WEIGHT * bm25_score
                + section_boost
            )
            doc.metadata["vector_score"] = round(vector_score, 6)
            doc.metadata["bm25_score"] = round(bm25_score, 6)
            doc.metadata["hybrid_score"] = round(hybrid_score, 6)
            if hybrid_score >= settings.RETRIEVAL_MIN_HYBRID_SCORE:
                scored.append((doc, hybrid_score))

        scored.sort(key=lambda item: item[1], reverse=True)
        result = scored[: limit or self.initial_k]
        self.last_timings["candidate_count"] = float(len(result))
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

    def expand_context(
        self,
        documents: List[Document],
        query: Optional[str] = None,
    ) -> List[Document]:
        """Add bounded same-document neighbors for answers spanning chunks."""
        if not settings.CONTEXT_EXPANSION_ENABLED or not documents:
            return documents
        auth_ids = list(self.allowed_document_ids) if self.allowed_document_ids is not None else None
        corpus = self._authorized_corpus()
        max_context_chunks = max(settings.CONTEXT_EXPANSION_MAX_CHUNKS, self.final_k)
        if query:
            variants = self.query_variants(query)
            exact_match = next(
                (doc for doc in documents if _exact_section_match(variants, doc)),
                None,
            )
            if exact_match:
                section = str(exact_match.metadata.get("section", "")).strip()
                document_id = str(exact_match.metadata.get("document_id", ""))
                section_chunks = [
                    doc for doc in corpus
                    if str(doc.metadata.get("document_id", "")) == document_id
                    and str(doc.metadata.get("section", "")).strip() == section
                ]
                section_chunks.sort(key=lambda doc: int(doc.metadata.get("chunk_index", 0)))
                return section_chunks[:max_context_chunks]

        by_doc: Dict[str, List[Document]] = defaultdict(list)
        for doc in corpus:
            by_doc[str(doc.metadata.get("document_id", ""))].append(doc)
        for chunks in by_doc.values():
            chunks.sort(key=lambda doc: int(doc.metadata.get("chunk_index", 0)))

        selected: Set[str] = set()
        expanded: List[Document] = []
        for doc in documents:
            key = _doc_key(doc)
            if key not in selected and len(expanded) < max_context_chunks:
                selected.add(key)
                expanded.append(doc)
        neighbor_count = max(settings.CONTEXT_EXPANSION_NEIGHBORS, 0)
        max_section_chunks = max(settings.CONTEXT_EXPANSION_MAX_CHUNKS, 1)
        for doc in expanded.copy():
            if len(expanded) >= max_context_chunks:
                break
            chunks = by_doc.get(str(doc.metadata.get("document_id", "")), [])
            section = str(doc.metadata.get("section", "")).strip()
            if section:
                section_chunks = [
                    item for item in chunks
                    if str(item.metadata.get("section", "")).strip() == section
                ]
                selected_in_section = sum(
                    _doc_key(item) in selected for item in section_chunks
                )
                remaining = min(max_section_chunks - selected_in_section, max_context_chunks - len(expanded))
                for chunk in section_chunks:
                    key = _doc_key(chunk)
                    if remaining <= 0:
                        break
                    if key not in selected:
                        selected.add(key)
                        chunk.metadata.setdefault("context_neighbor", True)
                        expanded.append(chunk)
                        remaining -= 1
                        if len(expanded) >= max_context_chunks:
                            break
                continue
            try:
                index = next(i for i, item in enumerate(chunks) if _doc_key(item) == _doc_key(doc))
            except StopIteration:
                continue
            for neighbor in chunks[max(0, index - neighbor_count): index + neighbor_count + 1]:
                if len(expanded) >= max_context_chunks:
                    break
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


def _section_match_boost(queries: Iterable[str], doc: Document) -> float:
    section_terms = _section_terms(doc)
    if not section_terms:
        return 0.0
    best_overlap = 0.0
    for query in queries:
        query_terms = set(_tokenize(query))
        if not query_terms:
            continue
        if section_terms.issubset(query_terms):
            return 0.35
        best_overlap = max(best_overlap, len(query_terms & section_terms) / len(query_terms))
    return min(best_overlap * 0.2, 0.2)


def _exact_section_match(queries: Iterable[str], doc: Document) -> bool:
    section_terms = _section_terms(doc)
    return bool(section_terms) and any(
        section_terms.issubset(set(_tokenize(query))) for query in queries
    )


def _section_terms(doc: Document) -> Set[str]:
    return set(_tokenize(" ".join(
        [str(doc.metadata.get("section", "")), str(doc.metadata.get("subsection", ""))]
    )))


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
