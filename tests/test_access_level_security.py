"""Tests to verify access_level is not exposed in API responses and is in JWT scope"""

from uuid import uuid4

import jwt

from app.config import settings
from app.services.auth import AuthService


def test_inspector_api_does_not_expose_access_level(client):
    """Verify that /inspector/all endpoint does not expose access_level field"""
    response = client.get("/inspector/all")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data

    # Check that no inspector in the response has access_level field
    for inspector in data["items"]:
        assert "access_level" not in inspector, (
            f"access_level should not be exposed in API response, but found in inspector {inspector.get('id')}"
        )
        # Verify expected fields are present
        assert "id" in inspector
        assert "username" in inspector
        assert "full_name" in inspector
        assert "is_deleted" in inspector
        assert "server_modified_at" in inspector


def test_jwt_token_contains_scope():
    """Verify that JWT access token contains scope field with access level"""
    auth_service = AuthService()

    # Create a token with MODIFY access level
    device_id = str(uuid4())
    access_token = auth_service.create_access_token(inspector_id=1, device_id=device_id, access_level="MODIFY")

    # Decode the token (without verification for testing)
    decoded = jwt.decode(
        access_token,
        auth_service._public_key,
        algorithms=["RS256"],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )

    # Verify scope field exists and contains the access level
    assert "scope" in decoded, "JWT token should contain 'scope' field"
    assert decoded["scope"] == "MODIFY", f"Expected scope to be 'MODIFY', got '{decoded['scope']}'"

    # Verify other expected fields
    assert "sub" in decoded
    assert "dev" in decoded
    assert "exp" in decoded
    assert "iat" in decoded
    assert "iss" in decoded
    assert "aud" in decoded


def test_jwt_token_scope_variations():
    """Verify JWT tokens can be created with different access levels"""
    auth_service = AuthService()
    device_id = str(uuid4())

    for access_level in ["READ", "INSPECT", "MODIFY"]:
        access_token = auth_service.create_access_token(inspector_id=1, device_id=device_id, access_level=access_level)

        # Decode and verify
        decoded = jwt.decode(
            access_token,
            auth_service._public_key,
            algorithms=["RS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )

        assert decoded["scope"] == access_level, f"Expected scope to be '{access_level}', got '{decoded['scope']}'"
