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
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

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
    llm_time_ms: float = 0.0
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
            "llm_time_ms": self.llm_time_ms,
            "total_time_ms": self.total_time_ms,
            "model": self.model,
            "has_answer": self.has_answer,
            "retrieval_debug": self.retrieval_debug,
        }


# ---------------------------------------------------------------------------
# LLM loader
# ---------------------------------------------------------------------------

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
    ) -> None:
        self.allowed_document_ids = allowed_document_ids
        self.user_id = user_id
        self.conversation_history = conversation_history
        self._retriever = get_retriever(allowed_document_ids)
        self._reranker = Reranker(top_n=settings.FINAL_RETRIEVAL_K)
        self._llm = None  # lazy

    def _ensure_llm(self):
        if self._llm is None:
            self._llm = _get_llm()
        return self._llm

    def query(self, question: str) -> RAGResponse:
        """
        Run the full RAG pipeline for *question*.

        Returns a RAGResponse with the answer, citations, and latency data.
        """
        total_start = time.perf_counter()

        # --- 1. Retrieval ---
        t0 = time.perf_counter()
        candidates = self._retriever.retrieve_candidates(question)
        retrieval_ms = (time.perf_counter() - t0) * 1000

        # --- 2. Reranking ---
        t0 = time.perf_counter()
        context_docs = self._reranker.rerank(question, candidates)
        reranking_ms = (time.perf_counter() - t0) * 1000
        context_docs = self._retriever.expand_context(context_docs)

        # --- 3. Prompt construction ---
        prompt = build_rag_prompt(
            question=question,
            context_docs=context_docs,
            history=self.conversation_history,
        )

        # --- 4. LLM inference ---
        t0 = time.perf_counter()
        try:
            llm = self._ensure_llm()
            raw = llm.invoke(prompt)
            answer = raw.content if hasattr(raw, "content") else str(raw)
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM inference failed", extra={"error": str(exc)})
            answer = NO_ANSWER_RESPONSE
        llm_ms = (time.perf_counter() - t0) * 1000

        total_ms = (time.perf_counter() - total_start) * 1000

        # --- 5. Build structured response ---
        citations = build_citations(context_docs)
        retrieval_debug = []
        if settings.DEBUG_RETRIEVAL:
            retrieval_debug = [
                {
                    "filename": doc.metadata.get("source_filename"),
                    "page": doc.metadata.get("page_number"),
                    "section": doc.metadata.get("section") or doc.metadata.get("subsection"),
                    "vector_score": doc.metadata.get("vector_score"),
                    "bm25_score": doc.metadata.get("bm25_score"),
                    "hybrid_score": doc.metadata.get("hybrid_score"),
                    "rerank_score": doc.metadata.get("rerank_score"),
                }
                for doc in context_docs
            ]
        has_answer = not is_no_answer(answer) and bool(context_docs)

        model_name = getattr(self._llm, "model", settings.OLLAMA_MODEL)

        logger.info(
            "RAG query completed",
            extra={
                "user_id": self.user_id,
                "retrieval_ms": round(retrieval_ms, 1),
                "reranking_ms": round(reranking_ms, 1),
                "llm_ms": round(llm_ms, 1),
                "total_ms": round(total_ms, 1),
                "chunks": len(context_docs),
                "has_answer": has_answer,
                "model": model_name,
                "candidate_chunks": len(candidates),
            },
        )

        return RAGResponse(
            answer=answer,
            citations=citations,
            context_docs=context_docs,
            retrieval_time_ms=round(retrieval_ms, 1),
            reranking_time_ms=round(reranking_ms, 1),
            llm_time_ms=round(llm_ms, 1),
            total_time_ms=round(total_ms, 1),
            model=model_name,
            has_answer=has_answer,
            query=question,
            retrieval_debug=retrieval_debug,
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
) -> EnterpriseRAGPipeline:
    """Return a configured EnterpriseRAGPipeline ready to query."""
    return EnterpriseRAGPipeline(
        allowed_document_ids=allowed_document_ids,
        user_id=user_id,
        conversation_history=conversation_history,
    )


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
