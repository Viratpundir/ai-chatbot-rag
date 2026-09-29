"""
app/rag/vector_store.py
-----------------------
Persistent FAISS vector store with per-document namespace support.

Extends the original src/vector_store.py (in-memory FAISS) with:
  - Persistence: index is saved to / loaded from VECTOR_STORE_PATH.
  - Per-document deletion by document_id metadata field.
  - A global singleton index managed by VectorStoreManager.
  - Thread-safe add / delete operations using a threading.Lock.

The store is keyed by an index_name (default: "main") so future stages
can run multiple named indexes (e.g., per-department).
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

from langchain_core.documents import Document

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class VectorStoreManager:
    """
    Manages a persistent FAISS index.

    Typical usage::

        vsm = VectorStoreManager()
        vsm.add_documents(chunks)          # during ingestion
        results = vsm.similarity_search(query, k=5)
        vsm.delete_document("doc-uuid")    # when a document is removed
    """

    def __init__(self, index_name: str = "main") -> None:
        self.index_name = index_name
        self._store_path = Path(settings.VECTOR_STORE_PATH) / index_name
        self._lock = threading.Lock()
        self._index = None  # lazy-loaded
        self._loaded_generation: Optional[str] = None

    @property
    def _generation_path(self) -> Path:
        return self._store_path / ".generation"

    def _read_generation(self) -> Optional[str]:
        try:
            return self._generation_path.read_text(encoding="ascii").strip()
        except FileNotFoundError:
            index_path = self._store_path / "index.faiss"
            if not index_path.exists():
                return None
            stat = index_path.stat()
            return f"legacy:{stat.st_mtime_ns}:{stat.st_size}"

    @contextmanager
    def _distributed_index_lock(self) -> Iterator[None]:
        if not settings.is_production or settings.FAISS_SINGLE_INSTANCE:
            yield
            return

        from redis import Redis

        client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        lock = client.lock(
            f"nexaiq:faiss:{self._store_path.resolve()}",
            timeout=1800,
            blocking_timeout=60,
        )
        acquired = False
        try:
            acquired = lock.acquire(blocking=True)
            if not acquired:
                raise RuntimeError("Could not acquire the shared FAISS index lock.")
            yield
        finally:
            if acquired:
                lock.release()
            client.close()

    def _load_current_generation(self) -> None:
        self._index = self._load_or_create()
        self._loaded_generation = self._read_generation()

    def _refresh_if_changed(self, *, distributed_lock_held: bool = False) -> None:
        current_generation = self._read_generation()
        if self._index is not None and current_generation == self._loaded_generation:
            return
        if distributed_lock_held or not settings.is_production:
            self._load_current_generation()
            return
        with self._distributed_index_lock():
            current_generation = self._read_generation()
            if self._index is None or current_generation != self._loaded_generation:
                self._load_current_generation()

    # ------------------------------------------------------------------
    # Index lifecycle
    # ------------------------------------------------------------------

    def _get_embeddings(self):
        from app.rag.embeddings import get_embeddings  # avoid circular at module load
        return get_embeddings()

    def _load_or_create(self):
        """Load existing index from disk, or return None if not yet created."""
        from langchain_community.vectorstores import FAISS  # lazy

        if (self._store_path / "index.faiss").exists():
            logger.info("Loading existing FAISS index", extra={"path": str(self._store_path)})
            return FAISS.load_local(
                str(self._store_path),
                self._get_embeddings(),
                allow_dangerous_deserialization=True,
            )
        return None

    def _save(self) -> None:
        """Persist index files and publish a generation marker for shared readers."""
        self._store_path.mkdir(parents=True, exist_ok=True)
        if self._index is not None:
            self._index.save_local(str(self._store_path))
            logger.debug("FAISS index saved", extra={"path": str(self._store_path)})
        else:
            for filename in ("index.faiss", "index.pkl"):
                (self._store_path / filename).unlink(missing_ok=True)
        temporary_marker = self._generation_path.with_name(f".generation.{uuid.uuid4().hex}.tmp")
        temporary_marker.write_text(uuid.uuid4().hex, encoding="ascii")
        os.replace(temporary_marker, self._generation_path)
        self._loaded_generation = self._read_generation()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_documents(self, documents: List[Document]) -> None:
        """
        Add *documents* to the index (creates the index if it doesn't exist).

        Thread-safe: acquires lock, updates, saves, releases.
        """
        from langchain_community.vectorstores import FAISS  # lazy

        if not documents:
            return

        with self._lock:
            with self._distributed_index_lock():
                self._refresh_if_changed(distributed_lock_held=True)

                if self._index is None:
                    logger.info("Creating new FAISS index")
                    self._index = FAISS.from_documents(documents, self._get_embeddings())
                else:
                    self._index.add_documents(documents)

                self._save()
            logger.info(
                "Documents added to vector store",
                extra={"count": len(documents), "index": self.index_name},
            )

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter_document_ids: Optional[List[str]] = None,
    ) -> List[Document]:
        """
        Return the *k* most similar chunks to *query*.

        Args:
            query:              The search string.
            k:                  Number of results.
            filter_document_ids: If provided, only return chunks whose
                                 metadata["document_id"] is in this list.
                                 This is the document-level auth filter —
                                 only authorised document IDs are passed in.
        """
        with self._lock:
            self._refresh_if_changed()
            if self._index is None:
                logger.warning("Vector store is empty — no documents indexed yet")
                return []
            if filter_document_ids is not None and not filter_document_ids:
                return []
            # Fetch extra candidates so filtering doesn't leave us with too few.
            fetch_k = len(self._index.index_to_docstore_id) if filter_document_ids else k
            results = self._index.similarity_search(query, k=fetch_k)

        if filter_document_ids:
            allowed = set(filter_document_ids)
            results = [
                doc for doc in results
                if doc.metadata.get("document_id") in allowed
            ]

        return results[:k]

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
        filter_document_ids: Optional[List[str]] = None,
        timings: Optional[dict[str, float]] = None,
    ) -> List[tuple[Document, float]]:
        """Like similarity_search but returns (Document, score) tuples."""
        index_load_started = time.perf_counter()
        with self._lock:
            self._refresh_if_changed()
            if self._index is None:
                return []
            if filter_document_ids is not None and not filter_document_ids:
                return []
        index_load_ms = (time.perf_counter() - index_load_started) * 1000

        embedding_started = time.perf_counter()
        from app.rag.embeddings import embed_query

        query_embedding = embed_query(query)
        embedding_ms = (time.perf_counter() - embedding_started) * 1000

        vector_search_started = time.perf_counter()
        fetch_k = index_size if filter_document_ids else k
        with self._lock:
            self._refresh_if_changed()
            index = self._index
            if index is None:
                return []
            fetch_k = len(index.index_to_docstore_id) if filter_document_ids else k
            results = index.similarity_search_with_score_by_vector(
                query_embedding,
                k=fetch_k,
            )
        vector_search_ms = (time.perf_counter() - vector_search_started) * 1000

        permission_filter_started = time.perf_counter()
        if filter_document_ids:
            allowed = set(filter_document_ids)
            results = [
                (doc, score) for doc, score in results
                if doc.metadata.get("document_id") in allowed
            ]

        if timings is not None:
            timings.update({
                "index_load_ms": index_load_ms,
                "embedding_ms": embedding_ms,
                "vector_search_ms": vector_search_ms,
                "permission_filter_ms": (time.perf_counter() - permission_filter_started) * 1000,
                "index_size": float(fetch_k if filter_document_ids else len(index.index_to_docstore_id)),
            })

        return results[:k]

    def iter_documents(
        self,
        filter_document_ids: Optional[List[str]] = None,
    ) -> List[Document]:
        """Return indexed chunks, restricted before lexical retrieval."""
        with self._lock:
            self._refresh_if_changed()
            if self._index is None:
                return []
            documents = list(self._index.docstore._dict.values())
        if filter_document_ids is None:
            return documents
        allowed = set(filter_document_ids)
        return [doc for doc in documents if doc.metadata.get("document_id") in allowed]

    def delete_document(self, document_id: str) -> int:
        """
        Remove all chunks belonging to *document_id* from the index.

        Returns the number of chunks removed.

        Note: FAISS does not natively support per-document deletion.
        We rebuild the index without the target document's chunks.
        This is acceptable for enterprise document counts (hundreds/thousands).
        For millions of chunks, switch to a vector store with native delete
        support (e.g., pgvector, Qdrant, Weaviate).
        """
        from langchain_community.vectorstores import FAISS  # lazy

        with self._lock:
            with self._distributed_index_lock():
                self._refresh_if_changed(distributed_lock_held=True)
                if self._index is None:
                    return 0

                all_docs = list(self._index.docstore._dict.values())
                kept = [doc for doc in all_docs if doc.metadata.get("document_id") != document_id]
                removed = len(all_docs) - len(kept)

                if removed == 0:
                    logger.info(
                        "No chunks found for document_id",
                        extra={"document_id": document_id},
                    )
                    return 0

                if kept:
                    self._index = FAISS.from_documents(kept, self._get_embeddings())
                else:
                    self._index = None

                self._save()
                logger.info(
                    "Chunks removed from vector store",
                    extra={"document_id": document_id, "removed": removed},
                )
                return removed

    def is_ready(self) -> bool:
        """Return True if the index exists and has at least one document."""
        with self._lock:
            self._refresh_if_changed()
            return self._index is not None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_manager: Optional[VectorStoreManager] = None
_manager_lock = threading.Lock()


def get_vector_store(index_name: str = "main") -> VectorStoreManager:
    """Return the global VectorStoreManager singleton."""
    global _manager
    with _manager_lock:
        if _manager is None or _manager.index_name != index_name:
            _manager = VectorStoreManager(index_name)
    return _manager


# ---------------------------------------------------------------------------
# Convenience shim — keeps the original one-liner API working
# ---------------------------------------------------------------------------
def create_vector_store(docs: List[Document], embeddings) -> VectorStoreManager:
    """
    Backward-compatible shim.

    Creates a fresh in-memory manager, adds *docs*, and returns it.
    Used by tests and one-off scripts.
    """
    mgr = VectorStoreManager(index_name="ephemeral")
    mgr.add_documents(docs)
    return mgr
