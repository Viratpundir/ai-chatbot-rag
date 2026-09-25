"""
app/api/v1/admin.py
-------------------
Admin dashboard endpoints.

Stage 1: Stubs.
Stage 12: Full implementation with analytics + system health.
Stage 13: Audit log viewing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.auth.permissions import require_admin
from app.core.logging import get_logger
from app.database.database import check_db_health, get_db
from app.database.models import AuditLog, Document, User
from app.database.repositories import AuditLogRepository, DocumentRepository, UserRepository
from app.rag.vector_store import get_vector_store

router = APIRouter(prefix="/admin", tags=["Admin"])
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Response models (inline for Stage 1 — move to schemas/admin.py in Stage 12)
# ---------------------------------------------------------------------------

class DashboardStats(BaseModel):
    total_users: int
    active_users: int
    total_documents: int
    processing_documents: int
    failed_documents: int
    total_queries: int
    queries_today: int


class SystemHealth(BaseModel):
    status: str
    database: str
    redis: str
    vector_store: str
    llm: str
    uptime_seconds: Optional[float] = None


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
    audit = AuditLogRepository(db)
    return DashboardStats(
        total_users=total_users,
        active_users=active_users,
        total_documents=sum(document_stats.values()),
        processing_documents=document_stats.get("processing", 0) + document_stats.get("pending", 0),
        failed_documents=document_stats.get("failed", 0),
        total_queries=await audit.count_by_action("rag_query", since_minutes=525600),
        queries_today=await audit.count_by_action("rag_query", since_minutes=1440),
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
    return SystemHealth(
        status="ok" if database == "ok" else "degraded",
        database=database,
        redis="not_configured",
        vector_store=vector_store,
        llm="configured",
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
