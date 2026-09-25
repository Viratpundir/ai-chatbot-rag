"""
app/schemas/users.py
--------------------
Pydantic schemas for user management endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    department: Optional[str] = None


class UserCreate(UserBase):
    """Used by admins to create a user with an assigned role."""
    role: str = "EMPLOYEE"
    password: Optional[str] = None   # if None, send OTP invite instead


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    department: Optional[str] = None
    is_active: Optional[bool] = None


class UserRoleUpdate(BaseModel):
    role: str


class UserResponse(UserBase):
    user_id: str
    role: str
    is_active: bool
    email_verified: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    page: int
    page_size: int
