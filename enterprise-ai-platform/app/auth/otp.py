"""
app/auth/otp.py
---------------
OTP service — all OTP business logic lives here.

Security contract
-----------------
1. OTP is 6 digits, generated with secrets.choice (CSPRNG).
2. Plaintext OTP is NEVER stored or logged — only a bcrypt hash is persisted.
3. Verification uses constant-time bcrypt comparison (passlib).
4. Each OTPCode row tracks: expires_at, attempts, is_used.
5. Resend rate limit: OTP_RESEND_COOLDOWN_SECONDS between sends per email.
6. Attempt limit: OTP_MAX_ATTEMPTS wrong guesses invalidate the OTP.
7. Generic error messages — never differentiate wrong code vs expired vs exhausted.

Flow: request_otp
-----------------
  check resend cooldown
  → lookup user (suppress if not found — anti-enum)
  → generate plaintext OTP  (CSPRNG)
  → bcrypt hash OTP
  → store OTPCode row (hash only)
  → send plaintext OTP by email
  → discard plaintext

Flow: verify_otp
----------------
  load latest unused unexpired OTPCode
  → increment attempt counter BEFORE comparing  (prevents oracle)
  → check attempt limit
  → check expiry
  → bcrypt verify (constant-time)
  → mark OTP used
  → mark email verified
  → record login success
  → return User
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.email import send_otp_email
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import generate_otp, hash_otp, verify_otp as _verify_hash
from app.database.models import User
from app.database.repositories import AuditLogRepository, UserRepository

logger = get_logger(__name__)

_GENERIC_ERR = (
    "Invalid or expired verification code. "
    "Please request a new one."
)


class OTPError(Exception):
    def __init__(self, message: str, code: str = "otp_error") -> None:
        super().__init__(message)
        self.code = code


# ===========================================================================
# Request OTP
# ===========================================================================

async def request_otp(
    db: AsyncSession,
    *,
    email: str,
    purpose: str = "login",
    ip_address: Optional[str] = None,
) -> None:
    """
    Generate, hash, store, and email a 6-digit OTP.

    Raises OTPError("resend_too_soon") if cooldown has not elapsed.
    Silently succeeds for unknown or inactive accounts (anti-enumeration).
    """
    email = email.strip().lower()
    repo  = UserRepository(db)
    audit = AuditLogRepository(db)

    # --- Resend rate limit ---
    recent = await repo.count_recent_otps(
        email, purpose, since_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS
    )
    if recent > 0:
        raise OTPError(
            f"Please wait {settings.OTP_RESEND_COOLDOWN_SECONDS} seconds "
            "before requesting a new code.",
            "resend_too_soon",
        )

    # --- User lookup (anti-enum: silently return if not found) ---
    user = await repo.get_by_email(email)
    user_id: Optional[str] = None
    to_name: Optional[str] = None

    if user is not None:
        if not user.is_active:
            logger.debug("OTP suppressed — inactive account")
            return
        user_id = user.id
        to_name = user.name
    elif purpose == "login":
        # Unknown email — return without sending (anti-enum)
        logger.debug("OTP suppressed — unknown email")
        return

    # --- Generate OTP (plaintext only in this scope) ---
    plaintext = generate_otp()       # 6-digit string, CSPRNG
    otp_hash  = hash_otp(plaintext)  # bcrypt — never log plaintext

    # --- Persist hash ---
    await repo.create_otp(
        email=email,
        otp_hash=otp_hash,
        purpose=purpose,
        user_id=user_id,
    )

    # --- Send email (only transmission of plaintext) ---
    await send_otp_email(
        to_email=email,
        otp=plaintext,
        purpose=purpose,
        to_name=to_name,
    )
    # plaintext goes out of scope here

    await audit.log(
        action="otp_requested",
        user_id=user_id,
        ip_address=ip_address,
        metadata={"purpose": purpose},
    )
    logger.info("OTP issued", extra={"user_id": user_id, "purpose": purpose})


# ===========================================================================
# Verify OTP
# ===========================================================================

async def verify_otp(
    db: AsyncSession,
    *,
    email: str,
    otp_input: str,
    purpose: str = "login",
    ip_address: Optional[str] = None,
) -> User:
    """
    Verify the OTP and return the authenticated User.

    Raises OTPError with a generic message on any failure.
    """
    email = email.strip().lower()
    repo  = UserRepository(db)
    audit = AuditLogRepository(db)

    # --- Load latest valid OTP record ---
    record = await repo.get_latest_otp(email, purpose)
    if record is None:
        await audit.log(action="otp_failed", ip_address=ip_address,
                        metadata={"reason": "no_valid_otp", "purpose": purpose})
        raise OTPError(_GENERIC_ERR, "invalid_otp")

    # --- Increment attempts BEFORE comparing (timing-oracle prevention) ---
    new_attempts = await repo.increment_otp_attempts(record.id)

    # --- Attempt limit ---
    if new_attempts > settings.OTP_MAX_ATTEMPTS:
        logger.warning("OTP attempt limit exceeded",
                       extra={"otp_id": record.id})
        await audit.log(action="otp_failed", user_id=record.user_id,
                        ip_address=ip_address,
                        metadata={"reason": "attempt_limit_exceeded"})
        raise OTPError(_GENERIC_ERR, "attempt_limit_exceeded")

    # --- Expiry (belt-and-suspenders — DB query already filters) ---
    if record.expires_at < datetime.now(timezone.utc):
        await audit.log(action="otp_failed", user_id=record.user_id,
                        ip_address=ip_address,
                        metadata={"reason": "expired"})
        raise OTPError(_GENERIC_ERR, "otp_expired")

    # --- Constant-time bcrypt comparison ---
    if not _verify_hash(otp_input, record.otp_hash):
        await audit.log(action="otp_failed", user_id=record.user_id,
                        ip_address=ip_address,
                        metadata={"reason": "wrong_code",
                                  "attempts": new_attempts})
        raise OTPError(_GENERIC_ERR, "invalid_otp")

    # --- Mark OTP used (single-use guarantee) ---
    await repo.mark_otp_used(record.id)

    # --- Load user ---
    user = await repo.get_by_email(email)
    if user is None or not user.is_active:
        raise OTPError("Account not found or deactivated.", "user_not_found")

    # Mark email verified on first successful OTP
    if not user.email_verified:
        await repo.mark_email_verified(user.id)

    await repo.record_login_success(user.id)

    await audit.log(action="otp_verified", user_id=user.id,
                    ip_address=ip_address,
                    metadata={"purpose": purpose})
    logger.info("OTP verified", extra={"user_id": user.id, "purpose": purpose})
    return user
