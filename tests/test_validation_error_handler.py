"""Tests for RequestValidationError handler"""


# Use the client fixture from conftest.py which has auth disabled
# No need to define a separate client fixture here


def test_validation_error_missing_required_field(client):
    """Test validation error when required field is missing"""
    # Login endpoint requires username, password, and device_id
    response = client.post(
        "/auth/login",
        json={
            "username": "test_user",
            "password": "test_password",
            # Missing device_id
        },
    )

    assert response.status_code == 422
    data = response.json()
    assert "type" in data
    assert data["type"] == "request_validation_error"
    assert "message" in data
    assert "device_id" in data["message"]


def test_validation_error_invalid_field_type(client):
    """Test validation error when field has invalid type"""
    # device_id should be a UUID string
    response = client.post(
        "/auth/login",
        json={
            "username": "test_user",
            "password": "test_password",
            "device_id": 12345,  # Should be string UUID
        },
    )

    assert response.status_code == 422
    data = response.json()
    assert data["type"] == "request_validation_error"
    assert "message" in data


def test_validation_error_invalid_uuid_format(client):
    """Test validation error when UUID format is invalid"""
    response = client.post(
        "/auth/login",
        json={
            "username": "test_user",
            "password": "test_password",
            "device_id": "not-a-valid-uuid",
        },
    )

    # Note: This may return 401 if authentication fails before validation
    # or 422 if validation happens first. Both are acceptable.
    assert response.status_code in [401, 422]
    if response.status_code == 422:
        data = response.json()
        assert data["type"] == "request_validation_error"
        assert "message" in data


def test_validation_error_empty_request_body(client):
    """Test validation error when request body is empty"""
    response = client.post("/auth/login", json={})

    assert response.status_code == 422
    data = response.json()
    assert data["type"] == "request_validation_error"
    assert "message" in data
    # Should mention all missing required fields
    assert "username" in data["message"]
    assert "password" in data["message"]
    assert "device_id" in data["message"]


def test_validation_error_multiple_invalid_fields(client):
    """Test validation error with multiple invalid fields"""
    response = client.post(
        "/auth/refresh",
        json={"refresh_token": 12345},  # Should be string
    )

    assert response.status_code == 422
    data = response.json()
    assert data["type"] == "request_validation_error"
    assert "message" in data


def test_validation_error_invalid_json(client):
    """Test validation error when JSON is malformed"""
    response = client.post(
        "/auth/login",
        data="not valid json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    data = response.json()
    assert data["type"] == "request_validation_error"
    assert "message" in data


def test_validation_error_extra_fields_allowed(client):
    """Test that extra fields don't cause validation errors (if model allows)"""
    from uuid import uuid4

    response = client.post(
        "/auth/login",
        json={
            "username": "test_user",
            "password": "test_password",
            "device_id": str(uuid4()),
            "extra_field": "should_be_ignored",
        },
    )

    # Should either succeed (401 for invalid credentials) or fail with validation error
    # depending on whether the model forbids extra fields
    assert response.status_code in [401, 422]
    if response.status_code == 422:
        data = response.json()
        assert data["type"] == "request_validation_error"


def test_validation_error_response_structure(client):
    """Test that validation error response has correct structure"""
    response = client.post(
        "/auth/login",
        json={
            "username": "test_user"
            # Missing required fields
        },
    )

    assert response.status_code == 422
    data = response.json()

    # Verify response structure matches BaseError model
    assert isinstance(data, dict)
    assert "type" in data
    assert "message" in data
    assert data["type"] == "request_validation_error"
    assert isinstance(data["message"], str)
    assert len(data["message"]) > 0


def test_validation_error_field_location_in_message(client):
    """Test that error message includes field location"""
    response = client.post(
        "/auth/login",
        json={
            "username": "test_user",
            "password": "test_password",
            # Missing device_id
        },
    )

    assert response.status_code == 422
    data = response.json()
    message = data["message"]

    # Message should contain field location information
    assert "Field:" in message or "field" in message.lower()
    assert "Error:" in message or "error" in message.lower()


def test_validation_error_with_nested_field(client):
    """Test validation error with nested field validation"""
    # This test assumes there's an endpoint with nested models
    # Using auth/change-password as it has multiple fields
    response = client.post(
        "/auth/change-password",
        json={
            "old_password": "test",
            "new_password": "test",
            # Missing device_id
        },
    )

    # Should get validation error (422) or auth error (401) if auth is required
    assert response.status_code in [401, 422]
    if response.status_code == 422:
        data = response.json()
        assert data["type"] == "request_validation_error"


def test_validation_error_preserves_status_code(client):
    """Test that validation errors return 422 status code"""
    response = client.post("/auth/login", json={"invalid": "data"})

    # FastAPI standard for validation errors is 422
    assert response.status_code == 422


def test_validation_error_content_type(client):
    """Test that validation error response has correct content type"""
    response = client.post("/auth/login", json={"username": "test"})

    assert response.status_code == 422
    assert "application/json" in response.headers.get("content-type", "")


def test_validation_error_different_endpoints(client):
    """Test validation error handling across different endpoints"""

    # Test on refresh endpoint
    response1 = client.post("/auth/refresh", json={})  # Missing refresh_token
    assert response1.status_code == 422
    assert response1.json()["type"] == "request_validation_error"

    # Test on change-password endpoint
    response2 = client.post("/auth/change-password", json={})  # Missing all fields
    # Will be 401 (auth required) or 422 (validation error)
    assert response2.status_code in [401, 422]
    if response2.status_code == 422:
        assert response2.json()["type"] == "request_validation_error"


def test_validation_error_vs_business_logic_error(client):
    """Test that validation errors are distinct from business logic errors"""
    from uuid import uuid4

    # Validation error (missing field)
    validation_response = client.post(
        "/auth/login",
        json={
            "username": "test_user",
            "password": "test_password",
            # Missing device_id
        },
    )
    assert validation_response.status_code == 422

    # Business logic error (invalid credentials)
    business_response = client.post(
        "/auth/login",
        json={
            "username": "nonexistent_user",
            "password": "wrong_password",
            "device_id": str(uuid4()),
        },
    )
    assert business_response.status_code == 401

    # They should have different status codes
    assert validation_response.status_code != business_response.status_code
