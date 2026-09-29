"""
Authentication API routes.

Provides endpoints for user registration, login, token refresh,
profile retrieval, and API key rotation. All routes are under the
/auth prefix.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    verify_password,
)
from core.database import get_db
from models.user import User
from schemas.auth import (
    CurrentUser,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    RotateApiKeyResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account.

    Validates email format, hashes the password, and creates a new user.
    Returns tokens and API key on success.

    Raises:
        409: If the email is already registered.
        422: If the request body is invalid.
    """
    hashed = hash_password(req.password)
    import secrets
    api_key = secrets.token_hex(32)
    user = User(email=req.email, hashed_password=hashed, api_key=api_key)
    db.add(user)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc

    await db.refresh(user)

    token_data = {
        "user_id": str(user.id),
        "email": user.email,
        "plan": user.plan,
    }

    return RegisterResponse(
        user_id=user.id,
        email=user.email,
        api_key=user.api_key,
        plan=user.plan,
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate an existing user and return tokens.

    Verifies the email exists and password matches. Returns access
    and refresh tokens along with the user's plan.

    Raises:
        401: If the email is not found or password is incorrect.
    """
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = {
        "user_id": str(user.id),
        "email": user.email,
        "plan": user.plan,
    }

    return LoginResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        plan=user.plan,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Issue a new access token using a valid refresh token.

    Validates the refresh token, looks up the user, and returns
    a fresh access token.

    Raises:
        401: If the refresh token is invalid or the user no longer exists.
    """
    from auth.security import _decode_token

    payload = _decode_token(req.refresh_token, expected_type="refresh")
    user_id_str = payload.get("user_id")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing user identification",
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in refresh token",
        ) from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account is inactive",
        )

    token_data = {
        "user_id": str(user.id),
        "email": user.email,
        "plan": user.plan,
    }

    return RefreshResponse(access_token=create_access_token(token_data))


@router.get("/me", response_model=MeResponse)
async def get_me(user: CurrentUser = Depends(get_current_user)):
    """Return the authenticated user's profile.

    Protected endpoint — requires a valid Bearer token.
    """
    from core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user.user_id))
        db_user = result.scalar_one_or_none()
        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

    return MeResponse(
        user_id=db_user.id,
        email=db_user.email,
        plan=db_user.plan,
        api_key=db_user.api_key,
        created_at=db_user.created_at,
    )


@router.post("/rotate-api-key", response_model=RotateApiKeyResponse)
async def rotate_api_key(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new API key for the authenticated user.

    The old key is immediately invalidated. Protected endpoint —
    requires a valid Bearer token.
    """
    import secrets

    new_key = secrets.token_hex(32)
    result = await db.execute(select(User).where(User.id == user.user_id))
    db_user = result.scalar_one_or_none()
    if db_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    db_user.api_key = new_key
    await db.flush()

    return RotateApiKeyResponse(api_key=new_key)
