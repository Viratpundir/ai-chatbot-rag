"""
app/core/security.py
--------------------
Shared, low-level security utilities.

Stages 3-5 will build on these primitives:
  - password hashing (bcrypt via passlib)
  - JWT encode / decode (python-jose)
  - OTP generation & hashing (secrets + bcrypt)
  - Email domain validation
  - File-type / MIME validation
  - Rate-limit helpers (token bucket, backed by Redis in Stage 5)

Everything here is deliberately free of FastAPI/Starlette imports so it
can be unit-tested in isolation and reused by workers.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Dependency: passlib[bcrypt]  (added to requirements.txt)
# ---------------------------------------------------------------------------
import bcrypt

# ---------------------------------------------------------------------------
# Dependency: python-jose[cryptography]  (added to requirements.txt)
# ---------------------------------------------------------------------------
from jose import JWTError, jwt

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
# bcrypt with work-factor 12.  Argon2id is the stronger choice for new
# systems, but bcrypt is better-supported in Python production stacks today.
# Switch to argon2 by replacing the scheme below once argon2-cffi stabilises.
_BCRYPT_ROUNDS = 12


def _bcrypt_bytes(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("Password must be no more than 72 UTF-8 bytes.")
    return encoded


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*.  Never log the return value."""
    return bcrypt.hashpw(
        _bcrypt_bytes(plain), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    ).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    try:
        return bcrypt.checkpw(_bcrypt_bytes(plain), hashed.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return False


def validate_password_strength(password: str) -> List[str]:
    """
    Validate password against policy.

    Returns a list of violation messages.  Empty list means password is valid.
    """
    errors: List[str] = []
    min_len = settings.PASSWORD_MIN_LENGTH

    if len(password) < min_len:
        errors.append(f"Password must be at least {min_len} characters long.")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        errors.append("Password must contain at least one digit.")
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>?/\\|`~]", password):
        errors.append("Password must contain at least one special character.")

    return errors


# ---------------------------------------------------------------------------
# OTP  (one-time passcodes)
# ---------------------------------------------------------------------------
_OTP_DIGITS = string.digits
_OTP_LENGTH = 6


def generate_otp() -> str:
    """
    Generate a cryptographically secure 6-digit OTP string.

    NEVER log this value.
    """
    return "".join(secrets.choice(_OTP_DIGITS) for _ in range(_OTP_LENGTH))


def hash_otp(otp: str) -> str:
    """
    Hash the OTP with bcrypt before database storage.

    We use bcrypt (not a fast hash like SHA-256) so brute-forcing the
    stored hash is expensive even if the DB is compromised.
    NEVER log *otp* itself.
    """
    return bcrypt.hashpw(
        _bcrypt_bytes(otp), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    ).decode("ascii")


def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """Return True if *plain_otp* matches *hashed_otp*."""
    return verify_password(plain_otp, hashed_otp)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
_ALGORITHM = settings.JWT_ALGORITHM
_SECRET = settings.JWT_SECRET_KEY


def create_access_token(
    subject: str,
    extra_claims: Optional[Dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject:      Usually the user's UUID string.
        extra_claims: Additional claims (role, department, etc.).
        expires_delta: Custom expiry; defaults to ACCESS_TOKEN_EXPIRE_MINUTES.
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": expire,
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def create_refresh_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT refresh token."""
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": expire,
        "type": "refresh",
        # jti makes each refresh token unique so they can be revoked individually
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and verify a JWT.

    Raises:
        JWTError: If the token is invalid, expired, or tampered.
    """
    return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])


# ---------------------------------------------------------------------------
# Email domain validation
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def is_valid_email_format(email: str) -> bool:
    """Return True if *email* passes basic RFC 5321 format check."""
    return bool(_EMAIL_RE.match(email))


def is_allowed_email_domain(email: str) -> bool:
    """
    Return True if the email's domain is in the allowed-domains list.

    If the list is empty (ALLOWED_EMAIL_DOMAINS not configured), all
    domains are permitted.
    """
    allowed = settings.allowed_email_domains_list
    if not allowed:
        return True
    domain = email.split("@")[-1].lower().strip()
    return domain in allowed


# ---------------------------------------------------------------------------
# File validation
# ---------------------------------------------------------------------------
# Map of allowed MIME types → extension
_ALLOWED_MIMES: Dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/html": "html",
    "text/x-markdown": "md",
}

_MAX_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


def validate_upload_file(
    filename: str,
    content_type: str,
    size_bytes: int,
) -> List[str]:
    """
    Validate a file upload.

    Returns a list of error messages.  Empty means the file is acceptable.
    """
    errors: List[str] = []
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    allowed_exts = settings.ALLOWED_EXTENSIONS
    if ext not in allowed_exts:
        errors.append(
            f"File type '.{ext}' is not allowed. "
            f"Allowed types: {', '.join(allowed_exts)}"
        )

    if content_type not in _ALLOWED_MIMES:
        errors.append(f"MIME type '{content_type}' is not permitted.")

    if size_bytes > _MAX_BYTES:
        errors.append(
            f"File size {size_bytes / 1024 / 1024:.1f} MB exceeds "
            f"the {settings.MAX_UPLOAD_SIZE_MB} MB limit."
        )

    return errors


# ---------------------------------------------------------------------------
# Secure random helpers
# ---------------------------------------------------------------------------
def generate_secure_token(nbytes: int = 32) -> str:
    """Return a URL-safe random token (for password-reset links, etc.)."""
    return secrets.token_urlsafe(nbytes)
