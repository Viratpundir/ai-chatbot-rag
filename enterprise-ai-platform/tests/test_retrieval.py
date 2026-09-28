from __future__ import annotations

from langchain_core.documents import Document

from app.core.config import settings
from app.rag import embeddings, reranker
from app.rag.pipeline import EnterpriseRAGPipeline
from app.rag.prompts import build_citations, build_rag_prompt
from app.rag.retriever import HybridRetriever
from app.rag.splitter import split_docs


class FakeVectorStore:
    def __init__(self, dense_documents, corpus):
        self.dense_documents = dense_documents
        self.corpus = corpus

    def similarity_search_with_score(self, query, k, filter_document_ids=None, timings=None):
        allowed = set(filter_document_ids) if filter_document_ids is not None else None
        documents = [
            (doc, score)
            for doc, score in self.dense_documents
            if allowed is None or doc.metadata.get("document_id") in allowed
        ]
        return documents[:k]

    def iter_documents(self, filter_document_ids=None):
        allowed = set(filter_document_ids) if filter_document_ids is not None else None
        return [
            doc for doc in self.corpus
            if allowed is None or doc.metadata.get("document_id") in allowed
        ]


def make_chunk(document_id, chunk_id, content, section="Leave Policy"):
    return Document(
        page_content=content,
        metadata={
            "document_id": document_id,
            "chunk_id": chunk_id,
            "chunk_index": int(chunk_id.split("-")[-1]),
            "source_filename": f"{document_id}.pdf",
            "page_number": 42,
            "section": section,
        },
    )


def test_bm25_recovers_exact_clause_outside_dense_results():
    generic = make_chunk("allowed", "chunk-0", "Employees should follow the standard leave policy.")
    exact = make_chunk("allowed", "chunk-1", "Emergency leave does not require the standard 7-day notice.")
    unrelated = make_chunk("allowed", "chunk-2", "The travel reimbursement form is due monthly.", section="Travel")
    store = FakeVectorStore([(generic, 0.01)], [generic, exact, unrelated])

    results = HybridRetriever(allowed_document_ids={"allowed"}, initial_k=2, top_k=2, vector_store=store).retrieve_candidates(
        "What is the exception to the 7-day leave application rule?"
    )

    assert exact in results
    assert exact.metadata["bm25_score"] > 0


def test_lexical_search_never_reads_unauthorized_corpus():
    allowed = make_chunk("allowed", "chunk-0", "The policy permits annual leave.")
    secret = make_chunk("secret", "chunk-0", "The exact exception is confidential leave access.")
    store = FakeVectorStore([], [allowed, secret])

    results = HybridRetriever(allowed_document_ids={"allowed"}, initial_k=5, top_k=5, vector_store=store).retrieve_candidates(
        "What is the confidential exception?"
    )

    assert all(doc.metadata["document_id"] == "allowed" for doc in results)


def test_chunking_preserves_heading_context_and_page_metadata():
    chunks = split_docs([
        Document(
            page_content="# Leave Policy\nEmergency leave does not require the standard 7-day notice.",
            metadata={"document_id": "doc-1", "source_filename": "handbook.pdf", "page_number": 42},
        )
    ])

    assert chunks[0].metadata["section"] == "Leave Policy"
    assert chunks[0].metadata["page_number"] == 42
    assert "Leave Policy" in chunks[0].page_content


def test_citations_include_section_and_retrieval_scores():
    doc = make_chunk("doc-1", "chunk-0", "Emergency leave is exempt.")
    doc.metadata.update({"vector_score": 0.8, "bm25_score": 1.0, "hybrid_score": 0.88, "rerank_score": 2.1})

    citation = build_citations([doc])[0]

    assert citation["filename"] == "doc-1.pdf"
    assert citation["page"] == 42
    assert citation["section"] == "Leave Policy"
    assert citation["hybrid_score"] == 0.88


def test_guide_prompt_requests_supported_steps_without_changing_chat_prompt():
    docs = [make_chunk("doc-1", "chunk-0", "Machine learning is a subset of AI.")]

    guide_prompt = build_rag_prompt("Explain AI", docs, response_style="guide")
    chat_prompt = build_rag_prompt("Explain AI", docs)

    assert "numbered steps" in guide_prompt
    assert "Do not invent steps" in guide_prompt
    assert "numbered steps" not in chat_prompt


def test_ethics_wording_expands_to_named_heading_and_synonyms():
    retriever = HybridRetriever(vector_store=FakeVectorStore([], []))

    variants = retriever.query_variants("What are the five principles of ethical AI?")

    assert "THE FIVE PILLARS OF AI ETHICS" in variants
    assert any("principles for ethical artificial intelligence" in item for item in variants)


def test_named_section_expansion_includes_all_bounded_section_chunks():
    chunks = [
        make_chunk("allowed", f"chunk-{index}", f"Section details {index}.", section="AI Ethics")
        for index in range(5)
    ]
    retriever = HybridRetriever(
        allowed_document_ids={"allowed"},
        initial_k=5,
        top_k=3,
        vector_store=FakeVectorStore([], chunks),
    )

    expanded = retriever.expand_context([chunks[1]])

    assert {doc.metadata["chunk_id"] for doc in expanded} == {
        doc.metadata["chunk_id"] for doc in chunks
    }
    assert len(expanded) <= settings.CONTEXT_EXPANSION_MAX_CHUNKS


def test_exact_section_query_uses_section_chunks_without_unrelated_reranked_context():
    heading = "THE FIVE PILLARS OF AI ETHICS"
    section_chunks = [
        make_chunk("allowed", f"chunk-{index}", f"Pillar details {index}.", section=heading)
        for index in range(4)
    ]
    unrelated = make_chunk("allowed", "chunk-8", "Unrelated AI policy details.", section="AI Policies")
    retriever = HybridRetriever(
        allowed_document_ids={"allowed"},
        initial_k=5,
        top_k=3,
        vector_store=FakeVectorStore([], [*section_chunks, unrelated]),
    )

    expanded = retriever.expand_context(
        [section_chunks[0], unrelated],
        query="What are the five principles of AI Ethics?",
    )

    assert expanded == section_chunks


def test_context_expansion_deduplicates_and_obeys_global_limit(monkeypatch):
    monkeypatch.setattr(settings, "CONTEXT_EXPANSION_MAX_CHUNKS", 4)
    docs = [make_chunk("allowed", f"chunk-{index}", f"Content {index}.", section="Shared") for index in range(8)]
    retriever = HybridRetriever(
        allowed_document_ids={"allowed"},
        initial_k=8,
        top_k=3,
        vector_store=FakeVectorStore([], docs),
    )

    expanded = retriever.expand_context([docs[0], docs[0], docs[5]])

    assert len(expanded) == 4
    assert len({doc.metadata["chunk_id"] for doc in expanded}) == 4


def test_identical_query_embedding_is_reused(monkeypatch):
    calls = []

    class FakeEmbeddings:
        def embed_query(self, text):
            calls.append(text)
            return [0.1, 0.2]

    embeddings._clear_query_embedding_cache()
    monkeypatch.setattr(embeddings, "get_embeddings", lambda: FakeEmbeddings())
    try:
        assert embeddings.embed_query("same question") == [0.1, 0.2]
        assert embeddings.embed_query("same question") == [0.1, 0.2]
    finally:
        embeddings._clear_query_embedding_cache()

    assert calls == ["same question"]


def test_identical_rerank_inputs_reuse_exact_scores(monkeypatch):
    calls = []

    class ScoreList(list):
        def tolist(self):
            return list(self)

    class FakeCrossEncoder:
        def predict(self, pairs):
            calls.append(tuple(pairs))
            return ScoreList([0.9, 0.1])

    documents = [
        make_chunk("allowed", "chunk-0", "First supported passage."),
        make_chunk("allowed", "chunk-1", "Second supported passage."),
    ]
    reranker._clear_rerank_score_cache()
    monkeypatch.setattr(reranker, "_get_cross_encoder", lambda: FakeCrossEncoder())
    try:
        first = reranker.Reranker(top_n=2).rerank("same question", documents.copy())
        second = reranker.Reranker(top_n=2).rerank("same question", documents.copy())
    finally:
        reranker._clear_rerank_score_cache()

    assert calls == [(('same question', documents[0].page_content), ('same question', documents[1].page_content))]
    assert [doc.metadata["chunk_id"] for doc in first] == [doc.metadata["chunk_id"] for doc in second]


def test_exact_named_section_match_gets_a_stronger_retrieval_boost():
    heading = make_chunk("allowed", "chunk-0", "Section content.", section="THE FIVE PILLARS OF AI ETHICS")
    other = make_chunk("allowed", "chunk-1", "Other content.", section="Student Conduct")

    retriever = HybridRetriever(vector_store=FakeVectorStore([], [heading, other]))
    results = retriever.retrieve_with_scores("What are the five principles of AI Ethics?", limit=2)

    assert results[0][0] == heading
    assert results[0][1] >= 0.35


def test_debug_trace_includes_query_candidates_ranking_and_confidence(monkeypatch):
    document = make_chunk(
        "allowed", "chunk-4", "The section explains fairness and accountability.", section="AI Ethics"
    )

    class TraceRetriever:
        initial_k = 15

        def retrieve_with_scores(self, query, limit):
            return [(document, 0.82)]

        def query_variants(self, query):
            return [query, "AI ethics principles"]

        def expand_context(self, documents, query=None):
            return documents

    class TraceReranker:
        def rerank(self, query, candidates):
            candidates[0].metadata["rerank_score"] = 1.7
            return candidates

    class TraceLLM:
        @staticmethod
        def invoke(prompt):
            return "Fairness reduces bias."

        @staticmethod
        def stream(prompt):
            yield "Fairness "
            yield "reduces bias."

    monkeypatch.setattr(settings, "DEBUG_RETRIEVAL", True)
    pipeline = EnterpriseRAGPipeline(allowed_document_ids={"allowed"})
    pipeline._retriever = TraceRetriever()
    pipeline._reranker = TraceReranker()
    pipeline._llm = TraceLLM()

    response = pipeline.query("Explain fairness in AI")
    stages = {entry["stage"]: entry for entry in response.retrieval_debug}

    assert stages["query"]["expanded_queries"] == ["AI ethics principles"]
    assert stages["candidate"]["chunk_id"] == "chunk-4"
    assert stages["candidate"]["source_filename"] == "allowed.pdf"
    assert stages["candidate"]["page"] == 42
    assert stages["candidate"]["retrieval_score"] == 0.82
    assert stages["reranked"]["rerank_score"] == 1.7
    assert stages["final_context"]["chunk_text_preview"].startswith("The section explains")
    assert stages["confidence"]["generation_has_answer"] is True

    streamed_tokens = []
    streamed_response = pipeline.query_stream(
        "Explain fairness in AI",
        streamed_tokens.append,
    )

    assert "".join(streamed_tokens) == response.answer
    assert streamed_response.citations == response.citations
    assert streamed_response.llm_first_token_ms is not None
