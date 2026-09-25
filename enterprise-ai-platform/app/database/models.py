"""
app/database/models.py
-----------------------
SQLAlchemy ORM models for the Enterprise AI Knowledge Platform.

Tables
------
  users                  Core user accounts
  roles                  Role definitions  (SUPER_ADMIN / ADMIN / EMPLOYEE / STUDENT)
  permissions            Fine-grained permission strings
  role_permissions       M2M: roles ↔ permissions
  user_roles             M2M: users ↔ roles  (a user can hold multiple roles)
  otp_codes              Time-limited, hashed OTP records
  sessions               Refresh-token sessions (for revocation)
  documents              Uploaded documents + processing state
  document_permissions   Per-document access grants (role / user / department)
  document_versions      Version history for documents
  conversations          Per-user conversation threads
  messages               Individual chat turns inside a conversation
  audit_logs             Immutable record of every significant action

Design notes
------------
- All PKs are UUID strings (server_default=gen_random_uuid() in Postgres).
- All timestamps are UTC, stored as TIMESTAMP WITH TIME ZONE.
- Soft-delete via is_active / status columns — rows are never hard-deleted
  in audit-sensitive tables.
- JSON columns store flexible metadata without requiring schema changes.
- Indexes cover every FK and every column used in WHERE clauses.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB as PostgreSQLJSONB, UUID as PostgreSQLUUID
from sqlalchemy.types import JSON, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class PortableUUID(TypeDecorator):
    impl = String
    cache_ok = True

    def __init__(self, as_uuid: bool = False, *args, **kwargs):
        self.as_uuid = as_uuid
        super().__init__(*args, **kwargs)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgreSQLUUID(as_uuid=False))
        return dialect.type_descriptor(String(36))


class PortableJSON(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgreSQLJSONB())
        return dialect.type_descriptor(JSON())


UUID = PortableUUID
JSONB = PortableJSON


# ---------------------------------------------------------------------------
# Enums  (stored as VARCHAR so they are readable in plain SQL)
# ---------------------------------------------------------------------------

class RoleEnum(str):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN       = "ADMIN"
    EMPLOYEE    = "EMPLOYEE"
    STUDENT     = "STUDENT"


ROLE_VALUES = ["SUPER_ADMIN", "ADMIN", "EMPLOYEE", "STUDENT"]

DOCUMENT_STATUS_VALUES = ["uploaded", "processing", "ready", "failed", "deleted"]

CLASSIFICATION_VALUES = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]

MESSAGE_ROLE_VALUES = ["user", "assistant", "system"]


# ===========================================================================
# USERS
# ===========================================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
    )
    name: Mapped[str]        = mapped_column(String(120), nullable=False)
    email: Mapped[str]       = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Role — denormalised for fast lookups (authoritative source is user_roles)
    role: Mapped[str] = mapped_column(
        Enum(*ROLE_VALUES, name="role_enum"),
        nullable=False,
        default="EMPLOYEE",
        server_default="EMPLOYEE",
        index=True,
    )

    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    is_active: Mapped[bool]    = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # Security counters
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=_now
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    otp_codes:    Mapped[List["OTPCode"]]    = relationship("OTPCode",    back_populates="user", cascade="all, delete-orphan")
    sessions:     Mapped[List["Session"]]    = relationship("Session",    back_populates="user", cascade="all, delete-orphan")
    documents:    Mapped[List["Document"]]   = relationship("Document",   back_populates="owner")
    conversations: Mapped[List["Conversation"]] = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    audit_logs:   Mapped[List["AuditLog"]]   = relationship("AuditLog",   back_populates="user")
    user_roles:   Mapped[List["UserRole"]]   = relationship(
        "UserRole",
        back_populates="user",
        foreign_keys="UserRole.user_id",
        cascade="all, delete-orphan",
    )
    doc_permissions: Mapped[List["DocumentPermission"]] = relationship(
        "DocumentPermission", back_populates="user", foreign_keys="DocumentPermission.user_id"
    )

    def __repr__(self) -> str:
        return f"<User {self.email} [{self.role}]>"


# ===========================================================================
# ROLES  &  PERMISSIONS
# ===========================================================================

class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str]          = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str]        = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())

    permissions: Mapped[List["RolePermission"]] = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    user_roles:  Mapped[List["UserRole"]]        = relationship("UserRole",       back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str]   = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)  # e.g. "document:upload"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    role_permissions: Mapped[List["RolePermission"]] = relationship("RolePermission", back_populates="permission")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[str]       = mapped_column(UUID(as_uuid=False), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)

    role:       Mapped["Role"]       = relationship("Role",       back_populates="permissions")
    permission: Mapped["Permission"] = relationship("Permission", back_populates="role_permissions")


class UserRole(Base):
    """
    M2M association between users and roles.

    The denormalised User.role column is the fast-path for RBAC checks.
    UserRole is the authoritative source and supports multi-role users
    (e.g., a user who is both ADMIN and EMPLOYEE in different departments).
    """
    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())
    granted_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="user_roles", foreign_keys=[user_id])
    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")


# ===========================================================================
# OTP CODES
# ===========================================================================

class OTPCode(Base):
    """
    Hashed OTP record.

    NEVER store the plaintext OTP — only the bcrypt hash.
    The plaintext is generated, emailed, and immediately discarded.
    """
    __tablename__ = "otp_codes"
    __table_args__ = (
        Index("ix_otp_codes_email_created", "email", "created_at"),
    )

    id: Mapped[str]          = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    email: Mapped[str]       = mapped_column(String(255), nullable=False, index=True)
    otp_hash: Mapped[str]    = mapped_column(String(255), nullable=False)   # bcrypt hash — never log
    purpose: Mapped[str]     = mapped_column(String(30), nullable=False, default="login")  # login | email_verify | password_reset
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int]    = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_used: Mapped[bool]    = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())

    user: Mapped[Optional["User"]] = relationship("User", back_populates="otp_codes")


# ===========================================================================
# SESSIONS  (refresh token store)
# ===========================================================================

class Session(Base):
    """
    Refresh token record.

    Storing refresh token JTI here allows individual sessions to be
    revoked (logout) without rotating the JWT secret.
    """
    __tablename__ = "sessions"

    id: Mapped[str]         = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str]    = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    jti: Mapped[str]        = mapped_column(String(64), nullable=False, unique=True, index=True)  # JWT ID from refresh token
    ip_address: Mapped[Optional[str]]  = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]]  = mapped_column(String(500), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="sessions")


# ===========================================================================
# DOCUMENTS
# ===========================================================================

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_owner_status", "owner_id", "status"),
        Index("ix_documents_department_classification", "department", "classification"),
    )

    id: Mapped[str]           = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    filename: Mapped[str]     = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str]    = mapped_column(String(1000), nullable=False)   # path on disk
    file_size: Mapped[int]    = mapped_column(Integer, nullable=False, default=0)
    file_type: Mapped[str]    = mapped_column(String(20), nullable=False)     # pdf | docx | txt | md | html
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    owner_id: Mapped[str]     = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)

    department: Mapped[Optional[str]]  = mapped_column(String(100), nullable=True, index=True)
    classification: Mapped[str] = mapped_column(
        Enum(*CLASSIFICATION_VALUES, name="classification_enum"),
        nullable=False,
        default="INTERNAL",
        server_default="INTERNAL",
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        Enum(*DOCUMENT_STATUS_VALUES, name="document_status_enum"),
        nullable=False,
        default="uploaded",
        server_default="uploaded",
        index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Ingestion metadata
    chunk_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    version: Mapped[int]       = mapped_column(Integer, nullable=False, default=1, server_default="1")
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # SHA-256
    processing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Flexible metadata (page count, word count, custom tags, etc.)
    doc_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime]          = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=_now)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    owner:       Mapped["User"]                    = relationship("User", back_populates="documents")
    permissions: Mapped[List["DocumentPermission"]] = relationship("DocumentPermission", back_populates="document", cascade="all, delete-orphan")
    versions:    Mapped[List["DocumentVersion"]]    = relationship("DocumentVersion",    back_populates="document", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Document {self.original_filename} [{self.status}]>"


# ---------------------------------------------------------------------------
# Document permissions
# ---------------------------------------------------------------------------

class DocumentPermission(Base):
    """
    Grant access to a document for a specific user, role, or department.

    At least one of user_id / role / department must be set.
    The RAG retriever calls a helper that resolves which document IDs
    a given user can access, then passes that set into HybridRetriever.
    """
    __tablename__ = "document_permissions"
    __table_args__ = (
        Index("ix_doc_perms_document_id", "document_id"),
        Index("ix_doc_perms_user_id",     "user_id"),
        Index("ix_doc_perms_role",         "role"),
        Index("ix_doc_perms_department",   "department"),
    )

    id: Mapped[str]          = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    # Grant target — at least one must be non-null
    user_id: Mapped[Optional[str]]    = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    role: Mapped[Optional[str]]       = mapped_column(Enum(*ROLE_VALUES, name="role_enum"), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    can_read: Mapped[bool]   = mapped_column(Boolean, nullable=False, default=True,  server_default="true")
    can_delete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    granted_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    granted_at: Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())

    document: Mapped["Document"] = relationship("Document", back_populates="permissions")
    user:     Mapped[Optional["User"]] = relationship("User", back_populates="doc_permissions", foreign_keys=[user_id])


# ---------------------------------------------------------------------------
# Document versions
# ---------------------------------------------------------------------------

class DocumentVersion(Base):
    """Track previous versions of a document for re-index / rollback."""
    __tablename__ = "document_versions"

    id: Mapped[str]           = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    document_id: Mapped[str]  = mapped_column(UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int]      = mapped_column(Integer, nullable=False)
    file_path: Mapped[str]    = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int]    = mapped_column(Integer, nullable=False)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())
    created_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="versions")


# ===========================================================================
# CONVERSATIONS  &  MESSAGES
# ===========================================================================

class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[str]       = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str]  = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str]    = mapped_column(String(200), nullable=False, default="New Conversation")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_at: Mapped[datetime]           = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=_now)

    user:     Mapped["User"]           = relationship("User",    back_populates="conversations")
    messages: Mapped[List["Message"]]  = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")

    def __repr__(self) -> str:
        return f"<Conversation {self.id[:8]} user={self.user_id[:8]}>"


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[str]               = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    conversation_id: Mapped[str]  = mapped_column(UUID(as_uuid=False), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str]             = mapped_column(
        Enum(*MESSAGE_ROLE_VALUES, name="message_role_enum"),
        nullable=False,
    )
    content: Mapped[str]          = mapped_column(Text, nullable=False)

    # RAG metadata — only set on assistant messages
    citations: Mapped[Optional[dict]]  = mapped_column(JSONB, nullable=True)   # list of citation objects
    retrieval_time_ms: Mapped[Optional[float]] = mapped_column(nullable=True)
    llm_time_ms:       Mapped[Optional[float]] = mapped_column(nullable=True)
    total_time_ms:     Mapped[Optional[float]] = mapped_column(nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    has_answer: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")


# ===========================================================================
# AUDIT LOGS
# ===========================================================================

# Actions that must always be logged
AUDIT_ACTIONS = [
    # Auth
    "user_registered", "user_login", "user_logout",
    "login_failed", "account_locked",
    "otp_requested", "otp_verified", "otp_failed",
    "password_reset_requested", "password_reset_completed",
    "email_verified",
    # Users
    "user_created", "user_updated", "user_deactivated", "user_role_changed",
    # Documents
    "document_uploaded", "document_deleted", "document_reindexed",
    "document_permission_granted", "document_permission_revoked",
    # RAG / Chat
    "rag_query",
    "agent_query",
    # Admin
    "admin_action",
    # System
    "system_event",
]


class AuditLog(Base):
    """
    Immutable audit trail.

    Rows are never updated or deleted.
    Use INSERT only.  No cascade deletes from user/document tables.
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_ts",         "user_id",       "timestamp"),
        Index("ix_audit_logs_action_ts",       "action",        "timestamp"),
        Index("ix_audit_logs_resource",        "resource_type", "resource_id"),
    )

    id: Mapped[str]                   = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]]    = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str]               = mapped_column(String(60), nullable=False, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)   # "document" | "user" | "session"
    resource_id: Mapped[Optional[str]]   = mapped_column(String(36), nullable=True)   # UUID of the affected resource
    timestamp: Mapped[datetime]          = mapped_column(DateTime(timezone=True), nullable=False, default=_now, server_default=func.now(), index=True)
    ip_address: Mapped[Optional[str]]    = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]]    = mapped_column(String(500), nullable=True)

    # Flexible payload — NEVER store passwords, OTPs, or API keys here
    # Store things like: document_name, old_role, new_role, query_length, etc.
    log_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Convenience FK — soft reference only (no ondelete cascade)
    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} user={self.user_id}>"
