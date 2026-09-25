"""
app/api/v1/users.py
-------------------
User management endpoints — fully implemented in Stage 3.

All endpoints are protected by RBAC guards enforced on the backend.
Frontend checks are supplementary only — this layer is the authority.

GET    /api/v1/users              List users          (ADMIN+)
POST   /api/v1/users              Create user         (ADMIN+)
GET    /api/v1/users/{id}         Get user            (ADMIN+ or self)
PATCH  /api/v1/users/{id}         Update profile      (ADMIN+ or self for name/dept)
PATCH  /api/v1/users/{id}/role    Change role         (SUPER_ADMIN only)
DELETE /api/v1/users/{id}         Deactivate user     (ADMIN+, cannot deactivate self)
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.password import AuthError, register_user
from app.auth.permissions import (
    RoleChecker,
    assert_owner_or_admin,
    require_admin,
    require_super_admin,
)
from app.core.logging import get_logger
from app.database.database import get_db
from app.database.models import User
from app.database.repositories import AuditLogRepository, UserRepository
from app.schemas.users import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserRoleUpdate,
    UserUpdate,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_response(user: User) -> UserResponse:
    return UserResponse(
        user_id=user.id,
        name=user.name,
        email=user.email,
        department=user.department,
        role=user.role,
        is_active=user.is_active,
        email_verified=user.email_verified,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login=user.last_login,
    )


# ---------------------------------------------------------------------------
# List users
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=UserListResponse,
    summary="List users (ADMIN+)",
    dependencies=[Depends(require_admin)],
)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List users with optional filters.

    SUPER_ADMIN sees all users.
    ADMIN sees all users — role changes are restricted separately.
    """
    offset = (page - 1) * page_size
    repo = UserRepository(db)
    users, total = await repo.get_many(
        role=role,
        department=department,
        is_active=is_active,
        offset=offset,
        limit=page_size,
    )
    return UserListResponse(
        users=[_to_response(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# Create user (admin-initiated)
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user (ADMIN+)",
    dependencies=[Depends(require_admin)],
)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a user with an assigned role.

    Only SUPER_ADMIN can create ADMIN or SUPER_ADMIN accounts.
    ADMIN can create EMPLOYEE and STUDENT accounts.
    """
    # Role elevation guard
    from app.auth.permissions import _role_rank  # noqa: PLC0415
    if _role_rank(body.role) >= _role_rank("ADMIN") and current_user.role != "SUPER_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only SUPER_ADMIN can create ADMIN or SUPER_ADMIN accounts.",
        )

    # Use a placeholder password if none provided (OTP invite flow — Stage 4)
    import secrets as _secrets  # noqa: PLC0415
    password = body.password or _secrets.token_urlsafe(24)

    try:
        user = await register_user(
            db,
            name=body.name,
            email=body.email,
            password=password,
            role=body.role,
            department=body.department,
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    audit = AuditLogRepository(db)
    await audit.log(
        action="user_created",
        user_id=current_user.id,
        resource_type="user",
        resource_id=user.id,
        metadata={"created_email": user.email, "role": user.role},
    )
    return _to_response(user)


# ---------------------------------------------------------------------------
# Get single user
# ---------------------------------------------------------------------------

@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get a user by ID (ADMIN+ or self)",
)
async def get_user(
    user_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return a user's profile.

    Any authenticated user can fetch THEIR OWN profile.
    Fetching another user's profile requires ADMIN+.
    """
    # Allow self-access
    if user_id != current_user.id:
        assert_owner_or_admin(user_id, current_user)

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return _to_response(user)


# ---------------------------------------------------------------------------
# Update user
# ---------------------------------------------------------------------------

@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user profile (ADMIN+ or self for name/department)",
)
async def update_user(
    body: UserUpdate,
    user_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update name / department / is_active.

    Users can update their own name and department.
    Only ADMIN+ can change is_active.
    """
    from app.auth.permissions import _role_rank  # noqa: PLC0415

    if user_id != current_user.id:
        assert_owner_or_admin(user_id, current_user)

    # Non-admins cannot change is_active
    if body.is_active is not None and _role_rank(current_user.role) < _role_rank("ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only ADMIN+ can activate or deactivate accounts.",
        )

    repo = UserRepository(db)
    existing = await repo.get_by_id(user_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    update_fields = body.model_dump(exclude_none=True)
    user = await repo.update(user_id, **update_fields)

    audit = AuditLogRepository(db)
    await audit.log(
        action="user_updated",
        user_id=current_user.id,
        resource_type="user",
        resource_id=user_id,
        metadata={"fields_changed": list(update_fields.keys())},
    )
    return _to_response(user)


# ---------------------------------------------------------------------------
# Change role
# ---------------------------------------------------------------------------

@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Change user role (SUPER_ADMIN only)",
    dependencies=[Depends(require_super_admin)],
)
async def change_role(
    body: UserRoleUpdate,
    user_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Assign a new role to a user.

    Only SUPER_ADMIN can change roles.
    A user cannot change their own role.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own role.",
        )

    valid_roles = {"SUPER_ADMIN", "ADMIN", "EMPLOYEE", "STUDENT"}
    if body.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(valid_roles))}",
        )

    repo = UserRepository(db)
    existing = await repo.get_by_id(user_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    old_role = existing.role
    user = await repo.update(user_id, role=body.role)

    audit = AuditLogRepository(db)
    await audit.log(
        action="user_role_changed",
        user_id=current_user.id,
        resource_type="user",
        resource_id=user_id,
        metadata={"old_role": old_role, "new_role": body.role},
    )
    return _to_response(user)


# ---------------------------------------------------------------------------
# Deactivate user
# ---------------------------------------------------------------------------

@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate a user (ADMIN+)",
    dependencies=[Depends(require_admin)],
)
async def deactivate_user(
    user_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Soft-deactivate a user account.

    - Cannot deactivate your own account.
    - ADMIN cannot deactivate another ADMIN or SUPER_ADMIN.
    - All sessions for the user are revoked immediately.
    """
    from app.auth.permissions import _role_rank  # noqa: PLC0415

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )

    repo = UserRepository(db)
    target = await repo.get_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # ADMINs cannot deactivate other ADMINs or SUPER_ADMINs
    if (
        current_user.role == "ADMIN"
        and _role_rank(target.role) >= _role_rank("ADMIN")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ADMIN cannot deactivate ADMIN or SUPER_ADMIN accounts.",
        )

    await repo.deactivate(user_id)
    # Revoke all active sessions for the deactivated user
    await repo.revoke_all_sessions(user_id)

    audit = AuditLogRepository(db)
    await audit.log(
        action="user_deactivated",
        user_id=current_user.id,
        resource_type="user",
        resource_id=user_id,
        metadata={"deactivated_email": target.email, "deactivated_role": target.role},
    )
    return None
