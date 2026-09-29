"""
Usage tracking middleware for API requests.

Logs every authenticated request under /api/* to the api_usage table
with endpoint path and token count. Uses background tasks to avoid
blocking the response.
"""
from __future__ import annotations

import logging
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class UsageMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that tracks API usage per authenticated request.

    Reads the authenticated user_id from request.state (set by the auth
    dependency) and inserts a usage record after the response is returned.
    Only tracks routes under /api/*. Uses no blocking DB calls.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the usage tracking middleware.

        Args:
            app: The ASGI application to wrap.
        """
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request, then log usage asynchronously.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler in the chain.

        Returns:
            The response from the route handler.
        """
        response = await call_next(request)

        # Only track /api/* routes
        if not request.url.path.startswith("/api/"):
            return response

        # Read user_id set by the auth dependency
        user_id: uuid.UUID | None = getattr(request.state, "user_id", None)
        if user_id is None:
            return response

        # Read token count from response header (set by endpoints after LLM calls)
        tokens_used_str = response.headers.get("X-Tokens-Used", "0")
        try:
            tokens_used = int(tokens_used_str)
        except (ValueError, TypeError):
            tokens_used = 0

        endpoint = request.url.path

        # Fire-and-forget: insert usage record without blocking the response
        import asyncio
        asyncio.get_event_loop().create_task(
            _log_usage(user_id, endpoint, tokens_used)
        )

        return response


async def _log_usage(user_id: uuid.UUID, endpoint: str, tokens_used: int) -> None:
    """Insert an API usage record asynchronously.

    Errors are logged but never raised — usage tracking must not
    break the main request flow.

    Args:
        user_id: The authenticated user's UUID.
        endpoint: The API endpoint path that was called.
        tokens_used: Number of LLM tokens consumed.
    """
    try:
        from core.database import AsyncSessionLocal
        from models.user import ApiUsage

        async with AsyncSessionLocal() as db:
            record = ApiUsage(
                user_id=user_id,
                endpoint=endpoint,
                tokens_used=tokens_used,
            )
            db.add(record)
            await db.commit()
    except Exception:
        logger.warning(
            "Failed to log API usage for user %s on %s",
            user_id,
            endpoint,
            exc_info=True,
        )
