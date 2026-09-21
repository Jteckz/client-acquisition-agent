"""
Core authentication and authorization utilities.

Provides password hashing (bcrypt), JWT token creation/verification,
and FastAPI dependencies for protecting routes. Supports both Bearer
tokens (for browser users) and API keys (for programmatic clients).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db
from schemas.auth import CurrentUser

# ── Password hashing ──────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt.

    Args:
        plain: The raw password to hash.

    Returns:
        The bcrypt hash string.
    """
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        plain: The raw password to check.
        hashed: The stored bcrypt hash.

    Returns:
        True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT token creation ────────────────────────────────────────────────


def create_access_token(data: dict) -> str:
    """Create a short-lived JWT access token.

    Encodes user_id, email, plan, and expiration into the token payload.

    Args:
        data: Dictionary containing at minimum 'user_id', 'email', 'plan'.

    Returns:
        The encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Create a long-lived JWT refresh token.

    Encodes user_id, email, plan, and expiration into the token payload.

    Args:
        data: Dictionary containing at minimum 'user_id', 'email', 'plan'.

    Returns:
        The encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _decode_token(token: str, expected_type: str = "access") -> dict:
    """Decode and validate a JWT token.

    Args:
        token: The JWT string to decode.
        expected_type: Expected token type ('access' or 'refresh').

    Returns:
        The decoded payload dictionary.

    Raises:
        HTTPException: 401 if the token is invalid, expired, or wrong type.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    token_type = payload.get("type")
    if token_type != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Expected {expected_type} token, got {token_type}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# ── HTTP Bearer scheme ────────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


# ── FastAPI dependencies ──────────────────────────────────────────────


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """FastAPI dependency: extract and validate the authenticated user from a Bearer token.

    Decodes the JWT, looks up the user in the database to confirm is_active,
    and returns a CurrentUser model. Sets request.state.user_id for downstream
    middleware usage tracking.

    Raises:
        HTTP 401 on any failure (missing token, invalid token, inactive user).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _decode_token(credentials.credentials, expected_type="access")
    user_id_str = payload.get("user_id")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identification",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    from models.user import User  # noqa: F811

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.user_id = user.id

    return CurrentUser(user_id=user.id, email=user.email, plan=user.plan)


async def get_current_user_or_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """FastAPI dependency: authenticate via Bearer token OR X-API-Key header.

    Checks the Authorization header for a Bearer token first. If not present,
    falls back to the X-API-Key header and looks up the user by API key.
    Returns the same CurrentUser model either way.

    This allows both browser users (JWT) and programmatic clients (API key)
    to authenticate through a single dependency.

    Raises:
        HTTP 401 if neither method provides valid authentication.
    """
    # Try Bearer token first
    if credentials is not None:
        return await get_current_user(request, credentials, db)

    # Fall back to API key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        from models.user import User  # noqa: F811

        result = await db.execute(select(User).where(User.api_key == api_key))
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key or account is inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )

        request.state.user_id = user.id
        return CurrentUser(user_id=user.id, email=user.email, plan=user.plan)

    # Neither provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication. Provide a Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ── Plan enforcement ──────────────────────────────────────────────────

PLAN_HIERARCHY = {"free": 0, "pro": 1, "agency": 2}


def require_plan(min_plan: str) -> Callable:
    """Return a FastAPI dependency that enforces a minimum subscription plan.

    Args:
        min_plan: The minimum required plan level ('free', 'pro', or 'agency').

    Returns:
        A dependency function that raises HTTP 403 if the user's plan
        is below the required level.

    Raises:
        ValueError: If min_plan is not a valid plan name.
    """
    if min_plan not in PLAN_HIERARCHY:
        raise ValueError(f"Invalid plan level: {min_plan}. Must be one of: {list(PLAN_HIERARCHY.keys())}")

    min_level = PLAN_HIERARCHY[min_plan]

    async def _check_plan(
        user: CurrentUser = Depends(get_current_user_or_api_key),
    ) -> CurrentUser:
        user_level = PLAN_HIERARCHY.get(user.plan, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This endpoint requires the '{min_plan}' plan or higher. Your current plan is '{user.plan}'.",
            )
        return user

    return _check_plan
