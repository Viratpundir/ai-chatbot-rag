"""Authenticated document management and permission endpoints."""

from __future__ import annotations

import hashlib
import asyncio
import uuid
from pathlib import Path as FilePath
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Path, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from app.auth.jwt import get_current_user
from app.auth.permissions import (
    assert_owner_or_admin,
    can_user_upload_documents,
    get_allowed_document_ids_for_user,
    require_admin,
)
from app.core.config import settings
from app.core.security import validate_upload_file
from app.database.database import get_db
from app.database.models import User
from app.database.repositories import AuditLogRepository, DocumentRepository
from app.schemas.documents import (
    DocumentListResponse,
    DocumentMetadataUpdate,
    DocumentPermissionAssign,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from app.storage import delete_document_file, is_object_storage_path, open_document_object, store_document_file
from app.workers.ingestion import enqueue_document_ingestion, remove_document_from_index

router = APIRouter(prefix="/documents", tags=["Documents"])


async def _process_uploaded_file(
    *,
    file: UploadFile,
    current_user: User,
    db,
    classification: str,
    department: str | None,
    background_tasks: BackgroundTasks,
) -> DocumentUploadResponse:
    filename = FilePath(file.filename or "").name
    content = await file.read(settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 1)
    errors = validate_upload_file(filename, file.content_type or "", len(content))
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    extension = filename.rsplit(".", 1)[-1].lower()
    stored_name = f"{uuid.uuid4()}.{extension}"
    stored_path = await asyncio.to_thread(
        store_document_file,
        stored_name,
        content,
        file.content_type,
    )
    checksum = hashlib.sha256(content).hexdigest()
    repo = DocumentRepository(db)
    document = await repo.create(
        filename=stored_name,
        original_filename=filename,
        file_path=stored_path,
        file_size=len(content),
        file_type=extension,
        mime_type=file.content_type,
        owner_id=current_user.id,
        department=department or current_user.department,
        classification=classification,
        checksum=checksum,
    )
    await AuditLogRepository(db).log(
        action="document_uploaded",
        user_id=current_user.id,
        resource_type="document",
        resource_id=document.id,
        metadata={"filename": filename, "size_bytes": len(content)},
    )
    background_tasks.add_task(enqueue_document_ingestion, document.id)
    return DocumentUploadResponse(
        document_id=document.id,
        filename=filename,
        status="uploaded",
        message="Document accepted for background processing.",
    )


def _to_response(document) -> DocumentStatusResponse:
    metadata = document.doc_metadata if isinstance(document.doc_metadata, dict) else {}
    return DocumentStatusResponse(
        document_id=document.id,
        filename=document.original_filename,
        status=document.status,
        owner_id=document.owner_id,
        file_size=document.file_size,
        classification=document.classification,
        department=document.department,
        version=document.version,
        created_at=document.created_at,
        updated_at=document.updated_at,
        chunk_count=document.chunk_count,
        page_count=metadata.get("page_count"),
        error_message=document.error_message,
        processing_started_at=document.processing_started_at,
        processing_completed_at=document.processing_completed_at,
    )


async def _get_accessible_document(document_id: str, user: User, db):
    document = await DocumentRepository(db).get_by_id(document_id)
    if document is None or document.status == "deleted":
        raise HTTPException(status_code=404, detail="Document not found.")
    role = str(user.role).upper()
    is_admin = role in {"ADMIN", "SUPER_ADMIN"}
    allowed = await get_allowed_document_ids_for_user(user, db)
    if not is_admin and document.owner_id != user.id and document.id not in allowed:
        raise HTTPException(status_code=403, detail="You cannot access this document.")
    return document


@router.post("", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    classification: str = Query("INTERNAL"),
    department: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    if not can_user_upload_documents(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to upload documents for your current role.",
        )
    if classification not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}:
        raise HTTPException(status_code=422, detail="Invalid document classification.")
    return await _process_uploaded_file(
        file=file,
        current_user=current_user,
        db=db,
        classification=classification,
        department=department,
        background_tasks=background_tasks,
    )


@router.post("/upload", response_model=list[DocumentUploadResponse], status_code=status.HTTP_202_ACCEPTED)
async def upload_documents_alias(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    classification: str = Query("INTERNAL"),
    department: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    return await upload_documents(
        background_tasks=background_tasks,
        files=files,
        classification=classification,
        department=department,
        current_user=current_user,
        db=db,
    )


@router.post("/bulk", response_model=list[DocumentUploadResponse], status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    classification: str = Query("INTERNAL"),
    department: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    if not can_user_upload_documents(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to upload documents for your current role.",
        )
    if classification not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}:
        raise HTTPException(status_code=422, detail="Invalid document classification.")
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required.")

    results: list[DocumentUploadResponse] = []
    for file in files:
        results.append(
            await _process_uploaded_file(
                file=file,
                current_user=current_user,
                db=db,
                classification=classification,
                department=department,
                background_tasks=background_tasks,
            )
        )
    return results


@router.get("/{document_id}/download")
async def download_document(
    document_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    document = await _get_accessible_document(document_id, current_user, db)
    if not document.file_path:
        raise HTTPException(status_code=404, detail="Stored file not found.")
    if is_object_storage_path(document.file_path):
        try:
            body = await asyncio.to_thread(open_document_object, document.file_path)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail="Stored file not found.") from exc

        async def stream_file():
            try:
                while chunk := await asyncio.to_thread(body.read, 64 * 1024):
                    yield chunk
            finally:
                await asyncio.to_thread(body.close)

        return StreamingResponse(
            stream_file(),
            media_type=document.mime_type or "application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.original_filename)}"
            },
        )
    if not FilePath(document.file_path).exists():
        raise HTTPException(status_code=404, detail="Stored file not found.")
    return FileResponse(
        path=document.file_path,
        media_type=document.mime_type or "application/pdf",
        filename=document.original_filename,
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    classification: str | None = Query(None),
    department: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    is_admin = str(current_user.role).upper() in {"ADMIN", "SUPER_ADMIN"}
    allowed = None if is_admin else await get_allowed_document_ids_for_user(current_user, db)
    documents, total = await DocumentRepository(db).get_many(
        owner_id=None if is_admin else current_user.id,
        status=status_filter,
        classification=classification,
        department=department,
        allowed_ids=allowed,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return DocumentListResponse(
        documents=[_to_response(document) for document in documents],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{document_id}", response_model=DocumentStatusResponse)
async def get_document(
    document_id: str = Path(...),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    return _to_response(await _get_accessible_document(document_id, current_user, db))


@router.patch("/{document_id}", response_model=DocumentStatusResponse)
async def update_document(
    body: DocumentMetadataUpdate,
    document_id: str = Path(...),
    current_user: User = Depends(require_admin),
    db=Depends(get_db),
):
    document = await DocumentRepository(db).get_by_id(document_id)
    if document is None or document.status == "deleted":
        raise HTTPException(status_code=404, detail="Document not found.")
    updated = await DocumentRepository(db).update_metadata(
        document_id,
        classification=body.classification,
        department=body.department,
        description=body.description,
    )
    return _to_response(updated)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str = Path(...),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    document = await DocumentRepository(db).get_by_id(document_id)
    if document is None or document.status == "deleted":
        raise HTTPException(status_code=404, detail="Document not found.")
    assert_owner_or_admin(document.owner_id, current_user)
    await DocumentRepository(db).soft_delete(document_id)
    await AuditLogRepository(db).log(
        action="document_deleted", user_id=current_user.id,
        resource_type="document", resource_id=document_id,
    )
    if background_tasks:
        background_tasks.add_task(remove_document_from_index, document_id)
        background_tasks.add_task(delete_document_file, document.file_path)
    else:
        await asyncio.to_thread(delete_document_file, document.file_path)
        await remove_document_from_index(document_id)
    return None


@router.post("/{document_id}/reindex", status_code=status.HTTP_202_ACCEPTED)
async def reindex_document(
    document_id: str = Path(...),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    document = await DocumentRepository(db).get_by_id(document_id)
    if document is None or document.status == "deleted":
        raise HTTPException(status_code=404, detail="Document not found.")
    assert_owner_or_admin(document.owner_id, current_user)
    await DocumentRepository(db).update_status(document_id, "pending")
    if background_tasks:
        background_tasks.add_task(enqueue_document_ingestion, document_id)
    await AuditLogRepository(db).log(
        action="document_reindexed", user_id=current_user.id,
        resource_type="document", resource_id=document_id,
    )
    return {"document_id": document_id, "status": "processing"}


@router.post("/{document_id}/permissions", status_code=status.HTTP_200_OK)
async def assign_permissions(
    body: DocumentPermissionAssign,
    document_id: str = Path(...),
    current_user: User = Depends(require_admin),
    db=Depends(get_db),
):
    document = await DocumentRepository(db).get_by_id(document_id)
    if document is None or document.status == "deleted":
        raise HTTPException(status_code=404, detail="Document not found.")
    repo = DocumentRepository(db)
    grants = 0
    for user_id in body.user_ids or []:
        await repo.grant_permission(document_id, user_id=user_id, granted_by=current_user.id)
        grants += 1
    for role in body.roles or []:
        if role not in {"STUDENT", "EMPLOYEE", "ADMIN", "SUPER_ADMIN"}:
            raise HTTPException(status_code=422, detail=f"Invalid role: {role}")
        await repo.grant_permission(document_id, role=role, granted_by=current_user.id)
        grants += 1
    if body.department:
        await repo.grant_permission(document_id, department=body.department, granted_by=current_user.id)
        grants += 1
    await AuditLogRepository(db).log(
        action="document_permission_granted", user_id=current_user.id,
        resource_type="document", resource_id=document_id,
        metadata={"grant_count": grants},
    )
    return {"document_id": document_id, "grants_created": grants}
