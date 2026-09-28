"""Persistent document-file storage with local development and S3-compatible backends."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit

from app.core.config import settings


@lru_cache(maxsize=1)
def _s3_client():
    import boto3

    if bool(settings.S3_ACCESS_KEY_ID) != bool(settings.S3_SECRET_ACCESS_KEY):
        raise RuntimeError("Configure both S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY, or use the host IAM role.")

    options = {}
    if settings.S3_REGION:
        options["region_name"] = settings.S3_REGION
    if settings.S3_ENDPOINT_URL:
        options["endpoint_url"] = settings.S3_ENDPOINT_URL
    if settings.S3_ACCESS_KEY_ID:
        options["aws_access_key_id"] = settings.S3_ACCESS_KEY_ID
        options["aws_secret_access_key"] = settings.S3_SECRET_ACCESS_KEY
    return boto3.client("s3", **options)


def is_object_storage_path(file_path: str) -> bool:
    return file_path.startswith("s3://")


def _parse_s3_path(file_path: str) -> tuple[str, str]:
    parsed = urlsplit(file_path)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError("Invalid S3 document path.")
    return parsed.netloc, parsed.path.lstrip("/")


def store_document_file(filename: str, content: bytes, content_type: str | None = None) -> str:
    """Store uploaded bytes remotely when configured, otherwise use local dev storage."""
    if not settings.S3_BUCKET:
        path = settings.upload_dir_path / Path(filename).name
        path.write_bytes(content)
        return str(path)

    prefix = settings.S3_DOCUMENT_PREFIX.strip("/")
    key = f"{prefix}/{Path(filename).name}" if prefix else Path(filename).name
    options = {"Bucket": settings.S3_BUCKET, "Key": key, "Body": content}
    if content_type:
        options["ContentType"] = content_type
    _s3_client().put_object(**options)
    return f"s3://{settings.S3_BUCKET}/{key}"


@contextmanager
def materialize_document(file_path: str) -> Iterator[Path]:
    """Yield a local path for the existing document loaders; clean S3 temp files afterward."""
    if not is_object_storage_path(file_path):
        yield Path(file_path)
        return

    bucket, key = _parse_s3_path(file_path)
    suffix = Path(key).suffix
    descriptor, temporary_path = tempfile.mkstemp(suffix=suffix)
    os.close(descriptor)
    local_path = Path(temporary_path)
    try:
        _s3_client().download_file(bucket, key, str(local_path))
        yield local_path
    finally:
        local_path.unlink(missing_ok=True)


def open_document_object(file_path: str):
    """Return an S3 streaming body, or None for a local filesystem path."""
    if not is_object_storage_path(file_path):
        return None
    bucket, key = _parse_s3_path(file_path)
    return _s3_client().get_object(Bucket=bucket, Key=key)["Body"]


def delete_document_file(file_path: str) -> None:
    """Delete a stored object or local development file."""
    if is_object_storage_path(file_path):
        bucket, key = _parse_s3_path(file_path)
        _s3_client().delete_object(Bucket=bucket, Key=key)
        return
    Path(file_path).unlink(missing_ok=True)


def storage_health() -> str:
    """Return a small non-sensitive storage status for diagnostics."""
    if not settings.S3_BUCKET:
        return "local"
    _s3_client().head_bucket(Bucket=settings.S3_BUCKET)
    return "ok"
