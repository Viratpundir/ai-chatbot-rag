"""
app/database/repositories.py
-----------------------------
Data-access layer (Repository pattern).

Every database interaction goes through a repository.
Routes and services NEVER build raw SQL or use the ORM directly —
they call a repository method.  This keeps the business logic decoupled
from SQLAlchemy and makes unit testing easy (swap the repo for a mock).

Repositories
------------
  UserRepository           CRUD + auth helpers for User / OTPCode / Session
  DocumentRepository       CRUD + permission resolution for Document
  ConversationRepository   CRUD for Conversation + Message
  AuditLogRepository       INSERT-only audit trail

Each repository is instantiated with an AsyncSession and is therefore
scoped to a single request (the FastAPI Depends(get_db) session).

Usage in a route::

    @router.post("/")
    async def create(db: AsyncSession = Depends(get_db)):
        repo = UserRepository(db)
        user = await repo.get_by_email("alice@company.com")
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.database.models import (
    AuditLog,
    Conversation,
    Document,
    DocumentPermission,
    Message,
    OTPCode,
    Session,
    User,
    UserRole,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ===========================================================================
# USER REPOSITORY
# ===========================================================================

class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Basic CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        name: str,
        email: str,
        password_hash: Optional[str] = None,
        role: str = "EMPLOYEE",
        department: Optional[str] = None,
    ) -> User:
        user = User(
            name=name,
            email=email.lower().strip(),
            password_hash=password_hash,
            role=role,
            department=department,
        )
        self.db.add(user)
        await self.db.flush()   # populate id without committing
        logger.info("User created", extra={"user_id": user.id, "role": role})
        return user

    async def get_by_id(self, user_id: str) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none()

    async def get_many(
        self,
        *,
        role: Optional[str] = None,
        department: Optional[str] = None,
        is_active: Optional[bool] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Tuple[List[User], int]:
        """Return (users, total_count) with optional filters."""
        q = select(User)
        if role:
            q = q.where(User.role == role)
        if department:
            q = q.where(User.department == department)
        if is_active is not None:
            q = q.where(User.is_active == is_active)

        total_result = await self.db.execute(
            select(func.count()).select_from(q.subquery())
        )
        total = total_result.scalar_one()

        users_result = await self.db.execute(
            q.order_by(User.created_at.desc()).offset(offset).limit(limit)
        )
        return users_result.scalars().all(), total

    async def update(self, user_id: str, **fields) -> Optional[User]:
        """Update arbitrary fields on a user row."""
        fields["updated_at"] = _utcnow()
        await self.db.execute(
            update(User).where(User.id == user_id).values(**fields)
        )
        return await self.get_by_id(user_id)

    async def deactivate(self, user_id: str) -> None:
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_active=False, updated_at=_utcnow())
        )

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    async def record_login_success(self, user_id: str) -> None:
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                last_login=_utcnow(),
                failed_login_attempts=0,
                locked_until=None,
                updated_at=_utcnow(),
            )
        )

    async def record_login_failure(self, user_id: str) -> int:
        """
        Increment failed_login_attempts.
        If threshold reached, set locked_until.
        Returns the new attempt count.
        """
        user = await self.get_by_id(user_id)
        if user is None:
            return 0
        new_count = (user.failed_login_attempts or 0) + 1
        values: Dict[str, Any] = {
            "failed_login_attempts": new_count,
            "updated_at": _utcnow(),
        }
        if new_count >= settings.MAX_LOGIN_ATTEMPTS:
            values["locked_until"] = _utcnow() + timedelta(
                minutes=settings.ACCOUNT_LOCKOUT_MINUTES
            )
        await self.db.execute(update(User).where(User.id == user_id).values(**values))
        return new_count

    async def is_locked(self, user_id: str) -> bool:
        user = await self.get_by_id(user_id)
        if user is None or user.locked_until is None:
            return False
        return user.locked_until > _utcnow()

    async def mark_email_verified(self, user_id: str) -> None:
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(email_verified=True, updated_at=_utcnow())
        )

    # ------------------------------------------------------------------
    # OTP management
    # ------------------------------------------------------------------

    async def create_otp(
        self,
        *,
        email: str,
        otp_hash: str,
        purpose: str = "login",
        user_id: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> OTPCode:
        """
        Store a hashed OTP.  The plaintext must NEVER be passed here.
        """
        ttl = ttl_seconds or settings.OTP_EXPIRE_SECONDS
        otp = OTPCode(
            user_id=user_id,
            email=email.lower().strip(),
            otp_hash=otp_hash,
            purpose=purpose,
            expires_at=_utcnow() + timedelta(seconds=ttl),
        )
        self.db.add(otp)
        await self.db.flush()
        return otp

    async def get_latest_otp(
        self, email: str, purpose: str = "login"
    ) -> Optional[OTPCode]:
        """Return the most recent unused, unexpired OTP for the email."""
        result = await self.db.execute(
            select(OTPCode)
            .where(
                and_(
                    OTPCode.email == email.lower().strip(),
                    OTPCode.purpose == purpose,
                    OTPCode.is_used == False,           # noqa: E712
                    OTPCode.expires_at > _utcnow(),
                )
            )
            .order_by(OTPCode.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def increment_otp_attempts(self, otp_id: str) -> int:
        otp = await self.db.get(OTPCode, otp_id)
        if otp is None:
            return 0
        otp.attempts += 1
        await self.db.flush()
        return otp.attempts

    async def mark_otp_used(self, otp_id: str) -> None:
        await self.db.execute(
            update(OTPCode).where(OTPCode.id == otp_id).values(is_used=True)
        )

    async def count_recent_otps(
        self, email: str, purpose: str, since_seconds: int
    ) -> int:
        """Count OTPs sent in the last *since_seconds* for rate limiting."""
        since = _utcnow() - timedelta(seconds=since_seconds)
        result = await self.db.execute(
            select(func.count()).where(
                and_(
                    OTPCode.email == email.lower().strip(),
                    OTPCode.purpose == purpose,
                    OTPCode.created_at > since,
                )
            )
        )
        return result.scalar_one()

    # ------------------------------------------------------------------
    # Session (refresh token) management
    # ------------------------------------------------------------------

    async def create_session(
        self,
        *,
        user_id: str,
        jti: str,
        expires_at: datetime,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Session:
        session = Session(
            user_id=user_id,
            jti=jti,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def get_session_by_jti(self, jti: str) -> Optional[Session]:
        result = await self.db.execute(
            select(Session).where(Session.jti == jti)
        )
        return result.scalar_one_or_none()

    async def revoke_session(self, jti: str) -> None:
        await self.db.execute(
            update(Session).where(Session.jti == jti).values(is_revoked=True)
        )

    async def revoke_all_sessions(self, user_id: str) -> None:
        """Revoke all sessions for a user (e.g., on password change)."""
        await self.db.execute(
            update(Session)
            .where(and_(Session.user_id == user_id, Session.is_revoked == False))  # noqa: E712
            .values(is_revoked=True)
        )

    async def touch_session(self, jti: str) -> None:
        """Update last_used_at timestamp."""
        await self.db.execute(
            update(Session)
            .where(Session.jti == jti)
            .values(last_used_at=_utcnow())
        )


# ===========================================================================
# DOCUMENT REPOSITORY
# ===========================================================================

class DocumentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        filename: str,
        original_filename: str,
        file_path: str,
        file_size: int,
        file_type: str,
        owner_id: str,
        mime_type: Optional[str] = None,
        department: Optional[str] = None,
        classification: str = "INTERNAL",
        description: Optional[str] = None,
        checksum: Optional[str] = None,
    ) -> Document:
        doc = Document(
            filename=filename,
            original_filename=original_filename,
            file_path=file_path,
            file_size=file_size,
            file_type=file_type,
            mime_type=mime_type,
            owner_id=owner_id,
            department=department,
            classification=classification,
            description=description,
            checksum=checksum,
            status="uploaded",
        )
        self.db.add(doc)
        await self.db.flush()
        logger.info("Document created", extra={"document_id": doc.id, "source_filename": original_filename})
        return doc

    async def get_by_id(self, document_id: str) -> Optional[Document]:
        result = await self.db.execute(
            select(Document)
            .where(Document.id == document_id)
            .options(selectinload(Document.permissions))
        )
        return result.scalar_one_or_none()

    async def get_many(
        self,
        *,
        owner_id: Optional[str] = None,
        status: Optional[str] = None,
        classification: Optional[str] = None,
        department: Optional[str] = None,
        allowed_ids: Optional[Set[str]] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Document], int]:
        q = select(Document).where(Document.status != "deleted")
        if owner_id:
            q = q.where(Document.owner_id == owner_id)
        if status:
            q = q.where(Document.status == status)
        if classification:
            q = q.where(Document.classification == classification)
        if department:
            q = q.where(Document.department == department)
        if allowed_ids is not None:
            q = q.where(Document.id.in_(allowed_ids))

        count_result = await self.db.execute(
            select(func.count()).select_from(q.subquery())
        )
        total = count_result.scalar_one()

        docs_result = await self.db.execute(
            q.order_by(Document.created_at.desc()).offset(offset).limit(limit)
        )
        return docs_result.scalars().all(), total

    async def update_status(
        self,
        document_id: str,
        status: str,
        error_message: Optional[str] = None,
        chunk_count: Optional[int] = None,
        doc_metadata: Optional[dict] = None,
    ) -> None:
        status = {"pending": "uploaded", "completed": "ready"}.get(status, status)
        values: Dict[str, Any] = {
            "status": status,
            "updated_at": _utcnow(),
        }
        if status in {"uploaded", "processing", "ready"}:
            values["error_message"] = None
        elif error_message is not None:
            values["error_message"] = error_message
        if chunk_count is not None:
            values["chunk_count"] = chunk_count
        if doc_metadata is not None:
            values["doc_metadata"] = doc_metadata
        if status == "processing":
            values["processing_started_at"] = _utcnow()
            values["processing_completed_at"] = None
        if status in {"ready", "failed"}:
            values["processing_completed_at"] = _utcnow()
        if status == "ready":
            values["indexed_at"] = _utcnow()
        await self.db.execute(
            update(Document).where(Document.id == document_id).values(**values)
        )

    async def update_metadata(
        self,
        document_id: str,
        *,
        classification: Optional[str] = None,
        department: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Document]:
        values: Dict[str, Any] = {"updated_at": _utcnow()}
        if classification:
            values["classification"] = classification
        if department is not None:
            values["department"] = department
        if description is not None:
            values["description"] = description
        await self.db.execute(
            update(Document).where(Document.id == document_id).values(**values)
        )
        return await self.get_by_id(document_id)

    async def soft_delete(self, document_id: str) -> None:
        await self.db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status="deleted", updated_at=_utcnow())
        )

    # ------------------------------------------------------------------
    # Permission resolution
    # ------------------------------------------------------------------

    async def get_allowed_document_ids(
        self,
        *,
        user_id: str,
        role: str,
        department: Optional[str],
    ) -> Set[str]:
        """
        Return the set of document IDs this user is authorised to read.

        A document is accessible if ANY of the following is true:
          1. A DocumentPermission row grants access to this user_id directly.
          2. A DocumentPermission row grants access to this role.
          3. A DocumentPermission row grants access to this department.
          4. The document classification is PUBLIC (everyone can read).
          5. The user owns the document.

        This set is passed directly to HybridRetriever — the LLM NEVER
        receives context from documents outside this set.
        """
        if role in {"ADMIN", "SUPER_ADMIN"}:
            result = await self.db.execute(
                select(Document.id).where(Document.status == "ready")
            )
            return {row[0] for row in result.all()}

        conditions = [
            # PUBLIC documents
            Document.classification == "PUBLIC",
            # User owns the document
            Document.owner_id == user_id,
        ]

        # Documents with explicit permission grants
        perm_subquery = (
            select(DocumentPermission.document_id)
            .where(
                and_(
                    DocumentPermission.can_read == True,  # noqa: E712
                    or_(
                        DocumentPermission.user_id == user_id,
                        DocumentPermission.role == role,
                        DocumentPermission.department == department
                        if department
                        else False,
                    ),
                )
            )
        ).scalar_subquery()

        conditions.append(Document.id.in_(perm_subquery))

        result = await self.db.execute(
            select(Document.id).where(
                and_(
                    Document.status == "ready",
                    or_(*conditions),
                )
            )
        )
        ids = {row[0] for row in result.all()}
        logger.debug(
            "Resolved allowed document IDs",
            extra={"user_id": user_id, "count": len(ids)},
        )
        return ids

    # ------------------------------------------------------------------
    # Permissions management
    # ------------------------------------------------------------------

    async def grant_permission(
        self,
        document_id: str,
        *,
        user_id: Optional[str] = None,
        role: Optional[str] = None,
        department: Optional[str] = None,
        granted_by: Optional[str] = None,
        can_read: bool = True,
        can_delete: bool = False,
    ) -> DocumentPermission:
        perm = DocumentPermission(
            document_id=document_id,
            user_id=user_id,
            role=role,
            department=department,
            granted_by=granted_by,
            can_read=can_read,
            can_delete=can_delete,
        )
        self.db.add(perm)
        await self.db.flush()
        return perm

    async def revoke_permission(self, permission_id: str) -> None:
        await self.db.execute(
            delete(DocumentPermission).where(DocumentPermission.id == permission_id)
        )

    async def get_document_stats(self) -> Dict[str, int]:
        """Return counts per status for the admin dashboard."""
        result = await self.db.execute(
            select(Document.status, func.count(Document.id))
            .where(Document.status != "deleted")
            .group_by(Document.status)
        )
        return {row[0]: row[1] for row in result.all()}


# ===========================================================================
# CONVERSATION REPOSITORY
# ===========================================================================

class ConversationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------

    async def create_conversation(
        self, *, user_id: str, title: str = "New Conversation"
    ) -> Conversation:
        conv = Conversation(user_id=user_id, title=title)
        self.db.add(conv)
        await self.db.flush()
        return conv

    async def get_conversation(
        self, conversation_id: str, user_id: str
    ) -> Optional[Conversation]:
        """Fetch a conversation — enforces ownership so users can't read each other's chats."""
        result = await self.db.execute(
            select(Conversation)
            .where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                    Conversation.is_active == True,  # noqa: E712
                )
            )
            .options(selectinload(Conversation.messages))
        )
        return result.scalar_one_or_none()

    async def list_conversations(
        self,
        user_id: str,
        offset: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Conversation], int]:
        q = select(Conversation).where(
            and_(
                Conversation.user_id == user_id,
                Conversation.is_active == True,  # noqa: E712
            )
        )
        count_result = await self.db.execute(
            select(func.count()).select_from(q.subquery())
        )
        total = count_result.scalar_one()

        convs_result = await self.db.execute(
            q.order_by(Conversation.updated_at.desc().nullsfirst())
            .offset(offset)
            .limit(limit)
        )
        return convs_result.scalars().all(), total

    async def rename_conversation(
        self, conversation_id: str, user_id: str, title: str
    ) -> Optional[Conversation]:
        await self.db.execute(
            update(Conversation)
            .where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            .values(title=title, updated_at=_utcnow())
        )
        return await self.get_conversation(conversation_id, user_id)

    async def delete_conversation(self, conversation_id: str, user_id: str) -> None:
        """Soft-delete — keeps the audit trail intact."""
        await self.db.execute(
            update(Conversation)
            .where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            .values(is_active=False, updated_at=_utcnow())
        )

    async def touch_conversation(self, conversation_id: str) -> None:
        """Update updated_at when a new message is added."""
        await self.db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=_utcnow())
        )

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def add_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        citations: Optional[List[Dict]] = None,
        retrieval_time_ms: Optional[float] = None,
        llm_time_ms: Optional[float] = None,
        total_time_ms: Optional[float] = None,
        model_used: Optional[str] = None,
        has_answer: Optional[bool] = None,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            citations=citations,
            retrieval_time_ms=retrieval_time_ms,
            llm_time_ms=llm_time_ms,
            total_time_ms=total_time_ms,
            model_used=model_used,
            has_answer=has_answer,
        )
        self.db.add(msg)
        await self.db.flush()
        await self.touch_conversation(conversation_id)
        return msg

    async def get_recent_messages(
        self, conversation_id: str, limit: int = 10
    ) -> List[Message]:
        """Return the last *limit* messages, oldest first (for LLM context)."""
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    def format_history(self, messages: List[Message]) -> str:
        """
        Serialise a message list to the plain-text format injected into RAG prompts.
        """
        if not messages:
            return "No previous conversation."
        lines = []
        for m in messages:
            speaker = "User" if m.role == "user" else "Assistant"
            lines.append(f"{speaker}: {m.content[:500]}")
        return "\n".join(lines)

    async def count_messages(self, conversation_id: str) -> int:
        result = await self.db.execute(
            select(func.count()).where(Message.conversation_id == conversation_id)
        )
        return result.scalar_one()


# ===========================================================================
# AUDIT LOG REPOSITORY
# ===========================================================================

class AuditLogRepository:
    """
    INSERT-only.  Rows are never updated or deleted.

    Design rule: never log passwords, OTPs, API keys, or sensitive document
    content.  The log_metadata dict should contain only diagnostic context
    (document_name, old_role, new_role, query_length, etc.).
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(
        self,
        *,
        action: str,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Write one audit log entry.

        This is fire-and-forget from the caller's perspective —
        exceptions are caught and logged so that an audit failure
        never breaks the user-facing operation.
        """
        try:
            entry = AuditLog(
                action=action,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                user_agent=user_agent,
                log_metadata=metadata,
            )
            self.db.add(entry)
            await self.db.flush()
            return entry
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to write audit log",
                extra={"action": action, "error": str(exc)},
            )
            # Return a detached stub so callers don't have to handle None
            return AuditLog(action=action, user_id=user_id)

    async def get_logs(
        self,
        *,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Tuple[List[AuditLog], int]:
        q = select(AuditLog)
        if user_id:
            q = q.where(AuditLog.user_id == user_id)
        if action:
            q = q.where(AuditLog.action == action)
        if resource_type:
            q = q.where(AuditLog.resource_type == resource_type)
        if date_from:
            q = q.where(AuditLog.timestamp >= date_from)
        if date_to:
            q = q.where(AuditLog.timestamp <= date_to)

        count_result = await self.db.execute(
            select(func.count()).select_from(q.subquery())
        )
        total = count_result.scalar_one()

        logs_result = await self.db.execute(
            q.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit)
        )
        return logs_result.scalars().all(), total

    async def get_recent_activity(self, limit: int = 20) -> List[AuditLog]:
        result = await self.db.execute(
            select(AuditLog)
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def count_by_action(
        self,
        action: str,
        since_minutes: int = 1440,
    ) -> int:
        since = _utcnow() - timedelta(minutes=since_minutes)
        result = await self.db.execute(
            select(func.count()).where(
                and_(
                    AuditLog.action == action,
                    AuditLog.timestamp >= since,
                )
            )
        )
        return result.scalar_one()
