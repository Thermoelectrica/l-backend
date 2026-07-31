"""Ownership validation dependency"""

from fastapi import Depends

from app.database import get_db_connection
from app.dependencies.auth import get_current_user, get_token_payload
from app.models.auth import TokenPayload
from app.models.inspector import Inspector
from app.services.ownership_validator import OwnershipValidator


def get_ownership_validator(
    conn=Depends(get_db_connection),
    current_user: Inspector = Depends(get_current_user),
    token_payload: TokenPayload = Depends(get_token_payload),
) -> OwnershipValidator:
    """Dependency to provide OwnershipValidator instance with current user and device_id"""
    return OwnershipValidator(conn, current_user, token_payload.dev)
