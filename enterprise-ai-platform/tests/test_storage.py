from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings
from app.main import validate_production_storage_settings
from app.storage import (
    delete_document_file,
    materialize_document,
    open_document_object,
    storage_health,
    store_document_file,
)
from app.rag.vector_store import VectorStoreManager


class FakeObjectBody:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        content, self.content = self.content, b""
        return content[:size] if size >= 0 else content

    def close(self) -> None:
        self.closed = True


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.body: FakeObjectBody | None = None

    def put_object(self, *, Bucket, Key, Body, ContentType=None):
        self.objects[(Bucket, Key)] = Body

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        Path(filename).write_bytes(self.objects[(bucket, key)])

    def get_object(self, *, Bucket, Key):
        self.body = FakeObjectBody(self.objects[(Bucket, Key)])
        return {"Body": self.body}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def head_bucket(self, *, Bucket):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


def test_local_document_storage_remains_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "S3_BUCKET", "")
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    stored_path = store_document_file("sample.pdf", b"pdf-bytes", "application/pdf")

    assert Path(stored_path).read_bytes() == b"pdf-bytes"
    with materialize_document(stored_path) as local_path:
        assert local_path == Path(stored_path)
    delete_document_file(stored_path)
    assert not Path(stored_path).exists()


def test_s3_storage_round_trips_file_and_temporary_processing_path(monkeypatch) -> None:
    fake_s3 = FakeS3Client()
    monkeypatch.setattr(settings, "S3_BUCKET", "nexaiq-documents")
    monkeypatch.setattr(settings, "S3_DOCUMENT_PREFIX", "tenant-files")
    monkeypatch.setattr("app.storage._s3_client", lambda: fake_s3)

    stored_path = store_document_file("document.pdf", b"pdf-bytes", "application/pdf")

    assert stored_path == "s3://nexaiq-documents/tenant-files/document.pdf"
    with materialize_document(stored_path) as local_path:
        assert local_path.read_bytes() == b"pdf-bytes"
        assert local_path.suffix == ".pdf"
    assert not local_path.exists()

    body = open_document_object(stored_path)
    assert body.read() == b"pdf-bytes"
    body.close()
    delete_document_file(stored_path)
    assert fake_s3.objects == {}
    assert storage_health() == "ok"


def test_second_faiss_manager_refreshes_shared_generation(tmp_path, monkeypatch) -> None:
    manager = VectorStoreManager(index_name="shared")
    second_manager = VectorStoreManager(index_name="shared")
    manager._store_path = tmp_path / "shared"
    second_manager._store_path = manager._store_path
    manager._store_path.mkdir()
    generation_file = manager._generation_path
    generation_file.write_text("generation-one", encoding="ascii")
    manager._loaded_generation = "generation-one"
    manager._index = object()
    refreshed_index = object()
    second_manager._loaded_generation = "generation-one"
    second_manager._index = object()
    monkeypatch.setattr(second_manager, "_load_or_create", lambda: refreshed_index)
    generation_file.write_text("generation-two", encoding="ascii")

    second_manager._refresh_if_changed()

    assert manager._index is not refreshed_index
    assert second_manager._index is refreshed_index
    assert second_manager._loaded_generation == "generation-two"


def test_production_storage_validation_rejects_ephemeral_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///local.db")
    monkeypatch.setattr(settings, "S3_BUCKET", "")
    monkeypatch.setattr(settings, "CELERY_ENABLED", False)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(settings, "VECTOR_STORE_PATH", "./data/vector_store")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="Invalid production configuration"):
        validate_production_storage_settings()


def test_production_storage_validation_accepts_shared_services(monkeypatch) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://user:pass@db.example.test/app")
    monkeypatch.setattr(settings, "S3_BUCKET", "nexaiq-documents")
    monkeypatch.setattr(settings, "CELERY_ENABLED", True)
    monkeypatch.setattr(settings, "REDIS_URL", "rediss://redis.example.test:6380/0")
    monkeypatch.setattr(settings, "VECTOR_STORE_PATH", "/mnt/efs/nexaiq/vector_store")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "OLLAMA_HOST", "https://ollama.example.test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-production-secret")

    validate_production_storage_settings()
