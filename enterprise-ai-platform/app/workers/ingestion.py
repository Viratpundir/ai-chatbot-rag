"""Background document ingestion used by the upload and re-index routes."""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.core.config import settings
from app.database.database import db_session
from app.database.repositories import DocumentRepository
from app.rag.loader import DocumentLoadError, load_documents
from app.rag.splitter import split_docs
from app.rag.vector_store import get_vector_store

logger = get_logger(__name__)


async def ingest_document(document_id: str) -> None:
    """Load, chunk, embed, and index one document without blocking upload."""
    async with db_session() as db:
        repo = DocumentRepository(db)
        document = await repo.get_by_id(document_id)
        if document is None or document.status == "deleted":
            return

        logger.info("[PROCESSING] %s", document_id)
        await repo.update_status(document_id, "processing")
        try:
            logger.info("[PDF EXTRACTION] %s", document_id)
            loaded = await asyncio.to_thread(load_documents, document.file_path, document_id)
            for page in loaded:
                page.metadata.update(
                    {
                        "source_filename": document.original_filename,
                        "owner_id": document.owner_id,
                        "department": document.department,
                        "classification": document.classification,
                    }
                )
            logger.info("[PDF EXTRACTION] %s pages=%d", document_id, len(loaded))
            chunks = await asyncio.to_thread(split_docs, loaded)
            for index, chunk in enumerate(chunks):
                chunk.metadata["chunk_id"] = f"{document_id}:{index}"
            if not chunks:
                raise DocumentLoadError("No text chunks were produced from the document.")
            logger.info("[CHUNKING] %s chunks=%d", document_id, len(chunks))
            logger.info("[EMBEDDING] %s vectors=%d", document_id, len(chunks))
            vector_store = get_vector_store()
            await asyncio.to_thread(vector_store.delete_document, document_id)
            await asyncio.to_thread(vector_store.add_documents, chunks)
            logger.info("[VECTOR STORE] %s indexed successfully", document_id)
            await repo.update_status(
                document_id,
                "ready",
                chunk_count=len(chunks),
                doc_metadata={"page_count": len(loaded)},
            )
            logger.info("[READY] %s", document_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[FAILED] %s", document_id)
            await repo.update_status(document_id, "failed", error_message=str(exc))


async def remove_document_from_index(document_id: str) -> None:
    """Remove all chunks for a soft-deleted document from FAISS."""
    await asyncio.to_thread(get_vector_store().delete_document, document_id)


async def enqueue_document_ingestion(document_id: str) -> None:
    """Queue ingestion in Celery when enabled, otherwise run the local task."""
    if settings.CELERY_ENABLED:
        from app.workers.celery_app import ingest_document_task
        ingest_document_task.delay(document_id)
        return
    await ingest_document(document_id)