"""
Async database connection and session management.

Provides an async SQLAlchemy engine and session factory for the auth database
(users, api_usage tables). The existing SQLite pipeline database remains
separate — this module handles only the auth-related tables.
"""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session and ensures cleanup.

    Usage:
        @app.get("/some-route")
        async def handler(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables defined in models.metadata.

    Called once at application startup to ensure the auth tables exist.
    Uses create_all which is idempotent — safe to call on every boot.
    """
    from models.user import Base  # noqa: F811

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
