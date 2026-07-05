"""
Authentication middleware for FastAPI.
Provides request authentication and authorization.
"""
from typing import Optional, Dict, Any

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

from src.loggers import Logger
from src.database.async_database import get_async_db
from src.auth.async_authentication import AsyncAuthenticationService

logger = Logger(__name__).get_logger()


async def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Extract and validate current user from request.

    Args:
        request: FastAPI request object

    Returns:
        User data dict or None if not authenticated
    """
    try:
        # Get session token from Authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return None

        if not auth_header.startswith("Bearer "):
            return None

        session_token = auth_header.replace("Bearer ", "")

        if not session_token:
            return None

        # Get async database session
        async for db in get_async_db():
            auth_service = AsyncAuthenticationService(db)
            user = await auth_service.get_current_user(session_token)
            return user

    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        return None

    return None


async def auth_required(request: Request) -> Dict[str, Any]:
    """
    Require authentication for request.

    Args:
        request: FastAPI request object

    Returns:
        User data dict

    Raises:
        HTTPException: If user is not authenticated
    """
    user = await get_current_user(request)

    if not user:
        logger.warning(
            f"Unauthorized access attempt",
            extra={
                "path": request.url.path,
                "method": request.method,
                "client_ip": request.client.host if request.client else None
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return user


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware for adding user context to requests.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process request and add user context.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response with user context
        """
        # Skip auth for public endpoints
        public_paths = ["/", "/health", "/docs", "/openapi.json", "/redoc"]
        if request.url.path in public_paths or request.url.path.startswith("/api/v1/auth"):
            return await call_next(request)

        # Get current user and add to request state
        user = await get_current_user(request)
        request.state.user = user
        request.state.is_authenticated = user is not None

        response = await call_next(request)
        return response


def get_user_from_request(request: Request) -> Optional[Dict[str, Any]]:
    """
    Get user from request state (set by middleware).

    Args:
        request: FastAPI request object

    Returns:
        User data dict or None
    """
    return getattr(request.state, "user", None)


def is_authenticated(request: Request) -> bool:
    """
    Check if request is authenticated.

    Args:
        request: FastAPI request object

    Returns:
        True if authenticated
    """
    return getattr(request.state, "is_authenticated", False)
