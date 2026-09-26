from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.workers import ingestion


@pytest.mark.asyncio
async def test_ingestion_closes_database_sessions_during_document_work(monkeypatch) -> None:
    active_sessions = 0
    statuses = []
    document = SimpleNamespace(
        id="doc-1",
        status="uploaded",
        file_path="sample.pdf",
        original_filename="sample.pdf",
        owner_id="owner-1",
        department=None,
        classification="INTERNAL",
    )

    class SessionContext:
        async def __aenter__(self):
            nonlocal active_sessions
            active_sessions += 1
            return object()

        async def __aexit__(self, exc_type, exc_value, traceback):
            nonlocal active_sessions
            active_sessions -= 1

    class DocumentRepository:
        def __init__(self, _db):
            pass

        async def get_by_id(self, _document_id):
            return document

        async def update_status(self, _document_id, status, **_kwargs):
            document.status = status
            statuses.append(status)

    class Chunk:
        def __init__(self):
            self.metadata = {}

    class VectorStore:
        def delete_document(self, _document_id):
            assert active_sessions == 0

        def add_documents(self, _chunks):
            assert active_sessions == 0

    def load_document(_file_path, _document_id):
        assert active_sessions == 0
        return [Chunk()]

    def split_document(_pages):
        assert active_sessions == 0
        return [Chunk()]

    monkeypatch.setattr(ingestion, "db_session", SessionContext)
    monkeypatch.setattr(ingestion, "DocumentRepository", DocumentRepository)
    monkeypatch.setattr(ingestion, "load_documents", load_document)
    monkeypatch.setattr(ingestion, "split_docs", split_document)
    monkeypatch.setattr(ingestion, "get_vector_store", VectorStore)

    await ingestion.ingest_document("doc-1")

    assert active_sessions == 0
    assert statuses == ["processing", "ready"]
