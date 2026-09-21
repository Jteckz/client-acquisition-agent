"""
Pydantic request/response models for authentication endpoints.

All auth-related schemas live here to keep route handlers clean
and ensure consistent API contract documentation.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


# ── Request models ─────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    """Body for POST /auth/register."""
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    """Body for POST /auth/login (JSON variant)."""
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Body for POST /auth/refresh."""
    refresh_token: str


# ── Response models ────────────────────────────────────────────────────

class RegisterResponse(BaseModel):
    """Response from POST /auth/register."""
    user_id: uuid.UUID
    email: str
    api_key: str
    plan: str
    access_token: str
    refresh_token: str


class LoginResponse(BaseModel):
    """Response from POST /auth/login."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    plan: str


class RefreshResponse(BaseModel):
    """Response from POST /auth/refresh."""
    access_token: str


class MeResponse(BaseModel):
    """Response from GET /auth/me."""
    user_id: uuid.UUID
    email: str
    plan: str
    api_key: str
    created_at: datetime


class RotateApiKeyResponse(BaseModel):
    """Response from POST /auth/rotate-api-key."""
    api_key: str


class CurrentUser(BaseModel):
    """Authenticated user context extracted from JWT or API key.

    Injected into route handlers via FastAPI dependency injection.
    """
    user_id: uuid.UUID
    email: str
    plan: str
