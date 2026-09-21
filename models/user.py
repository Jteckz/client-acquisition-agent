"""
SQLAlchemy async models for the users and api_usage tables.

Uses SQLAlchemy 2.0 Mapped syntax with UUID primary keys.
The users table stores credentials, plan, and API keys.
The api_usage table tracks per-request token consumption.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models in the auth system."""
    pass


class User(Base):
    """User account with credentials, plan tier, and API key.

    Attributes:
        id: UUID primary key, generated server-side.
        email: Unique email address used for login.
        hashed_password: Bcrypt-hashed password.
        api_key: Unique API key for programmatic access.
        plan: Subscription tier (free, pro, agency).
        is_active: Whether the account is active.
        created_at: Timestamp of account creation.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    api_key: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
    )
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default="free")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    api_usages: Mapped[list["ApiUsage"]] = relationship(
        "ApiUsage", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.email} plan={self.plan}>"


class ApiUsage(Base):
    """Per-request API usage record tracking endpoint calls and token consumption.

    Attributes:
        id: Auto-incrementing bigserial primary key.
        user_id: Foreign key to the users table.
        endpoint: The API endpoint path that was called.
        tokens_used: Number of LLM tokens consumed by the request.
        created_at: Timestamp of the request.
    """

    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship("User", back_populates="api_usages")

    def __repr__(self) -> str:
        return f"<ApiUsage user={self.user_id} endpoint={self.endpoint}>"
