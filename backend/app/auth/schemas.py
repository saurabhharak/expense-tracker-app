"""Pydantic schemas for auth requests and responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    id: UUID
    email: str | None = None
    phone: str | None = None
    full_name: str
    avatar_url: str | None = None
    is_active: bool
    email_verified: bool
    phone_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")
    user: UserResponse


class GoogleAuthURLResponse(BaseModel):
    authorization_url: str


class AuthErrorResponse(BaseModel):
    success: bool = False
    error: dict


class OtpRequestSchema(BaseModel):
    phone: str = Field(
        ...,
        pattern=r"^\+91\d{10}$",
        description="Indian phone in E.164 format: +91XXXXXXXXXX",
        examples=["+919876543210"],
    )


class OtpVerifySchema(BaseModel):
    phone: str = Field(
        ...,
        pattern=r"^\+91\d{10}$",
        description="Indian phone in E.164 format: +91XXXXXXXXXX",
        examples=["+919876543210"],
    )
    otp: str = Field(
        ...,
        pattern=r"^\d{6}$",
        description="6-digit OTP code",
        examples=["482901"],
    )


class OtpSentResponse(BaseModel):
    message: str = "OTP sent"
    expires_in: int = 300
