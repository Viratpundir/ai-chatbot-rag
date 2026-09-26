"""
app/schemas/documents.py
------------------------
Pydantic schemas for document management endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    """Returned immediately after upload — processing continues in background."""
    document_id: str
    filename: str
    status: str        # "uploaded" | "processing" | "ready" | "failed"
    message: str


class MultiDocumentUploadResponse(BaseModel):
    documents: List[DocumentUploadResponse]


class DocumentStatusResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    owner_id: Optional[str] = None
    file_size: Optional[int] = None
    classification: str
    department: Optional[str] = None
    version: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    chunk_count: Optional[int] = None
    page_count: Optional[int] = None
    error_message: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DocumentMetadataUpdate(BaseModel):
    classification: Optional[str] = None    # PUBLIC|INTERNAL|CONFIDENTIAL|RESTRICTED
    department: Optional[str] = None
    description: Optional[str] = None


class DocumentPermissionAssign(BaseModel):
    """Assign access to a document for specific users or roles."""
    user_ids: Optional[List[str]] = None
    roles: Optional[List[str]] = None
    department: Optional[str] = None


class DocumentListResponse(BaseModel):
    documents: List[DocumentStatusResponse]
    total: int
    page: int
    page_size: int


class DocumentSearchResult(BaseModel):
    document_id: str
    filename: str
    classification: str
    excerpt: str
    score: float
