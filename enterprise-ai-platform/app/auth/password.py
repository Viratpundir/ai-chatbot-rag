"""
app/auth/password.py
--------------------
Registration, login, account-lockout, and password-reset service.

This module owns ALL password-related business logic.
API routes call these functions — they never touch the ORM directly.

Security rules enforced here
----------------------------
- Passwords are NEVER logged or returned in responses.
- Hash comparison always uses the constant-time passlib verifier.
- Domain restriction is checked before any user is created.
- Account lockout is applied after MAX_LOGIN_ATTEMPTS failures.
- Password-reset tokens are single-use URL-safe random bytes (not JWTs),
  stored as SHA-256 hashes so the plaintext is never persisted.
- Generic error messages are used for login to prevent user enumeration
  (do NOT reveal whether the email exists or the password was wrong).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import (
    hash_password,
    is_allowed_email_domain,
    is_valid_email_format,
    validate_password_strength,
    verify_password,
)
from app.database.models import User
from app.database.repositories import UserRepository

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# In-process reset-token store
# ---------------------------------------------------------------------------
# Stage 5+ will migrate this to Redis.  For now a module-level dict is
# sufficient for demo / dev — tokens survive restarts only as long as the
# process is running, which is acceptable for the test phase.
#
# Structure: { sha256(token) -> (user_id, expires_at) }
_reset_tokens: dict[str, tuple[str, datetime]] = {}

_RESET_TOKEN_TTL_MINUTES = 30


class AuthError(Exception):
    """Raised for auth business-logic failures (not HTTP errors)."""
    def __init__(self, message: str, code: str = "auth_error") -> None:
        super().__init__(message)
        self.code = code


# ===========================================================================
# Registration
# ===========================================================================

async def register_user(
    db: AsyncSession,
    *,
    name: str,
    email: str,
    password: str,
    role: str = "EMPLOYEE",
    department: Optional[str] = None,
) -> User:
    """
    Create a new user account.

    Validation order (fail-fast):
      1. Email format
      2. Email domain restriction
      3. Password strength
      4. Duplicate email check
      5. Hash password and persist

    Returns the created User ORM object.
    Raises AuthError on any validation failure.
    """
    # --- 1. Email format ---
    email = email.strip().lower()
    if not is_valid_email_format(email):
        raise AuthError("Invalid email address format.", "invalid_email")

    # --- 2. Domain restriction ---
    if not is_allowed_email_domain(email):
        allowed = settings.ALLOWED_EMAIL_DOMAINS or "(none configured)"
        raise AuthError(
            f"Registrations are restricted to: {allowed}",
            "domain_not_allowed",
        )

    # --- 3. Password strength ---
    errors = validate_password_strength(password)
    if errors:
        raise AuthError("; ".join(errors), "weak_password")

    # --- 4. Duplicate check ---
    repo = UserRepository(db)
    existing = await repo.get_by_email(email)
    if existing is not None:
        raise AuthError(
            "An account with this email already exists.",
            "email_taken",
        )

    # --- 5. Hash + persist ---
    pw_hash = hash_password(password)
    user = await repo.create(
        name=name,
        email=email,
        password_hash=pw_hash,
        role=role,
        department=department,
    )

    logger.info(
        "User registered",
        extra={"user_id": user.id, "role": role, "department": department},
    )
    return user


# ===========================================================================
# Login
# ===========================================================================

async def authenticate_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    ip_address: Optional[str] = None,
) -> User:
    """
    Verify email + password and return the User on success.

    Raises AuthError with a GENERIC message on any failure so that
    attackers cannot distinguish "wrong email" from "wrong password".
    Increments failed-login counter and enforces account lockout.
    """
    _GENERIC_ERROR = "Invalid email or password."
    email = email.strip().lower()
    repo = UserRepository(db)

    # Lookup — deliberately don't reveal whether email exists
    user = await repo.get_by_email(email)
    if user is None:
        logger.info("Login attempt for unknown email", extra={"ip": ip_address})
        raise AuthError(_GENERIC_ERROR, "invalid_credentials")

    # Active check
    if not user.is_active:
        logger.info("Login attempt for inactive account", extra={"user_id": user.id})
        raise AuthError(_GENERIC_ERROR, "invalid_credentials")

    # Lockout check
    if await repo.is_locked(user.id):
        logger.warning("Login attempt on locked account", extra={"user_id": user.id})
        raise AuthError(
            f"Account temporarily locked. Try again in "
            f"{settings.ACCOUNT_LOCKOUT_MINUTES} minutes.",
            "account_locked",
        )

    # Password verification
    if not user.password_hash or not verify_password(password, user.password_hash):
        count = await repo.record_login_failure(user.id)
        remaining = max(0, settings.MAX_LOGIN_ATTEMPTS - count)
        logger.warning(
            "Failed login",
            extra={"user_id": user.id, "attempts": count, "ip": ip_address},
        )
        if remaining == 0:
            raise AuthError(
                f"Account locked after too many failed attempts. "
                f"Try again in {settings.ACCOUNT_LOCKOUT_MINUTES} minutes.",
                "account_locked",
            )
        raise AuthError(_GENERIC_ERROR, "invalid_credentials")

    # Success
    await repo.record_login_success(user.id)
    logger.info("Login success", extra={"user_id": user.id, "ip": ip_address})
    return user


# ===========================================================================
# Password reset
# ===========================================================================

async def initiate_password_reset(
    db: AsyncSession,
    *,
    email: str,
) -> Optional[str]:
    """
    Generate and return a password-reset token if the account exists.

    ALWAYS returns a generic response to the caller — never reveal
    whether the email is registered (anti-enumeration).

    Returns the plaintext token (to be emailed) or None if no account found.
    The token hash is stored in _reset_tokens.
    """
    email = email.strip().lower()
    repo = UserRepository(db)
    user = await repo.get_by_email(email)

    if user is None or not user.is_active:
        # Log at debug so we don't leak info in production logs either
        logger.debug("Password reset for unknown/inactive email (suppressed)")
        return None

    # Generate a cryptographically secure token
    token = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_RESET_TOKEN_TTL_MINUTES)

    _reset_tokens[token_hash] = (user.id, expires_at)

    logger.info(
        "Password reset initiated",
        extra={"user_id": user.id},
        # NEVER log the token itself
    )
    return token


async def complete_password_reset(
    db: AsyncSession,
    *,
    token: str,
    new_password: str,
) -> User:
    """
    Validate the reset token and set a new password.

    Raises AuthError if token is invalid, expired, or already used.
    """
    # Password strength
    errors = validate_password_strength(new_password)
    if errors:
        raise AuthError("; ".join(errors), "weak_password")

    token_hash = _hash_reset_token(token)
    entry = _reset_tokens.get(token_hash)

    if entry is None:
        raise AuthError("Invalid or expired reset token.", "invalid_token")

    user_id, expires_at = entry
    if datetime.now(timezone.utc) > expires_at:
        del _reset_tokens[token_hash]
        raise AuthError("Reset token has expired. Please request a new one.", "token_expired")

    # Consume the token (single-use)
    del _reset_tokens[token_hash]

    repo = UserRepository(db)
    pw_hash = hash_password(new_password)
    user = await repo.update(user_id, password_hash=pw_hash)

    if user is None:
        raise AuthError("User not found.", "user_not_found")

    # Revoke all existing sessions so the old password can't be replayed
    from app.database.repositories import UserRepository as _UR
    await _UR(db).revoke_all_sessions(user_id)

    logger.info("Password reset completed", extra={"user_id": user_id})
    return user


# ===========================================================================
# Helpers
# ===========================================================================

def _hash_reset_token(token: str) -> str:
    """SHA-256 hash of the reset token for storage.  NEVER log the token."""
    return hashlib.sha256(token.encode()).hexdigest()
