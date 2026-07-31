"""Integration tests for Inspector API"""

from fastapi.testclient import TestClient


def test_get_all_inspectors(client: TestClient):
    """Test retrieving all inspectors"""
    response = client.get("/inspector/all")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    items = data["items"]

    # Should have at least 3 inspectors
    assert len(items) >= 3

    # Verify structure of first item
    assert all(key in items[0] for key in ["id", "full_name", "username", "server_modified_at"])

    # Verify password_hash is NOT included
    assert "password_hash" not in items[0]


def test_inspector_data_structure(client: TestClient):
    """Test that inspectors have correct data structure"""
    response = client.get("/inspector/all")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Find inspector with id 1
    inspector = next((item for item in items if item["id"] == 1), None)
    assert inspector is not None

    # Verify all required fields are present
    assert "id" in inspector
    assert "full_name" in inspector
    assert "username" in inspector
    assert "server_modified_at" in inspector

    # Verify password_hash is NOT exposed
    assert "password_hash" not in inspector


def test_multiple_inspectors(client: TestClient):
    """Test that multiple inspectors are returned"""
    response = client.get("/inspector/all")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Should have multiple inspectors
    assert len(items) >= 3

    # Verify different inspectors have different data
    ids = [item["id"] for item in items]
    assert len(ids) == len(set(ids)), "Inspector IDs should be unique"

    usernames = [item["username"] for item in items]
    assert len(usernames) == len(set(usernames)), "Usernames should be unique"


def test_inspector_no_password_exposure(client: TestClient):
    """Test that password_hash is never exposed in the API"""
    response = client.get("/inspector/all")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Verify none of the inspectors have password_hash field
    for inspector in items:
        assert "password_hash" not in inspector, "password_hash should not be exposed"
        assert "password" not in inspector, "password should not be exposed"


# Tests for modified_since filter


def test_get_all_inspectors_with_modified_since_filter(client: TestClient):
    """Test filtering inspectors by modified_since parameter"""
    # Note: Inspectors are seeded data, so we can't easily create new ones with different timestamps
    # This test verifies the parameter works without errors

    # Get all inspectors without filter
    response = client.get("/inspector/all")
    assert response.status_code == 200
    all_inspectors = response.json()["items"]
    assert len(all_inspectors) >= 3

    # Get inspectors with a very old timestamp - should return all
    response = client.get("/inspector/all?modified_since=1900-01-01T00:00:00Z")
    assert response.status_code == 200
    filtered_inspectors = response.json()["items"]
    assert len(filtered_inspectors) >= 3

    # Get inspectors with a future timestamp - should return none
    response = client.get("/inspector/all?modified_since=2099-12-31T23:59:59Z")
    assert response.status_code == 200
    filtered_inspectors = response.json()["items"]
    assert len(filtered_inspectors) == 0
