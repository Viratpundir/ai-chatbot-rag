"""
app/api/v1/auth.py
------------------
Authentication endpoints — Stages 3 + 4.

POST /api/v1/auth/register          Create account (email + password)
POST /api/v1/auth/login             Authenticate, receive JWT pair
POST /api/v1/auth/logout            Revoke refresh token / session
POST /api/v1/auth/refresh           Exchange refresh token for new access token
GET  /api/v1/auth/me                Return current user profile
POST /api/v1/auth/forgot-password   Request a reset link (anti-enumeration)
POST /api/v1/auth/reset-password    Set new password using reset token
POST /api/v1/auth/request-otp       Request a 6-digit email OTP  (Stage 4)
POST /api/v1/auth/verify-otp        Verify OTP, receive JWT pair  (Stage 4)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import (
    get_current_user,
    make_token_pair,
    refresh_access_token,
    extract_jti,
)
from app.auth.password import (
    AuthError,
    authenticate_user,
    complete_password_reset,
    initiate_password_reset,
    register_user,
)
from app.auth.otp import OTPError, request_otp as _request_otp, verify_otp as _verify_otp
from app.core.config import settings
from app.core.logging import get_logger
from app.database.database import get_db
from app.database.models import User
from app.database.repositories import AuditLogRepository, UserRepository
from app.schemas.auth import (
    CurrentUserResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    OTPRequestBody,
    OTPRequestResponse,
    OTPVerifyRequest,
    OTPVerifyResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _user_agent(request: Request) -> Optional[str]:
    return request.headers.get("User-Agent")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new user account with email + password.

    - Validates email format and domain restriction (ALLOWED_EMAIL_DOMAINS).
    - Enforces password strength policy.
    - Hashes password with bcrypt before storage.
    - Returns user_id — does NOT return a token (email verification required
      in Stage 4; for Stage 3 dev/demo the account is immediately usable).
    """
    try:
        user = await register_user(
            db,
            name=body.name,
            email=body.email,
            password=body.password,
            role=body.role,
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Audit
    audit = AuditLogRepository(db)
    await audit.log(
        action="user_registered",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=_client_ip(request),
        metadata={"email": user.email, "role": user.role},
    )

    return RegisterResponse(
        message="Account created successfully. You may now log in.",
        user_id=user.id,
    )


# ---------------------------------------------------------------------------
# Password login
# ---------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login with email and password",
)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with email + password.

    Returns a JWT access token (short-lived) and refresh token (long-lived).
    The refresh token JTI is stored in the sessions table for revocation support.

    Returns HTTP 401 with a GENERIC error on any auth failure to prevent
    user-enumeration attacks.
    """
    ip = _client_ip(request)
    ua = _user_agent(request)
    audit = AuditLogRepository(db)

    try:
        user = await authenticate_user(db, email=body.email, password=body.password, ip_address=ip)
    except AuthError as exc:
        # Log the failure before raising
        # Use get_by_email to find user_id for audit (safe — we only log id)
        repo = UserRepository(db)
        existing = await repo.get_by_email(body.email)
        await audit.log(
            action="login_failed",
            user_id=existing.id if existing else None,
            ip_address=ip,
            metadata={"reason": exc.code},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Create token pair
    tokens = make_token_pair(user)

    # Persist refresh token session
    from datetime import datetime, timedelta, timezone
    from app.core.security import decode_token
    refresh_payload = decode_token(tokens["refresh_token"])
    jti = refresh_payload.get("jti", "")
    expires_at = datetime.fromtimestamp(refresh_payload["exp"], tz=timezone.utc)

    repo = UserRepository(db)
    await repo.create_session(
        user_id=user.id,
        jti=jti,
        expires_at=expires_at,
        ip_address=ip,
        user_agent=ua,
    )

    await audit.log(
        action="user_login",
        user_id=user.id,
        ip_address=ip,
        metadata={"method": "password"},
    )

    return LoginResponse(**tokens)


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Refresh an access token",
)
async def refresh(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange a valid refresh token for a new access token.

    The refresh token JTI is validated against the sessions table to
    ensure it has not been revoked.
    """
    result = await refresh_access_token(
        body.refresh_token,
        db,
        ip_address=_client_ip(request),
    )
    return RefreshResponse(**result)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout and revoke session",
)
async def logout(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Revoke the refresh token so it can no longer be used.

    The client should discard both the access and refresh tokens.
    The access token remains technically valid until it naturally expires
    (TTL ~30 min) — this is acceptable for a stateless JWT scheme.
    For immediate invalidation, set ACCESS_TOKEN_EXPIRE_MINUTES=5 or
    implement an access-token blocklist in Stage 5.
    """
    jti = extract_jti(body.refresh_token)
    if jti:
        repo = UserRepository(db)
        await repo.revoke_session(jti)

    audit = AuditLogRepository(db)
    await audit.log(
        action="user_logout",
        user_id=current_user.id,
        ip_address=_client_ip(request),
    )
    return None


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Get current authenticated user",
)
async def me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return CurrentUserResponse(
        user_id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        role=current_user.role,
        department=current_user.department,
        is_active=current_user.is_active,
        email_verified=current_user.email_verified,
    )


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    summary="Request a password reset link",
)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Send a password-reset token to the registered email.

    ALWAYS returns HTTP 200 with the same generic message regardless of
    whether the email is registered — prevents user enumeration.

    Stage 4 will wire this to the SMTP email service.
    For Stage 3 the token is returned in the response body (dev/demo only).
    """
    try:
        token = await initiate_password_reset(db, email=body.email)
    except Exception:
        # DB unavailable or any other error — still return generic 200
        # so the endpoint never leaks whether an account exists.
        token = None

    try:
        audit = AuditLogRepository(db)
        await audit.log(
            action="password_reset_requested",
            ip_address=_client_ip(request),
            metadata={"email_domain": body.email.split("@")[-1]},
        )
    except Exception:
        pass  # audit failure must never break the anti-enum guarantee

    # Stage 3 dev mode: include token in response so it can be tested
    # without an email server.  Stage 4 will remove this and send email.
    if token and settings.DEBUG:
        return ForgotPasswordResponse(
            message=(
                "Reset link sent. "
                f"[DEV MODE — token: {token}]"
            )
        )

    return ForgotPasswordResponse(
        message=(
            "If an account with that email exists, "
            "a password reset link has been sent."
        )
    )


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    summary="Reset password using a reset token",
)
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Set a new password using the token from the reset email.

    The token is single-use and expires after 30 minutes.
    All existing sessions are revoked on success.
    """
    try:
        user = await complete_password_reset(
            db,
            token=body.token,
            new_password=body.new_password,
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    audit = AuditLogRepository(db)
    await audit.log(
        action="password_reset_completed",
        user_id=user.id,
        ip_address=_client_ip(request),
    )

    return ResetPasswordResponse(
        message="Password updated successfully. Please log in with your new password."
    )


# ---------------------------------------------------------------------------
# OTP endpoints — Stage 4 (fully implemented)
# ---------------------------------------------------------------------------

@router.post(
    "/request-otp",
    response_model=OTPRequestResponse,
    summary="Request a 6-digit email OTP",
)
async def request_otp_endpoint(
    body: OTPRequestBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate and email a 6-digit OTP to the given address.

    Security guarantees:
    - ALWAYS returns HTTP 200 with a generic message (anti-enumeration).
    - Rate-limited: one send per OTP_RESEND_COOLDOWN_SECONDS (default 60 s).
    - OTP is bcrypt-hashed before storage — plaintext never persisted.
    - OTP expires after OTP_EXPIRE_SECONDS (default 300 s / 5 minutes).
    - Returns HTTP 429 only for resend-too-soon (exposes no account info).

    In DEBUG mode with no SMTP configured the OTP is printed to server stdout.
    """
    ip = _client_ip(request)
    try:
        await _request_otp(db, email=body.email, purpose="login", ip_address=ip)
    except OTPError as exc:
        if exc.code == "resend_too_soon":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(exc),
            ) from exc
        # All other OTP errors → swallow, return generic 200 (anti-enum)
        logger.debug("OTP request suppressed", extra={"code": exc.code})
    except Exception as exc:  # noqa: BLE001
        # SMTP or DB failure → log, return generic 200 (anti-enum)
        logger.error("OTP request failed internally", extra={"error": str(exc)})

    return OTPRequestResponse(
        message=(
            "If an account with that email exists, "
            "a verification code has been sent."
        )
    )


@router.post(
    "/verify-otp",
    response_model=OTPVerifyResponse,
    summary="Verify an email OTP and receive a JWT session",
)
async def verify_otp_endpoint(
    body: OTPVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify the 6-digit OTP and return a JWT access + refresh token pair.

    Security checks (all return a generic 401):
    - OTP must not be expired (5-minute window).
    - OTP must not have been used already.
    - Attempt counter must not exceed OTP_MAX_ATTEMPTS (default 5).
    - OTP must match the stored bcrypt hash (constant-time comparison).

    On success:
    - OTP is marked as used (single-use).
    - Email is marked as verified.
    - Refresh token session is persisted for revocation support.
    """
    ip = _client_ip(request)
    ua = _user_agent(request)

    try:
        user = await _verify_otp(
            db,
            email=body.email,
            otp_input=body.otp,
            purpose="login",
            ip_address=ip,
        )
    except OTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Create JWT pair
    tokens = make_token_pair(user)

    # Persist refresh token session for revocation support
    from datetime import datetime, timezone  # noqa: PLC0415
    from app.core.security import decode_token  # noqa: PLC0415
    refresh_payload = decode_token(tokens["refresh_token"])
    jti        = refresh_payload.get("jti", "")
    expires_at = datetime.fromtimestamp(refresh_payload["exp"], tz=timezone.utc)

    repo = UserRepository(db)
    await repo.create_session(
        user_id=user.id,
        jti=jti,
        expires_at=expires_at,
        ip_address=ip,
        user_agent=ua,
    )

    return OTPVerifyResponse(**tokens)
