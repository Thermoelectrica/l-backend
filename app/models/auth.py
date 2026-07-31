"""Authentication models"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.inspector import AccessLevel


class Token(BaseModel):
    """Refresh token stored in database"""

    id: UUID
    inspector_id: int
    device_id: str
    token_hash: str
    expires_at: datetime
    revoked: bool
    replaced_by_id: UUID | None
    used_at: datetime | None
    created_at: datetime


class LoginRequest(BaseModel):
    """Login request payload"""

    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    device_id: str


class TokenResponse(BaseModel):
    """Login response with tokens"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Refresh token request payload"""

    refresh_token: str = Field(..., min_length=1)


class TokenPayload(BaseModel):
    """JWT token payload"""

    sub: int  # inspector_id
    dev: str  # device id
    scope: str  # access level (READ, INSPECT, MODIFY)
    exp: int  # expiration time
    iat: int  # issued at time
    iss: str  # issuer
    aud: str  # audience


class InspectorWithPassword(BaseModel):
    """Inspector with password hash - Internal use only (for authentication)"""

    id: int
    full_name: str
    username: str
    password_hash: str
    access_level: AccessLevel = AccessLevel.READ
    server_modified_at: datetime


class PasswordChangeRequest(BaseModel):
    """Request for a password change"""

    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=1)
    device_id: str
