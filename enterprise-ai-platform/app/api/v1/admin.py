"""
app/api/v1/admin.py
-------------------
Admin dashboard endpoints.

Stage 1: Stubs.
Stage 12: Full implementation with analytics + system health.
Stage 13: Audit log viewing.
"""

from __future__ import annotations

import csv
import io
import json
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, func, select
import httpx
from redis.asyncio import Redis
from fastapi.responses import StreamingResponse

from app.auth.permissions import require_admin
from app.core.config import settings
from app.core.logging import get_logger
from app.database.database import check_db_health, get_db
from app.database.models import AuditLog, Conversation, Document, Message, User
from app.database.repositories import AuditLogRepository, DocumentRepository, UserRepository
from app.rag.embeddings import get_embeddings
from app.rag.vector_store import get_vector_store
from app.workers.ingestion import enqueue_document_ingestion

router = APIRouter(prefix="/admin", tags=["Admin"])
logger = get_logger(__name__)
_PROCESS_STARTED_AT = time.monotonic()


# ---------------------------------------------------------------------------
# Response models (inline for Stage 1 — move to schemas/admin.py in Stage 12)
# ---------------------------------------------------------------------------

class DashboardStats(BaseModel):
    total_users: int
    active_users: int
    total_documents: int
    processing_documents: int
    failed_documents: int
    ready_documents: int
    total_pages: int
    total_chunks: int
    searchable_documents: int
    total_queries: int
    queries_today: int
    average_retrieval_ms: Optional[float] = None
    average_llm_ms: Optional[float] = None
    average_total_ms: Optional[float] = None
    retrieval_top_k: int
    rerank_top_k: int


class AdminDocumentItem(BaseModel):
    document_id: str
    filename: str
    owner_id: str
    owner_name: str
    owner_email: str
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    file_size: int


class AdminDocumentList(BaseModel):
    documents: List[AdminDocumentItem]
    total: int
    page: int
    page_size: int


class SystemHealth(BaseModel):
    status: str
    database: str
    redis: str
    vector_store: str
    embeddings: str
    llm: str
    uptime_seconds: Optional[float] = None
    worker_count: Optional[int] = None


class VectorReindexResponse(BaseModel):
    status: str
    documents_queued: int
    skipped_in_progress: int


class AuditLogEntry(BaseModel):
    log_id: str
    user_id: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    timestamp: str
    ip_address: Optional[str]
    metadata: Optional[Dict[str, Any]]


class AuditLogList(BaseModel):
    logs: List[AuditLogEntry]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/dashboard",
    response_model=DashboardStats,
    summary="Get admin dashboard statistics (ADMIN+)",
)
async def dashboard(
    current_user: User = Depends(require_admin),
    db=Depends(get_db),
):
    """Return aggregate stats for the admin dashboard."""
    users = UserRepository(db)
    documents = DocumentRepository(db)
    _, total_users = await users.get_many(limit=1)
    active_users = (await users.get_many(is_active=True, limit=1))[1]
    document_stats = await documents.get_document_stats()
    totals = await db.execute(
        select(
            func.coalesce(func.sum(Document.doc_metadata["page_count"].as_integer()), 0),
            func.coalesce(func.sum(Document.chunk_count), 0),
            func.coalesce(func.sum(case((Document.status == "ready", 1), else_=0)), 0),
        ).where(Document.status != "deleted")
    )
    total_pages, total_chunks, searchable_documents = totals.one()
    timings = await db.execute(
        select(
            func.avg(Message.retrieval_time_ms),
            func.avg(Message.llm_time_ms),
            func.avg(Message.total_time_ms),
        )
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.role == "assistant")
    )
    average_retrieval_ms, average_llm_ms, average_total_ms = timings.one()
    audit = AuditLogRepository(db)
    return DashboardStats(
        total_users=total_users,
        active_users=active_users,
        total_documents=sum(document_stats.values()),
        processing_documents=(
            document_stats.get("uploaded", 0)
            + document_stats.get("processing", 0)
            + document_stats.get("pending", 0)
        ),
        failed_documents=document_stats.get("failed", 0),
        ready_documents=document_stats.get("ready", 0),
        total_pages=total_pages,
        total_chunks=total_chunks,
        searchable_documents=searchable_documents,
        total_queries=await audit.count_by_action("rag_query", since_minutes=525600),
        queries_today=await audit.count_by_action("rag_query", since_minutes=1440),
        average_retrieval_ms=round(average_retrieval_ms, 1) if average_retrieval_ms is not None else None,
        average_llm_ms=round(average_llm_ms, 1) if average_llm_ms is not None else None,
        average_total_ms=round(average_total_ms, 1) if average_total_ms is not None else None,
        retrieval_top_k=settings.INITIAL_RETRIEVAL_K,
        rerank_top_k=settings.FINAL_RETRIEVAL_K,
    )


@router.get(
    "/documents",
    response_model=AdminDocumentList,
    summary="List knowledge-base documents (ADMIN+)",
)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_admin),
    db=Depends(get_db),
):
    base_query = select(Document).where(Document.status != "deleted")
    count_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar_one()
    result = await db.execute(
        select(Document, User.name, User.email)
        .join(User, User.id == Document.owner_id)
        .where(Document.status != "deleted")
        .order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    documents = []
    for document, owner_name, owner_email in result.all():
        metadata = document.doc_metadata if isinstance(document.doc_metadata, dict) else {}
        documents.append(AdminDocumentItem(
            document_id=document.id,
            filename=document.original_filename,
            owner_id=document.owner_id,
            owner_name=owner_name,
            owner_email=owner_email,
            page_count=metadata.get("page_count"),
            chunk_count=document.chunk_count,
            status=document.status,
            error_message=document.error_message,
            created_at=document.created_at,
            file_size=document.file_size,
        ))
    return AdminDocumentList(
        documents=documents,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/health",
    response_model=SystemHealth,
    summary="System health check (ADMIN+)",
)
async def system_health(
    current_user: User = Depends(require_admin),
):
    """Check connectivity to all dependent services."""
    database = await check_db_health()
    vector_store = "ok" if get_vector_store().is_ready() else "empty"
    embeddings = "ready" if get_embeddings.cache_info().currsize else "not_loaded"

    if settings.CELERY_ENABLED:
        redis_client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        try:
            await redis_client.ping()
            redis = "ok"
        except Exception:  # noqa: BLE001
            redis = "offline"
        finally:
            await redis_client.aclose()
    else:
        redis = "not_configured"

    if settings.OPENAI_API_KEY:
        llm = "configured"
    else:
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                response = await client.get(f"{settings.OLLAMA_HOST.rstrip('/')}/api/tags")
            if response.is_success:
                models = response.json().get("models", [])
                llm = "ready" if any(
                    model.get("name") == settings.OLLAMA_MODEL for model in models
                ) else "model_missing"
            else:
                llm = "offline"
        except Exception:  # noqa: BLE001
            llm = "offline"

    status_value = "ok" if (
        database == "ok"
        and vector_store == "ok"
        and embeddings == "ready"
        and llm in {"ready", "configured"}
        and redis != "offline"
    ) else "degraded"
    return SystemHealth(
        status=status_value,
        database=database,
        redis=redis,
        vector_store=vector_store,
        embeddings=embeddings,
        llm=llm,
        uptime_seconds=round(time.monotonic() - _PROCESS_STARTED_AT, 1),
        worker_count=None,
    )


@router.post(
    "/vector/reindex",
    response_model=VectorReindexResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue existing documents for re-indexing (ADMIN+)",
)
async def reindex_vector_index(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db=Depends(get_db),
):
    """Re-run the existing ingestion worker for indexed and failed documents."""
    rows = await db.execute(
        select(Document.id, Document.status).where(Document.status != "deleted")
    )
    document_rows = rows.all()
    queued_statuses = {"ready", "failed", "uploaded"}
    queued_ids = [document_id for document_id, document_status in document_rows if document_status in queued_statuses]
    skipped_in_progress = sum(
        1 for _, document_status in document_rows if document_status in {"processing", "pending"}
    )
    for document_id in queued_ids:
        await DocumentRepository(db).update_status(document_id, "pending")
        background_tasks.add_task(enqueue_document_ingestion, document_id)
    await AuditLogRepository(db).log(
        action="vector_reindex_started",
        user_id=current_user.id,
        resource_type="vector_index",
        metadata={"documents_queued": len(queued_ids), "skipped_in_progress": skipped_in_progress},
    )
    return VectorReindexResponse(
        status="queued" if queued_ids else "completed",
        documents_queued=len(queued_ids),
        skipped_in_progress=skipped_in_progress,
    )


@router.get(
    "/audit-logs",
    response_model=AuditLogList,
    summary="View audit logs (ADMIN+)",
)
async def audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db=Depends(get_db),
):
    """
    Retrieve paginated audit logs.

    Admins see logs for their own scope.
    SUPER_ADMIN sees all logs.

    *Full implementation in Stage 13.*
    """
    parsed_from = datetime.fromisoformat(date_from) if date_from else None
    parsed_to = datetime.fromisoformat(date_to) if date_to else None
    if current_user.role != "SUPER_ADMIN":
        if user_id and user_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only view your own audit activity.")
        user_id = current_user.id
    logs, total = await AuditLogRepository(db).get_logs(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        date_from=parsed_from,
        date_to=parsed_to,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return AuditLogList(
        logs=[
            AuditLogEntry(
                log_id=log.id,
                user_id=log.user_id,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                timestamp=log.timestamp.isoformat(),
                ip_address=log.ip_address,
                metadata=log.log_metadata,
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/audit-logs/export",
    summary="Export audit logs as CSV (ADMIN+)",
)
async def export_audit_logs(
    current_user: User = Depends(require_admin),
    db=Depends(get_db),
):
    """Export actual audit rows and record the export action."""
    repo = AuditLogRepository(db)
    audit_user_id = None if current_user.role == "SUPER_ADMIN" else current_user.id
    records: List[AuditLog] = []
    offset = 0
    page_size = 200
    while True:
        page, total = await repo.get_logs(user_id=audit_user_id, offset=offset, limit=page_size)
        records.extend(page)
        offset += len(page)
        if not page or offset >= total:
            break

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["timestamp", "admin_user_id", "action", "resource_type", "resource_id", "ip_address", "metadata"])
    for record in records:
        writer.writerow([
            record.timestamp.isoformat(),
            record.user_id or "",
            record.action,
            record.resource_type or "",
            record.resource_id or "",
            record.ip_address or "",
            json.dumps(record.log_metadata or {}, ensure_ascii=False, default=str),
        ])
    await repo.log(
        action="audit_log_exported",
        user_id=current_user.id,
        resource_type="audit_log",
        metadata={"exported_rows": len(records), "format": "csv"},
    )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=enterprise-audit-log.csv"},
    )
