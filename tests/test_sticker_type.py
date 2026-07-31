"""Integration tests for StickerType API"""

from fastapi.testclient import TestClient


def test_get_all_sticker_types(client: TestClient):
    """Test retrieving all sticker types"""
    response = client.get("/sticker-type/all")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    items = data["items"]

    # Should have 10 sticker types from V3 migration
    assert len(items) == 10

    # Verify structure of first item
    assert all(key in items[0] for key in ["id", "name", "is_deleted", "server_modified_at", "temp_ranges"])


# Tests for modified_since filter


def test_get_all_sticker_types_with_modified_since_filter(client: TestClient):
    """Test filtering sticker types by modified_since parameter"""
    # Note: Sticker types are seeded data, so we can't easily create new ones with different timestamps
    # This test verifies the parameter works without errors

    # Get all sticker types without filter
    response = client.get("/sticker-type/all")
    assert response.status_code == 200
    all_types = response.json()["items"]
    assert len(all_types) == 10

    # Get sticker types with a very old timestamp - should return all
    response = client.get("/sticker-type/all?modified_since=1900-01-01T00:00:00Z")
    assert response.status_code == 200
    filtered_types = response.json()["items"]
    assert len(filtered_types) == 10

    # Get sticker types with a future timestamp - should return none
    response = client.get("/sticker-type/all?modified_since=2099-12-31T23:59:59Z")
    assert response.status_code == 200
    filtered_types = response.json()["items"]
    assert len(filtered_types) == 0
