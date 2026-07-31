"""Tests for TRUST_INVALID_TOKENS setting"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
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
def enable_trust_invalid_tokens():
    """Temporarily enable TRUST_INVALID_TOKENS for specific tests"""
    original_value = settings.trust_invalid_tokens
    settings.trust_invalid_tokens = True
    yield
    settings.trust_invalid_tokens = original_value


@pytest.fixture
def test_inspector_data():
    """Test inspector data"""
    return {
        "username": "test_trust_tokens_user",
        "password": "test_password_123",
        "full_name": "Test Trust Tokens Inspector",
    }


@pytest_asyncio.fixture
async def test_inspector(test_inspector_data):
    """Create a test inspector in the database"""
    auth_service = AuthService()
    password_hash = auth_service.hash_password(test_inspector_data["password"])

    # Insert test inspector directly into database
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

    # Cleanup after test
    conn = await asyncpg.connect(settings.get_database_url())
    try:
        await conn.execute("DELETE FROM lesiv.tokens WHERE inspector_id = $1", inspector_id)
        await conn.execute("DELETE FROM lesiv.inspector WHERE id = $1", inspector_id)
    finally:
        await conn.close()


def test_trust_invalid_tokens_with_expired_token(client, test_inspector, enable_auth, enable_trust_invalid_tokens):
    """Test that expired tokens are accepted when TRUST_INVALID_TOKENS=true"""
    auth_service = AuthService()
    device_id = str(uuid4())

    # First login to get a valid token
    login_response = client.post(
        "/auth/login",
        json={
            "username": test_inspector["username"],
            "password": test_inspector["password"],
            "device_id": device_id,
        },
    )
    assert login_response.status_code == 200

    # Create an expired token (expired 2 hours ago)
    with patch("app.services.auth.datetime") as mock_datetime:
        past_time = datetime.now(timezone.utc) - timedelta(hours=2)
        mock_datetime.now.return_value = past_time
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        expired_token = auth_service.create_access_token(
            inspector_id=test_inspector["id"],
            device_id=device_id,
            access_level="MODIFY",
        )

    # Verify the token is actually expired
    payload = auth_service.verify_access_token(expired_token)
    assert payload is None, "Token should be expired and invalid"

    # Test with TRUST_INVALID_TOKENS=true (already enabled by fixture)
    # The expired token should be accepted
    response = client.get("/plant/all", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 200, (
        f"Should accept expired token when TRUST_INVALID_TOKENS=true, got {response.status_code}: {response.text}"
    )


def test_trust_invalid_tokens_disabled_rejects_expired_token(client, test_inspector, enable_auth):
    """Test that expired tokens are rejected when TRUST_INVALID_TOKENS=false"""
    auth_service = AuthService()
    device_id = str(uuid4())

    # Ensure TRUST_INVALID_TOKENS is disabled
    settings.trust_invalid_tokens = False

    # Create an expired token
    with patch("app.services.auth.datetime") as mock_datetime:
        past_time = datetime.now(timezone.utc) - timedelta(hours=2)
        mock_datetime.now.return_value = past_time
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        expired_token = auth_service.create_access_token(
            inspector_id=test_inspector["id"],
            device_id=device_id,
            access_level="MODIFY",
        )

    # Verify the token is expired
    payload = auth_service.verify_access_token(expired_token)
    assert payload is None, "Token should be expired"

    # Test with TRUST_INVALID_TOKENS=false
    # The expired token should be rejected
    response = client.get("/plant/all", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401, "Should reject expired token when TRUST_INVALID_TOKENS=false"


def test_trust_invalid_tokens_with_valid_token(client, test_inspector, enable_auth, enable_trust_invalid_tokens):
    """Test that valid tokens still work normally with TRUST_INVALID_TOKENS=true"""
    device_id = str(uuid4())

    # Login to get a valid token
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

    # Valid token should work with TRUST_INVALID_TOKENS=true
    response = client.get("/plant/all", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200, "Valid token should work with TRUST_INVALID_TOKENS=true"


@pytest.mark.asyncio
async def test_decode_token_without_validation():
    """Test that decode_token_without_validation works correctly"""
    auth_service = AuthService()

    # Create an expired token
    with patch("app.services.auth.datetime") as mock_datetime:
        past_time = datetime.now(timezone.utc) - timedelta(hours=2)
        mock_datetime.now.return_value = past_time
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        expired_token = auth_service.create_access_token(
            inspector_id=123, device_id="test-device", access_level="MODIFY"
        )

    # Verify normal validation fails
    payload = auth_service.verify_access_token(expired_token)
    assert payload is None, "Normal validation should fail for expired token"

    # Verify decode without validation succeeds
    payload = auth_service.decode_token_without_validation(expired_token)
    assert payload is not None, "Decode without validation should succeed"
    assert payload.sub == 123, "Should extract correct inspector ID"
    assert payload.dev == "test-device", "Should extract correct device ID"
    assert payload.scope == "MODIFY", "Should extract correct access level"


@pytest.mark.asyncio
async def test_decode_token_without_validation_with_malformed_token():
    """Test that decode_token_without_validation fails with completely malformed tokens"""
    auth_service = AuthService()

    malformed_token = "this.is.not.a.valid.jwt.token"

    # Both methods should fail with malformed token
    payload = auth_service.verify_access_token(malformed_token)
    assert payload is None, "Normal validation should fail for malformed token"

    payload = auth_service.decode_token_without_validation(malformed_token)
    assert payload is None, "Decode without validation should also fail for malformed token"
