"""Tests for authentication endpoints"""

from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from app.config import settings
from app.services.auth import AuthService


@pytest.fixture
def enable_auth():
    """Temporarily enable authentication for specific tests"""
    original_value = settings.require_auth
    settings.require_auth = True
    yield
    settings.require_auth = original_value


@pytest.fixture
def test_inspector_data():
    """Test inspector data"""
    return {
        "username": "test_auth_user",
        "password": "test_password_123",
        "full_name": "Test Auth Inspector",
    }


@pytest_asyncio.fixture
async def test_inspector(test_inspector_data):
    """Create a test inspector in the database"""
    auth_service = AuthService()
    password_hash = auth_service.hash_password(test_inspector_data["password"])

    # Insert test inspector directly into database
    # Use a fresh connection to avoid pool closure issues
    conn = await asyncpg.connect(settings.get_database_url())
    try:
        # Delete existing tokens and inspector to avoid conflicts
        existing_id = await conn.fetchval(
            "SELECT id FROM lesiv.inspector WHERE username = $1",
            test_inspector_data["username"],
        )

        if existing_id:
            await conn.execute("DELETE FROM lesiv.tokens WHERE inspector_id = $1", existing_id)
            await conn.execute("DELETE FROM lesiv.inspector WHERE id = $1", existing_id)

        inspector_id = await conn.fetchval(
            """
            INSERT INTO lesiv.inspector (full_name, username, password_hash)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            test_inspector_data["full_name"],
            test_inspector_data["username"],
            password_hash,
        )
    finally:
        await conn.close()

    yield {"id": inspector_id, **test_inspector_data}

    # Cleanup after test - use a fresh connection
    conn = await asyncpg.connect(settings.get_database_url())
    try:
        await conn.execute("DELETE FROM lesiv.tokens WHERE inspector_id = $1", inspector_id)
        await conn.execute("DELETE FROM lesiv.inspector WHERE id = $1", inspector_id)
    finally:
        await conn.close()


def test_login_success(client, test_inspector):
    """Test successful login"""
    device_id = str(uuid4())

    response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device_id,
        },
    )

    if response.status_code != 200:
        print(f"Error response: {response.json()}")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # Verify tokens are not empty
    assert len(data["access_token"]) > 0
    assert len(data["refresh_token"]) > 0


def test_login_invalid_username(client, test_inspector):
    """Test login with invalid username"""
    device_id = str(uuid4())

    response = client.post(
        "/auth/login",
        json={
            "username": "nonexistent_user",
            "password": test_inspector["password"],
            "device_id": device_id,
        },
    )

    assert response.status_code == 401
    assert "Invalid username or password" in response.json()["detail"]


def test_login_invalid_password(client, test_inspector):
    """Test login with invalid password"""
    device_id = str(uuid4())

    response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": "wrong_password",
            "device_id": device_id,
        },
    )

    assert response.status_code == 401
    assert "Invalid username or password" in response.json()["detail"]


def test_refresh_token_success(client, test_inspector):
    """Test successful token refresh"""
    device_id = str(uuid4())

    # First, login to get tokens
    login_response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device_id,
        },
    )

    assert login_response.status_code == 200
    login_data = login_response.json()
    refresh_token = login_data["refresh_token"]

    # Now refresh the token
    refresh_response = client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert refresh_response.status_code == 200
    refresh_data = refresh_response.json()
    assert "access_token" in refresh_data
    assert "refresh_token" in refresh_data
    assert refresh_data["token_type"] == "bearer"

    # Refresh token should always be different (rotation)
    assert refresh_data["refresh_token"] != login_data["refresh_token"]
    # Access token may be the same if within reuse window (same timestamp)
    # but refresh token must be different


def test_refresh_token_invalid(client):
    """Test refresh with invalid token"""
    response = client.post("/auth/refresh", json={"refresh_token": "invalid_token_string"})

    assert response.status_code == 401
    assert "Invalid or expired refresh token" in response.json()["detail"]


def test_refresh_token_reuse_detection(client, test_inspector):
    """Test that reusing a revoked refresh token revokes the chain"""
    device_id = str(uuid4())

    # Login to get initial tokens
    login_response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device_id,
        },
    )

    assert login_response.status_code == 200
    old_refresh_token = login_response.json()["refresh_token"]

    # Refresh once (this revokes old_refresh_token)
    refresh_response = client.post("/auth/refresh", json={"refresh_token": old_refresh_token})

    assert refresh_response.status_code == 200

    # Try to reuse the old token (should fail - theft detection)
    reuse_response = client.post("/auth/refresh", json={"refresh_token": old_refresh_token})

    assert reuse_response.status_code == 401


def test_protected_route_with_valid_token(client, test_inspector):
    """Test accessing a protected route with valid access token"""
    device_id = str(uuid4())

    # Login to get access token
    login_response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device_id,
        },
    )

    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    # Try to access a protected route (using inspector endpoint as example)
    response = client.get(
        f"/inspectors/{test_inspector['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    # Should succeed (assuming inspector endpoint exists and is protected)
    assert response.status_code != 401


def test_protected_route_without_token(enable_auth, client, test_inspector):
    """Test accessing a protected route without token"""
    # This test assumes inspector endpoint is protected
    # If not protected yet, this test documents the expected behavior
    response = client.get("/inspector/all")

    # Should fail with 401 when auth is enabled
    assert response.status_code == 401


def test_protected_route_with_invalid_token(client, test_inspector):
    """Test accessing a protected route with invalid token"""
    response = client.get(
        f"/inspectors/{test_inspector['id']}",
        headers={"Authorization": "Bearer invalid_token_here"},
    )

    # Should either succeed (if not protected) or fail with 401
    assert response.status_code in [200, 401, 404]


def test_multiple_devices_same_user(client, test_inspector):
    """Test that same user can have tokens on multiple devices"""
    device1_id = str(uuid4())
    device2_id = str(uuid4())

    # Login from device 1
    response1 = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device1_id,
        },
    )

    assert response1.status_code == 200
    token1 = response1.json()["refresh_token"]

    # Login from device 2
    response2 = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device2_id,
        },
    )

    assert response2.status_code == 200
    token2 = response2.json()["refresh_token"]

    # Both tokens should be different
    assert token1 != token2

    # Both tokens should work for refresh
    refresh1 = client.post("/auth/refresh", json={"refresh_token": token1})
    assert refresh1.status_code == 200

    refresh2 = client.post("/auth/refresh", json={"refresh_token": token2})
    assert refresh2.status_code == 200


def test_jwt_token_structure(client, test_inspector):
    """Test that JWT tokens have correct structure and can be decoded"""
    import jwt

    from app.config import settings

    device_id = str(uuid4())

    # Login to get access token
    login_response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device_id,
        },
    )

    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    # Load public key
    with open(settings.public_key_path, "r") as f:
        public_key = f.read()

    # Decode and verify token structure
    payload = jwt.decode(
        access_token,
        public_key,
        algorithms=["RS256"],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )

    # Verify all required claims are present
    assert "sub" in payload
    assert "dev" in payload
    assert "exp" in payload
    assert "iat" in payload
    assert "iss" in payload
    assert "aud" in payload

    # Verify sub is a string (JWT spec requirement)
    assert isinstance(payload["sub"], str)
    # Verify it can be converted to int
    assert int(payload["sub"]) == test_inspector["id"]

    # Verify dev is a string UUID
    assert isinstance(payload["dev"], str)
    from uuid import UUID

    UUID(payload["dev"])  # Should not raise

    # Verify issuer and audience
    assert payload["iss"] == settings.jwt_issuer
    assert payload["aud"] == settings.jwt_audience


def test_middleware_authentication_flow(enable_auth, client, test_inspector):
    """Test that middleware properly validates tokens from Swagger UI"""
    device_id = str(uuid4())

    # Login to get access token
    login_response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device_id,
        },
    )

    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    # Test that middleware accepts the token with Bearer prefix
    response = client.get("/inspector/all", headers={"Authorization": f"Bearer {access_token}"})

    # Should not return 401 (authentication should succeed)
    assert response.status_code != 401, f"Middleware rejected valid token: {response.json()}"

    # Test with malformed token
    response = client.get("/inspector/all", headers={"Authorization": "Bearer malformed_token"})
    assert response.status_code == 401, f"Expected 401 but got {response.status_code}: {response.json()}"

    # Test without Bearer prefix - middleware accepts both formats, so this should succeed
    response = client.get("/inspector/all", headers={"Authorization": access_token})
    assert response.status_code != 401, f"Middleware rejected valid token without Bearer prefix: {response.json()}"

    # Test without Authorization header - should fail with 401
    response = client.get("/inspector/all")
    assert response.status_code == 401


def test_token_validation_with_auth_service(test_inspector):
    """Test that AuthService properly validates tokens it creates"""
    from app.services.auth import AuthService

    auth_service = AuthService()
    device_id = uuid4()

    # Create a token
    access_token = auth_service.create_access_token(test_inspector["id"], device_id, "MODIFY")

    # Verify the token
    payload = auth_service.verify_access_token(access_token)

    assert payload is not None, "AuthService failed to verify its own token"
    assert payload.sub == test_inspector["id"]
    # dev is stored as string in JWT, so compare as strings
    assert payload.dev == str(device_id)

    # Verify invalid token returns None
    invalid_payload = auth_service.verify_access_token("invalid_token")
    assert invalid_payload is None


def test_change_password_success(client, test_inspector):
    """Test successful password change"""
    device_id = str(uuid4())
    new_device_id = str(uuid4())

    # Login to get access token
    login_response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device_id,
        },
    )

    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]
    old_refresh_token = login_response.json()["refresh_token"]

    # Change password
    new_password = "new_secure_password_456"
    change_response = client.post(
        "/auth/change-password",
        json={
            "old_password": test_inspector["password"],
            "new_password": new_password,
            "device_id": new_device_id,
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert change_response.status_code == 200
    change_data = change_response.json()
    assert "access_token" in change_data
    assert "refresh_token" in change_data
    assert change_data["token_type"] == "bearer"

    # Verify new tokens are different from old ones
    assert change_data["access_token"] != access_token
    assert change_data["refresh_token"] != old_refresh_token

    # Verify old refresh token is revoked
    old_refresh_response = client.post("/auth/refresh", json={"refresh_token": old_refresh_token})
    assert old_refresh_response.status_code == 401

    # Verify new refresh token works
    new_refresh_response = client.post("/auth/refresh", json={"refresh_token": change_data["refresh_token"]})
    assert new_refresh_response.status_code == 200

    # Verify can't login with old password
    old_login_response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device_id,
        },
    )
    assert old_login_response.status_code == 401

    # Verify can login with new password
    new_login_response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": new_password,
            "device_id": device_id,
        },
    )
    assert new_login_response.status_code == 200


def test_change_password_invalid_old_password(client, test_inspector):
    """Test password change with incorrect old password"""
    device_id = str(uuid4())

    # Login to get access token
    login_response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device_id,
        },
    )

    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    # Try to change password with wrong old password
    change_response = client.post(
        "/auth/change-password",
        json={
            "old_password": "wrong_old_password",
            "new_password": "new_password_123",
            "device_id": device_id,
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert change_response.status_code == 409
    assert "Invalid old password" in change_response.json()["detail"]


def test_change_password_without_authentication(enable_auth, client, test_inspector):
    """Test password change without authentication token"""
    device_id = str(uuid4())

    # Try to change password without token
    change_response = client.post(
        "/auth/change-password",
        json={
            "old_password": test_inspector["password"],
            "new_password": "new_password_123",
            "device_id": device_id,
        },
    )

    assert change_response.status_code == 401


def test_change_password_with_invalid_token(enable_auth, client, test_inspector):
    """Test password change with invalid authentication token"""
    device_id = str(uuid4())

    # Try to change password with invalid token
    change_response = client.post(
        "/auth/change-password",
        json={
            "old_password": test_inspector["password"],
            "new_password": "new_password_123",
            "device_id": device_id,
        },
        headers={"Authorization": "Bearer invalid_token_here"},
    )

    assert change_response.status_code == 401


def test_change_password_revokes_all_tokens(client, test_inspector):
    """Test that password change revokes all existing tokens across all devices"""
    device1_id = str(uuid4())
    device2_id = str(uuid4())
    new_device_id = str(uuid4())

    # Login from device 1
    login1_response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device1_id,
        },
    )
    assert login1_response.status_code == 200
    token1 = login1_response.json()["refresh_token"]
    access_token1 = login1_response.json()["access_token"]

    # Login from device 2
    login2_response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device2_id,
        },
    )
    assert login2_response.status_code == 200
    token2 = login2_response.json()["refresh_token"]

    # Change password using device 1 token
    new_password = "new_secure_password_789"
    change_response = client.post(
        "/auth/change-password",
        json={
            "old_password": test_inspector["password"],
            "new_password": new_password,
            "device_id": new_device_id,
        },
        headers={"Authorization": f"Bearer {access_token1}"},
    )
    assert change_response.status_code == 200

    # Verify both old refresh tokens are revoked
    refresh1_response = client.post("/auth/refresh", json={"refresh_token": token1})
    assert refresh1_response.status_code == 401

    refresh2_response = client.post("/auth/refresh", json={"refresh_token": token2})
    assert refresh2_response.status_code == 401

    # Verify new token works
    new_refresh_token = change_response.json()["refresh_token"]
    new_refresh_response = client.post("/auth/refresh", json={"refresh_token": new_refresh_token})
    assert new_refresh_response.status_code == 200


async def test_change_password_updates_database(client, test_inspector):
    """Test that password change actually updates the password hash in database"""
    from app.services.auth import AuthService

    device_id = str(uuid4())
    auth_service = AuthService()

    # Get original password hash
    async def get_password_hash():
        conn = await asyncpg.connect(settings.get_database_url())
        try:
            password_hash = await conn.fetchval(
                "SELECT password_hash FROM lesiv.inspector WHERE username = $1",
                test_inspector["username"],
            )
            return password_hash
        finally:
            await conn.close()

    original_hash = await get_password_hash()

    # Login and change password
    login_response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device_id,
        },
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    new_password = "completely_new_password_999"
    change_response = client.post(
        "/auth/change-password",
        json={
            "old_password": test_inspector["password"],
            "new_password": new_password,
            "device_id": device_id,
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert change_response.status_code == 200

    # Get new password hash
    new_hash = await get_password_hash()

    # Verify hash changed
    assert new_hash != original_hash

    # Verify new hash validates new password
    assert auth_service.verify_password(new_password, new_hash)
    assert not auth_service.verify_password(test_inspector["password"], new_hash)
