"""
app/auth/permissions.py
-----------------------
Role-Based Access Control (RBAC) guards for FastAPI routes.

Usage
-----
    from app.auth.permissions import require_roles, RoleChecker

    # Declarative dependency (preferred — works with Swagger UI auth)
    @router.get("/admin/users", dependencies=[Depends(require_roles("ADMIN", "SUPER_ADMIN"))])
    async def list_users(...):
        ...

    # Or inject the checker and get the user in one step:
    @router.get("/admin/users")
    async def list_users(user: User = Depends(RoleChecker("ADMIN", "SUPER_ADMIN"))):
        ...

Role hierarchy
--------------
    SUPER_ADMIN > ADMIN > EMPLOYEE > STUDENT

SUPER_ADMIN has implicit access to everything ADMIN can do.
Use require_roles() to specify the MINIMUM role required.

Authorization is always enforced on the backend.
Frontend checks (hiding buttons, etc.) are supplementary only.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable, Optional, Set

from fastapi import Depends, HTTPException, status

from app.auth.jwt import get_current_user
from app.core.config import settings
from app.database.models import User

# ---------------------------------------------------------------------------
# Role hierarchy — higher index = more privilege
# ---------------------------------------------------------------------------
_ROLE_HIERARCHY: list[str] = ["STUDENT", "EMPLOYEE", "ADMIN", "SUPER_ADMIN"]
_ROLE_RANK: dict[str, int] = {r: i for i, r in enumerate(_ROLE_HIERARCHY)}


def _role_rank(role: str) -> int:
    return _ROLE_RANK.get(role, -1)


def has_minimum_role(user_role: str, minimum_role: str) -> bool:
    """Return True if *user_role* satisfies *minimum_role* or higher."""
    return _role_rank(user_role) >= _role_rank(minimum_role)


# ---------------------------------------------------------------------------
# Role checker class — usable as a FastAPI Depends()
# ---------------------------------------------------------------------------

class RoleChecker:
    """
    FastAPI dependency that validates the current user's role.

    Raises HTTP 403 if the user does not hold one of the allowed roles
    (or a role higher in the hierarchy than the minimum allowed role).

    Usage::

        @router.get("/", dependencies=[Depends(RoleChecker("ADMIN"))])
        async def endpoint(): ...

        # Or to also receive the user object:
        @router.get("/")
        async def endpoint(user: User = Depends(RoleChecker("ADMIN"))): ...
    """

    def __init__(self, *allowed_roles: str) -> None:
        self.allowed_roles: Set[str] = set(allowed_roles)
        # Determine the minimum rank from the provided roles
        self._min_rank = min(
            (_role_rank(r) for r in allowed_roles), default=999
        )

    async def __call__(
        self,
        current_user: User = Depends(get_current_user),
    ) -> User:
        user_rank = _role_rank(current_user.role)
        if user_rank < self._min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied. Required role: "
                    f"{' or '.join(sorted(self.allowed_roles, key=_role_rank, reverse=True))}. "
                    f"Your role: {current_user.role}."
                ),
            )
        return current_user


# ---------------------------------------------------------------------------
# Convenience factories
# ---------------------------------------------------------------------------

def require_roles(*roles: str) -> RoleChecker:
    """
    Return a RoleChecker dependency for use in route `dependencies=[...]`.

    The user needs to hold at least the MINIMUM rank among the listed roles
    (or any higher role).

    Example — allow ADMIN and SUPER_ADMIN::

        @router.get("/", dependencies=[Depends(require_roles("ADMIN", "SUPER_ADMIN"))])
    """
    return RoleChecker(*roles)


# Pre-built checkers for the most common patterns
require_super_admin = RoleChecker("SUPER_ADMIN")
require_admin       = RoleChecker("ADMIN", "SUPER_ADMIN")
require_employee    = RoleChecker("EMPLOYEE", "ADMIN", "SUPER_ADMIN")
require_any_role    = RoleChecker("STUDENT", "EMPLOYEE", "ADMIN", "SUPER_ADMIN")


# ---------------------------------------------------------------------------
# Document-level permission helper (used by chat + document routes)
# ---------------------------------------------------------------------------

async def get_allowed_document_ids_for_user(
    current_user: User,
    db,  # AsyncSession — typed loosely to avoid circular import
) -> set:
    """
    Resolve the set of document UUIDs the current user may read.

    Called in /chat/ask and /documents routes to enforce document-level
    access control BEFORE any content reaches the RAG pipeline.
    """
    from app.database.repositories import DocumentRepository  # lazy to avoid circular
    repo = DocumentRepository(db)
    return await repo.get_allowed_document_ids(
        user_id=current_user.id,
        role=current_user.role,
        department=current_user.department,
    )


def restrict_document_ids(
    allowed_document_ids: Set[str],
    selected_document_ids: Optional[Iterable[str]] = None,
    all_authorized: bool = True,
) -> Set[str]:
    """Return the subset of selected docs that remains within the user's allowed set.

    Behavior:
      - If all_authorized is True or no selection is supplied, the user's full
        allowed set is returned.
      - If a specific document list is supplied, only the intersection of that list
        and the authorized set is preserved.
      - Unauthorized document IDs are silently excluded before retrieval.
    """
    if all_authorized or not selected_document_ids:
        return set(allowed_document_ids)

    selected = {str(doc_id) for doc_id in selected_document_ids}
    if not selected:
        return set()

    return {doc_id for doc_id in selected if doc_id in allowed_document_ids}


def can_user_upload_documents(user: User) -> bool:
    """Return whether the user is allowed to upload documents based on role and config."""
    if user.role in {"ADMIN", "SUPER_ADMIN"}:
        return True
    if user.role == "EMPLOYEE" and settings.ALLOW_EMPLOYEE_UPLOAD:
        return True
    if user.role == "STUDENT" and settings.ALLOW_STUDENT_UPLOAD:
        return True
    return False


# ---------------------------------------------------------------------------
# Owner-or-admin check
# ---------------------------------------------------------------------------

def assert_owner_or_admin(resource_owner_id: str, current_user: User) -> None:
    """
    Raise HTTP 403 if *current_user* is neither the owner of the resource
    nor an ADMIN / SUPER_ADMIN.

    Used for operations like deleting a conversation or document.
    """
    if (
        current_user.id != resource_owner_id
        and _role_rank(current_user.role) < _role_rank("ADMIN")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )
