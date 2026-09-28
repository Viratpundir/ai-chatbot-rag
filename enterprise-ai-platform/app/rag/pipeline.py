"""
app/rag/pipeline.py
-------------------
Authorised RAG pipeline — the main entry point for all chat queries.

Flow
----
User query
  → HybridRetriever  (semantic + keyword, filtered by allowed_document_ids)
  → Reranker         (cross-encoder, optional)
  → build_rag_prompt (anti-hallucination prompt with citations)
  → LLM              (Ollama / OpenAI)
  → RAGResponse      (answer + structured citations + latency metadata)

Authorization contract
----------------------
The pipeline receives `allowed_document_ids` from the caller (API layer).
The API layer derives this set from the authenticated user's role +
document permissions (implemented in Stage 6-7).

The pipeline NEVER retrieves documents outside this set — the filter is
applied inside HybridRetriever before any content is sent to the LLM.

Backward compatibility
----------------------
The module preserves the original RAGChain.invoke() / .run() interface
so that Stage 1 wiring continues to work while later stages extend it.
"""

from __future__ import annotations

import time
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Set, Tuple

import httpx

from langchain_core.documents import Document

from app.core.config import settings
from app.core.logging import get_logger, RAGTrace
from app.rag.prompts import (
    NO_ANSWER_RESPONSE,
    build_citations,
    build_rag_prompt,
    is_no_answer,
)
from app.rag.reranker import Reranker
from app.rag.retriever import HybridRetriever, get_retriever

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class RAGResponse:
    """Structured response from the RAG pipeline."""
    answer: str
    citations: List[Dict] = field(default_factory=list)
    context_docs: List[Document] = field(default_factory=list)
    retrieval_time_ms: float = 0.0
    reranking_time_ms: float = 0.0
    embedding_time_ms: float = 0.0
    vector_search_time_ms: float = 0.0
    permission_filter_time_ms: float = 0.0
    lexical_search_time_ms: float = 0.0
    context_time_ms: float = 0.0
    prompt_time_ms: float = 0.0
    llm_time_ms: float = 0.0
    llm_first_token_ms: Optional[float] = None
    prompt_chars: int = 0
    approximate_prompt_tokens: int = 0
    total_time_ms: float = 0.0
    model: str = ""
    has_answer: bool = True
    query: str = ""
    retrieval_debug: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "answer": self.answer,
            "citations": self.citations,
            "retrieval_time_ms": self.retrieval_time_ms,
            "reranking_time_ms": self.reranking_time_ms,
            "embedding_time_ms": self.embedding_time_ms,
            "vector_search_time_ms": self.vector_search_time_ms,
            "permission_filter_time_ms": self.permission_filter_time_ms,
            "lexical_search_time_ms": self.lexical_search_time_ms,
            "context_time_ms": self.context_time_ms,
            "prompt_time_ms": self.prompt_time_ms,
            "llm_time_ms": self.llm_time_ms,
            "llm_first_token_ms": self.llm_first_token_ms,
            "prompt_chars": self.prompt_chars,
            "approximate_prompt_tokens": self.approximate_prompt_tokens,
            "total_time_ms": self.total_time_ms,
            "model": self.model,
            "has_answer": self.has_answer,
            "retrieval_debug": self.retrieval_debug,
        }


class RAGProviderError(RuntimeError):
    """Safe, user-facing classification for an LLM provider failure."""


class RAGProviderTimeout(RAGProviderError):
    """The configured LLM did not respond before its timeout."""


class RAGProviderUnavailable(RAGProviderError):
    """The configured LLM could not be reached or used."""


@dataclass
class _PreparedQuery:
    started_at: float
    candidate_results: List[Tuple[Document, float]]
    context_docs: List[Document]
    prompt: str
    timings: Dict[str, float]
    candidate_debug: List[Dict]
    reranked_debug: List[Dict]


# ---------------------------------------------------------------------------
# LLM loader
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_llm():
    """
    Return the configured LLM.

    Prefers Ollama (local, private).  Falls back to OpenAI if
    OPENAI_API_KEY is set and Ollama is unavailable.
    """
    # Try the modern langchain-ollama package first; fall back to the
    # legacy langchain_community.llms.Ollama if not installed.
    def _make_ollama():
        try:
            from langchain_ollama import OllamaLLM  # langchain>=0.3.1
            return OllamaLLM(
                base_url=settings.OLLAMA_HOST,
                model=settings.OLLAMA_MODEL,
                temperature=settings.LLM_TEMPERATURE,
            )
        except ImportError:
            from langchain_community.llms import Ollama  # legacy fallback
            return Ollama(
                base_url=settings.OLLAMA_HOST,
                model=settings.OLLAMA_MODEL,
                temperature=settings.LLM_TEMPERATURE,
            )

    try:
        return _make_ollama()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Ollama unavailable — checking OpenAI fallback",
            extra={"error": str(exc)},
        )

    if settings.OPENAI_API_KEY:
        from langchain_openai import ChatOpenAI  # lazy
        return ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model="gpt-3.5-turbo",
            temperature=settings.LLM_TEMPERATURE,
        )

    raise RuntimeError(
        "No LLM available. Start Ollama or set OPENAI_API_KEY."
    )


# ---------------------------------------------------------------------------
# Enterprise RAG Pipeline
# ---------------------------------------------------------------------------

class EnterpriseRAGPipeline:
    """
    Full authorised RAG pipeline.

    Intended to be instantiated per-request (lightweight — no model loading
    happens here; models are singletons cached in their respective modules).

    Args:
        allowed_document_ids: Set of document UUIDs the requesting user
                              may access.  None = unrestricted (admin / dev).
        user_id:              For tracing / audit logging.
        conversation_history: Optional serialised prior turns.
    """

    def __init__(
        self,
        allowed_document_ids: Optional[Set[str]] = None,
        user_id: str = "anonymous",
        conversation_history: Optional[str] = None,
        response_style: str = "answer",
    ) -> None:
        self.allowed_document_ids = allowed_document_ids
        self.user_id = user_id
        self.conversation_history = conversation_history
        self.response_style = response_style
        self._retriever = get_retriever(allowed_document_ids)
        self._reranker = Reranker(top_n=settings.FINAL_RETRIEVAL_K)
        self._llm = None  # lazy

    def _ensure_llm(self):
        if self._llm is None:
            self._llm = _get_llm()
        return self._llm

    def _build_response(
        self,
        question: str,
        prepared: _PreparedQuery,
        answer: str,
        llm_ms: float,
        first_token_ms: Optional[float] = None,
    ) -> RAGResponse:
        context_docs = prepared.context_docs
        citations = build_citations(context_docs)
        retrieval_debug = []
        if settings.DEBUG_RETRIEVAL:
            variants = self._retriever.query_variants(question)
            retrieval_debug = [
                {
                    "stage": "query",
                    "original_query": question,
                    "expanded_queries": variants[1:],
                },
                *prepared.candidate_debug,
                *prepared.reranked_debug,
                *[_debug_document(doc, "final_context") for doc in context_docs],
                {
                    "stage": "confidence",
                    "candidate_count": len(prepared.candidate_results),
                    "reranked_count": len(prepared.reranked_debug),
                    "final_context_count": len(context_docs),
                    "top_hybrid_score": max(
                        (score for _, score in prepared.candidate_results), default=0.0
                    ),
                    "top_rerank_score": max(
                        (doc.metadata.get("rerank_score", 0.0) for doc in context_docs),
                        default=None,
                    ),
                    "matched_sections": sorted({
                        str(doc.metadata.get("section"))
                        for doc in context_docs if doc.metadata.get("section")
                    }),
                    "generation_has_answer": not is_no_answer(answer),
                },
            ]
            logger.debug("RAG retrieval trace", extra={"retrieval_debug": retrieval_debug})

        has_answer = not is_no_answer(answer) and bool(context_docs)
        model_name = getattr(self._llm, "model", settings.OLLAMA_MODEL)
        total_ms = (time.perf_counter() - prepared.started_at) * 1000
        timings = prepared.timings
        logger.info(
            "RAG REQUEST completed",
            extra={
                "user_id": self.user_id,
                "embedding_ms": round(timings.get("embedding_ms", 0.0), 1),
                "vector_search_ms": round(timings.get("vector_search_ms", 0.0), 1),
                "permission_filter_ms": round(timings.get("permission_filter_ms", 0.0), 1),
                "authorized_corpus_snapshot_ms": round(timings.get("authorized_corpus_snapshot_ms", 0.0), 1),
                "lexical_search_ms": round(timings.get("lexical_search_ms", 0.0), 1),
                "dense_search_ms": round(timings.get("dense_search_ms", 0.0), 1),
                "authorized_corpus_chunks": int(timings.get("authorized_corpus_chunks", 0.0)),
                "retrieval_candidate_count": int(timings.get("candidate_count", 0.0)),
                "retrieval_ms": round(timings["retrieval_ms"], 1),
                "reranking_ms": round(timings["reranking_ms"], 1),
                "context_ms": round(timings["context_ms"], 1),
                "prompt_ms": round(timings["prompt_ms"], 1),
                "prompt_chars": int(timings["prompt_chars"]),
                "approximate_prompt_tokens": int(timings["approximate_prompt_tokens"]),
                "llm_first_token_ms": round(first_token_ms, 1) if first_token_ms is not None else None,
                "llm_ms": round(llm_ms, 1),
                "total_ms": round(total_ms, 1),
                "context_chunks": len(context_docs),
                "candidate_chunks": len(prepared.candidate_results),
                "citation_count": len(citations),
                "has_answer": has_answer,
                "model": model_name,
            },
        )
        return RAGResponse(
            answer=answer,
            citations=citations,
            context_docs=context_docs,
            retrieval_time_ms=round(timings["retrieval_ms"], 1),
            reranking_time_ms=round(timings["reranking_ms"], 1),
            embedding_time_ms=round(timings.get("embedding_ms", 0.0), 1),
            vector_search_time_ms=round(timings.get("vector_search_ms", 0.0), 1),
            permission_filter_time_ms=round(timings.get("permission_filter_ms", 0.0), 1),
            lexical_search_time_ms=round(timings.get("lexical_search_ms", 0.0), 1),
            context_time_ms=round(timings["context_ms"], 1),
            prompt_time_ms=round(timings["prompt_ms"], 1),
            llm_time_ms=round(llm_ms, 1),
            llm_first_token_ms=round(first_token_ms, 1) if first_token_ms is not None else None,
            prompt_chars=int(timings["prompt_chars"]),
            approximate_prompt_tokens=int(timings["approximate_prompt_tokens"]),
            total_time_ms=round(total_ms, 1),
            model=model_name,
            has_answer=has_answer,
            query=question,
            retrieval_debug=retrieval_debug,
        )

    def _provider_error(self, exc: Exception) -> RAGProviderError:
        message = str(exc)
        if settings.OPENAI_API_KEY:
            message = message.replace(settings.OPENAI_API_KEY, "[redacted]")
        message = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [redacted]", message)
        message = re.sub(
            r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)(\s*[:=]\s*)[^\s,;]+",
            r"\1\2[redacted]",
            message,
        )
        logger.error(
            "LLM provider request failed",
            extra={"exception_type": type(exc).__name__, "exception_message": message[:500]},
        )
        if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
            return RAGProviderTimeout("The AI service took too long to respond.")
        return RAGProviderUnavailable("The AI service is temporarily unavailable.")

    def query(self, question: str, response_style: Optional[str] = None) -> RAGResponse:
        """Run retrieval and non-streaming generation using the shared preparation path."""
        prepared = self._prepare_query(question, response_style, time.perf_counter())
        if not prepared.context_docs:
            return self._build_response(question, prepared, NO_ANSWER_RESPONSE, 0.0)

        llm_started = time.perf_counter()
        try:
            llm = self._ensure_llm()
            raw = llm.invoke(prepared.prompt)
            answer = raw.content if hasattr(raw, "content") else str(raw)
        except Exception as exc:  # noqa: BLE001
            raise self._provider_error(exc) from exc
        return self._build_response(
            question,
            prepared,
            answer,
            (time.perf_counter() - llm_started) * 1000,
        )

    def query_stream(
        self,
        question: str,
        on_token: Callable[[str], None],
        response_style: Optional[str] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> RAGResponse:
        """Run the same RAG path while forwarding provider chunks as they arrive."""
        prepared = self._prepare_query(question, response_style, time.perf_counter())
        if not prepared.context_docs:
            return self._build_response(question, prepared, NO_ANSWER_RESPONSE, 0.0)

        llm_started = time.perf_counter()
        first_token_ms: Optional[float] = None
        answer_parts: List[str] = []
        try:
            llm = self._ensure_llm()
            for chunk in llm.stream(prepared.prompt):
                if should_stop and should_stop():
                    break
                content = getattr(chunk, "content", chunk)
                if isinstance(content, list):
                    content = "".join(
                        part.get("text", "") for part in content if isinstance(part, dict)
                    )
                if not isinstance(content, str) or not content:
                    continue
                if first_token_ms is None:
                    first_token_ms = (time.perf_counter() - llm_started) * 1000
                answer_parts.append(content)
                on_token(content)
        except Exception as exc:  # noqa: BLE001
            raise self._provider_error(exc) from exc

        answer = "".join(answer_parts).strip() or NO_ANSWER_RESPONSE
        return self._build_response(
            question,
            prepared,
            answer,
            (time.perf_counter() - llm_started) * 1000,
            first_token_ms,
        )

    def _prepare_query(
        self,
        question: str,
        response_style: Optional[str],
        started_at: float,
    ) -> _PreparedQuery:
        retrieval_started = time.perf_counter()
        candidate_results = self._retriever.retrieve_with_scores(
            question,
            limit=self._retriever.initial_k,
        )
        timings = dict(getattr(self._retriever, "last_timings", {}))
        timings["retrieval_ms"] = (time.perf_counter() - retrieval_started) * 1000
        candidates = [doc for doc, _ in candidate_results]
        candidate_debug = (
            [_debug_document(doc, "candidate", retrieval_score=score) for doc, score in candidate_results]
            if settings.DEBUG_RETRIEVAL else []
        )

        rerank_started = time.perf_counter()
        reranked_docs = self._reranker.rerank(question, candidates)
        timings["reranking_ms"] = (time.perf_counter() - rerank_started) * 1000
        reranked_debug = (
            [_debug_document(doc, "reranked") for doc in reranked_docs]
            if settings.DEBUG_RETRIEVAL else []
        )

        context_started = time.perf_counter()
        context_docs = self._retriever.expand_context(reranked_docs, query=question)
        timings["context_ms"] = (time.perf_counter() - context_started) * 1000

        prompt_started = time.perf_counter()
        prompt = build_rag_prompt(
            question=question,
            context_docs=context_docs,
            history=self.conversation_history,
            response_style=response_style or self.response_style,
        )
        timings["prompt_ms"] = (time.perf_counter() - prompt_started) * 1000
        timings["prompt_chars"] = float(len(prompt))
        timings["approximate_prompt_tokens"] = float((len(prompt) + 3) // 4)

        return _PreparedQuery(
            started_at=started_at,
            candidate_results=candidate_results,
            context_docs=context_docs,
            prompt=prompt,
            timings=timings,
            candidate_debug=candidate_debug,
            reranked_debug=reranked_debug,
        )

    # ------------------------------------------------------------------
    # Backward-compatible interface (original RAGChain API)
    # ------------------------------------------------------------------

    def invoke(self, question: str) -> str:
        """Backward-compatible: return just the answer string."""
        return self.query(question).answer

    def run(self, question: str) -> str:
        """Alias for invoke()."""
        return self.invoke(question)


# ---------------------------------------------------------------------------
# Convenience factory — used by API routers and tests
# ---------------------------------------------------------------------------

def build_pipeline(
    allowed_document_ids: Optional[Set[str]] = None,
    user_id: str = "anonymous",
    conversation_history: Optional[str] = None,
    response_style: str = "answer",
) -> EnterpriseRAGPipeline:
    """Return a configured EnterpriseRAGPipeline ready to query."""
    return EnterpriseRAGPipeline(
        allowed_document_ids=allowed_document_ids,
        user_id=user_id,
        conversation_history=conversation_history,
        response_style=response_style,
    )


def _debug_document(
    doc: Document,
    stage: str,
    retrieval_score: Optional[float] = None,
) -> Dict:
    metadata = doc.metadata
    return {
        "stage": stage,
        "source_filename": metadata.get("source_filename"),
        "page": metadata.get("page_number", metadata.get("page")),
        "document_id": metadata.get("document_id"),
        "chunk_id": metadata.get("chunk_id"),
        "section": metadata.get("section") or metadata.get("subsection"),
        "similarity_score": metadata.get("vector_score"),
        "vector_score": metadata.get("vector_score"),
        "bm25_score": metadata.get("bm25_score"),
        "hybrid_score": metadata.get("hybrid_score"),
        "retrieval_score": retrieval_score,
        "rerank_score": metadata.get("rerank_score"),
        "chunk_text_preview": doc.page_content.strip()[:500],
    }


# ---------------------------------------------------------------------------
# Stage 1 shim — keeps existing api.py / app.py imports from breaking
# ---------------------------------------------------------------------------

class RAGChain:
    """
    Shim that wraps EnterpriseRAGPipeline with the original RAGChain API.

    Remove once all callers are migrated to build_pipeline().
    """

    def __init__(self, llm, vector_db, k: int = 3) -> None:  # noqa: ANN001
        # Ignore the injected llm/vector_db — pipeline manages its own
        self._pipeline = EnterpriseRAGPipeline(allowed_document_ids=None)

    def invoke(self, query: str) -> str:
        return self._pipeline.invoke(query)

    def run(self, query: str) -> str:
        return self.invoke(query)


def build_rag_chain(llm, vector_db) -> RAGChain:  # noqa: ANN001
    """Backward-compatible factory."""
    return RAGChain(llm, vector_db)
