"""Authentication middleware for global route protection"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import get_db_connection
from app.services.auth import AuthService


def extract_token_from_header(header_value: str) -> str:
    """
    Extract JWT token from Authorization or X-Auth-Token header.
    Supports both formats:
    - "Bearer <token>" (with Bearer prefix)
    - "<token>" (without Bearer prefix)

    Returns the token string.
    Raises ValueError if format is invalid.
    """
    parts = header_value.split()

    # Format: "Bearer <token>"
    if len(parts) == 2 and parts[0].lower() in ("bearer", "basic"):
        return parts[1]

    # Format: "<token>" (no Bearer prefix)
    if len(parts) == 1:
        return parts[0]

    # Invalid format
    raise ValueError("Invalid token format")


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce authentication on all routes except /auth"""

    def __init__(self, app):
        super().__init__(app)
        self.auth_service = AuthService()
        # Paths that don't require authentication
        self.public_paths = {
            "/",  # Health check
            "/docs",  # OpenAPI docs
            "/redoc",  # ReDoc
            "/openapi.json",  # OpenAPI schema
        }

    async def dispatch(self, request: Request, call_next):
        """Check authentication for all requests except public paths"""
        # If authentication is disabled, allow all requests
        if not settings.require_auth:
            return await call_next(request)

        path = request.url.path

        # Allow public paths
        if path in self.public_paths:
            return await call_next(request)

        # Allow all /auth routes (login, refresh)
        if path.startswith("/auth"):
            return await call_next(request)

        # All other routes require authentication
        # Try Authorization header first, then X-Auth-Token
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            auth_header = request.headers.get("X-Auth-Token")

        if not auth_header:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing authentication credentials"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Extract token (supports both "Bearer <token>" and "<token>" formats)
        try:
            token = extract_token_from_header(auth_header)
        except ValueError:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid authentication credentials format"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Verify token and get inspector using unified connection dependency
        inspector = None
        try:
            async for conn in get_db_connection():
                inspector = await self.auth_service.get_current_inspector(conn, token)

                # If token is invalid but TRUST_INVALID_TOKENS is enabled, try to decode without validation
                if not inspector and settings.trust_invalid_tokens:
                    payload = self.auth_service.decode_token_without_validation(token)
                    if payload:
                        # Get inspector from database using the token's sub claim
                        from app.repositories.auth import AuthRepository

                        auth_repo = AuthRepository()
                        inspector_with_password = await auth_repo.get_inspector_by_id(conn, payload.sub)

                        if inspector_with_password:
                            # Use the inspector from database (trusting expired/revoked token)
                            from app.models.inspector import Inspector

                            inspector = Inspector(
                                id=inspector_with_password.id,
                                username=inspector_with_password.username,
                                full_name=inspector_with_password.full_name,
                                access_level=inspector_with_password.access_level,
                                is_deleted=False,
                                server_modified_at=inspector_with_password.server_modified_at,
                            )
                break
        except Exception as e:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": f"Database connection error: {str(e)}"},
            )

        if not inspector:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Store inspector in request state for access in route handlers if needed
        request.state.current_user = inspector

        # Continue with the request
        return await call_next(request)
