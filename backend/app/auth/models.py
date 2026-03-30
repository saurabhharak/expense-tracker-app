"""SQLAlchemy models for users and refresh_tokens.

These map to the tables created in alembic/versions/001_users.py.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "expense_tracker"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=True)
    phone = Column(String(15), unique=True, nullable=True)
    google_id = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=False)
    avatar_url = Column(String(1024), nullable=True)
    preferences = Column(JSONB, nullable=False, server_default="""'{"currency": "INR", "fy_start_month": 4, "default_account_id": null, "screenshot_auto_confirm": false, "budget_alert_threshold": 80, "theme": "light"}'::jsonb""")
    is_active = Column(Boolean, nullable=False, server_default="true")
    email_verified = Column(Boolean, nullable=False, server_default="false")
    phone_verified = Column(Boolean, nullable=False, server_default="false")
    daily_api_cost_limit_paise = Column(Integer, nullable=False, server_default="500")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": "expense_tracker"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("expense_tracker.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash = Column(String(128), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    replaced_by = Column(
        UUID(as_uuid=True),
        ForeignKey("expense_tracker.refresh_tokens.id"),
        nullable=True,
    )
    user_agent = Column(String(512), nullable=True)
    ip_address = Column(INET, nullable=True)

    user = relationship("User", back_populates="refresh_tokens")
