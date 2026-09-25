"""Optional Redis/Celery worker entry point for production ingestion."""

from __future__ import annotations

import asyncio

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "enterprise_ai",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def ingest_document_task(self, document_id: str) -> None:
    from app.workers.ingestion import ingest_document
    asyncio.run(ingest_document(document_id))