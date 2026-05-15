from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from models.user import UserRole


class AuthSignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole


class AuthLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class AuthUserResponse(BaseModel):
    id: str
    full_name: str
    email: str
    role: UserRole
    vendor_id: str | None
    created_at: datetime


class AuthSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserResponse
