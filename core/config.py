"""
Centralized configuration for the Client Acquisition Agent auth system.

Loads all secrets and settings from environment variables using pydantic-settings.
Fails loudly at import time if required variables are missing.
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Required variables (no defaults — startup fails if missing):
        SECRET_KEY: Cryptographic key for JWT signing.
        DATABASE_URL: Async database connection string (e.g. postgresql+asyncpg://...).

    Optional variables with defaults:
        ALGORITHM: JWT signing algorithm.
        ACCESS_TOKEN_EXPIRE_MINUTES: Access token lifetime in minutes.
        REFRESH_TOKEN_EXPIRE_DAYS: Refresh token lifetime in days.
        CORS_ORIGINS: Comma-separated list of allowed CORS origins.
    """

    SECRET_KEY: str
    DATABASE_URL: str

    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance.

    Uses lru_cache so the env is read once at startup, not on every request.
    Raises SystemExit if required env vars are missing.
    """
    try:
        return Settings()
    except Exception as exc:
        print(
            f"FATAL: Failed to load settings from environment: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


settings = get_settings()
