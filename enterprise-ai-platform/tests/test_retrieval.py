from __future__ import annotations

from langchain_core.documents import Document

from app.rag.prompts import build_citations
from app.rag.retriever import HybridRetriever
from app.rag.splitter import split_docs


class FakeVectorStore:
    def __init__(self, dense_documents, corpus):
        self.dense_documents = dense_documents
        self.corpus = corpus

    def similarity_search_with_score(self, query, k, filter_document_ids=None):
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
