"""
app/schemas/auth.py
-------------------
Pydantic request / response schemas for authentication endpoints.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import validate_password_strength


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: Literal["EMPLOYEE", "STUDENT"] = "EMPLOYEE"

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        errors = validate_password_strength(v)
        if errors:
            raise ValueError("; ".join(errors))
        return v


class RegisterResponse(BaseModel):
    message: str
    user_id: str


# ---------------------------------------------------------------------------
# Login (password)
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int          # seconds


# ---------------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------------

class OTPRequestBody(BaseModel):
    email: EmailStr


class OTPRequestResponse(BaseModel):
    message: str
    # NOTE: never include the OTP value here


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class OTPVerifyResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        errors = validate_password_strength(v)
        if errors:
            raise ValueError("; ".join(errors))
        return v


class ResetPasswordResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Current user (GET /auth/me)
# ---------------------------------------------------------------------------

class CurrentUserResponse(BaseModel):
    user_id: str
    name: str
    email: str
    role: str
    department: Optional[str] = None
    is_active: bool
    email_verified: bool
