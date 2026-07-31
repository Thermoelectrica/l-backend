"""Authentication dependencies for FastAPI"""

from datetime import datetime, timezone
from typing import Annotated, Optional

import asyncpg
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.database import get_db_connection
from app.models.auth import TokenPayload
from app.models.inspector import Inspector
from app.services.auth import AuthService

# Support both Authorization header and X-Auth-Token header
security = HTTPBearer(auto_error=False)
x_auth_token_header = APIKeyHeader(name="X-Auth-Token", auto_error=False)
auth_service = AuthService()


def extract_token_from_x_auth_header(x_auth_token: Optional[str]) -> Optional[str]:
    """
    Extract JWT token from X-Auth-Token header.
    Supports both formats:
    - "Bearer <token>" (with Bearer prefix)
    - "<token>" (without Bearer prefix)

    Returns the token string or None if invalid.
    """
    if not x_auth_token:
        return None

    # Try to parse as "Bearer <token>"
    parts = x_auth_token.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]

    # Otherwise, treat the entire value as the token
    return x_auth_token


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    x_auth_token: Annotated[Optional[str], Depends(x_auth_token_header)],
    conn: Annotated[asyncpg.Connection, Depends(get_db_connection)],
) -> Inspector:
    """
    Dependency to get current authenticated user from JWT token.

    Supports both Authorization: Bearer <token> and X-Auth-Token headers.
    X-Auth-Token can be in either format:
    - "Bearer <token>" (with Bearer prefix)
    - "<token>" (without Bearer prefix)

    When auth is disabled (require_auth=False):
    - If a valid token is provided, returns the authenticated user
    - If no token is provided, returns anonymous user (id=-1)

    When auth is enabled (require_auth=True):
    - Requires a valid token, raises 401 if missing or invalid

    Raises:
        HTTPException: 401 if token is invalid or user not found (when auth is enabled)
    """
    # Try to get token from either Authorization header or X-Auth-Token header
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = extract_token_from_x_auth_header(x_auth_token)

    # If token is provided, always try to validate it
    if token:
        # Verify and decode token
        inspector_with_password = await auth_service.get_current_inspector(conn, token)

        if inspector_with_password is None:
            # Token is invalid - check if we should trust it anyway
            if settings.trust_invalid_tokens:
                # TRUST_INVALID_TOKENS is enabled, try to decode without validation
                payload = auth_service.decode_token_without_validation(token)
                if payload:
                    # Get inspector from database using the token's sub claim
                    from app.repositories.auth import AuthRepository

                    auth_repo = AuthRepository()
                    inspector_with_password = await auth_repo.get_inspector_by_id(conn, payload.sub)

                    if inspector_with_password:
                        # Return the user from database (trusting expired/revoked token)
                        return Inspector(
                            id=inspector_with_password.id,
                            username=inspector_with_password.username,
                            full_name=inspector_with_password.full_name,
                            access_level=inspector_with_password.access_level,
                            is_deleted=False,
                            server_modified_at=inspector_with_password.server_modified_at,
                        )

            # Token is invalid and we're not trusting invalid tokens
            if settings.require_auth:
                # Auth is enabled, reject invalid token
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                # Auth is disabled, fall through to return anonymous user
                pass
        else:
            # Token is valid, return the authenticated user with access_level from database
            return Inspector(
                id=inspector_with_password.id,
                username=inspector_with_password.username,
                full_name=inspector_with_password.full_name,
                access_level=inspector_with_password.access_level,  # Use access_level from database
                is_deleted=False,  # Default value since it's not in the auth query
                server_modified_at=inspector_with_password.server_modified_at,
            )

    # No credentials provided or invalid token with auth disabled
    if settings.require_auth:
        # Auth is enabled, credentials are required
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Auth is disabled, return anonymous user
    return Inspector(
        id=-1,
        username="anonymous",
        full_name="Anonymous User",
        is_deleted=False,
        server_modified_at=datetime.now(timezone.utc),
    )


async def get_token_payload(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    x_auth_token: Annotated[Optional[str], Depends(x_auth_token_header)],
) -> TokenPayload:
    """
    Dependency to extract and validate token payload from JWT token.
    This provides access to both user_id (sub) and device_id (dev).

    Supports both Authorization: Bearer <token> and X-Auth-Token headers.
    X-Auth-Token can be in either format:
    - "Bearer <token>" (with Bearer prefix)
    - "<token>" (without Bearer prefix)

    When auth is disabled (require_auth=False):
    - If a valid token is provided, returns the token payload
    - If no token is provided, returns anonymous token payload (sub=-1, dev="anonymous")

    When auth is enabled (require_auth=True):
    - Requires a valid token, raises 401 if missing or invalid

    Raises:
        HTTPException: 401 if token is missing or invalid (when auth is enabled)
    """
    # Try to get token from either Authorization header or X-Auth-Token header
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = extract_token_from_x_auth_header(x_auth_token)

    # If token is provided, always try to validate it
    if token:
        payload = auth_service.verify_access_token(token)

        if payload is None:
            # Token is invalid - check if we should trust it anyway
            if settings.trust_invalid_tokens:
                # TRUST_INVALID_TOKENS is enabled, try to decode without validation
                payload = auth_service.decode_token_without_validation(token)
                if payload:
                    # Return the payload from the invalid token
                    return payload

            # Token is invalid and we're not trusting invalid tokens
            if settings.require_auth:
                # Auth is enabled, reject invalid token
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                # Auth is disabled, fall through to return anonymous payload
                pass
        else:
            # Token is valid, return the payload
            return payload

    # No token provided or invalid token with auth disabled
    if settings.require_auth:
        # Auth is enabled, token is required
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Auth is disabled, return anonymous token payload
    return TokenPayload(
        sub=-1,
        dev="anonymous",
        scope="MODIFY",
        iat=int(datetime.now(timezone.utc).timestamp()),
        exp=int(datetime.now(timezone.utc).timestamp()) + 3600,
        iss=settings.jwt_issuer,
        aud=settings.jwt_audience,
    )
