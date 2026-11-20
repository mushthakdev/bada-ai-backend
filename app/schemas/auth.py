from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=150)
    phone: Optional[str] = Field(default=None, max_length=20)
    role: str = Field(default="advertiser", pattern="^(advertiser|agency)$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class OTPRequest(BaseModel):
    phone: str = Field(min_length=10, max_length=15)


class OTPVerifyRequest(BaseModel):
    phone: str
    otp: str = Field(min_length=4, max_length=8)


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    phone: Optional[str] = None
    role: str
    is_verified: bool
    onboarding_completed: bool
    preferred_language: str
    avatar_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    user: UserOut
    tokens: TokenResponse
