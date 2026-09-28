"""
app/auth/jwt.py
---------------
JWT token creation and FastAPI current-user dependency.

Token flow
----------
1. Login/OTP-verify  → create_access_token + create_refresh_token → return to client
2. Protected route   → client sends  Authorization: Bearer <access_token>
3. get_current_user  → decode token, load user from DB, return User
4. Logout            → revoke refresh token JTI in sessions table
5. Token refresh     → verify refresh token JTI not revoked → new access token

The access token is short-lived (default 30 min).
The refresh token is long-lived (default 7 days) and its JTI is
stored in the sessions table so it can be individually revoked.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger, user_id_var
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.database.database import get_db
from app.database.models import User
from app.database.repositories import UserRepository

logger = get_logger(__name__)

# Bearer scheme — auto_error=False so we can return a clean 401 ourselves
_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Token creation helpers
# ---------------------------------------------------------------------------

def make_token_pair(user: User) -> dict:
    """
    Create access + refresh token pair for a user.

    Returns a dict ready to feed into LoginResponse / OTPVerifyResponse.
    """
    extra = {
        "role":       user.role,
        "email":      user.email,
        "department": user.department,
    }
    access = create_access_token(subject=user.id, extra_claims=extra)
    refresh = create_refresh_token(subject=user.id)

    return {
        "access_token":  access,
        "refresh_token": refresh,
        "token_type":    "bearer",
        "expires_in":    settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def extract_jti(refresh_token: str) -> Optional[str]:
    """Decode a refresh token and return its jti claim, or None on error."""
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            return None
        return payload.get("jti")
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# FastAPI dependency: get current authenticated user
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Decode the Bearer token and return the authenticated User.

    Raises HTTP 401 on any failure:
      - Missing token
      - Malformed / expired token
      - User not found
      - Account deactivated
    """
    auth_started = time.perf_counter()
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = decode_token(token)
    except JWTError as exc:
        logger.warning("JWT decode failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    # Inject into logging context for this request
    user_id_var.set(user.id)
    request.state.auth_elapsed_ms = (time.perf_counter() - auth_started) * 1000

    return user


# ---------------------------------------------------------------------------
# Optional auth — returns None if no token provided (for public endpoints)
# ---------------------------------------------------------------------------

async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user but returns None instead of raising 401."""
    if credentials is None:
        return None
    try:
        return await get_current_user(request=request, credentials=credentials, db=db)
    except HTTPException:
        return None


# ---------------------------------------------------------------------------
# Refresh token handler
# ---------------------------------------------------------------------------

async def refresh_access_token(
    refresh_token: str,
    db: AsyncSession,
    ip_address: Optional[str] = None,
) -> dict:
    """
    Validate a refresh token and issue a new access token.

    Raises HTTPException 401 if token is invalid, expired, or revoked.
    """
    try:
        payload = decode_token(refresh_token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        ) from exc

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not a refresh token.",
        )

    jti = payload.get("jti")
    user_id = payload.get("sub")

    if not jti or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed refresh token.",
        )

    repo = UserRepository(db)
    session = await repo.get_session_by_jti(jti)

    if session is None or session.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked. Please log in again.",
        )

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at.astimezone(timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please log in again.",
        )

    user = await repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account deactivated.",
        )

    await repo.touch_session(jti)

    extra = {
        "role":       user.role,
        "email":      user.email,
        "department": user.department,
    }
    new_access = create_access_token(subject=user.id, extra_claims=extra)

    return {
        "access_token": new_access,
        "token_type":   "bearer",
        "expires_in":   settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
