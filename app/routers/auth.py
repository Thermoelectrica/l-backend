"""Authentication router"""

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db_connection
from app.dependencies.auth import get_current_user
from app.models.auth import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    TokenResponse,
)
from app.models.inspector import Inspector
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
auth_service = AuthService()


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    conn: Annotated[asyncpg.Connection, Depends(get_db_connection)],
):
    """
    Login endpoint - authenticate user and return access and refresh tokens.

    Args:
        request: Login credentials (username, password, device_id)
        conn: Database connection

    Returns:
        LoginResponse with access_token and refresh_token

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    result = await auth_service.login(
        conn,
        username=request.username,
        password=request.password,
        device_id=request.device_id,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return result


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: RefreshRequest,
    conn: Annotated[asyncpg.Connection, Depends(get_db_connection)],
):
    """
    Refresh endpoint - rotate refresh token and return new access and refresh tokens.

    Implements:
    - Token rotation: old token is revoked, new token is issued
    - Theft detection: if revoked token is reused, entire chain is revoked
    - Grace window: allows token reuse within a small time window for race conditions

    Args:
        request: Refresh token request
        conn: Database connection

    Returns:
        RefreshResponse with new access_token and refresh_token

    Raises:
        HTTPException: 401 if refresh token is invalid, expired, or revoked
    """
    result = await auth_service.refresh(conn, refresh_token_string=request.refresh_token)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return result


@router.post("/change-password", response_model=TokenResponse)
async def change_password(
    request: PasswordChangeRequest,
    current_user: Annotated[Inspector, Depends(get_current_user)],
    conn: Annotated[asyncpg.Connection, Depends(get_db_connection)],
):
    """
    Change password endpoint - requires authentication.

    Verifies old password, updates to new password, revokes all existing tokens,
    and returns a new token pair for the specified device.

    Args:
        request: Password change request (old_password, new_password, device_id)
        current_user: Current authenticated user (from JWT token)
        conn: Database connection

    Returns:
        TokenResponse with new access_token and refresh_token

    Raises:
        HTTPException: 409 if old password is invalid
        HTTPException: 401 if not authenticated
    """
    result = await auth_service.change_password(
        conn,
        inspector_id=current_user.id,
        old_password=request.old_password,
        new_password=request.new_password,
        device_id=request.device_id,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invalid old password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return result


@router.get("/check", status_code=status.HTTP_204_NO_CONTENT)
async def check_auth(_current_user: Annotated[Inspector, Depends(get_current_user)]):
    """
    Check authentication endpoint - verifies if the user is authenticated.

    This endpoint is protected by authentication and returns an empty response
    if the user is authenticated. If the user is not authenticated, the
    get_current_user dependency will raise a 401 Unauthorized error.

    Args:
        current_user: Current authenticated user (from JWT token)

    Returns:
        Empty response with 204 No Content status

    Raises:
        HTTPException: 401 if not authenticated
    """
    return None
